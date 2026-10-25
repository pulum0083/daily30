# 미국 브리핑 '나스닥 과열 체크' 섹션 프로토타입 — 10/23 발행본에 월봉 고점 vs 60개월선 섹션을 끼워 넣는다
import warnings; warnings.filterwarnings("ignore")
import yfinance as yf, numpy as np
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path("/Users/luke/Service App/double-shot")
SRC = ROOT / "web/briefings/2026-10-23/us/index.html"
OUT = ROOT / "web/_proto/us-nq60/index.html"
DOC = ROOT / "docs/prototypes/2026-10-25-us-briefing-nasdaq-overheat.html"

d = yf.Ticker("^IXIC").history(period="max", interval="1mo", auto_adjust=False).dropna(subset=["Close"])
d.index = d.index.tz_localize(None) if d.index.tz is not None else d.index
d = d[d.index <= "2026-10-31"]
d["ma60"] = d["Close"].rolling(60).mean()
d["g"] = (d["High"] / d["ma60"] - 1) * 100
cur = d.iloc[-1]
gap, hi, ma = float(cur["g"]), float(cur["High"]), float(cur["ma60"])
streak = 0
for v in d["g"][::-1]:
    if v >= 50: streak += 1
    else: break
level = "warn" if gap >= 70 else ("caution" if gap >= 50 else "ok")

# 차트: 최근 12년 월별 값
s = d.loc["2014-01-01":, "g"].dropna()
W, H, PADL, PADR, PADT, PADB = 640, 190, 0, 8, 10, 22
ymin, ymax = 0, 100
xs = np.linspace(PADL, W - PADR, len(s))
Y = lambda v: PADT + (H - PADT - PADB) * (1 - (min(max(v, ymin), ymax) - ymin) / (ymax - ymin))
pts = " ".join(f"{x:.1f},{Y(v):.1f}" for x, v in zip(xs, s.values))
area = f"{xs[0]:.1f},{Y(0):.1f} " + pts + f" {xs[-1]:.1f},{Y(0):.1f}"
years = [(xs[i], s.index[i].year) for i in range(len(s)) if s.index[i].month == 1 and s.index[i].year % 2 == 0]
peak_i = int(np.argmax(s.values))
svg = f'''<svg class="nq-chart" viewBox="0 0 {W} {H}" preserveAspectRatio="none" role="img" aria-label="나스닥 월봉 고점의 60개월선 대비 위치, 2014년 이후">
  <rect x="{PADL}" y="{Y(100):.1f}" width="{W-PADL-PADR}" height="{Y(70)-Y(100):.1f}" class="z-warn"/>
  <rect x="{PADL}" y="{Y(70):.1f}" width="{W-PADL-PADR}" height="{Y(50)-Y(70):.1f}" class="z-caution"/>
  <line x1="{PADL}" x2="{W-PADR}" y1="{Y(70):.1f}" y2="{Y(70):.1f}" class="th th-warn"/>
  <line x1="{PADL}" x2="{W-PADR}" y1="{Y(50):.1f}" y2="{Y(50):.1f}" class="th th-caution"/>
  <polygon points="{area}" class="area"/>
  <polyline points="{pts}" class="line"/>
</svg>'''
px = lambda x: f"calc(34px + (100% - 34px) * {x / W:.4f})"
py = lambda v: f"{Y(v) / H * 100:.2f}%"
svg = (f'<div class="nq-plot">{svg}'
       f'<i class="nq-dot" style="left:{px(xs[-1])};top:{py(s.values[-1])}"></i>'
       f'<i class="nq-dot2" style="left:{px(xs[peak_i])};top:{py(s.values[peak_i])}"></i>'
       + "".join(f'<span class="nq-ax" style="top:{py(v)}">{v}%</span>' for v in (70, 50, 0))
       + "".join(f'<span class="nq-yr" style="left:{px(x)}">{y}</span>' for x, y in years)
       + '</div>')
