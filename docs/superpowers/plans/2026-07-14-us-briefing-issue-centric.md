# 미국 브리핑 이슈 중심 전환 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 미국 시장 브리핑을 S&P500 방향 예측에서, 오늘의 촉매 이슈 3~5개를 "무슨 일 → 어느 섹터·종목에 어느 방향"으로 짚는 이슈 리포트로 전환한다.

**Architecture:** Jinja 템플릿(`scripts/templates/`) + config-driven `generate_html.py` 조립기 + `call_claude.py`(Claude Sonnet 5) AI 프롬프트로 구성된 정적 브리핑 파이프라인. 이번 변경은 (1) US AI 프롬프트를 `todays_view`·`issues` 계약으로 교체, (2) `call_claude.py`에서 US의 예측 채점·형식 로테이션 배선 제거 + 텔레그램 메시지 재구성, (3) `generate_html.py`에 `build_issues` 추가 + US 렌더 분기, (4) 신규 `_issues.html` + `us.html` 재구성 + 이슈 카드 CSS로 이뤄진다.

**Tech Stack:** Python 3, Jinja2, Anthropic SDK(claude-sonnet-5), pytest. HTML 템플릿 변경은 단위 테스트가 아니라 `generate_html.py`로 임시 날짜(`2099-01-01`) 렌더 후 grep·브라우저 프리뷰로 검증한다(프로젝트 관례).

**참조 스펙:** `docs/superpowers/specs/2026-07-14-us-briefing-issue-centric-design.md`
**참조 프로토타입:** `docs/prototypes/2026-07-14-us-issue-centric-briefing.html`

**검증 원칙 (모든 태스크 공통):**
- 라이브 산출물(`web/briefings/{실제날짜}/…`, `gh-pages`)은 절대 건드리지 않는다.
- 렌더 검증은 **가짜 날짜 `2099-01-01`** 로만 생성하고, 검증 후 `web/briefings/2099-01-01/` 디렉터리를 삭제한다.
- gitignored 입력(`data/analysis_us.json` 등)을 임시 수정했다면 원복한다.
- 텔레그램 발송·`git push`는 범위 밖(사용자 지시 시에만).

---

## File Structure

- `scripts/call_claude.py` — US_SYSTEM_PROMPT 교체(Task 1), US 파이프라인 배선 제거(Task 2), 텔레그램 메시지 US 분기(Task 3).
- `scripts/generate_html.py` — `build_issues`+숫자 가드 헬퍼(Task 4), render_briefing US 분기(Task 5).
- `scripts/templates/sections/_issues.html` — 신규 이슈 카드 섹션(Task 6).
- `scripts/templates/briefings/us.html` — 본문·사이드바 재구성(Task 7).
- `web/assets/style.css` — 이슈 카드 CSS 추가(Task 8, 순수 additive).
- `scripts/config/us.json` — sections_main 재정의(Task 9).
- `scripts/check_accuracy.py` + `.github/workflows/daily_report.yml` — US 채점 탈퇴(Task 10).

각 파일은 단일 책임을 유지한다. 템플릿은 표현, `generate_html.py`는 컨텍스트 조립, `call_claude.py`는 AI 출력 계약과 텔레그램 메시지를 담당한다.

---

## Task 1: call_claude.py — US_SYSTEM_PROMPT를 이슈 중심 계약으로 교체

**Files:**
- Modify: `scripts/call_claude.py:526-861` (US_SYSTEM_PROMPT 문자열 전체)

- [ ] **Step 1: 현재 US_SYSTEM_PROMPT 범위 확인**

Run: `grep -n 'US_SYSTEM_PROMPT = """\\\\' scripts/call_claude.py`
Expected: `526:US_SYSTEM_PROMPT = """\`

Run: `awk 'NR>=527 && /^"""/{print NR; exit}' scripts/call_claude.py`
Expected: `861` (닫는 `"""` 라인 — 이 라인 앞까지가 프롬프트 본문)

- [ ] **Step 2: US_SYSTEM_PROMPT 본문을 아래 전체로 교체**

`scripts/call_claude.py`의 526번 라인 `US_SYSTEM_PROMPT = """\` 부터 861번 라인 닫는 `"""` 까지를 아래로 통째로 바꾼다. (형식 로테이션 섹션 B~G, prediction/reasons/watch_items/telegram_signals 규칙은 모두 제거된다.)

```python
US_SYSTEM_PROMPT = """\
너는 20년 경력의 미국 주식시장 애널리스트다.
제공된 시장 데이터와 뉴스 요약을 분석하여, 오늘(한국 새벽) 미국 증시를 움직일 **핵심 촉매(이슈)** 3~5개를 골라 점검하는 리포트를 쓴다.
**지수 방향(오를까 내릴까)을 맞히는 게 아니다.** 오늘 어떤 이슈가 어느 섹터·종목에 어느 방향으로 작용하는지를 짚어준다.

## 글쓰기 기본 규칙 (모든 텍스트에 적용)

**[규칙 A] 의견·주장 먼저** — 무슨 일이 왜 중요한지(어느 섹터·종목에 영향)를 먼저 쓴다.
**[규칙 B] 모든 문장은 해요체로 끝낸다** — '~해요', '~예요', '~있어요', '~같아요', '~거든요' 중 하나.
❌ 금지: "~약세.", "~부담.", "~예상됨." 같은 명사·한자어 종결.
**[규칙 C] 주식 입문자도 이해하게 쉽게 쓴다** — 전문 용어는 괄호로 풀어준다.

## [핵심] 데이터 정합성 — 수치를 지어내지 않는다

- **이슈 카드(title·body)에는 어떤 가격·등락률·지수 레벨 숫자도 넣지 않는다.** 종목은 티커/이름으로만 지목한다. (예: "CRM이 눌려요" O, "CRM -4%" X)
- `todays_view`도 특정 숫자를 넣지 않고 정성적으로 쓴다. 단어 강조(`<b>단어</b>`)는 되지만 숫자 강조는 금지.
- 이슈는 반드시 제공된 뉴스 요약(`catalysts`·`headlines`·`key_indicators`)에 실제로 등장한 사건에 근거한다. **없는 사건을 지어내지 않는다.**
- 예외: `stock_picks`의 price·change·ma20 등 구조화 수치는 제공된 `us_candidates` 데이터값을 그대로 쓴다(검증 단계에서 실측 확인됨).

