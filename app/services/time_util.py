"""
KST 시간 처리 + 끼니 판별

주의 (핸드오프 5-2장 1번)
- Railway 서버는 UTC일 가능성이 높다. datetime.now()를 그대로 쓰면
  KST 00:00~08:59에 "어제" 날짜로 계산되므로, 모든 날짜/끼니 판별은 반드시 KST로 변환 후 한다.
"""
from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

# ===== 타임존 =====
KST = ZoneInfo("Asia/Seoul")

# ===== 끼니 정의 (핸드오프 3장) =====
# (키, 한글 라벨, 시작 시각) — 시작 시각 오름차순. 각 끼니는 다음 끼니 시작 직전까지.
# 야식(22:00~04:59)은 자정을 넘기므로 "22:00 이후 또는 05:00 이전"으로 따로 판별한다.
MEALS = [
    ("breakfast", "아침", time(5, 0)),
    ("brunch", "아점", time(10, 0)),
    ("lunch", "점심", time(11, 30)),
    ("snack", "간식", time(14, 30)),
    ("dinner", "저녁", time(17, 30)),
    ("late_night", "야식", time(22, 0)),
]

# 키 → 한글 라벨
MEAL_LABELS = {key: label for key, label, _ in MEALS}

# 허용되는 끼니 키 목록
MEAL_KEYS = [key for key, _, _ in MEALS]

# 끼니별 톤 / 메뉴 성격 (핸드오프 3장 표 그대로) — LLM 프롬프트에 넘겨 끼니마다 메뉴가 갈리게 한다
MEAL_GUIDE = {
    "breakfast": {"tone": "하루 기운 여는", "menu_style": "가볍고 따뜻한 것"},
    "brunch": {"tone": "게으름 용서", "menu_style": "브런치, 간단식"},
    "lunch": {"tone": "오후 버티기", "menu_style": "정식, 면, 덮밥"},
    "snack": {"tone": "당 충전", "menu_style": "디저트, 분식"},
    "dinner": {"tone": "하루 액땜 마무리", "menu_style": "고기, 찌개, 안주"},
    "late_night": {"tone": "죄책감 사면", "menu_style": "배달 야식류"},
}


def now_kst(now: Optional[datetime] = None) -> datetime:
    """
    현재 시각을 KST(aware datetime)로 반환한다.

    Args:
        now: 테스트용 주입 시각. None이면 실제 현재 시각.
             tz 정보가 없는(naive) 값이면 UTC로 간주한다 (서버 기본 시각이 UTC라는 가정).
    """
    if now is None:
        now = datetime.now(tz=KST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=ZoneInfo("UTC"))
    return now.astimezone(KST)


def today_kst(now: Optional[datetime] = None) -> date:
    """KST 기준 오늘 날짜 (일진 계산 기준일. 자정 기준 — 핸드오프 5-1장)"""
    return now_kst(now).date()


def detect_meal(now: Optional[datetime] = None) -> str:
    """
    KST 시각으로 끼니 키를 판별한다.

    판별 순서
    1) 야식: 22:00 이후 또는 05:00 이전 (자정 넘김 구간이라 OR 조건)
    2) 나머지: 시작 시각이 현재 시각 이하인 끼니 중 가장 늦은 것
    """
    t = now_kst(now).time()

    # 1) 야식 구간 (22:00 ~ 23:59, 00:00 ~ 04:59)
    late_start = MEALS[-1][2]   # 22:00
    first_start = MEALS[0][2]   # 05:00
    if t >= late_start or t < first_start:
        return "late_night"

    # 2) 05:00 ~ 21:59 구간: 시작 시각을 지난 끼니 중 마지막
    current = MEALS[0][0]
    for key, _, start in MEALS[:-1]:
        if t >= start:
            current = key
    return current


def next_kst_midnight(now: Optional[datetime] = None) -> datetime:
    """다음 KST 자정 시각 (캐시 만료 시각)"""
    tomorrow = today_kst(now) + timedelta(days=1)
    return datetime.combine(tomorrow, time(0, 0), tzinfo=KST)
