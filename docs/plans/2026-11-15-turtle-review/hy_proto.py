# 미국 브리핑 '돌파 관찰 목록'(쿨라매기 고르기 + 터틀 손절·청산) 시안 HTML — S&P 500 11/5·11/13 종가 실측
import json, sys
A, Q = json.load(open("hy_2026-11-05.json")), json.load(open("hy_2026-11-13.json"))
KO = {"EL": "에스티로더", "ACN": "액센츄어", "CCI": "크라운캐슬", "EFX": "에퀴팩스", "FDS": "팩트셋", "CDW": "CDW", "SWKS": "스카이웍스",
      "GEN": "젠디지털", "IT": "가트너", "MTD": "메틀러토레도", "PSX": "필립스66", "MPC": "마라톤페트롤리엄", "IQV": "아이큐비아", "HAS": "해즈브로"}
ko = lambda r: KO.get(r["t"], r["name"])
usd = lambda v: f"${v:,.2f}"
md = lambda s: f"{int(s[5:7])}/{int(s[8:10])}"
sg = lambda v, d=1: ("+" if v > 0 else "−" if v < 0 else "") + f"{abs(v):.{d}f}"

def why(r):
    w = r["why"]
    return (f'<div class="why"><span>{w["best"]} {sg(w["ret"], 0)}% · 상위 {w["top"]:g}%</span>'
            f'<span>최근 10일 폭 {w["w10"]}% (앞 20일 {w["w20"]}%)</span><span>10·20일선 위</span></div>')

def ladder(pts, dots):
    lo, hi = min(v for v, _ in pts), max(v for v, _ in pts)
    X = lambda v: (v - lo) / (hi - lo) * 100 if hi > lo else 50
    return '<div class="lad">' + "".join(f'<i class="{c}" style="left:{X(v):.1f}%"></i>' for v, c in pts) + '</div>'

def card_today(r):
    pts = [(r["lo20"], "p-lo"), (r["stop"], "p-st"), (r["entry"], "p-en"), (r["close"], "p-now")]
    return (f'<div class="ld"><div class="ldh"><b>{ko(r)}</b><small>{r["t"]}</small><span>하루 움직임 {r["npct"]}% · 종가 {usd(r["close"])} ({sg(r["chg"], 2)}%)</span></div>'
            + why(r) + ladder(pts, None) +
            f'<div class="leg"><span><i class="p-lo"></i>청산선 {usd(r["lo20"])} <em>20일 최저가</em></span><span><i class="p-st"></i>손절선 {usd(r["stop"])} <em>{r["stop_pct"]}%</em></span>'
            f'<span><i class="p-en"></i>돌파 {usd(r["entry"])}</span><span><i class="p-now"></i>종가 {usd(r["close"])}</span></div></div>')

def card_wait(r):
    pts = [(r["stop"], "p-st"), (r["pivot"], "p-en o"), (r["close"], "p-now")]
    return (f'<div class="ld"><div class="ldh"><b>{ko(r)}</b><small>{r["t"]}</small><span>기준선까지 <b>{sg(r["to_pivot"])}%</b> · 하루 움직임 {r["npct"]}%</span></div>'
            + why(r) + ladder(pts, None) +
            f'<div class="leg"><span><i class="p-now"></i>종가 {usd(r["close"])}</span><span><i class="p-en o"></i>기준선 {usd(r["pivot"])} <em>10일 최고가</em></span>'
            f'<span><i class="p-st"></i>넘으면 손절선 {usd(r["stop"])} <em>{r["stop_pct"]}%</em></span></div></div>')

def track(rows):
    if not rows:
        return ""
    li = ""
    for x in rows:
        st = f'진행 중 · {x["days"]}거래일째' if x["state"] == "진행 중" else ("손절" if x["state"] == "손절" else "20일 최저가에 청산") + f' · {x["days"]}거래일'
        cls = "up" if x["R"] > 0.05 else "dn" if x["R"] < -0.05 else ""
        li += (f'<li><span class="nm"><b>{ko(x)}</b><small>{md(x["from"])} 돌파</small></span><span class="st{" live" if x["state"] == "진행 중" else ""}">{st}</span>'
               f'<span class="r {cls}">{sg(x["R"], 2)}R<small>{sg(x["pct"])}%</small></span></li>')
    done = [x for x in rows if x["state"] != "진행 중"]
    sm = f'끝난 {len(done)}번 평균 {sg(sum(x["R"] for x in done) / len(done), 2)}R · ' if done else ""
    return (f'<div class="gh">넘은 뒤 어떻게 됐나 <small>{sm}진행 중 {len(rows) - len(done)}개</small></div><ul class="trk">{li}</ul>'
            '<p class="note">R = 손익 ÷ 손절할 때 잃는 돈. −1R이면 손절선에서 끝난 것이에요. 진행 중은 오늘 종가 기준이에요.</p>')

