"""
Gemini 호출 + JSON 파싱 (핸드오프 4-1장 LLM 역할, 7장 프롬프트 설계)

- LLM은 메뉴 선택 + 문구 생성만 담당. 만세력/오행/처방은 서버가 계산해서 넘긴다.
- 출력은 JSON 스키마 고정 (BapgwaeResult). 스키마 검증에 실패하면 LLMError → fallback.
- GEMINI_API_KEY가 없으면 비활성 (is_enabled() == False) → 호출 없이 fallback.

환경변수 (핸드오프 12-3장)
- GEMINI_API_KEY: 없으면 fallback 모드
- GEMINI_MODEL: 모델명. 없으면 DEFAULT_MODEL
- GEMINI_TIMEOUT_SEC: 호출 타임아웃(초). 없으면 DEFAULT_TIMEOUT_SEC (시연 중 무응답 방지)
"""
import logging
import os
from typing import Optional

from pydantic import ValidationError

from app.schemas import BapgwaeContext, BapgwaeResult
from app.services.ohaeng import OHAENG_ATTR, label

logger = logging.getLogger("hankki.llm")

# ===== 설정 기본값 =====
# 기본 모델: gemini-3.5-flash-lite (2026-10-20 사용자 확정)
# - 공식 문서상 새 프로젝트 권장 모델 중 하나, Stable
# - 기본 thinking이 minimal이라 응답이 빠름 (시연/타임아웃 유리)
# - 단가 입력 $0.30 / 출력 $2.50 per 1M → 하루 상한 60회 기준 월 약 8천원 이내 (추정)
# 다른 모델을 쓰려면 코드 수정 없이 GEMINI_MODEL 환경변수로 덮어쓴다
DEFAULT_MODEL = "gemini-3.5-flash-lite"
DEFAULT_TIMEOUT_SEC = 15

# ===== 클라이언트 (최초 호출 시 1회 생성) =====
_client = None


class LLMError(Exception):
    """LLM 호출/파싱 실패 (호출부에서 fallback으로 전환하는 신호)"""


def get_api_key() -> Optional[str]:
    """API 키 (빈 문자열은 미설정으로 취급)"""
    key = os.getenv("GEMINI_API_KEY", "").strip()
    return key or None


def get_model_name() -> str:
    """사용할 모델명"""
    return os.getenv("GEMINI_MODEL", "").strip() or DEFAULT_MODEL


def get_timeout_sec() -> float:
    """호출 타임아웃(초). 잘못된 값이면 기본값"""
    try:
        return float(os.getenv("GEMINI_TIMEOUT_SEC", DEFAULT_TIMEOUT_SEC))
    except ValueError:
        return DEFAULT_TIMEOUT_SEC


def is_enabled() -> bool:
    """LLM 사용 가능 여부 = API 키 설정 여부"""
    return get_api_key() is not None


def _get_client():
    """Gemini 클라이언트 지연 생성. SDK import도 여기서 해서 키 없는 환경의 기동 부담을 줄인다"""
    global _client
    if _client is None:
        from google import genai
        from google.genai import types

        _client = genai.Client(
            api_key=get_api_key(),
            # HttpOptions.timeout 단위는 밀리초 (SDK 소스로 확인)
            http_options=types.HttpOptions(timeout=int(get_timeout_sec() * 1000)),
        )
    return _client


