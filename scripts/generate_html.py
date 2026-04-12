#!/usr/bin/env python3
"""
Generate HTML briefing pages from structured JSON data.
Uses the DailyB design system (VARCO dark/light tokens).
The agent fills in the analysis text; this script handles HTML structure.
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


def get_web_base_url() -> str:
    """Return web base URL — env var first, then config.json, then hardcoded default."""
    url = os.environ.get("WEB_BASE_URL")
    if url:
        return url.rstrip("/")
    config_file = BASE_DIR / "config.json"
    if config_file.exists():
        with open(config_file, encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg.get("web", {}).get("base_url", "").rstrip("/")
    return "https://bejewelled-toffee-87de55.netlify.app"


def fmt_change(val: float | None) -> tuple[str, str]:
    """Returns (formatted string, css class) for a change value."""
    if val is None:
        return "N/A", ""
    sign = "+" if val >= 0 else ""
    css = "up" if val >= 0 else "down"
    return f"{sign}{val:.2f}%", css


def load_data(data_file: str) -> dict:
    path = Path(data_file)
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {data_file}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_analysis(briefing_type: str) -> dict:
    """Load Claude's analysis output from data/analysis_{type}.json."""
    analysis_file = DATA_DIR / f"analysis_{briefing_type}.json"
    if analysis_file.exists():
        with open(analysis_file, encoding="utf-8") as f:
            return json.load(f)
    return {}


