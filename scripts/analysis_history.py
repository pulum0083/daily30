# 분석 기록 — 시그널·섹터 반복 회피 힌트, 예측을 briefings.json에 저장, 확률 보정 힌트

from __future__ import annotations
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from claude_common import BASE_DIR, DATA_DIR, KST
from claude_prompts import SECTOR_BY_KEY, SECTOR_POOL


def extract_signal_emojis(reasons: list) -> list:
    """reasons[1:4]의 첫 토큰(이모지) 추출. reasons[0]은 항상 시장 방향 요약이라 제외."""
    if not isinstance(reasons, list) or len(reasons) < 2:
        return []
    signals = []
    for r in reasons[1:4]:
        if isinstance(r, str) and r.strip():
            first = r.strip().split(" ", 1)[0]
            signals.append(first)
    return signals


def load_signal_history(briefing_type: str) -> list:
    path = DATA_DIR / f"signal_history_{briefing_type}.json"
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("history", [])
    except Exception:
        return []


def save_signal_to_history(briefing_type: str, date_str: str, signals: list, keep: int = 10) -> None:
    """오늘 시그널을 date 기준 upsert. 최근 keep개만 보관."""
    if not signals:
        return
    path = DATA_DIR / f"signal_history_{briefing_type}.json"
    history = [h for h in load_signal_history(briefing_type) if h.get("date") != date_str]
    history.append({"date": date_str, "signals": signals})
    history.sort(key=lambda h: h.get("date", ""), reverse=True)
    history = history[:keep]
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"history": history}, f, ensure_ascii=False, indent=2)
    print(f"[call_claude] Saved signal history → {path} ({len(history)} entries)")


def load_sector_history(briefing_type: str) -> list:
    """data/sector_history_{type}.json의 history 배열을 반환. 없으면 빈 리스트."""
    path = DATA_DIR / f"sector_history_{briefing_type}.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("history", [])


def save_sector_to_history(briefing_type: str, date_str: str, sector_key: str, keep: int = 10) -> None:
    """오늘 선정 섹터를 date 기준 upsert. 최근 keep개만 보관 (최신순)."""
    path = DATA_DIR / f"sector_history_{briefing_type}.json"
    history = [h for h in load_sector_history(briefing_type) if h.get("date") != date_str]
    history.append({"date": date_str, "sector_key": sector_key})
    history.sort(key=lambda h: h.get("date", ""), reverse=True)
    history = history[:keep]
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"history": history}, f, ensure_ascii=False, indent=2)
    print(f"[call_claude] Saved sector history → {path} ({len(history)} entries)")


def build_sector_avoidance_hint(history: list, days: int = 5) -> str:
    """최근 N회 선정된 섹터를 회피 가이드 문자열로 포맷. history 비면 빈 문자열."""
    names = []
    for h in history[:days]:
        s = SECTOR_BY_KEY.get(h.get("sector_key"))
        if s:
            names.append(f"{s['emoji']} {s['name']}")
    if not names:
        return ""
    return (
        "\n## 🔄 섹터 로테이션 가이드\n"
        f"최근 다룬 섹터: {', '.join(names)}\n"
        "위 섹터는 가급적 피하고, 오늘 뉴스·시장 흐름상 가장 임팩트 큰 다른 섹터를 골라 "
        "sector_focus를 작성하세요. 단, 특정 섹터에 압도적 빅뉴스가 있으면 중복이어도 괜찮아요.\n"
    )


