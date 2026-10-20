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

from app.schemas import BapgwaeContext, BapgwaeResult, OfferingCommentOutput, OfferingSlot
from app.services.candidates import avoid_candidates, menu_candidates
from app.services.ohaeng import OHAENG_ATTR, label
from app.services.time_util import MEAL_GUIDE

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
1. menu는 입력의 "메뉴 후보" 중 하나를 골라 이름을 그대로 적는다. 후보에 없는 메뉴를 지어내지 않는다.
   오늘 일진과 처방 이야기에 가장 잘 어울리는 후보를 고른다.
2. 각 후보 옆 괄호는 그 메뉴가 대상 오행의 "색"과 "맛" 중 무엇을 만족하는지다.
   고른 후보의 기준을 chosen_basis에 "color"(색) 또는 "taste"(맛)로 적는다.
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
8. avoid_menu: 입력의 "피해야 할 메뉴 후보" 중 하나를 이름 그대로 적는다. avoid_reason은 식신 말투 한 줄.
9. 과도한 비하/혐오 표현 금지. 의학적/건강 효능을 단정하는 표현 금지.
10. 모든 값은 한국어로, 각 문장은 한두 줄 이내로 짧게.
"""


BASIS_LABEL = {"color": "색", "taste": "맛"}


def format_candidates(candidates: list) -> str:
    """[("비빔밥", "color"), ...] → "비빔밥(색), ..." """
    return ", ".join(f"{menu}({BASIS_LABEL[basis]})" for menu, basis in candidates)


def build_prompt(ctx: BapgwaeContext) -> str:
    """
    컨텍스트(서버 계산값)를 LLM 입력 텍스트로 만든다 (핸드오프 7장 입력값)
    메뉴는 코드가 뽑은 후보 중에서만 고르게 한다 (자유 선택 시 뻔한 메뉴로 쏠림 방지)
    """
    target_attr = OHAENG_ATTR[ctx.target_ohaeng]
    avoid_attr = OHAENG_ATTR[ctx.avoid_ohaeng]
    meal_guide = MEAL_GUIDE[ctx.meal]
    return f"""\
오늘의 밥괘를 내려주시게.

- 끼니: {ctx.meal_label} (톤: {meal_guide['tone']}, 끼니 메뉴 성격: {meal_guide['menu_style']})
- 사용자 일간 오행(본래 기운): {label(ctx.my_ohaeng)}
- 오늘 일진: {ctx.today_iljin}일, 오늘 일진 오행: {label(ctx.today_ohaeng)}
- 처방 타입: {ctx.prescription_type}
- 대상 오행(먹어야 할 기운): {label(ctx.target_ohaeng)} — 색: {target_attr['color']}, 맛: {target_attr['taste']}
- 피해야 할 오행: {label(ctx.avoid_ohaeng)} — 색: {avoid_attr['color']}, 맛: {avoid_attr['taste']}
- 메뉴 후보: {format_candidates(menu_candidates(ctx))}
- 피해야 할 메뉴 후보: {format_candidates(avoid_candidates(ctx))}
"""


def _call_json(system_instruction: str, prompt: str, schema) -> str:
    """
    Gemini를 JSON 스키마 고정 모드로 호출하고 응답 텍스트를 반환한다. (밥괘/공양 멘트 공통)

    Raises:
        LLMError: 키 미설정, 네트워크/한도 초과/타임아웃 등 호출 실패
    """
    if not is_enabled():
        raise LLMError("GEMINI_API_KEY 미설정")

    try:
        from google.genai import types

        response = _get_client().models.generate_content(
            model=get_model_name(),
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=schema,  # JSON 출력 스키마 고정
            ),
        )
    except Exception as e:  # SDK 예외 종류가 다양해서 전부 fallback 신호로 변환
        raise LLMError(f"Gemini 호출 실패: {type(e).__name__}: {e}") from e

    return response.text


def generate_bapgwae(ctx: BapgwaeContext) -> BapgwaeResult:
    """
    Gemini로 밥괘 결과를 생성한다.

    Raises:
        LLMError: 키 미설정, 네트워크/한도 초과/타임아웃, JSON 스키마 불일치 등 모든 실패
    """
    result = parse_response_text(_call_json(SYSTEM_INSTRUCTION, build_prompt(ctx), BapgwaeResult))
    # 후보 밖 메뉴는 실패로 보지 않고 기록만 한다 (표기 차이 "김치찌개" vs "돼지 김치찌개" 정도는 허용)
    if result.menu not in [m for m, _ in menu_candidates(ctx)]:
        logger.warning("LLM이 후보 밖 메뉴 선택: %s (후보: %s)", result.menu, format_candidates(menu_candidates(ctx)))
    return result


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


# ===== 공양 멘트 (핸드오프 11-3장: LLM은 comment만 생성) =====
# 밥괘와 별도 호출로 분리한 이유: 밥괘 메뉴가 먼저 확정된 뒤에 광고 정보를 넘기므로
# 광고가 밥괘 메뉴 선택에 섞여 들어갈 여지가 없다 ("밥괘와 공양 슬롯 완전 분리" 원칙).
OFFERING_SYSTEM_INSTRUCTION = """\
너는 "식신(食神)"이다. 노인 도사 말투("~하시게", "~구먼", "~다네")를 쓴다.
오늘 너에게 공양(광고비)을 올린 가게가 있어서, 밥괘와는 별개로 그 가게 메뉴를 "대안"으로 가볍게 권하는 멘트를 한다.

