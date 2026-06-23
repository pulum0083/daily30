# 종목 대시보드 3종 실측화 — 설계

작성일: 2026-06-24
대상: `web/stocks/index.html` (종목 대시보드) + 신규 섹터 페이지
상태: 설계 확정 → 스펙 리뷰 → 구현 계획(writing-plans)

## 1. 배경 · 범위

현재 `/stocks/index.html` 대시보드는 상단 "미국 연동 대표주" 3종목만 종가 기반 실측이고, 나머지(거래량 톱·ETF·섹터 등)는 일러스트레이션이다. 점검 결과 6개 일러스트 항목 중 **3개를 실측화**한다. 나머지 3개(종목별 담은 ETF·수급·목표가 등 별도 소스 필요)는 이번 범위 밖.

| 항목 | 현재 | 목표 |
| --- | --- | --- |
| ① 시세·차트·52주 | 3종목 종가만 | ~50종목, 매일 1회 실측 스냅샷 |
| ② 실시간 가격 | 3종목도 종가 | 한국 50종목 장중 라이브 + 미국 벨웨더 마감 후 라이브 |
| ③ 섹터 리스트 | 페이지 없음 (칩 클릭 시 갈 곳 없음) | 섹터별 전용 페이지 8개 |

**원칙**: SERVICE_RULES 0번 준수 — 화면에 찍히는 모든 수치는 실측. 라이브 데이터는 git 커밋하지 않는다.

## 2. 데이터 토대 — 종목 유니버스 (세 항목 공통)

기존 `fetch_data.py`의 `SECTOR_FOCUS_STOCKS`(8섹터·24종목)를 **별도 config 파일로 분리·확장**한다.

- 신규 파일: `scripts/config/stock_universe.json`
- 8섹터(semicon·battery·auto·defense·ship·bio·finance·power) × 섹터당 5~7종목 = **~50종목**
- 종목 추가 = JSON만 수정 (코드 변경 불필요)
- 이 한 파일이 **유니버스 + 섹터 그룹핑 + 섹터 페이지 목록**의 단일 출처

```json
{
  "sectors": {
    "semicon": {
      "label": "반도체",
      "stocks": [
        { "code": "005930", "name": "삼성전자" },
        { "code": "000660", "name": "SK하이닉스" }
      ]
    }
  },
  "bellwethers": {
    "semicon": [ { "t": "NVDA", "name": "엔비디아", "kind": "US" } ]
  }
}
```

- 한국 종목: 6자리 코드만 (`.KS`/`.KQ` 접미사 금지 — SERVICE_RULES 0번).
- `fetch_data.py`의 기존 `SECTOR_FOCUS_STOCKS`는 이 JSON을 읽도록 전환(또는 병행). 브리핑 파이프라인 회귀 주의.

## 3. ① 시세·차트·52주 — 매일 1회 스냅샷 빌드

신규 스크립트 `scripts/build_stocks_snapshot.py`:

- `stock_universe.json`의 ~50 한국 종목 + 미국 벨웨더를 순회
- 종목당 토스 `get_candles(code, "1d", 300)` 1회 호출 → 다음 계산:
  - 종가 (`closes[-1]`), 전일대비 등락률 (`closes[-1]` vs `closes[-2]`)
  - 52주 고저 (최근 252거래일 max/min)
  - 5일 / 20일 스파크라인 배열
  - MA200 (300일 받아 최근 200개 평균)
- 토스 실패 시 폴백: 한국 → 네이버 일봉, 미국 → yfinance (SERVICE_RULES 실측 우선순위 표 준수)
- 출력: `web/data/stocks-snapshot.json` (git 커밋됨, 날짜·`generated_at` 포함)
- 실행: GitHub Actions **하루 1회** — 기존 `kospi-close-briefing` 잡에 스텝 추가 (마감 후 종가 확정 시점)
- 화면의 시세·차트·52주는 전부 이 스냅샷에서 읽는다.

스냅샷 스키마(요약):
```json
{
  "generated_at": "2026-06-24T16:40:00+09:00",
  "stocks": {
    "005930": {
      "name": "삼성전자", "sector": "semicon",
      "close": 354000, "change_pct": -2.34,
      "wk52_high": 388000, "wk52_low": 301000,
      "spark5": [...], "spark20": [...], "ma200": 342100
    }
  },
  "bellwethers": { "NVDA": { "close": 178.2, "change_pct": 1.9 } }
}
```

## 4. ② 실시간 가격 — 서버리스 + 폴링 (B안)

신규 서버리스 엔드포인트 `api/stocks-live.mjs`:

- 요청 시 KST 현재 시각으로 시간대 분기:
  - **09:00–15:30 (한국 장중)**: 토스 `get_prices(한국 50종목)` 1회 호출 → 현재가·등락 반환
  - **한국 마감 후 ~ 미 장 마감**: 토스 `get_prices(미국 벨웨더)` 반환
  - 그 외 시간대: 라이브 데이터 없음 (프론트는 스냅샷 종가 표시)
