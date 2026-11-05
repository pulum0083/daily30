# 예측 성적표(/accuracy/)·방법론(/methodology/) 페이지 컨텍스트를 채점 기록과 백테스트 파일에서 만드는 모듈
"""
2026-11-05 애드센스 '가치가 별로 없는 콘텐츠' 대응(SERVICE_RULES §80). 다른 곳에 없는 자료 —
매일 채점한 예측 기록과 직접 돌린 백테스트 — 를 사람이 읽는 글로 공개한다.

숫자는 전부 파일에서 온다(§0·§20). 코드·템플릿에 숫자를 박지 않는다.
  · 성적표   data/briefings.json (check_accuracy가 매일 09:10 채점)
  · 방법론   scripts/config/kospi_open_prior_backtest.json (fit_open_gap_prior.py --write)
             scripts/config/us_close_prior.json · monthly_ma5*_backtest.json · nasdaq_overheat_backtest.json
             leading_signal.py의 가중치·확률식
파일이 없거나 모양이 다르면 그 칸은 비운다. 성적표는 채점 기록이 하나도 없으면 페이지를 쓰지 않는다.
"""
import collections
import json
from datetime import date
from pathlib import Path

try:
    from scripts.prediction_basis import is_open_basis
    from scripts import leading_signal as ls
except ImportError:
    from prediction_basis import is_open_basis
    import leading_signal as ls

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path(__file__).resolve().parent / "config"
WD = "월화수목금토일"


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _md(d: str) -> str:
    return f"{int(d[5:7])}/{int(d[8:10])}"


def _mdl(d: str) -> str:
    return f"{int(d[5:7])}월 {int(d[8:10])}일"


def _side(row: dict) -> str:
    p = row.get("predicted_direction") or ""
    return "up" if "상승" in p else "dn" if "하락" in p else "nt"


def _big_pct(row: dict) -> int:
    return max(row.get("up_pct") or 0, row.get("down_pct") or 0)


def _stat(rows: list) -> dict:
    n = len(rows)
    if not n:
        return {}
    hit = sum(1 for b in rows if b["is_correct"])
    up = sum(1 for b in rows if b.get("actual_direction") == "상승")
    return {"n": n, "hit": hit, "pct": round(hit / n * 100, 1), "base_n": up, "base": round(up / n * 100, 1),
            "edge": round((hit - up) / n * 100, 1), "from": _md(rows[0]["date"]), "to": _md(rows[-1]["date"])}


_BUCKETS = (("50~59%", 0, 60), ("60~69%", 60, 70), ("70~79%", 70, 80), ("80% 이상", 80, 101))


def _calib(rows: list) -> list:
    out = []
    for label, lo, hi in _BUCKETS:
        xs = [b for b in rows if lo <= _big_pct(b) < hi]
        if xs:
            h = sum(1 for b in xs if b["is_correct"])
            out.append({"label": label, "n": len(xs), "hit": h, "pct": round(h / len(xs) * 100)})
    return out


def _monthly(rows: list) -> list:
    m = collections.OrderedDict()
    for b in rows:
        k = b["date"][:7]
        m.setdefault(k, [0, 0, 0])
        m[k][0] += 1
        m[k][1] += 1 if b["is_correct"] else 0
        m[k][2] += 1 if b.get("actual_direction") == "상승" else 0
    return [{"label": f"{int(k[5:])}월", "n": n, "hit": h, "pct": round(h / n * 100), "base": round(up / n * 100)}
            for k, (n, h, up) in m.items()]


def _scored(rows: list, cond) -> list:
    return sorted([b for b in rows if cond(b) and b.get("is_correct") is not None], key=lambda b: b["date"])


