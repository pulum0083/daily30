# 'S&P 500 · 트럼프 1기 중간선거 뒤와 닮았을까' 홈 줄·상세 페이지 시안 — 야후 일봉·FRED 기준금리 실측(2026-11-13 종가)
import json, sys, math
import numpy as np, pandas as pd, yfinance as yf
D = pd.read_pickle("mt_data.pkl"); s = D["^GSPC"].dropna()
full = yf.download("^GSPC", start="1949-12-01", interval="1d", auto_adjust=False, progress=False)["Close"].squeeze().dropna()

def path(y1):  # 직전 해 말 종가 대비 % — 2년치
    base = s[s.index.year == y1 - 1].iloc[-1]
    x = s[(s.index.year >= y1) & (s.index.year <= y1 + 1)]
    return [((i - pd.Timestamp(y1, 1, 1)).days, round((v / base - 1) * 100, 2), i.strftime("%Y-%m-%d")) for i, v in x.items()]
A, B = path(2018), path(2026)
SPAN = 730; LO, HI = -15, 25
X = lambda d: d / SPAN * 100
Y = lambda v: (HI - v) / (HI - LO) * 100
def poly(p, a=0, b=None): return " ".join(f"{X(d)*10:.1f},{Y(v)*2:.1f}" for d, v, _ in p[a:b])
cut = next(i for i, (d, v, t) in enumerate(A) if t >= "2019-01-01")
now = B[-1]; same18 = [p for p in A if p[2][5:] <= now[2][5:] and p[2] < "2019"][-1]
corr = round(float(np.corrcoef([p[1] for p in A[:len(B)]], [p[1] for p in B])[0, 1]), 2)

# 사건 — 날짜는 실제 기록, 이름은 짧게(§0). 2026은 확인된 것만.
EV = [("2018-10-03", "파월 '갈 길 멀다'", 18), ("2018-11-06", "중간선거 · 민주당 하원 탈환", 18), ("2018-12-01", "화웨이 CFO 체포", 18),
      ("2018-12-19", "FOMC 인상 · 긴축 지속", 18), ("2018-12-24", "연중 저점", 18), ("2019-01-04", "파월 '인내심'", 18),
      ("2019-05-05", "트럼프 관세 인상 예고", 18), ("2019-07-31", "첫 금리 인하", 18), ("2019-12-13", "미·중 1단계 합의", 18),
      ("2026-05-22", "워시 의장 취임", 26), ("2026-09-16", "FOMC 인상 · 10년물 5% 돌파", 26), ("2026-10-06", "연중 고점", 26),
      ("2026-11-03", "중간선거", 26), ("2026-12-09", "FOMC(예정)", 26)]
def ev_at(d, y):
    y0 = 2018 if y == 18 else 2026; t = pd.Timestamp(d); src = A if y == 18 else B
    v = next((p[1] for p in src if p[2] >= d), None)
    return {"left": f"{X((t - pd.Timestamp(y0, 1, 1)).days):.2f}%", "day": (t - pd.Timestamp(y0, 1, 1)).days, "y": y, "d": f"{t.year}.{t.month}.{t.day}", "v": v}
evs = []
for i, (d, lab, y) in enumerate(EV, 1):
    e = ev_at(d, y); e.update(n=i, label=lab); evs.append(e)
# 번호 동그라미가 가까우면 줄을 바꿔 엇갈린다(같은 해 묶음 안에서, 왼쪽→오른쪽)
for yy in (18, 26):
    last = {}
    for e in [x for x in evs if x["y"] == yy]:
        p = float(e["left"][:-1]); r = 0
        while r in last and p - last[r] < 5.2: r += 1
        e["row"] = r; last[r] = p

# 중간선거 19번 — 선거일 종가 → 12개월 뒤
mid = []
for y in range(1950, 2023, 4):
    n1 = pd.Timestamp(y, 11, 1); ed = n1 + pd.Timedelta(days=(0 - n1.weekday()) % 7 + 1)
    p0 = full[:ed].iloc[-1]; p1 = full[:ed + pd.DateOffset(years=1)].iloc[-1]
    mid.append((y, round((p1 / p0 - 1) * 100, 1)))
