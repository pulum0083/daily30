# 종목 홈 신호 — 장중 실시간 / 마감 합류 하이브리드 아키텍처

작성 2026-06-27. 대상: 홈(`web/stocks/index.html`)의 3개 메뉴 — 오늘의 특이 신호 · 신호별 랭킹 · ETF로 읽는 시황.
선행: [신호 분류 규칙](2026-06-27-stock-home-signals-rules.md) · [색 절제 디자인](2026-06-27-stock-home-signals-color-design.md) · 콘셉트 메모(홈=시간 인지형 대시보드).

## 결론 (데이터 점검 결과)

3개 메뉴는 **수급 신호만 빼면 장중 실시간 구성이 가능**하다. 종목별 실시간/장중 잠정 수급은 무료 소스로 제공되지 않으므로(아래 점검 근거), 수급 계열은 **마감 후 일 단위**로만 합류시킨다.

### 실측 점검 근거 (2026-06-27)

| 소스 | 제공 필드 | 단위·주기 | 수급? |
| --- | --- | --- | --- |
| `polling.finance.naver.com/api/realtime/domestic/stock/{code}` | 현재가·등락률·누적거래량 | 종목별, 장중 실시간 | ✗ |
| `api.finance.naver.com/service/itemSummary.naver?itemcode={code}` | 현재가·**거래대금(`amount`)**·고저·시총·PER | 종목별, 장중 실시간 | ✗ |
| `/api/kospi-live` | 코스피 지수·등락률 | 시장, 10초 | — |
| `/api/market` | 코스닥·코스피200·환율·**시장 전체 수급** | 시장 단위, 장중 | △ 시장 합계만 |
| `m.stock.naver.com/api/stock/{code}/trend` | 외국인·기관·개인 순매수 수량·외국인보유율 | 종목별, **bizdate 일 단위 (마감 후 확정)** | ✓ 단 일 단위 |
| 일봉 스냅샷 `stocks-snapshot.json` | `vol_avg20`·`wk52_high`·외국인보유율 | 종목별, 마감 후 1회 | — |

> `trend`는 종목별 수급을 주지만 최신 행이 직전 거래일(bizdate)이며 **"오늘 장중 잠정" 행이 없다.** 따라서 장중 종목별 수급은 불가.

## 신호 2단 모델

각 신호 축을 데이터 가용성에 따라 단계로 분류한다.

| 신호 축 | 장중판(실시간) | 마감판(장 마감 기준) | 필요 데이터 |
| --- | :---: | :---: | --- |
| 역행(counter-trend) | ✅ | ✅ | 종목 등락률(polling) + 코스피(kospi-live) |
| 거래대금 쏠림 | ✅ | ✅ | `itemSummary.amount` |
| 신고가 근접 | ✅ | ✅ | 현재가(polling) + `wk52_high`(스냅샷) |
| 투매: 거래량 급증 + 급락 | ✅ | ✅ | 누적거래량(polling) + `vol_avg20`(스냅샷) + 등락률 |
| 투매: 매도 수급 조건 | ❌ | ✅ | 종목별 수급(`trend`, 일 단위) |
| 수급(연속·전환) | ❌ | ✅ | 종목별 수급 히스토리(`trend`, 일 단위) |
| ETF로 읽는 시황 | ✅ | ✅ | ETF 거래량·등락률(polling) — 수급 미사용, **24h 가용** |

- **장중판**: 역행·거래대금·신고가·거래량(투매 일부) + ETF 시황. 수급 계열은 미표시.
- **마감판**: 위 + 수급 신호(외국인/기관 연속·전환), 투매의 수급 조건 확정. = 완성본.
- ETF 시황은 수급을 안 쓰므로 시간대 무관 항상 실시간.

## API 설계 — `/api/signals` (신설)

새 데이터 의존성 없음. 기존 소스 조합으로 신호를 서버에서 계산해 반환한다.

**입력**
- 종목 유니버스 41 + ETF 10에 대해 `polling.finance`(현재가·등락률·누적거래량) + `itemSummary`(거래대금) 병렬 fetch.
- 코스피 등락률은 `/api/kospi-live` 재사용(또는 동일 호출).
- 정적 분모(`vol_avg20`·`wk52_high`)는 `stocks-snapshot.json`에서 읽음.

**판정 로직** — 임계값은 [규칙 스펙](2026-06-27-stock-home-signals-rules.md)의 상수 그대로 사용.
- 역행: `sign(stock_pct) ≠ sign(kospi_pct)` AND `|stock_pct − kospi_pct| ≥ 3.0%p`
- 거래대금 쏠림: `amount` 내림차순 상위 `TURNOVER_TOP_N(3)`
- 신고가: `price ≥ wk52_high × 0.98`
- 투매(장중판): `vol/vol_avg20 ≥ 1.5` AND `stock_pct ≤ −3.0%` (수급 조건 제외)

**출력**
```json
{ "phase": "intraday|closed", "asof": "...", "signals": [ {code,name,sector,pct,dir,cats:[...],badges:[...],why} ], "etf": {...} }
```
- `phase`는 `krMarketOpen()`(09:00~15:30 KST)으로 판정. `intraday`면 수급 cats 생략, `closed`면 `trend` 기반 수급 신호 포함.
- 응답 모양은 현재 `PROTO_SIGNALS`/`PROTO_ETF_SIGNAL` 구조와 동일하게 맞춰 프런트 렌더 함수 재사용.

**갱신 주기**: 장중 `setInterval` 120초(거래량 톱과 동일 cadence). 마감 후 1회.

## 프런트 — 시각 구분 (콘셉트 핵심)

홈에 실시간 영역과 마감 기준 영역이 공존하므로 라벨로 명확히 구분한다.

- 장중판 헤더 뱃지: 현재 `장중 2분` → **`●실시간`**(초록 pill, 대장주와 동일 스타일).
- 마감 후/주말: **`장 마감 기준`** 회색 라벨로 교체.
- 수급 신호 행은 마감판에서만 등장하므로, 장중→마감 전환 시 자연스럽게 추가됨(별도 안내 불필요).
- 색 절제 규칙([색 디자인 스펙](2026-06-27-stock-home-signals-color-design.md)) 유지 — 라벨도 무채색, 채도색은 등락 방향만.

## 범위·비범위

- **범위**: `/api/signals` 신설, 프런트 `renderSignals`/`renderSignalRank`/`renderEtfSignal`을 `PROTO_*` 하드코딩 → `/api/signals` fetch로 전환, phase별 라벨.
- **비범위**: 종목별 장중 잠정 수급 확보(소스 없음). KRX 유료/OTP 수급은 별도 검토 과제로 남김.
- **데이터 정합성**: 모든 수치 실측. 판정값 못 구한 종목·신호는 해당 행/뱃지 생략. [SERVICE_RULES 0](../../SERVICE_RULES.md) 준수.

## 검증

- 장중(평일 09:00~15:30): `/api/signals` `phase:intraday`, 수급 뱃지 없음, `●실시간` 라벨.
- 마감 후·주말: `phase:closed`, 수급 신호 포함, `장 마감 기준` 라벨.
- 거래대금 신호가 `itemSummary.amount` 실측과 일치하는지 1종목 대조.
- 신고가/투매 분모가 스냅샷 값과 일치하는지 확인.
