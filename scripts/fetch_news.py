#!/usr/bin/env python3
# Gemini Google Search grounding으로 최신 시장 뉴스를 수집·요약하는 스크립트

"""
흐름:
  Gemini 2.5 Flash (google_search grounding) → 그 시점 Google 검색 기반 최신 뉴스 수집·요약
  → data/news_summary_{type}.json 저장

Usage:
    python3 scripts/fetch_news.py --type kospi
    python3 scripts/fetch_news.py --type us
    python3 scripts/fetch_news.py --type kospi-close
"""
from __future__ import annotations  # `X | None` 어노테이션을 구버전 파이썬(로컬 3.9)에서도 허용

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import news_sources as ns
import superlative_subject as _ss

sys.path.insert(0, str(Path(__file__).resolve().parent))
# 역할별 모듈로 나눈 정의 — 원래 이름(fetch_news.X)으로도 그대로 읽힌다.
from news_common import (  # noqa: F401
    BASE_DIR, DATA_DIR, KST, get_gemini_api_key, EMPTY_NEWS,
)
from news_prompts import (  # noqa: F401
    _WEEKDAY_KO, _kospi_session_window, KOSPI_PROMPT, KOSPI_CLOSE_PROMPT, US_PROMPT, PROMPT_MAP,
)
from news_gate_grounding import (  # noqa: F401
    _SEARCH_FAILURE_RE, _PLACEHOLDER_ENTITY_RE, _load_today_calendar, _TEXT_KEY_HINTS, _NON_TEXT_KEYS, _ISO_DATE_RE,
    _item_text, _normalize_news_items, _NO_EVENT_CLAIM_RE, _grounding_failure_signals, _count_grounding_chunks, _is_grounding_failure,
    _drop_placeholder_entities, _SLOT_ECHO_RE, _drop_prompt_slot_echoes, _drop_search_failure_notes,
)
from news_gate_reality import (  # noqa: F401
    _DATE_PREFIX_RE, _parse_iso_date, _UP_WORDS, _DOWN_WORDS, _REALITY_SUBJECTS, _INDEX_SYMBOLS,
    _HIGH_SUPERLATIVE_RE, _LOW_SUPERLATIVE_RE, _INDEX_LEVEL_RE, _PRICE_LEVEL_RE, _claim_direction, _superlative_claim_wrong,
    _level_claim_wrong, _drop_reality_contradictions, _fetch_reality_snapshot, _catalyst_cutoff, _filter_stale_catalysts,
)
from news_gate_history import (  # noqa: F401
    _load_prev_catalysts, _GENERIC_UPPER, _norm_for_match, _char_ngrams, _jaccard, _distinctive_entities,
    _is_cross_day_recap, _drop_prev_run_echoes, _SELF_LABELED_ECHO_RE, _drop_cross_day_recaps, _history_path, _load_stale_catalysts,
    _append_catalyst_history,
)
from news_gate_earnings import (  # noqa: F401
    _EARNINGS_KEYWORDS, _is_earnings_catalyst, _parse_tickers, _earnings_age_cache, _days_since_last_earnings, _NAME_TO_TICKER,
    _NAME_TO_TICKER_NORM, _resolve_company_tickers, _ARROW_RE, _PAREN_TICKER_RE, _earnings_subject_tickers, _drop_stale_earnings,
    _PREVIEW_RE, _release_cache, _last_earnings_release, _drop_preview_after_release,
)
from news_rss import (  # noqa: F401
    _dedupe_articles, _articles_prompt_block, _PCT_RE, _article_blob, _unsourced_claim, _resolve_selection,
    _attach_verified_sources, _US_RSS_QUERIES, RSS_SELECT_MAX, RECENT_HOURS, _RSS_SELECT_PROMPT, _us_news_session,
    _is_recent, _verify_articles, fetch_and_summarize_rss,
)