ss = full[full.index >= "1950-01-01"]; fwd = (ss.shift(-252) / ss - 1).dropna() * 100
base_up, base_avg = round((fwd > 0).mean() * 100, 1), round(fwd.mean(), 1)
m_avg = round(sum(v for _, v in mid) / len(mid), 1)

def sg(v, d=1): return ("+" if v > 0 else "−" if v < 0 else "") + f"{abs(v):.{d}f}"
data = {"a": [[p[0], p[1], p[2]] for p in A], "b": [[p[0], p[1], p[2]] for p in B], "lo": LO, "hi": HI, "span": SPAN}

RANGES = [("2y", "2년", 0, 730), ("y1", "선거 해", 0, 364), ("mid", "선거 전후", 243, 455)]   # 일(1월 1일 = 0) 기준 창

def chart(key, S, E, shown):
    """창 [S, E]일만 그린다 — 세로 눈금·사건 번호·월 이름을 창에 맞춰 다시 잡는다(나스닥 체크 기간 버튼과 같은 방식)."""
    W = E - S
    pa = [p for p in A if S <= p[0] <= E]; pb = [p for p in B if S <= p[0] <= E]
    vals = [p[1] for p in pa + pb] + [0]
    step = 5 if max(vals) - min(vals) < 26 else 10
    lo = math.floor((min(vals) - 1) / step) * step; hi = math.ceil((max(vals) + 1) / step) * step
    xx = lambda d: (d - S) / W * 100
    yy = lambda v: (hi - v) / (hi - lo) * 100
    pl = lambda p: " ".join(f"{xx(d)*10:.1f},{yy(v)*2:.1f}" for d, v, _ in p)
    ticks = list(range(int(lo), int(hi) + 1, step))
    yt = "".join(f'<span class="ax" style="top:{yy(v):.1f}%">{sg(v,0)}%</span>' for v in ticks)
    grid = "".join(f'<line x1="0" x2="1000" y1="{yy(v)*2:.1f}" y2="{yy(v)*2:.1f}" class="{"z" if v == 0 else "g"}"/>' for v in ticks)
    a1 = [p for p in pa if p[2] < "2019"]; a2 = [p for p in pa if p[2] >= "2019"]
    if a1 and a2: a2 = [a1[-1]] + a2
    # 사건 — 창 안의 것만, 가까우면 줄을 바꿔 엇갈린다
    evw = []
    for e in evs:
        d = e["day"]
        if S <= d <= E:
            evw.append(dict(e, x=xx(d)))
    for yv in (18, 26):
        last = {}
        for e in [x for x in evw if x["y"] == yv]:
            r = 0
            while r in last and e["x"] - last[r] < 5.2: r += 1
            e["row"] = r; last[r] = e["x"]
    ev = "".join(f'<i class="ev y{e["y"]}" style="left:{e["x"]:.2f}%"></i><b class="evn y{e["y"]}" style="left:{e["x"]:.2f}%;'
                 f'{"top" if e["y"] == 18 else "bottom"}:{(e["row"] * 17) if e["y"] == 18 else (e["row"] * 17 - 8)}px">{e["n"]}</b>' for e in evw)
    yr = f'<line x1="{xx(365)*10:.1f}" x2="{xx(365)*10:.1f}" y1="0" y2="200" class="yr"/>' if S < 365 < E else ""
    labs = ""
    if S < 365 < E:
        labs = (f'<span class="yrl" style="left:{xx((S + 365) / 2):.1f}%">2018 · 2026</span>'
                f'<span class="yrl" style="left:{xx((365 + E) / 2):.1f}%">2019 · 2027</span>')
    nowh = (f'<i class="now" style="left:{xx(now[0]):.2f}%;top:{yy(now[1]):.2f}%"></i>'
            f'<span class="nowl" style="left:{xx(now[0]):.2f}%;top:{yy(now[1]):.2f}%">지금 {sg(now[1])}%</span>') if S <= now[0] <= E else ""
    # 월 이름 — 창 길이에 따라 3·2·1개월마다
    every = 3 if W > 400 else 2 if W > 250 else 1
    mx = ""
    for y0 in (0, 365):
        for mth in range(1, 13):
            d = (pd.Timestamp(2018 if y0 == 0 else 2019, mth, 1) - pd.Timestamp(2018, 1, 1)).days
            if S <= d <= E and (mth - 1) % every == 0:
                mx += f'<span style="left:{xx(d):.1f}%">{mth}월</span>'
    return (f'<div class="mt-r" data-r="{key}"{"" if shown else " hidden"}><div class="mt-plot">{yt}<div class="mt-in" data-s="{S}" data-e="{E}">'
            f'<svg viewBox="0 0 1000 200" preserveAspectRatio="none">{grid}{yr}'
            + (f'<polyline class="a18" points="{pl(a1)}"/>' if a1 else "") + (f'<polyline class="a19" points="{pl(a2)}"/>' if a2 else "")
            + (f'<polyline class="b26" points="{pl(pb)}"/>' if pb else "") +
            f'</svg>{ev}{nowh}{labs}<i class="cur" hidden></i><div class="tip" hidden></div></div></div>'
            f'<div class="mt-x">{mx}</div></div>')

