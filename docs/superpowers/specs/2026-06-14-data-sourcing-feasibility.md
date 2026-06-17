# 종목 서비스 데이터 수급 타당성 검토 (2026-06-14)

프로토타입(`mockups/flow-clickable.html`)에서 설계한 기능을 실제 서비스로 구현할 때
모든 데이터가 수급되는지, 어느 플랫폼에서 가져오는지 정리한 레퍼런스.

**종합 판정**: 구현 가능. 토스 Open API + 네이버 금융 조합으로 ~95% 실측 검증 완료.
단일 블로커 없음. 유일한 공백은 ETF 전체 구성종목(KRX 차단 → TOP10로 대체, v1 확정).

---

## 1. 기능 → 데이터 → 소스 → 상태

| 기능 | 핵심 데이터 | 소스 | 상태 |
| --- | --- | --- | --- |
| 가격·등락·MA20·MA200·골든크로스·스파크라인 | 일봉 | 토스(1순위) / 네이버 일봉(폴백) | ✅ 운영 중 |
| 직전 장중 차트 | 1분봉 | 토스 | ✅ |
| 시가총액 | `integration.marketValue` | 네이버 | ✅ |
| 52주 범위 | high/low | 네이버 `etfItemList`·일봉 | ✅ |
| 수급(외국인·기관·개인 5일+보유율) | `integration.dealTrendInfos` | **네이버 단독** | ✅ ⚠폴백 없음 |
| 증권사 목표주가·투자의견 | `integration.consensusInfo` | **네이버 단독** | ✅ ⚠폴백 없음 |
| 실적 분기추세(매출·영업이익) | `finance/quarter` | **네이버 단독** | ✅ ⚠폴백 없음 |
| AI 픽·전망 | `call_claude` | 자체 | ✅ 운영 중 |
| 기술신호 점수(티어2) | 일봉 계산 | 자체 | ✅ |
| 적중률 | `check_accuracy` | 자체 | ✅ 운영 중 |
| ETF 메타(AUM·추적지수·운용사·보수·상장일·분배·NAV) | `etfAnalysis` | **네이버 단독** | ✅ ⚠폴백 없음 |
| ETF 구성 TOP10 | `etfAnalysis` | 네이버 | ✅ |
| **ETF 전체 구성종목** | 전체 PDF(Portfolio Deposit File) | KRX | ❌ 차단 → v2 |
| 섹터 비중 | TOP10 근사 | 네이버 | ✅ 한계(전체 분포는 근사) |
| 지수 추세 바(ETF) | 브리핑 `prediction` / 기술신호 | 자체 | ✅ |
| 분배 건전성 | 분배율·총수익(Y1) | `etfAnalysis` | ✅ 스크립트 있음 |
| 패시브 노출도 | AUM×TOP10비중·시총·ADV20 | 네이버 | ✅ `build_etf_exposure.py` |
| 인컴 설계기 | 분배율·총수익·과세·상장일 | `etfAnalysis` | ✅ `build_income_etfs.py` |
| 랭킹(거래량·상승·하락)·섹터 | 일별 시세·industryCode | 네이버 | ✅ |

검증 시점: 네이버 4종(etfItemList·etfAnalysis·integration·finance/quarter) 2026-06-14 라이브 호출 확인.
토스·네이버 일봉·yfinance는 운영 파이프라인에서 사용 중.

## 2. 플랫폼별 평가 (KRX·네이버·Yahoo·NASDAQ Trader·업비트 + 토스)

| 플랫폼 | 역할 | 판정 |
| --- | --- | --- |
| **네이버 금융** | 주력 백본. 무인증으로 펀더멘털 전부(수급·목표가·실적·ETF메타·시총·52주) | ✅ 핵심. 비공식·ToS·차단 리스크 |
| **토스 Open API** | 가격·일봉/1분봉·환율. 인증·안정 | ✅ 가격 백본. 펀더멘털 없음 → 네이버 보완 |
| **KRX** | 공식. 유일 가치 = ETF 전체 구성종목(PDF) | ⚠ OTP 토큰 절차·차단(OTP 없이 400). v2 |
| **Yahoo(yfinance)** | 미국 종목 폴백 | ⚠ 보조. **국내 `.KS`는 KOSDAQ 유령데이터라 금지** |
| **NASDAQ Trader** | 미국 심볼 디렉토리(접근 OK, ETF 플래그 포함) | 미국 확장(Phase 2) 전엔 불필요 |
| **업비트** | 코인 시세 | ❌ 불필요(주식·ETF 서비스) |

### "ETF 전체 PDF" 보충
PDF = Portfolio Deposit File(납부자산구성내역) = ETF가 담은 전체 구성종목·비중의 공식 일별 명세.
네이버는 TOP10만 제공 → 전체(예: 200종목)는 KRX 공식 발표를 받아야 하나 인증/로그아웃 벽에 막힘.
v1은 TOP10로 가고(패시브 노출도 역인덱스도 TOP10 기준이라 일관), 전체 리스트는 v2.

## 3. 최대 리스크 — 네이버 무인증 단일 의존

수급·목표주가·실적·ETF메타는 **네이버 ONLY**라 토스/yfinance로 대체 불가.
네이버가 차단·구조 변경 시 해당 섹션이 통째로 붕괴.

**완화책(대부분 STOCKS_SERVICE_RULES에 이미 반영):**
- **Graceful degradation** — 수집 실패 영역은 섹션 생략(§0). 페이지가 깨지지 않고 축소됨.
- 호출 예의(rate limit·간격)·결과 캐싱·일 1회 배치.
- 대체 가능한 필드(가격·캔들)는 토스 우선 유지.

## 4. 서비스 적용(구현) 측면

**재사용**: `generate_html.py`(config-driven), `validate_analysis`(실측 주입·교정 게이트),
`toss_client`, `build_etf_exposure.py`/`build_income_etfs.py`(운영 중).

**신규 필요**:
- `data/stock_universe.json` 레지스트리(KOSPI200 시드 + 픽 누적)
- `data/stock_pages.json` 일별 빌더(가격·MA·신호 + 참고 데이터 fetch 포함)
- 종목·ETF HTML 템플릿(`scripts/templates/stocks/`)
- 라우팅·sitemap·JSON-LD, GHA 잡

**부하**: Phase 1a ~300페이지 × (토스 캔들 + 네이버 3~4콜) ≈ 일 1천 안팎. 감당 가능, 모니터링 후 필요 시 티어 차등(조기 최적화 금지).

**검증**: 기존 `validate_analysis` 실측 주입 패턴을 참고 데이터(목표가·수급·실적)까지 확장.

## 5. 결론

데이터·구현 모두 실현 가능. 막는 단일 요소 없음. 관리 포인트 3가지.
1. 네이버 의존 집중 → graceful degradation
2. ETF 전체 구성종목 → TOP10로 v1, KRX는 v2
3. 호출 부하 → 배치·캐싱

관련 문서: `STOCKS_SERVICE_RULES.md`(운영 룰), `2026-06-10-stock-page-engine-design.md`(설계).
