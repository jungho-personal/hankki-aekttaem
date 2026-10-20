"""
공양 슬롯: 광고 선택 + 표기 문구 + 고정 멘트 (핸드오프 11-3장)

설계 원칙
- 밥괘(오행 결과)와 완전 분리: 밥괘가 확정된 뒤에 공양을 고르고, 밥괘 메뉴에는 영향을 주지 않는다.
- 광고주/메뉴/링크/표기 문구는 코드(app/data/offerings.py)가 정한다.
- LLM은 식신 멘트(comment)만 만든다 (llm.generate_offering_comment). 실패 시 고정 문구.

노출 규칙
- 실제 광고주(SPONSORS) 중 해당 끼니 광고가 있으면 그것을 사용
- 없고 OFFERING_DEMO=true면 시연용 예시(DEMO_SPONSORS)를 "[광고 예시]"로 사용
- 둘 다 없으면 None → 응답 offering = null
"""
import os
from typing import Optional

from app.data.offerings import DEMO_SPONSORS, FALLBACK_COMMENTS, SPONSORS
from app.schemas import BapgwaeContext, Offering, OfferingSlot
from app.services.fallback import pick, seed_of
from app.services.text_util import josa

# 시연용 예시 광고 표기 (실제 광고로 오인되지 않게 고정)
DEMO_DISCLOSURE = "시연용 예시입니다. 실제 광고가 아니며 광고비를 받지 않았습니다"


def is_demo_enabled() -> bool:
    """OFFERING_DEMO 환경변수가 true/1/yes면 시연용 예시 광고 노출"""
    return os.getenv("OFFERING_DEMO", "").strip().lower() in ("1", "true", "yes")


def build_disclosure(sponsor_name: str, is_demo: bool) -> str:
    """
    광고 표기 문구 (공정위 지침 취지: 경제적 이해관계를 명확한 표현으로 공개 — 핸드오프 11-3장)
    예) "이 추천은 식신치킨으로부터 광고비를 받았습니다"
    """
    if is_demo:
        return DEMO_DISCLOSURE
    return f"이 추천은 {josa(sponsor_name, '으로부터', '로부터', rieul_as_without=True)} 광고비를 받았습니다"


def select_offering_slot(ctx: BapgwaeContext) -> Optional[OfferingSlot]:
    """
    끼니에 맞는 광고 1개를 고른다. 같은 (일간, 날짜, 끼니)면 항상 같은 광고 (결정적 선택).
    """
    # 1) 실제 광고주 우선
    candidates = [s for s in SPONSORS if ctx.meal in s["meals"]]
    is_demo = False

    # 2) 실제 광고가 없을 때만 시연용 예시
    if not candidates and is_demo_enabled():
        candidates = [s for s in DEMO_SPONSORS if ctx.meal in s["meals"]]
        is_demo = True

    if not candidates:
        return None

    sponsor = pick(candidates, seed_of(ctx))
    return OfferingSlot(
        sponsor_name=sponsor["sponsor_name"],
        menu=sponsor["menu"],
        disclosure=build_disclosure(sponsor["sponsor_name"], is_demo),
        link=sponsor.get("link", ""),
        is_demo=is_demo,
    )


def fallback_comment(slot: OfferingSlot, ctx: BapgwaeContext) -> str:
    """LLM 멘트를 못 받았을 때 쓰는 고정 멘트 (핸드오프 2-3장 바리에이션 중 결정적 선택)"""
    return pick(FALLBACK_COMMENTS, seed_of(ctx)).format(sponsor=slot.sponsor_name)


def build_offering(slot: OfferingSlot, comment: str) -> Offering:
    """코드가 채운 슬롯 + 멘트 → 응답용 Offering"""
    return Offering(**slot.model_dump(), comment=comment)
