# 해설 글 초안(md)을 /guides/ 정적 페이지로 바꾸는 생성 스크립트 — 숫자·그래프는 글 쓴 날 기준으로 굳는다(§87)
import html, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(__file__).resolve().parents[1] / "docs/plans/2026-11-13-adsense-articles/data"
DRAFTS = ROOT / "docs/plans/2026-11-13-adsense-articles"
TPL = (ROOT / "web/guides/accuracy-baseline/index.html").read_text()
SITE = "https://doubleshot.space"

HEAD = TPL[:TPL.index("<title>")]
STYLE = TPL[TPL.index("<style>"):TPL.index("</style>") + 8]
STYLE = STYLE.replace("</style>", """.g-tbl th.n{text-align:right;}
.g-tbl th:not(.n){text-align:left !important;}
.g-tbl td:first-child{white-space:nowrap;}
@media(max-width:420px){.g-tbl th,.g-tbl td{padding:8px 6px;}}
.g-fig{margin:14px 0 6px;}
.g-fig svg{width:100%;height:auto;display:block;}
.g-fig figcaption{font-size:12.5px;color:var(--muted);line-height:1.6;margin-top:6px;}
.g-ax{fill:var(--muted);font-size:12px;font-family:inherit;}
.g-lb{fill:var(--ink);font-size:12.5px;font-weight:700;font-family:inherit;}
.g-grid{stroke:var(--hairline);stroke-width:1;}
.g-line{fill:none;stroke:#2775ED;stroke-width:2;stroke-linejoin:round;}
.g-ink{fill:none;stroke:var(--ink);stroke-width:1.6;stroke-linejoin:round;}
.legal-sec ul.g-guide-list{padding:0;}
.g-guide-list{list-style:none;padding:0;margin:8px 0 0;display:grid;gap:12px;}
.g-guide-list li{padding:16px 18px;border:1px solid var(--hairline);border-radius:12px;}
.g-guide-list a{font-size:16px;font-weight:700;color:var(--ink);text-decoration:none;}
.g-guide-list a:hover{color:#2775ED;}
.g-guide-list p{margin:6px 0 0;font-size:13.5px;color:var(--muted);line-height:1.65;}
</style>""")
GNB = next(l for l in TPL.split("\n") if 'class="gnb' in l)
FOOT = next(l for l in TPL.split("\n") if 'class="legal-foot"' in l)
if 'href="/guides/"' not in FOOT:
    FOOT = FOOT.replace('<a href="/methodology/">방법론</a>', '<a href="/methodology/">방법론</a><a href="/guides/">해설 글</a>')
ADS = '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-7262578476089316" crossorigin="anonymous"></script>\n'
DATE_ISO = "2026-11-16T12:00:00+09:00"

