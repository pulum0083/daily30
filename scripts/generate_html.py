#!/usr/bin/env python3
# config-driven 섹션 조립으로 브리핑 HTML을 생성하는 조립기
"""브리핑 HTML 조립기.

call_claude.py가 다음 시그니처로 호출한다:
  generate_html.py --type {kospi|us|kospi-close} --data-file <latest_*.json> --date YYYY-MM-DD

analysis_{type}.json(Claude 분석) + data-file(시장 데이터)을 읽어
config/{internal}.json 선언에 따라 섹션 템플릿을 조립하고
web/briefings/{date}/{internal}/index.html 로 출력한다.

데이터가 없는 섹션은 조립 템플릿의 {% if %} 가드로 자동 생략된다(하이브리드).
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
from og_card import make_card

try:
    from scripts.verify_publish_gate import gate_write, check_sitemap  # noqa: F401 — weekly_report가 gh.gate_write로 쓴다
except ImportError:
    from verify_publish_gate import gate_write, check_sitemap  # noqa: F401

# 역할별 모듈로 나눈 정의 — 원래 이름(generate_html.X)으로도 그대로 읽힌다.
from html_common import (  # noqa: F401
    BASE_DIR, DATA_DIR, WEB_DIR, QUOTE_TODAY_FILE, BRIEFINGS_DIR, TEMPLATES_DIR,
    CONFIG_DIR, ASSET_VER, CSS_PATH, JS_PATH, KST, TYPE_MAP,
    SRC_TYPE, DATA_FILE, BRIEFING_LABELS, SCHEDULED_TIMES, DAY_FULL, DAY_SHORT,
    load_json, make_env, SITE_BASE, OG_IMAGE_URL, HL_NIGHT_CODES, GATE_BLOCKED,
    _jsonld, _breadcrumb, fmt_time, day_label, _md, _dow,
    _DOWS, _market_data_is_for,
)
from sections_shared import (  # noqa: F401
    MA5_BACKTEST_PATH, MA5_MARKETS, _ma5_price, build_monthly_ma5, _ma5_shown_this_month, _drop_ma5_repeats,
    _read_monthly_ma5, _ma5_backtest_stats, _load_quote_today, _chg_cell, build_market_items, build_fng_dial,
    _FNG_RATING_KO, _fng_label, _fng_is_fresh, build_analyst_quotes, build_accuracy, _baseline_pct,
    _edge_cls, _legacy_close_summary, build_scorecard, build_prediction,
)
from briefing_meta import (  # noqa: F401
    SEO_TITLE_PREFIX, BRAND_KO, _plain_text, briefing_head, _iso_kst, briefing_jsonld,
    strip_og_image,
)
from sections_close import (  # noqa: F401
    SUPPLY_HISTORY_FILE, SUPPLY_KEYS, _load_supply_history, write_supply_history_web, update_supply_history, supply_flow,
    build_scenario_context, build_why_what_so_context, build_qa_context, build_signal_context, build_flow_context, build_keynum_context,
    _split_comfort_line, _shares_label, build_close_vs, build_close_leaders, build_close_sections,
)
from sections_kospi import (  # noqa: F401
    _ISSUE_NUM_PATTERNS, _strip_issue_numbers, _prev_us_session_label, build_us_issue_results, _read_us_issue_results, ISSUE_RELATED_KR,
    _prev_label, build_prev_prediction, build_hero, _PRIOR_SIG_NAMES, build_prior_signals, build_prev_supply, build_us_session_map,
    _issue_title, build_issue_check, _abs_time_label, _domestic_card_title, build_reasons, build_ib_korea_views,
    build_domestic_issues,
)
from sections_us import (  # noqa: F401
    _PM_FUTURES, _PM_STOCKS, _pct_of, build_premarket_strip, save_us_index_position, NASDAQ_BACKTEST_PATH,
    _NQ_BADGE, build_struct_signal, build_nasdaq_check, _read_nasdaq_overheat, read_sp500_ma200,
    build_sp500_ma200, BREAKOUT_BACKTEST_PATH, read_breakout_watch, _cap_label, _bw_line, build_breakout_watch,
    build_issues, build_us_tone,
)
from standalone_pages import (  # noqa: F401
    NASDAQ_PAGE_URL, build_nasdaq_page, write_nasdaq_page, write_nasdaq_home, SP500_PAGE_URL, MIDTERM_PAGE_URL,
    _write_lt_page, write_sp500_page, write_midterm_page, write_trump_page, RECORD_PAGES, write_record_pages,
)
from sector_pages import (  # noqa: F401
    _fmt_krw, _fmt_pct, _pct_cls, _SECTOR_EMOJI, _SECTOR_COPY_PATH, _sector_copy,
    build_sector_pages,
)
from site_index import (  # noqa: F401
    find_latest_ready, update_vercel_briefings_route, _parse_close_price, _close_changes, write_briefings_list_json, ARCHIVE_TYPES,
    _archive_headline, _archive_dek, build_archive_context, write_briefings_index, RSS_ITEMS, _briefing_pub_date,
    write_briefings_rss, STOCKS_HOME_HTML, RECENT_START, RECENT_END, _WEEKDAYS, build_recent_briefings,
    WEEKLY_RECENT_MAX_AGE, build_recent_weekly, render_recent_briefings, write_stocks_recent_briefings, BRIEFING_INDEX_DAYS, ROBOTS_INDEX,
    ROBOTS_NOINDEX, _ROBOTS_RE, briefing_indexed, apply_briefing_robots, write_sitemap_xml, existing_dates,
    find_adjacent, build_list_context,
)


# ─────────────────────────────────────────────────────────────────────────────
# SEO 메타 (2026-07-21 신설) — 종목·미국·섹터 상세 페이지의 head 메타를 한곳에서 만든다.
#
# 배경: 종목 상세 46개가 <title> 외에 description·canonical·OG·JSON-LD를 하나도 갖지
# 않은 채 발행되고 있었다(STOCKS_SERVICE_RULES §9 발행 게이트 4번 미이행). 검색 유입을
# 노린 영구 자산인데 정작 검색엔진에 제출되는 형태가 비어 있었다.
#
# ⚠️ make_env()가 autoescape=False라 meta content를 템플릿에서 그대로 찍으면 따옴표가
#    섞였을 때 속성이 깨진다. 반드시 여기서 이스케이프해 넘긴다.


def render_briefing(internal_type: str, target_date: str, market_data: dict, force: bool = False) -> str:
    env = make_env()
    config = load_json(CONFIG_DIR / f"{internal_type}.json")
    src_type = SRC_TYPE[internal_type]
    # ── analysis 로드 우선순위 ──────────────────────────────────────────────────
    # 1순위: git에 커밋된 날짜별 snapshot (재생성 시 오염 방지)
    # 2순위: 임시 live 파일 — 반드시 날짜 검증 후 사용
    # --force 시 snapshot을 무시하고 항상 최신 analysis_{type}.json을 사용 (의도적 정정 재생성용)
    snapshot_path = BRIEFINGS_DIR / target_date / internal_type / "analysis_snapshot.json"
    analysis_path = DATA_DIR / f"analysis_{src_type}.json"

    if snapshot_path.exists() and not force:
        print(f"[generate_html] ⚠️ 기존 snapshot 사용 → {snapshot_path.relative_to(BASE_DIR)} "
              f"(새로 생성된 analysis_{src_type}.json은 무시됨. 의도적 정정이면 --force 사용)")
        analysis = load_json(snapshot_path)
    elif analysis_path.exists():
        analysis = load_json(analysis_path)
        analysis_date = (analysis.get("generated_at") or "")[:10]
        if analysis_date and analysis_date != target_date:
            raise RuntimeError(
                f"[generate_html] ⛔ 분석 날짜 불일치 — "
                f"analysis_{src_type}.json 생성일({analysis_date}) ≠ 대상 날짜({target_date}).\n"
                f"다른 워크플로우 실행으로 덮어써진 파일입니다. 오염된 예측 발행을 차단합니다.\n"
                f"해결: web/briefings/{target_date}/{internal_type}/analysis_snapshot.json 이 있으면 자동 사용됩니다."
            )
    else:
        analysis = {}

    generated_at = market_data.get("generated_at") or analysis.get("generated_at") or datetime.now(KST).isoformat()
    gen_time = fmt_time(generated_at)
    index_name = config["index_name"]
    prev_url, next_url = find_adjacent(internal_type, target_date)

    canonical_url = f"https://doubleshot.space/briefings/{target_date}/{internal_type}/"
    _issue_slot_map = {"kospi": "MARKET", "us": "US_MARKET"}
    ctx = {
        "date_str": target_date,
        "generated_at": generated_at,
        "generated_time": gen_time,
        "gnb_date": f"{target_date} KST {gen_time}",
        "index_name": index_name,
        "prev_url": prev_url, "next_url": next_url,
        "css_path": CSS_PATH, "js_path": JS_PATH,
        "canonical_url": canonical_url,
        "briefing_type": internal_type,
        "issue_slot": _issue_slot_map.get(internal_type, "MARKET"),
        **build_list_context(target_date, internal_type),
        **build_accuracy(internal_type),
        # 공유 카드(2026-10-27) — write_output이 같은 폴더에 og.png를 만든다. 못 만들면 태그를 지운다.
        # 텔레그램 메시지는 링크 미리보기를 끈다(send_telegram) — 이 카드는 카카오톡·X 공유용이다.
        "og_image": f"{canonical_url}og.png",
    }
    ctx["accuracy"] = bool(ctx.get("acc_30d_pct") is not None and (ctx.get("hit", 0) + ctx.get("miss", 0)) > 0)

    # 코스피 성적표 카드 — 사이드바 accuracy.html 대체(kospi 전용). 데이터 부족 시 빈 dict → 카드 생략.
    if internal_type == "kospi":
        ctx.update(build_scorecard(internal_type))
        ctx["scorecard"] = bool(ctx.get("sc_monthly"))

    if internal_type == "close":
        ctx.update(build_close_sections(analysis, market_data, index_name, target_date))
        from kr_official_closes import session_hours
        _o, _c, _ = session_hours(target_date.replace("-", ""))   # 수능일은 10:00 ~ 16:30(§91)
        ctx["close_session_hours"] = f"{_o[:2]}:{_o[2:]} ~ {_c[:2]}:{_c[2:]}"
    elif internal_type == "us":
        # 미국 이슈 중심 브리핑 — 예측 대신 오늘의 관점 + 이슈 카드. 성적표 사이드바 없음.
        ctx.update(build_issues(analysis))
        ctx.update(build_us_tone(market_data))
        ctx.update(build_analyst_quotes(market_data))
        # AI 종목 픽(진입·목표·손절)은 2026-10-26 제거 — 코스피와 같은 월봉 5개월선 안착 코너(결정론, §67)
        ctx.update(build_monthly_ma5(analysis, target_date, "us"))
        ctx["market_items"] = build_market_items(market_data, internal_type, gen_time)
        ctx["fng_dial"] = build_fng_dial(market_data, internal_type)
        ctx["todays_view"] = analysis.get("todays_view")
        ctx.update(build_nasdaq_check(analysis, target_date))   # 나스닥 체크(§65) — 이슈 아래
        ctx.update(build_sp500_ma200(analysis, target_date))    # S&P 500 200일선 체크(§81) — 나스닥 체크 아래
        ctx.update(build_breakout_watch(analysis, target_date)) # 돌파 관찰 목록(§88) — 200일선 체크 아래
        ctx.update(build_premarket_strip(analysis, market_data, target_date, gen_time))   # 프리마켓 실측 띠 — 맨 위
        save_us_index_position(analysis, market_data, target_date)
        ctx.update(build_struct_signal(analysis))               # 구조 신호 — 본문 맨 아래, 모바일은 시장 지표 위(§68 ⑤)
        ctx["accuracy"] = False  # 미국 성적표 사이드바는 내지 않는다(채점은 2026-11-03 재개)
    else:
        ctx.update(build_prediction(analysis, index_name, config["pred_title"], gen_time))
        ctx["quote_today"] = _load_quote_today(target_date)
        ctx.update(build_reasons(analysis, target_date))
        ctx.update(build_analyst_quotes(market_data))
        # 상승 모멘텀 종목(LLM 픽)은 2026-10-25 제거 — 그 자리에 월봉 5개월선 안착 종목(결정론)을 둔다
        ctx.update(build_monthly_ma5(analysis, target_date))
        ctx["market_items"] = build_market_items(market_data, internal_type, gen_time)
        ctx["fng_dial"] = build_fng_dial(market_data, internal_type)
        ctx["watch_items"] = analysis.get("watch_items") or analysis.get("watchpoints") or []
        ctx["todays_view"] = analysis.get("todays_view")
        ctx["format_in_view"] = True  # 코스피는 근거 형식을 '오늘의 관점' 안에서 렌더
        ctx.update(build_ib_korea_views(target_date))
        ctx.update(build_domestic_issues(target_date))
        # 3단 구조(2026-10-26) — 30초 요약 카드 + 오늘의 이슈 점검
        ctx.update(build_hero(analysis, target_date))
        ctx.update(build_prev_prediction(analysis, target_date))
        ctx.update(build_issue_check(ctx.get("us_issue_cards")))
        ctx.update(build_prior_signals(analysis, market_data, target_date))   # 예측 근거 신호 한 줄
        ctx.update(build_prev_supply(analysis, market_data, target_date))     # 전일 수급 카드
        ctx.update(build_us_session_map(analysis, market_data, target_date))  # 간밤 미국장 카드
        uls = analysis.get("us_linked_story") or {}
        if uls.get("title"):
            ctx["us_linked_title"] = uls["title"]
            ctx["us_linked_paragraphs"] = uls.get("paragraphs", [])
            ctx["us_linked_stocks"] = uls.get("related_stocks", [])
        else:
            # us_linked_story가 없으면(또는 폴백) 섹터 리뷰를 렌더한다 — 날짜 시드 랜덤으로 택1됨
            sf = analysis.get("sector_focus") or {}
            if sf.get("signal") and sf.get("paragraphs"):
                ctx["sector_emoji"] = sf.get("emoji", "🏭")
                ctx["sector_name"] = sf.get("sector_name", "반도체")
                ctx["sector_signal"] = sf["signal"]
                ctx["sector_paragraphs"] = sf.get("paragraphs", [])

    head = briefing_head(analysis, internal_type, target_date)
    ctx["page_title"] = head["title"]
    ctx["og_description"] = head["description"]
    # 발행 시각은 그 날짜의 값만 쓴다 — 스냅샷(날짜 고정)이 1순위. 재생성 때 낡은 시장 데이터 시각이 들어가지 않게.
    published = next((t for t in (analysis.get("generated_at"), generated_at)
                      if str(t or "")[:10] == target_date), "")
    ctx["seo_jsonld"] = briefing_jsonld(head, internal_type, target_date, published, canonical_url)

    template = env.get_template(config["template"])
    return template.render(**ctx), analysis


def write_output(html: str, internal_type: str, target_date: str, analysis=None):
    out_dir = BRIEFINGS_DIR / target_date / internal_type
    out_dir.mkdir(parents=True, exist_ok=True)
    card = make_card(analysis, internal_type, target_date)
    if card:
        (out_dir / "og.png").write_bytes(card)
    else:
        html = strip_og_image(html)
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"[generate_html] wrote {out_dir.relative_to(BASE_DIR)}/index.html")
    # analysis snapshot 저장 — git에 커밋되어 재생성 시 날짜 오염을 방지함
    if analysis:
        import json as _json
        snap_path = out_dir / "analysis_snapshot.json"
        snap_path.write_text(_json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[generate_html] snapshot → {snap_path.relative_to(BASE_DIR)}")


def patch_landing_hero(analysis: dict, target_date: str):
    """랜딩 페이지 Hero 위젯을 최신 코스피 분석으로 갱신한다 (코스피 브리핑 생성 시에만 호출).

    NOTE: 랜딩 hero는 고정 예시(2026-06-22 실측 브리핑)로 운영한다 — 자동 갱신 비활성화.
    sig_items 필드가 스키마에 없어 reasons가 항상 비던 문제도 있었음. 되살리려면 아래 return을 제거하고
    sig_items 대신 telegram_signals를 쓰도록 reason_lines를 수정해야 한다.
    """
    return
    landing = WEB_DIR / "landing.html"
    if not landing.exists():
        return

    prediction = analysis.get("prediction", {})
    direction = prediction.get("direction", "상승 우위")
    up_pct = prediction.get("up_pct", 50)
    sig_items = (analysis.get("sig_items") or [])[:5]
    reason_title = analysis.get("reason_title", "")

    arrow = "↑" if "상승" in direction else "↓"
    up_count = sum(1 for s in sig_items if s.get("level") == "up")
    total = len(sig_items)
    tone = "강세" if "상승" in direction else "약세"
    conf_text = f"{tone} 우위 · 신호 {total}개 중 {up_count}개가 상승"

    reason_lines = []
    for item in sig_items:
        label = item.get("label", "")
        desc = re.sub(r"<[^>]+>", "", item.get("desc", ""))
        level = item.get("level", "neu")
        tag_cls = "brief-tag risk" if level == "dn" else "brief-tag"
        reason_lines.append(
            f'          <div class="brief-reason">'
            f'<span class="{tag_cls}">{label}</span>'
            f"<span>{desc}</span></div>"
        )

    widget = (
        "<!-- HERO-WIDGET:START -->\n"
        '      <div class="live">\n'
        '        <div class="live-top">\n'
        f'          <div class="lab"><span class="live-dot"></span>{target_date} · 코스피 당일 예측</div>\n'
        f'          <div class="live-dir">{arrow} {direction} <span class="prob mono">{up_pct}% 상승</span></div>\n'
        f'          <div class="brief-head">{reason_title}</div>\n'
        f'          <div class="brief-sub">{conf_text}</div>\n'
        "        </div>\n"
        '        <div class="brief-reasons">\n'
        + "\n".join(reason_lines) + "\n"
        "        </div>\n"
        f'        <a class="brief-more" href="/briefings/{target_date}/kospi/">이 브리핑 전체 읽기 →</a>\n'
        "      </div>\n"
        "      <!-- HERO-WIDGET:END -->"
    )

    html = landing.read_text(encoding="utf-8")
    updated = re.sub(
        r"<!-- HERO-WIDGET:START -->.*?<!-- HERO-WIDGET:END -->",
        widget,
        html,
        flags=re.DOTALL,
    )
    if updated == html:
        print("[generate_html] landing.html hero 마커 없음, 패치 생략")
        return
    landing.write_text(updated, encoding="utf-8")
    print(f"[generate_html] landing.html hero → {target_date} 패치 완료")


def _finish_page_build(written_paths):
    """페이지 배치 생성 뒤 발행 게이트 결과를 종합한다. 위반이 있으면 exit 1.

    sitemap 포함 여부는 여기서만 검사할 수 있다 — write_sitemap_xml()이 '파일이 존재하는 페이지'만
    담기 때문에 쓰기 시점엔 아직 판정이 불가능하다.
    """
    problems = [f"메타 위반으로 발행 차단: {u}" for u in GATE_BLOCKED]
    problems += check_sitemap([f"{SITE_BASE}/{p[:-len('index.html')]}" for p in written_paths])
    if not problems:
        return
    for p in problems:
        print(f"::error::[발행 게이트] {p}", file=sys.stderr)
    print(f"\n❌ 발행 게이트 위반 {len(problems)}건 — 차단된 페이지는 직전 정상본이 유지됩니다",
          file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", choices=list(TYPE_MAP.keys()))
    parser.add_argument("--date", help="YYYY-MM-DD")
    parser.add_argument("--data-file", dest="data_file", help="시장 데이터 JSON 경로")
    parser.add_argument("--write-list-only", action="store_true",
                        help="briefings-list.json 만 갱신하고 HTML 재생성 없이 종료")
    parser.add_argument("--sync-index", action="store_true",
                        help="index.html + briefings-list.json 재동기화만 하고 종료 (수동 브리핑 수정 후 사용)")
    parser.add_argument("--sectors", action="store_true",
                        help="섹터별 종목 페이지 8개 생성하고 종료")
    parser.add_argument("--nasdaq-page", dest="nasdaq_page", action="store_true",
                        help="--date 날짜의 data/nasdaq_overheat.json으로 /stocks/nasdaq-check/ 상세 페이지만 다시 쓴다")
    parser.add_argument("--midterm-page", dest="midterm_page", action="store_true",
                        help="--date(KST) 직전 미국장 기준 data/midterm_2018.json으로 /stocks/midterm-2018/ 상세 페이지만 다시 쓴다")
    parser.add_argument("--trump-page", dest="trump_page", action="store_true",
                        help="--date(KST) 직전 미국장 기준 data/trump_terms.json으로 /stocks/trump-terms/ 상세 페이지만 다시 쓴다")
    parser.add_argument("--sp500-page", dest="sp500_page", action="store_true",
                        help="--date 날짜의 data/sp500_ma200.json으로 /stocks/sp500-200/ 상세 페이지만 다시 쓴다")
    parser.add_argument("--record-pages", dest="record_pages", action="store_true",
                        help="예측 성적표(/accuracy/)·방법론(/methodology/)만 다시 쓴다 — 평일 09:10 채점 잡이 부른다")
    parser.add_argument("--force", action="store_true",
                        help="기존 analysis_snapshot.json을 무시하고 최신 analysis_{type}.json으로 강제 재생성 (의도적 정정용)")
    args = parser.parse_args()

    if args.sectors:
        build_sector_pages()
        write_sitemap_xml()   # 섹터 URL이 sitemap에 들어가야 게이트의 색인 경로 검사가 성립한다
        _finish_page_build([])
        return

    if args.record_pages:
        written = write_record_pages()
        write_sitemap_xml()
        _finish_page_build(written)
        return

    if args.sp500_page or args.midterm_page or args.trump_page:
        if not args.date:
            parser.error("--sp500-page·--midterm-page·--trump-page 는 --date 가 필요합니다")
        (write_trump_page if args.trump_page else write_midterm_page if args.midterm_page else write_sp500_page)(args.date)
        write_sitemap_xml()
        _finish_page_build([])
        return

    if args.nasdaq_page:
        if not args.date:
            parser.error("--nasdaq-page 는 --date 가 필요합니다")
        write_nasdaq_page(args.date)
        write_sitemap_xml()
        _finish_page_build([])
        return

    if args.write_list_only:
        write_briefings_list_json()
        write_briefings_index()
        write_sitemap_xml()
        return

    if args.sync_index:
        latest = find_latest_ready()
        if latest:
            update_vercel_briefings_route(latest[0], latest[1])
        write_briefings_list_json()
        write_briefings_index()
        write_sitemap_xml()
        return

    if not args.type or not args.date or not args.data_file:
        parser.error("--type, --date, --data-file 은 필수입니다 (--write-list-only / --sync-index 사용 시 제외)")

    internal_type = TYPE_MAP[args.type]
    data_path = Path(args.data_file)
    market_data = load_json(data_path) if data_path.exists() else {}

    html, analysis = render_briefing(internal_type, args.date, market_data, force=args.force)
    write_output(html, internal_type, args.date, analysis)
    if internal_type == "kospi":
        patch_landing_hero(analysis, args.date)
    if internal_type == "us":
        # 나스닥 체크 상세 페이지 — 부가 페이지라 실패해도 브리핑 발행은 계속한다(§0 부칙과 같은 판단).
        try:
            write_nasdaq_page(args.date)
        except Exception as e:
            print(f"[generate_html] 나스닥 체크 상세 페이지 생성 실패({type(e).__name__}: {e}) — 건너뜀.",
                  file=sys.stderr)
        try:
            write_sp500_page(args.date)
        except Exception as e:
            print(f"[generate_html] S&P 500 200일선 상세 페이지 생성 실패({type(e).__name__}: {e}) — 건너뜀.",
                  file=sys.stderr)
    update_vercel_briefings_route(internal_type, args.date)
    write_briefings_list_json()
    write_briefings_index()
    write_sitemap_xml()


if __name__ == "__main__":
    main()
