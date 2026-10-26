# 미국 브리핑 '나스닥 체크' 섹션 + 텔레그램 나스닥 경고 블록 — 계획

프로토타입: `docs/prototypes/2026-10-25-us-briefing-nasdaq-overheat.html`, 빌더(참고용): `build_proto.py`. 선례: §61(월봉 5개월선 코너)·§62(텔레그램 새 형식).

## 지표
나스닥 종합지수(^IXIC) 이번 달 월봉 고점 ÷ 월말 종가 60개월 평균(진행 중인 이번 달 종가 포함) − 1.
2026-10-23 기준 +59.8%(고점 27,722.8 · 60개월선 17,349.5). 60% 미만 ✓ 정상 · 60% 이상 ⚠️ 주의 · 70% 이상 🚨 경고.

## 구성
1. 수집 `scripts/nasdaq_overheat.py` — 야후 일봉(1971~)을 받아 월별로 묶는다(고가=일봉 고가 최대, 종가=마지막 종가).
   야후 월봉 API는 진행 중인 달의 고가를 틀리게 준다(10월 26,111.6 vs 일봉 최대 27,722.8). 출력 `data/nasdaq_overheat.json`(date = 브리핑 날짜 KST).
   us-briefing 잡에서 fetch_data 다음, continue-on-error + timeout-minutes 5.
2. 백테스트 `scripts/backtest_nasdaq_overheat.py` → `scripts/config/nasdaq_overheat_backtest.json`(커밋). 하단 설명 숫자는 이 파일에서만 읽는다(§20). 파일이 없으면 섹션째 생략.
3. 렌더 `generate_html.build_nasdaq_check()` — 스냅샷 1순위, 데이터 파일은 날짜가 같을 때만(§45). 결과는 analysis에 넣어 스냅샷에 남긴다.
   템플릿 `sections/nasdaq_check.html` — 위치는 '오늘 점검할 이슈' 아래(사용자 결정 2026-10-26, 프로토타입은 관점 바로 아래였다). 그래프 글자·점은 HTML로 겹친다.
   하단 설명·면책은 `<details>` "근거와 면책 고지"로 접는다(사용자 결정 2026-10-26).
4. 텔레그램 `call_claude._nasdaq_telegram_lines()` — 같은 `build_nasdaq_check()`로 읽고 70% 이상일 때만 '👀 오늘 밤 볼 것' 아래에 붙인다.
5. 테스트·운영 규칙 §65·커밋. 푸시는 사용자 지시 시.