GUIDES = [
    {"slug": "accuracy-baseline", "title": "예측 적중률 70%는 높은 걸까 — '매일 상승'과 나란히 보는 법",
     "desc": "예측 적중률은 아무것도 안 해도 맞는 비율(기준선)과 나란히 봐야 해요. 더블샷이 매일 채점한 기록으로 적중률을 읽는 법을 짚었어요."},
    {"slug": "aftermarket-close", "title": "주식 종가가 사이트마다 다른 이유 — 애프터마켓 이후 '종가'의 뜻",
     "h1": "주식 종가가 사이트마다 다른 이유", "sub": "애프터마켓 이후 '종가'의 뜻 · 2026년 11월 16일 · 숫자는 11월 13일 거래분까지",
     "desc": "2026년 9월 애프터마켓이 열린 뒤 공식 종가와 포털 일봉 종가가 거의 매일 달라요. 실제 1분봉으로 차이를 재고, 어떤 숫자를 종가로 봐야 하는지 정리했어요.",
     "draft": "draft-02-aftermarket-close.md"},
    {"slug": "nasdaq-5y-average", "title": "나스닥이 5년 평균보다 60% 높으면 위험할까 — 1990년부터 442개월 기록",
     "h1": "나스닥이 5년 평균보다 60% 높으면 위험할까", "sub": "1990년부터 442개월 기록 · 2026년 11월 16일 · 지금 값은 11월 13일 종가",
     "desc": "나스닥 종합지수가 5년 평균보다 60%, 70% 위에 있었을 때 1년 뒤 무슨 일이 있었는지 1990년부터 442개월 기록으로 정리했어요.",
     "draft": "draft-03-nasdaq-overheat.md"},
    {"slug": "kospi-open-us-signals", "title": "코스피 시초가는 왜 밤사이 미국장을 따라갈까 — 727거래일로 확인한 신호",
     "h1": "코스피 시초가는 왜 밤사이 미국장을 따라갈까", "sub": "727거래일로 확인한 신호 · 2026년 11월 17일 · 숫자는 11월 17일 시초가까지",
     "desc": "밤사이 미국 반도체·나스닥·EWY·VIX·환율 가운데 무엇이 다음 날 코스피 시초가를 잘 설명했는지 2023년 11월부터 727거래일 기록으로 정리했어요.",
     "draft": "draft-04-kospi-open-us-signals.md", "date": "2026-11-17T12:00:00+09:00"},
    {"slug": "monthly-ma5-test", "title": "월봉 5개월선 위에 3개월 안착하면 오를까 — 코스피200 15년 검증",
     "h1": "월봉 5개월선 위에 3개월 안착하면 오를까", "sub": "코스피200 15년 검증 · 2026년 11월 26일 · 백테스트는 2026년 10월 25일 계산",
     "desc": "'월봉이 5개월 이동평균선 위에 3개월 안착하면 오른다'는 말을 코스피200 종목 2011~2025년 기록으로 확인했어요. 아무 달에나 산 것과 거의 같았어요.",
     "draft": "draft-05-monthly-ma5.md", "date": "2026-11-26T12:00:00+09:00"},
    {"slug": "sp-futures-close", "title": "밤 9시 S&P 선물로 그날 미국장 방향을 얼마나 맞힐까 — 593거래일 기록",
     "h1": "밤 9시 S&P 선물로 그날 미국장 방향을 얼마나 맞힐까", "sub": "593거래일 기록 · 2026년 11월 26일 · 구간표는 2026년 11월 3일 계산",
     "desc": "한국 시간 밤 9시의 S&P500 선물 변화로 그날 미국장이 오르며 끝날지를 얼마나 맞힐 수 있는지 2024년 6월부터 593거래일 기록으로 정리했어요.",
     "draft": "draft-06-sp-futures-close.md", "date": "2026-11-26T12:00:00+09:00"},
    {"slug": "income-etf-yield", "title": "월배당 ETF, 분배율이 높으면 좋은 걸까 — 76개 ETF의 1년 가격 변화",
     "h1": "월배당 ETF, 분배율이 높으면 좋은 걸까", "sub": "76개 ETF의 1년 가격 변화 · 2026년 11월 26일 · 국내 11월 24일·미국 11월 25일 종가",
     "desc": "분배율과 1년 가격 변화를 나란히 보면 월배당 ETF의 실제 수익이 보여요. 국내 60개·미국 16개 월배당 ETF 기록으로 분배율 구간별·종류별 차이를 정리했어요.",
     "draft": "draft-07-income-yield.md", "date": "2026-11-26T12:00:00+09:00"},
]


def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
    return s


def table(lines):
    rows = [[c.strip() for c in l.strip().strip("|").split("|")] for l in lines if not re.match(r"^\|\s*-", l)]
    head, body = rows[0], rows[1:]
    num = lambda c: len(c) <= 24 and bool(re.match(r"^[\s*+−\-]*[\d,.]+", c.replace("**", "")))
    ncol = [i > 0 and all(num(r[i]) for r in body if i < len(r)) for i in range(len(head))]
    cl = lambda i: ' class="n"' if ncol[i] else ""
    th = "".join("<th" + cl(i) + ">" + inline(c) + "</th>" for i, c in enumerate(head))
    trs = "".join("<tr>" + "".join("<td" + cl(i) + ">" + inline(c) + "</td>" for i, c in enumerate(r)) + "</tr>" for r in body)
    return f'<table class="g-tbl"><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>'


