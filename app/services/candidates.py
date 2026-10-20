"""
메뉴 후보 선택 + 사람 버킷 (메뉴 다양성)

- 사람 버킷: 생년월일(양력)을 PERSON_BUCKETS개 묶음으로 나눈 번호.
  캐시 키에 넣어서 같은 일간이라도 버킷이 다르면 다른 밥괘가 나오게 하고,
  같은 사람은 그날 같은 끼니에 항상 같은 버킷 → 같은 밥괘 (결과 고정 유지).
  LLM 밥괘 호출 상한 = 일간 10 × 버킷 × 끼니 6 / 일 (버킷 4 → 240회)
- 후보: (일간, 버킷, 날짜, 끼니) 시드로 메뉴 풀에서 결정적으로 뽑는다.
  같은 캐시 키 = 같은 시드 = 같은 후보라서 LLM/fallback 어느 쪽이든 키와 결과가 어긋나지 않는다.
- Python 내장 hash()는 프로세스마다 값이 바뀌므로 sha256을 쓴다.
"""
import hashlib
import random
from datetime import date
from typing import List, Tuple

from app.data.menu_pool import MENU_POOL
from app.schemas import BapgwaeContext

# 생년월일 버킷 수. 늘리면 다양성↑, LLM 호출 상한↑ (일간 10 × 버킷 × 끼니 6)
PERSON_BUCKETS = 4

# LLM에 제시하는 후보 수 (먹을 메뉴 / 피해야 할 메뉴 각각)
CANDIDATE_COUNT = 3

Candidate = Tuple[str, str]  # (메뉴, 기준 color|taste)


def _hash_int(text: str) -> int:
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")


def person_bucket(birth_solar: date) -> int:
    """생년월일(양력) → 버킷 번호 (0 ~ PERSON_BUCKETS-1)"""
    return _hash_int(f"birth|{birth_solar.isoformat()}") % PERSON_BUCKETS


def seed_of(ctx: BapgwaeContext) -> int:
    """결정적 선택용 시드. 캐시 키와 같은 값(일간, 버킷, 날짜, 끼니)에서만 만든다"""
    return _hash_int(f"{ctx.my_ilgan}|{ctx.bucket}|{ctx.today.isoformat()}|{ctx.meal}")


def _sample(pool: List[Candidate], rng: random.Random) -> List[Candidate]:
    return rng.sample(pool, min(CANDIDATE_COUNT, len(pool)))


def menu_candidates(ctx: BapgwaeContext) -> List[Candidate]:
    """먹을 메뉴 후보: 대상 오행 × 끼니 칸에서 뽑는다"""
    rng = random.Random(seed_of(ctx))
    return _sample(MENU_POOL[ctx.target_ohaeng][ctx.meal], rng)


def avoid_candidates(ctx: BapgwaeContext) -> List[Candidate]:
    """피해야 할 메뉴 후보: 대상 오행을 극하는 오행 × 끼니 칸에서 뽑는다 (먹을 메뉴와 다른 난수열)"""
    rng = random.Random(seed_of(ctx) ^ 0xA5A5A5A5)
    return _sample(MENU_POOL[ctx.avoid_ohaeng][ctx.meal], rng)
