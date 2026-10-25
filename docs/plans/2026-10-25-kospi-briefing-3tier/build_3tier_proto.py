# 코스피 아침 브리핑 3단 구조 프로토타입 — 앞선 미리보기(월봉 5개월선 A안 포함) 위에 요약·이슈 점검·더 보기를 재배치
import json, html as H, re
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path("/Users/luke/Service App/double-shot")
SRC = ROOT / "web/_proto/ma5final/index.html"
OUT = ROOT / "web/_proto/3tier/index.html"
DOC = ROOT / "docs/prototypes/2026-10-25-kospi-briefing-3tier.html"
snap = json.loads((ROOT / "web/briefings/2026-10-23/kospi/analysis_snapshot.json").read_text())
recs = json.loads((ROOT / "data/briefings.json").read_text())
recs = recs if isinstance(recs, list) else recs.get("briefings", [])

pred = snap["prediction"]
tv = snap["todays_view"]
down = pred["direction"].startswith("하락")
prob = pred["down_pct"] if down else pred["up_pct"]

# 어제 예측 결과(10/22) — 기록 그대로
y = next(r for r in recs if r.get("type") == "kospi" and r["date"] == "2026-10-22")
y_ok = y["is_correct"]
y_dir = y["predicted_direction"].replace(" 우위", "")
# 성적표 — 같은 페이지 사이드바와 같은 기준(시초가 기준 채점 기록)
op = [r for r in recs if r.get("type") == "kospi" and r.get("basis") == "open" and r.get("is_correct") is not None]
hit, n = sum(r["is_correct"] for r in op), len(op)
base = round(sum(1 for r in op if (r.get("actual_open_pct") or 0) > 0) / n * 100)
acc = round(hit / n * 100)


def chip_mark(m):
    p = m["pct"]
    return f'<span class="ic-tk {"up" if p > 0 else "dn"}">{H.escape(m["name"])} <b>{p:+.2f}%</b></span>'


def card(tag, tag_cls, title, body, impact=None, foot="", links=""):
    imp = (f'<span class="ic-imp {impact}">코스피 {"▼" if impact == "dn" else "▲"} <em>AI 판단</em></span>' if impact else "")
    return f'''<div class="ic-card">
  <div class="ic-top"><span class="ic-tag {tag_cls}">{tag}</span>{imp}</div>
  <div class="ic-title">{title}</div>
  <div class="ic-body">{body}</div>
  {f'<div class="ic-links">{links}</div>' if links else ''}
  {f'<div class="ic-foot">{foot}</div>' if foot else ''}
</div>'''


uc = snap["us_issue_results"]["cards"]
cards = []
# ① 간밤 미국(실측) — 이슈 결과 카드 3장을 그대로, 숫자는 여기서 한 번만
for i, c in enumerate(uc):
    marks = "".join(chip_mark(m) for sd in c["sides"] for m in sd["marks"])
    proxy = next((sd.get("proxy") for sd in c["sides"] if sd.get("proxy")), None)
    foot = "종목이 지정되지 않아 S&P500 실측으로 봤어요." if proxy else ""
    links = ('<span class="ic-lk-l">국내 연결</span><a href="/stocks/005930/">삼성전자</a><a href="/stocks/000660/">SK하이닉스</a>'
             '<span class="ic-lk-n">AI 해석</span>') if "반도체" in c["title"] else ""
    cards.append(card("간밤 미국 · 실측", "fact", H.escape(re.sub(r"\s*—.*$", "", c["title"])),
                      f'<p>{c["check_line"]}</p><div class="ic-tks">{marks}</div>', "dn", foot, links))
# ② 국내 뉴스 — 기존 수집분(출처·링크 그대로)
soup = BeautifulSoup(SRC.read_text(encoding="utf-8"), "html.parser")
dom_items = []
for a in soup.select(".dom-card"):
    dom_items.append(f'<a class="ic-news" href="{a["href"]}" target="_blank" rel="noopener noreferrer">'
                     f'<b>{a.select_one(".dom-title").get_text()}</b><span>{a.select_one(".dom-src").get_text()}</span></a>')