def pick_sector(focus: dict, recent_keys: list) -> dict:
    """Claude가 고른 sector_focus를 검증·보정한다.
    - sector_key가 풀에 없으면 최근(recent_keys) 제외하고 pool 순서상 첫 섹터로 폴백.
    - name·emoji는 항상 풀의 정본 값으로 덮어써 불일치를 막는다.
    - signal·paragraphs는 Claude 출력 유지.
    """
    focus = focus or {}
    key = focus.get("sector_key")
    if key not in SECTOR_BY_KEY:
        key = next(
            (s["key"] for s in SECTOR_POOL if s["key"] not in recent_keys),
            SECTOR_POOL[0]["key"],
        )
    elif key in recent_keys:
        # 최근 N회 중복 — 강제 교체하지 않고 경고만 남긴다 (빅뉴스 예외 허용)
        print(f"[call_claude] WARN: sector '{key}'가 최근 선정 이력과 중복 (빅뉴스 예외로 통과)")
    meta = SECTOR_BY_KEY[key]
    result = dict(focus)
    result["sector_key"] = meta["key"]
    result["sector_name"] = meta["name"]
    result["emoji"] = meta["emoji"]
    result.setdefault("signal", "")
    result.setdefault("paragraphs", [])
    return result


def build_avoidance_hint(history: list, days: int = 3) -> str:
    """최근 N일 시그널을 회피 가이드 문자열로 포맷. history 비면 빈 문자열."""
    recent = history[:days]
    if not recent:
        return ""
    lines = [
        "",
        "## [다양성 가이드 — reasons 작성 시 매우 중요]",
        "",
        "최근 브리핑에서 reasons[1]~[3]에 사용한 시그널 카테고리(이모지):",
    ]
    for h in recent:
        sigs = " ".join(h.get("signals", []))
        lines.append(f"  - {h.get('date', '?')}: {sigs}")
    lines += [
        "",
        "**오늘 reasons[1]~[3]에서는 위 카테고리를 가급적 피하고**, "
        "시스템 프롬프트의 시그널 풀에서 **다른 카테고리**를 우선 선택해라. "
        "매일 같은 이모지가 반복되면 독자가 단조롭게 느낀다.",
        "",
        "**예외 (임계치 초과 시 회피 규칙 무시)**: 아래 중 하나라도 충족하면 "
        "그 카테고리를 reasons에 반드시 포함한다. 정확성이 다양성보다 우선이다.",
        "  - SOX 또는 DRAM ETF 등락 ±3.5% 이상 → 💡 반도체",
        "  - VIX 전일 대비 ±15% 이상 또는 절대값 25 이상 → 😐/😰 VIX",
        "  - EWY 등락 ±3% 이상 또는 외국인 대규모 순매도/순매수 → 🇺🇸 외국인 수급",
        "  - WTI 유가 ±3% 이상 → 🛢️ 유가",
        "  - 10년물 금리 ±8bp 이상 → 🏦 금리",
        "  - 오늘 고영향 경제지표(CPI/NFP/FOMC 등) 발표 → 📅 경제 캘린더",
        "",
    ]
    return "\n".join(lines)


