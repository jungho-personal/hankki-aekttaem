"""
공양 슬롯 테스트 (핸드오프 11-3장)
- 노출 조건(OFFERING_DEMO, 실제 광고주 우선), 표기 문구, 멘트(LLM / 고정 문구), 캐시 고정, 밥괘와 분리

실행: .venv/bin/python -m pytest -v
"""
import pytest
from fastapi.testclient import TestClient

from app.data.offerings import DEMO_SPONSORS, FALLBACK_COMMENTS
from app.main import app
from app.schemas import BapgwaeResult
from app.services import llm
from app.services import offering as offering_mod
from app.services.cache import result_cache

client = TestClient(app)
PAYLOAD = {"birth_date": "1995-03-15", "calendar": "solar", "meal": "dinner"}


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    """테스트마다 캐시 초기화, 기본은 키 없음 + 데모 꺼짐"""
    result_cache.clear()
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OFFERING_DEMO", raising=False)
    yield
    result_cache.clear()


def fake_result(menu="김치찌개") -> BapgwaeResult:
    return BapgwaeResult(
        menu=menu, chosen_basis="color", basis_comment="흠..", ohaeng_reason="r",
        oracle="o", message="m", lucky_side_dish="s", avoid_menu="a", avoid_reason="ar",
    )


# ===================== 노출 조건 =====================
def test_no_offering_when_demo_off():
    """실제 광고주 없음 + 데모 꺼짐 → offering null"""
    assert client.post("/api/bapgwae", json=PAYLOAD).json()["offering"] is None


@pytest.mark.parametrize("value", ["true", "1", "yes", "TRUE"])
def test_demo_flag_values(monkeypatch, value):
    monkeypatch.setenv("OFFERING_DEMO", value)
    assert offering_mod.is_demo_enabled() is True


def test_demo_offering_in_fallback_mode(monkeypatch):
    """데모 켜짐 + 키 없음 → 예시 광고 + 고정 멘트, 표기는 시연용 문구"""
    monkeypatch.setenv("OFFERING_DEMO", "true")
    body = client.post("/api/bapgwae", json=PAYLOAD).json()
    off = body["offering"]
    assert off is not None
    assert off["is_demo"] is True
    assert off["disclosure"] == offering_mod.DEMO_DISCLOSURE
    assert off["sponsor_name"] in [s["sponsor_name"] for s in DEMO_SPONSORS if "dinner" in s["meals"]]
    assert off["comment"] in [c.format(sponsor=off["sponsor_name"]) for c in FALLBACK_COMMENTS]
    assert body["is_fallback"] is True


def test_every_meal_has_demo_sponsor():
    meals = ["breakfast", "brunch", "lunch", "snack", "dinner", "late_night"]
    for meal in meals:
        assert any(meal in s["meals"] for s in DEMO_SPONSORS), meal


def test_real_sponsor_takes_precedence(monkeypatch):
    """실제 광고주가 있으면 데모보다 우선, 표기는 '광고비를 받았습니다'"""
    monkeypatch.setenv("OFFERING_DEMO", "true")
    monkeypatch.setattr(offering_mod, "SPONSORS", [
        {"sponsor_name": "진짜치킨", "menu": "후라이드", "meals": ["dinner"], "link": "https://example.com"},
    ])
    off = client.post("/api/bapgwae", json=PAYLOAD).json()["offering"]
    assert off["sponsor_name"] == "진짜치킨"
    assert off["is_demo"] is False
    assert off["disclosure"] == "이 추천은 진짜치킨으로부터 광고비를 받았습니다"
    assert off["link"] == "https://example.com"


def test_real_sponsor_meal_filter(monkeypatch):
    """다른 끼니 광고만 있고 데모 꺼짐 → null"""
    monkeypatch.setattr(offering_mod, "SPONSORS", [
        {"sponsor_name": "진짜분식", "menu": "떡볶이", "meals": ["snack"], "link": ""},
    ])
    assert client.post("/api/bapgwae", json=PAYLOAD).json()["offering"] is None


