# 코스피 아침 '간밤 미국장' 카드 — 직전 미국 정규장의 지수·AI 칩·빅테크·섹터 등락을 모으고 규칙으로 한 문장을 만든다(2026-11-19)
"""
왜: 2026-11-19 아침 브리핑은 미국장을 "S&P500 −0.23%, 나스닥 +0.42%, 혼조 마감" 한 줄로만 썼다. 같은 밤
엔비디아 −2.89%·AMD +5.31%·브로드컴 +3.64%, 에너지 −3.27%·보안 +4.72%로 안에서는 돈이 크게 옮겨갔다.
지수 혼조 뒤의 이 흐름을 실측으로 짚는다.

- 숫자는 전부 정규장 종가-종가 등락(fetch_data._regular_session_change — 프리·애프터장 제외)이고,
  그 종가가 직전 미국장(prev_us_session) 날짜일 때만 쓴다. 다른 날 봉이면 그 종목을 뺀다(§45 날짜 고정).
- 문장은 숫자에서 정해진 규칙으로만 만든다. LLM 문장을 쓰지 않는다(§0).
- 화면은 '오늘의 이슈 점검'의 기존 카드 형식 그대로다(사용자 결정 2026-11-19).
"""
from __future__ import annotations

INDICES = [("^GSPC", "S&P500"), ("^IXIC", "나스닥"), ("^DJI", "다우"), ("^SOX", "반도체")]
AI_CHIPS = [("NVDA", "엔비디아"), ("AMD", "AMD"), ("AVGO", "브로드컴"), ("MU", "마이크론"), ("TSM", "TSMC"), ("ORCL", "오라클")]
BIGTECH = [("AAPL", "애플"), ("MSFT", "MS"), ("AMZN", "아마존"), ("META", "메타"), ("GOOGL", "알파벳"),
           ("TSLA", "테슬라")]
# 미국 섹터 ETF 11개 + 테마 2개(보안 CIBR · 소프트웨어 IGV)
SECTORS = [("XLK", "기술"), ("XLC", "커뮤니케이션"), ("XLY", "경기소비재"), ("XLP", "필수소비재"), ("XLE", "에너지"),
           ("XLF", "금융"), ("XLV", "헬스케어"), ("XLI", "산업재"), ("XLB", "소재"), ("XLRE", "부동산"),
           ("XLU", "유틸리티"), ("CIBR", "보안"), ("IGV", "소프트웨어")]
GROUPS = (("indices", INDICES), ("ai", AI_CHIPS), ("bigtech", BIGTECH), ("sectors", SECTORS))
BIG_MOVE = 1.0     # 문장에 이름을 올리는 최소 등락(%)
SECTOR_SHOW = 3    # 오른·내린 섹터 칩을 몇 개까지


def collect(prev_us: str, changes_fn) -> dict | None:
    """changes_fn(tickers) → {ticker: {"change_pct", "session_date"}}(fetch_data.fetch_regular_session_changes).
    직전 미국장(prev_us, 'YYYY-MM-DD') 날짜의 봉만 쓴다. 지수가 둘 미만이면 None(카드를 빼라는 뜻)."""
    tickers = [t for _, rows in GROUPS for t, _ in rows]
    try:
        ch = changes_fn(tickers) or {}
    except Exception as e:
        print(f"[us_session_map] 수집 실패: {e}")
        return None
    out = {"session": prev_us}
    for key, rows in GROUPS:
        out[key] = [{"ticker": t, "name": n, "pct": round(float(ch[t]["change_pct"]), 2)} for t, n in rows
                    if isinstance(ch.get(t), dict) and ch[t].get("session_date") == prev_us
                    and isinstance(ch[t].get("change_pct"), (int, float))]
    if len(out["indices"]) < 2:
        print(f"[us_session_map] {prev_us} 지수 봉이 {len(out['indices'])}개뿐 — 카드를 뺀다")
        return None
    return out


def _has_batchim(word: str) -> bool:
    """마지막 글자 받침. 영문은 읽는 소리로 — L·M·N·R(엘·엠·엔·알)만 받침이 있다."""
    ch = (word or " ")[-1]
    if "가" <= ch <= "힣":
        return (ord(ch) - 0xAC00) % 28 != 0
    return ch.upper() in "LMNR"


def _ga(word):
    return word + ("이" if _has_batchim(word) else "가")


def _names(rows):
    return "·".join(r["name"] for r in rows)


def _sorted(rows, reverse=True):
    return sorted(rows, key=lambda r: r["pct"], reverse=reverse)


