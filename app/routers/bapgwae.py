"""
POST /api/bapgwae — 밥괘 생성 (핸드오프 4-2장 처리 흐름)

흐름
1) KST 현재 시각 → 끼니 자동 판별 (수동 입력 우선)
2) 음력이면 양력 변환
3) 만세력: 사용자 일간 / 오늘 일진
4) 오행 관계로 처방 타입 결정
5) 캐시 조회 (일간, KST 날짜, 끼니)
6) Gemini 호출 → 실패 시 fallback
7) 캐시 저장 (KST 자정 만료) — 단, fallback 결과는 저장하지 않음 (아래 _resolve_result 참고)
"""
import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.schemas import BapgwaeContext, BapgwaeRequest, BapgwaeResponse, BapgwaeResult
from app.services import llm
from app.services.cache import make_key, result_cache
from app.services.fallback import build_fallback_result
from app.services.manseryeok import InvalidDateError, get_iljin, get_ilgan, lunar_to_solar
from app.services.ohaeng import gan_to_ohaeng, get_avoid_ohaeng, get_prescription
from app.services.time_util import MEAL_LABELS, detect_meal, now_kst

logger = logging.getLogger("hankki.bapgwae")

router = APIRouter(prefix="/api", tags=["bapgwae"])

# 생년월일 허용 하한 (lunar_python 계산은 더 넓게 되지만, 오입력 방지용)
MIN_BIRTH_YEAR = 1900


def parse_birth_date(req: BapgwaeRequest, today: date) -> date:
    """
    요청의 생년월일을 양력 date로 변환한다. (4-2장 2단계)

    Raises:
        InvalidDateError: 존재하지 않는 날짜, 범위 밖 날짜
    """
    year, month, day = (int(x) for x in req.birth_date.split("-"))

    if year < MIN_BIRTH_YEAR:
        raise InvalidDateError(f"{MIN_BIRTH_YEAR}년 이후 생년월일만 지원합니다")

    if req.calendar == "lunar":
        solar = lunar_to_solar(year, month, day, req.is_leap_month)
    else:
        try:
            solar = date(year, month, day)
        except ValueError as e:
            raise InvalidDateError(f"존재하지 않는 양력 날짜입니다: {req.birth_date}") from e

    if solar > today:
        raise InvalidDateError("미래 날짜는 생년월일로 입력할 수 없습니다")
    return solar


def build_context(req: BapgwaeRequest, now: datetime) -> BapgwaeContext:
    """요청 + 현재 시각으로 서버 계산값(만세력/오행/처방)을 만든다. (4-2장 1~4단계)"""
    today = now.date()

    # 1) 끼니: 수동 지정 우선, 없으면 KST 시각으로 자동 판별
    meal = req.meal or detect_meal(now)

    # 2~3) 생년월일 → 일간, 오늘 → 일진
    birth_solar = parse_birth_date(req, today)
    my_ilgan = get_ilgan(birth_solar)
    today_iljin = get_iljin(today)

    # 4) 오행 + 처방
    my_ohaeng = gan_to_ohaeng(my_ilgan)
    today_ohaeng = gan_to_ohaeng(today_iljin[0])  # 일진의 천간 기준
    prescription = get_prescription(my_ohaeng, today_ohaeng)

    return BapgwaeContext(
        today=today,
        meal=meal,
        meal_label=MEAL_LABELS[meal],
        my_ilgan=my_ilgan,
        today_iljin=today_iljin,
        my_ohaeng=my_ohaeng,
        today_ohaeng=today_ohaeng,
        prescription_type=prescription["type"],
        target_ohaeng=prescription["target_ohaeng"],
        avoid_ohaeng=get_avoid_ohaeng(prescription["target_ohaeng"]),
    )


def _resolve_result(ctx: BapgwaeContext, now: datetime) -> tuple:
    """
    캐시 → LLM → fallback 순으로 결과를 얻는다. (4-2장 5~7단계)

    Returns:
        (BapgwaeResult, is_fallback, is_cached)

    fallback 결과를 캐시에 넣지 않는 이유
    - LLM이 일시적으로 실패했을 때 fallback이 캐시되면 그날 자정까지 fallback으로 고정된다.
    - fallback은 결정적이라 캐시하지 않아도 같은 입력이면 같은 결과가 나온다.
    - 대신 LLM이 복구되면 그 끼니 결과가 fallback → LLM 결과로 한 번 바뀔 수 있다 (감수).
    """
    key = make_key(ctx.my_ilgan, ctx.today, ctx.meal)

    # 5) 캐시 조회
    cached = result_cache.get(key, now)
    if cached is not None:
        return cached, False, True

    # 6) LLM 호출 (키 미설정이면 바로 fallback)
    if llm.is_enabled():
        try:
            result = llm.generate_bapgwae(ctx)
            # 7) 캐시 저장. 동시 요청으로 이미 저장된 값이 있으면 그 값을 사용
            stored = result_cache.set_if_absent(key, result, now)
            return stored, False, stored is not result
        except llm.LLMError as e:
            logger.warning("LLM 실패 → fallback 사용: %s", e)

    return build_fallback_result(ctx), True, False


def create_bapgwae(req: BapgwaeRequest, now: Optional[datetime] = None) -> BapgwaeResponse:
    """
    밥괘 생성 본체. 테스트에서 now를 주입할 수 있도록 엔드포인트와 분리했다.
    """
    current = now_kst(now)
    ctx = build_context(req, current)
    result, is_fallback, is_cached = _resolve_result(ctx, current)

    # 요청 로그: 생년월일 원본은 남기지 않고 파생값만 기록 (개인정보 최소화)
    logger.info(
        "bapgwae date=%s meal=%s ilgan=%s iljin=%s type=%s target=%s menu=%s fallback=%s cached=%s",
        ctx.today, ctx.meal, ctx.my_ilgan, ctx.today_iljin, ctx.prescription_type,
        ctx.target_ohaeng, result.menu, is_fallback, is_cached,
    )

    return BapgwaeResponse(
        meal=ctx.meal,
        meal_label=ctx.meal_label,
        today_iljin=ctx.today_iljin,
        my_ilgan=ctx.my_ilgan,
        my_ohaeng=ctx.my_ohaeng,
        today_ohaeng=ctx.today_ohaeng,
        prescription_type=ctx.prescription_type,
        target_ohaeng=ctx.target_ohaeng,
        result=result,
        offering=None,  # MVP: 공양 슬롯 미노출 (핸드오프 11-3장)
        is_fallback=is_fallback,
        is_cached=is_cached,
    )


@router.post("/bapgwae", response_model=BapgwaeResponse)
def post_bapgwae(req: BapgwaeRequest) -> BapgwaeResponse:
    """
    밥괘 API. 동기 함수(def)로 둔 이유: Gemini SDK 호출이 블로킹이라
    FastAPI가 스레드풀에서 실행하게 해서 이벤트 루프를 막지 않기 위함.
    """
    try:
        return create_bapgwae(req)
    except InvalidDateError as e:
        raise HTTPException(status_code=400, detail=str(e))