peak_lbl = f"{s.index[peak_i].year}년 {s.index[peak_i].month}월 {s.values[peak_i]:.0f}%"

pos = min(gap, 100)
badge = {"warn": ("🚨 경고", "70% 돌파"), "caution": ("⚠️ 주의", "50% 넘음"), "ok": ("정상", "")}[level]
section = f'''<div class="open-section nq-section is-{level}">
  <div class="open-section__title">나스닥 과열 체크 <span class="nq-badge">{badge[0]}</span></div>
  <p class="nq-intro">나스닥 월봉 고점이 60개월(5년) 이동평균선보다 얼마나 위에 있는지 봐요. <b>50%</b>를 넘으면 주의, <b>70%</b>를 넘으면 경고로 표시해요.</p>
  <div class="nq-card">
    <div class="nq-top">
      <div><div class="nq-k">이번 달 고점 vs 60개월선</div>
        <div class="nq-v">+{gap:.1f}<small>%</small></div></div>
      <div class="nq-side"><span>이번 달 고점 <b>{hi:,.1f}</b></span><span>60개월선 <b>{ma:,.1f}</b></span><span>50% 위 <b>{streak}개월째</b></span></div>
    </div>
    <div class="nq-gauge"><div class="nq-track"><i class="seg ok"></i><i class="seg caution"></i><i class="seg warn"></i></div>
      <div class="nq-pin" style="left:{pos:.1f}%"><b>{gap:.1f}%</b></div>
      <div class="nq-ticks"><span style="left:0">0</span><span style="left:50%">50 주의</span><span style="left:70%">70 경고</span><span style="left:100%">100+</span></div>
    </div>
    <div class="nq-ch-h">2014년 이후 월별 위치 <span>· 최고 {peak_lbl}</span></div>
    {svg}
  </div>
  <p class="nq-foot">1985년 이후 50%를 넘은 달은 116개월이었고, 그 뒤 12개월 평균 수익률은 <b>+20.9%</b>로 전체 평균(+14.9%)과 크게 다르지 않았어요 — 50% 자체는 하락 신호가 아니에요.
  70%를 넘은 달 뒤에는 12개월 안에 <b>-20% 넘게 빠진 경우가 51%</b>(전체 19%)였지만, 그런 달은 1998~2000년과 2020~2021년 두 시기에 몰려 있어요. 매매 신호가 아니라 지금 위치를 알려주는 표시예요.
  나스닥 종합지수 월봉(이번 달은 진행 중)으로 계산했어요. <a href="/legal/disclaimer/">면책 고지</a></p>
</div>'''