def title_of(m: dict) -> str:
    signs = {r["pct"] > 0 for r in m["indices"] if r["pct"] != 0}
    if len(signs) == 2:
        inner = m["ai"] + m["sectors"]
        split = any(r["pct"] >= BIG_MOVE for r in inner) and any(r["pct"] <= -BIG_MOVE for r in inner)
        return "지수는 혼조, 안에서는 크게 갈렸어요" if split else "지수는 혼조로 끝났어요"
    if signs == {True}:
        return "지수가 나란히 올랐어요"
    if signs == {False}:
        return "지수가 나란히 내렸어요"
    return "지수는 거의 움직이지 않았어요"


def line_of(m: dict) -> str:
    """'AI 칩은 엔비디아가 내리고 AMD·브로드컴이 올랐어요. 섹터는 보안이 가장 많이 오르고 에너지가 가장 많이 내렸어요.'"""
    out = []
    ups = _sorted([r for r in m["ai"] if r["pct"] >= BIG_MOVE])[:2]
    downs = _sorted([r for r in m["ai"] if r["pct"] <= -BIG_MOVE], reverse=False)[:2]
    if ups and downs:
        out.append(f"AI 칩은 {_ga(_names(downs))} 내리고 {_ga(_names(ups))} 올랐어요.")
    elif ups:
        out.append(f"AI 칩은 {_ga(_names(ups))} 크게 올랐어요.")
    elif downs:
        out.append(f"AI 칩은 {_ga(_names(downs))} 크게 내렸어요.")
    if m["sectors"]:
        top, bot = _sorted(m["sectors"])[0], _sorted(m["sectors"], reverse=False)[0]
        if top["pct"] > 0 and bot["pct"] < 0:
            out.append(f"섹터는 {_ga(top['name'])} 가장 많이 오르고 {_ga(bot['name'])} 가장 많이 내렸어요.")
        elif top["pct"] > 0:
            out.append(f"섹터는 모두 올랐고 {_ga(top['name'])} 가장 많이 올랐어요.")
        elif bot["pct"] < 0:
            out.append(f"섹터는 모두 내렸고 {_ga(bot['name'])} 가장 많이 내렸어요.")
    return " ".join(out)


def card(m: dict | None) -> dict | None:
    """이슈 점검 카드 형식({title, check_line, groups})으로 바꾼다. 보여줄 게 없으면 None."""
    if not isinstance(m, dict) or len(m.get("indices") or []) < 2:
        return None
    m = {**{k: [r for r in (m.get(k) or []) if isinstance(r.get("pct"), (int, float))] for k, _ in GROUPS}, "session": m.get("session")}
    # 섹터는 많이 오른 3개와 많이 내린 3개를 한 열에 — 화면은 열 4개(지수·AI 칩·빅테크·섹터)로 맞춘다(2026-11-19)
    sec = (_sorted([r for r in m["sectors"] if r["pct"] > 0])[:SECTOR_SHOW]
           + _sorted([r for r in m["sectors"] if r["pct"] < 0])[-SECTOR_SHOW:])
    groups = [("지수", m["indices"]), ("AI 칩", _sorted(m["ai"])), ("빅테크", _sorted(m["bigtech"])), ("섹터", sec)]
    return {"title": title_of(m), "check_line": line_of(m), "session": m["session"],
            "groups": [{"label": lb, "marks": [{"name": r["name"], "pct": r["pct"]} for r in rows]}
                       for lb, rows in groups if rows]}


def directive(m: dict | None) -> str:
    """분석 프롬프트용 — 지수 혼조 뒤 자금 이동을 실측으로 알려 주고, 이 흐름을 짚게 한다."""
    c = card(m)
    if not c:
        return ""
    rows = "\n".join(f"- {g['label']}: " + ", ".join(f"{r['name']} {r['pct']:+.2f}%" for r in g["marks"])
                     for g in c["groups"])
    return ("## 직전 미국 정규장 지도 (실측, 정규장 종가 기준)\n"
            f"{c['title']}. {c['check_line']}\n{rows}\n"
            "지수 등락만 쓰지 말고, 지수 뒤에서 **어느 종목·섹터로 돈이 옮겨갔는지**(예: AI 칩 안에서 오른 쪽과 내린 쪽)를 "
            "`key_drivers`나 `todays_view` 복기에 한 번은 짚는다. 숫자는 위 표에 있는 것만 쓴다. "
            "위 등락은 정규장 종가 기준이다 — 시간외 움직임과 섞어 쓰지 않는다.\n\n")
