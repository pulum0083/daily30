# 오늘의 관점(todays_view) 백엔드 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `call_claude.py`가 코스피 오전 브리핑에 "오늘의 관점"(`todays_view` = 어제 복기 + 오늘 볼 것)을 구조화 필드로 생성하고, `validate_analysis.py`가 그 안의 모든 종목 수치를 실측으로 검증·교정하며, 이벤트는 실제 뉴스/캘린더에 근거한 것만 남기게 한다.

**Architecture:** 재설계 4단계(A 백엔드 / B 프론트 / C 텔레그램 / D 성적표) 중 **A단계**. 기존 분석 스키마에 `todays_view` 필드를 **가산(additive)**으로 추가한다 — 기존 `reason_title`·`reasons`·포맷 필드는 건드리지 않아 현재 렌더링이 깨지지 않는다. 렌더링(포맷 6종이 관점을 그리는 방식)은 B단계에서 결정한다. A단계는 **검증된 데이터 구조 생산**까지만 책임진다.

**Tech Stack:** Python 3, Anthropic SDK(call_claude), pytest(`scripts/test_validate_analysis.py`), 토스 Open API / 네이버 일봉(실측), yfinance(폴백).

**데이터 정합성 철칙(이 계획의 최상위 제약):** 화면·메시지에 나가는 모든 수치는 생성 시점 실측이어야 한다. LLM이 만든 숫자·날짜·이벤트는 실측/실데이터로 검증되기 전엔 노출 금지. 검증 불가 항목은 **생성하지 않고 생략**한다(빈 배열·항목 제거). 이 계획의 Task 3·4가 그 게이트다.

---

## 확정된 스키마 결정 (구현 전 유저 확인 필요)

```jsonc
"todays_view": {
  "view_title": "반도체가 다시 끌어올렸지만, 오늘 진짜 변수는 금리",   // 에디토리얼 한 줄
  "recap": [                                    // 어제 복기 (전일 마감 실측 기반)
    { "text": "반도체가 지수를 끌어올렸어요. <b>SK하이닉스</b>·<b>삼성전자</b>가 상승분 대부분을 만들었어요.",
      "codes": ["000660", "005930"] },          // ← 언급 종목 코드 명시 (검증용)
    { "text": "외국인이 6거래일 만에 순매수로 전환했어요.", "codes": [] }
  ],
  "outlook": [                                  // 오늘 볼 것 (뉴스/캘린더 근거)
    { "tag": "event", "text": "삼성전자 잠정실적 발표가 임박했어요 — 이번 주 방향의 1순위.",
      "source": "news" },                       // ← event는 반드시 근거 소스 표기
    { "tag": "watch", "text": "외국인 순매수가 이틀째 이어질지 확인하세요.", "source": null }
  ]
}
```

**핵심 설계 근거:**
- `recap[].codes`에 **코드를 명시**함으로써, 검증기가 한국 종목 "이름→코드 사전" 없이 `_fetch_kospi_realdata(code)`로 바로 실측한다. (`validate_prose_nonpick_stocks`가 한국 종목 미지원인 갭을 우회 — `scripts/validate_analysis.py:341`.)
- `outlook[].tag == "event"`는 **사실 주장**(실적 일정·지표 발표)이므로 반드시 `source`가 있어야 하고, 없으면 Task 4에서 제거된다. `tag == "watch"`는 정성적 관전 포인트라 소스 불요.
- 기존 `reason_title`/`reasons`/포맷 필드는 **그대로 유지**. `todays_view`는 추가 필드일 뿐.

> ⚠️ **B단계 미결 사항(지금 결정 안 함):** 포맷 6종(flow/keynum/scenario…)이 `todays_view`를 렌더하는 방식 — 캐논 구조를 generate_html이 기계 변환(Model 1) vs LLM이 포맷별 저작(Model 2). A단계는 캐논 구조만 생산하므로 이 결정과 무관하게 진행 가능.

---

## 파일 구조

- **Modify** `scripts/call_claude.py` — 시스템 프롬프트에 `todays_view` 스키마·근거 규칙 추가, JSON 예시에 필드 추가, kospi 브리핑에만 적용.
- **Modify** `scripts/validate_analysis.py` — `validate_todays_view_recap()` 신규(코드 기반 실측 교정), `validate_todays_view_outlook()` 신규(이벤트 근거 게이트), `validate()`에서 호출.
- **Test** `scripts/test_validate_analysis.py` — 위 두 함수의 단위 테스트 추가.

---

## Task 1: `todays_view` 검증 — recap 종목 실측 교정 (핵심 게이트, TDD)

**Files:**
- Modify: `scripts/validate_analysis.py` (신규 함수 `validate_todays_view_recap`, 기존 `_fetch_kospi_realdata:567`·`_direction_contradicts:317` 재사용)
- Test: `scripts/test_validate_analysis.py`

