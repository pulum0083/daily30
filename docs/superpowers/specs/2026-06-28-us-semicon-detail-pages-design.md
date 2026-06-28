# 미국 반도체 종목 상세 페이지 (US Lite Detail) — 설계

작성일: 2026-06-28

## 배경

종목 허브(`web/stocks/index.html`)의 🌙 "밤사이 미국 반도체 시황" 섹션에 노출되는 미국 종목들에 대해, 한국 종목처럼 클릭 진입 가능한 상세 페이지를 만든다. 단, 미국 종목은 한국 종목 상세 엔진(`detail.html`)이 요구하는 데이터(수급·외국인보유율·증권사 목표가·국내 트랙레코드) 대부분을 갖지 못하므로, **시세·차트·52주·MA·분기실적·동종 peers만 담는 경량 페이지**로 만든다.

## 범위

대상 7개 심볼.

| 구분 | 심볼 | 한글명 | 분기실적 |
| --- | --- | --- | --- |
| 단일종목 | AVGO | 브로드컴 | O |
| 단일종목 | NVDA | 엔비디아 | O |
| 단일종목 | AMD | AMD | O |
| 단일종목 | MU | 마이크론 | O |
| 단일종목 | ASML | ASML | O |
| ETF | SOXX | 반도체 ETF | X |
| ETF | SMH | 반도체 ETF | X |

`DRAM`(선행지표용 합성 심볼)은 단일 종목 페이지 대상이 아니다 — 허브 🌙 행에서도 클릭 비활성.

## URL · 라우팅

- URL 체계: `/stocks/us/{ticker소문자}/` (예: `/stocks/us/nvda/`, `/stocks/us/soxx/`)
- 출력 경로: `web/stocks/us/{ticker소문자}/index.html`
- 라우팅: 기존 한국 `/stocks/{code}/` 페이지가 `vercel.json`의 `{ "handle": "filesystem" }`로 자동 해소되는 것과 동일하게 동작할 것으로 본다. 미리보기에서 trailing-slash 해소를 검증하고, 안 되면 `^/stocks/us/([a-z]+)/?$ → /stocks/us/$1/index.html` 규칙을 명시 추가한다.
- 사이트맵: `generate_sitemap`에 7개 URL을 추가(`changefreq: weekly`, `priority: 0.6`).

## 데이터 소스 (전부 yfinance)

데이터 정합성 규칙(SERVICE_RULES 0번) 준수 — 실측만 사용, 추론·하드코딩 금지. 미국 종목은 한국 페이지와 동일하게 **직전 완료 세션 종가 기준**(`close[-1] vs close[-2]`)으로 표기한다.

- 시세·등락률·20일 스파크라인·52주 범위·MA20/MA200: `yf.Ticker(tk).history(period="300d")`의 종가 배열에서 산출.
  - 등락률 = `(close[-1] - close[-2]) / close[-2] * 100`
  - 스파크라인 = 최근 20개 종가
  - 52주 범위 = 종가 배열 min/max, 현재가 위치 %
  - MA20/MA200 거리 = 현재가 대비 이동평균 괴리 %
- 분기실적(단일종목만): `yf.Ticker(tk).quarterly_financials`에서 최근 4~5분기.
  - 매출 = `Total Revenue`
  - 영업이익 = `Operating Income` (없으면 `Total Operating Income As Reported` 폴백)
  - 단위 USD, `$XX.XB` / `$X.XXB` 형식 표기.
- 한글명·티커: `scripts/config/us_stocks.json`의 선언값.
- 실측 실패(가격 None) 시 해당 종목은 `RuntimeError`로 빌드 중단(fail-fast) — 기존 `build_stock_page`와 동일 정책.

정적 as-of-종가 페이지로 만든다(라이브 오버레이 없음). 허브 🌙 타일이 이미 `/api/stocks-live`로 라이브를 담당하므로 상세는 마지막 종가 스냅샷 역할.

