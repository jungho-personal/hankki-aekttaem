# 한끼액땜 🍚

생년월일과 오늘의 일진으로 보는 "오늘의 밥괘", 즉 식신이 점지해주는 끼니 메뉴.
기획/설계 배경은 상위 폴더의 `hankki-aekttaem-handoff.md`에 있어.

- 백엔드: FastAPI. 정적 프론트(`static/`)와 API(`/api/*`)를 서버 하나에서 같이 서빙
- 만세력: `lunar_python` / LLM: Gemini (`google-genai`)
- **`GEMINI_API_KEY`가 없으면 fallback 모드**로 동작해. 키 없이도 배포하고 시연할 수 있어

---

## 1. 구조

```
app/
├─ main.py              # FastAPI 앱, /api/health, 정적 파일 마운트
├─ routers/bapgwae.py   # POST /api/bapgwae (처리 흐름 전체)
├─ services/
│  ├─ time_util.py      # KST 변환, 끼니 판별
│  ├─ manseryeok.py     # 음력→양력, 일간/일진 (lunar_python)
│  ├─ ohaeng.py         # 오행 매핑, 상생/상극, 처방 타입
│  ├─ llm.py            # Gemini 호출, JSON 검증
│  ├─ cache.py          # 결과 고정 캐시 (일간+날짜+끼니, KST 자정 만료, 인메모리)
│  ├─ fallback.py       # LLM 실패/미설정 시 룰 기반 결과
│  ├─ offering.py       # 공양 슬롯: 광고 선택, 표기 문구, 고정 멘트
│  └─ text_util.py      # 조사 처리 (은/는, (으)로)
├─ data/fallback_menu.py  # 오행 × 끼니 30칸 fallback 메뉴
├─ data/offerings.py     # 공양 슬롯 광고 DB (실제 광고주 / 시연용 예시 / 고정 멘트)
└─ schemas.py           # 요청/응답 Pydantic 모델
static/index.html       # 프론트 (워크숍에서 교체할 대상)
tests/                  # 단위/API 테스트
scripts/verify_lunar.py # 1단계 만세력 검증 스크립트 + 로그
```

## 2. 로컬 실행

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --reload
# → http://127.0.0.1:8000
```

테스트:

```bash
.venv/bin/python -m pytest -q
```

키를 넣고 로컬에서 실행:

```bash
GEMINI_API_KEY=발급받은키 .venv/bin/uvicorn app.main:app --reload
```

## 3. API

### `GET /api/health`
```json
{"status": "ok", "llm_enabled": false, "model": "gemini-3.5-flash-lite"}
```
`llm_enabled`로 키가 적용됐는지 확인할 수 있어. 키 값 자체는 노출하지 않아.

### `POST /api/bapgwae`
요청:
```json
{"birth_date": "1995-03-15", "calendar": "solar", "is_leap_month": false, "meal": null}
```
- `birth_date`: `YYYY-MM-DD` 문자열. 음력은 `2023-02-30`처럼 양력에 없는 날짜도 받아
- `calendar`: `solar` | `lunar`
- `is_leap_month`: 음력일 때만 의미 있음
- `meal`: `breakfast` | `brunch` | `lunch` | `snack` | `dinner` | `late_night` | `null`(KST 자동 판별)

응답은 핸드오프 문서 6장과 같은 구조야. `offering`(공양 슬롯)은 광고가 없으면 `null`이고, 있으면 아래 구조야.
```json
{"sponsor_name": "식신치킨", "menu": "간장치킨", "comment": "식신 멘트(LLM)",
 "disclosure": "광고 표기 문구(코드 고정)", "link": "", "is_demo": true}
