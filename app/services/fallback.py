"""
LLM 실패/미설정 시 룰 기반 밥괘 생성 (핸드오프 4-5장, 5-2장 3번, 12-2장 3단계)

- 메뉴: LLM에 넘기는 것과 같은 후보(candidates.menu_candidates) 중 첫 번째
- 선택은 결정적(deterministic): 같은 (일간, 버킷, 날짜, 끼니)면 항상 같은 메뉴
  → 캐시가 없어도, 서버가 재시작돼도 fallback 결과는 동일
- 문구: 템플릿 고정 문구
"""
from app.data.fallback_menu import LUCKY_SIDE_DISH, ORACLE_BY_TODAY
from app.schemas import BapgwaeContext, BapgwaeResult
from app.services.candidates import avoid_candidates, menu_candidates, seed_of
from app.services.text_util import euro as _euro
from app.services.text_util import josa as _josa
from app.services.ohaeng import (
    OHAENG_ATTR,
    PRESCRIPTION_AEKTTAEM,
    PRESCRIPTION_BOOST,
    label,
)


def pick(items: list, seed: int):
    """리스트에서 seed 기반으로 하나 선택"""
    return items[seed % len(items)]


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
    seed = seed_of(ctx)
    target = ctx.target_ohaeng
    attr = OHAENG_ATTR[target]

    # 1) 먹을 메뉴: LLM과 같은 후보 중 첫 번째 (대상 오행 × 끼니 칸)
    menu, basis = menu_candidates(ctx)[0]

    # 2) 피해야 할 메뉴: 대상 오행을 극하는 오행 × 같은 끼니 칸의 첫 후보
    avoid_menu, _ = avoid_candidates(ctx)[0]

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
        lucky_side_dish=pick(LUCKY_SIDE_DISH[target], seed),
        avoid_menu=avoid_menu,
        avoid_reason=f"{label(ctx.avoid_ohaeng)} 기운이 오늘 그대에게 필요한 {label(target)} 기운을 누르니 멀리하시게",
    )