def md_body(md, charts):
    parts = md.split("\n---\n")
    body, src = parts[1], parts[2]
    out, sec_open, i = [], False, 0
    lines = body.strip("\n").split("\n")
    lead_done = False
    while i < len(lines):
        l = lines[i]
        if l.startswith("## "):
            if sec_open: out.append("  </section>")
            out.append('  <section class="legal-sec">'); out.append(f"    <h2>{inline(l[3:])}</h2>"); sec_open = True
        elif l.startswith("> "):  # 인용 묶음 — '운영자 한마디'만 상자로 싣고 나머지 인용은 싣지 않는다
            blk = []
            while i < len(lines) and lines[i].startswith("> "):
                blk.append(lines[i][2:]); i += 1
            if "운영자 한마디" in blk[0] and len(blk) > 1:
                out.append('    <div class="g-note"><p class="g-note-h">운영자 한마디</p>'
                           + "".join(f"<p>{inline(x)}</p>" for x in blk[1:]) + "</div>")
            continue
        elif l.startswith("[그래프 자리"):
            out.append(charts.pop(0))
        elif l.startswith("|"):
            blk = []
            while i < len(lines) and lines[i].startswith("|"):
                blk.append(lines[i]); i += 1
            out.append("    " + table(blk)); continue
        elif l.startswith("- "):
            blk = []
            while i < len(lines) and lines[i].startswith("- "):
                blk.append(f"<li>{inline(lines[i][2:])}</li>"); i += 1
            out.append("    <ul>" + "".join(blk) + "</ul>"); continue
        elif l.strip():
            if not lead_done and not sec_open:
                out.append(f'  <p class="legal-lead">{inline(l)}</p>'); lead_done = True
            else:
                out.append(f"    <p>{inline(l)}</p>")
        i += 1
    if sec_open: out.append("  </section>")
    items = [inline(x[2:]) for x in src.strip().split("\n") if x.startswith("- ")]
    out.insert(-1, '    <ul class="g-src">' + "".join(f"<li>{x}</li>" for x in items) + "</ul>")
    return "\n".join(out)


def chart_close():
    pts = json.load(open(DATA / "samsung_1min_20261113.json"))
    W, H, L, R, T, B = 420, 230, 54, 10, 22, 30
    tm = lambda hhmm: (int(hhmm[:2]) - 15) * 60 + int(hhmm[2:])
    x = lambda m: L + (W - L - R) * m / 300
    lo, hi = 205500, 209500
    y = lambda p: T + (H - T - B) * (hi - p) / (hi - lo)
    d, prev = [], None
    for t, p in pts:  # 계단선 — 체결이 없던 분은 직전 가격 유지
        X, Y = x(tm(t)), y(p)
        if prev is None: d.append(f"M{X:.1f},{Y:.1f}")
        else: d.append(f"H{X:.1f}V{Y:.1f}")
        prev = Y
    d.append(f"H{x(300):.1f}")
    g = []
    for p in (206000, 207000, 208000, 209000):
        g.append(f'<line class="g-grid" x1="{L}" x2="{W-R}" y1="{y(p):.1f}" y2="{y(p):.1f}"/><text class="g-ax" x="{L-6}" y="{y(p)+4:.1f}" text-anchor="end">{p:,}</text>')
    for h in range(15, 21):
        X = x((h - 15) * 60)
        g.append(f'<text class="g-ax" x="{X:.1f}" y="{H-12}" text-anchor="{"end" if h == 20 else "middle"}">{h}:00</text>')
    band = f'<rect x="{x(30):.1f}" y="{T}" width="{x(60)-x(30):.1f}" height="{H-T-B}" fill="var(--surface-inset,#F1F3F5)"/>'
    vl = "".join(f'<line x1="{x(m):.1f}" x2="{x(m):.1f}" y1="{T}" y2="{H-B}" stroke="var(--muted)" stroke-dasharray="3 3"/>' for m in (30, 60))
    close = f'<line x1="{L}" x2="{W-R}" y1="{y(206000):.1f}" y2="{y(206000):.1f}" stroke="#E03131" stroke-width="1.4" stroke-dasharray="5 4"/>'
    labels = (f'<text class="g-lb" x="{x(64):.1f}" y="{y(206000)+18:.1f}" fill="#E03131" style="fill:#E03131">공식 종가 206,000</text>'
              f'<text class="g-ax" x="{x(45):.1f}" y="{T+14}" text-anchor="middle">종가로만</text>'
              f'<text class="g-ax" x="{x(180):.1f}" y="{T+14}" text-anchor="middle">애프터마켓</text>'
              f'<circle cx="{x(299):.1f}" cy="{y(209000):.1f}" r="4" fill="#2775ED"/>'
              f'<text class="g-lb" x="{x(296):.1f}" y="{y(209000)+18:.1f}" text-anchor="end">19:59 209,000 = 일봉 종가</text>')
    svg = (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="2026년 11월 13일 삼성전자 15시부터 20시까지 1분봉 가격">'
           f'{band}{"".join(g)}{vl}{close}<path class="g-line" d="{"".join(d)}"/>{labels}</svg>')
    return ('    <figure class="g-fig">' + svg +
            '<figcaption>2026년 11월 13일 삼성전자 1분봉(네이버 증권). 15:30에 공식 종가 206,000원이 정해지고, 15:31~15:59는 그 가격으로만 거래돼요. 16시부터 가격이 다시 움직여 19:59에 209,000원으로 끝났어요.</figcaption></figure>')