DATA_DIR.mkdir(exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# 1단계(검색)와 2단계(정형화)는 요구 능력이 다르다 — 검색은 도구 호출 판단이 필요하고
# 정형화는 주어진 텍스트를 옮겨 담기만 하면 된다. 실측상 flash-lite가 양쪽 다 해내므로
# 같은 모델을 쓰되, 한쪽만 올리고 싶을 때 바꿀 자리를 분리해 둔다.
SEARCH_STAGE_MODEL = "gemini-2.5-flash-lite"
STRUCTURE_STAGE_MODEL = "gemini-2.5-flash-lite"

# 2단계 수집 — ① 산문으로 검색시켜 출처를 받고 ② 그 산문을 JSON으로 정형화한다
#
# **왜 나눴나 (2026-08-26 실측)**: 한 번의 호출로 "검색해서 JSON으로 내라"를 시키면
# gemini-2.5-flash-lite가 검색을 **아예 하지 않는다**. 프로덕션 프롬프트(4,038자)로
# 2회 반복 측정한 결과 `web_search_queries`가 매번 **0건**이었고, 그러면서 587~625토큰의
# 내용을 기억만으로 지어냈다("구체적인 수치는 검색 결과에 따라 추가" 같은 슬롯 문구가
# 응답에 그대로 남아 있었다). 4,000자짜리 엄격한 스키마를 받으면 작은 모델은 이걸
# 검색 과제가 아니라 **서식 채우기 과제**로 처리한다.
#
# 대조 실험으로 원인을 좁혔다.
#   짧은 프롬프트 · 산문 출력       → 쿼리 2건, 출처 5건
#   짧은 프롬프트 · "JSON만 출력"   → 쿼리 2건, 출처 **0건**
#   프로덕션 프롬프트 · flash-lite  → 쿼리 **0건**
#   "검색 의무" 프리픽스만 추가     → 쿼리 0건 (2회 모두 실패 — 지시만으론 안 된다)
#   출력 형식 지시를 **무시하라**고 명시 → 쿼리 4~18건, 출처 4~17건 (3개 타입 × 2회 전부 성공)
#
# 즉 작동 요인은 "검색하라"는 지시가 아니라 **형식 압박을 걷어내는 것**이다.
# 그래서 1단계에서는 스키마를 겨냥하지 않게 만들고, 정형화는 2단계로 분리한다.
#
# 이 구조는 §31이 처방한 "문서를 먼저 가져오고 LLM은 고르고 요약만" 으로 가는 징검다리다.
# 최종 목표는 여전히 RSS 우선 수집(fetch_news_live·fetch_ib_korea_views가 쓰는 방식)이며,
# 그쪽은 날짜·URL·출처가 실기사에서 그대로 오므로 날조가 구조적으로 불가능하다.
_SEARCH_STAGE_WRAP = (
    "너는 지금 **검색 단계**를 수행한다. 아래 지침은 '무엇을 찾아야 하는가'에 대한 것이다.\n"
    "지침 안의 출력 형식(JSON·필드명·스키마) 지시는 이번 단계에서 **전부 무시**한다.\n\n"
    "이번 단계의 규칙:\n"
    "1. 반드시 google_search로 실제 검색을 먼저 수행한다. 기억에 의존해 답하지 않는다.\n"
    "2. 결과는 JSON이 아니라 **한국어 산문**으로 쓴다. 코드블록·중괄호를 쓰지 않는다.\n"
    "3. 검색으로 확인한 사실만 쓴다. 확인 안 된 것은 쓰지 않는다.\n"
    "4. 각 사실마다 수치·날짜·출처 매체명을 함께 적는다.\n\n"
    "──── 무엇을 찾을지에 대한 지침 (출력 형식 지시는 무시) ────\n"
)

# 2단계는 검색 도구를 주지 않는다 — 근거는 1단계 결과가 전부여야 한다.
# 도구를 남겨두면 정형화 중에 새로 검색해 1단계 출처와 무관한 내용이 섞이고,
# 그러면 출처 개수(1단계 측정치)와 본문이 서로 다른 것을 가리키게 된다.
_STRUCTURE_STAGE_WRAP = (
    "아래 '검색 결과'는 방금 google_search로 수집한 내용이다.\n"
    "**이 검색 결과에 실제로 있는 사실만** 사용해 지침이 요구하는 JSON으로 정리한다.\n"
    "검색 결과에 없는 내용을 추가·추정·보간하지 않는다. 해당 항목을 채울 근거가 없으면 "
    "빈 배열로 둔다 — 비는 것이 지어내는 것보다 낫다.\n\n"
    "──── 검색 결과 ────\n{evidence}\n\n"
    "──── 출력 지침 ────\n"
)


def _grounding_sources(response) -> list:
    """출처 매체명(도메인) 목록. 진단·로그용이며 판정에는 쓰지 않는다.

    URI는 일부러 담지 않는다 — grounding_chunks의 uri는 만료되는 임시 리다이렉트라
    저장해두면 나중에 깨진 링크가 된다(§11). 링크로 쓰려면 수집 시점에 원문 URL로
    리졸브해야 하는데, 매 실행 20여 건을 리졸브하는 비용이 진단 가치보다 크다.
    """
    try:
        gm = getattr((response.candidates or [None])[0], "grounding_metadata", None)
        out = []
        for ch in (getattr(gm, "grounding_chunks", None) or []):
            title = getattr(getattr(ch, "web", None), "title", None)
            if title and title not in out:
                out.append(title)
        return out
    except Exception:
        return []


def _search_stage(client, types, prompt: str) -> tuple:
    """1단계 — 실제 검색을 시켜 근거 텍스트·출처 수·출처 매체를 받는다.

    반환 (근거 텍스트, 출처 수 or None, 출처 매체 목록).
    출력이 산문이 아니라 JSON으로 나와도 그대로 쓴다 — 2단계 입력으로는 어느 형태든
    상관없고, 중요한 건 **검색이 실제로 일어났는지**(출처 수)다.
    """
    r = client.models.generate_content(
        model=SEARCH_STAGE_MODEL,
        contents=_SEARCH_STAGE_WRAP + prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.3,
            max_output_tokens=2000,
        ),
    )
    return (r.text or "").strip(), _count_grounding_chunks(r), _grounding_sources(r)


