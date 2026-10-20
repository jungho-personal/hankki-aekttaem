"""
1단계 라이브러리 검증 스크립트 (개발용, 서비스 코드 아님)

목적
- lunar_python(중국 음력, UTC+8 기준)의 음력↔양력 변환과 일진(日辰)이
  한국 음력(한국천문연구원 기준, korean_lunar_calendar)과 일치하는지 전수 비교한다.
- 알려진 날짜로 일진 계산값을 검증한다.

실행
    .venv/bin/python scripts/verify_lunar.py
(korean_lunar_calendar는 검증용으로만 설치. requirements.txt에는 넣지 않음)
"""
from datetime import date, timedelta

from korean_lunar_calendar import KoreanLunarCalendar
from lunar_python import Solar

# ===== 비교 구간 =====
# 생년월일 입력으로 현실적인 범위 + 오늘 일진 계산 범위
START = date(1920, 1, 1)
END = date(2049, 12, 31)

# ===== 한국어 천간/지지 (index 0~9 / 0~11) =====
GAN_KO = "갑을병정무기경신임계"
ZHI_KO = "자축인묘진사오미신유술해"


def lunar_python_info(d: date):
    """lunar_python 기준: 양력 → (음력 년, 월, 일, 윤달여부), 일진(한글)"""
    lunar = Solar.fromYmd(d.year, d.month, d.day).getLunar()
    month = lunar.getMonth()  # 윤달은 음수 월로 표현됨
    ilgan = GAN_KO[lunar.getDayGanIndex()] + ZHI_KO[lunar.getDayZhiIndex()]
    return (lunar.getYear(), abs(month), lunar.getDay(), month < 0), ilgan


def korean_info(d: date):
    """korean_lunar_calendar(KASI) 기준: 양력 → (음력 년, 월, 일, 윤달여부), 일진(한글)"""
    cal = KoreanLunarCalendar()
    cal.setSolarDate(d.year, d.month, d.day)
    # 예: "계묘년 을묘월 기묘일 (윤월)" → 세 번째 토큰에서 "일" 제거
    ilgan = cal.getGapJaString().split()[2][:2]
    return (cal.lunarYear, cal.lunarMonth, cal.lunarDay, cal.isIntercalation), ilgan


def compare_all():
    """구간 전체 양력 날짜에 대해 두 라이브러리 결과를 비교하고 불일치 목록을 반환"""
    lunar_mismatch = []
    iljin_mismatch = []
    d = START
    total = 0
    while d <= END:
        lp_lunar, lp_iljin = lunar_python_info(d)
        ko_lunar, ko_iljin = korean_info(d)
        if lp_lunar != ko_lunar:
            lunar_mismatch.append((d, lp_lunar, ko_lunar))
        if lp_iljin != ko_iljin:
            iljin_mismatch.append((d, lp_iljin, ko_iljin))
        d += timedelta(days=1)
        total += 1
    return total, lunar_mismatch, iljin_mismatch


def check_known_dates():
    """널리 알려진 날짜의 일진을 확인 (2000-01-01 = 무오일)"""
    known = {
        date(2000, 1, 1): "무오",
    }
    for d, expected in known.items():
        _, got = lunar_python_info(d)
        print(f"[known] {d} expected={expected} got={got} {'OK' if got == expected else 'FAIL'}")


if __name__ == "__main__":
    check_known_dates()
    total, lunar_mm, iljin_mm = compare_all()
    print(f"[compare] {START} ~ {END}, 총 {total}일")
    print(f"[compare] 일진 불일치: {len(iljin_mm)}건")
    print(f"[compare] 음력 날짜 불일치: {len(lunar_mm)}건")
    # 불일치는 보통 음력 한 달(29~30일) 단위로 연속 발생 → 구간 단위로 묶어서 출력
    ranges = []
    for d, lp, ko in lunar_mm:
        if ranges and (d - ranges[-1][1]).days == 1:
            ranges[-1][1] = d
        else:
            ranges.append([d, d, lp, ko])
    print(f"[compare] 음력 날짜 불일치 구간: {len(ranges)}개")
    for start, end, lp, ko in ranges:
        print(f"  {start} ~ {end} ({(end - start).days + 1}일)  시작일 lunar_python={lp}  korean(KASI)={ko}")