# ===== 프롬프트 =====
SYSTEM_INSTRUCTION = """\
너는 "식신(食神)"이다. 사람들에게 오늘의 끼니 "밥괘"를 내려주는 존재다.
말투는 노인 도사 말투("~하시게", "~하리라", "~로다", "~구만")를 쓴다.
재미용 엔터테인먼트 서비스이며 정통 명리 해석이 아니다.

규칙
1. 메뉴는 해당 끼니에 한국에서 대중적으로 사 먹을 수 있는 메뉴 1개만 고른다.
2. 대상 오행의 "색" 또는 "맛" 중 하나를 골라, 메뉴 자체가 그 기준을 만족해야 한다. 둘 다 만족해도 된다.
   고른 기준을 chosen_basis에 "color" 또는 "taste"로 적는다.
3. basis_comment는 반드시 이 형식을 따른다:
   "흠.. 오늘은 [안 고른 기준] 음식을 내려주고 싶다만, 네 운을 보아하니 [고른 기준] 음식이 더 좋겠구만"
   예) 화, 색 선택: "흠.. 오늘은 쓴맛 음식을 내려주고 싶다만, 네 운을 보아하니 빨간 음식이 더 좋겠구만"
   예) 금, 맛 선택: "흠.. 오늘은 흰 음식을 내려주고 싶다만, 네 운을 보아하니 매운 음식이 더 좋겠구만"
4. ohaeng_reason: 이 메뉴가 왜 대상 오행에 맞는지 식신 말투로 한 줄.
5. oracle: 오늘 일진 기운을 해석한 신탁 한 줄. 직장인 공감 밈(상사, 회의, 야근 등)을 섞어도 좋다.
6. message: 처방 타입에 맞는 문장 구조를 쓴다.
   - 액땜: "이 [메뉴]로 [나쁜 기운]을 액땜하시게"
   - 부스트: "[메뉴]로 [부족한 기운]을 끌어올리시게"
   - 보양: "[메뉴]로 [본래 기운]을 든든히 채우시게"
7. lucky_side_dish: 대상 오행과 어울리는 흔한 반찬 1개.
8. avoid_menu: "피해야 할 오행"의 색 또는 맛에 해당하는, 같은 끼니의 대중 메뉴 1개. avoid_reason은 식신 말투 한 줄.
9. 과도한 비하/혐오 표현 금지. 의학적/건강 효능을 단정하는 표현 금지.
10. 모든 값은 한국어로, 각 문장은 한두 줄 이내로 짧게.
"""


def build_prompt(ctx: BapgwaeContext) -> str:
    """컨텍스트(서버 계산값)를 LLM 입력 텍스트로 만든다 (핸드오프 7장 입력값)"""
    target_attr = OHAENG_ATTR[ctx.target_ohaeng]
    avoid_attr = OHAENG_ATTR[ctx.avoid_ohaeng]
    return f"""\
오늘의 밥괘를 내려주시게.

- 끼니: {ctx.meal_label}
- 사용자 일간 오행(본래 기운): {label(ctx.my_ohaeng)}
- 오늘 일진: {ctx.today_iljin}일, 오늘 일진 오행: {label(ctx.today_ohaeng)}
- 처방 타입: {ctx.prescription_type}
- 대상 오행(먹어야 할 기운): {label(ctx.target_ohaeng)} — 색: {target_attr['color']}, 맛: {target_attr['taste']}
- 피해야 할 오행: {label(ctx.avoid_ohaeng)} — 색: {avoid_attr['color']}, 맛: {avoid_attr['taste']}
"""


def generate_bapgwae(ctx: BapgwaeContext) -> BapgwaeResult:
    """
    Gemini로 밥괘 결과를 생성한다.

    Raises:
        LLMError: 키 미설정, 네트워크/한도 초과/타임아웃, JSON 스키마 불일치 등 모든 실패
    """
    if not is_enabled():
        raise LLMError("GEMINI_API_KEY 미설정")

    try:
        from google.genai import types

        response = _get_client().models.generate_content(
            model=get_model_name(),
            contents=build_prompt(ctx),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=BapgwaeResult,  # JSON 출력 스키마 고정
            ),
        )
    except Exception as e:  # SDK 예외 종류가 다양해서 전부 fallback 신호로 변환
        raise LLMError(f"Gemini 호출 실패: {type(e).__name__}: {e}") from e

    return parse_response_text(response.text)


def parse_response_text(text: Optional[str]) -> BapgwaeResult:
    """
    LLM 응답 텍스트(JSON)를 BapgwaeResult로 검증한다.
    스키마를 지정해도 빈 응답/필드 누락이 있을 수 있어서 서버에서 한 번 더 검증한다.
    """
    if not text:
        raise LLMError("Gemini 응답이 비어 있음")
    try:
        result = BapgwaeResult.model_validate_json(text)
    except ValidationError as e:
        raise LLMError(f"Gemini 응답 스키마 불일치: {e}") from e

    # 빈 문자열 필드 방지 (스키마상 str이라 ""도 통과하므로)
    empty = [name for name, value in result.model_dump().items() if isinstance(value, str) and not value.strip()]
    if empty:
        raise LLMError(f"Gemini 응답에 빈 필드: {empty}")
    return result