def _structure_stage(client, types, prompt: str, evidence: str) -> str:
    """2단계 — 1단계 근거만으로 JSON을 만든다. 검색 도구 없음."""
    r = client.models.generate_content(
        model=STRUCTURE_STAGE_MODEL,
        contents=_STRUCTURE_STAGE_WRAP.format(evidence=evidence) + prompt,
        config=types.GenerateContentConfig(temperature=0.3, max_output_tokens=1400),
    )
    if not r.text:
        finish = (getattr(r.candidates[0], "finish_reason", "UNKNOWN")
                  if r.candidates else "NO_CANDIDATES")
        raise RuntimeError(f"Gemini 정형화 단계가 빈 응답 (finish_reason={finish})")
    return r.text.strip()


def fetch_and_summarize(briefing_type: str) -> dict:
    """Gemini Google Search grounding으로 최신 뉴스를 검색·요약해 dict로 반환한다."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise RuntimeError("google-genai not installed. Run: pip install google-genai")

    # google_search는 v1beta만 받는다 — google-genai 3.0부터 기본값이 v1이라 명시한다(2026-11-13)
    client = genai.Client(api_key=get_gemini_api_key(),
                          http_options=types.HttpOptions(api_version="v1beta"))
    today_date = datetime.now(KST).date()
    today = today_date.strftime("%Y-%m-%d")
    # 코스피 아침 브리핑만 세션 창을 계산해 주입 (다른 타입은 키를 무시한다)
    session_window, us_label = _kospi_session_window(today_date)
    prompt = PROMPT_MAP[briefing_type].format(
        today=today, session_window=session_window, us_label=us_label
    )

    prev_items = _load_prev_catalysts(briefing_type)
    if prev_items:
        listed = "\n".join(f"- {x}" for x in prev_items)
        prompt += (
            "\n\n[중복 방지] 아래는 직전 브리핑에서 이미 다룬 이슈다. 오늘 검색 결과가 이 목록과"
            " 같은 사건이면(단순 재보도·반복 요약) 우선순위를 낮추고 실제로 새로 발생한 다른 이슈를"
            " 우선 검색해 담는다. 같은 사건이라도 오늘 새로운 후속 전개(추가 발표·주가 반응 변화 등)가"
            f" 있다면 그 새 전개 중심으로 다시 담아도 된다:\n{listed}"
        )

    # 2026-07-28 저녁 미국 브리핑 1회성 힌트 (사용자 요청) — 코카콜라(KO) 52주 신고가
    # 실측 확인(토스증권 API, 07-28 장중 고가 86.79 > 직전 52주 내 최고치 85.68).
    # 오늘 날짜에만 적용되고 다음 날부터는 자동으로 빠진다 — 상시 규칙으로 코드에 박지 않는다.
    if briefing_type == "us" and today == "2026-07-28":
        prompt += (
            "\n\n[오늘의 참고 소재] 코카콜라(KO)가 오늘 52주 신고가를 경신했다(실측 확인됨)."
            " 관련 뉴스(실적·배당·투자의견 등 상승 배경)가 검색되면 catalysts에 포함한다."
            " 검색되지 않으면 억지로 만들지 않는다."
        )

    # ── 1단계: 실제로 검색시킨다 (출처는 여기서만 붙는다 — 위 상수 주석의 실측 참조) ──
    evidence, _gchunks, _sources = _search_stage(client, types, prompt)
    print(f"[fetch_news] 1단계 검색 — 출처 "
          f"{('%d건' % _gchunks) if _gchunks is not None else '조회불가'}"
          f"{(' (' + ', '.join(_sources[:6]) + ')') if _sources else ''}",
          file=sys.stderr)

    if not evidence:
        # 검색 단계가 빈손이면 정형화할 근거가 없다. 지어내게 두지 않고 여기서 끝낸다(§27).
        print("[fetch_news] ⚠️ 1단계가 빈 응답 — 뉴스 없이 발행한다", file=sys.stderr)
        return {"key_indicators": [], "catalysts": [], "headlines": [],
                "market_sentiment": "neutral",
                "grounding_failure": ["empty_search_stage"]}

    # ── 2단계: 1단계 근거만으로 정형화한다 (검색 도구 없음) ──
    raw = _structure_stage(client, types, prompt, evidence)

    # JSON 블록 추출 (마크다운 펜스·전후 텍스트 제거)
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    # { ... } 블록만 추출
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        raw = m.group(0)

    data = json.loads(raw)
    today_kst = datetime.now(KST).date()

    # ── ① 수집 결과 **전체**의 신뢰도를 원본 그대로 먼저 판정한다 ──────────────────
    # 반드시 정규화·게이트 **이전**이어야 한다. 게이트를 통과한 뒤 재면 스키마 위반은
    # 이미 지워져 있고(2026-08-04 실사고), 익명 플레이스홀더도 이미 제거된 뒤다.
    # _gchunks는 **1단계**에서 잰 값이다. 2단계 응답에는 도구가 없어 출처가 아예 없으므로
    # 거기서 재면 항상 0이 나와 매번 폐기된다 — 측정 지점을 옮기면 안 된다(§31 "게이트 앞뒤").
    _signals = _grounding_failure_signals(data, _load_today_calendar(briefing_type), _gchunks)
    print(f"[fetch_news] 그라운딩 출처 {('%d건' % _gchunks) if _gchunks is not None else '조회불가'}"
          f", 신호 {_signals or '없음'}", file=sys.stderr)
    if _is_grounding_failure(data, _load_today_calendar(briefing_type), _gchunks):
        print(f"[fetch_news] ⚠️ 그라운딩 실패로 뉴스 요약 전체 폐기: {_signals}", file=sys.stderr)
        print("[fetch_news] 뉴스 없이 발행한다 — 방향이 틀린 브리핑보다 빈 섹션이 안전하다(§27).",
              file=sys.stderr)
        return {"key_indicators": [], "catalysts": [], "headlines": [],
                "market_sentiment": "neutral", "grounding_failure": _signals,
                "grounding_sources": _sources}

    # ── ② 정규화 경계 — 모든 게이트가 같은 본문을 보게 만든다 ─────────────────────
    # LLM이 키 이름을 바꿔도(text → catalyst) 게이트가 통째로 눈이 머는 일을 막는다.
    for _fld in ("catalysts", "headlines", "key_indicators"):
        if isinstance(data.get(_fld), list):
            data[_fld] = _normalize_news_items(data[_fld])
            # 중복 방지용으로 프롬프트에 넣어준 직전 실행 목록을 그대로 되뱉는 경우가 있다
            # (2026-08-04 확인) — 그러면 어제의 날조가 매일 되살아난다.
            data[_fld] = _drop_prev_run_echoes(data[_fld], prev_items)

    if isinstance(data.get("catalysts"), list):
        # 1차: 실적형 catalyst를 yfinance 실제 발표일로 검증(자기보고 날짜 무시), stale 제외
        cats = _drop_stale_earnings(data["catalysts"], today_kst)
        cats = _drop_preview_after_release(cats, datetime.now(KST))
        # 2차: 자기보고 날짜 기반 stale 제외 + 순수 문자열로 환원
        # 코스피 아침은 직전 미국장까지 창을 넓힌다(월요일 주말 공백 — _catalyst_cutoff)
        cats = _filter_stale_catalysts(
            cats, today_kst, cutoff=_catalyst_cutoff(briefing_type, today_kst)
        )
        # 3차: 2일+ 전 catalyst와 실질 중복인 재탕을 하드 제외(날짜 창 밖 재탕 백스톱)
        stale = _load_stale_catalysts(briefing_type, today_kst)
        data["catalysts"] = _drop_cross_day_recaps(cats, stale)
    # headlines·key_indicators도 stale 실적 서사를 제외 — Gemini가 텍스트에 심은 '엔비디아 실적 발표'
    # 류 날조가 catalysts만 걸러도 다른 필드로 Claude에 새어나가던 것을 차단(실측 지수는 fetch_data가
    # 별도 소스라 해당 항목이 통째 빠져도 §0 안전).
    for _fld in ("headlines", "key_indicators"):
        if isinstance(data.get(_fld), list):
            data[_fld] = _drop_stale_earnings(data[_fld], today_kst)
            data[_fld] = _drop_preview_after_release(data[_fld], datetime.now(KST))
    # "…확인되지 않았습니다" 류 검색 실패 보고를 전 필드에서 제거 (이슈가 아니라 메타 서술)
    # + "B사"·"C은행"·"[기업]" 류 익명 플레이스홀더 주어를 담은 날조 항목도 함께 제거
    # + 실측 시장데이터와 방향이 반대인 주장도 제거 (유가 등)
    # ※ 수집 전체의 신뢰도 판정(①)은 이 위, 정규화·게이트 이전에 이미 끝났다.
    if _signals:
        print(f"[fetch_news] 그라운딩 경고(폐기 임계 미만): {_signals}", file=sys.stderr)

    reality = _fetch_reality_snapshot()
    for _fld in ("catalysts", "headlines", "key_indicators"):
        if isinstance(data.get(_fld), list):
            data[_fld] = _drop_search_failure_notes(data[_fld])
            data[_fld] = _drop_placeholder_entities(data[_fld])
            data[_fld] = _drop_prompt_slot_echoes(data[_fld])
            data[_fld] = _drop_reality_contradictions(data[_fld], reality)
    # 다운스트림(call_claude)이 기대하는 출력 shape은 문자열 리스트다 — 정규화는 게이트 내부
    # 용도이므로 여기서 되돌린다(catalysts는 _filter_stale_catalysts가 이미 문자열로 환원).
    for _fld in ("headlines", "key_indicators"):
        if isinstance(data.get(_fld), list):
            data[_fld] = [_item_text(it) for it in data[_fld] if _item_text(it)]
    # 진단용 — 이 수집이 실제로 어떤 매체를 근거로 삼았는지 파일에 남긴다. §31이 "출처가
    # 몇 건 붙었는지를 매 수집마다 남기라"고 한 이유가, 그 한 줄이 없어서 무출처 생성이
    # 석 달간 검증되지 않은 채 유지됐기 때문이다. 로그는 지나가지만 파일은 남는다.
    data["grounding_sources"] = _sources
    return data


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def _is_billing_error(e: Exception) -> bool:
    """결제·권한·키 오류 — 기다려도 풀리지 않는다(2026-11-08~09 결제 미납으로 이틀간 뉴스 없이 발행)."""
    msg = str(e).upper()
    return ("PERMISSION_DENIED" in msg or "BILLING" in msg or "OUTSTANDING BALANCE" in msg
            or "API_KEY_INVALID" in msg or "API KEY NOT VALID" in msg or "403" in msg)


def _is_retryable_error(e: Exception) -> bool:
    if _is_billing_error(e):
        return False
    msg = str(e).upper()
    return (
        "429" in msg or "RESOURCE_EXHAUSTED" in msg or "QUOTA" in msg
        or "503" in msg or "UNAVAILABLE" in msg or "SERVICE_UNAVAILABLE" in msg
    )


def alert_gemini_failure(briefing_type: str, err: Exception) -> None:
    """Gemini가 결제·권한 오류로 막혔을 때 관리자 텔레그램 알림(평문, §37). 알림 실패는 삼킨다."""
    label = {"kospi": "코스피 아침", "kospi-close": "코스피 마감", "us": "미국"}.get(briefing_type, briefing_type)
    cmd = {"kospi": "kospi", "kospi-close": "kospi-close", "us": "us"}.get(briefing_type, briefing_type)
    msg = (f"⛔ Gemini API가 막혀 {label} 브리핑을 만들지 않았어요.\n"
           f"오류: {str(err)[:300]}\n"
           "결제·키 문제면 https://aistudio.google.com/billing 에서 확인하세요. "
           "같은 키를 쓰는 종목 뉴스·주도주 근거·증권가 시황 요약도 함께 멈춰 있어요.\n"
           f"풀린 뒤 다시 만들기: gh workflow run daily_report.yml -f briefing_type={cmd}")
    try:
        from send_telegram import send_admin_alert
        send_admin_alert(msg)
    except Exception as e:
        print(f"[fetch_news] 관리자 알림 실패: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="시장 뉴스 수집·요약")
    parser.add_argument("--type", choices=["kospi", "kospi-close", "us"], required=True)
    parser.add_argument("--source", choices=["gemini", "rss"], default="gemini",
                        help="gemini=google_search 그라운딩(기존), rss=RSS 실기사 우선 수집(§31 이후 미국 브리핑)")
    args = parser.parse_args()

    collect = fetch_and_summarize_rss if args.source == "rss" else fetch_and_summarize
    print(f"[fetch_news] Fetching news (type={args.type}, source={args.source})")

    summary = None
    last_err = None
    for attempt in range(1, 4):
        try:
            summary = collect(args.type)
            print(
                f"[fetch_news] OK (attempt {attempt}): "
                f"{len(summary.get('key_indicators', []))} indicators, "
                f"{len(summary.get('headlines', []))} headlines"
            )
            break
        except Exception as e:
            last_err = e
            if _is_retryable_error(e) and attempt < 3:
                import time
                wait = 45 * attempt
                print(f"[fetch_news] 일시 오류({attempt}/3) — {wait}s 후 재시도: {e}", file=sys.stderr)
                time.sleep(wait)
            else:
                break

    if summary is None:
        print(f"[fetch_news] ERROR: {last_err}", file=sys.stderr)
        # stale 파일이 남아 있으면 downstream이 구 데이터를 쓰지 않도록 삭제
        stale = DATA_DIR / f"news_summary_{args.type}.json"
        if stale.exists():
            stale.unlink()
            print(f"[fetch_news] stale 뉴스 파일 삭제: {stale}", file=sys.stderr)
        # 결제·권한 오류는 기다려도 안 풀린다 — 브리핑을 만들지 않고 관리자에게 알린다(§83, 2026-11-09 사용자 결정).
        # 워크플로가 blocked 출력을 보고 이후 스텝(분석·발행·텔레그램)을 멈춘다.
        if last_err is not None and _is_billing_error(last_err):
            print("[fetch_news] ERROR: Gemini 결제·권한 오류 — 브리핑을 만들지 않는다", file=sys.stderr)
            alert_gemini_failure(args.type, last_err)
            gh_out = os.environ.get("GITHUB_OUTPUT")
            if gh_out:
                with open(gh_out, "a", encoding="utf-8") as f:
                    f.write("blocked=true\n")
            sys.exit(3)
        else:
            print("[fetch_news] WARN: 빈 뉴스로 계속 진행 (Gemini 일시 장애)", file=sys.stderr)
        summary = EMPTY_NEWS

    summary["generated_at"] = datetime.now(KST).isoformat()
    out_path = DATA_DIR / f"news_summary_{args.type}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"[fetch_news] Saved → {out_path}")

    # 오늘 발행한 catalyst를 히스토리에 기록(다음 실행의 교차일 recap 판정 기준)
    if summary.get("catalysts"):
        _append_catalyst_history(args.type, datetime.now(KST).date(), summary["catalysts"])


if __name__ == "__main__":
    main()