def build_accuracy(briefings: list) -> dict:
    """성적표 컨텍스트. 채점된 기록이 하나도 없으면 빈 dict."""
    ko = _scored(briefings, lambda b: b.get("type") == "kospi" and is_open_basis(b))
    us = _scored(briefings, lambda b: b.get("type") == "us")
    legacy = _scored(briefings, lambda b: b.get("type") == "kospi" and not is_open_basis(b))
    if not ko and not us:
        return {}
    days = []
    for b in reversed(ko):
        g = b.get("actual_open_pct")
        days.append({"date": _md(b["date"]), "wd": WD[date.fromisoformat(b["date"]).weekday()],
                     "side": _side(b), "pct": _big_pct(b), "ok": bool(b["is_correct"]),
                     "gap": g if isinstance(g, (int, float)) else None})
    backfilled = [b["date"] for b in us if b.get("backfilled")]
    split = ((_load(CONFIG_DIR / "kospi_open_prior_backtest.json") or {}).get("legacy_split") or {})
    last = max([b["date"] for b in ko + us])
    return {
        "asof": _mdl(last),
        "kospi": {"stat": _stat(ko), "days": days, "calib": _calib(ko),
                  "start": _mdl(ko[0]["date"]) if ko else ""},
        "us": {"stat": _stat(us), "monthly": _monthly(us), "calib": _calib(us),
               "backfilled": {"n": len(backfilled), "from": _md(backfilled[0]), "to": _md(backfilled[-1])} if backfilled else None},
        "legacy": {"stat": _stat(legacy), "split": split if split.get("days") else None},
    }


def _band_label(b: dict) -> str:
    f = lambda v: f"{v:+.1f}%".replace("+0.0%", "0.0%")
    if b.get("lo") is None:
        return f"{f(b['hi'])} 미만"
    if b.get("hi") is None:
        return f"{f(b['lo'])} 이상"
    return f"{f(b['lo'])} ~ {f(b['hi'])}"


def build_methodology() -> dict:
    """방법론 컨텍스트. 파일이 없는 항목은 None — 템플릿이 그 칸을 뺀다."""
    kp = _load(CONFIG_DIR / "kospi_open_prior_backtest.json")
    usp = _load(CONFIG_DIR / "us_close_prior.json")
    ma5 = _load(CONFIG_DIR / "monthly_ma5_backtest.json")
    ma5us = _load(CONFIG_DIR / "monthly_ma5_us_backtest.json")
    nq = _load(CONFIG_DIR / "nasdaq_overheat_backtest.json")
    w = ls.SIGNAL_WEIGHTS
    weights = [
        ("필라델피아 반도체(SOX)", "직전 미국장 등락 — 삼성전자·SK하이닉스와 가장 가깝게 움직여요", w.get("sox")),
        ("나스닥", "직전 미국장 등락", w.get("nasdaq")),
        ("나스닥100 선물", "07:25 현재 등락", w.get("nq")),
        ("한국 ETF(EWY)", "미국에 상장된 한국 ETF 등락에서 전날 코스피 움직임을 뺀 나머지", w.get("ewy")),
        ("VIX", "미국 변동성 지수 — 오르면 감점", w.get("vix")),
    ]

    def ma5_pair(d, key):
        try:
            h = d["horizons"]["12"]
            return {"sig": h["signal"], "base": h["base"], "period": d.get("signal_period", ""), "universe": d.get("universe", "")}
        except Exception:
            return None

    return {
        "kospi": kp if kp and kp.get("days") else None,
        "weights": [{"name": n, "what": t, "w": v} for n, t, v in weights if v is not None],
        "prob_a": ls.PROB_A, "prob_b": ls.PROB_B, "tol": ls.UP_PCT_TOLERANCE,
        "side_up": ls.SIDE_UP, "side_dn": ls.SIDE_DN,
        "us": {**usp, "bands": [{"label": _band_label(b), "days": b["days"], "up": b["up_pct"]} for b in usp.get("bands", [])],
               "from_label": f"{usp['data_from'][:4]}년 {int(usp['data_from'][5:7])}월",
               "to_label": f"{usp['data_through'][:4]}년 {int(usp['data_through'][5:7])}월"} if usp and usp.get("bands") else None,
        "ma5": ma5_pair(ma5, "kr") if ma5 else None,
        "ma5us": ma5_pair(ma5us, "us") if ma5us else None,
        "nq": nq if nq and nq.get("warn") else None,
    }
