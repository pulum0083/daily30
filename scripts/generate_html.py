#!/usr/bin/env python3
"""
Generate HTML briefing pages from structured JSON data.
Called AFTER call_claude.py produces data/analysis_{type}.json.

This module replaces Claude's HTML generation step, saving ~4,000 output tokens/run.
Claude only outputs the analysis JSON; this script renders the full page.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
import pytz

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
WEB_DIR = BASE_DIR / "web"
BRIEFINGS_DIR = WEB_DIR / "briefings"
BRIEFINGS_DIR.mkdir(parents=True, exist_ok=True)

KST = pytz.timezone("Asia/Seoul")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def fmt_generated_time(generated_at: str) -> str:
    try:
        dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = KST.localize(dt)
        else:
            dt = dt.astimezone(KST)
        return dt.strftime("%H:%M")
    except Exception:
        return "08:30"


def load_data(data_file: str) -> dict:
    path = Path(data_file)
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {data_file}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_analysis(briefing_type: str) -> dict:
    analysis_file = DATA_DIR / f"analysis_{briefing_type}.json"
    if analysis_file.exists():
        with open(analysis_file, encoding="utf-8") as f:
            return json.load(f)
    return {}


def get_web_base_url() -> str:
    url = os.environ.get("WEB_BASE_URL")
    if url:
        return url.rstrip("/")
    config_file = BASE_DIR / "config.json"
    if config_file.exists():
        with open(config_file, encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg.get("web", {}).get("base_url", "").rstrip("/")
    return "https://bejewelled-toffee-87de55.netlify.app"


# ─────────────────────────────────────────────────────────────────────────────
# Stock chart data builder
# ─────────────────────────────────────────────────────────────────────────────

def build_stock_charts(stock_picks: list, candidates: list) -> list:
    """Build stockCharts array for MARKET_DATA by matching picks to candidates."""
    charts = []
    for i, pick in enumerate(stock_picks, 1):
        pick_name = pick.get("name", "")
        candidate = next((c for c in candidates if c.get("name") == pick_name), None)
        if candidate:
            charts.append({
                "id": f"mc-{i}",
                "prices": candidate.get("sparkline", []),
                "ma20": candidate.get("ma20_sparkline", []),
                "ma200": candidate.get("ma200_sparkline", []),
            })
        else:
            charts.append({"id": f"mc-{i}", "prices": [], "ma20": [], "ma200": []})
    return charts


# ─────────────────────────────────────────────────────────────────────────────
# HTML fragment builders
# ─────────────────────────────────────────────────────────────────────────────

def build_stock_picks_html(stock_picks: list) -> str:
    html = ""
    for i, pick in enumerate(stock_picks, 1):
        ma200_dist = pick.get("ma200_dist_pct", 0)
        ma200_cls = "up" if ma200_dist >= 0 else "down"
        ma200_w = min(abs(ma200_dist) * 10, 100)
        sign = "+" if ma200_dist >= 0 else ""
        above_below = "상회" if ma200_dist >= 0 else "하회"
        golden = '<span class="golden-badge">★ GOLDEN</span>' if pick.get("golden") else ""
        html += f"""
                  <div class="stock-pick-card">
                    <div class="stock-pick-card__top">
                      <div class="stock-pick-card__rank">{i}</div>
                      <div class="stock-pick-card__info">
                        <div class="stock-pick-card__name">
                          {pick.get("name", "")}
                          <span class="ma20-badge">{pick.get("signal", "MA20 반등")}</span>
                          {golden}
                        </div>
                        <div class="stock-pick-card__meta">
                          <span class="stock-pick-card__price">{pick.get("price", "")}</span>
                          <span class="stock-pick-card__change {pick.get("change_cls", "up")}">{pick.get("change", "")}</span>
                        </div>
                        <div class="ma200-gauge">
                          <span class="ma200-gauge__label">200일선 대비</span>
                          <div class="ma200-gauge__track">
                            <div class="ma200-gauge__fill {ma200_cls}" style="width:{ma200_w:.0f}%"></div>
                          </div>
                          <span class="ma200-gauge__pct {ma200_cls}">{sign}{ma200_dist:.1f}% {above_below}</span>
                        </div>
                        <div class="stock-pick-card__scenario">
                          <span class="scenario-tag">{pick.get("scenario_tag", "단기 반등")}</span>
                          {pick.get("scenario", "")}
                        </div>
                      </div>
                      <div class="stock-pick-mini-chart">
                        <canvas id="mc-{i}" width="88" height="52"></canvas>
                        <div class="stock-pick-mini-chart__legend">
                          <span class="leg-price">주가</span>
                          <span class="leg-ma">MA20</span>
                          <span class="leg-ma200">MA200</span>
                        </div>
                      </div>
                    </div>
                    <div class="stock-pick-card__cta">
                      <span class="cta-label">실행 가이드</span>
                      {pick.get("action_guide", "")}
                    </div>
                  </div>"""
    return html


_FG_BLOCK = """\
                <div class="fg-block">
                  <div class="fg-block-header">
                    <span class="mkt-name" style="display:flex;align-items:center;gap:4px;">
                      공포탐욕지수
                      <button class="info-icon-btn" onclick="openFGModal()" aria-label="공포탐욕지수 설명">!</button>
                    </span>
                    <span class="fg-badge" id="fg-badge">-</span>
                  </div>
                  <div class="fg-body">
                    <div class="fg-gauge-mini"><canvas id="fg-gauge-canvas" style="width:118px;height:64px;display:block;"></canvas></div>
                    <div class="fg-info">
                      <div class="fg-now"><span class="fg-now-val" id="fg-value">-</span><span class="fg-now-lbl" id="fg-label">-</span></div>
                      <div class="fg-hist-grid">
                        <div class="fg-hist-item"><span class="lbl">전일</span><span class="val" id="fg-hist-prev">-</span></div>
                        <div class="fg-hist-item"><span class="lbl">1주</span><span class="val" id="fg-hist-1w">-</span></div>
                        <div class="fg-hist-item"><span class="lbl">1달</span><span class="val" id="fg-hist-1m">-</span></div>
                        <div class="fg-hist-item"><span class="lbl">1년</span><span class="val" id="fg-hist-1y">-</span></div>
                      </div>
                      <div id="fg-date" style="font-size:10px;color:var(--text-tertiary);margin-top:4px;"></div>
                    </div>
                  </div>
                </div>"""


def build_sidebar_items(briefing_type: str) -> str:
    """Build flat sidebar market items. Order differs per briefing type."""

    def mkt_row(name, val_id, badge_id, canvas_id):
        return f'                <div class="mkt-row"><div class="mkt-row-info"><span class="mkt-name">{name}</span><div class="mkt-vals"><div class="mkt-val" id="{val_id}">-</div><div class="mkt-chg" id="{badge_id}">-</div></div></div><div class="mkt-spark"><canvas id="{canvas_id}"></canvas></div></div>'

    if briefing_type == "kospi":
        rows = [
            mkt_row("나스닥",            "nasdaq-val", "nasdaq-badge", "c-nasdaq"),
            mkt_row("다우존스",           "dji-val",    "dji-badge",    "c-dji"),
            mkt_row("필라델피아 반도체",   "sox-val",    "sox-badge",    "c-sox"),
            mkt_row("달러 인덱스 DXY",   "dxy-val",    "dxy-badge",    "c-dxy"),
            mkt_row("WTI 국제유가",       "oil-val",    "oil-badge",    "c-oil"),
            _FG_BLOCK,
        ]
    else:  # us
        rows = [
            mkt_row("나스닥100 선물",     "nq-val",     "nq-badge",     "c-nq"),
            mkt_row("WTI 국제유가",       "oil-val",    "oil-badge",    "c-oil"),
            _FG_BLOCK,
        ]

    return "\n".join(rows)


# ─────────────────────────────────────────────────────────────────────────────
# Main HTML builder
# ─────────────────────────────────────────────────────────────────────────────

def build_full_html(data: dict, analysis: dict, date_str: str,
                    briefing_type: str, asset_prefix: str = "../") -> str:
    """Build complete HTML page for KOSPI or US briefing."""

    market_data_js = dict(data.get("market_data_js", {}))
    candidates_key = "kospi_candidates" if briefing_type == "kospi" else "us_candidates"
    candidates = data.get(candidates_key, [])

    pred = analysis.get("prediction", {})
    up_pct = pred.get("up_pct", 50)
    down_pct = pred.get("down_pct", 50)
    direction = pred.get("direction", "중립")
    confidence = pred.get("confidence", 70)
    reasons = analysis.get("reasons", [])[:4]
    stock_picks = analysis.get("stock_picks", [])
    generated_at = data.get("generated_at", datetime.now(KST).isoformat())
    gen_time = fmt_generated_time(generated_at)

    # Build stockCharts and inject into MARKET_DATA
    stock_charts = build_stock_charts(stock_picks, candidates)
    market_data_js["stockCharts"] = stock_charts
    market_data_json = json.dumps(market_data_js, ensure_ascii=False, indent=2)

    # Direction badge class
    dir_cls = "up" if direction == "상승 우위" else ("down" if direction == "하락 우위" else "")

    # Confidence interval bar widths
    up_light = confidence
    down_light = round(down_pct * confidence / up_pct) if up_pct > 0 else confidence

    # Reasons HTML
    if reasons:
        reasons_html = "\n".join(f"                    <li>{r}</li>" for r in reasons)
    else:
        reasons_html = "                    <li>데이터 수집 중...</li>"

    # Stock picks HTML
    picks_html = build_stock_picks_html(stock_picks)

    # Sidebar items HTML (flat, no groups)
    sidebar_groups = build_sidebar_items(briefing_type)

    # Type-specific strings
    if briefing_type == "kospi":
        page_title = f"Daily30' — 코스피 시초가 브리핑 {date_str}"
        badge_text = "코스피"
        gnb_time = "08:30"
        section_title = "코스피 시초가 방향 예측"
    else:
        page_title = f"Daily30' — 미국 시장 브리핑 {date_str}"
        badge_text = "미국"
        gnb_time = "22:30"
        section_title = "S&P500 방향 예측"

    # Use string Template-style to avoid brace collisions with JSON in f-string
    html = (
        "<!DOCTYPE html>\n"
        '<html lang="ko" class="light">\n'
        "<head>\n"
        '  <meta charset="UTF-8" />\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
        f"  <title>{page_title}</title>\n"
        f'  <link rel="stylesheet" href="{asset_prefix}assets/style.css" />\n'
        "</head>\n"
        "<body>\n"
        '  <nav class="gnb">\n'
        '    <div class="gnb__inner">\n'
        '      <div class="gnb__logo">\n'
        '        <div class="gnb__logo-mark">\n'
        '          <svg viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5">\n'
        '            <polyline points="22 7 13.5 15.5 8.5 10.5 2 17"></polyline>\n'
        '            <polyline points="16 7 22 7 22 13"></polyline>\n'
        "          </svg>\n"
        "        </div>\n"
        f"        <span class=\"gnb__title\">Daily<span>30'</span></span>\n"
        "      </div>\n"
        '      <div class="gnb__meta">\n'
        f'        <span class="gnb__date" id="gnb-date">{date_str} KST {gnb_time}</span>\n'
        f'        <span class="gnb__badge">{badge_text}</span>\n'
        '        <button class="gnb__theme-toggle" onclick="toggleTheme()" aria-label="테마 전환">\n'
        '          <svg class="icon-sun" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>\n'
        '          <svg class="icon-moon" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>\n'
        "        </button>\n"
        "      </div>\n"
        "    </div>\n"
        "  </nav>\n"
        "\n"
        '  <div class="layout-wrapper">\n'
        '    <div class="layout-grid">\n'
        "\n"
        "      <!-- 왼쪽: 브리핑 본문 -->\n"
        '      <div class="layout-grid__main">\n'
        "\n"
        '        <div class="accordion-item is-open is-today">\n'
        '          <div class="accordion-header">\n'
        f'            <div class="accordion-header__date-label">{date_str}</div>\n'
        '            <div class="accordion-header__badges">\n'
        f'              <span class="pred-badge {dir_cls}">{direction}</span>\n'
        "            </div>\n"
        "          </div>\n"
        "\n"
        '          <div class="accordion-body">\n'
        '            <div class="accordion-body__inner">\n'
        "\n"
        "              <!-- 1. 예측 카드 -->\n"
        '              <div class="open-section">\n'
        '                <div class="open-section__title">\n'
        f"                  {section_title}\n"
        '                  <button class="info-icon-btn" onclick="openPredModal()" aria-label="예측 방법 설명">i</button>\n'
        f'                  <span class="section-time">{gen_time} 생성</span>\n'
        "                </div>\n"
        '                <div class="prediction-card">\n'
        '                  <div class="prediction-summary">\n'
        f'                    <span class="prediction-label">{direction} 예측 (신뢰도 {confidence}%)</span>\n'
        "                  </div>\n"
        "                  <!-- PC: Confidence interval bar -->\n"
        '                  <div class="pred-confbar">\n'
        '                    <div class="pred-confbar__row">\n'
        '                      <div class="pred-confbar__header">\n'
        '                        <span style="color:var(--status-up)">상승</span>\n'
        f'                        <span style="color:var(--text-secondary)">{up_pct}%</span>\n'
        "                      </div>\n"
        '                      <div class="pred-confbar__track">\n'
        f'                        <div class="pred-confbar__light" style="width:{up_light}%;background:var(--status-up-bg)"></div>\n'
        f'                        <div class="pred-confbar__solid up" style="width:{up_pct}%"></div>\n'
        "                      </div>\n"
        f'                      <div class="pred-confbar__meta">신뢰구간 {confidence}% → 최대 {up_light}%</div>\n'
        "                    </div>\n"
        '                    <div class="pred-confbar__row">\n'
        '                      <div class="pred-confbar__header">\n'
        '                        <span style="color:var(--status-down)">하락</span>\n'
        f'                        <span style="color:var(--text-secondary)">{down_pct}%</span>\n'
        "                      </div>\n"
        '                      <div class="pred-confbar__track">\n'
        f'                        <div class="pred-confbar__light" style="width:{down_light}%;background:var(--status-down-bg)"></div>\n'
        f'                        <div class="pred-confbar__solid down" style="width:{down_pct}%"></div>\n'
        "                      </div>\n"
        f'                      <div class="pred-confbar__meta">신뢰구간 {confidence}% → 최대 {down_light}%</div>\n'
        "                    </div>\n"
        "                  </div>\n"
        "                  <!-- Mobile: Diverging bar -->\n"
        '                  <div class="pred-divbar">\n'
        '                    <div class="pred-divbar__header">\n'
        f'                      <span style="color:var(--status-down)">하락 {down_pct}%</span>\n'
        f'                      <span style="color:var(--status-up)">상승 {up_pct}%</span>\n'
        "                    </div>\n"
        '                    <div class="pred-divbar__track">\n'
        f'                      <div class="pred-divbar__down" style="flex:{down_pct}">\n'
        f'                        <span class="pred-divbar__pct">{down_pct}%</span>\n'
        "                      </div>\n"
        f'                      <div class="pred-divbar__up" style="flex:{up_pct}">\n'
        f'                        <span class="pred-divbar__pct">{up_pct}%</span>\n'
        "                      </div>\n"
        "                    </div>\n"
        '                    <div class="pred-divbar__neutral">\n'
        '                      <div class="pred-divbar__tick"></div>\n'
        '                      <div class="pred-divbar__label">중립(50%)</div>\n'
        "                    </div>\n"
        "                  </div>\n"
        "                </div>\n"
        "              </div>\n"
        "\n"
        "              <!-- 2. 예측 근거 -->\n"
        '              <div class="open-section">\n'
        '                <div class="open-section__title">예측 근거</div>\n'
        '                <div class="reason-block">\n'
        "                  <ul>\n"
        + reasons_html + "\n"
        "                  </ul>\n"
        "                </div>\n"
        "              </div>\n"
        "\n"
        '              <div class="divider"></div>\n'
        "\n"
        "              <!-- 3. 잭 켈로그 전략 종목 -->\n"
        '              <div class="open-section">\n'
        '                <div class="open-section__title">\n'
        "                  잭 켈로그 20일선 전략 추종 종목\n"
        '                  <button class="info-btn" onclick="openKelloggModal()" aria-label="전략 설명">?</button>\n'
        "                </div>\n"
        '                <div style="font-size:13px; color:var(--text-secondary); margin-bottom:10px; line-height:1.7;">\n'
        "                  MA20을 상향 돌파하거나 정확히 지지 반등한 종목 중 거래량 급증을 동반한 모멘텀 종목만을 선별합니다.\n"
        "                </div>\n"
        '                <div class="stock-picks">'
        + picks_html + "\n"
        "                </div>\n"
        "              </div>\n"
        "\n"
        "            </div><!-- /accordion-body__inner -->\n"
        "          </div><!-- /accordion-body -->\n"
        "        </div><!-- /accordion-item -->\n"
        "\n"
        '        <div class="t-caption" style="margin-top:16px; text-align:right;">\n'
        f"          생성: {generated_at} | DailyB v1\n"
        "        </div>\n"
        "      </div><!-- /layout-grid__main -->\n"
        "\n"
        "      <!-- 오른쪽: 시장 지표 사이드바 -->\n"
        '      <aside class="layout-grid__right">\n'
        '        <div class="right-panel">\n'
        '          <div class="panel-header">\n'
        '            <span class="section-title">시장 지표</span>\n'
        f'            <span class="pub-time">{date_str} {gen_time}</span>\n'
        "          </div>\n"
        '          <div class="mkt-list">\n'
        + sidebar_groups + "\n"
        "          </div><!-- /mkt-list -->\n"
        "        </div><!-- /right-panel -->\n"
        "      </aside><!-- /layout-grid__right -->\n"
        "\n"
        "    </div><!-- /layout-grid -->\n"
        "  </div><!-- /layout-wrapper -->\n"
        "\n"
        "  <!-- 잭 켈로그 모달 -->\n"
        '  <div class="info-modal-backdrop" id="kellogg-modal" onclick="if(event.target===this)closeKelloggModal()">\n'
        '    <div class="info-modal" role="dialog" aria-modal="true" aria-labelledby="kellogg-modal-title">\n'
        '      <button class="info-modal__close" onclick="closeKelloggModal()" aria-label="닫기">\n'
        '        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>\n'
        "      </button>\n"
        '      <div class="info-modal__title" id="kellogg-modal-title">잭 켈로그 20일선 전략이란?</div>\n'
        '      <div class="info-modal__body">\n'
        "        <p>잭 켈로그(Zack Kellogg)의 20일 이동평균선(MA20) 전략은 단기 모멘텀을 이용한 스윙 트레이딩 기법입니다.</p>\n"
        "        <br>\n"
        "        <p><strong>선별 기준</strong></p>\n"
        '        <ul style="padding-left:16px; margin-top:6px; display:flex; flex-direction:column; gap:6px;">\n'
        "          <li>MA20을 <strong>상향 돌파</strong>하거나 정확히 <strong>지지 반등</strong>한 종목</li>\n"
        "          <li>돌파 시점에 <strong>거래량 급증</strong>을 동반한 종목</li>\n"
        "          <li>최소 <strong>3거래일 이상</strong> MA20 위에서 유지 중인 종목</li>\n"
        "        </ul>\n"
        "        <br>\n"
        '        <p style="color:var(--text-tertiary); font-size:12px;">※ 매매 추천이 아닌 전략 추종 종목 탐색 목적으로 제공됩니다.</p>\n'
        "      </div>\n"
        "    </div>\n"
        "  </div>\n"
        "\n"
        "  <!-- 공포탐욕지수 모달 -->\n"
        '  <div class="info-modal-backdrop" id="fg-modal" onclick="if(event.target===this)closeFGModal()">\n'
        '    <div class="info-modal" role="dialog" aria-modal="true" aria-labelledby="fg-modal-title">\n'
        '      <button class="info-modal__close" onclick="closeFGModal()" aria-label="닫기">\n'
        '        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>\n'
        "      </button>\n"
        '      <div class="info-modal__title" id="fg-modal-title">공포탐욕지수(Fear &amp; Greed Index)</div>\n'
        '      <div class="info-modal__body">\n'
        "        <p>시장의 7가지 요인을 분석하여 현재 투자자의 심리를 극단적인 공포(0)부터 극단적인 탐욕(100)까지 측정하는 심리지표입니다.</p>\n"
        "        <br>\n"
        '        <ul style="padding-left:16px; margin-top:0; display:flex; flex-direction:column; gap:8px;">\n'
        '          <li><strong style="color:#1D4ED8">0~24</strong> : 극단적 공포(Extreme Fear)</li>\n'
        '          <li><strong style="color:#2563EB">25~44</strong> : 공포(Fear)</li>\n'
        '          <li><strong style="color:#CA8A04">45~54</strong> : 중립(Neutral)</li>\n'
        '          <li><strong style="color:#E03131">55~74</strong> : 탐욕(Greed)</li>\n'
        '          <li><strong style="color:#B91C1C">75~100</strong> : 극단적 탐욕(Extreme Greed)</li>\n'
        "        </ul>\n"
        "      </div>\n"
        "    </div>\n"
        "  </div>\n"
        "\n"
        "  <!-- 시초가 예측 모달 -->\n"
        '  <div class="info-modal-backdrop" id="pred-modal" onclick="if(event.target===this)closePredModal()">\n'
        '    <div class="info-modal" role="dialog" aria-modal="true" aria-labelledby="pred-modal-title">\n'
        '      <button class="info-modal__close" onclick="closePredModal()" aria-label="닫기">\n'
        '        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>\n'
        "      </button>\n"
        '      <div class="info-modal__title" id="pred-modal-title">시초가 방향 예측이란?</div>\n'
        '      <div class="info-modal__body">\n'
        "        <p>미국 선물·지수, 외국인 수급, 반도체 지표, 공포탐욕지수 등 다수의 시장 데이터를 종합하여 AI가 다음 거래일 시초가 방향을 분석한 결과입니다.</p>\n"
        "        <br>\n"
        "        <p><strong>읽는 법</strong></p>\n"
        '        <ul style="padding-left:16px; margin-top:6px; display:flex; flex-direction:column; gap:6px;">\n'
        "          <li><strong>상승 우위</strong> — 상승 압력이 하락 압력보다 높다는 판단</li>\n"
        "          <li><strong>하락 우위</strong> — 하락 압력이 상승 압력보다 높다는 판단</li>\n"
        "          <li><strong>중립</strong> — 방향성 신호가 혼재되어 판단 보류</li>\n"
        "          <li><strong>신뢰도</strong> — 수집된 데이터의 일관성 수준 (높을수록 신호가 명확)</li>\n"
        "        </ul>\n"
        "        <br>\n"
        '        <p style="color:var(--text-tertiary); font-size:12px;">※ AI 분석 결과이며 투자 권고가 아닙니다. 실제 시장은 예측과 다를 수 있습니다.</p>\n'
        "      </div>\n"
        "    </div>\n"
        "  </div>\n"
        "\n"
        "  <script>\n"
        "  window.MARKET_DATA = " + market_data_json + ";\n"
        "  </script>\n"
        f'  <script src="{asset_prefix}assets/main.js"></script>\n'
        "</body>\n"
        "</html>"
    )
    return html


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate HTML briefing from analysis JSON")
    parser.add_argument("--type", choices=["kospi", "us", "weekly"], required=True)
    parser.add_argument("--data-file", required=True, help="Path to latest_{type}.json")
    parser.add_argument("--date", default=None, help="Date string (YYYY-MM-DD)")
    args = parser.parse_args()

    date_str = args.date or datetime.now(KST).strftime("%Y-%m-%d")

    try:
        data = load_data(args.data_file)
        analysis = load_analysis(args.type)
    except FileNotFoundError as e:
        print(f"[generate_html] ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if args.type == "weekly":
        html_briefing = f"<html><body><h1>Weekly Report {date_str}</h1></body></html>"
        html_index = html_briefing
    else:
        # briefings/*.html uses "../assets/" prefix
        html_briefing = build_full_html(data, analysis, date_str, args.type, asset_prefix="../")
        # index.html uses "assets/" prefix
        html_index = build_full_html(data, analysis, date_str, args.type, asset_prefix="")

    # Save to briefings archive
    filename = f"{date_str}-{args.type}.html"
    out_path = BRIEFINGS_DIR / filename
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_briefing)
    print(f"[generate_html] Saved → {out_path}")

    # Update index.html
    index_path = WEB_DIR / "index.html"
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html_index)
    print(f"[generate_html] index.html updated")


if __name__ == "__main__":
    main()
