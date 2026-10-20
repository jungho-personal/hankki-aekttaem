"""
API 테스트: 엔드포인트 동작, 캐시 고정, LLM 실패 → fallback, 입력 검증, 정적 파일 서빙

LLM은 monkeypatch로 가짜 함수로 바꿔서 네트워크 없이 검증한다.
실행: .venv/bin/python -m pytest -v
"""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import bapgwae as router_mod
from app.schemas import BapgwaeRequest, BapgwaeResult
from app.services import llm
from app.services.cache import result_cache
from app.services.time_util import KST

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    """테스트마다 캐시 초기화 + 기본은 키 없음(fallback 모드)"""
    result_cache.clear()
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    yield
    result_cache.clear()


def fake_result(menu="김치찌개") -> BapgwaeResult:
    return BapgwaeResult(
        menu=menu, chosen_basis="color", basis_comment="흠..", ohaeng_reason="r",
        oracle="o", message="m", lucky_side_dish="s", avoid_menu="a", avoid_reason="ar",
    )


def enable_fake_llm(monkeypatch, fn):
    """키가 있는 것처럼 만들고 generate_bapgwae를 가짜 함수로 교체"""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(llm, "generate_bapgwae", fn)


# ===================== 기본 동작 =====================
def test_health_without_key():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["llm_enabled"] is False
    assert "test-key" not in res.text  # 키 값 노출 금지


def test_static_index_served():
    res = client.get("/")
    assert res.status_code == 200
    # 본문 문구는 디자인 마크업(<span> 등)에 따라 쪼개질 수 있어 <title>로 확인
    assert "<title>한끼액땜" in res.text


def test_fallback_mode_without_key():
    """키 없음 → fallback 응답, 스펙 필드 전부 존재"""
    res = client.post("/api/bapgwae", json={"birth_date": "1995-03-15", "calendar": "solar", "meal": "lunch"})
    assert res.status_code == 200
    body = res.json()
    assert body["is_fallback"] is True
    assert body["is_cached"] is False
    assert body["offering"] is None
    assert body["meal"] == "lunch" and body["meal_label"] == "점심"
    assert set(body["result"]) == set(BapgwaeResult.model_fields)
    for key in ["today_iljin", "my_ilgan", "my_ohaeng", "today_ohaeng", "prescription_type", "target_ohaeng"]:
        assert body[key]


def test_meal_auto_when_null():
    """meal=null → 서버가 KST 시각으로 판별"""
    req = BapgwaeRequest(birth_date="1995-03-15", calendar="solar", meal=None)
    noon_kst = datetime(2026, 10, 20, 12, 0, tzinfo=KST)
    assert router_mod.create_bapgwae(req, now=noon_kst).meal == "lunch"
    late_kst = datetime(2026, 10, 20, 23, 30, tzinfo=KST)
    assert router_mod.create_bapgwae(req, now=late_kst).meal == "late_night"


def test_lunar_leap_changes_ilgan():
    """
    같은 음력 날짜라도 윤달 여부에 따라 양력이 달라져 일간이 바뀜.
    1998년 평5월은 29일 → 5/1과 윤5/1은 29일 차이 → 천간이 달라짐 (계 vs 임, 1단계 실행으로 확인)
    (평달이 30일인 해는 30일 차이 → 천간 10일 주기라 일간이 우연히 같음)
    """
    base = {"birth_date": "1998-05-01", "calendar": "lunar", "meal": "lunch"}
    normal = client.post("/api/bapgwae", json={**base, "is_leap_month": False}).json()
    leap = client.post("/api/bapgwae", json={**base, "is_leap_month": True}).json()
    assert normal["my_ilgan"] == "계"
    assert leap["my_ilgan"] == "임"


# ===================== 입력 검증 =====================
@pytest.mark.parametrize("payload, status", [
    ({"birth_date": "1995-02-30", "calendar": "solar"}, 400),                          # 없는 양력 날짜
    ({"birth_date": "2024-02-01", "calendar": "lunar", "is_leap_month": True}, 400),   # 없는 윤달
    ({"birth_date": "2999-01-01", "calendar": "solar"}, 400),                          # 미래
    ({"birth_date": "1800-01-01", "calendar": "solar"}, 400),                          # 범위 밖
    ({"birth_date": "1995/03/15", "calendar": "solar"}, 422),                          # 형식 오류
    ({"birth_date": "1995-03-15", "calendar": "moon"}, 422),                           # calendar 오류
    ({"birth_date": "1995-03-15", "calendar": "solar", "meal": "supper"}, 422),        # meal 오류
])
def test_invalid_input(payload, status):
    assert client.post("/api/bapgwae", json=payload).status_code == status


