# 종목 상세 페이지 엔진 main 통합 — 설계·컨텍스트 노트

작성일: 2026-06-24
상태: 조사 완료, 구현 대기

## 배경 / 문제

라이브(`https://doubleshot.space/stocks/`)에서 종목 상세 페이지(`/stocks/{code}/`)가 **모두 404**.

- 허브(`web/stocks/index.html`)는 `goStock(code)` → `/stocks/{code}/`로 링크하지만, 해당 정적 파일이 main에 없음.
- Vercel은 디렉터리 기반 정적 서빙이라 파일이 없으면 404 (별도 라우팅 규칙 불필요 — 파일만 있으면 됨).

## 근본 원인

종목 상세 페이지 + 생성 엔진 전체가 **`feature/stock-page-engine` 브랜치에만 존재하고 main에 미머지** 상태.

- 해당 브랜치는 main보다 **411 커밋 뒤처짐**, feature가 main 대비 29 커밋 앞섬 (크게 divergent — 전체 머지는 부적합).
- 관련 커밋: `20809aa`(프로토 2종) → `9da33da`(3종목 실생성+사이트맵) → `735d17e`(미생성 peer 404 방지).

## feature 브랜치 엔진 구조

| 구성요소 | 경로(feature) | 역할 |
| --- | --- | --- |
| 생성기 | `scripts/generate_html.py` `build_stock_page()` / `build_all_stocks()` | stocks.json 순회 → 상세 HTML 생성 |
| 실측 래퍼 | `generate_html.py` `stock_realdata(code)` | `_fetch_kospi_realdata` + `_fetch_stock_closes`로 시세·sparkline·52주 |
| 종가 헬퍼 | `generate_html.py` `_fetch_stock_closes()` / `_naver_daily_closes()` | 52주 범위용 일봉 종가(토스 우선·네이버 폴백) |
| CLI | `generate_html.py` `--stocks` 플래그 | 일괄 생성 진입점 |
| 유니버스 | `scripts/config/stocks.json` | 3종목(005930·000660·005380) + peers |
| 템플릿 | `scripts/templates/stocks/detail.html` (191줄) | 자체완결 standalone HTML |
| 스타일 | `web/assets/stocks.css` (283줄) | 자체 `:root` 정의, 완결형 |
| 스크립트 | `web/assets/stocks.js` (104줄) | `data-spark` → sparkline SVG 렌더 |

## 호환성 조사 결과

### ✅ 호환 (그대로 포팅 가능)
- main의 `validate_analysis.py`에 `_fetch_kospi_realdata` 존재. 반환 `_closes_to_realdata` → `price`, `change_pct`, `sparkline` 제공.
- `stock_realdata` 래퍼가 추가하는 `week52_low/high/pos_pct`와 합쳐 템플릿이 쓰는 `rd.*` 필드 전부 충족.
  - 템플릿 사용 rd 필드: `price`, `change_pct`, `sparkline`, `week52_low`, `week52_high`, `week52_pos_pct` (※ `rd.min`은 오탐 — pretendard.min.css).
- `_fetch_stock_closes`는 토스 실패 시 네이버 폴백 → 토스 IP차단 현재도 동작.
- stocks.css / stocks.js 자체완결 → 그대로 가져오면 됨.

### ⚠️ 수정 필요 (staleness 갭)
1. **섹터 링크 URL 불일치** — 템플릿은 `/stocks/sectors/{한글}/`(복수형·한글), main 실제는 `/stocks/sector/{영문키}/`(단수형·영문키: semicon/power/...). → 404.
   - 해결: stocks.json에 `sector_key` 추가, 템플릿 링크를 `/stocks/sector/{{ stock.sector_key }}/`로 수정 (브레드크럼 + "섹터 전체 →" 2곳).
2. **standalone에서 `goHub`/`goBack` 미정의** — 브레드크럼·섹터칩 `onclick="event.preventDefault();goHub(...)"`가 detail 페이지엔 로드 안 됨(stocks.js만 로드). preventDefault가 href 폴백까지 막음.
   - 해결: 해당 onclick 제거하고 순수 href 링크로. (`goBack` 뒤로가기 버튼은 stocks.js에 정의돼 있으면 유지, 없으면 제거.)
3. **main generate_html.py에 `_fetch_kospi_realdata` import 없음** → import 추가 필요.
4. **사이트맵** — 종목 상세 URL을 `write_sitemap_xml`에 포함.
5. **허브 goStock 가드** — 허브는 다수 종목(012450·035420·035720 등)에 `goStock()` 링크하지만 생성 페이지는 3종목뿐. 나머지는 여전히 404.
   - 해결: `STOCK_PAGES`를 생성된 3종목으로 갱신하고, `goStock`이 `STOCK_PAGES`에 없으면 이동 대신 "준비 중" 툴팁. (feature의 `735d17e` 의도 반영.)

### 데이터 정합성 메모
detail.html은 **시세·sparkline·52주만 실측**, 나머지(수급·기술지표·목표가·분기실적·담은ETF·신호칩·"오늘 왜 움직였나")는 **일러스트레이션**. 페이지 상단 `proto-tag` 배너 + 각 섹션 refnote로 명시 고지함. SERVICE_RULES §0 실측 원칙상 "실측 아님"을 명확히 표기하는 한 허용. 후속 과제로 실측 전환 필요.

## 구현 계획 (태스크)

1. **에셋 포팅** — `web/assets/stocks.css`, `web/assets/stocks.js`를 feature에서 가져오기.
2. **유니버스** — `scripts/config/stocks.json` 포팅 + 각 종목에 `sector_key` 필드 추가(005930·000660→semicon, 005380→auto).
3. **템플릿 포팅·수정** — `scripts/templates/stocks/detail.html`:
   - 섹터 링크 2곳 → `/stocks/sector/{{ stock.sector_key }}/`
   - 브레드크럼·섹터칩 `onclick` 제거(순수 href)
4. **생성기 포팅** — `generate_html.py`에 `_naver_daily_closes`, `_fetch_stock_closes`, `stock_realdata`, `build_stock_page`, `build_all_stocks` 추가 + `_fetch_kospi_realdata` import + `--stocks` 플래그.
5. **사이트맵** — 종목 상세 URL 포함.
6. **허브 가드** — `STOCK_PAGES` 3종목 갱신 + `goStock` 미생성 코드 가드.
7. **생성·검증·커밋** — `python3 scripts/generate_html.py --stocks`로 오늘자 실측 3페이지 생성 → 프리뷰 확인 → 커밋.

## 검증 기준
- `/stocks/005930/`, `/stocks/000660/`, `/stocks/005380/` 200 응답 + 시세·sparkline·52주 실측 렌더.
- 상세→섹터/peer 링크 클릭 시 404 없음.
- 허브에서 미생성 종목 클릭 시 404 대신 "준비 중".
