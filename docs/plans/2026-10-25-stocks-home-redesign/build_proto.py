# 종목 시그널 첫 페이지 개편 프로토타입 — 시간대 5종 카드 + 압축 홈, 10/23(금) 실데이터로 채운다
import json, html as H, re, urllib.request
from pathlib import Path

ROOT = Path("/Users/luke/Service App/double-shot")
OUT = ROOT / "web/_proto/stocks-home/index.html"
DOC = ROOT / "docs/prototypes/2026-10-25-stocks-home-redesign.html"
J = lambda p: json.loads((ROOT / p).read_text(encoding="utf-8"))

snap = J("web/data/stocks-snapshot.json")
uni = J("scripts/config/stock_universe.json")["sectors"]
ks = J("web/briefings/2026-10-23/kospi/analysis_snapshot.json")
us = J("web/briefings/2026-10-23/us/analysis_snapshot.json")
bridge = J("web/data/overnight-bridge.json")
acc = J("web/data/accuracy-summary.json")["kospi"]
DETAIL = {"005930", "000660", "005380"}
st = snap["stocks"]


def get(u):
    return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=15).read())


def bars(ymd):
    r = get(f"https://api.stock.naver.com/chart/domestic/index/KOSPI/minute?startDateTime={ymd}0900&endDateTime={ymd}1530")
    return [(int(x["localDateTime"][8:10]) * 60 + int(x["localDateTime"][10:12]), x["currentPrice"]) for x in r]


# ── 장중 비교 곡선 (13:30 시점 재현) ───────────────────────────────────────
PREV2, PREV1 = 5735.66, 5533.77           # 10/21·10/22 종가
T_NOW = 13 * 60 + 30
yd = [(t, (p / PREV2 - 1) * 100) for t, p in bars("20261022")]
td = [(t, (p / PREV1 - 1) * 100) for t, p in bars("20261023") if t <= T_NOW]
t0, t1 = 9 * 60, 15 * 60 + 30
allv = [v for _, v in yd + td]
lo, hi = min(allv) - .3, max(allv) + .3
W, Hh = 300, 130
X = lambda t: (t - t0) / (t1 - t0) * W
Y = lambda v: (hi - v) / (hi - lo) * Hh
poly = lambda s: " ".join(f"{X(t):.1f},{Y(v):.1f}" for t, v in s)
td_now = td[-1][1]
yd_now = next(v for t, v in yd if t == T_NOW)
diff = td_now - yd_now
# 결론 문장 — 대결판(_vs-core.verdict)과 같은 규칙: 오늘의 방향을 먼저 말한다(§54)
if td_now >= 0 and yd_now >= 0:
    verdict = "어제보다 더 오르고 있어요" if diff > 0 else "오르고 있지만 어제보다 오름폭이 작아요"
elif td_now < 0 and yd_now < 0:
    verdict = "내리고 있지만 어제보다 낙폭이 작아요" if diff > 0 else "어제보다 더 내리고 있어요"
else:
    verdict = "어제와 달리 오르고 있어요" if td_now >= 0 else "어제와 달리 내리고 있어요"
tcls = "up" if td_now >= 0 else "dn"
ycls = "up" if yd_now >= 0 else "dn"
curve = f'''<div class="cv"><svg viewBox="0 0 {W} {Hh}" preserveAspectRatio="none">
<rect x="{X(T_NOW):.1f}" y="0" width="{W - X(T_NOW):.1f}" height="{Hh}" class="rest"/>
<line x1="0" x2="{W}" y1="{Y(0):.1f}" y2="{Y(0):.1f}" class="zero"/>
<polyline points="{poly(yd)}" class="yd"/><polyline points="{poly(td)}" class="td {tcls}"/></svg>
<i class="cv-dot {tcls}" style="left:{X(T_NOW)/W*100:.1f}%;top:{Y(td_now)/Hh*100:.1f}%"></i>
<span class="cv-l" style="top:{Y(0)/Hh*100:.1f}%">0%</span>
<div class="cv-ax"><span>09:00</span><span>12:00</span><span>15:30</span></div></div>
<div class="cv-lg"><span><i class="td"></i>오늘</span><span><i class="yd"></i>어제 같은 시각</span></div>'''

