"""
LLM 실패/미설정 시 룰 기반 밥괘 생성 (핸드오프 4-5장, 5-2장 3번, 12-2장 3단계)

- 메뉴: 오행 × 끼니 30칸 표에서 선택
- 선택은 결정적(deterministic): 같은 (일간, 날짜, 끼니)면 항상 같은 메뉴
  → 캐시가 없어도, 서버가 재시작돼도 fallback 결과는 동일
- 문구: 템플릿 고정 문구
"""
from app.data.fallback_menu import FALLBACK_MENU, LUCKY_SIDE_DISH, ORACLE_BY_TODAY
from app.schemas import BapgwaeContext, BapgwaeResult
from app.services.manseryeok import GAN_KO
from app.services.ohaeng import (
    OHAENG_ATTR,
    PRESCRIPTION_AEKTTAEM,
    PRESCRIPTION_BOOST,
    label,
)


def _seed(ctx: BapgwaeContext) -> int:
    """
    결정적 선택용 정수. Python 내장 hash()는 프로세스마다 값이 바뀌므로 쓰지 않는다.
    날짜 서수 + 일간 index → 날마다, 일간마다 다른 칸이 골라진다.
    """
    return ctx.today.toordinal() + GAN_KO.index(ctx.my_ilgan)


def _pick(items: list, seed: int):
    """리스트에서 seed 기반으로 하나 선택"""
    return items[seed % len(items)]


def _josa(word: str, with_batchim: str, without_batchim: str, rieul_as_without: bool = False) -> str:
    """
    받침에 맞는 조사를 붙인다. 예) 김밥+은/는 → 김밥은, 요거트+은/는 → 요거트는
    rieul_as_without: (으)로처럼 ㄹ받침이면 받침 없는 쪽을 쓰는 조사 (예: 냉모밀로)
    한글이 아닌 끝 글자는 받침 없음으로 처리
    """
    last = word[-1]
    if not "가" <= last <= "힣":
        return word + without_batchim
    jong = (ord(last) - ord("가")) % 28  # 0이면 받침 없음, 8이면 ㄹ
    if jong == 0 or (rieul_as_without and jong == 8):
        return word + without_batchim
    return word + with_batchim


def _euro(word: str) -> str:
    """(으)로 — 예) 김치볶음밥으로, 요거트로, 냉모밀로"""
    return _josa(word, "으로", "로", rieul_as_without=True)


def build_basis_comment(target_ohaeng: str, chosen_basis: str) -> str:
    """
    식신 선택 멘트 (핸드오프 4-5장 형식)
    "흠.. 오늘은 [안 고른 기준] 음식을 내려주고 싶다만, 네 운을 보아하니 [고른 기준] 음식이 더 좋겠구만"
    """
    attr = OHAENG_ATTR[target_ohaeng]
    chosen = attr["color_adj"] if chosen_basis == "color" else attr["taste_adj"]
    other = attr["taste_adj"] if chosen_basis == "color" else attr["color_adj"]
    return f"흠.. 오늘은 {other} 음식을 내려주고 싶다만, 네 운을 보아하니 {chosen} 음식이 더 좋겠구만"


def build_message(ctx: BapgwaeContext, menu: str) -> str:
    """처방 타입별 문구 (핸드오프 2-2장 템플릿)"""
    if ctx.prescription_type == PRESCRIPTION_AEKTTAEM:
        return f"이 {_euro(menu)} 오늘 그대를 누르는 {label(ctx.today_ohaeng)} 기운을 액땜하시게"
    if ctx.prescription_type == PRESCRIPTION_BOOST:
        return f"{_euro(menu)} 오늘 들어온 {label(ctx.target_ohaeng)} 기운을 끌어올리시게"
    return f"{_euro(menu)} 본래의 {label(ctx.my_ohaeng)} 기운을 든든히 채우시게"


def build_fallback_result(ctx: BapgwaeContext) -> BapgwaeResult:
    """컨텍스트로 룰 기반 밥괘 결과를 만든다"""
    seed = _seed(ctx)
    target = ctx.target_ohaeng
    attr = OHAENG_ATTR[target]

    # 1) 먹을 메뉴: 대상 오행 × 끼니 칸에서 선택
    menu, basis = _pick(FALLBACK_MENU[target][ctx.meal], seed)

    # 2) 피해야 할 메뉴: 대상 오행을 극하는 오행 × 같은 끼니 칸에서 선택
    avoid_menu, _ = _pick(FALLBACK_MENU[ctx.avoid_ohaeng][ctx.meal], seed)

    # 3) 오행 근거: 고른 기준(색/맛)을 그대로 설명
    basis_word = f"색({attr['color']})" if basis == "color" else f"맛({attr['taste']})"
    ohaeng_reason = f"{_josa(menu, '은', '는')} {label(target)}의 {basis_word}을 품은 음식이로다"

    return BapgwaeResult(
        menu=menu,
        chosen_basis=basis,
        basis_comment=build_basis_comment(target, basis),
        ohaeng_reason=ohaeng_reason,
        oracle=ORACLE_BY_TODAY[ctx.today_ohaeng],
        message=build_message(ctx, menu),
        lucky_side_dish=_pick(LUCKY_SIDE_DISH[target], seed),
        avoid_menu=avoid_menu,
        avoid_reason=f"{label(ctx.avoid_ohaeng)} 기운이 오늘 그대에게 필요한 {label(target)} 기운을 누르니 멀리하시게",
    )
