#!/usr/bin/env python3
# 어제 미국 브리핑이 내건 이슈의 결과를 그 세션 실측으로 채점해 코스피 아침 브리핑에 넘기는 스크립트
"""
Usage:
    python3 scripts/score_us_issues.py [--date YYYY-MM-DD]

출력: data/us_issue_results.json

미국 브리핑(21:15 KST)의 이슈 카드는 산문이 아니라 up/down × {label, tickers} 구조라
어떤 종목을 지목했는지가 스냅샷에 남아 있다. 그 세션이 끝난 뒤(미국 마감 05~06시 KST)
코스피 아침 브리핑(07:25)에서 **그 종목들이 실제로 어떻게 움직였는지만** 보여준다.

**적중·빗나감을 판정하지 않는다.** 미국 브리핑의 이슈는 예측이 아니라 관전 포인트라,
채점 대상이 아닌 것을 채점하면 무슨 말인지 알 수 없는 화면이 된다(2026-09-08 사용자 지적 —
"어제 랠리의 배경"이라는 서술형 이슈에 "3중 1 적중"이 붙어 있었다). 어제 예상과 맞았는지는
말하지 않고, 읽는 사람이 수치를 보고 직접 판단한다.

**숫자·문구가 전부 결정론이다. LLM이 개입하지 않는다.**

**날짜 고정 조회가 이 스크립트의 핵심이다.** 대상 ET 세션의 봉을 골라 직전 봉과 비교하고,
그 날짜 봉이 없으면 해당 티커를 버린다 — "최신 봉"으로 폴백하지 않는다. 07:25는 미국 마감
1.5시간 뒤라 일봉이 아직 안 왔을 수 있는데, 그때 최신 봉을 쓰면 조용히 **전전 세션 등락률**이
실린다(§24가 fast_info.previous_close를 믿어서 터진 것과 같은 계열). 나중에 재생성해도 같은
값이 나오는 것은 덤이다.

측정 불가는 채우지 않는다 — 티커도 프록시도 없는 이슈는 카드째 빠지고, 남는 카드가 0이면
섹션 자체가 사라진다(운영 규칙 0).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import pytz

sys.path.insert(0, str(Path(__file__).resolve().parent))
from session_label import us_session_to_score, us_session_label  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
BRIEFINGS_DIR = BASE_DIR / "web" / "briefings"
KST = pytz.timezone("Asia/Seoul")

OUT_PATH = DATA_DIR / "us_issue_results.json"

# 티커가 지정되지 않은 이슈에 대입하는 프록시. **지수 전반을 뜻하는 라벨만** 넣는다.
# "지수 전반·소비재·운송"처럼 섹터가 섞인 라벨은 S&P500 하나로 대표할 수 없어 일부러 뺐다 —
# 매핑을 늘릴수록 실측이 아니라 추론이 늘어난다. 채점 못 하는 이슈는 그냥 빠지면 된다.
_PROXY = {
    "지수 전반": ("^GSPC", "S&P500"),
    "지수전반": ("^GSPC", "S&P500"),
    "위험자산 전반": ("^GSPC", "S&P500"),
    "지수·위험자산": ("^GSPC", "S&P500"),
}

_PAREN_RE = re.compile(r"[(（].*?[)）]")


def normalize_label(label: str) -> str:
    """프록시 매칭용 정규화. 괄호 단서와 공백 차이를 걷어낸다.

    '지수 전반(변동성 하락)'·'지수 전반 (서프라이즈 시)'는 괄호가 조건일 뿐 주어는 지수 전반이다.
    반면 '지수 전반, 특히 성장주'처럼 대상이 실제로 섞인 라벨은 여기서 걸러지지 않아 매칭에 실패하고,
    그게 의도한 동작이다.
    """
    if not label:
        return ""
    return re.sub(r"\s+", " ", _PAREN_RE.sub("", label)).strip()


def proxy_for(label: str):
    """지수 계열 라벨이면 (심볼, 표시이름), 아니면 None."""
    return _PROXY.get(normalize_label(label))


def _has_final_consonant(word: str) -> bool:
    """마지막 글자에 받침이 있는지. 한글이 아니면 있는 것으로 본다(‘이’가 무난)."""
    if not word:
        return True
    ch = word[-1]
    if not ("가" <= ch <= "힣"):
        return True
    return (ord(ch) - 0xAC00) % 28 != 0


def _eun_neun(word: str) -> str:
    """보조사 — '지수 전반은' / '전기차는'."""
    return "은" if _has_final_consonant(word) else "는"


# 제목에 박힌 시점 표현. 미국 브리핑은 21:15 KST(=그날 아침 ET)에 나가므로 제목의 시제가
# 그 시점 기준이다 — 다음날 코스피 브리핑에서 그대로 읽으면 어긋난다(2026-09-08 사용자 지적:
# "오늘 밤 고용지표"가 월요일 아침에 오늘 밤 일처럼 읽혔다). 실측 138건 중 오늘 12·이번 주 6·
# 내일 5로 미래·현재 시점어가 대부분이고 과거형은 2건뿐이다.
_TIME_RE = re.compile(
    r"(오늘\s*밤|오늘밤|오늘|내일|모레|어제|전날|금일|이번\s*주|이번주|간밤|어젯밤|지난밤|밤사이)"
    r"\s*(새벽|아침|밤|낮|오전|오후)?\s*(은|는|이|가|의|도|에|엔|까지|부터)?\s*")
_LEAD_PUNCT_RE = re.compile(r"^[\s—·,\-–]+")


def retitle(title: str, session_label: str) -> str:
    """제목의 시점 표현을 읽는 사람 기준으로 맞춘다.

    '오늘 밤'은 그 브리핑이 가리킨 세션 **자체**라 라벨로 정확히 치환된다('간밤'·'지난 금요일').
    나머지(오늘·내일·이번 주·어제…)는 지금 프레임에서 무엇을 가리키는지 단정할 수 없으므로
    **지어내지 않고 지운다** — 어느 세션인지는 섹션 제목이 이미 말하고 있다(§0).

    지우고 나서 남는 게 없거나 너무 짧으면 원문을 그대로 둔다. 시점을 고치려다 제목을
    망가뜨리는 것이 더 나쁘다.
    """
    if not title:
        return title

    def _sub(m):
        head = m.group(1).replace(" ", "")
        return f"{session_label} " if (head == "오늘밤" and session_label) else ""

    out = _TIME_RE.sub(_sub, title)
    out = _LEAD_PUNCT_RE.sub("", re.sub(r"\s{2,}", " ", out)).strip()
    return out if len(out) >= 6 else title


def mood(marks: list) -> str:
    """지목된 종목들이 **실제로** 어떻게 움직였는지. 어제 예상과 맞았는지는 보지 않는다."""
    ups = sum(1 for m in marks if m["pct"] > 0)
    downs = sum(1 for m in marks if m["pct"] < 0)
    if len(marks) == 1:
        pct = marks[0]["pct"]
        return "올랐어요" if pct > 0 else ("내렸어요" if pct < 0 else "보합이었어요")
    if ups and downs:
        return "엇갈렸어요"
    if ups:
        return "나란히 올랐어요"
    if downs:
        return "나란히 내렸어요"
    return "보합이었어요"


def check_line(label: str, marks: list) -> str:
    """카드 한 줄. 실측 움직임만 말하고 판정하지 않는다."""
    return f"{label}{_eun_neun(label)} <b>{mood(marks)}</b>"


def build_cards(issues: list, measure, session_label: str = "") -> list:
    """이슈 리스트를 채점 카드로. `measure(ticker) -> pct | None` 를 주입받아 네트워크와 분리한다.

    - 측정 가능한 근거가 하나도 없는 카드는 통째로 뺀다(운영 규칙 0).
    - 같은 프록시·같은 방향이 다시 나오면 뒤엣것은 제목만 남긴다 — 티커 없는 '지수 전반'이
      한 브리핑에 둘 이상 들어가면 글자 하나까지 같은 결과가 반복돼 화면이 고장 난 것처럼 보인다.
    """
    cards, seen_proxy = [], {}
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        title = (issue.get("title") or "").strip()
        if not title:
            continue
        title = retitle(title, session_label)
        sides = []
        for side in ("up", "down"):
            s = issue.get(side)
            if not isinstance(s, dict):
                continue
            label = (s.get("label") or "").strip()
            tickers = [t for t in (s.get("tickers") or []) if isinstance(t, str) and t.strip()]
            proxy_sym = proxy_name = None
            if not tickers:
                hit = proxy_for(label)
                if not hit:
                    continue          # 티커도 프록시도 없으면 채점하지 않는다
                proxy_sym, proxy_name = hit
                tickers = [proxy_sym]
            marks = []
            for t in tickers:
                pct = measure(t)
                if pct is None:
                    continue          # 그 세션 봉이 없으면 이 티커는 버린다
                marks.append({
                    "ticker": t,
                    "name": proxy_name or t,
                    "pct": round(pct, 2),
                })
            if not marks:
                continue
            sides.append({
                "side": side, "label": label, "marks": marks,
                "proxy": proxy_name if proxy_sym else None,
            })
        if not sides:
            continue

        card = {"title": title, "sides": sides}
        head = sides[0]
        key = (head["marks"][0]["ticker"], head["side"]) if head.get("proxy") else None
        if key and key in seen_proxy:
            # 앞 카드와 같은 지표·같은 방향 — 결과는 한 번만 보여준다.
            card["duplicate_of"] = seen_proxy[key]
            card["sides"] = []
        else:
            if key:
                seen_proxy[key] = len(cards) + 1
            card["check_line"] = check_line(head["label"], head["marks"])
        cards.append(card)
    return cards


def bar_change_on(ticker: str, session_date, _cache={}):
    """해당 ET 세션 봉의 직전 봉 대비 등락률(%). 그 날짜 봉이 없으면 None.

    **최신 봉으로 폴백하지 않는다** — 위 모듈 주석 참조. yfinance만 쓴다(일봉에 날짜가
    붙어 있어 세션을 못 박을 수 있다). 한 섹션 안의 값이 전부 같은 소스에서 나오는 편이
    소스별 미세한 종가 차이로 카드끼리 어긋나는 것보다 낫다.
    """
    key = (ticker, str(session_date))
    if key in _cache:
        return _cache[key]
    out = None
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period="60d").dropna(subset=["Close"])
        dates = [d.strftime("%Y-%m-%d") for d in hist.index]
        target = str(session_date)
        if target in dates:
            i = dates.index(target)
            if i > 0:
                cur, prev = float(hist["Close"].iloc[i]), float(hist["Close"].iloc[i - 1])
                if prev:
                    out = (cur - prev) / prev * 100
        if out is None:
            print(f"[score_us_issues] {ticker}: {session_date} 봉 없음 — 제외", file=sys.stderr)
    except Exception as e:
        print(f"[score_us_issues] {ticker} 조회 실패: {e}", file=sys.stderr)
    _cache[key] = out
    return out


def load_us_issues(session_date) -> list:
    """그 날짜 미국 브리핑 스냅샷의 이슈. 없으면 빈 리스트(섹션 생략)."""
    snap = BRIEFINGS_DIR / str(session_date) / "us" / "analysis_snapshot.json"
    if not snap.exists():
        print(f"[score_us_issues] {snap} 없음 — 채점 건너뜀", file=sys.stderr)
        return []
    try:
        return json.loads(snap.read_text(encoding="utf-8")).get("issues") or []
    except Exception as e:
        print(f"[score_us_issues] 스냅샷 파싱 실패: {e}", file=sys.stderr)
        return []


def main():
    ap = argparse.ArgumentParser(description="직전 미국장 이슈 실측 채점")
    ap.add_argument("--date", help="코스피 브리핑 날짜(KST, 기본 오늘)")
    args = ap.parse_args()

    today = (datetime.strptime(args.date, "%Y-%m-%d").date() if args.date
             else datetime.now(KST).date())
    session = us_session_to_score(today)
    if session is None:
        # 미국이 쉬어 새 세션이 없다 — 직전 세션은 어제 브리핑에서 이미 채점했다.
        # 같은 결과를 이틀 연속 내보내지 않는다.
        print("[score_us_issues] 새로 채점할 미국 세션이 없음(직전 세션은 이미 채점됨) — 섹션 생략",
              file=sys.stderr)
        OUT_PATH.write_text(json.dumps({
            "generated_at": datetime.now(KST).isoformat(),
            "briefing_date": str(today),
            "us_session_date": None,
            "cards": [],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0

    issues = load_us_issues(session)
    label = us_session_label(today)
    cards = build_cards(issues, lambda t: bar_change_on(t, session), label)
    payload = {
        "generated_at": datetime.now(KST).isoformat(),
        "briefing_date": str(today),
        "us_session_date": str(session),
        "session_label": label,
        "cards": cards,
    }
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[score_us_issues] {session} 세션 · 이슈 {len(issues)}건 → 카드 {len(cards)}건 저장 → {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
