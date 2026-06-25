<!-- 종목 허브 재설계 — 결정 사항과 그 근거 기록 -->

# 종목 허브 재설계 — 컨텍스트 노트

## 배경

나박AI(nabakai.com) 첫 화면을 레퍼런스로, 종목 허브의 거래량/상승/하락 톱이
"와닿지 않는다"는 피드백. 사용자 제안 두 가지:
1. 실시간 상승/하락 종목을 데이터로 (나박 스타일)
2. 더블샷이 고른 모멘텀 종목을 장중 트래킹

## 핵심 결정 (2026-06-25)

### 결정 1 — 나박 스타일 수급 시그널은 포기, 정직한 실측만
**Why:** 나박의 차별점인 `외인/기관 실시간 순매수`·`매수벽`·`스마트머니`·`외국계 창구`는
한국 시장에서 종목별 장중 실시간으로는 KRX 유료 피드/증권사 제휴 없이 불가.
보유 소스(yfinance·네이버 폴링·토스 Open API)에 이 영역이 통째로 비어 있음.
→ 따라하면 LLM/추정으로 수급 숫자를 만들어야 하고, 이는 피벗 전 신뢰 붕괴 원인의 반복.
사용자 확정: "없음 — 정직한 실측만". 운영규칙 0번(실측만 표시) 준수.

### 결정 2 — ②(픽 트래킹)를 메인 축, ①(상승/하락)은 정직한 축소판
**Why:** ②는 우리만의 자산. 데이터가 정직(가격 폴링만)하고, 아침 브리핑(예측)과
종목 허브를 연결하는 스토리("우리가 찍은 종목, 지금 +3.2% 가는 중")가 가능.
①은 등락 랭킹만 남으면 차별화 약하지만, 라이브 실측이라 정직함은 유지.

### 결정 3 — 파이프라인 수정 0줄, 프론트 + vol-top 확장만
**Why:** 픽 데이터(`stock_picks`)가 이미 git 커밋된
`web/briefings/{date}/kospi/analysis_snapshot.json`에 entry/target/stop 포함 완비.
`/api/stocks-live?codes=`가 라이브 가격 제공. 메모리 "예측 신규개발 정지" 원칙과
운영규칙 0번(스냅샷=진실 소스)에 부합. update_latest 등 파이프라인 손대지 않음.

## 검토 중 발견한 문제 (긴급)

현재 허브의 **상승 톱·하락 톱·ETF 톱은 HTML 하드코딩 가짜 데이터.**
`신호 69`·`AI 78` 뱃지도 출처 없음.
- 하락 톱 1위 "삼성전자 −6.4%" ↔ 같은 화면 코스피 주도주 "삼성전자 +9.84%" 정면 모순.
- 데이터 정합성 붕괴 = 신뢰 상실. 재설계와 별개로 즉시 제거 대상.
- index.html L586~600(상승/하락), L615~628(ETF 상승/하락)이 가짜 행.

## 데이터 소스 정리

| 항목 | 소스 | 비고 |
| --- | --- | --- |
| 픽 진입/목표/손절 | `analysis_snapshot.json` `stock_picks[]` | git 커밋, 날짜 고정, 정적 |
| 픽 라이브 가격 | `/api/stocks-live?codes=` | `{code,price,changePct}` |
| 거래량 톱 | `/api/vol-top` (확장 예정: 41종목 전체) | 네이버 polling.finance |
| 급증배수 | live vol ÷ 스냅샷 `vol_avg20` | 클라이언트 계산 |
| 52주 신고가 | 스냅샷 `wk52_high` + live price | 클라이언트 계산 |

## 구현 중 발견 — stocks-live API 신뢰성 버그 (수정함)

`/api/stocks-live`가 Vercel 런타임에서 국내 종목에 `TypeError: fetch failed`(TLS 연결 실패)로
빈 배열만 반환하고 있었음. 원인은 `m.stock.naver.com/api/stock/{code}/basic` 호스트가
Vercel undici fetch에서 연결 실패. (node 단독 실행·curl에서는 정상이라 환경 특이적.)
→ vol-top이 쓰는 검증된 `polling.finance.naver.com/api/realtime/domestic/stock/{code}`로 교체.
응답 필드 `closePriceRaw`·`fluctuationsRatioRaw` 사용, 반환 형태 `{code,price,changePct}` 동일.
부수 효과: 코스피 주도주 위젯도 그동안 라이브 갱신이 죽어 있었는데 함께 복구됨.
해외(미국 벨웨더)는 `api.stock.naver.com` 유지(HDR_M).

## 미해결 / 추후

- ETF 상승/하락 톱 실측화 — ETF 코드용 라이브 등락 소스 필요 (phase 2)
- ① 통합 블록 UI 형태 — 탭 vs 컴팩트 한 줄 (구현 시 결정)
- 픽을 kospi 아침 픽만 쓸지, close/us도 포함할지 — 일단 장중 추적이므로 kospi 아침 픽