```
- 가게/메뉴/표기/링크는 코드(`app/data/offerings.py`)가 넣고, LLM은 `comment`만 만들어. 밥괘가 확정된 뒤에 별도 호출이라 밥괘 메뉴에는 영향 없음
- 멘트 LLM이 실패하면 고정 문구로 대체 (밥괘는 그대로)
- 실제 광고주 등록: `SPONSORS`에 `{"sponsor_name", "menu", "meals", "link"}` 추가 → 표기는 "이 추천은 OO으로부터 광고비를 받았습니다"로 자동 생성

오류 응답:
- `400`: 존재하지 않는 날짜(없는 윤달 포함), 미래 날짜, 1900년 이전. `detail`에 한글 메시지가 들어가
- `422`: 형식 오류(날짜 형식, calendar/meal 값)

## 4. 환경변수

| 변수 | 필수 | 설명 |
|---|---|---|
| `GEMINI_API_KEY` | X | 없으면 fallback 모드 |
| `GEMINI_MODEL` | X | 모델명. 비우면 `gemini-3.5-flash-lite` (2026-10-20 확정. 실제 호출은 키 설정 후 확인 필요) |
| `GEMINI_TIMEOUT_SEC` | X | Gemini 호출 타임아웃(초), 기본 15. 넘으면 fallback |
| `OFFERING_DEMO` | X | `true`면 결과 아래 공양 슬롯에 **시연용 예시 광고**를 `[광고 예시]` 표기로 노출. 비우면 실제 광고주(`app/data/offerings.py`의 `SPONSORS`)만 노출 (현재 없음 → `offering: null`) |
| `PORT` | Railway가 주입 | 직접 설정하지 않음 |

## 5. Railway 배포 체크리스트

설정 파일
- `railpack.json`: 시작 명령. **없으면 빌드 실패해** (Railpack은 `app/main.py` 구조를 FastAPI로 자동 인식 못 함. `railway.json`의 startCommand는 빌드 준비 단계에서 안 읽힘. 2026-10-20 실제 배포에서 확인)
- `railway.json`: 헬스체크 `/api/health`, 재시작 정책
- `.python-version` (3.10), `requirements.txt`

### 현재 배포 (2026-10-20)
- URL: https://hankki-web-production.up.railway.app
- Railway 프로젝트 `hankki-aekttaem` / 서비스 `hankki-web` / 환경 `production`
- **GitHub `main`에 push하면 자동 재배포돼** (서비스 Source = `jungho-personal/hankki-aekttaem`, branch `main`)
- push 없이 로컬 파일을 바로 올려보고 싶을 때는 CLI로도 가능해 (이 폴더가 서비스에 링크돼 있음)
```bash
railway up --ci --service hankki-web
```

### 최초 배포 (CLI)
```bash
railway login
```
```bash
railway init
```
```bash
railway up
```
```bash
railway domain
```

### 최초 배포 (대시보드 + GitHub)
1. Railway → New Project → Deploy from GitHub repo → 이 레포 선택
2. Settings → Networking → Generate Domain
3. 배포 로그에서 `Uvicorn running on http://0.0.0.0:xxxx` 확인
4. `https://<도메인>/api/health` → `{"status":"ok","llm_enabled":false,...}` 확인

### 워크숍 당일
1. Google AI Studio에서 API 키 발급
2. Railway Variables에 `GEMINI_API_KEY`(필요하면 `GEMINI_MODEL`도) 추가. 변수를 바꾸면 자동으로 재배포돼
3. `/api/health`에서 `llm_enabled: true` 확인
4. 실제 요청을 보내 `is_fallback: false`인지 확인. `true`면 Railway 로그에서 `LLM 실패 → fallback 사용` 사유를 확인
5. 프론트 교체: `static/index.html` 수정 → push(또는 `railway up`) → 재배포

### 주의
- 캐시는 인메모리라 **재배포하면 초기화**돼. 그래서 같은 날 결과가 한 번 바뀔 수 있어
- 레플리카는 1개로 유지해. 여러 개면 인스턴스마다 결과가 다를 수 있어
- API 키는 Railway Variables에만 둬. 코드, 프론트, GitHub에는 절대 넣지 마

## 6. 알려진 한계

- **음력 변환은 중국 음력 기준**(`lunar_python`)이라 한국 음력과 어긋나는 달이 있어. 1920~2049년 중 56구간, 1,768일이 해당돼
  - 대부분은 음력 한 달이 통째로 하루씩 밀리는 경우야
  - 윤달 자체가 다른 해: 1925, 2012(한국 윤3월 / 중국 윤4월), 2017(한국 윤5월 / 중국 윤6월)
  - 일진(오늘 일진, 양력 생일의 일간)은 전 구간 일치해
  - 상세 목록은 `scripts/verify_lunar.log`에 있어
- 결과는 일간 기준이라 같은 일간인 사람끼리는 같은 날 같은 끼니에 같은 밥괘가 나와 (의도된 동작)
