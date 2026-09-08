# 실측 카드 → '이슈 체크'(판정 제거) 3안 프로토타입 생성. 수치는 발행 스냅샷에서만 온다.
import json, pathlib

snap = json.load(open("web/briefings/2026-09-07/kospi/analysis_snapshot.json"))
cards = snap["us_issue_results"]["cards"]

def fmt(p): return ("+" if p >= 0 else "−") + f"{abs(p):.2f}%"

def _batchim(w):
    """마지막 글자에 받침이 있는지. 한글이 아니면 있는 것으로 본다."""
    if not w: return True
    ch = w[-1]
    if not ("가" <= ch <= "힣"): return True
    return (ord(ch) - 0xAC00) % 28 != 0

def eun_neun(w):   # 지수 전반'은' / 전기차'는'
    return "은" if _batchim(w) else "는"
def cls(p): return "up" if p > 0 else ("dn" if p < 0 else "flat")

def tickers(marks, judged):
    out = []
    for m in marks:
        if judged:
            c = "chk-tk hit" + (" dnmove" if m["pct"] < 0 else "") if m["hit"] else "chk-tk miss"
        else:
            c = f"chk-tk {cls(m['pct'])}"
        out.append(f'<span class="{c}">{m["name"]} <span class="pct">{fmt(m["pct"])}</span></span>')
    return "".join(out)

def mood(marks):
    ups = sum(1 for m in marks if m["pct"] > 0)
    dns = sum(1 for m in marks if m["pct"] < 0)
    if len(marks) == 1:
        m = marks[0]
        return "올랐어요" if m["pct"] > 0 else ("내렸어요" if m["pct"] < 0 else "보합이었어요")
    if ups and dns: return "엇갈렸어요"
    if ups: return "나란히 올랐어요"
    if dns: return "나란히 내렸어요"
    return "보합이었어요"

def render(variant):
    rows = []
    for c in cards:
        s = c["sides"][0]
        marks, label = s["marks"], s["label"]
        arrow = "▲" if s["side"] == "up" else "▼"
        proxy = (f'<div class="proxy-note">※ 종목이 지정되지 않아 {marks[0]["name"]} 실측으로 봤어요.</div>'
                 if s.get("proxy") else "")
        if variant == "A":
            body = f'<div class="chk-row"><span class="chk-label">{label}</span>{tickers(marks, False)}</div>'
        elif variant == "B":
            body = (f'<div class="chk-line">{label}{eun_neun(label)} <b>{mood(marks)}</b></div>'
                    f'<div class="chk-row">{tickers(marks, False)}</div>')
        else:  # C — 이슈가 본 방향을 맥락으로 남기되 판정하지 않는다
            side_ko = "상방 요인으로 봤어요" if s["side"] == "up" else "하방 요인으로 봤어요"
            body = (f'<div class="chk-line"><span class="chk-side {s["side"]}">{arrow} {label}</span> '
                    f'<span class="chk-dim">{side_ko}</span></div>'
                    f'<div class="chk-row">{tickers(marks, False)}</div>')
        rows.append(f'''    <div class="issue-card">
      <div class="issue-card__title">{c["title"]}</div>
      {body}{proxy}
    </div>''')
    return "\n".join(rows)