def chart_nasdaq():
    sys.path.insert(0, str(ROOT / "scripts"))
    import nasdaq_overheat as nq
    months = json.load(open(ROOT / "scripts/fixtures/nasdaq_monthly_20261023.json"))["months"]
    gs = [g for g in nq.gap_series(months) if g and g["m"] >= "1990-01"]
    W, H, L, R, T, B = 420, 250, 48, 10, 14, 26
    n = len(gs)
    x = lambda i: L + (W - L - R) * i / (n - 1)
    lo, hi = -50, 190
    y = lambda v: T + (H - T - B) * (hi - v) / (hi - lo)
    d = "M" + "L".join(f"{x(i):.1f},{y(g['g']):.1f}" for i, g in enumerate(gs))
    out = []
    for v in (-50, 0, 50, 100, 150):
        out.append(f'<line class="g-grid" x1="{L}" x2="{W-R}" y1="{y(v):.1f}" y2="{y(v):.1f}"/><text class="g-ax" x="{L-6}" y="{y(v)+4:.1f}" text-anchor="end">{v:+d}%</text>'.replace("+0%", "0%"))
    for v, c, lab in ((60, "#E8A33D", "주의 60%"), (70, "#E03131", "경고 70%")):
        out.append(f'<line x1="{L}" x2="{W-R}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="{c}" stroke-width="1.2" stroke-dasharray="5 4"/>')
    out.append(f'<text class="g-ax" x="{W-R}" y="{y(70)-5:.1f}" text-anchor="end" style="fill:#E03131">경고 70%</text>')
    out.append(f'<text class="g-ax" x="{W-R}" y="{y(60)+13:.1f}" text-anchor="end" style="fill:#C98420">주의 60%</text>')
    idx = {g["m"]: i for i, g in enumerate(gs)}
    for yr in (1990, 2000, 2010, 2020):
        i = idx[f"{yr}-01"]
        out.append(f'<text class="g-ax" x="{x(i):.1f}" y="{H-10}" text-anchor="middle">{yr}</text>')
    marks = [("2000-03", "2000.3 +182%", "start", 6, 4), ("2002-09", "2002.9 −43%", "start", 8, 5),
             ("2021-02", "2021.2 +84%", "end", -6, -6)]
    for m, lab, anc, dx, dy in marks:
        i = idx[m]; X, Y = x(i), y(gs[i]["g"])
        out.append(f'<circle cx="{X:.1f}" cy="{Y:.1f}" r="3.5" fill="var(--ink)"/><text class="g-lb" x="{X+dx:.1f}" y="{Y+dy:.1f}" text-anchor="{anc}">{lab}</text>')
    svg = (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="1990년부터 2026년 10월까지 나스닥 종합지수가 5년 평균보다 몇 % 위에 있었는지">'
           f'{"".join(out[:5])}<path class="g-ink" d="{d}"/>{"".join(out[5:])}</svg>')
    return ('    <figure class="g-fig">' + svg +
            '<figcaption>달마다 나스닥 종합지수 고점이 최근 60개월 월말 종가 평균보다 몇 % 위였는지(1990년 1월~2026년 10월, 야후 파이낸스 ^IXIC로 계산). 70%를 넘은 달은 1997~2000년과 2020~2021년에 몰려 있어요.</figcaption></figure>')


