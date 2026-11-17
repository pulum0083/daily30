#!/usr/bin/env python3
# Claude 분석 결과(analysis_*.json)의 수치·본문을 실측·규칙으로 검증·교정하는 발행 게이트
"""
call_claude → [validate_analysis] → generate_html 사이에서 동작.

- 교정 가능: analysis_*.json 제자리 교정 후 저장 (exit 0)
- 치명적/교정 불가: exit 1 + 관리자 텔레그램 알림 (발행 중단)

설계: docs/superpowers/specs/2026-06-02-analysis-validation-gate-design.md
"""
import argparse
import copy
import html
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

try:
    import scripts.superlative_subject as _ss
except ImportError:
    import superlative_subject as _ss

sys.path.insert(0, str(Path(__file__).resolve().parent))
# 역할별 모듈로 나눈 정의 — 원래 이름(validate_analysis.X)으로도 그대로 읽힌다.
from gate_text import (  # noqa: F401
    SCALAR_PROSE, EXCLUDED_FIELDS, FX_MIN, FX_MAX, INDEX_PCT_MAX, REASONS_MIN,
    GYEONG_RE, HWANYUL_CTX_RE, WON_NUM_RE, INDEX_CTX_RE, PCT_NUM_RE, parse_price,
    strip_tags, find_forbidden, is_contradicted, _CHANGE_CTX_RE, _PCT_RE, _extract_change_claims,
    _NON_TICKER, _PROSE_FETCH_ALIAS, _US_TICKER_RE, _UP_WORDS_RE, _DOWN_WORDS_RE, _sentence_split,
    _join_sentences, _direction_contradicts, _walk_strings, _collect_strings, _filter_list_prose,
)
from gate_realdata import (  # noqa: F401
    _closes_to_realdata, _closes_from_toss_candles, _us_live_price, _fetch_us_realdata, _pin_session_date, _drop_rows_at_pin,
    _toss_candle_date, _naver_row_date, _fetch_kospi_realdata,
)
from gate_prose import (  # noqa: F401
    validate_prose_nonpick_stocks, validate_todays_view_recap, validate_todays_view_outlook, _us_figure_stale, _INDEX_NAME_SYMBOL, _PCT_NEAR_RE,
    _index_figures, _index_figure_wrong, validate_key_drivers, fix_overnight_labels, _ROLE_SUFFIX, fix_officeholder_names,
)
from gate_superlative import (  # noqa: F401
    _SUPERLATIVE_HIGH_RE, _SUPERLATIVE_LOW_RE, _SUPERLATIVE_LIST_FIELDS, _index_extremes, find_superlative_violations, _superlative_texts,
    clamp_prediction_to_prior, clamp_us_prediction_to_prior, validate_index_superlatives,
)
from gate_events import (  # noqa: F401
    _PREVIEW_TENSE_RE, _EVENT_ACRONYM_RE, _event_keywords, find_event_tense_violations, validate_event_tense, fix_event_day_words,
    _NO_PREMARKET_INDEX, _SESSION_WORDS, _SENT_SPLIT, find_session_mislabels, _PREMARKET_PHRASE, _PREMARKET_DROP,
    _ISSUE_BODY_MAX_SENT, trim_issue_bodies, _ISSUE_FALL_NOW, _ISSUE_RISE_NOW, _ISSUE_MIN_MOVE, _premarket_opposite,
    fix_issue_premarket_contradictions, _ISSUE_ROSE_PAST, _ISSUE_FELL_PAST, _prev_us_session_str, drop_stale_earnings_issues, fix_issue_side_tickers,
    fix_session_mislabels, limit_data_issues,
)
from gate_close import (  # noqa: F401
    _fetch_kospi_index_levels, inject_kospi_index_levels, _extract_eok_values, _SUPPLY_ACTORS, _SUPPLY_AMOUNT_RE, _SUPPLY_SKIP,
    _SUPPLY_SKIP_MORNING, _fmt_eok, _amount_value, fix_supply_amounts, _ALL_STOCKS_RE, _ALL_SECTORS_RE,
    fix_all_claims, _check_supply_scale,
)
from gate_format import (  # noqa: F401
    FORMAT_BODY_FIELDS, FORMAT_FALLBACK, _TITLE_PCT_RE, _AMOUNT_NO_COMMA_RE, fix_amount_commas, fix_view_title_figures,
    fix_format_payload_mismatch,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

LATEST_FILE = {
    "kospi": "latest_kospi.json",
    "us": "latest_us.json",
    "kospi-close": "latest_kospi_close.json",
}


# ── 픽 외 종목 산문 검증 ────────────────────────────────────────────────────────


# ── 픽 종목 실측 주입 (yfinance 직접 fetch) ───────────────────────────────────
# Claude는 후보 풀과 무관하게 종목을 자유 선택하므로, 사전 수집된 candidate가
# 대부분 비어 있다. 픽된 종목의 ticker를 직접 fetch해 price·change·MA·sparkline을
# 실측으로 덮어쓰고, generate_html이 읽는 candidate 리스트에도 주입한다.


# ── 검증 본체 ─────────────────────────────────────────────────────────────────
def validate(analysis, latest, btype):
    """analysis를 검증·교정한다.

    Returns dict: {analysis(교정본), corrections[], warnings[], blocks[]}
    blocks 비어있지 않으면 발행 차단.
    """
    a = copy.deepcopy(analysis)
    corrections, warnings, blocks = [], [], []

    # 1) 구조 필드 — 예측형 브리핑(kospi)만. 마감(kospi-close)은 예측 필드가 없는 시황 요약이라 제외.
    #    us는 이슈 중심 구조로 재정의되며 prediction 필드가 없어졌으므로(예측 정확도 채점 탈퇴) 제외.
    if btype == "kospi":
        pred = a.get("prediction") or {}
        up = pred.get("up_pct")
        if not isinstance(up, (int, float)) or isinstance(up, bool) or not (0 <= up <= 100):
            blocks.append(f"prediction.up_pct 비정상: {up!r}")
        if not pred.get("direction"):
            blocks.append("prediction.direction 누락")

    # 1-a) 형식↔본문 불일치 — 빈 껍데기 섹션 발행 차단. 다른 교정보다 먼저 형식을 확정해야
    #      이후 단계가 실제로 렌더될 필드를 대상으로 검사한다.
    fix_format_payload_mismatch(a, corrections, warnings, blocks)

    # 1-b) 위로 한 줄 — 순수 정서적 문구만 허용. 숫자·%·종목 티커가 섞이면 통째로 제거.
    cl = a.get("comfort_line")
    if isinstance(cl, str) and cl.strip():
        if re.search(r"\d|%|[A-Z]{2,5}\b", strip_tags(cl)):
            warnings.append(f"comfort_line 제거 (숫자·티커 포함): {cl!r}")
            a["comfort_line"] = ""

    # 2-c) 산문 교차검증 — 픽 외 개별 종목 방향 모순 (us 전용)
    if btype == "us":
        validate_prose_nonpick_stocks(a, btype, corrections, warnings)

    # 2-d) 오늘의 관점 검증 (kospi 전용)
    validate_todays_view_recap(a, btype, corrections, warnings)
    validate_todays_view_outlook(a, btype, corrections, warnings)
    validate_key_drivers(a, btype, corrections, warnings)
    fix_view_title_figures(a, btype, corrections)

    # 2-d-2) 이슈 세션 오표기 — 프리장 미거래 지수를 '프리마켓에서'로 서술 (us 전용)
    if btype == "us":
        fix_session_mislabels(a, corrections)      # 같은 절에 지수+프리마켓이면 교정, 남는 건 아래에서 경고
        limit_data_issues(a, corrections)          # 시장 데이터형 이슈는 하루 1개까지
        drop_stale_earnings_issues(a, corrections) # 실적 이슈의 티커가 최근 발표가 아니면 뺀다(2026-11-10)
        trim_issue_bodies(a, corrections)          # 이슈 본문은 한 문장
        fix_issue_premarket_contradictions(a, latest, corrections)   # 지금 일처럼 쓴 방향이 프리마켓 실측과 반대면 교정
        _sess = _prev_us_session_str(a)
        if _sess:
            fix_issue_side_tickers(a, latest, corrections, _sess)    # 지난 장 일로 쓴 칩을 직전 정규장 실측과 대조
        for hit in find_session_mislabels(a.get("issues")):
            warnings.append(
                f"세션 오표기 의심 — {hit['subject']}는 프리장에 거래되지 않는다"
                f"(그 수치는 직전 정규장 값): {hit['sentence'][:80]}"
            )

    # 2-d-3) 지수 '사상 최고/최저' 정성 주장 실측 대조 (전 타입)
    validate_index_superlatives(a, corrections, warnings, blocks)

    # 2-d-2) 이미 끝난 경제 이벤트를 예고형으로 쓴 서술 차단 (§29)
    validate_event_tense(a, (latest or {}).get("economic_calendar"), corrections, warnings, blocks)
    fix_event_day_words(a, (latest or {}).get("economic_calendar"), corrections)   # '오늘 새벽 FOMC' → 실제 KST 날짜

    # 2-e) '간밤' 표기 교정 — 월요일·휴일 다음날 (kospi 전용)
    fix_overnight_labels(a, btype, corrections)

    # 2-f) 현직 인물 교정 — 전임 연준 의장 이름을 현직 역할로 쓴 표현 (전 타입, §64)
    fix_officeholder_names(a, corrections, warnings)

    # 2-g) 제목·보조 문장 금액 쉼표 (전 타입)
    fix_amount_commas(a, corrections)

    # 3) 계층 2 — 리스트형 본문
    if isinstance(a.get("reasons"), list):
        kept, _ = _filter_list_prose(a["reasons"], "reasons", corrections)
        a["reasons"] = kept
        if len(kept) < REASONS_MIN:
            blocks.append(f"reasons가 {len(kept)}개로 과소 (최소 {REASONS_MIN})")
    if isinstance(a.get("brief_lines"), list):   # 마감 세 줄 요약 — 위반 줄만 뺀다
        a["brief_lines"], _ = _filter_list_prose(a["brief_lines"], "brief_lines", corrections)
    if isinstance(a.get("watch_items"), list):
        a["watch_items"], _ = _filter_list_prose(a["watch_items"], "watch_items", corrections)
    if btype == "kospi":
        inject_kospi_index_levels(a, corrections, warnings)
    sf = a.get("sector_focus")
    if isinstance(sf, dict):
        if isinstance(sf.get("paragraphs"), list):
            kept, _ = _filter_list_prose(sf["paragraphs"], "sector_focus.paragraphs", corrections)
            sf["paragraphs"] = kept
            if not kept:
                blocks.append("sector_focus.paragraphs 전부 제거됨")
        # signal 필드: 30자 이내 한 문장 — 금지 패턴 감지 시 경고만(필수 필드라 제거 불가)
        if isinstance(sf.get("signal"), str):
            bad = find_forbidden(sf["signal"])
            if bad:
                warnings.append(f"sector_focus.signal 금지 패턴 감지 (수동 확인 필요): {bad}")

    # sector_semicon (us 전용) — paragraphs·signal 검증
    ss = a.get("sector_semicon")
    if isinstance(ss, dict):
        if isinstance(ss.get("paragraphs"), list):
            kept, _ = _filter_list_prose(ss["paragraphs"], "sector_semicon.paragraphs", corrections)
            ss["paragraphs"] = kept
        if isinstance(ss.get("signal"), str):
            bad = find_forbidden(ss["signal"])
            if bad:
                warnings.append(f"sector_semicon.signal 금지 패턴 감지 (수동 확인 필요): {bad}")

    # 3-b) telegram_signals — 텔레그램 직송 문자열이므로 모든 타입에서 검증
    if isinstance(a.get("telegram_signals"), list):
        a["telegram_signals"], _ = _filter_list_prose(
            a["telegram_signals"], "telegram_signals", corrections
        )

    # 4) 계층 2 — 스칼라 본문 (금지 문장 제거 후 계속 발행)
    for fld in SCALAR_PROSE.get(btype, []):
        if fld in EXCLUDED_FIELDS:
            continue
        text = a.get(fld)
        if not isinstance(text, str) or not text:
            continue
        bad = find_forbidden(text)
        if not bad:
            continue
        # 금지 패턴을 포함한 문장만 제거
        import re as _re
        sentences = _re.split(r'(?<=[.!?요])\s+', text)
        kept = [s for s in sentences if not find_forbidden(s)]
        if kept:
            a[fld] = " ".join(kept)
            corrections.append(f"본문 '{fld}' 금지 문장 제거: {bad}")
        else:
            # 전체가 금지 패턴인 경우 필드 삭제
            a[fld] = ""
            warnings.append(f"본문 '{fld}' 전체 제거 (금지 패턴 {bad})")

    # 5) 수급 금액 ↔ 실측. 코스피 아침은 전 거래일 정규장 확정 수급이 실측이다(2026-11-10 '백만원' 실사고).
    if btype == "kospi":
        fix_supply_amounts(a, latest, corrections, warnings, skip=_SUPPLY_SKIP_MORNING)

    # 수급 수치 스케일 크로스체크 (kospi-close only)
    if btype == "kospi-close":
        fix_supply_amounts(a, latest, corrections, warnings)   # 본문 수급 금액 ↔ 실측(15:40 확정)
        fix_all_claims(a, latest, corrections)                 # '전종목·전 섹터' ↔ 시장 폭·섹터 실측
        _check_supply_scale(a, latest, warnings)

    return {"analysis": a, "corrections": corrections, "warnings": warnings, "blocks": blocks}


# ── 관리자 알림 ───────────────────────────────────────────────────────────────
def build_block_alert(btype, blocks):
    """차단 알림 메시지. 인용하는 블록 텍스트는 브리핑 산문(<b> 태그·부등호 포함)이라
    반드시 이스케이프한다 — 안 하면 parse_mode=HTML이 400을 뱉고, 하필 가장 알아야 할
    차단 상황에서만 알림이 사라진다(2026-08-24 실사고)."""
    body = "\n".join(f"• {html.escape(str(b))}" for b in blocks)
    return f"🚫 <b>{html.escape(btype)}</b> 브리핑 발행 차단\n{body}"


def send_admin_alert(message):
    """차단 시 관리자 텔레그램으로 알림. 키 미설정이면 조용히 건너뜀(차단은 유지).

    **HTML 실패 시 평문으로 한 번 더 보낸다.** 이 알림의 본문에는 모델이 쓴 산문이
    그대로 들어가는데, 그 산문에 <b> 같은 태그가 섞이고 길이 제한으로 잘리면
    parse_mode=HTML이 400을 뱉는다 — 실제로 2026-08-24·08-26 발행 차단 알림이 둘 다
    이 이유로 실패했고, 그래서 "브리핑이 안 나갔다"는 사실을 아무도 몰랐다.
    가장 중요한 알림이 자기 서식 때문에 죽는 구조라 서식을 포기하더라도 반드시 보낸다.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_ADMIN_CHAT_ID")
    if not token or not chat_id:
        print("[validate] 관리자 알림 키 미설정 — 알림 건너뜀 (차단은 유지)", file=sys.stderr)
        return

    def _post(text, parse_mode):
        payload = {"chat_id": chat_id, "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=urllib.parse.urlencode(payload).encode())
        urllib.request.urlopen(req, timeout=10)

    try:
        _post(message, "HTML")
        print("[validate] 관리자 알림 발송 완료", file=sys.stderr)
        return
    except Exception as e:
        detail = ""
        try:                          # HTTPError면 텔레그램이 사유를 본문에 준다
            detail = f" — {e.read().decode('utf-8', 'replace')[:300]}"
        except Exception:
            pass
        print(f"[validate] 관리자 알림 HTML 실패({e}){detail} — 평문으로 재시도",
              file=sys.stderr)

    try:
        _post(strip_tags(message), None)
        print("[validate] 관리자 알림 발송 완료(평문)", file=sys.stderr)
    except Exception as e:
        print(f"[validate] 관리자 알림 실패: {e}", file=sys.stderr)


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="분석 결과 검증·교정 게이트")
    parser.add_argument("--type", choices=["kospi", "us", "kospi-close"], required=True)
    args = parser.parse_args()
    btype = args.type

    analysis_path = DATA_DIR / f"analysis_{btype}.json"
    latest_path = DATA_DIR / LATEST_FILE[btype]

    if not analysis_path.exists():
        print(f"[validate] {analysis_path} 없음 — 검증 건너뜀", file=sys.stderr)
        return 0
    analysis = load_json(analysis_path)
    latest = load_json(latest_path) if latest_path.exists() else {}

    result = validate(analysis, latest, btype)

    # 4-b) 선행신호 prior 오버라이드 (kospi 전용) — strong prior가 LLM 방향과 정반대면 재생성
    if btype == "kospi":
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from leading_signal import (compute_prior, prior_contradicts_direction,
                                    direction_breaks_prior, prior_side)
        prior = compute_prior(latest)
        llm_dir = (result["analysis"].get("prediction") or {}).get("direction", "")
        # prior 확률이 한쪽(55%↑/45%↓)을 가리키는데 AI 방향이 다르면 그 방향으로 다시 쓰게 한다(§57).
        # strong prior와 정반대인 경우(옛 조건)는 이 조건에 포함되지만, 확률을 못 낸 날을 위해 함께 둔다.
        forced_dir = prior_side(prior) or prior["direction"]
        if direction_breaks_prior(prior, llm_dir) or prior_contradicts_direction(prior, llm_dir):
            print(f"[validate] 🧭 선행신호 오버라이드: LLM '{llm_dir}' ↔ prior '{forced_dir}' "
                  f"(시초가 상승 확률 {prior.get('up_pct')}%, score {prior['score']}) — {forced_dir}로 재생성", file=sys.stderr)
            try:
                regen = subprocess.run(
                    [sys.executable, str(Path(__file__).resolve().parent / "call_claude.py"),
                     "--type", "kospi", "--no-html", "--force-direction", forced_dir],
                    timeout=300,
                )
            except subprocess.TimeoutExpired:
                send_admin_alert("⚠️ kospi 방향 오버라이드 재생성 타임아웃(5분) — LLM 방향 유지 발행")
                regen = None
            if regen and regen.returncode == 0:
                analysis = load_json(analysis_path)
                result = validate(analysis, latest, btype)
                new_dir = (result["analysis"].get("prediction") or {}).get("direction", "")
                if forced_dir not in new_dir:
                    send_admin_alert(f"⚠️ kospi 방향 오버라이드 재생성 뒤에도 방향이 '{new_dir}' — prior {forced_dir}와 다른 채 발행")
                send_admin_alert(
                    f"🧭 <b>kospi</b> 방향 오버라이드\n"
                    f"LLM: {llm_dir} → prior: {forced_dir} (시초가 상승 확률 {prior.get('up_pct')}%, 강도 {prior['strength']}, score {prior['score']})\n"
                    f"SOX {prior['signals'].get('sox')} / EWY {prior['signals'].get('ewy')} / VIX {prior['signals'].get('vix')}"
                )
            elif regen is not None:
                send_admin_alert(f"⚠️ kospi 방향 오버라이드 재생성 실패(rc={regen.returncode}) — LLM 방향 {llm_dir} 유지 발행")

    # 4-c) up_pct를 prior 확률 ±10%p 안으로 당긴다(kospi 전용, §57). 방향 재생성이 실패해 AI 방향이 남았으면
    #      숫자만 고치지 않는다 — 방향과 확률이 서로 어긋난 채 나가느니 AI 원본을 그대로 두고 관리자에게 알린다(위 알림).
    if btype == "kospi":
        clamp_prediction_to_prior(result["analysis"], prior, result["corrections"])
    elif btype == "us":
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from leading_signal import compute_prior_us
        clamp_us_prediction_to_prior(result["analysis"], compute_prior_us(latest), result["corrections"])

    for w in result["warnings"]:
        print(f"[validate] ⚠️  {w}")
    for c in result["corrections"]:
        print(f"[validate] 🔧 교정: {c}")

    if result["blocks"]:
        summary = "\n".join(f"  • {b}" for b in result["blocks"])
        print(f"[validate] 🚫 발행 차단 — 치명적 오류:\n{summary}", file=sys.stderr)
        send_admin_alert(build_block_alert(btype, result["blocks"]))
        return 1

    # 교정본 저장 (교정 사항이 있을 때만 덮어씀)
    if result["corrections"]:
        with open(analysis_path, "w", encoding="utf-8") as f:
            json.dump(result["analysis"], f, ensure_ascii=False, indent=2)
        print(f"[validate] ✓ {len(result['corrections'])}건 교정 후 저장 → {analysis_path}")
    else:
        print("[validate] ✓ 검증 통과 — 교정 없음")
    return 0


if __name__ == "__main__":
    sys.exit(main())
