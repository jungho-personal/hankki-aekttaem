"""
FastAPI 앱 진입점 (핸드오프 5-1장: Railway 서비스 1개에서 정적 프론트 + API 동시 서빙)

실행
    로컬:    .venv/bin/uvicorn app.main:app --reload
    Railway: uvicorn app.main:app --host 0.0.0.0 --port $PORT
"""
import logging
import mimetypes
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import bapgwae
from app.services import llm

# ===== 로깅 =====
# Railway는 stdout을 로그로 수집하므로 기본 핸들러로 충분
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# ===== MIME =====
# 서버(Linux) Python 3.10의 mimetypes에는 .webp가 없어 application/octet-stream으로 나가고,
# 그러면 브라우저가 이미지를 그리지 않는다 → 직접 등록
mimetypes.add_type("image/webp", ".webp")

# ===== 경로 =====
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# ===== 앱 =====
app = FastAPI(title="한끼액땜", description="오행 기반 끼니 메뉴 추천 — 오늘의 밥괘")

# API 라우터는 정적 파일 마운트보다 먼저 등록해야 /api/* 가 정적 파일에 가로채이지 않는다
app.include_router(bapgwae.router)


@app.get("/api/health", tags=["system"])
def health() -> dict:
    """
    배포 확인용. LLM 활성 여부와 모델명을 노출한다 (키 값 자체는 절대 노출하지 않음).
    워크숍 현장에서 "키 설정이 먹었는지" 바로 확인하는 용도.
    """
    return {"status": "ok", "llm_enabled": llm.is_enabled(), "model": llm.get_model_name()}


# 정적 프론트: "/" 요청 시 static/index.html 서빙
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