- [ ] **Step 1: 실패 테스트 작성** — recap 항목의 방향 서술이 실측과 모순이면 항목이 제거되고 correction이 기록되는지.

```python
# scripts/test_validate_analysis.py 에 추가
import scripts.validate_analysis as va

def test_todays_view_recap_removes_contradicted_stock(monkeypatch):
    # 005930 실측이 하락(-1.5%)인데 recap은 "급등"이라고 주장 → 제거되어야 함
    def fake_fetch(code):
        return {"change_pct": -1.5, "price": 70000.0} if code == "005930" else {"error": "n/a"}
    monkeypatch.setattr(va, "_fetch_kospi_realdata", fake_fetch)

    analysis = {"todays_view": {"view_title": "t", "recap": [
        {"text": "<b>삼성전자</b>가 급등하며 지수를 끌어올렸어요.", "codes": ["005930"]},
        {"text": "외국인이 순매수로 전환했어요.", "codes": []},
    ], "outlook": []}}
    corrections, warnings = [], []
    va.validate_todays_view_recap(analysis, "kospi", corrections, warnings)

    texts = [r["text"] for r in analysis["todays_view"]["recap"]]
    assert "삼성전자" not in " ".join(texts)        # 모순 항목 제거
    assert "외국인" in " ".join(texts)               # 코드 없는 항목은 유지
    assert any("todays_view" in c for c in corrections)
```

- [ ] **Step 2: 실패 확인**

Run: `cd "/Users/luke/Service App/double-shot" && python3 -m pytest scripts/test_validate_analysis.py::test_todays_view_recap_removes_contradicted_stock -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'validate_todays_view_recap'`

- [ ] **Step 3: 최소 구현** — `validate_analysis.py`에 추가 (기존 `_direction_contradicts`, `_fetch_kospi_realdata` 재사용):

```python
def validate_todays_view_recap(analysis: dict, btype: str,
                               corrections: list, warnings: list) -> None:
    """오늘의 관점 recap 항목 중, codes로 명시된 종목의 방향 서술이
    실측과 모순이면 해당 항목을 제거한다. (한국 종목: 코드로 직접 실측)"""
    if btype != "kospi":
        return
    tv = analysis.get("todays_view") or {}
    recap = tv.get("recap")
    if not isinstance(recap, list):
        return
    # 코드→실측 등락률 캐시
    real: dict = {}
    for item in recap:
        for code in (item.get("codes") or []):
            if code not in real:
                d = _fetch_kospi_realdata(code)
                if "error" not in d and d.get("change_pct") is not None:
                    real[code] = d["change_pct"]
    kept = []
    for item in recap:
        codes = [c for c in (item.get("codes") or []) if c in real]
        bad = [c for c in codes if _direction_contradicts(item.get("text", ""), real[c])]
        if bad:
            corrections.append(f"todays_view.recap 항목 제거 (종목 방향 모순 {bad}): {item.get('text','')[:50]}")
        else:
            kept.append(item)
    tv["recap"] = kept
```

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest scripts/test_validate_analysis.py::test_todays_view_recap_removes_contradicted_stock -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add scripts/validate_analysis.py scripts/test_validate_analysis.py
git commit -m "feat(validate): todays_view recap 종목 실측 방향 검증"
```

---

## Task 2: `todays_view` 검증 — outlook 이벤트 근거 게이트 (TDD)

**Files:**
- Modify: `scripts/validate_analysis.py` (신규 `validate_todays_view_outlook`)
- Test: `scripts/test_validate_analysis.py`

- [ ] **Step 1: 실패 테스트 작성** — `tag=="event"`인데 `source`가 없거나 뉴스 근거에 없는 이벤트는 제거, `tag=="watch"`는 유지.

```python
def test_todays_view_outlook_drops_ungrounded_event():
    analysis = {"todays_view": {"view_title": "t", "recap": [], "outlook": [
        {"tag": "event", "text": "삼성전자 잠정실적 임박.", "source": "news"},   # 근거 있음 → 유지
        {"tag": "event", "text": "FOMC가 오늘 열려요.", "source": None},          # 근거 없음 → 제거
        {"tag": "watch", "text": "외국인 순매수 이어질지 보세요.", "source": None}, # watch → 유지
    ]}}
    corrections, warnings = [], []
    va.validate_todays_view_outlook(analysis, "kospi", corrections, warnings)
    kept = analysis["todays_view"]["outlook"]
    assert {"삼성전자 잠정실적 임박." in o["text"] for o in kept} == {True}
    assert all("FOMC" not in o["text"] for o in kept)     # 근거 없는 event 제거
    assert any(o["tag"] == "watch" for o in kept)          # watch 유지
    assert any("todays_view.outlook" in c for c in corrections)
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest scripts/test_validate_analysis.py::test_todays_view_outlook_drops_ungrounded_event -v`
Expected: FAIL — `has no attribute 'validate_todays_view_outlook'`

- [ ] **Step 3: 최소 구현**

```python
def validate_todays_view_outlook(analysis: dict, btype: str,
                                 corrections: list, warnings: list) -> None:
    """오늘의 관점 outlook 중 사실 주장(tag=='event')은 source가 있어야 유지한다.
    source가 없는 event는 근거 없는 일정 주장(할루시네이션 위험)이므로 제거.
    tag=='watch'(정성 관전)는 소스 없이 유지."""
    if btype != "kospi":
        return
    tv = analysis.get("todays_view") or {}
    outlook = tv.get("outlook")
    if not isinstance(outlook, list):
        return
    kept = []
    for o in outlook:
        if o.get("tag") == "event" and not (o.get("source") or "").strip():
            corrections.append(f"todays_view.outlook event 제거 (근거 소스 없음): {o.get('text','')[:50]}")
            continue
        kept.append(o)
    tv["outlook"] = kept