## 오늘의 관점(todays_view) 작성 규칙

하루 전체를 한 줄로 프레이밍하는 리드다. 두 필드를 반드시 채운다.
- `view_title`: 오늘 미국장의 지배적 테마를 한 문장으로. 헤드라인 톤. (예: "돈이 소프트웨어를 떠나 AI 인프라로 — CPI가 그 속도를 정한다")
- `dek`: view_title을 뒷받침하는 1~2문장. 오늘의 대표 촉매와 그 파급을 요약. 해요체. 숫자 금지, 단어 강조만 허용.

## 오늘의 이슈(issues) 작성 규칙

오늘 미국장을 움직일 촉매를 **중요도 순으로 3~5개** 고른다. 각 이슈는 아래 구조를 따른다.

- `title`: 이슈 헤드라인. 무슨 일이 일어났는지 한 줄. 숫자 금지.
- `body`: 1~2문장. 무슨 일이고 왜 중요한지(어느 섹터·종목에 어떻게 작용하는지). 해요체. 숫자 금지.
- `down`(선택): 눌리는 쪽. `{"label": "섹터/테마명", "tickers": ["TICKER", ...]}`. 특정 종목이 없으면 tickers는 빈 배열.
- `up`(선택): 수혜 쪽. 같은 구조.

**양면/단면 규칙:**
- 자금 이동(rotation)형 이슈는 `down`+`up`을 **둘 다** 쓴다. (예: IBM 발언 → 소프트웨어 down, AI 인프라 up)
- 한 방향만 영향인 이슈는 한쪽만 쓴다. (예: CPI 서프라이즈 → 지수 전반 down 하나만)
- 어느 쪽도 특정 섹터로 좁혀지지 않으면 label을 "지수 전반"으로 쓰고 tickers는 빈 배열.

**이슈 선택 우선순위 (구체적 뉴스 촉매를 지수 등락 수치보다 우선):**
1. 📢 빅테크·주도주 이벤트 — 실적 콜 발언, 가이던스, 신제품, M&A, 대형 계약 (매그니피센트7·AVGO·AMD 등)
2. 📅 매크로 이벤트 — 오늘 예정/발표된 CPI·PPI·PCE·NFP·FOMC. 시장 분위기를 좌우하는 지표.
3. 🏦 금리·연준·달러 시그널
4. 🌏 아시아·유럽 증시, 지정학, 유가·금 등 오늘 뚜렷한 흐름
- 뉴스 요약에 촉매가 없으면 억지로 이슈를 만들지 않는다. 3개 미만이어도 있는 만큼만 쓴다.

## 종목 선택(stock_picks) 규칙 — 잭 켈로그 MA20 전략 (기존 유지)

- `us_candidates` 배열에서 `ma20_signal`이 "crossing_up"인 종목 최우선, "above"·`ma20_dist_pct` 작은 종목 차선.
- price, change_pct, ma20, ma20_dist_pct, ma200, ma200_dist_pct는 데이터값 그대로 사용(변경 금지).
- 3~5개, 섹터 분산 고려. 가능하면 오늘의 이슈와 연관된 종목을 우선.
- `scenario`: 정확히 2문장 해요체. 진입가·목표가·손절가는 여기 쓰지 않는다(구조화 필드로만).
- `action_guide`에 쓴 진입/목표/손절을 entry·target·target_pct·stop·stop_pct 필드로도 동일 출력.

## 출력 형식

순수 JSON만 출력한다. 마크다운 코드블록, 설명 텍스트, 앞뒤 줄바꿈 없이 오직 JSON.

**[필수] JSON에 반드시 포함할 필드: todays_view(view_title·dek), issues, stock_picks**

