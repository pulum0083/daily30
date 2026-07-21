# 발행 게이트 자동화 · 야간 추정가 전면 배치 — 체크리스트

출처: `docs/reports/2026-07-21-kospilab-competitive-review.html` §4 우선순위 2번·5번

> 5번의 "앱 설치 유도"는 이미 완료 상태(`d5bbb3c2`). 종목 상세 46개·미국 상세 8개 발행본에서
> `pwa-install.js`·manifest 확인함. 5번에서 남은 것은 야간 가격 배치뿐이다.

## A. 발행 게이트 자동화 (우선순위 2번)

- [x] `scripts/verify_publish_gate.py` 신설 — 메타 5종·JSON-LD 파싱·canonical 일치·`/v2/` 부재 검사
      → verify: 현재 발행본(종목 46 + 미국 8 + 섹터 8) 전수 감사 통과
- [x] `generate_html.py` 쓰기 경로에 게이트 삽입 — 위반 페이지는 **쓰지 않음**(직전 정상본 유지)
      → verify: 메타를 일부러 뺀 렌더가 스킵되고 기존 파일이 그대로 남는지
- [x] 실행 종료 시 위반 1건 이상이면 `exit 1`
      → verify: 스텝이 실패로 표시되되 `continue-on-error`로 마감 브리핑 발행은 계속되는지 확인
- [x] sitemap 포함 검사 — 생성된 페이지가 `sitemap.xml`에 전부 들어갔는지
      → verify: 섹터 8개 포함 확인 (7/21 이전엔 누락됐던 항목)
- [x] `scripts/test_publish_gate.py` — 정상 통과 / 항목별 누락 검출 회귀 테스트
      → verify: `pytest scripts/test_publish_gate.py` 통과
- [x] `.github/workflows/ci.yml` 신설 — push·PR에서 pytest + 발행본 전수 감사
      → verify: 워크플로우가 실행하는 명령을 로컬에서 동일하게 돌려 통과

## B. 야간 추정가 — 종목 상세 히어로 (우선순위 5번)

- [x] `generate_html.py` — HL 커버 3종목(005930·000660·005380)에 `hl_night` 플래그 전달
- [x] `detail.html` — 히어로 `.top` 아래 야간 스트립 (기본 숨김, `data-close`에 종가 실측 주입)
- [x] `web/assets/stocks.js` — 장 마감 시에만 `/api/hl-night` 폴링, 종가 대비 % 계산
- [x] `adjusted:true`(실제 종가로 대체된 값)면 표시하지 않음 — 운영 규칙 0
- [x] `scripts/test_night_hero.py` — 3종목만 스트립 존재 / 나머지 43종목 부재
- [x] 브라우저 실측 검증 — 값·문구·갱신 주기 표기가 실제와 1:1인지

## 커밋 단위

1. `feat(seo): 발행 게이트 자동화` — A 전체
2. `feat(stocks): 종목 상세 히어로에 야간 추정가 배치` — B 전체