def _hl_snapshot(date_str: str) -> dict:
    """하이퍼리퀴드 값을 기록만 한다 — 프롬프트·화면에 넣지 않는다(scripts/hl_signals.py)."""
    try:
        d = json.load(open(DATA_DIR / "hl_signals.json", encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {"hl": d["moves"]} if d.get("date") == date_str and d.get("moves") else {}


def _signal_snapshot(briefing_type: str, date_str: str = "") -> dict:
    """예측 시점의 선행신호·prior를 그대로 남긴다 (사후 캘리브레이션용).

    지금까지 이 값들이 어디에도 아카이브되지 않아 **prior의 실전 성적을 추적할 방법이
    없었다.** diagnose_direction_signals.py는 yfinance로 과거를 복원하는데, 선물(NQ·ES·YM)은
    과거 시세를 정확히 되살릴 수 없어 백테스트에서 통째로 제외된다 — 그래서 정작 07:25에
    유일하게 실시간인 신호의 가중치(nq=0.3)만 피팅 없이 손으로 들어가 있었다.
    예측 행에 신호를 같이 적어두면 앞으로는 briefings.json 하나로 신호↔결과 조인이 된다.

    실패해도 조용히 빈 dict — 아카이브 때문에 발행이 막히면 안 된다.
    """
    if briefing_type == "us":
        try:
            from leading_signal import compute_prior_us
            prior = compute_prior_us(json.load(open(DATA_DIR / "latest_us.json", encoding="utf-8")))
            return {"prior_direction": prior["direction"], "prior_up_pct": prior.get("up_pct"),
                    "signals": prior["signals"]}
        except Exception as e:
            print(f"[call_claude] 선행신호 스냅샷 생략: {e}", file=sys.stderr)
            return {}
    if briefing_type != "kospi":
        return {}
    try:
        from leading_signal import compute_prior
        latest = json.load(open(DATA_DIR / "latest_kospi.json", encoding="utf-8"))
        prior = compute_prior(latest)
        sig = prior["signals"]
        return {
            "prior_direction": prior["direction"],
            "prior_score": prior["score"],
            "prior_strength": prior["strength"],
            "prior_up_pct": prior.get("up_pct"),     # score → 시초가 상승 확률 환산값(사후 검증용)
            "signals": {k: sig.get(k) for k in
                        ("sox", "nasdaq", "nq", "es", "ym", "ewy", "ewy_resid",
                         "kospi", "usdkrw", "vix")},
            **_hl_snapshot(date_str),
        }
    except Exception as e:
        print(f"[call_claude] 선행신호 스냅샷 생략: {e}", file=sys.stderr)
        return {}


def _direction_from_pct(pred: dict) -> str:
    """미국 예측엔 방향 필드가 없다 — up_pct·down_pct 큰 쪽으로 정한다(채점·화면 표기와 같은 규칙)."""
    up, down = pred.get("up_pct"), pred.get("down_pct")
    if not isinstance(up, (int, float)) or not isinstance(down, (int, float)) or up == down:
        return "중립"
    return "상승 우위" if up > down else "하락 우위"


def save_prediction_to_briefings(briefing_type: str, date_str: str, analysis: dict) -> None:
    """Append or update the prediction record in data/briefings.json for accuracy tracking."""
    path = DATA_DIR / "briefings.json"
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"[call_claude] WARNING: briefings.json 파싱 실패 ({e}), 백업 후 복구합니다.")
            backup = path.with_suffix(".json.bak")
            path.rename(backup)
            data = {"briefings": []}
    else:
        data = {"briefings": []}

    pred = analysis.get("prediction", {})
    briefings = data.setdefault("briefings", [])

    existing_idx = next(
        (i for i, b in enumerate(briefings) if b["date"] == date_str and b["type"] == briefing_type),
        None,
    )

    entry = {
        "date": date_str,
        "type": briefing_type,
        "predicted_direction": pred.get("direction") or _direction_from_pct(pred),
        "up_pct": pred.get("up_pct", 0),
        "down_pct": pred.get("down_pct", 0),
        "confidence": pred.get("confidence", 0),
        # 채점 기준 — "open"이면 시초가(§57). 분석 JSON에 찍힌 값을 그대로 옮긴다(없으면 종가 기준 기록).
        "basis": pred.get("basis"),
        "actual_direction": None,
        "actual_change_pct": None,
        "is_correct": None,
        "generated_at": datetime.now(KST).isoformat(),
        "checked_at": None,
        # 예측 시점 선행신호 스냅샷 — 사후 캘리브레이션·가중치 재피팅용
        **_signal_snapshot(briefing_type, date_str),
    }

    if entry["basis"] is None:
        del entry["basis"]
    if existing_idx is not None:
        # Preserve existing actual result (don't overwrite accuracy data on re-run)
        prev = briefings[existing_idx]
        entry["actual_direction"] = prev.get("actual_direction")
        entry["actual_change_pct"] = prev.get("actual_change_pct")
        entry["actual_open_pct"] = prev.get("actual_open_pct")
        entry["is_correct"] = prev.get("is_correct")
        # 이미 채점된 기록은 그때의 기준을 지킨다 — 재실행으로 기준이 바뀌면 채점값과 어긋난다.
        if prev.get("is_correct") is not None:
            entry.pop("basis", None)
            if prev.get("basis"):
                entry["basis"] = prev["basis"]
        entry["checked_at"] = prev.get("checked_at")
        briefings[existing_idx] = entry
    else:
        briefings.append(entry)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[call_claude] Saved prediction to briefings.json ({date_str}, {briefing_type})")


def build_calibration_hint(briefing_type: str = "kospi", min_n: int = 20) -> str:
    """지금까지의 up_pct 구간별 실제 적중 실적을 프롬프트용 표로 만든다.

    모델은 자기 성적을 한 번도 본 적이 없었다 — briefings.json은 발송 **후** 기록이고
    check_accuracy는 09:10 KST에 돌아 07:25 브리핑보다 항상 늦다. 그래서 up_pct가
    실현 분포와 무관하게 표류했다(2026-07-27 진단: 하락 예측 구간 20~39의 실제 상승률이
    41~50%로 사실상 동전던지기, 반면 40~59 구간은 74회 중 3회만 사용).

    **채점 완료된 항목만** 집계한다. 미채점을 옛 결과로 대신 채우지 않는다(§16 방지 룰).
    표본이 min_n 미만이면 빈 문자열 — 근거 없는 표를 보여주느니 안 보여준다.
    """
    path = BASE_DIR / "data" / "briefings.json"
    if not path.exists():
        return ""
    try:
        rows = json.load(open(path, encoding="utf-8")).get("briefings", [])
    except Exception:
        return ""

    from prediction_basis import stats_rows, outcome_pct
    # 코스피는 시초가 기준 기록만 센다(§57) — 종가 기준으로 낸 옛 up_pct와 섞으면 표가 뜻을 잃는다.
    scored = [
        dict(r, _out=outcome_pct(r)) for r in stats_rows(rows)
        if r.get("type") == briefing_type
        and isinstance(r.get("up_pct"), (int, float))
        and outcome_pct(r) is not None
    ]
    if len(scored) < min_n:
        return ""

    buckets = {}
    for r in scored:
        lo = int(r["up_pct"]) // 10 * 10
        buckets.setdefault(lo, []).append(r["_out"] > 0)

    lines = [
        "\n## 📊 지금까지의 up_pct 캘리브레이션 (본인 실적 — 확률 보정에 반영할 것)",
        f"채점 완료 {len(scored)}건 기준. '실제 상승률'은 그 구간으로 예측한 날 중 실제로 오른 비율이다.",
        "",
        "| up_pct 구간 | 예측 횟수 | 실제 상승률 |",
        "|---|---|---|",
    ]
    for lo in sorted(buckets):
        ups = buckets[lo]
        lines.append(f"| {lo}~{lo + 9} | {len(ups)}회 | {100 * sum(ups) / len(ups):.0f}% |")

    overall_up = 100 * sum(1 for r in scored if r["_out"] > 0) / len(scored)
    lines += [
        "",
        f"- 전체 기간 실제 상승 비율(기저율)은 **{overall_up:.0f}%** 다.",
        "- **읽는 법**: 어떤 구간의 '실제 상승률'이 그 구간 값과 크게 어긋나면 그 구간을 잘못 쓰고 있다는 뜻이다."
        " 예를 들어 up_pct 30대로 낸 날의 실제 상승률이 40%를 넘는다면 하락 확신이 과했다는 신호다.",
        "- 이 표는 과거 실적일 뿐 오늘의 정답이 아니다. 오늘 선행신호가 명확하면 그쪽을 따르고,"
        " **애매할 때 기저율 쪽으로 당기는 기준**으로만 쓴다.",
    ]
    return "\n".join(lines) + "\n"