# ── 섹터 평균 (당일·주간) ───────────────────────────────────────────────
def chg(d, off=0):
    sp = d.get("spark20") or []
    if off == 0:
        return d.get("change_pct")
    return (sp[-1 - off] / sp[-2 - off] - 1) * 100 if len(sp) >= 2 + off else None


def sec_rows(weekly=False, off=0):
    out = []
    for key, s in uni.items():
        vals = []
        for x in s["stocks"]:
            d = st.get(x["code"])
            if not d:
                continue
            if weekly:
                sp = d.get("spark20") or []
                if len(sp) >= 6:
                    vals.append((sp[-1] / sp[-6] - 1) * 100)
            elif chg(d, off) is not None:
                vals.append(chg(d, off))
        if vals:
            out.append((key, s["label"], sum(vals) / len(vals), len(vals)))
    return sorted(out, key=lambda r: -r[2])


def sec_html(rows, cap):
    m = max(abs(r[2]) for r in rows) or 1
    li = "".join(f'''<a class="sb" href="/stocks/sector/{k}/"><span class="sb-n">{lbl}</span>
<span class="sb-bar"><i class="{"up" if v >= 0 else "dn"}" style="width:{abs(v)/m*50:.1f}%;{"left:50%" if v >= 0 else f"right:50%"}"></i></span>
<b class="{"up" if v >= 0 else "dn"}">{v:+.2f}%</b></a>''' for k, lbl, v, n in rows)
    return f'<div class="blk"><div class="bh"><h3>섹터 한눈에</h3><span>{cap}</span></div><div class="sbs">{li}</div><p class="note">섹터 대표 종목 평균 · 누르면 섹터 페이지</p></div>'


# ── 특이신호 상위 3 (프로토타입: 10/23 거래량 급증 + 등락) ─────────────
cands = []
for code, d in st.items():
    if d.get("vol") and d.get("vol_avg20") and d.get("change_pct") is not None:
        cands.append((d["vol"] / d["vol_avg20"], code, d))
cands.sort(reverse=True)
sec_of = {x["code"]: k for k, s in uni.items() for x in s["stocks"]}
sig = ""
for r, code, d in cands[:3]:
    link = (f'<a class="go" href="/stocks/{code}/">상세 →</a>' if code in DETAIL
            else f'<a class="go soft" href="/stocks/sector/{sec_of.get(code, "semicon")}/">{uni.get(sec_of.get(code), {}).get("label", "섹터")} 보기 →</a>')
    c = d["change_pct"]
    sig += f'''<div class="sg"><div><b>{H.escape(d["name"])}</b><span>거래량 평소의 {r:.1f}배</span></div>
<div class="sg-r"><b class="{"up" if c >= 0 else "dn"}">{c:+.2f}%</b>{link}</div></div>'''
sig_html = f'<div class="blk"><div class="bh"><h3>지금 뜨는 특이신호</h3><a href="#">전체 46종목 →</a></div>{sig}<p class="note">상세 페이지가 없는 종목은 막지 않고 섹터 페이지로 보내요.</p></div>'

# ── 주도주 3종목 한 줄 ───────────────────────────────────────────────────
def leaders(weekly=False, off=0):
    t = ""
    for code in ("005930", "000660", "005380"):
        d = st[code]
        v = (d["spark20"][-1] / d["spark20"][-6] - 1) * 100 if weekly else chg(d, off)
        px = d["spark20"][-1 - off]
        t += f'''<a class="ld" href="/stocks/{code}/"><span>{d["name"]}</span><b>{px:,.0f}</b><em class="{"up" if v >= 0 else "dn"}">{v:+.2f}%</em></a>'''
    return f'<div class="blk"><div class="bh"><h3>주도주</h3><span>{"주간 등락" if weekly else ("10/22 종가" if off else "10/23 종가")}</span></div><div class="lds">{t}</div><details class="more"><summary>야간 추정가·수급 펼치기</summary><p class="note">지금의 주도주 위젯(곡선·뉴스 핀·수급)을 여기 접어 둬요.</p></details></div>'

