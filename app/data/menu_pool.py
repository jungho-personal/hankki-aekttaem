"""
오행 × 끼니 메뉴 후보 풀 — LLM 후보 제시 + fallback 공용

- 요청마다 (일간, 사람 버킷, 날짜, 끼니) 시드로 이 풀에서 후보 몇 개를 뽑아 LLM에 넘기고,
  LLM은 그중 하나를 골라 문구를 쓴다. LLM이 실패하면 fallback이 첫 번째 후보를 쓴다.
  (LLM에게 자유 선택을 맡기면 "초록 → 비빔밥", "빨강 → 김치찌개"처럼 뻔한 메뉴로 쏠려서 풀로 다양성을 강제)
- 각 메뉴에 어떤 기준(color=색 / taste=맛)으로 그 오행에 넣었는지 붙여둔다.
- 끼니 메뉴 성격(time_util.MEAL_GUIDE)에 맞는 대중 메뉴만 넣는다.
- 규칙: 같은 끼니에서 X 오행 칸과 "X를 극하는 오행" 칸은 메뉴가 겹치면 안 된다
  (먹을 메뉴와 피해야 할 메뉴가 같아지는 것 방지 — tests/test_core.py에서 검사)
"""

# MENU_POOL[오행][끼니] = [(메뉴, 기준), ...]
MENU_POOL = {
    "목": {  # 초록 / 신맛
        "breakfast": [
            ("야채죽", "color"), ("그린 스무디", "color"), ("시금치 된장국", "color"), ("아보카도 토스트", "color"),
            ("매생이국", "color"), ("브로콜리 수프", "color"), ("쑥국", "color"), ("플레인 요거트볼", "taste"),
        ],
        "brunch": [
            ("샐러드", "color"), ("아보카도 샌드위치", "color"), ("시저 샐러드", "color"), ("바질 페스토 파스타", "color"),
            ("포케", "color"), ("시금치 프리타타", "color"), ("레몬 크림 파스타", "taste"), ("그릭요거트볼", "taste"),
        ],
        "lunch": [
            ("비빔밥", "color"), ("쌈밥", "color"), ("열무국수", "color"), ("곤드레밥", "color"), ("쌀국수", "color"),
            ("냉모밀", "taste"), ("물냉면", "taste"), ("비빔냉면", "taste"), ("초계국수", "taste"), ("탕수육", "taste"),
        ],
        "snack": [
            ("녹차 아이스크림", "color"), ("말차 라떼", "color"), ("말차 롤케이크", "color"), ("쑥떡", "color"),
            ("키위 스무디", "color"), ("요거트", "taste"), ("레몬 마들렌", "taste"), ("레몬에이드", "taste"),
            ("새콤달콤 과일컵", "taste"),
        ],
        "dinner": [
            ("샤브샤브", "color"), ("월남쌈", "color"), ("미나리 삼겹살", "color"), ("부추전", "color"),
            ("냉채족발", "taste"), ("골뱅이무침", "taste"), ("물회", "taste"), ("유린기", "taste"), ("해파리냉채", "taste"),
        ],
        "late_night": [
            ("쫄면", "taste"), ("비빔국수", "taste"), ("골뱅이소면", "taste"), ("냉채족발", "taste"),
            ("탕수육", "taste"), ("유린기", "taste"), ("물냉면", "taste"), ("회무침", "taste"),
        ],
    },
    "화": {  # 빨강 / 쓴맛
        "breakfast": [
            ("토마토 스프", "color"), ("토마토 달걀볶음", "color"), ("김치죽", "color"), ("김치콩나물국", "color"),
            ("딸기 스무디", "color"), ("샥슈카", "color"), ("냉이된장국", "taste"), ("아메리카노와 베이글", "taste"),
        ],
        "brunch": [
            ("김치볶음밥", "color"), ("토마토 파스타", "color"), ("샥슈카", "color"), ("라자냐", "color"),
            ("김치전", "color"), ("마르게리타 피자", "color"), ("로제 파스타", "color"),
        ],
        "lunch": [
            ("제육볶음", "color"), ("김치찌개", "color"), ("순두부찌개", "color"), ("오징어덮밥", "color"),
            ("육개장", "color"), ("부대찌개", "color"), ("김치볶음밥", "color"), ("토마토 스파게티", "color"),
        ],
        "snack": [
            ("떡볶이", "color"), ("라볶이", "color"), ("딸기 탕후루", "color"), ("딸기 케이크", "color"),
            ("딸기 빙수", "color"), ("티라미수", "taste"), ("다크초콜릿", "taste"), ("아포가토", "taste"),
        ],
        "dinner": [
            ("닭갈비", "color"), ("육개장", "color"), ("닭볶음탕", "color"), ("김치찜", "color"), ("쭈꾸미볶음", "color"),
            ("낙곱새", "color"), ("고추장 삼겹살", "color"), ("아귀찜", "color"),
        ],
        "late_night": [
            ("불닭볶음면", "color"), ("닭발", "color"), ("떡볶이", "color"), ("양념치킨", "color"),
            ("쭈꾸미볶음", "color"), ("오돌뼈", "color"), ("페퍼로니 피자", "color"), ("낙지볶음", "color"),
        ],
    },
    "토": {  # 노랑 / 단맛
        "breakfast": [
            ("호박죽", "color"), ("계란토스트", "color"), ("계란찜", "color"), ("콘스프", "color"),
            ("스크램블 에그", "color"), ("프렌치토스트", "taste"), ("찐 고구마", "taste"),
        ],
        "brunch": [
            ("오므라이스", "color"), ("에그 베네딕트", "color"), ("에그 샌드위치", "color"),
            ("팬케이크", "taste"), ("프렌치토스트", "taste"), ("크로플", "taste"), ("허니버터 브레드", "taste"),
        ],
        "lunch": [
            ("카레라이스", "color"), ("돈까스", "color"), ("계란볶음밥", "color"), ("텐동", "color"),
            ("불고기덮밥", "taste"), ("규동", "taste"), ("데리야끼 치킨덮밥", "taste"), ("함박스테이크", "taste"),
            ("잡채밥", "taste"),
        ],
        "snack": [
            ("계란빵", "color"), ("카스테라", "color"), ("바나나 우유", "color"), ("에그타르트", "color"),
            ("고구마", "taste"), ("붕어빵", "taste"), ("호떡", "taste"), ("와플", "taste"), ("꿀떡", "taste"),
            ("츄러스", "taste"),
        ],
        "dinner": [
            ("후라이드 치킨", "color"), ("불고기", "taste"), ("찜닭", "taste"), ("소갈비찜", "taste"),
            ("양념 돼지갈비", "taste"), ("떡갈비", "taste"), ("닭꼬치", "taste"),
        ],
        "late_night": [
            ("후라이드 치킨", "color"), ("콘치즈", "color"), ("감자튀김", "color"), ("치즈볼", "color"),
            ("허니버터 치킨", "taste"), ("닭강정", "taste"), ("고구마 피자", "taste"),
        ],
    },
    "금": {  # 흰색 / 매운맛
        "breakfast": [
            ("누룽지", "color"), ("콩나물국밥", "color"), ("북엇국", "color"), ("떡국", "color"),
            ("소고기무국", "color"), ("닭죽", "color"), ("순두부", "color"), ("우유와 시리얼", "color"),
        ],
        "brunch": [
            ("우동", "color"), ("크림 파스타", "color"), ("까르보나라", "color"), ("베이글과 크림치즈", "color"),
            ("크림 리조또", "color"), ("클램차우더", "color"), ("알리오 올리오", "color"),
        ],
        "lunch": [
            ("설렁탕", "color"), ("곰탕", "color"), ("닭칼국수", "color"), ("돼지국밥", "color"),
            ("돈코츠 라멘", "color"), ("만둣국", "color"), ("짬뽕", "taste"), ("마라탕", "taste"), ("마라샹궈", "taste"),
        ],
        "snack": [
            ("찐빵", "color"), ("우유 빙수", "color"), ("백설기", "color"), ("크림빵", "color"),
            ("치즈케이크", "color"), ("우유 푸딩", "color"), ("매운 어묵", "taste"),
        ],
        "dinner": [
            ("백숙", "color"), ("삼계탕", "color"), ("보쌈", "color"), ("수육", "color"), ("모듬회", "color"),
            ("닭한마리", "color"), ("마라탕", "taste"), ("마라샹궈", "taste"), ("양꼬치", "taste"),
        ],
        "late_night": [
            ("보쌈", "color"), ("크림 떡볶이", "color"), ("라면", "taste"), ("짬뽕", "taste"),
            ("마라탕", "taste"), ("마라샹궈", "taste"), ("양꼬치", "taste"),
        ],
    },
    "수": {  # 검정 / 짠맛
        "breakfast": [
            ("미역국", "color"), ("흑임자죽", "color"), ("검은콩 두유", "color"),
            ("전복죽", "taste"), ("명란 계란밥", "taste"), ("장조림 버터밥", "taste"), ("간장계란밥", "taste"),
        ],
        "brunch": [
            ("김밥", "color"), ("먹물 파스타", "color"),
            ("명란 파스타", "taste"), ("간장계란밥", "taste"), ("명란 오차즈케", "taste"),
        ],
        "lunch": [
            ("짜장면", "color"), ("짜장밥", "color"), ("장어덮밥", "color"), ("순대국", "taste"), ("초밥", "taste"),
            ("고등어구이 정식", "taste"), ("간장게장 정식", "taste"),
        ],
        "snack": [
            ("흑임자 라떼", "color"), ("흑당 버블티", "color"), ("오레오 쉐이크", "color"), ("김부각", "color"),
            ("소금빵", "taste"), ("쥐포구이", "taste"), ("프레첼", "taste"),
        ],
        "dinner": [
            ("장어구이", "color"), ("족발", "taste"), ("고등어구이", "taste"), ("갈치조림", "taste"),
            ("간장게장", "taste"), ("굴보쌈", "taste"), ("꼬막비빔밥", "taste"),
        ],
        "late_night": [
            ("짜파게티", "color"), ("짜장면", "color"), ("족발", "taste"), ("순대", "taste"),
            ("간장치킨", "taste"), ("버터 오징어구이", "taste"), ("먹태구이", "taste"),
        ],
    },
}
