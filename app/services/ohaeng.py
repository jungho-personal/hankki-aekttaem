"""
오행 매핑, 상생/상극, 처방 타입 결정 (핸드오프 4-3, 4-4장)

처방 규칙은 서비스 자체 규칙이며 명리 정설이 아님 (재미용).
"""

# ===== 천간 → 오행 =====
GAN_OHAENG = {
    "갑": "목", "을": "목",
    "병": "화", "정": "화",
    "무": "토", "기": "토",
    "경": "금", "신": "금",
    "임": "수", "계": "수",
}

# ===== 오행 표기용 한자 =====
OHAENG_HANJA = {"목": "木", "화": "火", "토": "土", "금": "金", "수": "水"}

# ===== 오색/오미 대응 (핸드오프 4-3, 4-5장) =====
# color / taste: LLM 프롬프트에 넘기는 기준 이름
# color_adj / taste_adj: fallback 문구에서 "___ 음식" 형태로 쓰는 표현
OHAENG_ATTR = {
    "목": {"color": "초록", "taste": "신맛", "color_adj": "초록빛", "taste_adj": "새콤한"},
    "화": {"color": "빨강", "taste": "쓴맛", "color_adj": "빨간", "taste_adj": "쌉싸름한"},
    "토": {"color": "노랑", "taste": "단맛", "color_adj": "노란", "taste_adj": "달달한"},
    "금": {"color": "흰색", "taste": "매운맛", "color_adj": "흰", "taste_adj": "매운"},
    "수": {"color": "검정", "taste": "짠맛", "color_adj": "검은", "taste_adj": "짭짤한"},
}

# ===== 상생 관계: key가 value를 생(生)함 =====
SANGSAENG = {"목": "화", "화": "토", "토": "금", "금": "수", "수": "목"}

# ===== 상극 관계: key가 value를 극(剋)함 =====
SANGGEUK = {"목": "토", "토": "수", "수": "화", "화": "금", "금": "목"}

# ===== 처방 타입 =====
PRESCRIPTION_AEKTTAEM = "액땜"
PRESCRIPTION_BOOST = "부스트"
PRESCRIPTION_BOYANG = "보양"


def gan_to_ohaeng(gan: str) -> str:
    """천간 한 글자 → 오행 (예: "병" → "화")"""
    return GAN_OHAENG[gan]


def label(ohaeng: str) -> str:
    """표시용 라벨 (예: "화" → "화(火)")"""
    return f"{ohaeng}({OHAENG_HANJA[ohaeng]})"


def generator_of(ohaeng: str) -> str:
    """ohaeng을 생(生)해주는 오행 (예: 화를 생하는 건 목)"""
    return next(k for k, v in SANGSAENG.items() if v == ohaeng)


def controller_of(ohaeng: str) -> str:
    """ohaeng을 극(剋)하는 오행 (예: 화를 극하는 건 수)"""
    return next(k for k, v in SANGGEUK.items() if v == ohaeng)


def get_prescription(my_ohaeng: str, today_ohaeng: str) -> dict:
    """
    사용자 일간 오행과 오늘 일진 오행을 비교해 처방 타입을 결정한다. (핸드오프 4-4장 그대로)

    Args:
        my_ohaeng: 사용자 일간의 오행 (목/화/토/금/수)
        today_ohaeng: 오늘 일진 천간의 오행

    Returns:
        {"type": 처방 타입, "target_ohaeng": 먹어야 할 오행}
    """
    # 1) 오늘 기운이 나를 극함 → 나를 생해주는 오행으로 액땜
    if SANGGEUK[today_ohaeng] == my_ohaeng:
        return {"type": PRESCRIPTION_AEKTTAEM, "target_ohaeng": generator_of(my_ohaeng)}

    # 2) 오늘 기운이 나를 생해줌 → 그 기운 그대로 부스트
    if SANGSAENG[today_ohaeng] == my_ohaeng:
        return {"type": PRESCRIPTION_BOOST, "target_ohaeng": today_ohaeng}

    # 3) 그 외 → 내 오행 강화 (보양)
    return {"type": PRESCRIPTION_BOYANG, "target_ohaeng": my_ohaeng}


def get_avoid_ohaeng(target_ohaeng: str) -> str:
    """
    "피해야 할 메뉴"의 오행 = 대상 오행을 극하는 오행 (핸드오프 4-5장)
    예) 대상이 목이면 금(금극목) 기운 메뉴를 피한다.
    """
    return controller_of(target_ohaeng)
