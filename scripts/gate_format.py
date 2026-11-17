# 형식·제목 게이트 — 근거 형식과 본문 필드 일치, 헤드라인 숫자 대조, 금액 쉼표

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_text import strip_tags


# ── 형식↔본문 불일치 ──────────────────────────────────────────────────────────
# 각 형식의 '근거 섹션 본문'이 담기는 필드. 하나라도 차 있으면 섹션이 렌더된다.
# generate_html.build_*_context()가 실제로 읽는 키와 1:1로 맞춘다 — 한쪽만 바뀌면 이 게이트가
# 조용히 헛돈다. 형식을 추가할 땐 여기에도 등록할 것(test_registry_covers_every_rotation_format).
FORMAT_BODY_FIELDS = {
    "split": (),                                   # 형식별 필드 없음 — todays_view의 recap/outlook이 본문
    "scenario": ("sc_left_items", "sc_right_items", "sc_summary"),
    "why_what_so": ("why", "what", "so_what"),
    "brief": ("brief_lines", "dek"),               # 마감 세 줄 요약 — 세 줄이 다 빠져도 dek가 있으면 타이틀+dek로 렌더된다
    "qa": ("qa_items",),
    "signal": ("sig_items",),
    "flow": ("flow_steps",),
    "keynum": ("num_cards",),
}
FORMAT_FALLBACK = "split"


_TITLE_PCT_RE = re.compile(r"\d+(?:\.\d+)?(?=\s*%)")


_AMOUNT_NO_COMMA_RE = re.compile(r"(?<![\d,.])(\d{4,})(?=\s*(?:억|조|만|원))")


def fix_amount_commas(analysis, corrections):
    """제목·보조 문장의 금액(억·조·만·원 앞 네 자리 이상 숫자)에 쉼표를 넣는다 (전 타입, 2026-10-27).

    제목은 "6047억", 보조 문장은 "6,047억원"처럼 한 메시지 안에서 표기가 갈렸다. 숫자는 바꾸지 않고 표기만 맞춘다.
    "5500선"·"2026년"처럼 금액 단위가 아닌 숫자는 건드리지 않는다.
    """
    def fix(text):
        return _AMOUNT_NO_COMMA_RE.sub(lambda m: f"{int(m.group(1)):,}", text)

    targets = [(analysis, k) for k in ("reason_title", "market_title", "dek")]
    tv = analysis.get("todays_view")
    if isinstance(tv, dict):
        targets += [(tv, "view_title"), (tv, "dek")]
    for obj, key in targets:
        val = obj.get(key)
        if isinstance(val, str):
            new = fix(val)
            if new != val:
                obj[key] = new
                corrections.append(f"금액 쉼표 — {key}: {val[:40]} → {new[:40]}")