## 페이지 섹션 (`stocks/us_detail.html` 신설)

1. **헤더 카드** — 한글명 + 티커 + USD 시세 + 등락률 + 20일 스파크라인
2. **20일 종가 차트** — 한국 페이지의 장중 1분봉 탭은 제거(미국 장은 한국 밤 시간), 20일 종가 단일 패널
3. **실측 핵심 지표** — 52주 범위(현재 위치 %), MA20·MA200 거리
4. **분기 실적** — 매출·영업이익 막대(단일종목만, ETF 생략)
5. **사이드바: 같은 섹터** — 동종 반도체 peers 상호 링크(`us_stocks.json`의 peers 선언, 전부 미국 페이지로 연결)

**생략 섹션**(미국 종목에 데이터 없음): 오늘의 시그널, 외국인 보유율, 미 벨웨더, 증권사 목표가, 수급 동향, 더블샷 트랙레코드.

## 진입 동선

허브 `web/stocks/index.html`의 🌙 섹션 `ue-row`를 클릭 가능하게 만든다.

- 각 행 클릭 → `/stocks/us/{ticker소문자}/`로 이동. ETF 행 포함.
- `DRAM` 선행행은 클릭 비활성(합성 심볼).
- 한국 주도주 타일의 `tile-go` 화살표 UX와 시각적으로 일관되게 처리.

## 구현 단위

- **신규 `scripts/config/us_stocks.json`** — 7개 심볼 선언(ticker, name, kind: stock|etf, peers).
- **신규 `scripts/templates/stocks/us_detail.html`** — 경량 Jinja2 템플릿(위 5개 섹션). 헤더 한 줄 한글 주석.
- **`scripts/generate_html.py`**
  - `build_us_stock_page(stock, peers)` — yfinance 실측 → 컨텍스트 → 렌더 → `web/stocks/us/{tk}/index.html` 기록.
  - `build_all_us_stocks()` — `us_stocks.json` 순회, peer 등락률 캐시 재사용, fail-fast.
  - `--us-stocks` CLI 플래그 추가(기존 `--stocks`와 병렬).
  - `generate_sitemap`에 7개 URL 추가.
- **`web/stocks/index.html`** — 🌙 `ue-row` 렌더에 클릭 핸들러/링크 추가(DRAM 제외).

기존 한국 `detail.html`·`build_stock_page`·`stocks.json`은 건드리지 않는다.

## 빌드 · 운영

- 생성 명령: `python3 scripts/generate_html.py --us-stocks`
- 갱신 주기: 한국 종목 페이지와 같은 시점에 재생성(수동/스케줄). 정적 종가 기준이므로 매 거래일 1회 재생성이면 충분.
- 텔레그램 발송 없음(SERVICE_RULES 8번).

## 검증 기준 (성공 조건)

1. `python3 scripts/generate_html.py --us-stocks` 실행 시 7개 페이지가 `web/stocks/us/{tk}/index.html`에 생성되고, 가격·52주·MA·(단일종목)분기실적이 실측으로 채워진다.
2. 미리보기에서 `/stocks/us/nvda/` 진입 시 페이지가 정상 렌더(라우팅 해소 확인).
3. 허브 🌙 섹션의 NVDA 행 클릭 → `/stocks/us/nvda/` 이동. DRAM 행은 클릭 비활성.
4. ETF(SOXX) 페이지는 분기실적 섹션 없이 렌더.
5. 실측 실패 시 fail-fast로 빌드 중단(빈 수치 페이지 발행 안 됨).
6. 생략 섹션(수급·외국인·증권사·트랙레코드)이 미국 페이지에 나타나지 않는다.

## 비범위 (YAGNI)

- 라이브 가격 오버레이 — 허브 타일이 담당, 상세는 정적.
- 미국 종목 검색 색인(허브 검색창 편입) — 후속.
- 분기실적 외 밸류에이션 지표(PER·시총 등) — 후속.
- DRAM·QQQ 등 비대상 심볼 페이지.
