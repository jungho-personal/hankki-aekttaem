"""
공양 슬롯(광고) 데이터 = "광고 DB" (핸드오프 11-3장)

원칙
- 광고주/메뉴/링크/표기 문구는 여기(코드)가 정한다. LLM이 광고주를 고르거나 지어내면 안 됨.
- LLM은 식신 멘트(comment)만 만든다.

필드
- sponsor_name: 가게 이름 (표시 그대로)
- menu: 공양 메뉴
- meals: 노출할 끼니 키 목록 (breakfast/brunch/lunch/snack/dinner/late_night)
- link: 가게 링크. 없으면 "" (프론트가 링크를 그리지 않음)
"""

# ===== 실제 광고주 (계약된 광고주만 등록. 현재 없음) =====
SPONSORS: list = []

# ===== 시연용 예시 광고주 (OFFERING_DEMO=true일 때만 노출) =====
# 전부 가상의 가게. 실제 상호와 겹치지 않게 세계관 이름으로 지었다.
# 노출 시 표기는 "[광고 예시]" + "실제 광고가 아닌 시연용 예시" 문구로 고정된다.
DEMO_SPONSORS: list = [
    {"sponsor_name": "새벽국밥집", "menu": "콩나물국밥", "meals": ["breakfast"], "link": ""},
    {"sponsor_name": "게으름브런치", "menu": "에그베네딕트", "meals": ["brunch"], "link": ""},
    {"sponsor_name": "오행반점", "menu": "차돌짬뽕", "meals": ["lunch"], "link": ""},
    {"sponsor_name": "쩝쩝분식", "menu": "로제떡볶이", "meals": ["snack"], "link": ""},
    {"sponsor_name": "식신치킨", "menu": "간장치킨", "meals": ["dinner", "late_night"], "link": ""},
    {"sponsor_name": "액땜족발", "menu": "불족발", "meals": ["dinner", "late_night"], "link": ""},
]

# ===== 공양 멘트 고정 문구 (LLM 실패/미설정 시. 핸드오프 2-3장 바리에이션) =====
# {sponsor}: 가게 이름
FALLBACK_COMMENTS: list = [
    "흠, 공양이 정성스러우니 밥괘가 영 내키지 않거든 이 집도 한번 맛보시게~",
    "공양을 받았으니 모른 척할 수가 없구먼. {sponsor}도 괜찮다네~",
    "식신도 먹고살아야 하지 않겠는가. {sponsor} 한번 들러보시게~",
    "이 집 사장님이 향을 아주 정성껏 피웠다네~",
]
