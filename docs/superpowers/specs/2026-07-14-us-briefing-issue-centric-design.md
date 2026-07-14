# 미국 브리핑 이슈 중심 전환 — 설계 스펙

> 이 스펙은 기존 계획 `docs/superpowers/plans/2026-07-14-us-briefing-kospi-parity.md`(미국 브리핑을 코스피와 동일한 예측 구조로 정렬)을 **폐기**하고 대체한다. 방향은 정반대다 — 코스피와의 예측 정렬이 아니라, 미국 브리핑을 예측에서 이슈 점검으로 전환한다.

## 배경 / 문제

미국장은 한국 시각으로 새벽에 열린다. 구독자에게 "S&P500이 오를까 내릴까"의 방향 예측보다, **오늘 시장을 움직이는 촉매가 무엇이고 그게 어느 섹터·종목에 어느 방향으로 작용하는가**가 훨씬 쓸모 있다.

예: IBM CEO가 실적 콜에서 "고객사들이 AI 인프라 투자하느라 소프트웨어 지출을 줄이고 있다"고 발언 → SaaS 전반 약세, AI 인프라(NVDA)로 자금 이동. 이런 양면 서사가 좋은 리포트다.

## 목표

미국 시장 브리핑을 **지수 방향 예측 → 이슈 중심 점검**으로 전환한다.

- 지수 방향 예측(direction/up_pct/confidence)과 정확도 채점을 미국 브리핑에서 제거한다.
- 오늘의 촉매 3~5개를 이슈 카드로 제시한다. 각 이슈는 "무슨 일 → 어느 섹터·종목에 어느 방향".
- 이슈가 양면(자금 이동)이면 눌리는 쪽/수혜 쪽을 모두, 단면이면 한쪽만 표시한다.

## 비목표 (YAGNI)

- 이슈 카드 종목에 실측 등락률 주입 — 하지 않는다. 티커·이름만.
- 코스피 예측 브리핑 구조 변경 — 이번 범위 밖. 코스피는 그대로 예측 중심.
- 이슈 자체의 사후 정확도 채점 — 하지 않는다.

## 페이지 구조

```
본문:  오늘의 관점 → 오늘의 이슈(3~5) → 월가 코멘트 → 프리장 신고가 → 종목 픽
사이드바:  시장 지표(market_data) → 텔레그램/월배당 CTA
```

**제거:** 방향 예측(prediction) · 이렇게 보는 이유(reasons 산문) · 성적표(사이드바 accuracy).
**유지:** 월가 코멘트(analyst_quotes) · 프리장 신고가(nh_stock) · 종목 픽(stock_picks) · 시장 지표.

## 데이터 계약 — `analysis_us.json`

`call_claude.py`의 US 프롬프트가 아래 JSON을 생성한다. `prediction` 필드는 제거하고 `todays_view`·`issues`를 추가한다.

```jsonc
{
  "todays_view": "오늘 미국장은 CPI 소화하며 SW 약세 vs AI 인프라 강세로 갈렸어요.",
  "issues": [
    {
      "title": "IBM CEO \"고객사, AI 인프라 투자하느라 SW 지출 줄인다\"",
      "body": "실적 콜 발언에 SaaS 전반이 흔들림. 클라우드 인프라로 자금이 쏠리는 반작용.",
      "down": { "label": "소프트웨어", "tickers": ["CRM", "NOW", "ADBE"] },
      "up":   { "label": "AI 인프라", "tickers": ["NVDA"] }
    },
    {
      "title": "6월 CPI 예상 상회, 금리 인하 기대 후퇴",
      "body": "헤드라인 물가가 컨센서스를 웃돌며 위험자산 전반에 부담.",
      "down": { "label": "지수 전반", "tickers": [] }
    }
  ],
  "analyst_quotes": [ ... ],   // 기존 구조 유지
  "nh_stocks": [ ... ],        // 기존 구조 유지
  "stock_picks": [ ... ]       // 기존 구조 유지
}
```

### 이슈 카드 필드 규칙

| 필드 | 규칙 |
| --- | --- |
| `title` | 이슈 헤드라인. 가격·등락률 숫자 금지. |
| `body` | 1~2문장. 무슨 일이 일어났고 왜 중요한지. 숫자 금지. 해요체. |
| `down` | 눌리는 쪽. `{label, tickers[]}`. 없으면 필드 자체 생략. |
| `up` | 수혜 쪽. `{label, tickers[]}`. 없으면 필드 자체 생략. |