cards.append(card("국내 · 뉴스", "news", "어제 장 이후 국내 소식", "".join(dom_items)))
# ③ 오늘 확인할 것 — AI 관전 포인트
watch = "".join(f"<li>{o['text']}</li>" for o in tv.get("outlook", []))
cards.append(card("오늘 볼 것 · AI 해석", "ai", "개장 뒤 확인할 세 가지", f'<ul class="ic-ul">{watch}</ul>'))

hero = f'''<div class="bx-hero {"dn" if down else "up"}">
  <div class="bx-k"><span>10월 23일(금) 시초가 방향 예측</span><span class="bx-k-t">06:35 생성</span></div>
  <div class="bx-main">
    <div class="bx-dir"><span class="bx-arrow">{"↓" if down else "↑"}</span>{pred["direction"]}</div>
    <div class="bx-prob"><b>{prob}%</b><span>신뢰도 {pred["confidence"]}%</span></div>
  </div>
  <div class="bx-head">{H.escape(tv["view_title"])}</div>
  <p class="bx-dek">{tv.get("dek", "")}</p>
  <div class="bx-chips">
    <span class="bx-chip {"ok" if y_ok else "miss"}"><em>어제 예측</em><b>{y_dir} → {"적중" if y_ok else "빗나감"}</b><span>시초가 {y["actual_open_pct"]:+.2f}%</span></span>
  </div>
  <p class="bx-def">09:00 코스피가 전일 종가보다 위로 열릴지 아래로 열릴지에 대한 확률이에요. 장중 흐름과 종가는 예측하지 않아요.</p>
</div>'''

issues = f'''<div class="open-section ic-section">
  <div class="ic-h"><h2>오늘의 이슈 점검</h2><span>간밤 미국 · 국내 · 오늘 볼 것</span></div>
  <div class="ic-list">{"".join(cards)}</div>
  <div class="ic-src">실측 = 거래소 종가로 확인한 숫자 · 뉴스 = 수집한 기사 원문 · AI 해석 = 분석 모델의 판단이에요.
    <a href="/briefings/2026-10-22/us/">간밤 미국 브리핑 보기 →</a></div>
</div>'''

inner = soup.select_one(".accordion-body__inner")
ma5 = inner.select_one(".ma5m-section")
ma5_html = str(ma5)
inner.clear()
inner.append(BeautifulSoup(hero + issues + '<div class="divider"></div>' + ma5_html, "html.parser"))
sc = soup.select_one(".sc-card")
if sc is not None:
    sc["id"] = "scorecard"

