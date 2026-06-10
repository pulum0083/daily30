# 종목 페이지 엔진 — 설계 문서

작성일: 2026-06-10
상태: 승인됨 (Phase 1 MVP 범위)

## 배경과 목표

더블샷은 매일 날짜 고정 URL(브리핑) 3개만 생성한다. 한 번 지나가면 검색에서 아무것도 흡수하지 못하는 **닫힌 푸시 루프**다. 신규 유입은 구독 입소문뿐이라 트래픽이 정체되고, 페이지뷰 기반 광고 수익이 구조적으로 불가능하다.

ETFNow가 작동하는 방식(프로그래매틱 SEO + 매일 쓰는 도구 + 교육 콘텐츠 해자)을 더블샷 자산에 적용한다. **핵심 레버는 종목별 영구 페이지**다. 더블샷은 이미 매일 종목별 실측가·MA20·MA200·스파크라인을 토스 API로 수집하고 있다. 데이터는 이미 생산 중이고, 영구 URL로 펼치기만 하면 된다.

목표: `/stocks/{code}/` 영구 페이지를 양산해 "삼성전자 주가 전망" 같은 롱테일 검색어를 흡수하고, 닫힌 푸시 루프를 열린 검색 루프로 전환한다.

## 범위와 단계

| Phase | 내용 | 데이터 |
| ----- | ---- | ------ |
| **1 (본 문서)** | 종목별 영구 페이지. AI 전망(픽된 날) + 기술 지표(매일) + 하이브리드 맥락 | 기존 파이프라인 데이터만 |
| 2 (후속) | "이 종목을 담은 ETF" 역인덱스 + 조합(co-occurrence) | KRX/네이버 ETF 구성종목 신규 수집 |
| 3 (후속) | 종목별 AI 예측 적중률 표시 | Phase 1에서 기록 시작한 픽→결과 누적 |

본 문서는 **Phase 1만** 구현 범위로 한다. Phase 2·3은 맥락 유지를 위해 기록하되 별도 spec으로 다룬다.

## 아키텍처

### 1. 종목 레지스트리 (`data/stock_universe.json`)

파이프라인에 한 번이라도 등장한 종목 코드를 누적 저장한다.

- 소스: `kospi_candidates`, `sector_stocks`, `stock_picks`(픽). 각 실행 시 등장 코드를 레지스트리에 머지(append-only).
- 레코드: `{ code, name, market(KOSPI/KOSDAQ), sector, first_seen, last_seen }`
- 6자리 코드를 키로 한다. `.KS`/`.KQ` 접미사는 저장하지 않는다(SERVICE_RULES 준수).
- **알려진 처리 필요점**: `stock_picks`는 `name`만 갖고 코드가 없을 수 있다 → `kospi_candidates`/`sector_stocks`의 name↔ticker 매핑으로 코드를 역추적. 매핑 실패 종목은 레지스트리에 넣지 않는다(이름만으로 페이지를 만들지 않는다).

### 2. 일별 데이터 갱신

매 브리핑 실행 시 레지스트리 전체 종목의 데이터를 갱신한다.

- 토스 Open API `get_candles(code, interval="1d", count=300)` → 종가 배열로 가격·등락률(close[-1] vs close[-2])·MA20·MA200·20일 스파크라인 산출.
- 실패 시 네이버 일봉 폴백(SERVICE_RULES의 한국 종목 우선순위와 동일).
- **데이터 정합성 규칙 준수**: 모든 수치는 해당 시점 실측값. LLM 생성 숫자 사용 금지. `validate_analysis._fetch_kospi_realdata` 로직을 재사용한다.
- 출력: `data/stock_pages.json` — `{ code: { price, change_pct, ma20_dist, ma200_dist, golden, volume, sparkline, sector, updated_at } }`

### 3. 페이지 데이터 조립

종목별 페이지 컨텍스트를 만든다.

- **기술 지표(매일)**: `data/stock_pages.json`에서.
- **AI 전망·매매 가이드(픽된 날만)**: 당일 `stock_picks`에 해당 코드가 있으면 주입. 없으면 "오늘은 픽 안 됨" 상태.
- **하이브리드 맥락(매일)**:
  - 과거 픽 이력 → `web/briefings/{date}/{type}/analysis_snapshot.json`들을 스캔해 해당 종목이 픽된 날짜·시나리오 요약 추출(최근 N건).
  - 섹터 내 상대 위치 → `sector_stocks` 같은 섹터 종목과 등락·MA 비교.
  - 수급 → 기존 수집 데이터 재배치(있을 때만).

### 4. HTML 생성

`generate_html.py`를 확장한다.