- 라이브 데이터는 **git 커밋하지 않는다** (라이브 내보내기 금지). 기존 `kospi-live.mjs`·`market.mjs` 서버리스 패턴 재사용.
- 프론트(`web/stocks/index.html` 인라인 또는 분리 JS):
  - 스냅샷을 baseline으로 렌더 → `/api/stocks-live` 폴링으로 가격만 패치
  - 한국 10초 / 미국 30~60초 폴링
  - sessionStorage로 새로고침 복원(기존 라이브 패널 패턴 재사용)
- 50종목이 토스 1회 호출에 들어오므로(`get_prices` 최대 200) 호출 비용 문제 없음.

## 5. ③ 섹터 리스트 — 전용 페이지 (A안)

- 경로: `/stocks/sector/{key}/index.html` × 8 (semicon·battery·auto·defense·ship·bio·finance·power)
- 각 페이지 내용: 해당 섹터 종목들의 종가·등락·52주·스파크라인(스냅샷 기반), 장중에는 `/api/stocks-live` 필터링으로 라이브
- 홈 "섹터별 보기" 칩 → 해당 섹터 페이지로 링크
- `generate_html.py`(또는 빌드 스크립트)가 8페이지를 **정적 생성·커밋** → SEO 영구 자산 (ETFNow 트래픽 전략과 정합)
- 템플릿: `scripts/templates/pages/` 아래 섹터 페이지 템플릿 1개 + config 순회

## 6. 빌드 / 배포 흐름

```
매일 1회 (kospi-close 잡에 스텝 추가):
  build_stocks_snapshot.py  → web/data/stocks-snapshot.json (커밋)
  generate_html.py          → 홈 대시보드 데이터 주입 + 섹터 8페이지 재생성 (커밋)
  → main 커밋 → gh-pages 배포

상시:
  /api/stocks-live (서버리스, 커밋 안 함) ← 프론트 폴링 (KR 10s / US 30~60s)
```

## 7. 제외 (YAGNI / 이번 범위 밖)

- 종목별 "담은 ETF" 리스트 — 새 데이터 소스 필요, 후속
- 수급(외국인·기관)·목표가·분기 실적 — 각각 소스 확보 필요, 후속
- 거래량 톱 / ETF 거래량 톱 일러스트 실측화 — 이번 3개 항목에 미포함
- **장 종료 후 24시간 참고 시세 (후속, 이번 범위 밖)** — 상단 하이라이트 3종목(삼성전자·SK하이닉스·현대차)만 대상. 국내 증시 장 종료 후, Hyperliquid·Binance에 상장된 한국 주식 무기한 선물(퍼프) 가격을 기준 원/달러 환율로 환산한 24시간 참고 시세를 표시한다. 별도 데이터 소스(Hyperliquid·Binance API) 배선 필요 → 본 3종 실측화 완료 후 별도 사이클로 구현.

## 8. 성공 기준

- `stock_universe.json` 한 파일로 ~50종목 8섹터가 정의되고, 종목 추가가 JSON 수정만으로 된다.
- `build_stocks_snapshot.py`가 50종목 종가·52주·스파크라인·MA200을 실측으로 `stocks-snapshot.json`에 쓴다.
- 대시보드 상단·거래량 영역 시세가 스냅샷 실측값으로 표시된다(일러스트 제거).
- 한국 장중 `/api/stocks-live` 폴링으로 50종목 가격이 실시간 갱신되고, 한국 마감 후엔 미국 벨웨더가 라이브로 움직인다.
- `/stocks/sector/{8개}/` 페이지가 정적 생성되어 칩 클릭으로 진입되고, 검색엔진에 노출되는 영구 URL이다.
- 라이브 데이터는 git 커밋되지 않는다.

## 9. 리스크 / 확인 필요

- **브리핑 파이프라인 회귀**: `SECTOR_FOCUS_STOCKS`를 JSON으로 전환 시 `fetch_sector_stocks()` 등 기존 소비처가 깨지지 않게 한다. 병행(JSON 로드 후 기존 형태로 변환) 권장.
- **SOX 등 지수 벨웨더**: 토스 미제공 시 ETF(SOXX) 대체 또는 생략 (기존 스펙 §5 동일 이슈).
- **미국 장중 시간대 분기**: 서머타임(DST) 경계로 미 장 마감 시각이 바뀜 — KST 기준 분기 시 DST 처리.
- **50종목 토스 캔들 빌드 시간**: 종목당 1회 × 50 = 직렬 시 수십 초. Actions 타임아웃 내 처리되는지 확인(필요 시 병렬/배치).