css = '''<style id="tier3-css">
.bx-hero{border:1px solid var(--hairline);border-radius:var(--r-lg);padding:16px 18px 14px;background:var(--canvas);box-shadow:var(--s1);margin-top:4px}
.bx-hero.dn{background:linear-gradient(180deg,var(--dn-bg),var(--canvas) 70%)} .bx-hero.up{background:linear-gradient(180deg,var(--up-bg),var(--canvas) 70%)}
.bx-k{display:flex;justify-content:space-between;font-size:12px;color:var(--muted);font-weight:600}
.bx-main{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-top:8px}
.bx-dir{font-size:30px;font-weight:800;letter-spacing:-.6px;line-height:1.15;color:var(--ink);display:flex;align-items:baseline;gap:6px}
.bx-hero.dn .bx-dir,.bx-hero.dn .bx-prob b{color:var(--dn)} .bx-hero.up .bx-dir,.bx-hero.up .bx-prob b{color:var(--up)}
.bx-arrow{font-size:26px}
.bx-prob{text-align:right} .bx-prob b{display:block;font-size:30px;font-weight:800;line-height:1.15;letter-spacing:-1px}
.bx-prob span{font-size:11px;color:var(--muted)}
.bx-head{font-size:15px;font-weight:600;color:var(--ink);line-height:1.5;margin-top:10px}
.accordion-body__inner>.ma5m-section:last-child{margin-bottom:28px}
.bx-dek{font-size:13px;color:var(--ink-2,#4b5563);line-height:1.65;margin:6px 0 0} .bx-dek b{font-weight:700;color:var(--ink)}
.bx-chips{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.bx-chip{display:flex;align-items:baseline;gap:6px;flex-wrap:wrap;background:var(--surface-soft);border:1px solid var(--hairline);border-radius:999px;padding:5px 11px;font-size:12px;color:var(--ink);text-decoration:none}
.bx-chip em{font-style:normal;color:var(--muted)} .bx-chip b{font-weight:700} .bx-chip span{color:var(--muted);font-size:11px}
.bx-chip.miss b{color:var(--muted)} .bx-chip.ok b{color:var(--primary)}
.bx-def{font-size:11px;color:var(--muted);line-height:1.6;margin-top:10px}
.ic-section{margin-top:26px}
.ic-h{display:flex;align-items:baseline;gap:10px;margin-bottom:10px;flex-wrap:wrap} .ic-h h2{font-size:18px;font-weight:800;color:var(--ink);letter-spacing:-.3px}
.ic-h span{font-size:12px;color:var(--muted)}
.ic-list{display:flex;flex-direction:column;gap:10px}
.ic-card{border:1px solid var(--hairline);border-radius:var(--r-lg);padding:13px 15px;background:var(--canvas)}
.ic-top{display:flex;justify-content:space-between;align-items:center;gap:8px}
.ic-tag{font-size:11px;font-weight:700;border-radius:999px;padding:2px 9px}
.ic-tag.fact{background:var(--surface-inset);color:var(--ink)} .ic-tag.news{background:var(--gold-bg);color:var(--gold)} .ic-tag.ai{background:var(--primary-bg);color:var(--primary)}
.ic-imp{font-size:12px;font-weight:700} .ic-imp.dn{color:var(--dn)} .ic-imp.up{color:var(--up)} .ic-imp em{font-style:normal;font-weight:500;color:var(--muted);font-size:10px;margin-left:3px}
.ic-title{font-size:15px;font-weight:700;color:var(--ink);margin-top:8px}
.ic-body{font-size:13px;color:var(--ink);line-height:1.65;margin-top:4px} .ic-body p{margin:0}
.ic-tks{display:flex;flex-wrap:wrap;gap:5px;margin-top:7px}
.ic-tk{font-size:11.5px;border-radius:6px;padding:2px 7px;background:var(--surface-soft);color:var(--ink);font-variant-numeric:tabular-nums}
.ic-tk.dn b{color:var(--dn)} .ic-tk.up b{color:var(--up)}
.ic-links{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-top:9px;font-size:12px}
.ic-links a{color:var(--primary);font-weight:600;text-decoration:none;border:1px solid var(--primary-bg);background:var(--primary-bg);border-radius:999px;padding:2px 9px}
.ic-lk-l{color:var(--muted)} .ic-lk-n{color:var(--muted);font-size:10px}
.ic-foot{font-size:11px;color:var(--muted);margin-top:7px}
.ic-news{display:flex;justify-content:space-between;gap:10px;padding:7px 0;border-top:1px solid var(--hairline);color:var(--ink);text-decoration:none;font-size:13px}
.ic-news:first-child{border-top:0;padding-top:2px} .ic-news span{color:var(--muted);font-size:11px;white-space:nowrap}
.ic-ul{margin:2px 0 0;padding-left:18px;display:flex;flex-direction:column;gap:4px}
.ic-src{font-size:11px;color:var(--muted);line-height:1.6;margin-top:10px} .ic-src a{color:var(--primary);font-weight:600;white-space:nowrap}
</style>'''
out = str(soup).replace("</head>", css + "\n</head>", 1)
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(out, encoding="utf-8")
DOC.write_text(out.replace("<head>", "<head>\n<!-- 코스피 아침 브리핑 3단 구조 프로토타입(30초 요약·오늘의 이슈 점검·월봉 5개월선) — 10/23 발행본 기반, 스타일은 운영 사이트에서 불러온다 -->\n<base href=\"https://doubleshot.space/\">", 1), encoding="utf-8")
print(OUT, f"적중 {hit}/{n} 기준선 {base}% 어제 {y_dir} {'적중' if y_ok else '빗나감'}")