TPL = '''<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>이슈 체크 — 3안</title>
<style>
:root{--canvas:#FFF;--surface-soft:#F9FAFB;--surface-inset:#EEF1F5;--hairline:#E5E7EB;--ink:#13151A;--muted:#6B7280;
 --primary:#006EFF;--primary-bg:#E8F4FF;--up:#F33942;--up-bg:#FFF5F7;--dn:#006EFF;--dn-bg:#EFF6FF;
 --gold:#B7791F;--gold-bg:#FEF3C7;--r-md:10px;--r-lg:16px;}
html.dark{--canvas:#1C1D1F;--surface-soft:#242628;--surface-inset:#2A2B2D;--hairline:#3C3E40;--ink:#F3F5F7;--muted:#888B90;
 --primary:#1C82FF;--primary-bg:rgba(28,130,255,.12);--up:#F74B53;--up-bg:rgba(247,75,83,.15);
 --dn:#1C82FF;--dn-bg:rgba(0,110,255,.15);--gold:#E0B252;--gold-bg:rgba(224,178,82,.14);}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
html{font-size:15px;-webkit-font-smoothing:antialiased;}
body{font-family:'Pretendard Variable','Pretendard',-apple-system,sans-serif;background:var(--surface-soft);
 color:var(--ink);word-break:keep-all;padding:26px 18px 80px;}
.wrap{max-width:660px;margin:0 auto;}
.toggle{position:fixed;top:14px;right:14px;z-index:9;background:var(--canvas);border:1px solid var(--hairline);
 border-radius:999px;padding:7px 14px;font-size:12px;font-weight:700;color:var(--ink);cursor:pointer;}
h1{font-size:19px;font-weight:800;letter-spacing:-.02em;}
.intro{font-size:13px;color:var(--muted);margin-top:8px;line-height:1.7;}
.variant{margin-top:32px;}
.tag{display:inline-block;font-size:11px;font-weight:800;background:var(--gold-bg);color:var(--gold);
 padding:4px 10px;border-radius:999px;margin-bottom:6px;}
.note{font-size:12.5px;color:var(--muted);line-height:1.7;margin:8px 0 14px;}
.panel{background:var(--canvas);border:1px solid var(--hairline);border-radius:var(--r-lg);padding:20px 18px;}
.open-section__title{font-size:11px;font-weight:600;color:var(--muted);letter-spacing:.06em;text-transform:uppercase;
 margin-bottom:12px;display:flex;align-items:center;gap:6px;}
.open-section__title::before{content:'';display:block;width:3px;height:12px;background:var(--primary);border-radius:2px;}
.us-badge{display:inline-flex;align-items:center;gap:4px;background:var(--primary-bg);color:var(--primary);
 font-size:11px;font-weight:700;padding:3px 8px;border-radius:4px;margin-right:6px;line-height:1;}
.issue-list{display:flex;flex-direction:column;gap:12px;counter-reset:issue;}
.issue-card{border:1px solid var(--hairline);border-radius:var(--r-md);padding:15px 16px;background:var(--canvas);}
.issue-card__title{font-size:15px;font-weight:800;color:var(--ink);letter-spacing:-.02em;line-height:1.4;
 display:flex;align-items:center;gap:8px;}
.issue-card__title::before{counter-increment:issue;content:counter(issue);flex:0 0 20px;width:20px;height:20px;
 border-radius:50%;background:var(--primary-bg);color:var(--primary);font-size:11px;font-weight:800;
 display:flex;align-items:center;justify-content:center;}
.chk-line{font-size:12.5px;font-weight:700;color:var(--ink);margin-top:11px;padding-top:11px;
 border-top:1px dashed var(--hairline);line-height:1.5;}
.chk-dim{font-weight:600;color:var(--muted);}
.chk-side{font-weight:800;}
.chk-side.up{color:var(--up);} .chk-side.down{color:var(--dn);}
.chk-row{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-top:9px;}
.chk-row:first-child{margin-top:11px;padding-top:11px;border-top:1px dashed var(--hairline);}
.chk-label{font-size:12px;font-weight:800;color:var(--muted);margin-right:3px;}
.chk-tk{display:inline-flex;align-items:center;gap:5px;font-size:11.5px;font-weight:700;padding:2px 8px;
 border-radius:5px;background:var(--surface-inset);color:var(--ink);}
.chk-tk .pct{font-variant-numeric:tabular-nums;font-weight:800;}
.chk-tk.up{background:var(--up-bg);color:var(--up);}
.chk-tk.dn{background:var(--dn-bg);color:var(--dn);}
.proxy-note{font-size:11px;color:var(--muted);margin-top:8px;line-height:1.5;}
.sec-foot{font-size:11.5px;color:var(--muted);margin-top:12px;}
.sec-foot a{color:var(--primary);font-weight:700;}
</style></head><body>
<button class="toggle" onclick="document.documentElement.classList.toggle('dark')">🌓 다크</button>
<div class="wrap">
<h1>이슈 체크 — 판정을 걷어낸 3안</h1>
<p class="intro">9/7(월) 발행본에 실제로 나갔던 카드 4장을 그대로 쓴다. 수치는 스냅샷의 실측이고 손으로 넣은 숫자가 없다.<br>
공통 변경 — <b>적중/빗나감 배지 제거</b>, <b>취소선 제거</b>, 색은 판정이 아니라 <b>실제 등락 방향</b>을 뜻한다.
섹션 제목도 “이렇게 끝났어요”(결과) → “짚은 이슈”(체크)로 바꿨다.</p>
{BODY}
</div></body></html>'''

VARIANTS = [
 ("A", "A안 · 수치만", "해석을 전부 뺀다. 이슈 제목 아래 관련 종목의 실제 등락만 놓는다. 가장 담백하고 오해할 여지가 없지만, 왜 그 종목들인지는 제목으로만 짐작해야 한다."),
 ("B", "B안 · 중립 한 줄 + 수치 (추천)", "종목들이 <b>실제로</b> 어떻게 움직였는지만 한 줄로 요약한다(나란히 올랐어요·엇갈렸어요). 어제 예상과 맞았는지는 말하지 않는다 — 읽는 사람이 직접 본다."),
 ("C", "C안 · 어제 관점을 맥락으로만", "어제 브리핑이 그 이슈를 상방/하방 요인으로 봤다는 <b>사실</b>만 남기고 채점은 하지 않는다. 연결은 가장 뚜렷하지만 방향 표시가 다시 판정처럼 읽힐 위험이 있다."),
]
body = []
for key, tag, note in VARIANTS:
    body.append(f'''<div class="variant"><span class="tag">{tag}</span>
<div class="note">{note}</div>
<div class="panel">
  <div class="open-section__title"><span class="us-badge">🇺🇸 US</span> 지난 금요일 미국 브리핑이 짚은 이슈</div>
  <div class="issue-list">
{render(key)}
  </div>
  <div class="sec-foot">ET 2026-09-04 정규장 종가 기준 실측이에요. · <a href="#">지난 금요일 미국 브리핑 보기 →</a></div>
</div></div>''')

out = pathlib.Path("docs/prototypes/2026-09-08-us-issue-check.html")
out.write_text(TPL.replace("{BODY}", "\n".join(body)), encoding="utf-8")
print("생성:", out)