css = '''<style id="nq-css">
.nq-section{--warn:#dc2626;--warn-bg:#fef2f2;--cau:#d97706;--cau-bg:#fffbeb}
.nq-badge{display:inline-block;margin-left:6px;padding:2px 8px;border-radius:999px;font-size:12px;font-weight:700;vertical-align:1px}
.is-caution .nq-badge{background:var(--cau-bg);color:var(--cau)} .is-warn .nq-badge{background:var(--warn-bg);color:var(--warn)}
.nq-intro{font-size:13px;color:var(--muted);line-height:1.65;margin:6px 0 10px}
.nq-card{border:1px solid var(--hairline);border-radius:var(--r-lg,16px);padding:15px 16px 12px;background:var(--canvas)}
.is-caution .nq-card{border-color:#fcd34d;background:linear-gradient(180deg,var(--cau-bg),var(--canvas) 55%)}
.is-warn .nq-card{border-color:#fca5a5;background:linear-gradient(180deg,var(--warn-bg),var(--canvas) 55%)}
.nq-top{display:flex;justify-content:space-between;align-items:flex-end;gap:12px;flex-wrap:wrap}
.nq-k{font-size:12px;color:var(--muted);font-weight:600}
.nq-v{font-size:34px;font-weight:800;letter-spacing:-1px;line-height:1.1;margin-top:2px}
.nq-v small{font-size:20px;margin-left:1px}
.is-caution .nq-v{color:var(--cau)} .is-warn .nq-v{color:var(--warn)}
.nq-side{display:flex;flex-direction:column;gap:2px;font-size:12px;color:var(--muted);text-align:right}
.nq-side b{color:var(--ink);font-weight:700;margin-left:4px}
.nq-gauge{position:relative;margin:22px 0 26px}
.nq-track{display:flex;height:8px;border-radius:999px;overflow:hidden}
.nq-track .seg{display:block;height:100%} .seg.ok{width:50%;background:#e5e7eb} .seg.caution{width:20%;background:#fcd34d} .seg.warn{width:30%;background:#f87171}
.nq-pin{position:absolute;top:-19px;transform:translateX(-50%);font-size:11px;white-space:nowrap}
.nq-pin::after{content:'';position:absolute;left:50%;top:15px;width:2px;height:16px;margin-left:-1px;background:var(--ink);border-radius:1px}
.nq-pin b{font-weight:800;color:var(--ink)}
.nq-ticks{position:relative;height:14px;margin-top:6px;font-size:10.5px;color:var(--muted)}
.nq-ticks span{position:absolute;transform:translateX(-50%);white-space:nowrap}
.nq-ticks span:first-child{transform:none} .nq-ticks span:last-child{transform:translateX(-100%)}
.nq-ch-h{font-size:12px;font-weight:700;color:var(--ink);margin-bottom:4px} .nq-ch-h span{font-weight:500;color:var(--muted)}
.nq-plot{position:relative;height:150px} .nq-chart{position:absolute;top:0;left:34px;width:calc(100% - 34px);height:100%;display:block}
.nq-dot,.nq-dot2{position:absolute;border-radius:50%;transform:translate(-50%,-50%)} .nq-dot{width:9px;height:9px;background:#d97706;border:2px solid #fff;box-shadow:0 0 0 1px #d97706} .nq-dot2{width:6px;height:6px;background:var(--muted)}
.nq-ax{position:absolute;left:0;width:28px;text-align:right;transform:translateY(-50%);font-size:10px;color:var(--muted)}
.nq-yr{position:absolute;bottom:0;transform:translateX(-50%);font-size:10px;color:var(--muted)}
.nq-chart .z-caution{fill:#fef3c7;opacity:.7} .nq-chart .z-warn{fill:#fee2e2;opacity:.7}
.nq-chart .th{stroke-width:1;stroke-dasharray:3 3;vector-effect:non-scaling-stroke} .th-caution{stroke:#d97706} .th-warn{stroke:#dc2626}
.nq-chart .area{fill:var(--ink);opacity:.05} .nq-chart .line{fill:none;stroke:var(--ink);stroke-width:1.6;vector-effect:non-scaling-stroke}
.nq-foot{font-size:12px;color:var(--muted);line-height:1.7;margin-top:10px}
.nq-foot b{color:var(--ink)} .nq-foot a{color:var(--primary);font-weight:600;white-space:nowrap}
</style>'''

soup = BeautifulSoup(SRC.read_text(encoding="utf-8"), "html.parser")
lead = soup.select_one(".tv-lead")
lead.insert_after(BeautifulSoup(section, "html.parser"))
out = str(soup).replace("</head>", css + "\n</head>", 1)
OUT.write_text(out, encoding="utf-8")
DOC.write_text(out.replace("<head>", "<head>\n<!-- 미국 브리핑 '나스닥 과열 체크' 섹션 프로토타입(월봉 고점 vs 60개월선, 50% 주의·70% 경고) — 10/23 발행본 기반, 스타일은 운영 사이트에서 불러온다 -->\n<base href=\"https://doubleshot.space/\">", 1), encoding="utf-8")
print(f"gap {gap:.1f}% hi {hi:.1f} ma60 {ma:.1f} streak {streak} level {level}")