def test_lunar_feb_30_accepted():
    """음력 2월 30일은 양력에 없지만 유효 (2023 평2월은 30일)"""
    res = client.post("/api/bapgwae", json={"birth_date": "2023-02-30", "calendar": "lunar", "meal": "lunch"})
    assert res.status_code == 200


# ===================== LLM + 캐시 =====================
def test_llm_result_cached_same_day(monkeypatch):
    """LLM 결과는 캐시되어 같은 날 같은 끼니 재요청 시 LLM을 다시 부르지 않음"""
    calls = []

    def fake(ctx):
        calls.append(ctx)
        return fake_result(menu=f"메뉴{len(calls)}")

    enable_fake_llm(monkeypatch, fake)
    payload = {"birth_date": "1995-03-15", "calendar": "solar", "meal": "lunch"}

    first = client.post("/api/bapgwae", json=payload).json()
    second = client.post("/api/bapgwae", json=payload).json()

    assert len(calls) == 1
    assert first["is_fallback"] is False and first["is_cached"] is False
    assert second["is_cached"] is True
    assert first["result"] == second["result"]


def test_cache_key_is_ilgan_not_birthdate(monkeypatch):
    """일간이 같은 다른 생일(10일 차이 → 같은 천간)은 같은 캐시를 공유 (의도된 동작, 4-5장)"""
    calls = []
    enable_fake_llm(monkeypatch, lambda ctx: calls.append(ctx) or fake_result())
    a = client.post("/api/bapgwae", json={"birth_date": "1995-03-15", "calendar": "solar", "meal": "lunch"}).json()
    b = client.post("/api/bapgwae", json={"birth_date": "1995-03-25", "calendar": "solar", "meal": "lunch"}).json()
    assert a["my_ilgan"] == b["my_ilgan"]
    assert len(calls) == 1 and b["is_cached"] is True


def test_different_meal_calls_llm_again(monkeypatch):
    calls = []
    enable_fake_llm(monkeypatch, lambda ctx: calls.append(ctx) or fake_result())
    client.post("/api/bapgwae", json={"birth_date": "1995-03-15", "calendar": "solar", "meal": "lunch"})
    client.post("/api/bapgwae", json={"birth_date": "1995-03-15", "calendar": "solar", "meal": "dinner"})
    assert len(calls) == 2


def test_llm_failure_falls_back_and_not_cached(monkeypatch):
    """LLM 실패 → fallback 응답, fallback은 캐시하지 않음 → LLM 복구 시 LLM 결과로 전환"""
    def broken(ctx):
        raise llm.LLMError("한도 초과")

    enable_fake_llm(monkeypatch, broken)
    payload = {"birth_date": "1995-03-15", "calendar": "solar", "meal": "lunch"}
    res = client.post("/api/bapgwae", json=payload).json()
    assert res["is_fallback"] is True
    assert len(result_cache) == 0

    # LLM 복구
    monkeypatch.setattr(llm, "generate_bapgwae", lambda ctx: fake_result("복구메뉴"))
    res2 = client.post("/api/bapgwae", json=payload).json()
    assert res2["is_fallback"] is False and res2["result"]["menu"] == "복구메뉴"


def test_real_generate_with_bad_client_raises_llm_error(monkeypatch):
    """실제 generate_bapgwae에서 SDK 예외가 나도 LLMError로 변환되는지 (네트워크 없이 클라이언트를 가짜로)"""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    class BoomModels:
        def generate_content(self, **kwargs):
            raise RuntimeError("network down")

    class BoomClient:
        models = BoomModels()

    monkeypatch.setattr(llm, "_get_client", lambda: BoomClient())
    req = BapgwaeRequest(birth_date="1995-03-15", calendar="solar", meal="lunch")
    ctx = router_mod.build_context(req, datetime(2026, 10, 20, 12, 0, tzinfo=KST))
    with pytest.raises(llm.LLMError):
        llm.generate_bapgwae(ctx)
