"""
만세력: 음력→양력 변환, 일간/일진 계산 (lunar_python 사용)

1단계에서 실제 설치·실행으로 확인한 사항 (lunar_python 1.4.8)
- 양력 → 일진: Solar.fromYmd(y, m, d).getLunar().getDayGanIndex() / getDayZhiIndex()
  (index 0~9 / 0~11. 문자열 메서드 getDayGan()은 한자 "甲"을 반환하므로 index로 한글 매핑)
- 음력 → 양력: Lunar.fromYmd(y, m, d).getSolar()
- 윤달: 음수 월로 표현. 예) 2023년 윤2월 1일 = Lunar.fromYmd(2023, -2, 1) → 2023-03-22
- 존재하지 않는 음력 날짜(윤달 없는 해의 윤달, 일수 초과 등)는 Exception 발생
- 일진: 1920~2049 전 구간에서 한국천문연구원 기준(korean_lunar_calendar)과 불일치 0건
- 알려진 한계: 음력 날짜는 중국 음력(UTC+8) 기준이라 한국 음력과 하루씩 어긋나는 달이 있음
  (1920~2049 중 1,768일). 사용자 결정으로 lunar_python 그대로 사용 (핸드오프 5-1장).

일진 기준: 자정 (자시 23시 기준 아님 — 핸드오프 5-1장). 시각은 00:00:00으로 고정 계산.
"""
from datetime import date

from lunar_python import Lunar, Solar

# ===== 천간/지지 한글 (lunar_python index 순서와 동일) =====
GAN_KO = ("갑", "을", "병", "정", "무", "기", "경", "신", "임", "계")
ZHI_KO = ("자", "축", "인", "묘", "진", "사", "오", "미", "신", "유", "술", "해")


class InvalidDateError(ValueError):
    """존재하지 않는 양력/음력 날짜"""


def lunar_to_solar(year: int, month: int, day: int, is_leap_month: bool) -> date:
    """
    음력 날짜를 양력 date로 변환한다.

    Args:
        year, month, day: 음력 년/월/일 (month는 1~12 양수)
        is_leap_month: 윤달 여부. True면 lunar_python 규칙대로 음수 월로 넘긴다.

    Raises:
        InvalidDateError: 해당 해에 그 윤달이 없거나, 일수가 범위를 벗어난 경우
    """
    if not 1 <= month <= 12:
        raise InvalidDateError(f"음력 월은 1~12여야 합니다: {month}")

    lunar_month = -month if is_leap_month else month
    try:
        solar = Lunar.fromYmd(year, lunar_month, day).getSolar()
    except Exception as e:  # lunar_python은 범용 Exception을 던짐
        leap_text = "윤" if is_leap_month else ""
        raise InvalidDateError(f"존재하지 않는 음력 날짜입니다: {year}년 {leap_text}{month}월 {day}일") from e

    return date(solar.getYear(), solar.getMonth(), solar.getDay())


def get_day_pillar(d: date) -> tuple:
    """
    양력 날짜의 일주(日柱) = (천간, 지지) 한글을 반환한다.
    - 사용자 생일에 쓰면: 천간이 "일간(日干)"
    - 오늘 날짜에 쓰면: 오늘의 "일진(日辰)"
    """
    lunar = Solar.fromYmd(d.year, d.month, d.day).getLunar()
    return GAN_KO[lunar.getDayGanIndex()], ZHI_KO[lunar.getDayZhiIndex()]


def get_ilgan(birth_solar: date) -> str:
    """사용자 일간(日干) 한 글자 (예: "병")"""
    return get_day_pillar(birth_solar)[0]


def get_iljin(today: date) -> str:
    """오늘 일진 두 글자 (예: "갑자")"""
    gan, zhi = get_day_pillar(today)
    return gan + zhi