# ── 구조 신호 카드 ───────────────────────────────────────────────────────
struct = '''<div class="blk"><div class="bh"><h3>구조 신호</h3><span>월 단위로 바뀌는 신호</span></div>
<a class="ss" href="/briefings/2026-10-23/us/"><span class="ss-k">나스닥 체크</span><b>+59.8%</b><span class="pill ok">✓ 정상</span><em>60개월선 대비 월봉 고점 · 60% 주의 · 70% 경고</em></a>
<a class="ss" href="/briefings/2026-10-23/kospi/"><span class="ss-k">월봉 5개월선 안착</span><b>메리츠금융지주</b><span class="pill nb">3개월째</span><em>지금 이격 +5.5% · 매매 신호 아님</em></a></div>'''

ovn = next(r for r in bridge["rows"] if r["sector"] == "반도체")
overnight = f'''<div class="blk one"><span class="ok-k">🌙 밤사이 미국</span> {ovn["us_label"]} <b class="{ovn["us_cls"]}">{ovn["us_change_fmt"]}</b> → 국내 {ovn["kr_label"]} <b class="{ovn["kr_cls"]}">{ovn["kr_change_fmt"]}</b> <a href="#">자세히 →</a></div>'''

# ── 밤사이 미국: 코스피 선행 ETF + AI 인프라 주식 (10/23 종가, /api/stocks-live 실값) ──
FX = 1326.9
US = {"DRAM": (47.06, 3.02), "EWY": (151.26, 1.48), "SOXX": (478.2, 0.53), "SKHY": (137.02, 4.05),
      "MU": (877.55, 2.46), "SNDK": (1238.03, -1.82), "NVDA": (210.96, -0.59), "AMD": (516.79, 1.74),
      "AVGO": (321.68, -0.48), "TSM": (418.51, 1.49), "ASML": (1571.8, 0.72)}
QQQ, VIX = -0.01, (19.45, 2.21)
def px(tk):
    usd = US[tk][0]
    return f'<span class="krw">{usd * FX:,.0f}원</span><span class="usd">${usd:,.2f}</span>'
cls = lambda v: "up" if v > 0 else ("dn" if v < 0 else "")
LEAD = [("EWY", "한국 ETF", "코스피 추종"), ("DRAM", "메모리·HBM", "삼성·하이닉스 선행"), ("SOXX", "반도체 ETF", "미 반도체 전체")]
lead_up = sum(1 for t, _, _ in LEAD if US[t][1] > 0)
lead_html = "".join(f'''<div class="ue-lead"><span class="ue-tk">{tk}</span><span class="ue-ln">{nm}</span><b class="{cls(US[tk][1])}">{US[tk][1]:+.2f}%</b>
<span class="ue-lp">{px(tk)}</span><span class="ue-ld">{d}</span></div>''' for tk, nm, d in LEAD)
GROUPS = [("메모리", [("SK하이닉스", "SKHY", "/stocks/000660/"), ("마이크론", "MU", "/stocks/us/mu/"), ("샌디스크", "SNDK", "/stocks/us/sndk/")]),
          ("AI 칩", [("엔비디아", "NVDA", "/stocks/us/nvda/"), ("AMD", "AMD", "/stocks/us/amd/"), ("브로드컴", "AVGO", "/stocks/us/avgo/")]),
          ("파운드리·장비", [("TSMC", "TSM", "/stocks/us/tsm/"), ("ASML", "ASML", "/stocks/us/asml/")])]
mx = max(abs(US[t][1]) for _, g in GROUPS for _, t, _ in g)
ai_html = ""
for gname, items in GROUPS:
    rows = "".join(f'''<a class="ue-row" href="{h}"><span class="ue-n">{n} <em>{t}</em></span><span class="ue-p">{px(t)}</span>
<span class="ue-bar"><i class="{cls(US[t][1])}" style="width:{abs(US[t][1])/mx*100:.0f}%"></i></span><b class="{cls(US[t][1])}">{US[t][1]:+.2f}%</b></a>''' for n, t, h in items)
    ai_html += f'<div class="ue-g"><div class="ue-gt">{gname}</div>{rows}</div>'