def chart_open_years():
    d = json.load(open(DATA / "kospi_open_gap_20261117.json"))
    W, H, L, R, T, B = 420, 220, 36, 8, 22, 28
    y = lambda v: T + (H - T - B) * (100 - v) / 100
    out = []
    for v in (0, 25, 50, 75, 100):
        out.append(f'<line class="g-grid" x1="{L}" x2="{W-R}" y1="{y(v):.1f}" y2="{y(v):.1f}"/><text class="g-ax" x="{L-6}" y="{y(v)+4:.1f}" text-anchor="end">{v}%</text>')
    gw = (W - L - R) / len(d["years"]); bw = gw * 0.3
    for i, r in enumerate(d["years"]):
        cx = L + gw * (i + 0.5)
        for v, dx, fill, cls in ((r["base"], -bw * 0.55, "#B5BCC7", "g-ax"), (r["model"], bw * 0.55, "#2775ED", "g-lb")):
            X = cx + dx - bw / 2
            out.append(f'<rect x="{X:.1f}" y="{y(v):.1f}" width="{bw:.1f}" height="{y(0)-y(v):.1f}" rx="2" fill="{fill}"/>'
                       f'<text class="{cls}" x="{X+bw/2:.1f}" y="{y(v)-5:.1f}" text-anchor="middle">{v:.0f}</text>')
        out.append(f'<text class="g-ax" x="{cx:.1f}" y="{H-9}" text-anchor="middle">{r["y"]}</text>')
    leg = (f'<rect x="{L}" y="4" width="10" height="10" rx="2" fill="#B5BCC7"/><text class="g-ax" x="{L+14}" y="13">매일 \'위로\'만 찍었을 때</text>'
           f'<rect x="{L+150}" y="4" width="10" height="10" rx="2" fill="#2775ED"/><text class="g-ax" x="{L+164}" y="13">미국 신호로 예측</text>')
    svg = (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="연도별 코스피 시초가 방향 적중률 — 매일 위로 찍었을 때와 미국 신호로 예측했을 때">'
           f'{"".join(out)}{leg}</svg>')
    return ('    <figure class="g-fig">' + svg +
            f'<figcaption>코스피 시초가가 전날 종가보다 높게 열릴지 맞힌 비율(%). {d["from"][:4]}년 11월~{d["to"][:4]}년 11월 {d["days"]}거래일, 2026년 11월 17일에 다시 계산했어요.</figcaption></figure>')


