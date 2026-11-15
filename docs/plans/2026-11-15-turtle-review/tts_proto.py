# 미국 브리핑 '터틀 신고가 종목' 시안 HTML — S&P 500 실측(tts_2026-11-09.json·tts_2026-11-13.json), 시가총액 큰 순
import json, sys
A9, A13 = json.load(open("tts_2026-11-09.json")), json.load(open("tts_2026-11-13.json"))
KO = {"ABNB": "에어비앤비", "TDG": "트랜스다임", "PEG": "PSEG(전력)", "UAL": "유나이티드항공", "DTE": "DTE에너지", "BEN": "프랭클린리소시스",
      "ALGN": "얼라인테크놀로지", "COP": "코노코필립스", "LYB": "라이온델바젤", "WSM": "윌리엄스소노마", "AAPL": "애플", "JNJ": "존슨앤드존슨",
      "COST": "코스트코", "KO": "코카콜라", "PG": "P&G", "PEP": "펩시코", "APP": "앱러빈", "RSG": "리퍼블릭서비시스", "EW": "에드워즈",
      "BDX": "벡턴디킨슨", "XEL": "엑셀에너지", "STE": "스테리스", "NI": "나이소스", "CLX": "클로락스", "AMZN": "아마존", "TMO": "써모피셔", "MCD": "맥도날드", "MRNA": "모더나", "RCL": "로열캐리비안", "SPG": "사이먼프로퍼티", "LLY": "일라이릴리", "WMT": "월마트"}
ko = lambda r: KO.get(r["t"], r["name"])
md = lambda s: f'{int(s[5:7])}/{int(s[8:10])}'
usd = lambda v: f'${v:,.2f}'
SHOW = 6
def head(S): return f'<div class="sh"><span class="st">터틀 신고가 종목</span><span class="sd">S&amp;P 500 · {md(S["asof"])} 종가 · 시가총액 큰 순</span></div>'
def lead(S):
    n, c, e = len(S["new"]), len(S["cont"]), len(S["ended"])
    a = f'<b>{n}종목</b>이 55일 최고가를 새로 넘었어요' if n else '55일 최고가를 <b>새로</b> 넘은 종목은 없어요'
    return f'<div class="lead">{a}. 이미 추세 중이던 {c}종목은 최고가를 이어갔고, {e}종목은 20일 최저가를 깨 추세가 끝났어요.</div>'
def table(S):
    rows = "".join(
        f'<tr><td class="nmc"><b>{ko(r)}</b><small>{r["t"]} · {r["quiet"]}거래일 만의 신고가</small></td>'
        f'<td class="num">{usd(r["entry"])}</td><td class="num">{r["npct"]}%</td>'
        f'<td class="num dn">{usd(r["stop"])}<small>{r["stop_pct"]}%</small></td>'
        f'<td class="num">{usd(r["lo20"])}<small>{r["lo20_pct"]}%</small></td>'
        f'<td class="num">{r["unit"]}%</td></tr>' for r in S["new"][:SHOW])
    more = f'<div class="more-l">외 {len(S["new"]) - SHOW}종목 · {", ".join(ko(r) for r in S["new"][SHOW:])}</div>' if len(S["new"]) > SHOW else ""
    return (f'<div class="gh">새로 넘은 종목</div><table class="tt"><thead><tr><th>종목</th><th>돌파 가격<small>55일 최고가</small></th><th>하루 움직임<small>N</small></th>'
            f'<th>손절선<small>돌파 − 2N</small></th><th>청산선<small>20일 최저가</small></th><th>한 단위<small>계좌의</small></th></tr></thead><tbody>{rows}</tbody></table>{more}'
            '<p class="note">한 단위 = 하루 움직임(N)만큼 움직일 때 계좌가 1%만 흔들리는 크기예요. 30%면 계좌의 30%어치예요.</p>')
def cards(S):  # 모바일 — 표 대신 카드
    out = ""
    for r in S["new"][:SHOW]:
        out += (f'<div class="cd"><div class="cdh"><b>{ko(r)}</b><small>{r["t"]}</small><span>{r["quiet"]}거래일 만의 신고가</span></div>'
                f'<div class="cdg"><span>돌파 <b>{usd(r["entry"])}</b></span><span>하루 움직임 <b>{r["npct"]}%</b></span>'
                f'<span>손절선 <b class="dn">{usd(r["stop"])}</b> ({r["stop_pct"]}%)</span><span>청산선 <b>{usd(r["lo20"])}</b> ({r["lo20_pct"]}%)</span>'
                f'<span>한 단위 <b>계좌의 {r["unit"]}%</b></span></div></div>')
    more = f'<div class="more-l">외 {len(S["new"]) - SHOW}종목 · {", ".join(ko(r) for r in S["new"][SHOW:])}</div>' if len(S["new"]) > SHOW else ""
    return '<div class="gh">새로 넘은 종목</div>' + out + more
def ladder(S):  # B안 — 가격 사다리
    out = ""
    for r in S["new"][:SHOW]:
        pts = [(r["lo20"], "p-lo"), (r["stop"], "p-st"), (r["entry"], "p-en")] + [(a, "p-ad") for a in r["adds"]]
        lo, hi = min(p[0] for p in pts), max(p[0] for p in pts); X = lambda v: (v - lo) / (hi - lo) * 100
        dots = "".join(f'<i class="{c}" style="left:{X(v):.1f}%"></i>' for v, c in pts)
        leg = (f'<div class="leg"><span><i class="p-lo"></i>청산 {usd(r["lo20"])}</span><span><i class="p-st"></i>손절 {usd(r["stop"])}</span>'
               f'<span><i class="p-en"></i>돌파 {usd(r["entry"])}</span><span><i class="p-ad"></i>더 사는 자리 {" · ".join(usd(a) for a in r["adds"])}</span></div>')
        out += (f'<div class="ld"><div class="ldh"><b>{ko(r)}</b><small>{r["t"]}</small><span>하루 움직임 {r["npct"]}% · 한 단위 계좌의 {r["unit"]}%</span></div>'
                f'<div class="lad"><u style="left:{X(r["stop"]):.1f}%;right:{100 - X(r["adds"][2]):.1f}%"></u>{dots}</div>{leg}</div>')
    return ('<div class="gh">새로 넘은 종목 <small>돌파 뒤 ½N 오를 때마다 한 단위씩 더 사요(최대 4단위)</small></div>' + out)