ai_up = sum(1 for _, g in GROUPS for _, t, _ in g if US[t][1] > 0)
ai_n = sum(len(g) for _, g in GROUPS)
us_block = f'''<div class="blk ue"><div class="bh"><h3>🌙 밤사이 미국</h3><div class="ue-cur"><button class="on" data-c="krw">원화</button><button data-c="usd">달러</button></div></div>
<div class="ue-meta"><span>10/23 종가</span><span>나스닥 QQQ <b class="{cls(QQQ)}">{QQQ:+.2f}%</b></span><span>VIX <b>{VIX[0]}</b> <b class="{cls(VIX[1])}">{VIX[1]:+.2f}%</b></span></div>
<div class="ue-sec"><div class="ue-st"><h4>코스피 선행 ETF</h4><span>{len(LEAD)}개 중 <b class="up">{lead_up} 상승</b></span></div>
<p class="ue-sd">한국 장이 열리기 전에 코스피 방향을 먼저 보여주는 ETF예요.</p><div class="ue-leads">{lead_html}</div></div>
<div class="ue-sec"><div class="ue-st"><h4>AI 인프라 주식</h4><span>{ai_n}개 중 <b class="up">{ai_up} 상승</b> · <b class="dn">{ai_n - ai_up} 하락</b></span></div><div class="ue-ais">{ai_html}</div></div>
<p class="note">환율 {FX:,.1f}원 적용 · 미국 장 시작 전엔 직전 종가, 장중엔 실시간</p></div>'''

trust = f'<div class="trust">시초가 예측 적중 <b>{acc["hit"]}/{acc["scored"]}</b> ({acc["pct"]}%) · 매일 07:25·16:25·21:15 발행</div>'
strip_b = lambda t: re.sub(r"<[^>]+>", "", t)

# ── 시간대 카드 ──────────────────────────────────────────────────────────
pred = ks["prediction"]
hero = {
"morning": f'''<div class="hero is-dn"><div class="hk"><span>오늘 07:29 · 코스피 시초가 예측</span><span class="live">새 브리핑</span></div>
<div class="hm"><b class="hd">↓ 하락 우위</b><b class="hp">{pred["down_pct"]}%<small>신뢰도 {pred["confidence"]}%</small></b></div>
<h2>어제 -3.52% 맞았는데 또? 메타發 반도체 -6.72% 2차 충격</h2>
<p class="dek">{ks["todays_view"]["dek"]}</p>
<a class="cta" href="/briefings/2026-10-23/kospi/">오늘 코스피 브리핑 보기 →</a>{trust}</div>''',
"intraday": f'''<div class="hero"><div class="hk"><span>장중 · 어제 같은 시각과 비교</span><span class="live">● 13:30</span></div>
<h2>{verdict}</h2>
<p class="dek">코스피 지금 <b class="{tcls}">{td_now:+.2f}%</b> · 어제 같은 시각 <b class="{ycls}">{yd_now:+.2f}%</b> — <b>{abs(diff):.2f}%p</b> {"높아요" if diff > 0 else "낮아요"}.</p>{curve}
<a class="cta ghost" href="/briefings/2026-10-23/kospi/">아침 예측 다시 보기 →</a></div>''',
"close": '''<div class="hero"><div class="hk"><span>오늘 16:32 · 코스피 마감</span><span class="live">새 브리핑</span></div>
<h2>-4%까지 빠졌는데 플러스 마감? 기관이 코스피를 끌어올렸다</h2>
<p class="dek">기관이 <b>8,726억원</b>을 사들이며 받쳤지만, 외국인은 <b>9,934억원</b>을 던지고 떠났어요.</p>
<div class="chip ok">📝 아침 시초가 예측 하락 우위 → 시초가 -2.36% ✓ 적중</div>
<a class="cta" href="/briefings/2026-10-23/close/">마감 브리핑 보기 →</a></div>''',
"evening": f'''<div class="hero is-dn"><div class="hk"><span>오늘 21:17 · 미국 시장 브리핑</span><span class="live">새 브리핑</span></div>
<div class="hm"><b class="hd">↓ 하락 우위</b><b class="hp">{us["prediction"]["down_pct"]}%</b></div>
<h2>반도체가 먼저 맞았다 — 빅테크 실적·FOMC가 몰려오는 한 주</h2>
<p class="dek">직전 정규장에서 <b>반도체·메모리</b>에 매물이 쏟아졌고, 프리마켓에서도 SOX가 고개를 못 들고 있어요. 이번 주엔 <b>빅테크 실적</b>과 <b>FOMC</b>가 줄줄이 나와요.</p>
<div class="chip">나스닥 체크 <b>+59.8%</b> · ✓ 정상</div>
<a class="cta" href="/briefings/2026-10-23/us/">미국 브리핑 보기 →</a></div>''',
"weekend": '''<div class="hero"><div class="hk"><span>이번 주 정리 · 10/19~10/23</span><span class="live wk">주말</span></div>
<div class="wk3"><div><span>코스피 주간</span><b class="dn">-2.08%</b><em>5,668 → 5,550</em></div>
<div><span>예측 성적</span><b>3/5</b><em>시초가 기준</em></div>
<div><span>가장 강했던 섹터</span><b class="WKTOPCLS">WKTOP</b><em>WKTOPV</em></div></div>
<h2>+1.76 → -3.73 → +3.29 → -3.52, 하루씩 뒤집힌 롤러코스터</h2>
<p class="dek">코스피는 닷새 내내 오름과 내림을 번갈아 하다 주간 <b class="dn">-2.08%</b>로 마쳤어요.</p>
<a class="cta ghost" href="/briefings/">이번 주 브리핑 다시 보기 →</a></div>''',
}
wk = sec_rows(weekly=True)
top = wk[0]
hero["weekend"] = (hero["weekend"].replace("WKTOPCLS", "up" if top[2] >= 0 else "dn")
                   .replace("WKTOPV", f"{top[2]:+.2f}%").replace("WKTOP", top[1]))