```

- [ ] **Step 4: 통과 확인**

Run: `python3 -m pytest scripts/test_validate_analysis.py::test_todays_view_outlook_drops_ungrounded_event -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add scripts/validate_analysis.py scripts/test_validate_analysis.py
git commit -m "feat(validate): todays_view outlook 이벤트 근거 게이트"
```

---

## Task 3: 검증 함수를 `validate()` 본류에 연결

**Files:**
- Modify: `scripts/validate_analysis.py` (`validate()` 함수, 기존 `validate_prose_nonpick_stocks` 호출 지점 근처 — line 849~)

- [ ] **Step 1: 실패 테스트 작성** — `validate()` 한 번 호출로 recap·outlook이 함께 교정되는지 (두 게이트가 배선됐는지).

```python
def test_validate_wires_todays_view(monkeypatch):
    monkeypatch.setattr(va, "_fetch_kospi_realdata", lambda c: {"change_pct": -2.0} if c == "000660" else {"error":"x"})
    analysis = {"todays_view": {"view_title": "t",
        "recap": [{"text": "<b>SK하이닉스</b>가 급등했어요.", "codes": ["000660"]}],
        "outlook": [{"tag": "event", "text": "지표 발표.", "source": None}]},
        "prediction": {"direction": "상승 우위", "up_pct": 55, "confidence": 60},
        "stock_picks": []}
    # validate()는 latest 데이터를 받지만 여기선 todays_view 경로만 확인
    corrections = va.validate(analysis, {"indices": {}}, "kospi").get("corrections", [])
    assert any("todays_view.recap" in c for c in corrections)
    assert any("todays_view.outlook" in c for c in corrections)
```

> 참고: `validate()`의 실제 반환 형태(현재 corrections/warnings를 어떻게 반환/구성하는지)를 `scripts/validate_analysis.py:849`에서 확인하고, 테스트의 반환 접근(`.get("corrections")`)을 실제 구조에 맞춘다. 반환이 튜플이면 언패킹으로 조정.

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest scripts/test_validate_analysis.py::test_validate_wires_todays_view -v`
Expected: FAIL (두 함수가 아직 `validate()`에서 호출되지 않음)

- [ ] **Step 3: 최소 구현** — `validate()` 내부, 기존 산문 검증 호출부 근처에 두 줄 추가:

```python
    validate_todays_view_recap(analysis, btype, corrections, warnings)
    validate_todays_view_outlook(analysis, btype, corrections, warnings)
```

- [ ] **Step 4: 통과 확인 + 전체 회귀**

Run: `python3 -m pytest scripts/test_validate_analysis.py -v`
Expected: 신규 3개 PASS, 기존 테스트 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add scripts/validate_analysis.py scripts/test_validate_analysis.py
git commit -m "feat(validate): validate()에 todays_view 검증 배선"
```

---

## Task 4: `call_claude.py` — `todays_view` 생성 프롬프트·스키마 추가

> 이 태스크는 프롬프트 엔지니어링이라 순수 TDD가 아니다. **수용 기준**(acceptance criteria)으로 검증한다.

**Files:**
- Modify: `scripts/call_claude.py` (JSON 예시 블록 `scripts/call_claude.py:389~412` 근처에 `todays_view` 추가, kospi 시스템 프롬프트에 생성 규칙 추가)

- [ ] **Step 1: JSON 예시에 `todays_view` 추가** — 위 "확정된 스키마" 블록을 예시 JSON에 삽입 (kospi 경로에만).

- [ ] **Step 2: 생성 규칙을 시스템 프롬프트에 추가** (아래 문안을 kospi 프롬프트에 삽입):

```
### 오늘의 관점(todays_view) 작성 규칙 (코스피 오전 브리핑 전용)
- view_title: 오늘 시장을 한 줄로 규정하는 에디토리얼 제목. 예측 방향 단정 금지, 관점 제시.
- recap(어제 복기, 2~3개): 전일 마감 데이터(지수·수급·섹터)에 근거해 "어제 무슨 일"을 서술.
  · 개별 종목을 언급하면 반드시 그 종목의 6자리 코드를 codes 배열에 넣는다. (미기재 시 검증 불가로 제거됨)
  · 픽에 없는 종목이라도 codes를 넣으면 실측 검증을 통과할 수 있다. 코드 없는 종목 수치 서술 금지.