def charts():
    seg = '<div class="mt-seg" role="group" aria-label="기간">' + "".join(
        f'<button type="button" data-r="{k}" aria-pressed="{"true" if i == 0 else "false"}">{l}</button>' for i, (k, l, _, _) in enumerate(RANGES)) + '</div>'
    return seg, "".join(chart(k, S, E, i == 0) for i, (k, _, S, E) in enumerate(RANGES))

evlist = ("<div class='mt-evs'><div><h4><i class='k18'></i>2018 ~ 2019</h4>" +
          "".join(f'<p><b class="y18">{e["n"]}</b>{e["d"][5:].replace(".", "/") if e["d"].startswith("2018") else e["d"][2:].replace(".", "/")} {e["label"]}<em>{sg(e["v"])}%</em></p>' for e in evs if e["y"] == 18) +
          "</div><div><h4><i class='k26'></i>2026</h4>" +
          "".join(f'<p><b class="y26">{e["n"]}</b>{e["d"][5:].replace(".", "/")} {e["label"]}<em>{(sg(e["v"]) + "%") if e["v"] is not None else "아직"}</em></p>' for e in evs if e["y"] == 26) +
          "</div></div>")

bars_hi = 40; bars_lo = 0
BY = lambda v: (bars_hi - v) / (bars_hi - bars_lo) * 100
bars = "".join(
    f'<div class="mb{" hl" if y == 2018 else ""}" title="{y}년 선거일 뒤 12개월 {sg(v)}%"><i style="top:{BY(max(v,0)):.1f}%;height:{abs(BY(v)-BY(0)):.1f}%"></i>'
    f'<em style="top:calc({BY(max(v,0)):.1f}% - 15px)">{sg(v,0)}</em><span>{str(y)[2:]}</span></div>' for y, v in mid)

home_row = (f'<a class="lt-r" href="#detail"><span class="lt-t"><span class="lt-k">중간선거 해 · 2018년 비교<em>11/13(금) 종가</em></span>'
            f'<span class="lt-v">{sg(now[1])}%<small>2018년 같은 날 {sg(same18[1])}%</small></span>'
            f'<span class="lt-d">중간선거 뒤 12개월, 1950년 이후 19번 모두 올랐어요</span></span>'
            f'<span class="lt-g"><svg viewBox="0 0 1000 200" preserveAspectRatio="none"><line x1="0" x2="1000" y1="{Y(0)*2:.1f}" y2="{Y(0)*2:.1f}"/>'
            f'<polyline class="p18" points="{poly(A)}"/><polyline class="l" points="{poly(B)}"/></svg>'
            f'<i style="left:{X(now[0]):.1f}%;top:{Y(now[1]):.1f}%"></i></span><span class="lt-go">›</span></a>')