def fix_view_title_figures(analysis, btype, corrections):
    """헤드라인(todays_view.view_title)의 등락률이 검증된 본문에 없으면 헤드라인을 근거 문장으로 바꾼다 (kospi).

    헤드라인은 웹 페이지 맨 위·아카이브·텔레그램 첫 줄에 그대로 나가는데, 숫자 게이트는 key_drivers·recap에만 있다.
    그래서 헤드라인의 % 숫자는 게이트를 통과한 key_drivers·recap에 같은 숫자로 있어야 한다(부호는 보지 않는다 —
    "-6.72% 급락"과 "6.72% 밀렸다"는 같은 주장이다). 없으면 key_drivers[0]의 굵은 첫 문장으로 바꾼다(§0).
    호출 시점은 validate_key_drivers 이후 — 제거된 항목의 숫자를 근거로 삼지 않는다.
    """
    if btype != "kospi":
        return
    tv = analysis.get("todays_view")
    if not isinstance(tv, dict) or not isinstance(tv.get("view_title"), str):
        return
    title = tv["view_title"]
    figs = set(_TITLE_PCT_RE.findall(strip_tags(title)))
    if not figs:
        return
    kd = [k for k in (analysis.get("key_drivers") or []) if isinstance(k, dict)]
    evidence = " ".join(strip_tags(x.get("text", "")) for x in kd + list(tv.get("recap") or []) if isinstance(x, dict))
    missing = sorted(figs - set(_TITLE_PCT_RE.findall(evidence)))
    if not missing:
        return
    lead = ""
    if kd:
        m = re.search(r"<b>(.*?)</b>", kd[0].get("text", ""))
        lead = strip_tags(m.group(1) if m else kd[0].get("text", "")).strip()
    if lead and not (set(_TITLE_PCT_RE.findall(lead)) - set(_TITLE_PCT_RE.findall(evidence))):
        tv["view_title"] = lead
        corrections.append(f"view_title 교체 (근거에 없는 숫자 {missing}): {strip_tags(title)[:50]} → {lead[:50]}")
    else:
        corrections.append(f"view_title의 근거 없는 숫자 {missing} — 대체할 근거 문장이 없어 숫자만 지움: {strip_tags(title)[:50]}")
        tv["view_title"] = re.sub(r"\s*[+\-−]?\d+(?:\.\d+)?\s*%", "", title).strip()


def fix_format_payload_mismatch(analysis, corrections, warnings, blocks):
    """찍힌 analysis_format의 본문이 비었으면 내용에 맞는 형식으로 내려앉힌다.

    call_claude가 형식을 랜덤 추첨해 프롬프트로 지시한 뒤, 응답 내용과 무관하게
    `analysis["analysis_format"] = chosen_format`으로 덮어쓴다. 모델이 지시한 형식의 필드를
    내놓지 않으면 generate_html이 그 형식 템플릿을 골라 **빈 껍데기**를 렌더한다.

    2026-08-13 실사고: keynum으로 찍혔으나 num_cards가 없어 `<div class="keynum-grid"></div>`가
    그대로 발행됐다. 게다가 todays_view의 recap/outlook은 split일 때만 렌더되므로, 모델이
    만들어둔 복기·관전 2단까지 함께 사라져 근거 본문이 통째로 빈 채 나갔다.

    내용이 온전한데 포장만 어긋난 것이므로 발행을 막지 않고 split으로 내려앉힌다 — §0은
    "짧거나 섹션이 비는 것은 감수하되 틀린 것은 감수하지 않는다"이고, 여기서 틀린 것은 없다.
    다만 내려앉힐 내용조차 없으면 빈 브리핑이 나가므로 그때는 발행을 막는다.
    """
    fmt = analysis.get("analysis_format")
    if not fmt:
        return
    fields = FORMAT_BODY_FIELDS.get(fmt)
    if fields is None:
        warnings.append(
            f"analysis_format '{fmt}'가 FORMAT_BODY_FIELDS에 미등록 — 빈 섹션 검사를 건너뛴다. "
            "형식을 추가했다면 이 표에도 등록할 것")
        return
    if not fields or any(analysis.get(f) for f in fields):
        return

    # split으로 내려앉혔을 때 실제로 보여줄 본문이 남는가.
    tv = analysis.get("todays_view") or {}
    has_core = bool(tv.get("recap") or tv.get("outlook") or analysis.get("key_drivers"))
    if not has_core:
        blocks.append(
            f"analysis_format '{fmt}'의 본문({'/'.join(fields)})이 비었고 "
            "todays_view·key_drivers도 없어 근거 섹션이 통째로 빈다 — 빈 브리핑 발행 차단")
        return

    analysis["analysis_format"] = FORMAT_FALLBACK
    corrections.append(
        f"analysis_format '{fmt}' → '{FORMAT_FALLBACK}': "
        f"'{fmt}' 본문({'/'.join(fields)})이 비어 빈 섹션이 렌더될 상황 — "
        "모델이 실제로 만든 todays_view 본문으로 렌더한다")
