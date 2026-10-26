# 종목 상세 페이지 제거 — 수집·페이지·링크

사용자 결정(2026-10-26): 종목 상세 페이지(국내 `/stocks/{code}/` 3종목 · 미국 `/stocks/us/{ticker}/` 10종목)를 없앤다.
수집도 멈추고, 상세 페이지로 가는 링크도 없앤다. "괜한 리소스 낭비".

## 남기는 것 (다른 화면이 쓰는 데이터 — §36 소비자 전수 확인)
- `fetch_stock_targets.py` → `web/data/stock-targets.json` — 종목 홈 '코스피 주도주' 위젯의 증권사 목표주가가 쓴다.
- `build_stocks_snapshot.py` → `web/data/stocks-snapshot.json` — 종목 홈·섹터 페이지가 쓴다.
- 섹터 페이지 `/stocks/sector/{key}/` 8종 — 종목 상세가 아니다.
- `scripts/config/stocks.json` — `fetch_movers_why.py`의 종목 유니버스다(§36). `detail_page` 플래그만 의미가 없어진다.

## 멈추는 것
- 마감 잡 `generate_html.py --stocks`(국내 상세), `--us-stocks`(미국 상세), `fetch_valuation.py`(상세 페이지만 쓰던 밸류에이션).

## 지우는 것
- 발행된 상세 페이지 13개(`web/stocks/{3 codes}/`, `web/stocks/us/`), 템플릿 `stocks/detail.html`·`us_detail.html`, 상세 전용 코드·테스트.
- 링크: 종목 홈(주도주 타일·특이신호·섹터 박스·검색·밤사이 미국 행), 섹터 페이지 카드·선행 지표 링크, 브리핑 사이드바 특이신호,
  브리핑 종목 픽·월봉 5개월선 종목명 링크, sitemap.

## 옛 주소
- 발행된 브리핑(§33, 고치지 않는다)과 검색엔진에 옛 주소가 남는다 → `vercel.json`에서 `/stocks/{6자리}/`·`/stocks/us/{티커}/`를
  `/stocks/`로 301 리다이렉트해 404를 만들지 않는다(§33 "삭제 로직과 사이트맵은 같은 수명").

## 내 판단(사용자 확인 전 기본값)
- 검색(⌘K)은 남기고, 결과를 누르면 그 종목의 섹터 페이지로 보낸다(상세 페이지가 없으니 토스트만 뜨는 검색은 의미가 없다).
- 특이신호·섹터 카드도 같은 규칙 — 섹터 페이지로.
