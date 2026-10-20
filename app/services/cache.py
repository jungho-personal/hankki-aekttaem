"""
결과 고정 캐시 (핸드오프 4-5장, 5-2장 7번)

- 키: (사용자 일간, KST 오늘 날짜, 끼니)
- 만료: 다음 KST 자정
- MVP: 인메모리. 서버 재시작/재배포 시 휘발되고, 인스턴스가 여러 개면 인스턴스끼리 결과가 다를 수 있다.
  필요해지면 이 클래스와 같은 get/set_if_absent 인터페이스로 Redis 구현을 만들어 교체한다.
"""
import threading
from datetime import date, datetime
from typing import Any, Optional, Tuple

from app.services.time_util import next_kst_midnight, now_kst

# 캐시 키 타입: (일간, 날짜, 끼니)
CacheKey = Tuple[str, date, str]


def make_key(ilgan: str, today: date, meal: str) -> CacheKey:
    """캐시 키 생성 (일간 + KST 날짜 + 끼니)"""
    return (ilgan, today, meal)


class ResultCache:
    """
    만료 시각이 있는 인메모리 캐시.

    FastAPI의 동기 엔드포인트는 스레드풀에서 동시에 돌 수 있으므로 Lock으로 보호한다.
    """

    def __init__(self):
        # key → (value, expires_at)
        self._store: dict = {}
        self._lock = threading.Lock()

    def get(self, key: CacheKey, now: Optional[datetime] = None) -> Optional[Any]:
        """만료되지 않은 값이 있으면 반환, 없거나 만료됐으면 None (만료된 항목은 삭제)"""
        current = now_kst(now)
        with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            value, expires_at = item
            if current >= expires_at:
                del self._store[key]
                return None
            return value

    def set_if_absent(self, key: CacheKey, value: Any, now: Optional[datetime] = None) -> Any:
        """
        키가 비어 있을 때만 저장하고, 최종적으로 캐시에 들어 있는 값을 반환한다.

        같은 키로 동시에 두 요청이 LLM을 호출했을 때, 먼저 저장된 결과를 둘 다 쓰게 해서
        "같은 날 같은 끼니 = 같은 밥괘"가 깨지지 않도록 한다.
        """
        current = now_kst(now)
        with self._lock:
            self._purge_expired(current)
            item = self._store.get(key)
            if item is not None:
                return item[0]
            self._store[key] = (value, next_kst_midnight(current))
            return value

    def clear(self) -> None:
        """전체 삭제 (테스트용)"""
        with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)

    def _purge_expired(self, current: datetime) -> None:
        """만료된 항목 정리 (Lock을 잡은 상태에서만 호출). 키가 하루 최대 60개라 전체 순회해도 부담 없음"""
        expired = [k for k, (_, exp) in self._store.items() if current >= exp]
        for k in expired:
            del self._store[k]


# ===== 앱 전역 캐시 인스턴스 =====
result_cache = ResultCache()
