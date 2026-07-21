# 종목·섹터 페이지 SEO 메타 주입 체크리스트 (2026-07-21)

근거: `docs/reports/2026-07-21-kospilab-competitive-review.html` 치명①

문제: 종목 상세 46개 + 미국 8개의 `<head>`에 SEO 기여 태그가 `<title>` 하나뿐.
`meta description`·`canonical`·OG·JSON-LD 전무. 섹터 8개는 sitemap 누락.
`STOCKS_SERVICE_RULES.md` §9 발행 게이트 4번("JSON-LD 유효")이 문서로만 존재해 아무도 못 잡음.

## 공통 기반

- [x] `generate_html.py`에 SEO 컨텍스트 헬퍼 추가 (`_seo_ctx`, `_jsonld`, `_html_attr`)
- [x] ⚠️ Jinja `autoescape=False`라 meta content는 Python에서 HTML 이스케이프해 넘길 것
- [x] JSON-LD는 `</` → `<\/` 치환으로 script 조기 종료 방지
- [x] 공용 partial `templates/stocks/_head_seo.html` 신설 (standalone 템플릿 2개가 공유)

## 종목 상세 46개 (`stocks/detail.html`)

- [x] description — 종목명·코드·섹터 + 실제 제공 항목만 나열
- [x] ⚠️ 목표주가는 3종목만 있으므로 `broker_targets` 있을 때만 문구에 포함 (운영 규칙 0)
- [x] canonical / og:* / twitter:* / robots
- [x] JSON-LD — `BreadcrumbList` + `Corporation`(tickerSymbol)

## 미국 상세 8개 (`stocks/us_detail.html`)

- [x] 동일 partial 적용, 브레드크럼은 홈 › 종목 › 미국 반도체 › {티커}
- [x] JSON-LD — `BreadcrumbList` + `Corporation`(ETF는 Corporation 대신 생략)

## 섹터 8개 (`pages/stock_sector.html` → `base.html`)

- [x] `base.html`에 `meta description`·robots·og:url·og:site_name·twitter·JSON-LD 블록 추가
- [x] `build_sector_pages()`가 `canonical_url`·description·JSON-LD 전달
- [x] `write_sitemap_xml()`에 섹터 8개 URL 추가

## 하지 않는 것 (의도적)

- [x] `FAQPage` JSON-LD — 페이지에 실제 FAQ가 없으면 구글 구조화 데이터 가이드라인 위반. 콘텐츠 먼저.
- [x] `SearchAction` — 검색이 URL 기반이 아니라 클라이언트 팔레트라 타깃 URL이 없음
- [x] manifest/theme-color 등 PWA 태그 — SEO 아님, 별도 작업(보고서 우선순위 5)

## 검증

- [x] 생성 결과에 5종 메타가 모두 있는지 자동 검사 스크립트
- [x] JSON-LD가 유효 JSON으로 파싱되는지
- [x] canonical URL이 실제 경로와 일치하는지
- [x] sitemap URL 수 증가 확인 (89 → 97)
- [x] ⚠️ `--stocks`는 라이브 시세를 종가로 굽는다 → **장중 실행 금지**. 템플릿 렌더만 오프라인 검증