day = sec_rows()
day_prev = sec_rows(off=1)
kospi_1330 = PREV1 * (1 + td_now / 100)
ibar = {
"morning": '<div class="ibar"><span>10/22 마감</span><span>코스피 <b>5,533.77</b> <span class="dn">-3.52%</span></span><span>코스닥 <b>764.10</b> <span class="dn">-3.62%</span></span></div>',
"intraday": f'<div class="ibar"><span>13:30</span><span>코스피 <b>{kospi_1330:,.2f}</b> <span class="{tcls}">{td_now:+.2f}%</span></span></div>',
}
close_bar = '<div class="ibar"><span>10/23 마감</span><span>코스피 <b>5,550.30</b> <span class="up">+0.30%</span></span><span>코스닥 <b>751.69</b> <span class="dn">-1.62%</span></span><span>기관 <b class="up">+8,682</b> 외국인 <b class="dn">-9,811</b>억</span></div>'

body = {
"morning": us_block + leaders(off=1) + struct + sec_html(day_prev, "10/22 종가"),
"intraday": sig_html + leaders() + sec_html(day, "프로토타입: 10/23 종가로 대신"),
"close": sec_html(day, "10/23 마감") + sig_html + leaders(),
"evening": us_block + leaders() + struct + sec_html(day, "10/23 마감"),
"weekend": struct + sec_html(wk, "주간 등락") + leaders(weekly=True),
}
slots = [("morning", "07:30 아침"), ("intraday", "장중"), ("close", "15:30 마감"), ("evening", "21:15 미국"), ("weekend", "주말")]
panes = "".join(f'<section class="pane" data-slot="{k}"{"" if k == "weekend" else " hidden"}>{ibar.get(k, close_bar)}{hero[k]}{body[k]}</section>' for k, _ in slots)
switch = "".join(f'<button data-s="{k}"{" class=on" if k == "weekend" else ""}>{l}</button>' for k, l in slots)

