"""
Pydantic 모델: API 요청/응답 (핸드오프 6장) + 서비스 내부 컨텍스트
"""
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

# ===== 공통 타입 =====
MealKey = Literal["breakfast", "brunch", "lunch", "snack", "dinner", "late_night"]
CalendarType = Literal["solar", "lunar"]
BasisType = Literal["color", "taste"]


# ===== 요청 =====
class BapgwaeRequest(BaseModel):
    """
    POST /api/bapgwae 요청

    birth_date를 date 타입이 아닌 문자열로 받는 이유:
    음력에는 "2월 30일"처럼 양력에 없는 날짜가 있어서, date로 받으면 정상 음력 입력이 422로 튕긴다.
    형식만 여기서 검사하고 실제 날짜 유효성은 양력/음력에 맞춰 서비스에서 검사한다.
    """

    birth_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", examples=["1995-03-15"])
    calendar: CalendarType = "solar"
    is_leap_month: bool = False  # 음력일 때만 의미 있음. 양력이면 무시
    meal: Optional[MealKey] = None  # null이면 KST 시각으로 자동 판별


# ===== 응답 =====
class BapgwaeResult(BaseModel):
    """밥괘 본문 (LLM 출력 스키마와 동일. fallback도 같은 구조로 채운다)"""

    menu: str
    chosen_basis: BasisType
    basis_comment: str
    ohaeng_reason: str
    oracle: str
    message: str
    lucky_side_dish: str
    avoid_menu: str
    avoid_reason: str


class OfferingSlot(BaseModel):
    """
    공양 슬롯 중 코드(광고 DB)가 채우는 부분 (핸드오프 11-3장)
    LLM은 여기에 손대지 않고 comment만 따로 만든다.
    """

    sponsor_name: str
    menu: str
    disclosure: str  # 광고 표기 문구 (코드 고정)
    link: str        # 없으면 "" → 프론트가 링크를 그리지 않음
    is_demo: bool    # 시연용 예시 여부 → 프론트 표기 "[광고 예시]" / "[광고]"


class Offering(OfferingSlot):
    """
    공양 슬롯 응답 (핸드오프 6장 구조 + is_demo)
    노출할 광고가 없으면 응답의 offering은 null.
    """

    comment: str  # 식신 멘트 (LLM 생성, 실패 시 고정 문구)


class OfferingCommentOutput(BaseModel):
    """공양 멘트 LLM 출력 스키마 (밥괘와 별도 호출)"""

    comment: str


class BapgwaeResponse(BaseModel):
    """POST /api/bapgwae 응답"""

    meal: MealKey
    meal_label: str
    today_iljin: str
    my_ilgan: str
    my_ohaeng: str
    today_ohaeng: str
    prescription_type: str
    target_ohaeng: str
    result: BapgwaeResult
    offering: Optional[Offering] = None
    is_fallback: bool
    is_cached: bool


# ===== 서비스 내부 컨텍스트 =====
class BapgwaeContext(BaseModel):
    """
    코드(서버)가 계산한 값 묶음. LLM 프롬프트와 fallback 문구 생성에 같은 값을 넘긴다.
    (사용자 생년월일 원본은 넣지 않음 — 캐시 키와 동일하게 일간/버킷/날짜/끼니에서 파생되는 값만)
    """

    today: date
    meal: MealKey
    meal_label: str
    my_ilgan: str
    bucket: int = 0  # 생년월일 버킷 (candidates.person_bucket). 메뉴 후보 시드 + 캐시 키
    today_iljin: str
    my_ohaeng: str
    today_ohaeng: str
    prescription_type: str
    target_ohaeng: str
    avoid_ohaeng: str
