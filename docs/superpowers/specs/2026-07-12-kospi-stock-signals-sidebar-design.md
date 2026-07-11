# 종목 신호 사이드바 위젯 — 설계 (Stage B 슬라이스8)

작성: 2026-07-12
프로토타입: `docs/prototypes/2026-07-11-kospi-briefing-redesign.html` (사이드바 종목 신호 위젯, line 771~792)

## 목적

코스피 오전 브리핑 사이드바에, 이미 종목 대시보드(`/stocks/`)가 소비 중인 `/api/signals`를
재사용해 "지금 포착된 종목 신호" 상위 3개를 라이브로 노출한다. 성적표 카드 아래에 위치해
독자를 종목 상세 페이지·신호 전체 화면으로 유도하는 동선을 만든다.

## 데이터 소스

- 클라이언트에서 `/api/signals` fetch. **60초 폴링**(사이드바 market_data 패널과 동일 주기).
- 응답 필드 사용:
  - `phase` — `'intraday'`(장중) / `'closed'`(장 마감). 상태 판정에 그대로 사용(별도 KST 시계 불필요).
  - `signals` — 이미 서버에서 점수순 정렬된 배열. 각 항목:
    `{ code, name, sector, pct, dir, cats, badges, why }`. **상위 3개만** 표시.
- Python(서버 렌더) 변경 없음 — 순수 클라이언트 소비.

## 표시 규칙

### 상태별 헤더/힌트
- `phase === 'intraday'`: 헤더 "📡 오늘의 종목 신호"
- `phase === 'closed'`: 헤더 "📡 지난 장 포착 신호" + 서브노트 "지난 마감 기준" +
  하단 힌트 "실시간 신호는 09:00 장 시작부터 갱신돼요."

### 행 구성 (상위 3개)
- 종목명 → 링크 `/stocks/{code}/`
- 배지: `badges[0]` 텍스트, 색은 `cats[0]` 기준 매핑
  - gold: `vol_surge`, `turnover`
  - blue: `inst_buy`, `foreign_buy`, `foreign_sell`
  - green: `near_high`, `counter_up`
- 등락률: `pct` (up/dn 색), `dir` 필드 사용

### CTA
- "종목 신호 전체 보기 →" → `/stocks/#signals-all`
  (프로토타입의 `/stocks/#signals`는 실제 화면 id가 아님 — `web/stocks/index.html`의
  `<div class="screen" id="signals-all">`에 맞춰 정정)

## 적용 범위 / 숨김 규칙

- **코스피 오전 브리핑에만** 노출. 마감·미국 브리핑엔 미적용
  (`/api/signals`는 한국 종목 대상 + intraday 신호라 마감·미국 맥락엔 부적합).
- **과거 날짜 브리핑(URL 날짜 < 오늘)에서는 위젯 전체를 숨긴다.**
  신호는 '오늘' 값만 의미가 있으므로, 과거 페이지에 오늘 신호를 보여주면 오해 소지.
  코스피 밴드의 과거 브리핑 처리와 동일한 `isPast` 패턴 재사용.
- fetch 실패 / `signals` 빈 배열이면 위젯 숨김 — 이전 세션·하드코딩 값 금지(데이터 정합성 철칙).

## 위치

`kospi.html` 사이드바(`layout-grid__right`) 순서:

```
market_data (나스닥·SOX·VIX)
scorecard (우리 성적표)
[신규] 종목 신호 위젯      ← 여기
_sidebar_kospi (텔레그램 · 월배당 계산기 · footer)
```

## 구현 구성

- **템플릿**: `scripts/templates/sections/_stock_signals.html` (신규)
  - 껍데기 마크업만. 행 내용은 JS가 채움. 초기 `hidden`(JS가 데이터 확인 후 노출).
  - `data-is-past` 속성으로 과거 브리핑 여부 전달(밴드와 동일 패턴).
- **CSS**: 프로토타입의 `.sw-list/.sw-row/.sw-name/.sw-badge/.sw-chg/.sw-hint/.side-note`를
  `style.css`에 이식. CSS 변수는 슬라이스1~6과 동일 규칙으로 매핑(`--dim`→`--muted` 등).
- **JS**: `web/assets/main.js`에 `initStockSignals()` 추가.
  - 기존 `initNowBand`/`initLiveMarketPanel`의 fetch·60초 폴링·`isPast` 판정 패턴 재사용.
  - `phase`로 헤더/힌트 토글, `signals.slice(0,3)`로 행 렌더.
  - `main.js` IIFE 내부 load 핸들러에 `initStockSignals()` 호출 등록(base.html 아님 — 밴드와 동일).
- **kospi.html**: scorecard include 다음 줄에 `{% include "sections/_stock_signals.html" %}` 추가.
- **Python**: 변경 없음.

## 검증

- mock 하니스로 `/api/signals` 샘플 JSON(intraday/closed 2종) 주입해 렌더 확인.
- 상태별: intraday 헤더 + 3행, closed 헤더+힌트, past(숨김), 빈 signals(숨김), fetch 실패(숨김).
- 다크 모드 렌더.
- 라이브 폴링은 실제 Vercel serverless 필요 → 배포 후 라이브 API로 최종 확인(로컬 검증 한계).

## YAGNI / 범위 밖

- 마감·미국 브리핑 확장 안 함.
- 신호 카테고리별 필터·정렬 UI 없음(상위 3개 고정, 전체는 `/stocks/#signals-all`로 위임).
- 서버 사이드 렌더 폴백 없음(JS 없으면 위젯 미노출 — 라이브 컴포넌트 성격상 허용).
