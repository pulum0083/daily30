# briefings.json에 쌓인 하이퍼리퀴드 기록을 시초가 갭과 대조해 지금 계산값·AI와 비교한다(수동 실행)
import json
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / "data" / "briefings.json"


def report(rows: list) -> dict:
    """신호별 {적중, 건수}. 시초가 갭이 채점된 코스피 행 중 hl이 있는 것만 센다."""
    use = [r for r in rows if r.get("type") == "kospi" and r.get("hl") and isinstance(r.get("actual_open_pct"), (int, float))]
    getters = {"prior": lambda r: r.get("prior_score"), "AI": lambda r: (r["up_pct"] - 50) if isinstance(r.get("up_pct"), (int, float)) else None}
    for coin in sorted({c for r in use for c in r["hl"]}):
        getters[coin] = lambda r, c=coin: r["hl"].get(c)
    out = {}
    for name, get in getters.items():
        z = [(get(r), r["actual_open_pct"]) for r in use if isinstance(get(r), (int, float)) and get(r) != 0]
        out[name] = {"hit": sum((v > 0) == (g >= 0) for v, g in z), "n": len(z)}
    return out


if __name__ == "__main__":
    for name, v in report(json.loads(PATH.read_text(encoding="utf-8"))["briefings"]).items():
        print(f"{name:6s} {v['hit']}/{v['n']}" + (f" {v['hit'] / v['n'] * 100:.1f}%" if v["n"] else ""))