FOOT = ('<div class="foot"><details class="fine"><summary>근거와 면책 고지</summary><p>종목은 쿨라매기 조건으로 골라요 — 1·3·6달 상승률 중 하나가 S&amp;P 500 상위 2%, '
        '6달 저점에서 30% 넘게 오름, 종가가 10일선·20일선 위, 최근 10일 폭이 앞 20일 폭의 60%보다 좁고 저점이 높아짐, 하루 평균 움직임 3% 이상. '
        '기준선(10일 최고가)을 넘으면 돌파로 보고, 손절선은 돌파 가격에서 하루 움직임의 두 배(2N) 아래, 청산선은 20일 최저가예요(터틀 규칙). '
        '2016년부터 S&amp;P 500에 이 규칙대로 사고팔았다면 한 번 평균 +0.51R이었지만, 2025년 한 해를 빼면 +0.22R로 아무 날에나 산 경우(+0.16R)와 거의 같았어요. '
        '이긴 비율은 31%이고 대부분 손절로 끝났어요. 지금 S&amp;P 500에 남은 종목으로 시험해 실제보다 좋게 나왔을 수 있어요. 매수 권유가 아니에요.</p></details></div>')

def sec(S, body):
    nt, nw = len(S["today"]), len(S["wait"])
    lead = (f'<b>{nt}종목</b>이 기준선을 넘었고, ' if nt else '기준선을 새로 넘은 종목은 없고, ') + (f'<b>{nw}종목</b>이 조건을 채우고 기준선을 기다리고 있어요.' if nw else '조건을 채운 종목도 없어요.')
    return (f'<div class="sec"><div class="sh"><span class="st">돌파 관찰 목록</span><span class="sd">S&amp;P 500 · {md(S["asof"])} 종가</span></div>'
            f'<div class="lead">{lead}</div>{body}{FOOT}</div>')

def body(S):
    b = ""
    if S["today"]:
        b += '<div class="gh">기준선을 넘은 종목</div>' + "".join(card_today(r) for r in S["today"])
    if S["wait"]:
        b += '<div class="gh">기준선을 기다리는 종목 <small>넘으면 위 칸으로 올라가요</small></div>' + "".join(card_wait(r) for r in S["wait"])
    return b + track(S["track"])

css = open("tt_proto.css").read() + open("hy_proto.css").read() if False else open("hy_proto.css").read()
html = f'''<!-- 미국 브리핑 '돌파 관찰 목록'(쿨라매기 고르기 + 터틀 손절·청산) 시안 — S&P 500 일봉 11/5·11/13 종가 실측 -->
<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>돌파 관찰 목록 시안</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css">
<style>{css}</style></head><body>
<div class="top"><h1>미국 브리핑 · 돌파 관찰 목록 시안</h1><p>종목은 쿨라매기 조건으로 고르고, 손절·청산선은 터틀 규칙으로 정해요. 숫자는 S&amp;P 500 11/5(목) 종가 실측이에요. 위치는 '오늘 점검할 이슈' 아래, 텔레그램에는 넣지 않아요.</p></div>
<div class="v"><h3>11/5 · 돌파 1종목 + 대기 4종목</h3><div class="pair"><div class="fw pc"><small>PC 720px</small>{sec(A, body(A))}</div><div class="fw ph"><small>모바일 343px</small>{sec(A, body(A))}</div></div></div>
<div class="v"><h3>11/13 · 돌파 없는 날</h3><p>11/5에 넘은 에스티로더는 다음 날 손절선에 닿아 끝났어요 — 그 결과도 그대로 보여요.</p><div class="pair"><div class="fw pc"><small>PC 720px</small>{sec(Q, body(Q))}</div></div></div>
</body></html>'''
open(sys.argv[1], "w").write(html)
print("ok")
