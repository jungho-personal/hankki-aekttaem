"""
단위 테스트 (핸드오프 12-2장 5단계 목록)
- 오행 판정, 처방 타입, 끼니 경계(야식 자정 넘김), UTC→KST 날짜 변환, 음력/윤달 변환, 캐시 키/만료
- fallback 결정성, LLM 응답 파싱

실행: .venv/bin/python -m pytest -v
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.schemas import BapgwaeContext
from app.services import llm
from app.services.cache import ResultCache, make_key
from app.services.fallback import build_fallback_result
from app.services.manseryeok import InvalidDateError, get_iljin, get_ilgan, lunar_to_solar
from app.services.ohaeng import (
    GAN_OHAENG,
    gan_to_ohaeng,
    get_avoid_ohaeng,
    get_prescription,
)
from app.services.time_util import KST, detect_meal, next_kst_midnight, today_kst

UTC = timezone.utc


def kst(y, mo, d, h=0, mi=0):
    """KST aware datetime 헬퍼"""
    return datetime(y, mo, d, h, mi, tzinfo=KST)


# ===================== 오행 판정 =====================
class TestOhaeng:
    def test_gan_to_ohaeng_all(self):
        """천간 10개 → 오행 매핑"""
        expected = {"갑": "목", "을": "목", "병": "화", "정": "화", "무": "토",
                    "기": "토", "경": "금", "신": "금", "임": "수", "계": "수"}
        assert GAN_OHAENG == expected
        assert gan_to_ohaeng("병") == "화"

    def test_avoid_ohaeng(self):
        """피해야 할 오행 = 대상 오행을 극하는 오행"""
        assert get_avoid_ohaeng("목") == "금"  # 금극목
        assert get_avoid_ohaeng("화") == "수"  # 수극화
        assert get_avoid_ohaeng("토") == "목"  # 목극토
        assert get_avoid_ohaeng("금") == "화"  # 화극금
        assert get_avoid_ohaeng("수") == "토"  # 토극수


# ===================== 처방 타입 =====================
class TestPrescription:
    def test_aekttaem_when_today_controls_me(self):
        """오늘이 나를 극함 → 액땜, 나를 생해주는 오행"""
        # 금극목: 나=목, 오늘=금 → 수생목이므로 수
        assert get_prescription("목", "금") == {"type": "액땜", "target_ohaeng": "수"}
        # 수극화: 나=화, 오늘=수 → 목생화이므로 목
        assert get_prescription("화", "수") == {"type": "액땜", "target_ohaeng": "목"}

    def test_boost_when_today_generates_me(self):
        """오늘이 나를 생함 → 부스트, 오늘 오행"""
        # 목생화: 나=화, 오늘=목
        assert get_prescription("화", "목") == {"type": "부스트", "target_ohaeng": "목"}
        # 금생수: 나=수, 오늘=금
        assert get_prescription("수", "금") == {"type": "부스트", "target_ohaeng": "금"}

    def test_boyang_otherwise(self):
        """그 외(같은 오행, 내가 생/극하는 경우) → 보양, 내 오행"""
        assert get_prescription("목", "목") == {"type": "보양", "target_ohaeng": "목"}  # 같음
        assert get_prescription("목", "화") == {"type": "보양", "target_ohaeng": "목"}  # 내가 생함
        assert get_prescription("목", "토") == {"type": "보양", "target_ohaeng": "목"}  # 내가 극함

    def test_all_25_combinations_distribution(self):
        """5×5 조합 전수: 액땜 5, 부스트 5, 보양 15"""
        types = [get_prescription(m, t)["type"] for m in "목화토금수" for t in "목화토금수"]
        assert types.count("액땜") == 5
        assert types.count("부스트") == 5
        assert types.count("보양") == 15


# ===================== 끼니 경계 =====================
class TestMealBoundary:
    @pytest.mark.parametrize("h, mi, expected", [
        (4, 59, "late_night"),   # 새벽 야식 끝
        (5, 0, "breakfast"),
        (9, 59, "breakfast"),
        (10, 0, "brunch"),
        (11, 29, "brunch"),
        (11, 30, "lunch"),
        (14, 29, "lunch"),
        (14, 30, "snack"),
        (17, 29, "snack"),
        (17, 30, "dinner"),
        (21, 59, "dinner"),
        (22, 0, "late_night"),   # 야식 시작
        (23, 59, "late_night"),
        (0, 0, "late_night"),    # 자정 넘김
    ])
    def test_meal_boundaries_kst(self, h, mi, expected):
        assert detect_meal(kst(2026, 10, 20, h, mi)) == expected

    def test_meal_from_utc_input(self):
        """UTC 시각을 넣어도 KST로 변환 후 판별: UTC 03:00 = KST 12:00 → 점심"""
        assert detect_meal(datetime(2026, 10, 20, 3, 0, tzinfo=UTC)) == "lunch"
        # UTC 13:30 = KST 22:30 → 야식
        assert detect_meal(datetime(2026, 10, 20, 13, 30, tzinfo=UTC)) == "late_night"


# ===================== UTC → KST 날짜 =====================
class TestKstDate:
    def test_utc_evening_is_next_day_in_kst(self):
        """UTC 10/19 20:00 = KST 10/20 05:00 → 날짜는 10/20 (어제 일진 버그 방지)"""
        assert today_kst(datetime(2026, 10, 19, 20, 0, tzinfo=UTC)) == date(2026, 10, 20)

    def test_naive_datetime_treated_as_utc(self):
        """tz 없는 값은 UTC로 간주 (서버 기본 시각 가정)"""
        assert today_kst(datetime(2026, 10, 19, 15, 0)) == date(2026, 10, 20)  # KST 00:00
        assert today_kst(datetime(2026, 10, 19, 14, 59)) == date(2026, 10, 19)  # KST 23:59

    def test_next_midnight(self):
        assert next_kst_midnight(kst(2026, 10, 20, 23, 59)) == kst(2026, 10, 21)
        assert next_kst_midnight(kst(2026, 10, 20, 0, 0)) == kst(2026, 10, 21)


# ===================== 만세력: 일진/일간, 음력/윤달 =====================
class TestManseryeok:
    def test_known_iljin(self):
        """2000-01-01 = 무오일 (널리 알려진 기준일)"""
        assert get_iljin(date(2000, 1, 1)) == "무오"

    def test_iljin_60_cycle(self):
        """일진은 60일 주기"""
        d = date(2026, 10, 20)
        assert get_iljin(d) == get_iljin(d + timedelta(days=60))
        assert get_iljin(d) != get_iljin(d + timedelta(days=1))

    def test_ilgan_is_first_char_of_iljin(self):
        d = date(1995, 3, 15)
        assert get_ilgan(d) == get_iljin(d)[0]

    def test_lunar_to_solar_normal(self):
        """음력 2023-02-01(평달) → 양력 2023-02-20"""
        assert lunar_to_solar(2023, 2, 1, False) == date(2023, 2, 20)

    def test_lunar_to_solar_leap(self):
        """음력 2023 윤2월 1일 → 양력 2023-03-22 (평달과 다름)"""
        assert lunar_to_solar(2023, 2, 1, True) == date(2023, 3, 22)

    def test_lunar_30th_day(self):
        """양력에 없는 '2월 30일'도 음력에선 유효할 수 있음 (2023 평2월은 30일까지)"""
        assert lunar_to_solar(2023, 2, 30, False) == date(2023, 3, 21)

    def test_leap_month_not_exist(self):
        """윤달이 없는 해/월의 윤달 입력 → InvalidDateError"""
        with pytest.raises(InvalidDateError):
            lunar_to_solar(2024, 2, 1, True)

    def test_lunar_day_overflow(self):
        """그 달 일수를 넘는 날짜 → InvalidDateError"""
        with pytest.raises(InvalidDateError):
            lunar_to_solar(2023, 1, 31, False)


# ===================== 캐시 키/만료 =====================
class TestCache:
    def test_key(self):
        assert make_key("병", date(2026, 10, 20), "lunch") == ("병", date(2026, 10, 20), "lunch")

    def test_hit_before_midnight_and_expire_at_midnight(self):
        cache = ResultCache()
        key = make_key("병", date(2026, 10, 20), "lunch")
        cache.set_if_absent(key, "A", kst(2026, 10, 20, 12, 0))
        assert cache.get(key, kst(2026, 10, 20, 23, 59)) == "A"   # 자정 전 → 유지
        assert cache.get(key, kst(2026, 10, 21, 0, 0)) is None    # KST 자정 → 만료
        assert len(cache) == 0                                    # 만료 항목 삭제됨

    def test_expire_uses_kst_not_utc(self):
        """UTC 15:00 = KST 자정 → 만료"""
        cache = ResultCache()
        key = make_key("병", date(2026, 10, 20), "lunch")
        cache.set_if_absent(key, "A", kst(2026, 10, 20, 12, 0))
        assert cache.get(key, datetime(2026, 10, 20, 14, 59, tzinfo=UTC)) == "A"
        assert cache.get(key, datetime(2026, 10, 20, 15, 0, tzinfo=UTC)) is None

    def test_set_if_absent_keeps_first(self):
        """동시 요청 대비: 먼저 저장된 값 유지"""
        cache = ResultCache()
        key = make_key("병", date(2026, 10, 20), "lunch")
        now = kst(2026, 10, 20, 12, 0)
        assert cache.set_if_absent(key, "A", now) == "A"
        assert cache.set_if_absent(key, "B", now) == "A"
        assert cache.get(key, now) == "A"

    def test_different_keys_independent(self):
        cache = ResultCache()
        now = kst(2026, 10, 20, 12, 0)
        cache.set_if_absent(make_key("병", date(2026, 10, 20), "lunch"), "A", now)
        assert cache.get(make_key("병", date(2026, 10, 20), "dinner"), now) is None
        assert cache.get(make_key("정", date(2026, 10, 20), "lunch"), now) is None


# ===================== fallback =====================
def _ctx(**overrides) -> BapgwaeContext:
    base = dict(
        today=date(2026, 10, 20), meal="lunch", meal_label="점심", my_ilgan="병",
        today_iljin="갑자", my_ohaeng="화", today_ohaeng="목", prescription_type="부스트",
        target_ohaeng="목", avoid_ohaeng="금",
    )
    base.update(overrides)
    return BapgwaeContext(**base)


class TestFallback:
    def test_deterministic(self):
        """같은 컨텍스트 → 같은 결과"""
        assert build_fallback_result(_ctx()) == build_fallback_result(_ctx())

    def test_menu_from_target_and_avoid_from_avoid_ohaeng(self):
        from app.data.fallback_menu import FALLBACK_MENU
        r = build_fallback_result(_ctx())
        assert r.menu in [m for m, _ in FALLBACK_MENU["목"]["lunch"]]
        assert r.avoid_menu in [m for m, _ in FALLBACK_MENU["금"]["lunch"]]
        assert r.chosen_basis in ("color", "taste")

    def test_all_30_cells_have_menu(self):
        """오행 5 × 끼니 6 = 30칸 모두 메뉴가 있어야 함"""
        from app.data.fallback_menu import FALLBACK_MENU
        meals = ["breakfast", "brunch", "lunch", "snack", "dinner", "late_night"]
        for oh in "목화토금수":
            for meal in meals:
                assert FALLBACK_MENU[oh][meal], f"{oh}/{meal} 비어 있음"

    def test_josa(self):
        """받침에 맞는 조사: (으)로, 은/는"""
        from app.services.fallback import _euro, _josa
        assert _euro("김치볶음밥") == "김치볶음밥으로"
        assert _euro("요거트") == "요거트로"
        assert _euro("냉모밀") == "냉모밀로"  # ㄹ받침은 '로'
        assert _josa("김밥", "은", "는") == "김밥은"
        assert _josa("라면", "은", "는") == "라면은"
        assert _josa("치킨", "은", "는") == "치킨은"
        assert _josa("요거트", "은", "는") == "요거트는"

    def test_message_by_prescription(self):
        assert "액땜하시게" in build_fallback_result(_ctx(prescription_type="액땜")).message
        assert "끌어올리시게" in build_fallback_result(_ctx(prescription_type="부스트")).message
        assert "채우시게" in build_fallback_result(_ctx(prescription_type="보양")).message


# ===================== LLM 응답 파싱 =====================
class TestLlmParse:
    VALID = ('{"menu":"김치찌개","chosen_basis":"color","basis_comment":"흠..","ohaeng_reason":"a",'
             '"oracle":"b","message":"c","lucky_side_dish":"d","avoid_menu":"e","avoid_reason":"f"}')

    def test_valid(self):
        assert llm.parse_response_text(self.VALID).menu == "김치찌개"

    @pytest.mark.parametrize("text", [
        None, "", "not json",
        '{"menu":"김치찌개"}',                                        # 필드 누락
        VALID.replace('"color"', '"smell"'),                          # 잘못된 basis
        VALID.replace('"김치찌개"', '"  "'),                           # 빈 필드
    ])
    def test_invalid_raises_llm_error(self, text):
        with pytest.raises(llm.LLMError):
            llm.parse_response_text(text)

    def test_disabled_without_key(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        assert llm.is_enabled() is False
        monkeypatch.setenv("GEMINI_API_KEY", "   ")
        assert llm.is_enabled() is False

    def test_model_env(self, monkeypatch):
        monkeypatch.delenv("GEMINI_MODEL", raising=False)
        assert llm.get_model_name() == llm.DEFAULT_MODEL
        monkeypatch.setenv("GEMINI_MODEL", "some-model")
        assert llm.get_model_name() == "some-model"