- `TYPE_MAP`/`SRC_TYPE`에 `stock` 추가, 또는 종목 전용 생성 함수.
- `scripts/config/stock.json` — 섹션 선언(config-driven 패턴 유지).
- `scripts/templates/stocks/stock.html` — 종목 페이지 템플릿. `base.html` 레이아웃 상속.
- 디자인: 더블샷 기존 DS 토큰·컴포넌트(`section-card`, `pred-gauge`, `ma200-gauge`, `stock-pick-card`)를 그대로 재사용. NCAI 토큰은 이미 `:root`에 반영돼 있음. 상승=빨강 `#E03131`/하락=파랑 `#2775ED` 증시 관례 유지.
- 출력: `web/stocks/{code}/index.html`

### 5. 라우팅·SEO

- `vercel.json`에 `/stocks/{code}/` 라우트 추가.
- `write_sitemap_xml()` 확장 → 종목 URL 전체 포함.
- JSON-LD 구조화 데이터(`Dataset` 또는 `FinancialProduct`) 페이지마다 삽입.
- YMYL 대응: 면책·출처·근거를 페이지마다 명시.
- gh-pages 배포 파이프라인 그대로.

### 6. 적중률 기록 (표시는 Phase 3)

`check_accuracy.py`를 확장해 픽→결과를 **종목 단위로** 누적 기록한다.

- 저장: `data/stock_accuracy.json` — `{ code: [{ date, predicted_direction, actual_change_pct, is_correct }] }`
- Phase 1에서는 **기록만** 한다. 페이지에는 표시하지 않는다(자리도 두지 않음 — YAGNI).
- Phase 3에서 이 데이터로 적중률 섹션을 채운다.

## 페이지 구성 (stock-page-ds 목업 확정안)

`/stocks/{code}/` 한 URL이 데이터에 따라 자동 전환.

1. **헤더** — 종목명·코드·섹터칩 / 종가·등락 / 스파크라인
2. **AI 오늘의 전망** (픽된 날만) — `pred-gauge` + 신뢰도 + 시나리오 산문. 아니면 "오늘은 AI 픽에 선정되지 않음 + 기술 지표 안내"
3. **매매 가이드** (픽된 날만) — 진입/목표/손절 타일
4. **기술적 지표** (매일) — MA20·MA200 게이지, 골든크로스, 거래량, 시가총액
5. **하이브리드 맥락** (매일) — 과거 픽 이력, 섹터 내 상대 위치, 수급
6. **면책** — YMYL 고정 문구

## 데이터 출처 현황

| 데이터 | 출처 | 상태 |
| ----- | ---- | ---- |
| 종목 가격·MA·스파크라인 | 토스 Open API → 네이버 폴백 | 기존 사용 중 |
| AI 전망·매매 가이드 | `call_claude` stock_picks | 기존 사용 중 |
| 과거 픽 이력 | `analysis_snapshot.json` (커밋됨) | 복원 가능 |
| ETF 구성종목 (Phase 2) | KRX / 네이버 금융 | 신규 필요 |

ETFNow 출처(KRX·네이버·Yahoo·NASDAQ Trader·업비트) 중 업비트(코인)는 불필요. Phase 2에서 NASDAQ Trader(심볼 리스트) 정도만 신규.

## 검증 기준

1. **레지스트리** → 파이프라인 실행 후 `stock_universe.json`에 당일 등장 종목이 누적되는지. 코드 매핑 실패 종목이 제외되는지.
2. **데이터 갱신** → `stock_pages.json`의 가격이 실제 시장가와 일치하는지(`validate_analysis` 실측과 대조). `.KS`/`.KQ` 미사용 확인.
3. **페이지 생성** → 픽된 종목은 AI 전망 풀세트, 비픽 종목은 기술 지표만 렌더되는지. `/v2/` 경로 미발생.
4. **라우팅·sitemap** → `/stocks/{code}/` 접근 가능, sitemap에 URL 포함, JSON-LD 유효.
5. **적중률 기록** → `check_accuracy` 실행 후 `stock_accuracy.json`에 픽 종목 결과가 누적되는지.

## 범위 밖 (Phase 1)

- ETF 역인덱스·조합 섹션 (Phase 2)
- 적중률 **표시** (Phase 3, 기록만 Phase 1)
- 교육 콘텐츠 롱테일 글
- 애드센스 신청 (트래픽 확보 후)
- KOSPI200/KOSDAQ150 전체 유니버스 확장 (초기엔 자연 누적)

## 리스크

- **YMYL·E-E-A-T**: 구글 금융 콘텐츠 최엄격 심사. 면책·출처·실측 기반임을 페이지마다 강조.
- **AI 생성 콘텐츠 정책**: 스핀 텍스트가 아닌 실측 데이터 기반임이 방어 논리. 비픽 종목 페이지가 과도하게 얇아지지 않도록 하이브리드 맥락으로 보완.
- **유니버스 데이터 부하**: 레지스트리가 커지면 일별 토스 candles 호출량 증가. 초기 자연 누적으로 규모를 통제하고, 호출 실패 시 폴백·부분 갱신 허용.
- **name↔code 매핑**: 픽이 이름만 가질 때 코드 역추적 실패 가능. 실패 시 페이지 미생성으로 안전 처리.