def chart_open_signals():
    d = json.load(open(DATA / "kospi_open_gap_20261117.json"))
    rows = d["signals"]
    W, L, R, T, rh = 420, 150, 34, 8, 26
    H = T + rh * len(rows) + 26
    x = lambda v: L + (W - L - R) * (v - 30) / 50     # 30~80% 구간을 그린다
    out = []
    for v in (30, 40, 50, 60, 70, 80):
        out.append(f'<line class="g-grid" x1="{x(v):.1f}" x2="{x(v):.1f}" y1="{T}" y2="{T+rh*len(rows)}"/><text class="g-ax" x="{x(v):.1f}" y="{H-8}" text-anchor="middle">{v}%</text>')
    for i, r in enumerate(rows):
        Y = T + rh * i
        dim = r["k"] in ("ewy", "usdkrw")
        out.append(f'<text class="g-ax" x="{L-8}" y="{Y+rh/2+4:.1f}" text-anchor="end" style="fill:var(--ink)">{html.escape(r["name"])}</text>'
                   f'<rect x="{x(30):.1f}" y="{Y+6:.1f}" width="{x(r["hit"])-x(30):.1f}" height="{rh-12}" rx="2" fill="{"#B5BCC7" if dim else "#2775ED"}"/>'
                   f'<text class="g-lb" x="{x(r["hit"])+4:.1f}" y="{Y+rh/2+4:.1f}">{r["hit"]:.1f}</text>')
    for v, c, lab in ((50, "var(--muted)", "동전 50%"), (59.6, "#E03131", "매일 위로 59.6%")):
        out.append(f'<line x1="{x(v):.1f}" x2="{x(v):.1f}" y1="{T-4}" y2="{T+rh*len(rows)}" stroke="{c}" stroke-width="1.2" stroke-dasharray="4 3"/>')
    svg = (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="밤사이 미국 숫자별 코스피 시초가 방향 부호 적중률">{"".join(out)}</svg>')
    return ('    <figure class="g-fig">' + svg +
            '<figcaption>숫자 하나만으로 다음 날 시초가 방향을 맞힌 비율(%). 빨간 점선은 매일 \'위로\'만 찍었을 때(59.6%), 회색 점선은 동전 던지기(50%)예요. 회색 막대 둘(EWY 그대로·원/달러)은 더블샷이 쓰지 않는 형태예요.</figcaption></figure>')


def _bars(rows, aria, cap, ymax=100, base=None, base_lab=None):
    """세로 막대 하나씩 — rows = [(아래 글자, 값, 색)]. base가 있으면 빨간 점선."""
    W, H, L, R, T, B = 420, 220, 36, 8, 22, 34
    y = lambda v: T + (H - T - B) * (ymax - v) / ymax
    out = []
    for v in range(0, ymax + 1, 25):
        out.append(f'<line class="g-grid" x1="{L}" x2="{W-R}" y1="{y(v):.1f}" y2="{y(v):.1f}"/><text class="g-ax" x="{L-6}" y="{y(v)+4:.1f}" text-anchor="end">{v}%</text>')
    gw = (W - L - R) / len(rows); bw = min(gw * 0.56, 44)
    for i, (lab, v, fill) in enumerate(rows):
        cx = L + gw * (i + 0.5)
        out.append(f'<rect x="{cx-bw/2:.1f}" y="{y(v):.1f}" width="{bw:.1f}" height="{y(0)-y(v):.1f}" rx="2" fill="{fill}"/>'
                   f'<text class="g-lb" x="{cx:.1f}" y="{y(v)-5:.1f}" text-anchor="middle">{v:.0f}</text>'
                   f'<text class="g-ax" x="{cx:.1f}" y="{H-14}" text-anchor="middle">{html.escape(lab)}</text>')
    if base is not None:
        out.append(f'<line x1="{L}" x2="{W-R}" y1="{y(base):.1f}" y2="{y(base):.1f}" stroke="#E03131" stroke-width="1.2" stroke-dasharray="4 3"/>'
                   f'<text class="g-ax" x="{L+4}" y="{y(base)-5:.1f}" style="fill:#E03131">{html.escape(base_lab)}</text>')
    svg = f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(aria)}">{"".join(out)}</svg>'
    return '    <figure class="g-fig">' + svg + f'<figcaption>{cap}</figcaption></figure>'