{
  "todays_view": {
    "view_title": "돈이 소프트웨어를 떠나 AI 인프라로 — CPI가 그 속도를 정한다",
    "dek": "IBM CEO 발언에 <b>SaaS 전반이 흔들리고</b>, 그 자금이 반도체·데이터센터로 쏠리고 있어요. 오늘 밤 나올 <b>CPI</b>가 이 회전의 속도를 정할 거예요."
  },
  "issues": [
    {
      "title": "IBM CEO \\"고객사, AI 인프라 투자하느라 SW 지출 줄인다\\"",
      "body": "실적 콜 발언에 SaaS 전반이 흔들렸어요. 기업 IT 예산이 소프트웨어 구독에서 클라우드·AI 인프라로 옮겨가는 구조적 반작용이 부각됐어요.",
      "down": {"label": "소프트웨어", "tickers": ["CRM", "NOW", "ADBE"]},
      "up": {"label": "AI 인프라", "tickers": ["NVDA", "AVGO"]}
    },
    {
      "title": "오늘 밤 CPI 발표 — 금리 인하 기대의 분수령",
      "body": "물가가 예상을 웃돌면 위험자산 전반에 부담이에요. 반대로 둔화가 확인되면 성장주에 안도 랠리가 나올 수 있어요.",
      "down": {"label": "지수 전반", "tickers": []}
    }
  ],
  "stock_picks": [
    {
      "ticker": "NVDA",
      "name": "NVDA (엔비디아)",
      "price": "$XXX.XX",
      "change": "+X.XX%",
      "change_cls": "up",
      "signal": "20일선 상향 돌파",
      "golden": false,
      "ma20_dist_pct": 3.2,
      "ma200_dist_pct": 22.1,
      "scenario_tag": "모멘텀 가속",
      "scenario": "전일 20일선을 막 돌파한 종목이에요. AI 인프라로의 자금 회전에서 수혜가 이어질 것 같아요.",
      "action_guide": "시가 $XXX 이내 진입. 목표: $YYY / 손절: $ZZZ 이탈 시.",
      "entry": "$XXX", "target": "$YYY", "target_pct": "+X.X%", "stop": "$ZZZ", "stop_pct": "-X.X%"
    }
  ]
}
"""
```

- [ ] **Step 3: 문법 확인 (파일이 import 가능한지)**

Run: `python3 -c "import ast; ast.parse(open('scripts/call_claude.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 4: 커밋**

```bash
git add scripts/call_claude.py
git commit -m "feat(us): US_SYSTEM_PROMPT를 이슈 중심 계약(todays_view·issues)으로 교체"
```

---

## Task 2: call_claude.py — US 파이프라인 배선에서 예측·형식 로테이션 제거

US는 이제 예측이 없으므로 형식 로테이션·시그널 히스토리·예측 채점 기록을 하지 않는다. 이 3곳은 `if briefing_type in ("kospi", "us")` 또는 `if args.type != "kospi-close"` 조건으로 US를 포함하고 있어, US를 빼야 한다.

**Files:**
- Modify: `scripts/call_claude.py:1342-1367` (형식 로테이션 + 시그널 회피)
- Modify: `scripts/call_claude.py:1414-1417` (시그널 히스토리 저장)
- Modify: `scripts/call_claude.py:1503-1505` (예측 채점 기록)

- [ ] **Step 1: 형식 로테이션을 kospi 전용으로 축소**

`scripts/call_claude.py` line 1361-1367 블록:

```python
    # 브리핑 형식 랜덤 선택 (Python이 제어, Claude는 지시받은 형식만 사용)
    if briefing_type == "kospi":
        chosen_format = random.choices(FORMAT_POOL_KOSPI, weights=FORMAT_WEIGHTS_KOSPI, k=1)[0]
    else:
        chosen_format = random.choices(FORMAT_POOL, weights=FORMAT_WEIGHTS, k=1)[0]
    user_content += f"\n\n## 오늘 브리핑 근거 섹션 형식\n반드시 `{chosen_format}` 형식으로 출력하고, JSON에 `\"analysis_format\": \"{chosen_format}\"`을 포함한다.\n"
    print(f"[call_claude] Selected format: {chosen_format}")
```

를 아래로 바꾼다 (US는 형식 지시 없음):

```python
    # 브리핑 형식 랜덤 선택 — kospi 예측 브리핑 전용. US는 이슈 중심이라 형식 로테이션을 쓰지 않는다.
    chosen_format = None
    if briefing_type == "kospi":
        chosen_format = random.choices(FORMAT_POOL_KOSPI, weights=FORMAT_WEIGHTS_KOSPI, k=1)[0]
        user_content += f"\n\n## 오늘 브리핑 근거 섹션 형식\n반드시 `{chosen_format}` 형식으로 출력하고, JSON에 `\"analysis_format\": \"{chosen_format}\"`을 포함한다.\n"
        print(f"[call_claude] Selected format: {chosen_format}")
```

- [ ] **Step 2: analysis_format 강제 주입을 조건부로**

line 1411-1412:

```python
    # 브리핑 형식 강제 주입 — Claude가 빠뜨려도 항상 올바른 형식 보장
    analysis["analysis_format"] = chosen_format
```

를 아래로 바꾼다:

```python
    # 브리핑 형식 강제 주입 — kospi 전용(US는 형식 없음)
    if chosen_format:
        analysis["analysis_format"] = chosen_format
```

- [ ] **Step 3: 시그널 히스토리 저장을 kospi 전용으로**

line 1414-1417:

```python
    # 응답에서 시그널 추출 후 히스토리에 저장 (kospi 예측 + us 브리핑)
    if briefing_type in ("kospi", "us"):
        signals = extract_signal_emojis(analysis.get("reasons", []))
        save_signal_to_history(briefing_type, date_str, signals)
```

를 아래로 바꾼다 (US는 reasons가 없으므로 제외):

```python
    # 응답에서 시그널 추출 후 히스토리에 저장 (kospi 예측 전용 — US는 reasons 없음)
    if briefing_type == "kospi":
        signals = extract_signal_emojis(analysis.get("reasons", []))
        save_signal_to_history(briefing_type, date_str, signals)
```

- [ ] **Step 4: 시그널 회피 힌트도 kospi 전용으로**

line 1342-1350:

```python
    # 다양성 가이드: 최근 시그널 카테고리 회피 (kospi 예측 + us 브리핑)
    if briefing_type in ("kospi", "us"):
        history = load_signal_history(briefing_type)
```

의 조건을 `if briefing_type == "kospi":` 로 바꾼다. (그 아래 블록 들여쓰기·내용은 그대로 둔다.)

- [ ] **Step 5: 예측 채점 기록에서 US 제외**

line 1503-1505:

```python
        # validate 통과 후 교정된 analysis로 briefings.json 기록 (kospi-close는 prediction 필드 없음)
        if args.type != "kospi-close":
            save_prediction_to_briefings(args.type, date_str, analysis)
```

를 아래로 바꾼다 (US도 예측 채점 탈퇴 — kospi만 기록):

```python
        # validate 통과 후 교정된 analysis로 briefings.json 기록.
        # kospi만 예측 채점 대상 — US는 이슈 중심 전환(2026-07-14)으로 채점 탈퇴, kospi-close는 prediction 없음.
        if args.type == "kospi":
            save_prediction_to_briefings(args.type, date_str, analysis)
```

- [ ] **Step 6: 문법 확인**

Run: `python3 -c "import ast; ast.parse(open('scripts/call_claude.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 7: 커밋**

```bash
git add scripts/call_claude.py
git commit -m "feat(us): 예측 형식 로테이션·시그널 히스토리·예측 채점 기록에서 US 제외"
```

---

## Task 3: call_claude.py — save_telegram_message의 US 분기를 이슈 기반으로 재구성

US 텔레그램 메시지가 더 이상 존재하지 않는 `prediction`을 참조하지 않도록, US일 때는 `todays_view.view_title` + 이슈 제목으로 메시지를 만든다.

**Files:**
- Modify: `scripts/call_claude.py:1146-1211` (save_telegram_message)
- Test: `scripts/test_us_telegram_message.py` (신규)

- [ ] **Step 1: 실패하는 테스트 작성**

Create `scripts/test_us_telegram_message.py`:

```python
# US 이슈 중심 텔레그램 메시지가 예측 대신 오늘의 관점·이슈 제목으로 구성되는지 검증
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import call_claude as cc


def test_us_telegram_uses_todays_view_and_issues(tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    analysis = {
        "todays_view": {"view_title": "돈이 SW에서 AI 인프라로", "dek": "..."},
        "issues": [
            {"title": "IBM CEO SW 지출 경고"},
            {"title": "오늘 밤 CPI 발표"},
            {"title": "엔비디아 중국 재개"},
        ],
    }
    cc.save_telegram_message("us", "2026-07-14", analysis)
    msg = (tmp_path / "telegram_message_us.txt").read_text(encoding="utf-8")
    assert "미국 시장 브리핑" in msg
    assert "돈이 SW에서 AI 인프라로" in msg
    assert "IBM CEO SW 지출 경고" in msg
    assert "예측:" not in msg          # 예측 라인이 없어야 함
    assert "신뢰도:" not in msg


def test_kospi_telegram_still_has_prediction(tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "DATA_DIR", tmp_path)
    analysis = {
        "prediction": {"direction": "상승 우위", "up_pct": 60, "down_pct": 40, "confidence": 70},
        "reason_title": "왜 오를까",
        "reasons": ["📈 선물 강세예요."],
    }
    cc.save_telegram_message("kospi", "2026-07-14", analysis)
    msg = (tmp_path / "telegram_message_kospi.txt").read_text(encoding="utf-8")
    assert "예측:" in msg
    assert "신뢰도:" in msg
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest scripts/test_us_telegram_message.py -v`
Expected: FAIL — 현재 US 메시지에 "예측:"·"신뢰도:"가 들어가 있어 `assert "예측:" not in msg` 실패.

- [ ] **Step 3: save_telegram_message에 US 분기 추가**

`scripts/call_claude.py` line 1170-1205 구간(kospi/else 분기와 lines 구성)을 아래로 바꾼다. 기존 pred 파싱(1157-1168)은 kospi에서만 쓰이므로 그대로 두되, US는 별도 경로로 빠진다.

`if briefing_type == "kospi":` 로 시작하는 블록(1170행)부터 `msg = "\n".join(lines)` (1207행) 직전까지를 아래로 교체한다:

```python
    if briefing_type == "us":
        # US 이슈 중심: 예측 대신 오늘의 관점 + 이슈 제목으로 구성
        header = f"🇺🇸 미국 시장 브리핑 | {date_display}"
        link   = f"{web_base}/briefings/us/{date_str}/"
        tv = analysis.get("todays_view") or {}
        view_title = strip_html(tv.get("view_title", ""))
        issues = analysis.get("issues") or []
        lines = [header, divider]
        if view_title:
            lines += [f"🧭 {view_title}"]
        issue_titles = [strip_html(it.get("title", "")) for it in issues if it.get("title")]
        if issue_titles:
            lines += ["", "오늘 점검할 이슈:"]
            for t in issue_titles[:3]:
                lines.append(f"• {t}")
        lines += [f"🔗 상세 분석 → {link}"]
    else:
        if briefing_type == "kospi":
            header = f"🇰🇷 코스피 예측 브리핑 | {date_display}"
            link   = f"{web_base}/briefings/ko/{date_str}/"
        else:
            header = f"📊 브리핑 | {date_display}"
            link   = f"{web_base}/briefings/{date_str}/"

        # 직전 예측 결과. 아직 채점 전(check_accuracy가 이 발송 이후인 09:10 KST에 실행)이면
        # None → 배지 자체를 생략한다(_last_scored_result 참고 — 옛 채점 결과로 대체 금지).
        prev_result = ""
        if briefing_type == "kospi":
            prev = _last_scored_result("kospi", date_str)
            prev_result = "지난 예측 ✓ 적중" if prev is True else ("지난 예측 ✗ 빗나감" if prev is False else "")

        lines = [
            header,
            divider,
            f"{dir_emoji} 예측: <b>{direction} ({dir_pct}%)</b>",
            f"신뢰도: <b>{confidence}%</b>",
        ]
        if prev_result:
            lines += [prev_result]

        if reason_title:
            lines += [divider, f"💬 {reason_title}"]

        # telegram_signals 우선 사용, 없으면 reasons 앞 2개로 폴백
        signals = telegram_signals[:2] if telegram_signals else [strip_html(r) for r in reasons[:2]]
        if signals:
            lines += ["", "핵심 시그널:"]
            for s in signals:
                lines.append(f"• {strip_html(s)}")

        lines += [f"🔗 상세 분석 → {link}"]
```

주: 기존 코드에서 `header`/`link`가 kospi/else로 먼저 정해지던 것(1170-1175)이 위 블록으로 흡수되므로, **1170-1175의 기존 `if briefing_type == "kospi": ... else: ...` header/link 블록은 삭제**한다(위 교체 블록이 그 역할을 대신함). `divider = "─" * 20`(1177) 정의는 위 블록보다 앞에 있어야 하므로 유지한다.

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest scripts/test_us_telegram_message.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/call_claude.py scripts/test_us_telegram_message.py
git commit -m "feat(us): 텔레그램 메시지를 이슈 중심(오늘의 관점+이슈 제목)으로 재구성 + 테스트"
```

---

## Task 4: generate_html.py — build_issues 헬퍼 + 숫자 가드

이슈 배열을 렌더 컨텍스트로 정규화하고, title·body에 새어든 가격·등락률·지수 레벨 숫자를 최종 방어선에서 제거한다.

**Files:**
- Modify: `scripts/generate_html.py` (헬퍼 함수 추가 — build_prediction 등 다른 build_* 함수 근처)
- Test: `scripts/test_build_issues.py` (신규)

- [ ] **Step 1: 실패하는 테스트 작성**

Create `scripts/test_build_issues.py`:

```python
# build_issues: 이슈 정규화 + title·body 숫자 가드 검증
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_html as gh


def test_two_sided_issue_normalized():
    analysis = {"issues": [{
        "title": "IBM SW 경고",
        "body": "SaaS가 흔들려요.",
        "down": {"label": "소프트웨어", "tickers": ["CRM", "NOW"]},
        "up": {"label": "AI 인프라", "tickers": ["NVDA"]},
    }]}
    out = gh.build_issues(analysis)["issues"]
    assert len(out) == 1
    assert out[0]["down"]["tickers"] == ["CRM", "NOW"]
    assert out[0]["up"]["label"] == "AI 인프라"


def test_single_sided_issue_keeps_one_side():
    analysis = {"issues": [{"title": "CPI 발표", "body": "부담이에요.",
                            "down": {"label": "지수 전반", "tickers": []}}]}
    out = gh.build_issues(analysis)["issues"]
    assert "up" not in out[0]
    assert out[0]["down"]["label"] == "지수 전반"


def test_numbers_stripped_from_title_and_body():
    analysis = {"issues": [{
        "title": "CRM -4% 급락, 지수 5,431 이탈",
        "body": "엔비디아가 $168까지 올랐어요. 반도체가 +2.3% 강세예요.",
        "up": {"label": "반도체", "tickers": ["NVDA"]},
    }]}
    out = gh.build_issues(analysis)["issues"][0]
    for token in ["-4%", "5,431", "$168", "+2.3%"]:
        assert token not in out["title"] + out["body"], f"{token} 가 남아있음"
    # 티커 필드는 영향받지 않음
    assert out["up"]["tickers"] == ["NVDA"]


def test_empty_or_titleless_issues_dropped():
    analysis = {"issues": [{"title": "", "body": "x"}, {"body": "no title"}]}
    assert gh.build_issues(analysis)["issues"] == []


def test_no_issues_key():
    assert gh.build_issues({})["issues"] == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest scripts/test_build_issues.py -v`
Expected: FAIL — `AttributeError: module 'generate_html' has no attribute 'build_issues'`

- [ ] **Step 3: build_issues + _strip_issue_numbers 구현**

`scripts/generate_html.py` 상단 import 구역에 `re`가 이미 있는지 확인(`grep -n "^import re" scripts/generate_html.py`). 없으면 추가한다. 그리고 다른 `def build_*` 함수들 근처에 아래를 추가한다:

```python
# 이슈 카드 title·body에서 새어든 수치(등락률·가격·지수 레벨)를 제거하는 최종 방어선.
# 운영 규칙 0: 이슈 카드에는 실측이 없으므로 어떤 숫자도 표시하지 않는다(티커는 별도 필드라 무관).
_ISSUE_NUM_PATTERNS = [
    re.compile(r"[-+]?\d[\d,.]*\s*%"),          # 등락률: -4%, +2.3%
    re.compile(r"\$\s?\d[\d,.]*"),               # 가격: $168, $ 168.5
    re.compile(r"\b\d{1,3}(?:,\d{3})+\b"),       # 콤마 그룹 지수 레벨: 5,431
]


def _strip_issue_numbers(text: str) -> str:
    if not text:
        return ""
    out = text
    for pat in _ISSUE_NUM_PATTERNS:
        out = pat.sub("", out)
    # 숫자 제거로 생긴 이중 공백·공백앞 구두점 정리
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\s+([,.·])", r"\1", out)
    return out.strip()


def build_issues(analysis: dict) -> dict:
    """analysis.issues → 렌더용 이슈 리스트. title 없는 항목 제외, title·body 숫자 가드 적용."""
    issues = []
    for it in (analysis.get("issues") or []):
        title = _strip_issue_numbers(it.get("title", ""))
        if not title:
            continue
        entry = {"title": title, "body": _strip_issue_numbers(it.get("body", ""))}
        for side in ("down", "up"):
            s = it.get(side)
            if isinstance(s, dict) and (s.get("label") or s.get("tickers")):
                entry[side] = {"label": s.get("label", ""), "tickers": list(s.get("tickers") or [])}
        issues.append(entry)
    return {"issues": issues}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest scripts/test_build_issues.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/generate_html.py scripts/test_build_issues.py
git commit -m "feat(us): generate_html build_issues + 이슈 숫자 가드 헬퍼 + 테스트"
```

---

## Task 5: generate_html.py — render_briefing에 US 이슈 분기 배선

US일 때 prediction/reasons 대신 issues·todays_view를 컨텍스트에 넣고, accuracy 사이드바를 끄고, og_description을 관점 기반으로 만든다.

**Files:**
- Modify: `scripts/generate_html.py:917-948` (render_briefing의 close/else 분기)

- [ ] **Step 1: else 분기를 us / kospi로 나눈다**

`scripts/generate_html.py` line 920-948 (현재 `else:` 블록, close가 아닌 kospi·us 공용 경로)를 아래 구조로 바꾼다. 기존 kospi 관련 코드(build_prediction, build_reasons, us_linked/sector 등)는 `elif internal_type == "kospi":` 아래로 그대로 옮긴다.

기존 블록:

```python
    else:
        ctx.update(build_prediction(analysis, index_name, config["pred_title"], gen_time))
        ctx.update(build_reasons(analysis))
        ctx.update(build_analyst_quotes(market_data))
        ctx["stock_picks"] = build_stock_picks(analysis, market_data, internal_type)
        ctx["market_items"] = build_market_items(market_data, internal_type, gen_time)
        ctx["watch_items"] = analysis.get("watch_items") or analysis.get("watchpoints") or []
        # 오늘의 관점(todays_view) — 코스피 오전 브리핑 전용. 없으면 None → 템플릿에서 섹션 생략.
        ctx["todays_view"] = analysis.get("todays_view") if internal_type == "kospi" else None
        # 코스피는 근거 형식을 '오늘의 관점' 안에서 렌더 → 형식별 자체 제목(reason_title) 숨김.
        ctx["format_in_view"] = (internal_type == "kospi")
        if internal_type == "kospi":
            ctx.update(build_ib_korea_views())
            uls = analysis.get("us_linked_story") or {}
            if uls.get("title"):
                ctx["us_linked_title"] = uls["title"]
                ctx["us_linked_paragraphs"] = uls.get("paragraphs", [])
                ctx["us_linked_stocks"] = uls.get("related_stocks", [])
            else:
                # us_linked_story가 없으면(또는 폴백) 섹터 리뷰를 렌더한다 — 날짜 시드 랜덤으로 택1됨
                sf = analysis.get("sector_focus") or {}
                if sf.get("signal") and sf.get("paragraphs"):
                    ctx["sector_emoji"] = sf.get("emoji", "🏭")
                    ctx["sector_name"] = sf.get("sector_name", "반도체")
                    ctx["sector_signal"] = sf["signal"]
                    ctx["sector_paragraphs"] = sf.get("paragraphs", [])
        d = ctx.get("direction", "")
        rp = ctx.get("readout_pct", "")
        ctx["og_description"] = f"{config['pred_title']}: {d} {rp}% · 신뢰도 {ctx.get('confidence','')}%"
```

를 아래로 바꾼다:

```python
    elif internal_type == "us":
        # 미국 이슈 중심 브리핑 — 예측 대신 오늘의 관점 + 이슈 카드. 성적표 사이드바 없음.
        ctx.update(build_issues(analysis))
        ctx.update(build_analyst_quotes(market_data))
        ctx["stock_picks"] = build_stock_picks(analysis, market_data, internal_type)
        ctx["market_items"] = build_market_items(market_data, internal_type, gen_time)
        ctx["todays_view"] = analysis.get("todays_view")
        ctx["accuracy"] = False  # US 채점 탈퇴 — 성적표 사이드바 미표시
        tv = analysis.get("todays_view") or {}
        ctx["og_description"] = tv.get("view_title") or f"{target_date} 미국 시장 이슈 점검"
    else:
        ctx.update(build_prediction(analysis, index_name, config["pred_title"], gen_time))
        ctx.update(build_reasons(analysis))
        ctx.update(build_analyst_quotes(market_data))
        ctx["stock_picks"] = build_stock_picks(analysis, market_data, internal_type)
        ctx["market_items"] = build_market_items(market_data, internal_type, gen_time)
        ctx["watch_items"] = analysis.get("watch_items") or analysis.get("watchpoints") or []
        ctx["todays_view"] = analysis.get("todays_view")
        ctx["format_in_view"] = True  # 코스피는 근거 형식을 '오늘의 관점' 안에서 렌더
        ctx.update(build_ib_korea_views())
        uls = analysis.get("us_linked_story") or {}
        if uls.get("title"):
            ctx["us_linked_title"] = uls["title"]
            ctx["us_linked_paragraphs"] = uls.get("paragraphs", [])
            ctx["us_linked_stocks"] = uls.get("related_stocks", [])
        else:
            sf = analysis.get("sector_focus") or {}
            if sf.get("signal") and sf.get("paragraphs"):
                ctx["sector_emoji"] = sf.get("emoji", "🏭")
                ctx["sector_name"] = sf.get("sector_name", "반도체")
                ctx["sector_signal"] = sf["signal"]
                ctx["sector_paragraphs"] = sf.get("paragraphs", [])
        d = ctx.get("direction", "")
        rp = ctx.get("readout_pct", "")
        ctx["og_description"] = f"{config['pred_title']}: {d} {rp}% · 신뢰도 {ctx.get('confidence','')}%"
```

주: 마지막 `else:`는 이제 kospi 전용이다(close·us는 위에서 처리됨). `format_in_view`는 kospi에서 항상 True다.

- [ ] **Step 2: 문법 확인**

Run: `python3 -c "import ast; ast.parse(open('scripts/generate_html.py').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: 커밋**

```bash
git add scripts/generate_html.py
git commit -m "feat(us): render_briefing에 US 이슈 분기 배선 (issues·todays_view·성적표 제거)"
```

---

## Task 6: 신규 섹션 템플릿 _issues.html

**Files:**
- Create: `scripts/templates/sections/_issues.html`

- [ ] **Step 1: 템플릿 작성**

Create `scripts/templates/sections/_issues.html`:

```html
{# 미국 브리핑 오늘의 이슈 카드 (양면/단면 분기, 감성 색) #}
{% if issues %}
<div class="open-section">
  <div class="open-section__title">📌 오늘 점검할 이슈</div>
  <div class="issue-list">
    {% for it in issues %}
    <div class="issue-card">
      <div class="issue-card__title">{{ it.title }}</div>
      {% if it.body %}<div class="issue-card__body">{{ it.body }}</div>{% endif %}
      {% if it.down or it.up %}
      <div class="issue-card__impact">
        {% if it.down %}
        <div class="imp-side down">
          <span class="imp-arrow">▼</span><span class="imp-label">{{ it.down.label }}</span>
          {% if it.down.tickers %}<span class="imp-tickers">{% for t in it.down.tickers %}<span class="imp-tk">{{ t }}</span>{% endfor %}</span>{% endif %}
        </div>
        {% endif %}
        {% if it.up %}
        <div class="imp-side up">
          <span class="imp-arrow">▲</span><span class="imp-label">{{ it.up.label }}</span>
          {% if it.up.tickers %}<span class="imp-tickers">{% for t in it.up.tickers %}<span class="imp-tk">{{ t }}</span>{% endfor %}</span>{% endif %}
        </div>
        {% endif %}
      </div>
      {% endif %}
    </div>
    {% endfor %}
  </div>
</div>
{% endif %}
```

- [ ] **Step 2: 커밋**

```bash
git add scripts/templates/sections/_issues.html
git commit -m "feat(us): 오늘의 이슈 카드 섹션 템플릿 _issues.html 신규"
```

---

## Task 7: us.html 본문·사이드바 재구성

**Files:**
- Modify: `scripts/templates/briefings/us.html`

- [ ] **Step 1: accordion-body__inner 본문과 사이드바 교체**

`scripts/templates/briefings/us.html`에서 `<div class="accordion-body__inner">` 안의 본문 블록을 아래로 바꾼다(오늘의 관점 → 이슈 → 월가 코멘트 → 종목 픽):

```html
          <div class="accordion-body__inner">
            {% if todays_view %}
            <div class="open-section tv-lead">
              <div class="tv-kicker">🧭 오늘의 관점</div>
              <h2 class="tv-title">{{ todays_view.view_title }}</h2>
              {% if todays_view.dek %}<p class="tv-dek">{{ todays_view.dek | safe }}</p>{% endif %}
            </div>
            {% endif %}
            {% include "sections/_issues.html" %}
            <div class="divider"></div>
            {% if analyst_quotes %}{% include "sections/analyst_quotes.html" %}{% endif %}
            {% if stock_picks %}{% include "sections/stock_picks.html" %}{% endif %}
          </div>
```

그리고 `<aside class="layout-grid__right">` 블록에서 accuracy include를 제거한다. 아래로 바꾼다:

```html
    <aside class="layout-grid__right">
      {% if market_items %}{% include "sections/market_data.html" %}{% endif %}
      {% include "sections/_chip_cta.html" %}
    </aside>
```

주: 기존 `{% include "sections/prediction.html" %}`, format 분기(`{% if analysis_format ... %}`), `comfort_line`, `{% if accuracy %}...accuracy.html` 은 모두 제거된다.

- [ ] **Step 2: 문법·잔존 확인**

Run: `grep -nE "prediction.html|analysis_format|comfort_line|accuracy.html" scripts/templates/briefings/us.html`
Expected: (출력 없음 — 모두 제거됨)

- [ ] **Step 3: 커밋**

```bash
git add scripts/templates/briefings/us.html
git commit -m "feat(us): us.html을 오늘의 관점·이슈·월가·픽 구조로 재구성"
```

---

## Task 8: style.css에 이슈 카드 CSS 추가 (additive)

프로토타입에서 검증한 이슈 카드 스타일을 실제 스타일시트에 추가한다. 신규 클래스만 추가하므로 기존 페이지에 영향 없음. `tv-lead`·`open-section` 등은 이미 style.css에 존재하므로 재정의하지 않는다.

**Files:**
- Modify: `web/assets/style.css` (파일 끝에 추가)

- [ ] **Step 1: 이슈 카드 CSS 블록을 style.css 끝에 추가**

Append to `web/assets/style.css`:

```css
/* ── 미국 브리핑 오늘의 이슈 카드 ── */
.issue-list{display:flex;flex-direction:column;gap:12px;}
.issue-card{border:1px solid var(--hairline);border-radius:var(--r-md);padding:15px 16px;background:var(--canvas);}
.issue-card__title{font-size:15px;font-weight:800;color:var(--ink);letter-spacing:-.02em;line-height:1.4;}
.issue-card__body{font-size:13px;color:var(--muted);margin-top:7px;line-height:1.65;}
.issue-card__body b{color:var(--ink);}
.issue-card__impact{display:flex;flex-direction:column;gap:7px;margin-top:13px;padding-top:12px;border-top:1px dashed var(--hairline);}
.imp-side{display:flex;align-items:baseline;gap:9px;flex-wrap:wrap;}
.imp-arrow{font-size:11px;font-weight:800;flex-shrink:0;line-height:1.3;}
.imp-label{font-size:12px;font-weight:800;flex-shrink:0;}
.imp-side.down .imp-arrow,.imp-side.down .imp-label{color:var(--dn);}
.imp-side.up .imp-arrow,.imp-side.up .imp-label{color:var(--up);}
.imp-tickers{display:flex;gap:6px;flex-wrap:wrap;}
.imp-tk{font-size:11.5px;font-weight:700;padding:2px 8px;border-radius:5px;background:var(--surface-inset);color:var(--ink);letter-spacing:-.2px;}
.imp-side.down .imp-tk{background:var(--dn-bg);color:var(--dn);}
.imp-side.up .imp-tk{background:var(--up-bg);color:var(--up);}
```

- [ ] **Step 2: 커밋**

```bash
git add web/assets/style.css
git commit -m "feat(us): 이슈 카드 CSS 추가 (신규 클래스, additive)"
```

---

## Task 9: us.json config 갱신

**Files:**
- Modify: `scripts/config/us.json`

- [ ] **Step 1: sections_main 재정의 + 예측 관련 필드 정리**

`scripts/config/us.json`을 아래로 바꾼다:

```json
{
  "type": "us",
  "index_name": "S&P500",
  "template": "briefings/us.html",
  "url_prefix": "us",
  "scheduled_time": "21:20",
  "gnb_time": "21:20",
  "sections_main": ["todays_view", "issues", "analyst_quotes", "stock_picks"],
  "sections_sidebar": ["market_data"]
}
```

주: `pred_title` 제거. `generate_html.py`의 US 경로는 이제 `config["pred_title"]`을 참조하지 않는다(Task 5에서 og_description을 todays_view로 대체). `sections_main`/`sections_sidebar`는 문서적 선언이며 실제 렌더는 템플릿이 담당한다.

- [ ] **Step 2: pred_title 참조 잔존 확인**

Run: `python3 -c "import json; c=json.load(open('scripts/config/us.json')); print('pred_title' in c)"`
Expected: `False`

Run: `grep -n "config\[.pred_title.\]" scripts/generate_html.py`
Expected: US 경로(Task 5에서 수정한 `elif internal_type == \"us\"`)에는 없어야 함. kospi 경로(마지막 else)에만 남아 있으면 정상.

- [ ] **Step 3: 커밋**

```bash
git add scripts/config/us.json
git commit -m "feat(us): us.json sections_main을 이슈 중심 구조로 재정의, pred_title 제거"
```

---

## Task 10: check_accuracy.py — US 채점 탈퇴

US는 예측 기록을 더 이상 만들지 않지만(Task 2), 방어적으로 check_accuracy도 US를 건너뛰게 하고, 워크플로우의 US accuracy 스텝을 제거한다.

**Files:**
- Modify: `scripts/check_accuracy.py:170` (check_accuracy), `:239` (backfill)
- Modify: `.github/workflows/daily_report.yml:489-490` (US accuracy 스텝)
- Test: `scripts/test_check_accuracy_us_skip.py` (신규)

- [ ] **Step 1: 실패하는 테스트 작성**

Create `scripts/test_check_accuracy_us_skip.py`:

```python
# US는 예측 채점 대상이 아님을 검증 — check_accuracy("...", "us")는 아무 것도 채점하지 않는다
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_accuracy as ca


def test_check_accuracy_us_is_noop(capsys):
    # US는 조기 반환. 예외 없이 안내 로그만 출력.
    ca.check_accuracy("2026-07-14", "us")
    err = capsys.readouterr().err
    assert "us" in err.lower()


def test_backfill_us_is_noop(capsys):
    ca.backfill("us")
    err = capsys.readouterr().err
    assert "us" in err.lower()
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest scripts/test_check_accuracy_us_skip.py -v`
Expected: FAIL — 현재 check_accuracy가 US에 대해 briefings.json을 실제로 조회(조기 반환 안내 로그 없음).

- [ ] **Step 3: check_accuracy·backfill 조기 반환 추가**

`scripts/check_accuracy.py`의 `def check_accuracy(date_str, briefing_type="kospi", force=False):` 본문 첫 줄에 추가:

```python
    if briefing_type == "us":
        print("[check_accuracy] US는 이슈 중심 전환(2026-07-14)으로 채점 대상이 아니에요 — skip", file=sys.stderr)
        return
```

`def backfill(briefing_type="kospi", force=False):` 본문 첫 줄에도 동일하게 추가:

```python
    if briefing_type == "us":
        print("[check_accuracy] US backfill skip — 채점 탈퇴", file=sys.stderr)
        return
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest scripts/test_check_accuracy_us_skip.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 워크플로우에서 US accuracy 스텝 제거**

`.github/workflows/daily_report.yml`의 US accuracy 스텝(line 489-490 부근)을 찾는다:

Run: `grep -n "check_accuracy.py --type us" .github/workflows/daily_report.yml`

해당 스텝(`- name:` 블록 전체, `run: python3 scripts/check_accuracy.py --type us --backfill` 포함 2~4줄)을 삭제한다. `--type kospi --backfill` 스텝은 그대로 둔다.

- [ ] **Step 6: 워크플로우 YAML 유효성 확인**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/daily_report.yml')); print('OK')"`
Expected: `OK`

- [ ] **Step 7: 커밋**

```bash
git add scripts/check_accuracy.py scripts/test_check_accuracy_us_skip.py .github/workflows/daily_report.yml
git commit -m "feat(us): 예측 정확도 채점에서 US 탈퇴 (check_accuracy skip + 워크플로우 스텝 제거) + 테스트"
```

---

## Task 11: 엔드투엔드 렌더 검증 (가짜 날짜) + 브라우저 프리뷰

라이브를 건드리지 않고 `2099-01-01`로 US 브리핑을 실제 생성해 이슈 구조가 렌더되는지 확인한다.

**Files:**
- 임시: `data/analysis_us.json`(gitignored, 검증 후 원복), `web/briefings/2099-01-01/`(검증 후 삭제)

- [ ] **Step 1: 전체 테스트 스위트 통과 확인**

Run: `python3 -m pytest scripts/test_build_issues.py scripts/test_us_telegram_message.py scripts/test_check_accuracy_us_skip.py -v`
Expected: PASS (전부)

- [ ] **Step 2: 검증용 이슈 형식 fixture 작성 (원본 백업 후)**

```bash
cp data/analysis_us.json /tmp/analysis_us.backup.json
```

`data/analysis_us.json`을 아래 이슈 형식으로 덮어쓴다(stock_picks는 원본 값 일부 재사용 가능):

```json
{
  "todays_view": {
    "view_title": "돈이 소프트웨어를 떠나 AI 인프라로 — CPI가 그 속도를 정한다",
    "dek": "IBM CEO 발언에 <b>SaaS 전반이 흔들리고</b>, 그 자금이 반도체·데이터센터로 쏠리고 있어요."
  },
  "issues": [
    {"title": "IBM CEO \"고객사, AI 인프라 투자하느라 SW 지출 줄인다\"",
     "body": "실적 콜 발언에 SaaS 전반이 흔들렸어요. 기업 IT 예산이 클라우드·AI 인프라로 옮겨가는 반작용이 부각됐어요.",
     "down": {"label": "소프트웨어", "tickers": ["CRM", "NOW", "ADBE"]},
     "up": {"label": "AI 인프라", "tickers": ["NVDA", "AVGO"]}},
    {"title": "오늘 밤 CPI 발표 — 금리 인하 기대의 분수령",
     "body": "물가가 예상을 웃돌면 위험자산 전반에 부담이에요.",
     "down": {"label": "지수 전반", "tickers": []}},
    {"title": "엔비디아, 중국 H20 수출 재개 승인 소식",
     "body": "규제 완화 기대에 반도체 장비·설계주가 강세예요.",
     "up": {"label": "반도체", "tickers": ["NVDA", "AMD", "ASML"]}}
  ],
  "stock_picks": []
}
```

- [ ] **Step 3: 가짜 날짜로 렌더**

Run:
```bash
python3 scripts/generate_html.py --type us --date 2099-01-01 --data-file data/latest_us.json --force
```
Expected: 에러 없이 `web/briefings/2099-01-01/us/index.html` 생성.

- [ ] **Step 4: 렌더 결과 grep 검증**

Run:
```bash
grep -c "issue-card\|오늘의 관점\|imp-side" web/briefings/2099-01-01/us/index.html
grep -c "pred-badge\|성적표\|accuracy" web/briefings/2099-01-01/us/index.html
```
Expected: 첫 명령 ≥ 3 (이슈 구조 존재), 둘째 명령 0 (예측·성적표 없음).

- [ ] **Step 5: 브라우저 프리뷰로 시각 확인**

로컬 서버로 `web/briefings/2099-01-01/us/index.html`을 열어(예: `python3 -m http.server`) 오늘의 관점·이슈 카드(양면/단면 ▲▼)·월가·픽·사이드바가 프로토타입과 일치하는지 확인한다. `read_console_messages`로 JS 에러 없음 확인.

- [ ] **Step 6: 정리 — 임시 산출물 삭제 + fixture 원복**

```bash
rm -rf web/briefings/2099-01-01
cp /tmp/analysis_us.backup.json data/analysis_us.json
git status   # web/briefings/2099-01-01 이 남아있지 않은지, data/analysis_us.json이 원복됐는지 확인
```
Expected: `git status`에 2099-01-01 흔적 없음.

- [ ] **Step 7: 최종 커밋 (검증 자체는 산출물 없음 — 앞 태스크 커밋으로 충분. 필요 시 문서만)**

검증 단계는 코드 변경이 없으므로 별도 커밋 불필요. 전체 작업 완료 상태 확인:

Run: `git log --oneline -11`
Expected: Task 1~10의 커밋이 순서대로 보임.

---

## Self-Review 메모

- **Spec coverage:** 페이지 구조(Task 6·7), 데이터 계약 issues/todays_view(Task 1·4), 정확도 채점 탈퇴(Task 2·10), 텔레그램 배지(Task 3), 발행 보호 issues<2(Task 6의 `{% if issues %}` + 있는 만큼 렌더), 데이터 정합성 숫자 가드(Task 4), 프리장 신고가 제외(스펙 반영, 태스크 없음) — 모두 커버.
- **프리장 신고가:** 스펙에서 범위 제외 확정. 이 플랜에 태스크 없음.
- **accuracy-summary 히스토리:** 기존 US 기록은 `data/briefings.json`·`web/data/accuracy-summary.json`에 남지만 신규 US 예측이 추가되지 않으므로 증가하지 않는다. 과거 요약 재작성은 범위 밖(별도 정리 대상).
