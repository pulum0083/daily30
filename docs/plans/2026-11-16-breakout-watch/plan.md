# 미국 브리핑 '돌파 관찰 목록' 섹션 — 계획

시안: `docs/prototypes/2026-11-16-breakout-watch-clear.html`(쉬운 화면, 사용자 결정 2026-11-16 "실제 미국 브리핑에 넣어봐").
근거·백테스트: `docs/plans/2026-11-15-turtle-review/`(hy_bt.py·hy_state.py·context-notes.md).

## 무엇을
S&P 500 종목 중 쿨라매기 조건(크게 오른 뒤 좁게 쉬는 종목)을 채운 종목이 최근 10일 최고가를 넘는지 지켜보고,
넘은 뒤 터틀 규칙(2N 손절·20일 최저가 청산)으로 어떻게 끝났는지를 그대로 보여준다. 숫자·문장은 전부 결정론(LLM 없음).
'추천'이 아니라 관찰 목록이다. 과거 성적(2025년 빼면 아무 날과 비슷)을 섹션 안에 밖으로 꺼내 둔다. 텔레그램에는 넣지 않는다.

## 구성
1. 수집 `scripts/breakout_watch.py` → `data/breakout_watch.json`(gitignore). 직전 미국 정규장(`prev_us_session`) 일봉 기준.
   S&P 500 구성 종목은 `sp500_ma200.fetch_constituents()` 재사용, 15개월 일봉 OHLC(분할·배당 반영).
   조건·돌파·추적 계산은 hy_bt.py·hy_state.py와 같은 정의를 numpy로 옮긴다. 한글 종목명은 보여줄 종목만 네이버에서.
2. 백테스트 수치 `scripts/config/breakout_watch_backtest.json`(커밋) — 화면 문장의 숫자는 여기서만 읽는다(§20). 없으면 섹션 생략.
3. 렌더 `generate_html.build_breakout_watch()` — 스냅샷 1순위, 파일은 날짜가 같을 때만(§45). 템플릿 `sections/breakout_watch.html`,
   위치는 S&P 500 200일선 체크 아래(이슈 아래 묶음). CSS는 style.css(.bw-*), ASSET_VER 올림.
4. 워크플로 us-briefing 잡: S&P 500 200일선 다음 스텝(continue-on-error · timeout 5).
5. 테스트 `scripts/test_breakout_watch.py`, 운영 규칙 §88.