def chart_ma5():
    d = json.load(open(DATA / "monthly_ma5_20261126.json"))["kr"]["horizons"]
    W, H, L, R, T, B = 420, 220, 36, 8, 22, 28
    y = lambda v: T + (H - T - B) * (60 - v) / 60
    out = []
    for v in (0, 20, 40, 60):
        out.append(f'<line class="g-grid" x1="{L}" x2="{W-R}" y1="{y(v):.1f}" y2="{y(v):.1f}"/><text class="g-ax" x="{L-6}" y="{y(v)+4:.1f}" text-anchor="end">{v}%</text>')
    hs = ("3", "6", "12"); gw = (W - L - R) / 3; bw = gw * 0.3
    for i, h in enumerate(hs):
        cx = L + gw * (i + 0.5)
        for v, dx, fill, cls in ((d[h]["base"]["win_pct"], -bw * 0.55, "#B5BCC7", "g-ax"), (d[h]["signal"]["win_pct"], bw * 0.55, "#2775ED", "g-lb")):
            X = cx + dx - bw / 2
            out.append(f'<rect x="{X:.1f}" y="{y(v):.1f}" width="{bw:.1f}" height="{y(0)-y(v):.1f}" rx="2" fill="{fill}"/>'
                       f'<text class="{cls}" x="{X+bw/2:.1f}" y="{y(v)-5:.1f}" text-anchor="middle">{v:.1f}</text>')
        out.append(f'<text class="g-ax" x="{cx:.1f}" y="{H-9}" text-anchor="middle">{h}개월 뒤</text>')
    leg = (f'<rect x="{L}" y="4" width="10" height="10" rx="2" fill="#B5BCC7"/><text class="g-ax" x="{L+14}" y="13">아무 달에나 샀을 때</text>'
           f'<rect x="{L+140}" y="4" width="10" height="10" rx="2" fill="#2775ED"/><text class="g-ax" x="{L+154}" y="13">조건을 채운 뒤</text>')
    svg = f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="월봉 5개월선 안착 조건 뒤 오른 비율과 아무 달에나 샀을 때 비교">{"".join(out)}{leg}</svg>'
    return ('    <figure class="g-fig">' + svg +
            '<figcaption>산 뒤 3·6·12개월이 지나 가격이 올라 있던 비율(%). 코스피200 현재 구성 종목, 신호 2011년 1월~2025년 8월.</figcaption></figure>')


def chart_sp_bands():
    d = json.load(open(DATA / "us_close_prior_20261126.json"))
    labs = ("−0.5↓", "−0.5~−0.2", "−0.2~0", "0~+0.2", "+0.2~+0.5", "+0.5↑")
    base = sum(b["days"] * b["up_pct"] for b in d["bands"]) / sum(b["days"] for b in d["bands"])
    rows = [(l, b["up_pct"], "#2775ED" if b["up_pct"] >= 50 else "#5D97F1") for l, b in zip(labs, d["bands"])]
    return _bars(rows, "밤 9시 S&P500 선물 변화 구간별 그날 상승 마감 비율",
                 f'밤 9시 15분 선물 변화(%) 구간별로 그날 S&P500이 오르며 끝난 비율(%). 빨간 점선은 아무 날이나 골랐을 때({base:.1f}%). 2024년 6월~2026년 11월 {d["days"]}거래일.',
                 base=base, base_lab=f"아무 날 {base:.1f}%")


def chart_income():
    d = json.load(open(DATA / "income_etfs_20261126.json"))["etfs"]
    bk = ((0, 5, "5% 미만"), (5, 10, "5~10%"), (10, 15, "10~15%"), (15, 25, "15~25%"), (25, 1000, "25% 이상"))
    rows = []
    for lo, hi, lab in bk:
        g = [e for e in d if lo <= e["yield_ttm"] < hi]
        rows.append((lab, 100 * sum(e["price_1y"] < 0 for e in g) / len(g), "#5D97F1" if lo >= 10 else "#B5BCC7"))
    return _bars(rows, "분배율 구간별 1년 가격이 내린 월배당 ETF 비율",
                 '분배율 구간마다 1년 전보다 가격이 내린 ETF의 비율(%). 국내 60개·미국 16개 월배당 ETF, 국내 2026년 11월 24일·미국 11월 25일 종가.')


