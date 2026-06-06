# Double-Shot 서비스 운영 규칙

> 운영 중 발생한 이슈와 설계 결정을 바탕으로 정리한 규칙.
> CLAUDE.md의 운영 규칙과 함께 참고한다.

---

## 1. 라이브 스코어보드 노출 규칙

스코어보드는 **당일 브리핑과 과거 브리핑 모두**에 표시된다. 상태에 따라 렌더링 방식이 달라진다.

### 당일 브리핑 — 노출 조건 (AND)

| 조건 | 내용 |
|------|------|
| URL 날짜 = 오늘 KST | `/briefings/YYYY-MM-DD/kospi/`의 날짜가 오늘이어야 함 |
| 평일 | 토·일 미표시 |
| 08:50 KST 이후 | 그 이전 시간대 `display:none` |

### 당일 상태 분기

| 시각 (KST) | 상태 | 배지 색상 |
|-----------|------|---------|
| 08:50 ~ 08:59 | 준비 중 | 골드 |
| 09:00 ~ 15:29 | 장중 LIVE | 초록 |
| 15:30 ~ 23:59 | 마감 | 회색 |

### 과거 브리핑 — 정적 결과 표시

URL 날짜가 오늘보다 이전이면 폴링 없이 정적 결과를 표시한다.

- **`data-actual-pct` 속성 있음**: 예측 적중/빗나감 메시지 + 등락률 + 게이지 바늘 렌더링.
- **`data-actual-pct` 비어 있음**: "결과 집계 중…" 표시. 다음 날 09:10 `check_accuracy.py` 실행 후 자동 주입.
- **뉴스 이슈**: `/data/kospi-news-{date}.json` (날짜별 아카이브)를 fetch. 없으면 빈 상태.
- **시장 지표 패널**: `/data/market-{date}.json`을 fetch해 종가·수급 정적 표시 (스파크라인 없음).

### 공통 원칙

- **스코어보드는 HTML에 `display:none`으로 생성된다.** JS가 조건을 충족할 때만 표시. CSS 조작이나 인라인 스타일 제거로 강제 표시하면 안 된다.
- `isPast` 플래그(`initLiveScoreboard()` 내부)와 `mktIsPast`(`initLiveMarketPanel()` 내부)는 별도로 계산된다. 상태 로직 수정 시 두 곳 모두 확인.

---

## 2. 휴장일 처리 규칙

### 브리핑 미생성

- `holiday_check.py`가 한국·미국 공휴일을 확인해 휴장일에는 파이프라인 자체가 실행되지 않는다.
- 휴장일에는 해당 날짜의 브리핑 HTML이 생성되지 않는다.

### 이미 생성된 페이지가 있을 경우

다음 두 가지를 모두 처리한다.

1. **HTML 파일 삭제**  
   `web/briefings/YYYY-MM-DD/kospi/index.html` 및 디렉토리 삭제.

2. **briefings-list.json 초기화**  
   해당 날짜의 `kospi` 슬롯을 `ready` → `pending`으로 변경:
   ```json
   "kospi": {
     "state": "pending",
     "scheduled_time": "07:30"
   }
   ```

### 주의

- 과거 브리핑이 남아있는 상태에서 다음날 장중에 접근하면 라이브 스코어보드가 노출될 수 있다. URL 날짜 체크(§1)가 막아주지만, 휴장일에는 당일 브리핑 자체가 없으므로 이전 날짜 페이지가 계속 노출된다. **혼선을 막으려면 이전 날짜 페이지를 삭제한다.**

---

## 3. 브리핑 페이지 생명주기

```
생성
  generate_html.py 실행
    → web/briefings/YYYY-MM-DD/{type}/index.html 생성
    → briefings-list.json 슬롯 state: "ready" 등록

수정
  generate_html.py 재실행 시 HTML 완전 재생성 (수동 수정 덮어씀)
  수동 패치가 있으면 재생성 전에 반드시 확인

삭제
  HTML 파일 + 디렉토리 삭제
  briefings-list.json 슬롯 state: "pending"으로 초기화
  generate_html.py --write-list-only 실행 → 목록 페이지 갱신
```

---

## 4. UI 설계 원칙

### 게이지 색상 — 투자 방향성과 분리

이 서비스의 기본 색상 규칙은 `빨강 = 상승`, `파랑 = 하락`이다.  
**예측 정확도 게이지는 이 색상 규칙을 따르지 않는다.** 혼동을 방지하기 위해 별도 체계를 사용한다.