def build_kospi_html(data: dict, analysis: dict, date_str: str) -> str:
    sp500 = data.get("us_indices", {}).get("sp500", {})
    nasdaq = data.get("us_indices", {}).get("nasdaq", {})
    dow = data.get("us_indices", {}).get("dow", {})
    sox = data.get("sox", {})
    ewy = data.get("ewy", {})
    vix = data.get("vix", {})
    dxy = data.get("dxy", {})
    wti = data.get("oil", {}).get("wti", {})
    us10y = data.get("rates", {}).get("us10y", {})

    sp500_chg, sp500_cls = fmt_change(sp500.get("change_pct"))
    nasdaq_chg, nasdaq_cls = fmt_change(nasdaq.get("change_pct"))
    dow_chg, dow_cls = fmt_change(dow.get("change_pct"))
    sox_chg, sox_cls = fmt_change(sox.get("change_pct"))
    ewy_chg, ewy_cls = fmt_change(ewy.get("change_pct"))
    dxy_chg, dxy_cls = fmt_change(dxy.get("change_pct"))
    wti_chg, wti_cls = fmt_change(wti.get("change_pct"))

    pred = analysis.get("prediction", {})
    up_pct = pred.get("up_pct", 50)
    down_pct = pred.get("down_pct", 50)
    direction = pred.get("direction", "중립")
    confidence = pred.get("confidence", 70)
    reasons = analysis.get("reasons", [])
    stock_picks = analysis.get("stock_picks", [])
    generated_at = data.get("generated_at", datetime.now(KST).isoformat())

    reasons_html = "\n".join(
        f"<li>{r}</li>" for r in reasons
    ) if reasons else "<li>데이터 수집 중...</li>"

    picks_html = ""
    for i, pick in enumerate(stock_picks, 1):
        ma20_dist = pick.get("ma20_dist_pct", 0)
        ma200_dist = pick.get("ma200_dist_pct", 0)
        ma20_cls = "up" if ma20_dist >= 0 else "down"
        ma200_cls = "up" if ma200_dist >= 0 else "down"
        ma200_w = min(abs(ma200_dist) * 10, 100)
        golden = '<span class="golden-badge">★ GOLDEN</span>' if pick.get("golden") else ""
        picks_html += f"""
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
                <span class="stock-pick-card__change {pick.get('change_cls', 'up')}">{pick.get('change', '')}</span>
              </div>
              <div class="ma200-gauge">
                <span class="ma200-gauge__label">200일선 대비</span>
                <div class="ma200-gauge__track">
                  <div class="ma200-gauge__fill {ma200_cls}" style="width:{ma200_w:.0f}%"></div>
                </div>
                <span class="ma200-gauge__pct {ma200_cls}">{'+' if ma200_dist >= 0 else ''}{ma200_dist:.1f}% {'상회' if ma200_dist >= 0 else '하회'}</span>
              </div>
              <div class="stock-pick-card__scenario">
                <span class="scenario-tag">{pick.get("scenario_tag", "단기 반등")}</span>
                {pick.get("scenario", "")}
              </div>
            </div>
          </div>
          <div class="stock-pick-card__cta">
            <span class="cta-label">실행 가이드</span>
            {pick.get("action_guide", "")}
          </div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="ko" class="dark">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Daily30' — 코스피 시초가 브리핑 {date_str}</title>
  <link rel="stylesheet" href="../assets/style.css" />
</head>
<body>
  <nav class="gnb">
    <div class="gnb__inner">
      <div class="gnb__logo">
        <div class="gnb__logo-mark">
          <svg viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5">
            <polyline points="22 7 13.5 15.5 8.5 10.5 2 17"></polyline>
            <polyline points="16 7 22 7 22 13"></polyline>
          </svg>
        </div>
        <span class="gnb__title">Daily<span>30'</span></span>
      </div>
      <div class="gnb__meta">
        <span class="gnb__date">{date_str} KST 08:30</span>
        <span class="gnb__badge">코스피</span>
      </div>
    </div>
  </nav>

  <div class="layout-wrapper">
    <!-- 핵심 지표 요약 -->
    <div class="market-summary-bar">
      <div class="mkt-item">
        <span class="mkt-item__label">S&P500</span>
        <span class="mkt-item__val {sp500_cls}">{sp500_chg}</span>
      </div>
      <div class="mkt-item">
        <span class="mkt-item__label">NASDAQ</span>
        <span class="mkt-item__val {nasdaq_cls}">{nasdaq_chg}</span>
      </div>
      <div class="mkt-item">
        <span class="mkt-item__label">SOX</span>
        <span class="mkt-item__val {sox_cls}">{sox_chg}</span>
      </div>
      <div class="mkt-item">
        <span class="mkt-item__label">EWY</span>
        <span class="mkt-item__val {ewy_cls}">{ewy_chg}</span>
      </div>
      <div class="mkt-item">
        <span class="mkt-item__label">VIX</span>
        <span class="mkt-item__val">{vix.get('price', 'N/A')}</span>
      </div>
      <div class="mkt-item">
        <span class="mkt-item__label">DXY</span>
        <span class="mkt-item__val {dxy_cls}">{dxy_chg}</span>
      </div>
      <div class="mkt-item">
        <span class="mkt-item__label">WTI</span>
        <span class="mkt-item__val {wti_cls}">{wti_chg}</span>
      </div>
      <div class="mkt-item">
        <span class="mkt-item__label">미10년물</span>
        <span class="mkt-item__val">{us10y.get('price', 'N/A')}%</span>
      </div>
    </div>

    <!-- 예측 카드 -->
    <div class="accordion-item is-open is-today">
      <div class="accordion-header">
        <div class="accordion-header__date-label">{date_str}</div>
        <div class="accordion-header__badges">
          <span class="pred-badge {'up' if direction == '상승 우위' else 'down'}">{direction}</span>
        </div>
      </div>

      <div class="accordion-body">
        <!-- 1. 예측 -->
        <div class="open-section">
          <div class="open-section__title">코스피 시초가 방향 예측</div>
          <div class="prediction-card">
            <div class="prediction-summary">
              <span class="prediction-label">{direction} 예측 (신뢰도 {confidence}%)</span>
              <span class="prediction-confidence">08:30 생성</span>
            </div>
            <div class="bar-chart">
              <div class="bar-row">
                <div class="bar-row__label"><span class="dot" style="background:var(--status-up)"></span>상승</div>
                <div class="bar-row__track"><div class="bar-row__fill up" style="width:{up_pct}%"></div></div>
                <span class="bar-row__pct up">{up_pct}%</span>
              </div>
              <div class="bar-row">
                <div class="bar-row__label"><span class="dot" style="background:var(--status-down)"></span>하락</div>
                <div class="bar-row__track"><div class="bar-row__fill down" style="width:{down_pct}%"></div></div>
                <span class="bar-row__pct down">{down_pct}%</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 2. 예측 근거 -->
        <div class="open-section">
          <div class="open-section__title">예측 근거</div>
          <div class="reason-block">
            <ul>{reasons_html}</ul>
          </div>
        </div>

        <div class="divider"></div>

        <!-- 3. 잭 켈로그 전략 종목 -->
        <div class="open-section">
          <div class="open-section__title">잭 켈로그 20일선 전략 추종 종목</div>
          <div style="font-size:13px; color:var(--text-secondary); margin-bottom:10px; line-height:1.7;">
            MA20을 상향 돌파하거나 정확히 지지 반등한 종목 중 거래량 급증을 동반한 모멘텀 종목만을 선별합니다.
          </div>
          <div class="stock-picks">{picks_html}</div>
        </div>
      </div>
    </div>

    <div class="t-caption" style="margin-top:16px; text-align:right;">
      생성: {generated_at} | DailyB v1
    </div>
  </div>

  <script src="../assets/main.js"></script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Generate HTML briefing")
    parser.add_argument("--type", choices=["kospi", "us", "weekly"], required=True)
    parser.add_argument("--data-file", required=True, help="Path to the data JSON file")
    parser.add_argument("--date", default=None, help="Date string (YYYY-MM-DD)")
    args = parser.parse_args()

    date_str = args.date or datetime.now(KST).strftime("%Y-%m-%d")

    try:
        data = load_data(args.data_file)
        analysis = load_analysis(args.type)
    except FileNotFoundError as e:
        print(f"[generate_html] ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if args.type == "kospi":
        html_content = build_kospi_html(data, analysis, date_str)
    elif args.type == "us":
        # US template — same structure, different data sections
        # For brevity, reuse kospi builder with US data adaptation
        html_content = build_kospi_html(data, analysis, date_str)
    else:
        html_content = f"<html><body><h1>Weekly Report {date_str}</h1></body></html>"

    # Save to briefings archive
    filename = f"{date_str}-{args.type}.html"
    out_path = BRIEFINGS_DIR / filename
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"[generate_html] Saved → {out_path}")

    # Update index.html
    index_path = WEB_DIR / "index.html"
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"[generate_html] index.html updated")


if __name__ == "__main__":
    main()