css = open("mt_proto.css").read()
SEG, CH = charts()
detail = f'''
<main class="ltp" id="detail">
  <div class="ltp-crumb"><span><a href="#">종목 홈</a> › 중간선거 해 비교</span></div>
  <h1 class="ltp-title">트럼프 1기 중간선거 뒤와 닮았을까?</h1>
  <p class="ltp-lead">2026년 S&amp;P 500을 같은 대통령의 첫 중간선거 해였던 2018년과 겹쳐 봐요. 2018년 선은 그다음 해 2019년 말까지 이어 그렸어요 — <b>그때 실제로 일어난 일</b>이에요. 2027년을 예측하는 선이 아니에요.</p>

  <section class="ltp-card">
    <div class="ltp-k">S&amp;P 500 · 2025년 말 종가 대비 · 11/13(금) 종가</div>
    <div class="ltp-v">{sg(now[1])}<small>%</small></div>
    <p class="ltp-say">2018년 같은 날엔 <b>{sg(same18[1])}%</b>였어요. 두 해 곡선이 닮은 정도는 <b>{corr}</b>예요(1이면 똑같고 0이면 관계없어요). 큰 줄기 — 연초부터 오르다 가을에 꺾인 모양 — 는 비슷하지만, 하루하루 움직임은 거의 관계가 없어요.</p>
  </section>

  <section class="ltp-card">
    <div class="ltp-h"><h2>연초 대비 흐름</h2>{SEG}</div>
    <div class="ltp-leg"><span><i class="k18"></i>2018년</span><span><i class="k19"></i>2019년(그다음 해)</span><span><i class="k26"></i>2026년</span><span><i class="z"></i>0% = 직전 해 말 종가</span></div>
    {CH}
    {evlist}
  </section>

  <section class="ltp-card">
    <div class="ltp-h"><h2>같은 날 나란히 · 11/13</h2><small>닮은 점과 다른 점</small></div>
    <table><thead><tr><th></th><th>2018년</th><th>2026년</th></tr></thead><tbody>
      <tr><td>연초 대비 S&amp;P 500</td><td>{sg(same18[1])}%</td><td>{sg(now[1])}%</td></tr>
      <tr><td>그해 고점에서</td><td>−7.1%</td><td>−3.3%</td></tr>
      <tr><td>10년물 국채 금리</td><td>3.14%</td><td>5.15%</td></tr>
      <tr class="hl"><td>기준금리(상단)</td><td>2.25% · 올해 3번 인상</td><td>4.00% · 9/16 인상</td></tr>
    </tbody></table>
    <div class="mt-concl"><b>닮은 점</b> — 두 해 모두 9월 FOMC에서 금리를 올렸고, 가을에 고점을 찍은 뒤 밀렸어요.<br><b>다른 점</b> — 2018년은 이 무렵 이미 고점에서 7% 빠져 있었고 12월 24일까지 −19.8%로 깊어졌어요. 2026년은 아직 3% 아래예요. 10년물 금리는 2018년보다 2%p 높아요.<br><b>2019년엔</b> — 연준이 12월에 한 번 더 올린 뒤 2019년 1월 '인내심'으로 돌아섰고, 7월부터 세 번 내렸어요. S&amp;P 500은 그해 +28.9%(나스닥 +35.2%) 올랐어요.</div>
  </section>

  <section class="ltp-card">
    <div class="ltp-h"><h2>중간선거 19번 · 선거일 뒤 12개월</h2><small>1950 ~ 2022 · S&amp;P 500 종가</small></div>
    <p class="ltp-say">19번 모두 올랐어요 — 평균 <b>+{m_avg}%</b>, 가장 낮았던 해도 +1.1%(1986)였어요. 아무 날에나 사서 12개월 뒤를 보면 오른 비율 {base_up}%, 평균 +{base_avg}%예요.</p>
    <div class="mt-bars"><span class="ax" style="top:{BY(40):.1f}%">+40</span><span class="ax" style="top:{BY(20):.1f}%">+20</span><span class="ax" style="top:{BY(0):.1f}%">0</span>
      <div class="mb-in"><i class="mb-base" style="top:{BY(base_avg):.1f}%"><span>아무 날 평균 +{base_avg}%</span></i><i class="mb-zero" style="top:{BY(0):.1f}%"></i>{bars}</div></div>
    <p class="ltp-fine">2026년 칸은 2027년 11월에 채워져요. 표본이 19번뿐이고 시대마다 금리·경기가 달랐어요. 중간선거 뒤에 오른 이유는 해마다 달랐다는 점도 함께 봐 주세요.</p>
  </section>

  <section class="ltp-sec"><details class="mt-fine"><summary>근거와 면책 고지</summary>
    <p>S&amp;P 500 일별 종가(야후 파이낸스, 배당 제외)를 직전 해 마지막 종가와 비교했어요. 기준금리는 연준 목표 범위 상단(FRED DFEDTARU), 10년물 금리는 미국 10년 국채 수익률(^TNX)이에요. 사건 날짜는 실제 기록이고, 2026년 사건은 확인된 것만 넣었어요. 두 해가 닮았다는 사실이 2027년 흐름을 알려 주지는 않아요. 투자 권유가 아니에요.</p></details></section>
</main>'''