- outlook(오늘 볼 것, 2~3개): 오늘 주목할 것.
  · tag="event"는 실적·지표 발표 등 **일정 사실**. 뉴스 요약(news_summary)·economic_calendar에 실제로 있는 것만. 있으면 source에 근거를 표기("news"/"calendar"). 근거 없으면 event로 쓰지 말 것.
  · tag="watch"는 "외국인 수급 지속 여부" 같은 **정성 관전 포인트**. 소스 불요, source=null.
  · 실제 이벤트가 없으면 outlook은 watch 항목만으로 채우거나 더 적게 출력한다. 없는 일정을 지어내지 않는다.
```

- [ ] **Step 3: 수용 기준 확인 — 실행 후 산출 JSON 점검**

Run: `cd "/Users/luke/Service App/double-shot" && python3 scripts/call_claude.py --type kospi --no-html` (실제 API 호출; 키 필요)
그 후:
```bash
python3 -c "import json;d=json.load(open('data/analysis_kospi.json'));tv=d.get('todays_view',{});
assert 'view_title' in tv and isinstance(tv.get('recap'),list) and isinstance(tv.get('outlook'),list), 'todays_view 구조 누락';
print('recap codes 존재:', all('codes' in r for r in tv['recap']));
print('event엔 source 존재:', all(o.get('source') for o in tv['outlook'] if o.get('tag')=='event'));
print('OK')"
```
Expected: `todays_view` 구조 존재, recap 항목마다 codes 키, event마다 source. 실패 시 프롬프트 문안 보강 후 재실행.

- [ ] **Step 4: 검증 파이프라인 end-to-end 확인**

Run: `python3 scripts/validate_analysis.py --type kospi`
Expected: 에러 없이 완료. recap 종목 수치가 실측과 다르면 correction 로그 출력, 근거 없는 event 제거 로그 출력.

- [ ] **Step 5: 커밋**

```bash
git add scripts/call_claude.py
git commit -m "feat(call_claude): 코스피 오전 브리핑 todays_view(오늘의 관점) 생성"
```

---

## Task 5: 파이프라인 순서·스냅샷 정합성 확인 (문서/회귀)

**Files:**
- 확인만: `scripts/call_claude.py`(--render 경로), `scripts/generate_html.py`(analysis_snapshot 커밋)

- [ ] **Step 1:** `call_claude --no-html → validate_analysis → call_claude --render` 순서에서 `todays_view`가 `--render` 시점(검증 후)의 데이터로 전달되는지 확인. (SERVICE_RULES 파이프라인 순서 준수 — 검증 이전 산출물에 관점이 들어가면 교정 미반영.)
- [ ] **Step 2:** `generate_html.py`가 커밋하는 `analysis_snapshot.json`에 `todays_view`가 포함되는지 확인(스냅샷은 전체 analysis dict를 저장하므로 자동 포함될 것 — 실제 확인).
- [ ] **Step 3:** B단계(프론트 렌더)는 이 스냅샷의 `todays_view`를 소비한다고 문서에 명시. 커밋.

```bash
git add docs/superpowers/plans/2026-07-11-todays-view-backend.md
git commit -m "docs: todays_view 백엔드 파이프라인 정합성 확인"
```

---

## Self-Review 메모

- **철칙 커버리지:** recap 종목 수치 → Task 1(실측 교정), outlook 이벤트 → Task 2(근거 게이트), 파이프라인 순서 → Task 5. LLM 생성 데이터가 검증 전 노출되는 경로 없음.
- **가산성:** 기존 `reasons`/포맷 필드 미변경 → 현재 렌더링 회귀 위험 없음.
- **B단계 의존:** 포맷이 관점을 그리는 방식(Model 1/2)은 A 완료 후 B에서 결정. A는 캐논 구조만 생산.
- **미해결(다음 단계):** 충돌 2(성적표 틀린 날 이유 저장)는 D단계에서 결정. outlook의 news/calendar 근거를 실제로 어떻게 주입하는지(현재 news_summary에 economic_calendar가 실려 있는지)는 Task 4 실행 시 확인 필요.