def page(slug, title, desc, crumb_title, h1, sub, body, article=True, date=DATE_ISO):
    url = f"{SITE}/guides/{slug}/" if slug else f"{SITE}/guides/"
    lds = []
    if article:
        lds.append({"@context": "https://schema.org", "@type": "Article", "headline": title, "description": desc,
                    "datePublished": date, "dateModified": date, "inLanguage": "ko-KR", "mainEntityOfPage": url,
                    "author": {"@type": "Organization", "name": "더블샷", "alternateName": "Double-Shot", "url": f"{SITE}/about/"},
                    "publisher": {"@type": "Organization", "name": "더블샷", "alternateName": "Double-Shot",
                                  "logo": {"@type": "ImageObject", "url": f"{SITE}/icons/icon-512.png"}}})
    items = [{"@type": "ListItem", "position": 1, "name": "홈", "item": f"{SITE}/stocks/"},
             {"@type": "ListItem", "position": 2, "name": "해설 글", "item": f"{SITE}/guides/"}]
    if slug: items.append({"@type": "ListItem", "position": 3, "name": crumb_title})
    lds.append({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": items})
    ld = "".join(f'<script type="application/ld+json">{json.dumps(x, ensure_ascii=False, separators=(",", ":"))}</script>\n' for x in lds)
    e = lambda s: html.escape(s, quote=True)
    head = (HEAD + f"<title>{e(title)} | 더블샷(Double-Shot)</title>\n"
            f'<meta name="description" content="{e(desc)}">\n'
            '<meta name="robots" content="index, follow, max-image-preview:large">\n'
            '<meta name="naver-site-verification" content="d2ac1feb412642dd359d2c5db626a1dffeaf8110" />\n'
            f'<meta property="og:type" content="{"article" if article else "website"}">\n<meta property="og:site_name" content="더블샷(Double-Shot)">\n'
            f'<meta property="og:title" content="{e(title)}">\n<meta property="og:description" content="{e(desc)}">\n'
            f'<meta property="og:url" content="{url}">\n<meta property="og:image" content="{SITE}/assets/og-image.png">\n'
            f'<link rel="canonical" href="{url}">\n'
            '<link href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css" rel="stylesheet">\n'
            '<link rel="stylesheet" href="/assets/style.css?v=20260704">\n<link rel="icon" type="image/svg+xml" href="/favicon.svg">\n'
            + ld + STYLE + "\n" + ADS + "</head>\n<body>\n" + GNB + "\n")
    crumb = '<a href="/stocks/">더블샷</a> › ' + (f'<a href="/guides/">해설 글</a> › {html.escape(crumb_title)}' if slug else "해설 글")
    return (head + f'<div class="legal-wrap">\n  <div class="legal-crumb">{crumb}</div>\n'
            f'  <h1 class="legal-h1">{html.escape(h1)}</h1>\n  <div class="legal-meta">{html.escape(sub)}</div>\n'
            + body + "\n\n" + FOOT + "\n</div>\n</body>\n</html>\n")


charts = {"aftermarket-close": [chart_close()], "nasdaq-5y-average": [chart_nasdaq()],
          "kospi-open-us-signals": [chart_open_years(), chart_open_signals()],
          "monthly-ma5-test": [chart_ma5()], "sp-futures-close": [chart_sp_bands()], "income-etf-yield": [chart_income()]}
for gd in GUIDES[1:]:
    md = (DRAFTS / gd["draft"]).read_text()
    body = md_body(md, charts[gd["slug"]])
    out = ROOT / f"web/guides/{gd['slug']}/index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page(gd["slug"], gd["title"], gd["desc"], gd["h1"], gd["h1"], gd["sub"], body, date=gd.get("date", DATE_ISO)))
    print("wrote", out, len(body))

lis = "".join(f'<li><a href="/guides/{g["slug"]}/">{html.escape(g["title"])}</a><p>{html.escape(g["desc"])}</p></li>' for g in reversed(GUIDES))
idx_body = ('  <p class="legal-lead">더블샷이 매일 쌓는 예측 채점 기록과 직접 돌린 백테스트, 데이터를 다루다 알게 된 사실을 정리한 글이에요. 숫자는 글마다 기준일을 적었고, 지금 값은 각 지표 페이지에서 확인할 수 있어요.</p>\n'
            f'  <section class="legal-sec">\n    <ul class="g-guide-list">{lis}</ul>\n  </section>')
(ROOT / "web/guides/index.html").write_text(page("", "해설 글 — 시장 지표와 예측 기록 읽는 법", "더블샷이 매일 채점한 예측 기록과 직접 돌린 백테스트로 시장 지표를 읽는 법을 정리한 해설 글 모음이에요.", "", "해설 글", "2026년 11월 26일 갱신", idx_body, article=False))
print("wrote index")
