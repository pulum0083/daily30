# 미국 브리핑 '시장 추세판' 시안 HTML을 tt_state.json(11/13 종가 실측)으로 만든다
import json, sys
S = json.load(open("tt_state.json")); R = S["rows"]
on = [r for r in R if r["on"]]
off = sorted([r for r in R if not r["on"]], key=lambda r: r["to_brk"] / r["n_pct"])
recent = sorted([r for r in R if r["ev_age"] is not None and r["ev_age"] <= 4], key=lambda r: r["ev_age"])
def nx(r): return r["to_brk"] / r["n_pct"]   # 돌파선까지 하루 평균 움직임 몇 번
def row_on(r):
    w = min(r["to_exit"] / 10 * 100, 100)
    return (f'<div class="tr"><div class="nm"><b>{r["k"]}</b><small>{r["t"]}</small></div>'
            f'<div class="mid"><span class="pill on">상승 추세 {r["days"]}일째</span><span class="sub">시작 뒤 {r["gain"]:+.1f}%</span></div>'
            f'<div class="dist"><div class="bar ex"><i style="width:{w:.0f}%"></i></div><span>청산선까지 −{r["to_exit"]:.1f}%</span></div></div>')
def row_off(r):
    w = max(100 - min(nx(r) / 12 * 100, 100), 3)
    ago = f'{r["last_d"]}에 추세 끝' if r["last_ev"] == "out" else ""
    return (f'<div class="tr"><div class="nm"><b>{r["k"]}</b><small>{r["t"]}</small></div>'
            f'<div class="mid"><span class="sub">{ago}</span></div>'
            f'<div class="dist"><div class="bar"><i style="width:{w:.0f}%"></i></div><span>돌파선까지 +{r["to_brk"]:.1f}% <em>· 보통 하루 움직임의 {nx(r):.1f}배</em></span></div></div>')
def ev_line(r):
    if r["last_ev"] == "in":
        return f'<li><span class="pill on">시작</span><b>{r["k"]}</b> {r["last_d"]}에 55일 최고가를 넘어 상승 추세가 시작됐어요.</li>'
    return f'<li><span class="pill">끝</span><b>{r["k"]}</b> {r["last_d"]}에 20일 최저가를 깨 추세가 끝났어요.</li>'
foot = ('<details class="fine"><summary>근거와 면책 고지</summary><p>터틀 규칙(리처드 데니스)의 55일 시스템이에요. '
        '55일 최고가를 넘으면 상승 추세, 그 뒤 20일 최저가를 깨면 끝이에요. 시장마다 미국 상장 ETF 일봉 종가로 계산해요. '
        '2000년부터 22개 시장 ETF에 같은 규칙으로 사고팔았다면 한 번 평균 +0.92R(한 번 손절할 때 잃는 돈의 0.92배)이었고, '
        '아무 날에나 사서 같은 규칙으로 팔았다면 +0.40R이었어요. 이긴 비율은 24%로, 몇 번의 큰 추세가 나머지 손실을 메운 구조예요. '
        '하락 추세에 판 경우(숏)는 손해였어요. 개별 종목에선 효과가 없었어요.</p></details>')
ON_NAMES = ", ".join(r["k"] for r in on)
summ = f'{len(R)}개 시장 중 <b>{len(on)}개</b>만 상승 추세예요' + (f' — {ON_NAMES}' if on else '')
A = (f'<div class="sec"><div class="sh"><span class="st">시장 추세판</span><span class="sd">터틀 55일 규칙 · {S["asof"][5:].replace("-","/")} 종가</span></div>'
     f'<div class="lead">{summ}.</div>'
     + (f'<div class="gh">상승 추세 중</div>' + "".join(row_on(r) for r in on) if on else '')
     + '<div class="gh">추세 없음 <small>돌파선(55일 최고가)에 가까운 순</small></div>' + "".join(row_off(r) for r in off)
     + f'<div class="foot">{foot}</div></div>')
ON_TXT = ", ".join("%s %d일째" % (r["k"], r["days"]) for r in on) or "없음"
B = (f'<div class="sec"><div class="sh"><span class="st">시장 추세판</span><span class="sd">터틀 55일 규칙 · {S["asof"][5:].replace("-","/")} 종가</span></div>'
     f'<ul class="ev">{"".join(ev_line(r) for r in recent)}</ul>'
     f'<div class="lead s">지금 상승 추세 · <b>{ON_TXT}</b></div>'
     f'<details class="all"><summary>{len(R)}개 시장 전체 보기</summary>'
     + (f'<div class="gh">상승 추세 중</div>' + "".join(row_on(r) for r in on) if on else '')
     + '<div class="gh">추세 없음 <small>돌파선에 가까운 순</small></div>' + "".join(row_off(r) for r in off)
     + f'</details><div class="foot">{foot}</div></div>')
tg = ('📈 시장 추세판\n'
      + "\n".join((f'{r["k"]} 상승 추세 시작({r["last_d"]})' if r["last_ev"] == "in" else f'{r["k"]} 추세 끝({r["last_d"]})') for r in recent)
      + '\n지금 상승 추세 · ' + (ON_NAMES or "없음"))
css = open("tt_proto.css").read()
html = f'''<!-- 미국 브리핑 '시장 추세판'(터틀 55일 규칙) 섹션 시안 — 미국 상장 ETF 14개 일봉 {S["asof"]} 종가 실측 -->
<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>시장 추세판 시안</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css">
<style>{css}</style></head><body>
<div class="top"><h1>미국 브리핑 · 시장 추세판 시안</h1><p>터틀 55일 규칙으로 시장 14개의 추세 상태를 보여줘요. 숫자는 {S["asof"]}(금) 종가 실측이에요. 위치는 '오늘 점검할 이슈' 아래(나스닥 체크 다음)를 생각했어요.</p></div>
<div class="v"><h3>A안 · 매일 전체 판<span class="rec">한눈에</span></h3><p>상승 추세 중인 시장을 먼저, 나머지는 돌파선에 가까운 순서로 늘어놓아요. 막대가 길수록 돌파선에 가까워요. 시장마다 흔들리는 폭이 달라서, 보통 하루 움직임의 몇 배 남았는지로 순서를 매겨요.</p>
<div class="pair"><div class="fw pc"><small>PC 720px</small>{A}</div><div class="fw ph"><small>모바일 343px</small>{A}</div></div></div>
<div class="v"><h3>B안 · 바뀐 시장 먼저, 전체는 접기<span class="rec">짧게</span></h3><p>최근 며칠 사이 추세가 시작되거나 끝난 시장만 문장으로 보여주고, 14개 전체는 눌러서 펼쳐요. 바뀐 시장이 없는 날엔 '지금 상승 추세' 한 줄과 전체 보기만 남아요.</p>
<div class="pair"><div class="fw pc"><small>PC 720px</small>{B}</div><div class="fw ph"><small>모바일 343px</small>{B}</div></div></div>
<div class="v"><h3>텔레그램(B안과 함께, 바뀐 날만)</h3><pre class="tg">{tg}</pre></div>
</body></html>'''
open(sys.argv[1], "w").write(html)
