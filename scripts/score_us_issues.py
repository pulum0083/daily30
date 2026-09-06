#!/usr/bin/env python3
# 어제 미국 브리핑이 내건 이슈의 결과를 그 세션 실측으로 채점해 코스피 아침 브리핑에 넘기는 스크립트
"""
Usage:
    python3 scripts/score_us_issues.py [--date YYYY-MM-DD]

출력: data/us_issue_results.json

미국 브리핑(21:15 KST)의 이슈 카드는 산문이 아니라 up/down × {label, tickers} 구조라
방향 주장이 검증 가능한 형태로 스냅샷에 남아 있다. 그 세션이 끝난 뒤(미국 마감 05~06시 KST)
코스피 아침 브리핑(07:25)에서 실측으로 채점한다.

**숫자·판정·문구가 전부 결정론이다. LLM이 개입하지 않는다.**

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
from session_label import prev_us_session, us_session_label  # noqa: E402

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


def _i_ga(word: str) -> str:
    """주격 조사 — '지수 전반이' / '전기차가'."""
    return "이" if _has_final_consonant(word) else "가"


def fmt_pct(pct: float) -> str:
    """등락률 표기. 마이너스는 하이픈이 아니라 −(U+2212)로 — 화면 폭이 흔들리지 않는다."""
    return ("+" if pct >= 0 else "−") + f"{abs(pct):.2f}%"


def verdict(total: int, hits: int) -> tuple[str, str]:
    """판정 배지 (클래스, 문구). 적중 개수를 세어 만든다."""
    if hits == total:
        return ("all", "적중" if total == 1 else f"{total}건 전부")
    if hits == 0:
        return ("none", "빗나감")
    return ("part", f"{total}중 {hits} 적중")


def result_line(label: str, want_up: bool, marks: list) -> str:
    """결과 한 줄. LLM 문장이 아니라 실측에서 조립한 템플릿이다."""
    hits = [m for m in marks if m["hit"]]
    if len(marks) == 1:
        m = marks[0]
        pct = m["pct"]
        actual = "올랐어요" if pct > 0 else ("내렸어요" if pct < 0 else "보합이었어요")
        line = f'{label}{_i_ga(label)} <b>{actual}</b> · {m["name"]} {fmt_pct(pct)}'
        return line + (" — 예상과 반대예요" if not hits else "")
    moved = "올랐어요" if want_up else "내렸어요"
    avg = sum(m["pct"] for m in marks) / len(marks)
    return (f'{label} {len(marks)}종목 중 <b>{len(hits)}종목이 {moved}</b> '
            f'· 평균 {fmt_pct(avg)}')


def build_cards(issues: list, measure) -> list:
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
                    "hit": (pct > 0) if side == "up" else (pct < 0),
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
            total = sum(len(s["marks"]) for s in sides)
            hits = sum(1 for s in sides for m in s["marks"] if m["hit"])
            card["verdict_class"], card["verdict_text"] = verdict(total, hits)
            card["result_line"] = result_line(head["label"], head["side"] == "up", head["marks"])
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
    session = prev_us_session(today)
    if session is None:
        print("[score_us_issues] 직전 미국장을 찾지 못함 — 건너뜀", file=sys.stderr)
        return 0

    issues = load_us_issues(session)
    cards = build_cards(issues, lambda t: bar_change_on(t, session))
    payload = {
        "generated_at": datetime.now(KST).isoformat(),
        "briefing_date": str(today),
        "us_session_date": str(session),
        "session_label": us_session_label(today),
        "cards": cards,
    }
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[score_us_issues] {session} 세션 · 이슈 {len(issues)}건 → 카드 {len(cards)}건 저장 → {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
