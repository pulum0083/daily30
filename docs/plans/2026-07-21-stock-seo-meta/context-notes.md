# 종목·섹터 SEO 메타 주입 — 결정과 근거 (2026-07-21)

근거 보고서: `docs/reports/2026-07-21-kospilab-competitive-review.html` 치명①

## 무엇이 문제였나

발행된 `/stocks/{code}/`의 `<head>`에 `meta`·`link` 태그가 전부 합쳐 5개뿐이었고,
SEO에 기여하는 건 `<title>` 하나였다. `description`·`canonical`·OG·JSON-LD가 전무.
성장 전략의 1번 자산(46개 영구 페이지)이 검색엔진에 사실상 빈 형태로 제출되고 있었다.

섹터 페이지 8개는 생성은 되는데 `sitemap.xml`에 없어 색인 경로 자체가 없었다.

`STOCKS_SERVICE_RULES.md` §9 발행 전 검증 기준 4번이 "JSON-LD 유효"를 명시하는데도
46개 전부가 통과 못 한 채 나갔다 — **게이트가 문서상 체크리스트로만 존재**했기 때문이다.

## 구조 선택

종목 상세(`stocks/detail.html`)와 미국 상세(`stocks/us_detail.html`)는 `base.html`을
상속하지 않는 **standalone 템플릿**이고, 섹터(`pages/stock_sector.html`)는 `base.html`을
상속한다. 그래서 두 경로로 나눴다.

- standalone 2개 → 공용 partial `stocks/_head_seo.html`을 `{% include %}`
- 섹터 → `base.html`에 직접 메타 추가

`base.html`은 브리핑 3종·브리핑 목록도 상속하므로, 여기 추가한 메타는 그 페이지들에도
같이 적용된다(개선이므로 그대로 둠). 블록 미정의 자식에서도 기본값으로 폴백하는 것을
확인했다.

## 이스케이프 — 반드시 Python에서

`make_env()`가 **`autoescape=False`**다. 템플릿에서 `{{ }}`로 meta content를 찍으면
따옴표가 섞였을 때 속성이 깨진다. 그래서 `_attr()`(= `html.escape(quote=True)`)로
**Python에서 미리 이스케이프**해 넘긴다. 템플릿은 그대로 출력만 한다.

JSON-LD는 `json.dumps` 후 `</` → `<\/` 치환한다. 종목명에 `</script>`가 들어갈 일은
없지만, 값이 외부 데이터에서 오는 이상 script 조기 종료 가능성을 코드로 막아둔다.

## description은 "실제로 있는 섹션만" 나열한다

`_stock_seo()`가 `foreign_rate`·`supply5`·`financials`·`broker_targets` 유무를 보고
description 문구를 조립한다. **목표주가는 현재 3종목(005930·000660·005380)만 수집**되므로,
전 종목에 "증권사 목표주가"를 적으면 43종목이 없는 걸 있다고 말하는 셈이다 — 운영 규칙 0 위반.

테스트 `test_description_omits_sections_the_page_does_not_have`가 이걸 고정한다.

## JSON-LD는 실제로 페이지에 있는 것만 선언한다

넣은 것:
- `BreadcrumbList` — 페이지에 실제로 보이는 브레드크럼과 1:1. 섹터 링크가 실제 생성 경로와
  같은지도 테스트로 검증(끊긴 브레드크럼 방지).
- `Corporation` (name·tickerSymbol·url) — 페이지가 실제로 그 기업을 다루므로 정확하다.

**의도적으로 넣지 않은 것:**
- `FAQPage` — 경쟁사(코스피랩)가 이걸로 리치 리절트를 먹고 있지만, **페이지에 실제 FAQ가
  없는데 선언하면 구글 구조화 데이터 가이드라인 위반**이다. FAQ 콘텐츠를 먼저 만들어야 한다
  (보고서 우선순위 6번).
- `SearchAction` — 우리 검색은 URL 기반이 아니라 클라이언트 커맨드 팔레트라 타깃 URL이 없다.
  없는 엔드포인트를 선언할 수 없다.
- 미국 **ETF**(SOXX·SMH·DRAM)에는 `Corporation`을 붙이지 않는다. ETF는 법인이 아니다.
  타입을 억지로 맞추지 않고 브레드크럼만 낸다.

## 섹터는 왜 `_seo_ctx`를 안 쓰나

`stock_sector.html`이 이미 `{% block og_desc %}`로 섹터별 설명(종목 수·평균 등락률)을
만들고 있었다. `base.html`의 `meta description`이 `{{ self.og_desc() }}`로 **그 블록을
그대로 재사용**하므로 정본이 한 곳이다. Python에서 description을 또 넘기면 두 값이
어긋날 수 있어, 섹터는 `canonical_url`과 JSON-LD만 넘긴다.

## 반영 시점

지금(15:12 KST)은 장중이라 `generate_html.py --stocks`를 **수동 실행하지 않았다** —
`--stocks`는 라이브 시세를 종가로 구워버린다. 오늘 16:25 `kospi-close-briefing` 잡이
`--sectors` → `--stocks` → `--us-stocks`를 순서대로 돌리므로 62개 페이지가 자동 반영된다.
`sitemap.xml`만 오프라인 생성이 안전해서 지금 갱신했다(89 → 97 URL).

## 남은 것

- `test_validate_analysis.py::test_block_close_scalar_prose`가 **이 작업 전부터 실패** 중이다.
  stash 후 재현으로 확인했다. 이번 변경과 무관하므로 건드리지 않았다.
- 보고서 우선순위 2번(발행 게이트 자동화)은 `scripts/test_stock_seo_meta.py`로 **부분 달성**.
  다만 이건 템플릿 렌더 검사이고, 실제 발행된 HTML을 CI에서 검사하는 게이트는 아직 없다.