- **양면 이슈**: `down`+`up` 둘 다 존재.
- **단면 이슈**: 한쪽만 존재(예: CPI 서프라이즈 → `down`만).
- `tickers`는 빈 배열 허용(섹터 전반 영향 등 특정 종목 지목이 어려운 경우).
- 감성 색은 `down`(약세=파랑 계열)·`up`(강세=빨강 계열)의 존재로 템플릿이 자동 결정. 별도 sentiment 필드 없음.

## 데이터 정합성 (운영 규칙 0 준수)

- 이슈 카드에는 **실측이 없으므로 어떤 수치도 넣지 않는다.** 티커·이름만.
- `title`·`body`에 가격·등락률·지수 레벨 숫자가 새어들면 정규식으로 검출해 해당 숫자를 제거하거나 이슈를 폐기한다(`fetch_research_reports.py`의 숫자 가드 방식 차용).
- 이슈 서술은 `fetch_news.py`가 수집한 뉴스에 근거해야 하며, LLM이 없는 사건을 지어내지 않는다.

## 발행 보호

- `issues`가 0~1개로 빈약해도 **브리핑은 발행한다.** 오늘의 관점 + 월가 코멘트 + 프리장 신고가 + 종목 픽이 본문을 지탱한다.
- `issues`가 0개면 이슈 섹션만 생략한다(섹션 자체 미표시).

## 정확도 채점 탈퇴 (이번 범위 포함)

미국 브리핑은 현재 `check_accuracy.py` 채점 대상이며 텔레그램에 "지난 예측" 배지가 붙는다. 예측을 제거하므로 아래를 정리한다.

- 미국 예측을 `data/briefings.json` 채점 큐에 더 이상 등록하지 않는다(등록 지점 확인 후 US 제외).
- `check_accuracy.py`가 US 항목을 채점하려다 실패하지 않도록 US를 건너뛴다.
- 텔레그램 US 메시지에서 "지난 예측" 배지 로직을 제거한다.
- 사이드바 `accuracy` 섹션을 US에서 제거한다.

## 뉴스 소싱 (튜닝은 구현 후)

이슈 품질은 `fetch_news.py`의 US 검색이 프리장 급등락 촉매·실적 콜·CPI 등 매크로 이벤트를 실제로 물어오느냐에 달려 있다. US 검색 프롬프트에 "프리장 급등락 촉매"·"오늘 예정된 매크로 지표" 지시를 보강할 필요가 있어 보이나, **실제 출력을 보고 튜닝**한다(구현 후 반복).

## 변경 파일

| 파일 | 변경 |
| --- | --- |
| `scripts/call_claude.py` | `US_SYSTEM_PROMPT` 교체 — `prediction` 제거, `todays_view`·`issues` 계약 추가. |
| `scripts/config/us.json` | `sections_main` 재정의, `pred_title`·prediction 관련 필드 제거. |
| `scripts/templates/sections/_issues.html` | **신규** — 이슈 카드 렌더(양면/단면 분기, 감성 색). |
| `scripts/templates/briefings/us.html` | prediction·reasons 블록 제거, todays_view·issues 삽입, 사이드바 accuracy 제거. |
| `scripts/generate_html.py` | US에 `issues`·`todays_view` 컨텍스트 주입, accuracy 게이트에서 US 제외, 이슈 숫자 가드. |
| `scripts/check_accuracy.py` | US 채점 제외. |
| `scripts/send_telegram.py` | US "지난 예측" 배지 제거. |

## 검증 원칙 (모든 태스크 공통)

- 라이브 산출물(`web/briefings/{실제날짜}/…`, `gh-pages`)은 절대 건드리지 않는다.
- 렌더 검증은 **가짜 날짜 `2099-01-01`** 로만 생성하고, 검증 후 `web/briefings/2099-01-01/` 디렉터리를 삭제한다.
- gitignored 입력(`data/analysis_us.json` 등)을 임시 수정했다면 원복한다.
- 텔레그램 발송·`git push`는 범위 밖(사용자 지시 시에만).