| 영역 | 색상 | 의미 |
|------|------|------|
| 이탈 (좌) | 회색 | 중립 / 아직 미결 |
| 박빙 (중앙) | 회색(surface-inset) | 팽팽 |
| 적중 (우) | 초록 (#16A34A) | 정확 / 성공 |

> 빨강을 "적중"에 쓰면 "경고/하락"으로 오해할 수 있다. 초록은 전 세계적으로 "정확/성공"을 의미한다.

### 예측 섹션 — 항상 펼쳐진 상태

예측 섹션(방향 게이지, 신뢰도, 근거)은 **항상 펼쳐진 상태**로 표시한다.  
아코디언 토글은 제거됐으며, 자동 접힘 로직도 추가하지 않는다.

---

## 5. 텔레그램 발송 금지 조건

- 작업 완료 알림, 수동 테스트, 개발 중 임시 실행 시 발송 금지.
- 스케줄된 브리핑 파이프라인 외 ad-hoc 발송은 구독자 채널 노이즈가 된다.

---

## 6. 라이브 스코어보드 UI 규칙

### 색상 — 예측 방향 기준 (시장 관행과 동일)

| 상태 | 색상 | CSS 변수 |
|------|------|---------|
| 상승 (up) | 빨간 | `--up` (#E03131) |
| 하락 (dn) | 파란 | `--dn` (#2775ED) |

`lsb-pred-tag`(예측 방향 뱃지)는 **verdict(순항/빗나감)가 아닌 예측 방향 고정 컬러**를 사용한다.  
verdict 컬러는 헤드라인 em 텍스트에만 적용한다.

### 스코어보드 코멘트 — 방향별 분리

- 상승 우위 `hit` / 상승 우위 `miss` / 하락 우위 `hit` / 하락 우위 `miss` 4가지 풀로 분리.
- 30초(현재 10초) 갱신마다 각 풀에서 **랜덤 선택**.
- **하락 우위 miss**(하락 예측인데 상승) 코멘트는 기분 좋은 표현으로 구성한다.
- "순항 중"처럼 방향이 함축된 표현은 방향 무관 풀에 넣지 않는다.

### 실시간 갱신 주기

| 항목 | 설정 |
|------|------|
| 코스피 지수 폴링 | 10초 (`setInterval(fetchKospi, 10000)`) |
| API 캐시 | `s-maxage=10` (네이버 API 10초마다 실호출) |
| 뉴스 이슈 갱신 | 1시간 (Vercel cron, GitHub Actions) |

### 마감 후 예측 결과 타이틀 구조

`isAfterMarket()` 블록에서 표시되는 텍스트 규칙.

| 요소 | DOM ID | 형식 |
|------|--------|------|
| 대표 타이틀 | `lsb-head-em` | 예측 결과 요약문 ("오늘 장이 종료됐어요." 금지) |
| 서브 타이틀 | `lsb-sub` | 등락률 한 줄 ("nn% 하락 마감이에요.") |

케이스별 규칙:

| 케이스 | 대표 타이틀 | 비고 |
|--------|------------|------|
| hit.up (상승 예측 적중) | "상승 예측이 맞았어요." 등 | 아쉬움 표현 없음 |
| hit.dn (하락 예측 적중) | "하락 예측이 맞았어요. [아쉬움 표현]" | **아쉬움 표현 필수** |
| miss.up (상승 예측 실패) | "아쉽게도 예측이 빗나갔어요." 등 | |
| miss.dn (하락 예측 실패) | "이번엔 AI가 틀렸어요." 등 | 기분 좋은 오답 표현 |
| tight (박빙) | "박빙으로 마감했어요." 등 | |

`CLOSE_MSGS` 구조는 케이스마다 `title` 배열과 `sub` 배열을 분리 관리하며, 인덱스를 공유해 `title[idx]`와 `sub[idx % sub.length]`를 쌍으로 출력한다.

---

### 코스피 지수 — 오도미터 효과

- 지수 업데이트 시 자릿수별 독립 롤링 애니메이션 적용 (`lsb-odo-digit` + `lsb-odo-inner`).
- `<span>`은 기본 `display:inline`이라 CSS `transform` 미작동 → `.lsb-idx`에 `display:inline-block` 필수.
- 첫 렌더는 `transition:none`으로 즉시 세팅, 이후 갱신부터 `0.55s cubic-bezier` 롤링.

### 카운트다운 타이머

- `lsb-cd-num`(숫자 span)만 `overflow:hidden` 래퍼 안에서 슬라이드업 애니메이션.
- `fetchKospi` 호출 시 카운터 10 리셋 → 9 → 8 … 0 순으로 표시.

---

## 7. 뉴스 수집 스케줄 (kospi-news-live)

**30분 단위** 수집. 09:10·09:30은 장 초반 2슬롯, 이후 정각·30분 반복, 15:00 마감.

| 시각 (KST) | UTC cron |
|-----------|----------|
| 09:10 | `10 0 * * 1-5` |
| 09:30 | `30 0 * * 1-5` |
| 10:00 | `0 1 * * 1-5` |
| 10:30 | `30 1 * * 1-5` |
| 11:00 | `0 2 * * 1-5` |
| 11:30 | `30 2 * * 1-5` |
| 12:00 | `0 3 * * 1-5` |
| 12:30 | `30 3 * * 1-5` |
| 13:00 | `0 4 * * 1-5` |
| 13:30 | `30 4 * * 1-5` |
| 14:00 | `0 5 * * 1-5` |
| 14:30 | `30 5 * * 1-5` |
| 15:00 | `0 6 * * 1-5` |

Vercel cron → `/api/trigger?type=kospi-news-live` → GitHub Actions `kospi-news-live` job → `fetch_news_live.py` 순으로 실행.

**주의:** `kospi-news-live` job은 `actions/checkout@v6` + `GITHUB_TOKEN`을 사용한다. `GH_PAT` secret은 이 job에 불필요하며, 사용하면 secret 미설정 시 checkout 실패한다.

플레이스홀더("오늘의 이슈 준비 중") 항목은 히스토리에 누적되지 않도록 `fetch_news_live.py`에서 필터링한다.

---

## 8. 배포 워크플로우

**Vercel은 `main` 브랜치 push 시 자동 배포된다.** 따라서 push = 배포.

- 코드 수정 → `git commit` (push 없음)
- 여러 커밋을 쌓은 뒤 **"배포해줘"** 요청 시 `git push` 1회
- Vercel 배포 큐 누적 방지 및 불필요한 배포 최소화

Claude는 명시적 배포 요청 없이 `git push`하지 않는다.

### Vercel 프로젝트 구조 (2026-06-05 통합 후)

| 항목 | 값 |
|------|-----|
| 프로젝트명 | `double-shot` (단일, 팀: `pulum0083s-projects`) |
| 연결 레포 | `pulum0083/daily30` (`main` 브랜치) |
| 도메인 | `doubleshot.space` |
| `.vercel/project.json` | `projectId: prj_XRVsCkXlroRpbd9WVPgtH3OiE6Fo` |

`daily30` Vercel 프로젝트는 삭제됨. 동명의 프로젝트를 새로 만들지 말 것.  
`main` push → Vercel 자동 production 배포 → `doubleshot.space` 자동 반영.

---

## 9. 데이터 신선도 — 브리핑 생성 시각 기준

> **브리핑에 쓰이는 모든 시장 데이터는 브리핑 생성 시각 기준 최신 데이터여야 한다.**

### 원칙

- **전날 데이터·몇 시간 전 데이터 사용 금지.** `latest_{type}.json`에 저장된 데이터가 오래됐으면 `fetch_data.py`를 재실행한 뒤 브리핑을 생성한다.
- 수동 재실행 시 가장 먼저 데이터 수집부터 시작한다:
  ```
  python3 scripts/fetch_data.py --type us       # 또는 kospi / kospi-close
  python3 scripts/fetch_news.py --type us
  python3 scripts/call_claude.py --type us --no-html
  python3 scripts/validate_analysis.py --type us
  python3 scripts/call_claude.py --type us --render
  ```
- `latest_{type}.json`의 `generated_at` 필드가 오늘 날짜가 맞는지 확인한다.  
  틀리면 수집부터 다시 시작한다.

### 데이터 수집 시각 기준

| 브리핑 | 수집 기준 시각 |
|--------|--------------|
| 코스피 예측 (07:30) | 당일 07:30 전후 수집 데이터 |
| 코스피 마감 (16:00) | 당일 장 마감(15:30) 후 수집 데이터 |
| 미국 (21:20) | 당일 21:20 전후 수집 데이터 (프리마켓 반영) |

---

## 10. 시장 데이터 수집 우선순위 (Toss API 1순위)

> **Toss 증권 Open API를 1순위로 사용한다. 네이버·Yahoo Finance는 폴백이다.**

### 우선순위 표

| 데이터 | 1순위 | 폴백 |
|--------|-------|------|
| 국내 종목 캔들 (일봉·분봉) | Toss `get_candles(symbol)` | 네이버 일봉 API |
| 국내 종목 현재가 | Toss `get_prices([symbols])` | 네이버 금융 |
| 미국 종목 캔들·현재가 | yfinance (티커 직접) | — |
| 환율 (USD/KRW) | Toss `get_exchange_rate()` | 네이버 환율 API |
| 지수 (코스피·나스닥 등) | yfinance | — |

### Toss API 함수 (`scripts/toss_client.py`)

| 함수 | 설명 |
|------|------|
| `get_candles(symbol, interval, count)` | 캔들 조회. `interval="1d"` 일봉, `"1m"` 1분봉. 최대 300개(내부 페이지네이션). |
| `get_prices(symbols)` | 현재가 일괄 조회. 심볼 리스트 최대 200개. |
| `get_exchange_rate(base, quote)` | 환율. 기본 USD→KRW `midRate` 반환. |

### 국내 종목 심볼 형식

- Toss API 심볼: `KR7005930003` (ISIN 형식) — `.KS`/`.KQ` 접미사 사용 금지.
- 네이버 폴백: 6자리 코드 (`005930`) — `.KS`/`.KQ` 접미사 사용 금지.
- yfinance에 `.KS`를 붙이면 KOSDAQ 종목이 유령 데이터(하루 stale)를 반환하므로 국내 종목에는 yfinance 사용 금지.

### Toss API 인증

`config.json`의 `toss.client_id` / `toss.client_secret` 또는 환경변수 `TOSS_CLIENT_ID` / `TOSS_CLIENT_SECRET`.  
토큰은 내부적으로 캐시되며 만료 60초 전 자동 갱신된다.

---

## 11. 데이터 정합성 — 배포 전 필수 체크

> **LLM이 생성한 수치는 신뢰하지 않는다. 배포 전에 반드시 실측으로 검증한다.**

### 9-1. 자동 파이프라인 순서 (절대 바꾸지 말 것)

```
call_claude --no-html        분석 JSON 생성
  → validate_analysis        실측 주입 + 금지패턴 교정
  → call_claude --render     교정된 데이터로 HTML 생성
  → send_telegram            HTML 생성 후 발송
```

`--render` 전 단계(HTML·텔레그램)가 검증 전에 생성되면 교정이 반영되지 않는다.

### 9-2. 수동 배포 전 체크리스트

브리핑 HTML을 직접 생성하거나 수정할 때 아래 항목을 반드시 확인한다.

**종목 가격·등락률**
- [ ] `analysis_{type}.json`의 종목 가격·등락률이 실제 시장 데이터와 일치하는가
- [ ] 미국 종목: yfinance 직접 조회 / 국내 종목: 네이버 일봉 API (`.KS` 접미사 금지)
- [ ] sparkline 데이터가 빈 배열(`[]`)이 아닌가

**코스피 마감 브리핑 추가 확인**
- [ ] `market_breadth.up`, `market_breadth.down` 모두 0이 아닌가
- [ ] `investor_trading.foreign.net`, `.institution.net`, `.individual.net` 정상인가
- [ ] `dpick` 배열이 존재하고 비어있지 않은가

**공통**
- [ ] `vercel.json`의 `/briefings` 루트 라우트가 오늘 최신 브리핑을 가리키는가
- [ ] `web/data/briefings-list.json`이 오늘 슬롯을 포함하는가

### 9-3. 로컬 수동 실행 시 Claude Desktop 환경변수 충돌 주의

Claude Desktop 앱이 빈 `ANTHROPIC_AUTH_TOKEN` 환경변수를 주입해 Anthropic SDK가 오동작한다.
`call_claude.py`의 `get_anthropic_api_key()`에서 자동으로 정리하므로 별도 조치 불필요.
단, SDK를 직접 호출하는 다른 스크립트에서는 아래를 확인한다.

```python
for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_CUSTOM_HEADERS"):
    if not os.environ.get(var):
        os.environ.pop(var, None)
```

### 9-4. generate_html.py 실행 시 덮어쓰기 주의

`generate_html.py --type {kospi|us|kospi-close}` 실행 시 해당 날짜 브리핑 HTML이 **완전 재생성**된다.
수동 수정 내역이 있으면 실행 전 반드시 확인.

브리핑 목록 JSON만 갱신할 때는 `--write-list-only` 사용:
```bash
python3 scripts/generate_html.py --write-list-only
```