# ===================== 표기 문구 =====================
def test_disclosure_josa():
    assert offering_mod.build_disclosure("식신치킨", False) == "이 추천은 식신치킨으로부터 광고비를 받았습니다"
    assert offering_mod.build_disclosure("게으름브런치", False) == "이 추천은 게으름브런치로부터 광고비를 받았습니다"
    assert offering_mod.build_disclosure("오행반점", True) == offering_mod.DEMO_DISCLOSURE


# ===================== LLM 멘트 + 분리 + 캐시 =====================
def test_llm_comment_and_separation(monkeypatch):
    """
    밥괘가 먼저 확정되고, 공양 멘트 호출은 확정된 밥괘 메뉴를 받는다.
    밥괘 호출에는 광고 정보가 전혀 넘어가지 않는다 (generate_bapgwae는 ctx만 받음).
    """
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("OFFERING_DEMO", "true")
    order = []

    def fake_bapgwae(ctx):
        order.append("bapgwae")
        return fake_result("제육볶음")

    def fake_comment(slot, ctx, bapgwae_menu):
        order.append(("comment", bapgwae_menu, slot.sponsor_name))
        return f"{slot.sponsor_name} 공양 멘트"

    monkeypatch.setattr(llm, "generate_bapgwae", fake_bapgwae)
    monkeypatch.setattr(llm, "generate_offering_comment", fake_comment)

    body = client.post("/api/bapgwae", json=PAYLOAD).json()
    assert order[0] == "bapgwae"
    assert order[1][0] == "comment" and order[1][1] == "제육볶음"
    assert body["result"]["menu"] == "제육볶음"  # 밥괘 메뉴는 광고와 무관하게 유지
    assert body["offering"]["comment"] == f"{body['offering']['sponsor_name']} 공양 멘트"

    # 같은 키 재요청 → 캐시에서 밥괘 + 공양 모두 그대로, LLM 추가 호출 없음
    again = client.post("/api/bapgwae", json=PAYLOAD).json()
    assert again["is_cached"] is True
    assert again["offering"] == body["offering"]
    assert len(order) == 2


def test_comment_llm_failure_keeps_bapgwae(monkeypatch):
    """공양 멘트 LLM 실패 → 고정 멘트. 밥괘는 LLM 결과 그대로 (is_fallback false)"""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("OFFERING_DEMO", "true")
    monkeypatch.setattr(llm, "generate_bapgwae", lambda ctx: fake_result("제육볶음"))

    def broken(slot, ctx, menu):
        raise llm.LLMError("한도 초과")

    monkeypatch.setattr(llm, "generate_offering_comment", broken)
    body = client.post("/api/bapgwae", json=PAYLOAD).json()
    assert body["is_fallback"] is False
    assert body["result"]["menu"] == "제육볶음"
    off = body["offering"]
    assert off["comment"] in [c.format(sponsor=off["sponsor_name"]) for c in FALLBACK_COMMENTS]


def test_no_comment_call_when_no_offering(monkeypatch):
    """노출할 광고가 없으면 멘트 LLM 호출 자체를 하지 않음 (비용 0)"""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    calls = []
    monkeypatch.setattr(llm, "generate_bapgwae", lambda ctx: fake_result())
    monkeypatch.setattr(llm, "generate_offering_comment", lambda *a: calls.append(a) or "x")
    assert client.post("/api/bapgwae", json=PAYLOAD).json()["offering"] is None
    assert calls == []


def test_offering_prompt_has_no_ohaeng_claim_inputs():
    """공양 멘트 프롬프트에는 가게/메뉴/확정 밥괘만 넘기고, 오행 대상 정보는 넘기지 않음"""
    from datetime import datetime

    from app.routers.bapgwae import build_context
    from app.schemas import BapgwaeRequest
    from app.services.time_util import KST

    ctx = build_context(BapgwaeRequest(**PAYLOAD), datetime(2026, 10, 20, 18, tzinfo=KST))
    slot = offering_mod.OfferingSlot(sponsor_name="식신치킨", menu="간장치킨", disclosure="d", link="", is_demo=True)
    prompt = llm.build_offering_prompt(slot, ctx, "제육볶음")
    assert "식신치킨" in prompt and "간장치킨" in prompt and "제육볶음" in prompt
    assert "대상 오행" not in prompt