page = f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>종목 시그널 개편안</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<style>
:root{{--ink:#13151a;--ink2:#4b5563;--muted:#6b7280;--line:#e5e7eb;--bg:#f6f7f9;--card:#fff;--up:#e03131;--dn:#2775ed;--pri:#2563eb;--ok:#059669}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);font-family:'Pretendard Variable',Pretendard,system-ui,sans-serif;color:var(--ink);-webkit-font-smoothing:antialiased}}
a{{color:inherit;text-decoration:none}} .up{{color:var(--up)}} .dn{{color:var(--dn)}}
.gnb{{position:sticky;top:0;z-index:5;background:#16181a;color:#fff;height:52px;display:flex;align-items:center;gap:14px;padding:0 16px}}
.gnb b{{font-size:17px}} .gnb b span{{color:#60a5fa}} .gnb a{{font-size:13px;color:#cbd5e1}} .gnb .on{{color:#4ade80;font-weight:700}}
.wrap{{max-width:480px;margin:0 auto;padding:12px 16px 40px}}
.proto{{border:1px dashed #c4b5fd;border-radius:12px;padding:8px 10px;margin-bottom:12px;font-size:11px;color:#7c3aed;background:#faf5ff}}
.proto div{{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}}
.proto button{{border:1px solid #ddd6fe;background:#fff;color:#6d28d9;border-radius:999px;padding:4px 10px;font-size:12px;cursor:pointer;font-family:inherit}}
.proto button.on{{background:#7c3aed;color:#fff;border-color:#7c3aed}}
.ttl{{display:flex;justify-content:space-between;align-items:center;margin:4px 0 10px}} .ttl h1{{font-size:15px;margin:0;color:var(--muted);font-weight:700}}
.ttl .q{{border:1px solid var(--line);background:#fff;border-radius:10px;padding:6px 10px;font-size:12px;color:var(--muted)}}
.ibar{{display:flex;gap:12px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin-bottom:10px}} .ibar b{{color:var(--ink)}}
.hero{{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:16px 16px 14px;box-shadow:0 1px 2px rgba(0,0,0,.04)}}
.hero.is-dn{{background:linear-gradient(180deg,#eef4ff,#fff 60%)}}
.hk{{display:flex;justify-content:space-between;font-size:12px;color:var(--muted);font-weight:600}}
.live{{color:var(--pri)}} .live.wk{{color:var(--muted)}}
.hm{{display:flex;justify-content:space-between;align-items:baseline;margin-top:8px}}
.hd,.hp{{font-size:26px;font-weight:800;letter-spacing:-.5px;line-height:1.2}} .hero.is-dn .hd,.hero.is-dn .hp{{color:var(--dn)}}
.hp{{text-align:right}} .hp small{{display:block;font-size:12px;font-weight:500;color:var(--muted);letter-spacing:0}}
.hero h2{{font-size:17px;line-height:1.45;margin:10px 0 0;letter-spacing:-.2px}}
.dek{{font-size:13.5px;line-height:1.7;color:var(--ink2);margin:6px 0 0}} .dek b{{color:var(--ink)}}
.cta{{display:block;margin-top:12px;background:var(--ink);color:#fff;text-align:center;border-radius:10px;padding:10px;font-size:13px;font-weight:700}}
.cta.ghost{{background:#fff;color:var(--ink);border:1px solid var(--line)}}
.trust{{margin-top:10px;font-size:11.5px;color:var(--muted);text-align:center}} .trust b{{color:var(--ink)}}
.chip{{display:inline-block;margin-top:10px;font-size:12px;border:1px solid var(--line);border-radius:999px;padding:5px 11px;background:#f9fafb}} .chip.ok{{color:#065f46;background:#ecfdf5;border-color:#a7f3d0}}
.idx2{{display:flex;gap:14px;margin-top:10px;font-size:13px;color:var(--muted)}} .idx2 b{{color:var(--ink);font-size:16px}} .idx2 em{{font-style:normal;font-weight:700}}
.wk3{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:10px}} .wk3 div{{background:#f9fafb;border-radius:12px;padding:9px 10px}}
.wk3 span{{display:block;font-size:11px;color:var(--muted)}} .wk3 b{{display:block;font-size:18px;margin-top:2px}} .wk3 em{{font-style:normal;font-size:11px;color:var(--muted)}}
.cv{{position:relative;height:130px;margin-top:12px}} .cv svg{{position:absolute;inset:0;width:100%;height:100%}}
.cv .rest{{fill:#f3f4f6}} .cv .zero{{stroke:#d1d5db;stroke-dasharray:3 3;vector-effect:non-scaling-stroke}}
.cv .yd{{fill:none;stroke:#9ca3af;stroke-width:1.5;vector-effect:non-scaling-stroke}} .cv .td{{fill:none;stroke:var(--up);stroke-width:2.2;vector-effect:non-scaling-stroke}} .cv .td.dn{{stroke:var(--dn)}}
.cv-dot.dn{{background:var(--dn)}} .cv-dot{{position:absolute;width:9px;height:9px;border-radius:50%;background:var(--up);border:2px solid #fff;transform:translate(-50%,-50%)}}
.cv-l{{position:absolute;right:0;font-size:10px;color:var(--muted);transform:translateY(-120%)}}
.cv-ax{{position:absolute;left:0;right:0;bottom:-16px;display:flex;justify-content:space-between;font-size:10px;color:var(--muted)}}
.cv-lg{{display:flex;gap:12px;font-size:11px;color:var(--muted);margin-top:22px}} .cv-lg i{{display:inline-block;width:12px;height:3px;border-radius:2px;margin-right:4px;vertical-align:middle}}
.cv-lg i.td{{background:var(--ink)}} .cv-lg i.yd{{background:#9ca3af}}
.blk{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:13px 14px;margin-top:12px}}
.blk.one{{font-size:13px;line-height:1.6}} .blk.one a{{color:var(--pri);font-weight:600;white-space:nowrap}} .ok-k{{font-weight:700}}
.bh{{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px}} .bh h3{{margin:0;font-size:15px}} .bh span{{font-size:11.5px;color:var(--muted)}} .bh a{{font-size:12px;color:var(--pri);font-weight:600}}
.sb{{display:grid;grid-template-columns:64px 1fr 58px;align-items:center;gap:8px;padding:5px 0;font-size:13px}} .sb b{{text-align:right;font-size:12.5px}}
.sb-bar{{position:relative;height:8px;background:#f3f4f6;border-radius:4px}} .sb-bar i{{position:absolute;top:0;height:100%;border-radius:4px}} .sb-bar i.up{{background:#f87171}} .sb-bar i.dn{{background:#60a5fa}}
.sb-bar::after{{content:'';position:absolute;left:50%;top:-2px;bottom:-2px;width:1px;background:#d1d5db}}
.note{{font-size:11px;color:var(--muted);margin:8px 0 0}}
.sg{{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-top:1px solid #f3f4f6}} .sg:first-of-type{{border-top:0}}
.sg span{{display:block;font-size:11.5px;color:var(--muted);margin-top:1px}} .sg-r{{text-align:right}} .sg-r b{{display:block;font-size:14px}}
.go{{font-size:11.5px;color:var(--pri);font-weight:600}} .go.soft{{color:var(--muted)}}
.lds{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}} .ld{{background:#f9fafb;border-radius:12px;padding:9px 10px}}
.ld span{{display:block;font-size:11.5px;color:var(--muted)}} .ld b{{display:block;font-size:15px;margin-top:2px}} .ld em{{font-style:normal;font-size:12px;font-weight:700}}
.more summary{{font-size:12px;color:var(--muted);margin-top:8px;cursor:pointer}}
.ss{{display:grid;grid-template-columns:1fr auto;gap:2px 8px;align-items:center;padding:9px 0;border-top:1px solid #f3f4f6}} .ss:nth-of-type(1){{border-top:0}}
.ss-k{{font-size:12px;color:var(--muted)}} .ss b{{font-size:15px;grid-column:1}} .ss .pill{{grid-column:2;grid-row:1/3;font-size:12px;border-radius:999px;padding:3px 9px;font-weight:700}}
.pill.ok{{background:#ecfdf5;color:var(--ok)}} .pill.nb{{background:#eff6ff;color:var(--pri)}} .ss em{{grid-column:1/3;font-style:normal;font-size:11px;color:var(--muted)}}
.ue-cur{{display:flex;border:1px solid var(--line);border-radius:999px;overflow:hidden}} .ue-cur button{{border:0;background:#fff;padding:4px 11px;font-size:12px;font-family:inherit;color:var(--muted);cursor:pointer}} .ue-cur button.on{{background:var(--ink);color:#fff}}
.ue .usd{{display:none}} .ue.is-usd .usd{{display:inline}} .ue.is-usd .krw{{display:none}}
.ue-meta{{display:flex;gap:12px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin:-2px 0 4px}} .ue-meta b{{color:var(--ink)}} .ue-meta b.up{{color:var(--up)}} .ue-meta b.dn{{color:var(--dn)}}
.ue-sec{{border-top:1px solid #f3f4f6;margin-top:10px;padding-top:10px}}
.ue-st{{display:flex;justify-content:space-between;align-items:baseline}} .ue-st h4{{margin:0;font-size:14px}} .ue-st span{{font-size:12px;color:var(--muted)}}
.ue-sd{{font-size:11.5px;color:var(--muted);margin:3px 0 8px}}
.ue-leads{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}}
.ue-lead{{background:#f9fafb;border-radius:12px;padding:9px 10px;display:flex;flex-direction:column;gap:1px;min-width:0}}
.ue-ln{{font-size:11.5px;color:var(--ink2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}} .ue-ln em,.ue-n em{{font-style:normal;color:var(--muted);font-size:11px}}
.ue-tk{{font-size:13px;font-weight:800;letter-spacing:.2px}} .ue-lead b{{font-size:19px;letter-spacing:-.4px}} .ue-lp{{font-size:11.5px;color:var(--ink2)}} .ue-ld{{font-size:10.5px;color:var(--muted);margin-top:2px}}
.ue-g{{margin-top:8px}} .ue-gt{{font-size:11px;font-weight:700;color:var(--muted);margin-bottom:2px}}
.ue-row{{display:grid;grid-template-columns:1fr auto 54px 56px;gap:8px;align-items:center;padding:6px 0;font-size:13px}}
.ue-p{{font-size:12.5px;font-weight:600;text-align:right;font-variant-numeric:tabular-nums}}
.ue-bar{{height:6px;background:#f3f4f6;border-radius:3px;overflow:hidden}} .ue-bar i{{display:block;height:100%;border-radius:3px}} .ue-bar i.up{{background:#f87171}} .ue-bar i.dn{{background:#60a5fa}}
.ue-row b{{text-align:right;font-size:13px;font-variant-numeric:tabular-nums}}
@media (min-width:720px){{
.wrap{{max-width:880px;padding:20px 24px 48px}}
.ttl h1{{font-size:16px}}
.hero{{padding:18px 22px 16px}}
.trust{{text-align:left}}
.cta{{display:inline-block;padding:9px 22px}}
.cv{{height:220px}}
.blk{{padding:16px 20px}}
.ue-ais{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}}
.ue-row{{grid-template-columns:1fr auto 48px}} .ue-row .ue-bar{{display:none}}
.sbs{{display:grid;grid-template-columns:1fr 1fr;grid-template-rows:repeat(4,auto);grid-auto-flow:column;column-gap:28px}}
}}
.foot{{margin-top:18px;display:flex;gap:10px;justify-content:center;font-size:12px}} .foot a{{color:var(--pri);font-weight:600}}
</style></head><body>
<div class="gnb"><b>Double<span>-Shot</span></b><a class="on">종목</a><a>브리핑</a><a>월배당</a></div>
<div class="wrap">
<div class="proto">프로토타입 · 시간대를 눌러 첫 화면이 어떻게 바뀌는지 보세요 (숫자는 10/23 금요일 실데이터 — 각 시간대에 알 수 있던 값만, 헤드라인은 새 규칙 예시. 장중 카드의 특이신호·섹터만 10/23 종가로 대신)<div>{switch}</div></div>
<div class="ttl"><h1>종목 시그널</h1><span class="q">🔍 종목 검색</span></div>
{panes}
<div class="foot"><a href="/briefings/">브리핑 아카이브</a><a href="/stocks/income-designer/">월배당 설계</a></div>
</div>
<script>document.querySelectorAll('.ue-cur button').forEach(b=>b.onclick=()=>{{document.querySelectorAll('.ue').forEach(u=>u.classList.toggle('is-usd',b.dataset.c==='usd'));
document.querySelectorAll('.ue-cur button').forEach(x=>x.classList.toggle('on',x.dataset.c===b.dataset.c));}});
document.querySelectorAll('.proto button').forEach(b=>b.onclick=()=>{{
document.querySelectorAll('.proto button').forEach(x=>x.classList.toggle('on',x===b));
document.querySelectorAll('.pane').forEach(p=>p.hidden=p.dataset.slot!==b.dataset.s);}});</script>
</body></html>'''
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(page, encoding="utf-8")
DOC.write_text(page.replace("<head>", "<head>\n<!-- 종목 시그널 첫 페이지 개편 프로토타입(시간대 5종 첫 화면 + 압축 홈) — 10/23 실데이터, 헤드라인은 새 규칙 예시 -->\n<base href=\"https://doubleshot.space/\">", 1), encoding="utf-8")
print("ok", f"intraday today {td_now:+.2f} yd {yd_now:+.2f}", "week top", top[1], f"{top[2]:+.2f}", "signals", [c[2]["name"] for c in cands[:3]])