def ends(S):
    if not S["ended"]: return ""
    li = "".join(f'<li><b>{ko(r)}</b> {r["days"]}거래일 만에 끝 · 추세 시작 뒤 <span class="{"up" if r["since"] >= 0 else "dn"}">{r["since"]:+.1f}%</span></li>' for r in S["ended"])
    return f'<div class="gh">추세 끝 <small>20일 최저가를 깼어요</small></div><ul class="ends">{li}</ul>'
def conts(S):
    if not S["cont"]: return ""
    nm = ", ".join(ko(r) for r in S["cont"][:8]); rest = len(S["cont"]) - 8
    return f'<div class="gh">추세 이어감 <small>이미 추세 중에 최고가를 다시 넘었어요</small></div><p class="cont">{nm}{f" 외 {rest}종목" if rest > 0 else ""}</p>'
FOOT = ('<div class="foot"><details class="fine"><summary>근거와 면책 고지</summary><p>리처드 데니스가 터틀에게 가르친 55일 규칙이에요. '
        '① 55일 최고가를 넘으면 산다 ② 하루 움직임(N)으로 크기를 정한다 ③ 돌파 가격 − 2N에서 자르고 ½N 오를 때마다 한 단위 더(최대 4단위) '
        '④ 20일 최저가를 깨면 전부 판다. 2016년부터 S&amp;P 500 종목에 이 규칙대로 사고팔았다면 한 번 평균 +0.42R(한 번 손절할 때 잃는 돈의 0.42배)이었고, '
        '아무 날에나 사서 같은 규칙으로 팔았다면 +0.58R이었어요. 개별 종목에선 신고가 돌파가 더 나은 출발점이 아니었다는 뜻이에요. '
        '이긴 비율은 21%로, 몇 번의 큰 추세가 나머지 손실을 메운 구조예요. 지금 S&amp;P 500에 남은 종목으로 시험해 결과가 실제보다 좋게 나왔을 수 있어요.</p></details></div>')
def sec(S, body): return f'<div class="sec">{head(S)}{lead(S)}{body}{FOOT}</div>'
A_pc, A_ph = sec(A9, table(A9) + ends(A9) + conts(A9)), sec(A9, cards(A9) + ends(A9) + conts(A9))
B_any = sec(A9, ladder(A9) + ends(A9) + conts(A9))
E = sec(A13, ends(A13) + conts(A13))
tg = (f'🐢 터틀 신고가 · {md(A9["asof"])}\n' + ", ".join(ko(r) for r in A9["new"][:3]) + f' 외 {len(A9["new"]) - 3}종목이 55일 최고가를 새로 넘었어요.\n'
      + "추세 끝 · " + ", ".join(ko(r) for r in A9["ended"]))
css = open("tt_proto.css").read() + open("tts_proto.css").read()
html = f'''<!-- 미국 브리핑 '터틀 신고가 종목' 섹션 시안 — S&P 500 일봉 실측(11/9·11/13 종가), 시가총액 큰 순 -->
<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>터틀 신고가 종목 시안</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css">
<style>{css}</style></head><body>
<div class="top"><h1>미국 브리핑 · 터틀 신고가 종목 시안</h1><p>문서의 규칙 네 가지를 S&amp;P 500 종목에 그대로 적용했어요. 숫자는 11/9(월) 종가 실측이에요(새로 넘은 종목 7개). 하루 움직임 1% 미만 종목(인수합병으로 가격이 묶인 종목 등)은 뺐어요. 위치는 '오늘 점검할 이슈' 아래를 생각했어요.</p></div>
<div class="v"><h3>A안 · 표<span class="rec">숫자 한눈에</span></h3><p>새로 넘은 종목을 시가총액 큰 순으로 6개까지, 돌파 가격·하루 움직임·손절선·청산선·한 단위 크기를 나란히 보여줘요. 모바일은 카드로 바뀌어요.</p>
<div class="pair"><div class="fw pc"><small>PC 720px</small>{A_pc}</div><div class="fw ph"><small>모바일 343px</small>{A_ph}</div></div></div>
<div class="v"><h3>B안 · 가격 사다리<span class="rec">규칙이 보이게</span></h3><p>종목마다 청산선·손절선·돌파 가격·추가 매수 자리(½N마다)를 한 줄 위에 찍어요. 규칙 ③·④가 그림으로 보여요.</p>
<div class="pair"><div class="fw pc"><small>PC 720px</small>{B_any}</div><div class="fw ph"><small>모바일 343px</small>{B_any}</div></div></div>
<div class="v"><h3>새로 넘은 종목이 없는 날(11/13 실측)</h3><p>1년 중 26일 정도는 새로 넘은 종목이 없어요. 그날은 이렇게 짧아져요.</p>
<div class="pair"><div class="fw pc"><small>PC 720px</small>{E}</div></div></div>
<div class="v"><h3>텔레그램(새로 넘은 종목이 있는 날만)</h3><pre class="tg">{tg}</pre></div>
</body></html>'''
open(sys.argv[1], "w").write(html)