규칙
1. comment는 한두 문장, 60자 이내로 짧게.
2. 가게 이름과 메뉴는 입력에 주어진 그대로만 쓴다. 다른 가게나 메뉴를 지어내지 않는다.
3. 공양을 받았다는 사실을 숨기지 않고 능청스럽게 드러낸다.
   예) "흠, 공양이 정성스러우니 밥괘가 영 내키지 않거든 이 집도 한번 맛보시게~"
   예) "공양을 받았으니 모른 척할 수가 없구먼. ○○도 괜찮다네~"
   예) "식신도 먹고살아야 하지 않겠는가. ○○ 한번 들러보시게~"
4. 공양 메뉴가 오늘 운이나 오행에 맞는다고 주장하지 않는다. 밥괘 메뉴보다 낫다고 하지 않는다.
5. 의학적/건강 효능 단정 금지. 비하/혐오 표현 금지.
6. "[광고]" 같은 표기 문구는 쓰지 않는다 (화면에서 따로 붙인다).
"""


def build_offering_prompt(slot: OfferingSlot, ctx: BapgwaeContext, bapgwae_menu: str) -> str:
    """공양 멘트 입력 텍스트. 밥괘 메뉴는 이미 확정된 값을 참고로만 넘긴다."""
    return f"""\
공양 멘트를 내려주시게.

- 끼니: {ctx.meal_label}
- 오늘의 밥괘 메뉴(이미 확정됨, 바꾸지 말 것): {bapgwae_menu}
- 공양 올린 가게: {slot.sponsor_name}
- 공양 메뉴: {slot.menu}
"""


def generate_offering_comment(slot: OfferingSlot, ctx: BapgwaeContext, bapgwae_menu: str) -> str:
    """
    공양 슬롯 식신 멘트를 생성한다.

    Raises:
        LLMError: 호출 실패, 스키마 불일치, 빈 멘트
    """
    text = _call_json(OFFERING_SYSTEM_INSTRUCTION, build_offering_prompt(slot, ctx, bapgwae_menu), OfferingCommentOutput)
    if not text:
        raise LLMError("공양 멘트 응답이 비어 있음")
    try:
        comment = OfferingCommentOutput.model_validate_json(text).comment.strip()
    except ValidationError as e:
        raise LLMError(f"공양 멘트 스키마 불일치: {e}") from e
    if not comment:
        raise LLMError("공양 멘트가 빈 문자열")
    return comment