html = f'''<!-- 'S&P 500 · 트럼프 1기 중간선거 뒤와 닮았을까' 시안 — 홈 장기 신호 줄 + 상세 페이지. 2026-11-13 종가 실측(야후·FRED) -->
<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>중간선거 해 비교 시안</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css">
<style>{css}</style></head><body>
<div class="top"><h1>중간선거 해 비교 시안</h1><p>① 종목 홈 '장기 신호' 블록에서 코스피 체크 줄 자리에 들어갈 줄, ② 그 줄을 누르면 가는 상세 페이지예요. 숫자는 전부 2026-11-13(금) 종가 실측이에요.</p></div>
<div class="v"><h3>① 종목 홈 · 장기 신호 줄</h3><div class="pair"><div class="fw pc"><small>PC 616px</small><section class="ss">{home_row}</section></div><div class="fw ph"><small>모바일 343px</small><section class="ss">{home_row}</section></div></div></div>
<div class="v"><h3>② 상세 페이지 (/stocks/midterm-2018/)</h3>{detail}</div>
<script>
const MT = {json.dumps(data, ensure_ascii=False)};
document.querySelectorAll('.mt-in').forEach(el => {{
  const cur = el.querySelector('.cur'), tip = el.querySelector('.tip');
  const at = (arr, d) => {{ let b = null; for (const p of arr) {{ if (p[0] <= d) b = p; else break; }} return b; }};
  const fmt = v => (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(1) + '%';
  el.addEventListener('mousemove', e => {{
    const S = +el.dataset.s, E = +el.dataset.e;
    const r = el.getBoundingClientRect(), f = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), d = S + f * (E - S);
    const a = at(MT.a, d), b = d <= MT.b[MT.b.length - 1][0] ? at(MT.b, d) : null;
    if (!a) return;
    const md = a[2].slice(5).replace('-', '/').replace(/^0/, '').replace('/0', '/');
    const y2 = a[2] >= '2019';
    tip.innerHTML = '<b>' + md + '</b>' + (y2 ? '2019' : '2018') + ' <span class="k">' + fmt(a[1]) + '</span>' + (b ? '<br>' + (y2 ? '2027' : '2026') + ' <span class="k">' + fmt(b[1]) + '</span>' : (y2 ? '' : '<br>2026 <span class="k">아직</span>'));
    cur.style.left = (f * 100) + '%'; cur.hidden = false; tip.hidden = false;
    tip.style.left = Math.min(r.width - 120, Math.max(0, f * r.width + 10)) + 'px'; tip.style.top = '6px';
  }});
  el.addEventListener('mouseleave', () => {{ cur.hidden = true; tip.hidden = true; }});
}});
document.querySelectorAll('.mt-seg button').forEach(btn => btn.addEventListener('click', () => {{
  const card = btn.closest('.ltp-card'), k = btn.dataset.r;
  card.querySelectorAll('.mt-seg button').forEach(b => b.setAttribute('aria-pressed', b === btn ? 'true' : 'false'));
  card.querySelectorAll('.mt-r').forEach(r => {{ r.hidden = r.dataset.r !== k; }});
}}));
</script></body></html>'''
open(sys.argv[1], "w").write(html)
print("ok", now, same18, corr, m_avg, base_up, base_avg)
