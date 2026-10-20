"""
한국어 문구 유틸 (조사 처리)
fallback 문구와 공양 표기 문구에서 같이 쓴다.
"""


def josa(word: str, with_batchim: str, without_batchim: str, rieul_as_without: bool = False) -> str:
    """
    받침에 맞는 조사를 붙인다. 예) 김밥+은/는 → 김밥은, 요거트+은/는 → 요거트는
    rieul_as_without: (으)로처럼 ㄹ받침이면 받침 없는 쪽을 쓰는 조사 (예: 냉모밀로)
    한글이 아닌 끝 글자는 받침 없음으로 처리
    """
    last = word[-1]
    if not "가" <= last <= "힣":
        return word + without_batchim
    jong = (ord(last) - ord("가")) % 28  # 0이면 받침 없음, 8이면 ㄹ
    if jong == 0 or (rieul_as_without and jong == 8):
        return word + without_batchim
    return word + with_batchim


def euro(word: str) -> str:
    """(으)로 — 예) 김치볶음밥으로, 요거트로, 냉모밀로"""
    return josa(word, "으로", "로", rieul_as_without=True)
