# 실측 JSON → C안 섹션 HTML 생성 → 발행된 9/4 코스피 페이지 사본에 주입(프로토타입 전용).
import json, re, pathlib

SC = "/private/tmp/claude-501/-Users-luke-Service-App-double-shot/30e8f8e3-53eb-4c41-9a17-373f271c3102/scratchpad"
rows = json.load(open(f"{SC}/measured0903.json"))
PROXY_NAME = {"^GSPC": "S&P500"}

def fmt(p):
    return ("+" if p >= 0 else "−") + f"{abs(p):.2f}%"

cards, skipped = [], []
for r in rows:
    sides = [s for s in r["sides"] if [m for m in s["marks"] if "pct" in m]]
    if not sides:                      # 측정 가능한 근거가 하나도 없으면 카드째 생략(§0)
        skipped.append(r["title"]); continue
    inner = []
    for s in sides:
        ms = [m for m in s["marks"] if "pct" in m]
        want_up = s["side"] == "up"
        hits = [m for m in ms if m["hit"]]
        pcts = [m["pct"] for m in ms]
        avg = sum(pcts) / len(pcts)
        n, h = len(ms), len(hits)
        # 판정 배지 — 적중 수를 세어 만든다(결정론)
        if h == n:
            vcls, vtxt = "all", ("적중" if n == 1 else f"{n}건 전부")
        elif h == 0:
            vcls, vtxt = "none", "빗나감"
        else:
            vcls, vtxt = "part", f"{n}중 {h} 적중"
        # 결과 한 줄 — 템플릿 + 실측 조립
        moved = "올랐어요" if want_up else "내렸어요"
        if n == 1:
            m = ms[0]
            nm = PROXY_NAME.get(m["t"], m["t"])
            actual = "올랐어요" if m["pct"] > 0 else ("내렸어요" if m["pct"] < 0 else "보합이었어요")
            line = f'{s["label"]}이 <b>{actual}</b> · {nm} {fmt(m["pct"])}'
            if h == 0:
                line += " — 예상과 반대예요"
        else:
            line = f'{s["label"]} {n}종목 중 <b>{h}종목이 {moved}</b> · 평균 {fmt(avg)}'
        tks = []
        for m in ms:
            nm = PROXY_NAME.get(m["t"], m["t"])
            if m["hit"]:
                cls = "res-tk hit" + (" dnmove" if m["pct"] < 0 else "")
                tks.append(f'<span class="{cls}">{nm} <span class="pct">{fmt(m["pct"])}</span><span class="res-mark">✓</span></span>')
            else:
                tks.append(f'<span class="res-tk miss">{nm} <span class="pct">{fmt(m["pct"])}</span></span>')
        arrow, scls = ("▲", "up") if want_up else ("▼", "down")
        proxy = ""
        if s.get("proxy"):
            proxy = (f'<div class="proxy-note">※ 종목이 지정되지 않은 “{s["label"]}”은 '
                     f'{PROXY_NAME.get(s["proxy"], s["proxy"])} 실측으로 채점했어요.</div>')
        inner.append((vcls, vtxt, line, f'''      <div class="imp-side {scls}">
        <span class="imp-arrow">{arrow}</span><span class="imp-label">{s["label"]}</span>
        <span class="imp-tickers">{"".join(tks)}</span>
      </div>
{proxy}'''))
    vcls, vtxt, line, body = inner[0]
    rest = "".join(x[3] for x in inner[1:])
    cards.append(f'''    <div class="issue-card">
      <div class="issue-card__title">{r["title"]}<span class="verdict {vcls}">{vtxt}</span></div>
      <div class="reshead"><div class="reshead__txt">{line}</div></div>
      <div class="issue-card__impact">
{body}{rest}      </div>
    </div>''')

section = f'''<div class="open-section">
  <div class="open-section__title us-linked-title">
    <span class="us-badge"><span class="us-badge__flag" aria-hidden="true">🇺🇸</span>US</span> 간밤 이슈, 이렇게 끝났어요
  </div>
  <div class="issue-list issue-list--numbered">
{chr(10).join(cards)}
  </div>
  <div class="sec-foot">ET 9/3 정규장 종가 기준 실측이에요. · <a href="/briefings/2026-09-03/us/">간밤 미국 브리핑 보기 →</a></div>
</div>

'''

CSS = '''<style>
/* 새로 추가되는 규칙만(나머지는 발행 페이지의 style.css 그대로) */
.res-tk{display:inline-flex;align-items:center;gap:5px;font-size:11.5px;font-weight:700;padding:2px 8px;
  border-radius:5px;background:var(--surface-inset);color:var(--ink);letter-spacing:-.2px;}
.res-tk .pct{font-variant-numeric:tabular-nums;font-weight:800;}
.res-tk.hit{background:var(--up-bg);color:var(--up);}
.res-tk.hit.dnmove{background:var(--dn-bg);color:var(--dn);}
.res-tk.miss{background:var(--surface-inset);color:var(--muted);text-decoration:line-through;text-decoration-thickness:1px;}
.res-mark{font-size:10px;font-weight:900;}
.verdict{margin-left:auto;font-size:11px;font-weight:800;padding:3px 9px;border-radius:999px;flex-shrink:0;letter-spacing:-.2px;}
.verdict.all{background:var(--up-bg);color:var(--up);}
.verdict.part{background:var(--gold-bg);color:var(--gold);}
.verdict.none{background:var(--surface-inset);color:var(--muted);}
.reshead{margin-top:11px;padding-top:11px;border-top:1px dashed var(--hairline);}
.reshead__txt{font-size:12.5px;font-weight:700;color:var(--ink);line-height:1.5;}
.proxy-note{font-size:11px;color:var(--muted);margin-top:6px;line-height:1.5;}
.sec-foot{font-size:11.5px;color:var(--muted);margin-top:12px;line-height:1.6;}
.sec-foot a{color:var(--primary);font-weight:700;}
.proto-banner{position:sticky;top:0;z-index:99;background:#B7791F;color:#fff;font-size:12px;font-weight:700;
  padding:8px 14px;text-align:center;letter-spacing:-.2px;}
</style>
'''

src = pathlib.Path("web/briefings/2026-09-04/kospi/index.html").read_text(encoding="utf-8")
# style.css를 인라인한다 — 프로토타입을 어디서 열어도 그대로 보이게(상대경로는 스냅샷 렌더에서 깨진다).
_css = pathlib.Path("web/assets/style.css").read_text(encoding="utf-8")
src = re.sub(r'<link[^>]*href="/assets/style\.css[^"]*"[^>]*>', "<style>" + _css + "</style>", src, count=1)
src = src.replace("</head>", CSS + "</head>", 1)
banner = ('<div class="proto-banner">프로토타입 — 2026-09-04 발행 코스피 브리핑에 '
          '‘간밤 이슈, 이렇게 끝났어요’ 섹션(C안)을 얹은 것이다. 수치는 ET 9/3 정규장 실측.</div>')
src = src.replace("<body", banner + "\n<body", 1) if "<body" in src else src
anchor = '<div class="open-section">\n  <div class="open-section__title us-linked-title">'
assert anchor in src, "주입 지점 못 찾음"
src = src.replace(anchor, section + anchor, 1)
out = pathlib.Path("docs/prototypes/2026-09-06-kospi-briefing-with-scoreboard.html")
out.write_text(src, encoding="utf-8")
print("생성:", out, len(src), "bytes")
print("카드:", len(cards), "/ 생략된 이슈:", skipped)
