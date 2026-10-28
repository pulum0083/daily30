// '어제랑 비교해서' 장중 대결판 — /api/intraday?vs=intraday 응답을 #vs-root에 그린다(설계 §4.2, 시안 v4)
(function () {
  var root = document.getElementById('vs-root');

  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function f2(n) { return n == null ? '—' : (n > 0 ? '+' : n < 0 ? '−' : '') + Math.abs(n).toFixed(2); }
  function cls(n) { return n > 0 ? 'up' : n < 0 ? 'dn' : ''; }
  function fmt(n) { return Number(n).toLocaleString('en-US'); }
  function eok(e) { var a = Math.abs(e), s = e > 0 ? '+' : e < 0 ? '−' : ''; return a >= 10000 ? s + (a / 10000).toFixed(2) + '조' : s + fmt(a) + '억'; }

  // 두 곡선을 한 세로 눈금에 담는다 — 0%선이 항상 보이게 0을 포함하고 위아래 25% 여백.
  // 12%일 땐 0% 근처에서 움직이는 선이 카드 위 끝에 붙어 보였다(2026-09-15 사용자 지적).
  function scale(yPts, tPts) {
    var all = [0];
    (yPts || []).concat(tPts || []).forEach(function (p) { all.push(p[1]); });
    var lo = Math.min.apply(null, all), hi = Math.max.apply(null, all), pad = (hi - lo) * 0.25 || 0.4;
    return { lo: lo - pad, hi: hi + pad };
  }

  function hhmm(m) { var t = 540 + Math.round(m); return String(Math.floor(t / 60)).padStart(2, '0') + ':' + String(t % 60).padStart(2, '0'); }

  // 마우스 위치(가로 0~1)에서 가장 가까운 샘플 점 — 곡선에 실제로 있는 점만 보여준다(보간하지 않는다, §0)
  function hoverAt(yPts, tPts, frac) {
    var want = Math.max(0, Math.min(1, frac)) * 390, best = null;
    (tPts || []).concat(yPts || []).forEach(function (p) { if (best == null || Math.abs(p[0] - want) < Math.abs(best - want)) best = p[0]; });
    if (best == null) return null;
    function at(pts) { var hit = (pts || []).filter(function (p) { return p[0] === best; })[0]; return hit ? hit[1] : null; }
    var t = at(tPts), y = at(yPts);
    return { m: best, time: hhmm(best), t: t, y: y, diff: t != null && y != null ? Math.round((t - y) * 100) / 100 : null };
  }

  // 세로 눈금 — 범위가 3%p를 넘으면 1%p, 아니면 0.5%p 간격
  function ticks(lo, hi) {
    var step = hi - lo > 3 ? 1 : 0.5, out = [];
    for (var v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(Math.round(v * 100) / 100);
    return out;
  }
  function tickText(v) { return v === 0 ? '0%' : (v > 0 ? '+' : '−') + Math.abs(v); }
  function last(pts) { return pts && pts.length ? pts[pts.length - 1] : null; }

  // 픽셀 좌표 점들을 잇는 매끄러운 곡선 조각(Catmull-Rom → 베지어, 'M' 없음). 값은 실제 샘플 점에서만 찍힌다.
  function smoothTail(p) {
    var d = '';
    for (var i = 0; i < p.length - 1; i++) {
      var p0 = p[i - 1] || p[i], p1 = p[i], p2 = p[i + 1], p3 = p[i + 2] || p2;
      d += 'C' + (p1[0] + (p2[0] - p0[0]) / 6).toFixed(1) + ' ' + (p1[1] + (p2[1] - p0[1]) / 6).toFixed(1) + ' ' +
        (p2[0] - (p3[0] - p1[0]) / 6).toFixed(1) + ' ' + (p2[1] - (p3[1] - p1[1]) / 6).toFixed(1) + ' ' + p2[0].toFixed(1) + ' ' + p2[1].toFixed(1);
    }
    return d;
  }
  function smoothPath(pts, x, y) {
    if (!pts.length) return '';
    var p = pts.map(function (q) { return [+x(q[0]), +y(q[1])]; });
    return 'M' + p[0][0].toFixed(1) + ' ' + p[0][1].toFixed(1) + smoothTail(p);
  }

  // 오늘−어제 부호가 같은 구간 [[분, 오늘, 어제]…]. 같은 분에 어제 값이 없으면 구간을 끊는다(없는 값을 이어 칠하지 않는다, §0).
  // 부호가 바뀌는 두 점 사이는 직선 교차점을 경계로 넣는다 — 그림 경계일 뿐 값으로 쓰지 않는다.
  function bandRuns(yPts, tPts) {
    var ys = {}, out = [], cur = null, prev = null;
    (yPts || []).forEach(function (p) { ys[p[0]] = p[1]; });
    function push(pt, sg) { if (!cur || cur.sg !== sg) { cur = { sg: sg, pts: [] }; out.push(cur); } cur.pts.push(pt); }
    (tPts || []).forEach(function (p) {
      if (ys[p[0]] == null) { cur = prev = null; return; }
      var pt = [p[0], p[1], ys[p[0]]], d = pt[1] - pt[2];
      if (prev) {
        var dp = prev[1] - prev[2];
        if (d * dp < 0) {
          var f = dp / (dp - d), m = prev[0] + (pt[0] - prev[0]) * f, v = prev[1] + (pt[1] - prev[1]) * f, c = [m, v, v];
          cur.pts.push(c); push(c, d > 0 ? 1 : -1);
        }
      }
      push(pt, d > 0 ? 1 : d < 0 ? -1 : (cur ? cur.sg : 1));
      prev = pt;
    });
    return out.filter(function (r) { return r.pts.length > 1; });
  }

  // 곡선 SVG(가로로 늘려 그린다 — 글자는 넣지 않는다). 시안 B(2026-10-28): 오늘 곡선과 0%선 사이를 칠한다 —
  // 0% 위(전일 종가보다 높음)면 빨강, 아래면 파랑. 면 색은 오늘의 오르내림만 뜻하고, 어제와의 차이는 위 세 칸과
  // 아래 회색 막대(diffSvg)가 맡는다. 옛 H안은 두 곡선 사이를 칠해, 내내 오른 날도 어제보다 덜 오른 구간이
  // 파랗게 보여 '내렸다'로 읽혔다(2026-10-28 사용자 지적).
  function chartSvg(yPts, tPts) {
    var W = 600, H = 180, s = scale(yPts, tPts), lo = s.lo, hi = s.hi;
    function x(m) { return (m / 390 * W).toFixed(1); }
    function y(v) { return ((hi - v) / (hi - lo) * H).toFixed(1); }
    var out = '', lt = last(tPts);
    ticks(lo, hi).forEach(function (v) { if (v !== 0) out += '<line x1="0" x2="' + W + '" y1="' + y(v) + '" y2="' + y(v) + '" class="vs-grid" vector-effect="non-scaling-stroke"/>'; });
    if (lt && lt[0] < 390) {
      out += '<rect x="' + x(lt[0]) + '" y="0" width="' + (W - x(lt[0])).toFixed(1) + '" height="' + H + '" class="vs-rest"/>' +
        '<line x1="' + x(lt[0]) + '" x2="' + x(lt[0]) + '" y1="0" y2="' + H + '" class="vs-now" vector-effect="non-scaling-stroke"/>';
    }
    out += '<line x1="0" x2="' + W + '" y1="' + y(0) + '" y2="' + y(0) + '" class="vs-zero" vector-effect="non-scaling-stroke"/>';
    var zero = (tPts || []).map(function (p) { return [p[0], 0]; });
    bandRuns(zero, tPts).forEach(function (r) {
      var a = r.pts.map(function (q) { return [+x(q[0]), +y(q[1])]; }), b = r.pts.map(function (q) { return [+x(q[0]), +y(q[2])]; }).reverse();
      out += '<path d="M' + a[0][0].toFixed(1) + ' ' + a[0][1].toFixed(1) + smoothTail(a) + 'L' + b[0][0].toFixed(1) + ' ' + b[0][1].toFixed(1) + smoothTail(b) +
        'Z" class="vs-area ' + (r.sg > 0 ? 'up' : 'dn') + '"/>';
    });
    return '<svg class="vs-chart" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none" role="img" aria-label="코스피 곡선">' + out +
      '<path d="' + smoothPath(yPts || [], x, y) + '" class="vs-line-y" vector-effect="non-scaling-stroke"/>' +
      '<path d="' + smoothPath(tPts || [], x, y) + '" class="vs-line-t ' + (lt ? cls(lt[1]) : '') + '" vector-effect="non-scaling-stroke"/></svg>';
  }

  // 같은 분에 두 곡선 값이 모두 있는 점의 차이(오늘−어제). 한쪽만 있는 분은 뺀다(§0 — 채우지 않는다).
  function diffPts(yPts, tPts) {
    var ys = {};
    (yPts || []).forEach(function (p) { ys[p[0]] = p[1]; });
    return (tPts || []).filter(function (p) { return ys[p[0]] != null; })
      .map(function (p) { return [p[0], Math.round((p[1] - ys[p[0]]) * 100) / 100]; });
  }

  // 곡선 아래 차이 막대 칸 — 샘플 분마다 0축 세로 막대. 회색만 쓴다(선 위 진하게 = 오늘이 높음, 아래 옅게 = 낮음) —
  // 빨강·파랑은 오르내림을 뜻하므로 '어제보다 낮다'가 '내렸다'로 읽히지 않게 한다(2026-10-28). 없으면 칸째 생략.
  function diffSvg(yPts, tPts) {
    var d = diffPts(yPts, tPts);
    if (!d.length) return '';
    var W = 600, H = 56, mid = H / 2, mx = 0.2, gap = 5, lt = last(tPts), out = '';
    d.forEach(function (p, i) { mx = Math.max(mx, Math.abs(p[1])); if (i) gap = Math.min(gap, p[0] - d[i - 1][0]) || gap; });
    var bw = gap / 390 * W * 0.62;
    if (lt && lt[0] < 390) out += '<rect x="' + (lt[0] / 390 * W).toFixed(1) + '" y="0" width="' + (W - lt[0] / 390 * W).toFixed(1) + '" height="' + H + '" class="vs-rest"/>';
    out += '<line x1="0" x2="' + W + '" y1="' + mid + '" y2="' + mid + '" class="vs-zero" vector-effect="non-scaling-stroke"/>';
    d.forEach(function (p) {
      if (!p[1]) return;
      var h = Math.max(Math.abs(p[1]) / mx * (mid - 2), 1);
      out += '<rect x="' + (p[0] / 390 * W - bw / 2).toFixed(1) + '" y="' + (p[1] > 0 ? mid - h : mid).toFixed(1) + '" width="' + bw.toFixed(1) +
        '" height="' + h.toFixed(1) + '" class="vs-dbar ' + (p[1] > 0 ? 'hi' : 'lo') + '"/>';
    });
    return '<svg class="vs-dchart" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none" role="img" aria-label="오늘과 어제의 차이 막대">' + out + '</svg>';
  }

  // 차이 막대 칸 — 위에 '어제와 차이' 설명, 오른쪽 끝에 지금 시각의 차이 %p(색 없이)
  function diffBox(yPts, tPts, relRaw) {
    var ds = diffSvg(yPts, tPts), lp = last(diffPts(yPts, tPts));
    if (!ds) return '';
    var rel = relRaw || '어제';
    return '<p class="vs-dcap"><b>' + esc(rel) + josa(rel, '과', '와') + ' 차이</b>선 위 = 오늘이 높음 · 아래 = 낮음</p>' +
      '<div class="vs-diffbox"><div class="vs-dplot">' + ds + '</div>' +
      '<span class="vs-end" style="top:50%"><b>' + f2(lp[1]) + '%p</b></span></div>';
  }

  // 결론 카드 맨 위 세 칸 — 오늘 · 어제 같은 시각 · 차이(코스피, 확정 분 기준). 오늘 값이 없으면 칸째 뺀다(§0).
  function kpiRow(d) {
    var k = d.kospi;
    if (!k || k.t == null) return '';
    var rel = esc(d.prev.rel);
    var dTxt = k.diff == null ? '' : k.diff > 0 ? '오늘이 더 높아요' : k.diff < 0 ? '오늘이 더 낮아요' : '같아요';
    return '<div class="vs-kpis">' +
      '<div class="vs-kpi"><span class="l">오늘</span><b class="' + cls(k.t) + '">' + f2(k.t) + '%</b><span class="s">' + esc(d.time) + ' 기준</span></div>' +
      '<div class="vs-kpi"><span class="l">' + rel + ' 같은 시각</span><b class="y">' + (k.y != null ? f2(k.y) + '%' : '—') + '</b><span class="s">' + esc(d.prev.label || '') + '</span></div>' +
      '<div class="vs-kpi"><span class="l">차이</span><b>' + (k.diff != null ? f2(k.diff) + '%p' : '—') + '</b><span class="s">' + dTxt + '</span></div></div>';
  }

  // 곡선 위에 겹치는 글자 — 왼쪽 여백 세로 눈금, 오른쪽 여백 선 끝 값, 곡선 안 '남은 장'.
  // 어제 끝 값은 색을 빼 회색으로 둔다 — 오늘이 주인공이다(시안 B). 차이 괄호는 위 세 칸과 아래 막대가 맡아 뺐다.
  // 늘려 그린 SVG 안에 글자를 넣으면 찌그러지므로 같은 비율(%)로 HTML을 얹는다.
  function chartOverlay(yPts, tPts, rel) {
    var s = scale(yPts, tPts), lo = s.lo, hi = s.hi, lt = last(tPts), ly = last(yPts);
    function top(v) { return (hi - v) / (hi - lo) * 100; }
    var left = ticks(lo, hi).map(function (v) { return '<span class="vs-ytick" style="top:' + top(v).toFixed(2) + '%">' + tickText(v) + '</span>'; }).join('');
    var right = '', plot = '';
    if (lt && ly && lt[0] === ly[0]) {
      var tt = top(lt[1]), yt = top(ly[1]), gap = Math.abs(tt - yt), MIN = 20;
      var ta = tt, ya = yt;                          // 끝 값 두 줄이 겹치면 가운데를 기준으로 서로 밀어낸다
      if (gap < MIN) { var mid = (tt + yt) / 2, sgn = tt <= yt ? -1 : 1; ta = mid + sgn * MIN / 2; ya = mid - sgn * MIN / 2; }
      ta = Math.max(8, Math.min(92, ta)); ya = Math.max(8, Math.min(92, ya));
      right = '<span class="vs-end" style="top:' + ta.toFixed(2) + '%"><b class="' + cls(lt[1]) + '">' + f2(lt[1]) + '%</b>오늘</span>' +
        '<span class="vs-end" style="top:' + ya.toFixed(2) + '%"><b class="y">' + f2(ly[1]) + '%</b>' + rel + '</span>';
      var xp = lt[0] / 390 * 100;
      plot += '<i class="vs-enddot y" style="left:' + xp.toFixed(2) + '%;top:' + yt.toFixed(2) + '%"></i><i class="vs-enddot t ' + cls(lt[1]) + '" style="left:' + xp.toFixed(2) + '%;top:' + tt.toFixed(2) + '%"></i>';
      if (lt[0] <= 330) plot += '<span class="vs-rest-l" style="left:' + xp.toFixed(2) + '%">남은 장</span>';
    }
    return { left: left, right: right, plot: plot };
  }

  // 강도 판정 한마디 — 서버 판정(거래량 ±10%, 진폭 ±0.3%p)을 두 개 묶어 읽는다. 둘 다 없으면 뱃지를 뺀다.
  var HEAT_WORDS = {
    'strong,strong': '어제보다 뜨거워요', 'weak,weak': '어제보다 조용해요', 'same,same': '어제와 비슷해요',
    'strong,same': '거래가 더 붐벼요', 'same,strong': '더 크게 출렁여요',
    'weak,same': '거래가 더 한산해요', 'same,weak': '출렁임이 작아요',
    'strong,weak': '거래는 늘고 출렁임은 작아요', 'weak,strong': '거래는 줄고 출렁임은 커요',
  };
  function heatWord(vj, aj) {
    if (vj && aj) return HEAT_WORDS[vj + ',' + aj] || '';
    var one = vj || aj, isVol = !!vj;
    if (!one) return '';
    return one === 'same' ? '어제와 비슷해요' : isVol ? (one === 'strong' ? '거래가 더 붐벼요' : '거래가 더 한산해요')
      : (one === 'strong' ? '더 크게 출렁여요' : '출렁임이 작아요');
  }

  // 강도 카드(강도 C, 2026-10-28) — 큰 숫자 두 개: 거래량은 어제 같은 시각 대비 %, 진폭은 어제의 몇 배.
  // 지수 1분봉엔 거래대금이 없어 거래량(천주)으로 비교한다. 값이 없는 칸은 '—'로 비운다(§0).
  function heatCard(axes) {
    if (!axes || !axes.heat) return '';
    var vol = axes.heat.vol, amp = axes.heat.amp;
    if (!vol || !amp) return '';
    if (vol.t == null && amp.t == null) return '';   // 오늘 값이 둘 다 없으면 카드째 생략한다(F5, §0)
    var vBig = vol.diff != null ? (vol.diff >= 0 ? '+' : '−') + Math.abs(Math.round(vol.diff)) + '%' : vol.t != null ? fmt(vol.t) + '<small>천주</small>' : '—';
    var vSub = vol.t != null ? fmt(vol.t) + '천주 · 어제 ' + (vol.y != null ? fmt(vol.y) : '—') : '오늘 값 없음';
    var ratio = amp.t != null && amp.y > 0 ? amp.t / amp.y : null;
    var aBig = ratio != null ? ratio.toFixed(1) + '배' : amp.t != null ? amp.t.toFixed(2) + '%' : '—';
    var aSub = amp.t != null ? amp.t.toFixed(2) + '% · 어제 ' + (amp.y != null ? amp.y.toFixed(2) + '%' : '—') : '오늘 값 없음';
    var word = heatWord(vol.judge, amp.judge);
    return '<div class="vs-card"><div class="vs-card-h vsx-hc"><p>얼마나 뜨거운가</p>' + (word ? '<span class="vsx-badge">' + word + '</span>' : '') + '</div>' +
      '<div class="vsx-two"><div><span class="l">거래량</span><b>' + vBig + '</b><span class="s">' + vSub + '</span></div>' +
      '<div><span class="l">하루 진폭</span><b>' + aBig + '</b><span class="s">' + aSub + '</span></div></div></div>';
  }

  // 주도권 카드(시장 기준선, 2026-10-28) — 섹터 대표 3종목 평균을 오늘 등락 순 막대로 그리고, 코스피·코스닥 오늘 등락을
  // 세로 점선으로 긋는다. 코스피 선을 넘은 섹터만 진한 빨강이다. 코스피는 axes가 아니라 응답 최상위 kospi에 있다 —
  // 없으면 그 선과 아래 한 줄만 뺀다(지어내지 않는다). 대표 종목 이름은 행에 마우스를 올리면 보인다.
  function leadCard(axes, kospi) {
    if (!axes || !axes.sectors || !axes.sectors.length) return '';
    var secs = axes.sectors.filter(function (s) { return typeof s.t === 'number'; }).slice().sort(function (a, b) { return b.t - a.t; });
    if (!secs.length) return '';
    var kp = kospi && typeof kospi.t === 'number' ? kospi.t : null;
    var kq = axes.market && axes.market.kosdaq && typeof axes.market.kosdaq.t === 'number' ? axes.market.kosdaq.t : null;
    var vals = secs.map(function (s) { return s.t; }).concat([0]);
    if (kp != null) vals.push(kp);
    if (kq != null) vals.push(kq);
    var lo = Math.min.apply(null, vals) - 0.5, hi = Math.max.apply(null, vals) + 0.5;
    function p(v) { return ((v - lo) / (hi - lo) * 100).toFixed(2); }
    var rows = secs.map(function (s, i) {
      var rank = s.rank != null ? s.rank : i + 1, a = Math.min(p(0), p(s.t)), w = Math.abs(p(s.t) - p(0));
      // 순위가 어제와 같으면 '–'를 단다(2026-10-28 사용자 요청). 어제 순위를 모르면(move null) 아무것도 달지 않는다.
      var mv = s.move > 0 ? '<small class="up">▲' + s.move + '</small>' : s.move < 0 ? '<small class="dn">▼' + (-s.move) + '</small>'
        : s.move === 0 ? '<small class="eq" aria-label="어제와 같은 순위">–</small>' : '';
      var n = s.n != null ? s.n : (s.names || []).length;
      var tone = s.t < 0 ? 'dn' : kp != null && s.t >= kp ? 'up' : 'up-l';
      return '<div class="vsx-lr" title="' + esc('대표 ' + n + '종목 · ' + (s.names || []).join(' · ')) + '">' +
        '<div class="nm"><span class="vsx-rk' + (rank === 1 ? ' top' : '') + '">' + rank + '</span>' + esc(s.label) + mv +
        (n && n < 3 ? '<small class="n">' + n + '종목</small>' : '') + '</div>' +
        '<div class="tk"><i class="' + tone + '" style="left:' + a + '%;width:' + w.toFixed(2) + '%"></i></div>' +
        '<div class="v ' + cls(s.t) + '">' + f2(s.t) + '%</div></div>';
    }).join('');
    var lines = '<i class="vsx-vl z" style="left:' + p(0) + '%"></i>';
    if (kq != null) lines += '<i class="vsx-vl q" style="left:' + p(kq) + '%"></i><span class="vsx-vlab q" style="left:' + p(kq) + '%">코스닥 ' + f2(kq) + '%</span>';
    if (kp != null) lines += '<i class="vsx-vl k" style="left:' + p(kp) + '%"></i><span class="vsx-vlab k" style="left:' + p(kp) + '%">코스피 ' + f2(kp) + '%</span>';
    var foot = '';
    if (kp != null) {
      // 센 쪽이 절반을 넘으면 짧은 쪽(약한 섹터)을 적는다 — 섹터 이름을 여덟 개 늘어놓지 않는다.
      var beat = secs.filter(function (s) { return s.t >= kp; }).map(function (s) { return s.label; });
      var weak = secs.filter(function (s) { return s.t < kp; }).map(function (s) { return s.label; });
      var list = beat.length > secs.length / 2 ? weak : beat, what = list === beat ? '센' : '약한';
      var tail = list.length ? list[list.length - 1] : '';
      foot = '<p class="vs-sub">' + (list.length === 0 ? (list === beat ? '코스피보다 센 섹터는 없어요.' : '모든 섹터가 코스피보다 세요.')
        : '코스피보다 ' + what + ' 섹터는 <b>' + esc(list.join('·')) + '</b>' + (list.length === 1 ? '뿐이에요.' : josa(tail, '이에요.', '예요.'))) + '</p>';
    }
    return '<div class="vs-card"><div class="vs-card-h"><p>어디가 이끄나</p></div>' +
      '<p class="vs-sub vsx-desc">섹터 대표 3종목 평균 · 숫자는 오늘 순위, 화살표는 어제 대비' + (kp != null ? ' · 점선을 넘은 섹터가 코스피보다 센 곳' : '') + '</p>' +
      '<div class="vsx-lead' + (kp != null || kq != null ? ' has-lab' : '') + '">' + rows + '<div class="vsx-lines">' + lines + '</div></div>' + foot + '</div>';
  }

  // 수급 카드(판 쪽 vs 산 쪽, 2026-10-28) — 가운데 선 왼쪽에 판 주체, 오른쪽에 산 주체를 쌓은 한 줄 막대를 오늘·어제 이 시각
  // 두 줄로 놓는다(같은 눈금). 판 만큼 누군가 샀으므로 두 쪽 길이가 거의 같다. 색은 매수 빨강·매도 파랑, 같은 쪽 안에서는
  // 가운데에 가까울수록 진하다. 기타법인은 최상위 flow에서만 오고, 없으면 막대에서 빠진다(§0).
  // 그 아래는 기관 안 순매수 구성(산 주체만 비율 막대) + 판 주체 한 줄.
  // slot이 close·night이면 카드 라벨을 "정규장 확정 15:40"으로 바꿔 애프터장이 섞인 홈 LIVE 바와 구분한다(F2).
  var ACTORS = ['개인', '외국인', '기관', '기타법인'];
  function flowCard(axes, slot, ctx) {
    if (!axes || !axes.flow) return '';
    ctx = ctx || {};
    var main = axes.flow.main || {}, etc = ctx.etc || {}, rel = ctx.rel || '어제';
    function val(k, side) { var v = k === '기타법인' ? etc[side] : main[k] && main[k][side]; return typeof v === 'number' ? v : null; }
    var rows = [['오늘', 't'], [rel + ' 이 시각', 'y']].filter(function (r) {
      return ['개인', '외국인', '기관'].some(function (k) { return val(k, r[1]) != null; });
    });
    if (!rows.length) return '';
    function sideSum(side, sg) { return ACTORS.reduce(function (a, k) { var v = val(k, side); return v != null && Math.sign(v) === sg ? a + Math.abs(v) : a; }, 0); }
    var span = Math.max.apply(null, rows.map(function (r) { return Math.max(sideSum(r[1], 1), sideSum(r[1], -1)); })) * 1.05 || 1;
    var bars = rows.map(function (r) {
      var side = r[1], L = 50, R = 50, segs = '', nb = 0, ns = 0;
      ACTORS.forEach(function (k) {
        var v = val(k, side);
        if (!v) return;
        var w = Math.abs(v) / span * 50;
        if (v < 0) { L -= w; segs += '<i class="dn s' + Math.min(ns++, 2) + '" style="left:' + L.toFixed(2) + '%;width:' + w.toFixed(2) + '%"></i>'; }
        else { segs += '<i class="up s' + Math.min(nb++, 2) + '" style="left:' + R.toFixed(2) + '%;width:' + w.toFixed(2) + '%"></i>'; R += w; }
      });
      function cap(sg) {
        var tot = sideSum(side, sg);
        return ACTORS.filter(function (k) { var v = val(k, side); return v != null && Math.sign(v) === sg && (k !== '기타법인' || Math.abs(v) >= tot * 0.1); })
          .map(function (k) { var v = val(k, side); return esc(k) + ' <b class="' + cls(v) + '">' + eok(v) + '</b>'; }).join(' · ');
      }
      return '<div class="vsx-bal"><div class="cap"><span>← 판 쪽</span><span class="m">' + esc(r[0]) + '</span><span>산 쪽 →</span></div>' +
        '<div class="bar">' + segs + '<i class="mid"></i></div>' +
        '<div class="who"><span>' + cap(-1) + '</span><span class="r">' + cap(1) + '</span></div></div>';
    }).join('');
    var both = ['개인', '외국인', '기관'].filter(function (k) { return val(k, 't') != null && val(k, 'y') != null; });
    var note = '';
    if (rows.length === 2 && both.length) {
      var same = both.every(function (k) { return Math.sign(val(k, 't')) === Math.sign(val(k, 'y')); });
      var sy = both.reduce(function (a, k) { return a + Math.abs(val(k, 'y')); }, 0);
      var r = sy ? both.reduce(function (a, k) { return a + Math.abs(val(k, 't')); }, 0) / sy : null;
      var len = r == null ? '' : r >= 1.05 ? '오늘 막대가 약 ' + r.toFixed(1) + '배 길어요.' : r <= 0.95 ? '오늘 막대가 ' + esc(rel) + '의 약 ' + r.toFixed(1) + '배로 짧아요.' : '길이는 비슷해요.';
      note = '<p class="vs-sub">' + (same ? '두 막대의 구도가 같고, ' : esc(rel) + josa(rel, '과', '와') + ' 사고판 쪽이 바뀌었고, ') + len + '</p>';
    }
    var inst = (axes.flow.inst || []).filter(function (f) { return typeof f.t === 'number'; });
    var pos = inst.filter(function (f) { return f.t > 0; }), neg = inst.filter(function (f) { return f.t < 0; });
    var tot = pos.reduce(function (a, f) { return a + f.t; }, 0), instHtml = '';
    if (pos.length) {
      instHtml += '<div class="vsx-stack">' + pos.map(function (f, i) {
        var sh = f.t / tot;
        return '<i class="g' + Math.min(i, 5) + '" style="width:' + (sh * 100).toFixed(2) + '%">' + (sh > 0.12 ? esc(f.key) + ' ' + Math.round(sh * 100) + '%' : '') + '</i>';
      }).join('') + '</div><div class="vsx-skey">' + pos.map(function (f, i) {
        return '<span><i class="g' + Math.min(i, 5) + '"></i>' + esc(f.key) + ' ' + eok(f.t) + (f.turned ? '(' + esc(rel) + josa(rel, '은', '는') + ' 팔았어요)' : '') + '</span>';
      }).join('') + '</div>';
    }
    if (neg.length) instHtml += '<p class="vs-sub">판 곳 · ' + neg.map(function (f) { return esc(f.key) + ' ' + eok(f.t) + (f.turned ? '(' + esc(rel) + josa(rel, '은', '는') + ' 샀어요)' : ''); }).join(', ') + '</p>';
    var subLabel = (slot === 'close' || slot === 'night') ? '<span>정규장 확정 15:40</span>' : '';
    return '<div class="vs-card"><div class="vs-card-h"><p>누가 사는가</p>' + subLabel + '</div>' +
      '<p class="vs-sub vsx-desc">코스피 전체 누적 순매수 · 왼쪽은 판 쪽, 오른쪽은 산 쪽이에요</p>' + bars + note +
      (instHtml ? '<p class="vs-lbl vsx-sec">기관 순매수 구성</p>' + instHtml : '') + '</div>';
  }

  // 결론 근거 4줄(가격·강도·주도권·누가) — 승인 시안(docs/prototypes/2026-09-16-vs-home-design.html heroCard) 그대로다.
  // 코스피 %만 오늘 절대값을 다시 적지 않는다(§0·F2, LIVE 바와 중복). 강도·주도권·누가는 코스피 %가 아니라 시안대로
  // 오늘 절대값도 함께 적는다. 입력이 없는 줄은 채우지 않고 통째로 뺀다. open은 "이 시각" 기준, close·night은 하루 전체.
  function heroWhy(d, slot) {
    var relRaw = d.prev.rel, rel = esc(relRaw), open = slot === 'open', lines = [];

    if (d.kospi && d.kospi.y != null && d.kospi.diff != null) {
      var kd = d.kospi.diff;
      lines.push(['가격', (open ? rel + ' 이 시각엔 ' : rel + josa(relRaw, '은', '는') + ' ') +
        '<b class="' + cls(d.kospi.y) + '">' + f2(d.kospi.y) + '%</b>였어요. 지금은 ' +
        '<b class="' + cls(kd) + '">' + f2(kd) + '%p</b> 더 ' + (kd >= 0 ? '높아요' : '낮아요')]);
    }

    var heat = d.axes && d.axes.heat;
    if (heat && heat.vol && heat.amp && heat.vol.diff != null && heat.vol.y != null &&
        heat.amp.t != null && heat.amp.y != null) {
      lines.push(['강도', '거래량이 <b class="' + cls(heat.vol.diff) + '">' + f2(heat.vol.diff) + '%</b>' +
        '(어제 ' + fmt(heat.vol.y) + '천주), 진폭은 <b>' + heat.amp.t.toFixed(2) + '%</b>(어제 ' + heat.amp.y.toFixed(2) + '%)']);
    }

    var sectors = d.axes && d.axes.sectors;
    if (sectors && sectors.length) {
      var leader = sectors.filter(function (s) { return s.rank === 1; })[0];
      var prevLeader = sectors.filter(function (s) { return s.prevRank === 1; })[0];
      var parts = [];
      if (leader && leader.prevRank != null) {
        parts.push('<b>' + esc(leader.label) + '</b>' + josa(leader.label, '이', '가') + ' 어제 ' + leader.prevRank + '위에서 <b class="up">1위</b>로');
      }
      if (prevLeader && (!leader || prevLeader.key !== leader.key)) {
        parts.push('<b>' + esc(prevLeader.label) + '</b>' + josa(prevLeader.label, '이', '가') + ' 어제 1위에서 <b class="dn">' + prevLeader.rank + '위</b>로');
      }
      if (parts.length) lines.push(['주도권', parts.join(', ')]);
    }

    var instM = d.axes && d.axes.flow && d.axes.flow.main && d.axes.flow.main.기관;
    if (instM && instM.y != null && instM.t != null) {
      var yTxt = eok(instM.y);
      lines.push(['누가', (open ? rel + ' 이 시각 기관은 ' : rel + ' 기관은 ') +
        '<b class="' + cls(instM.y) + '">' + yTxt + '</b>' + wasKo(yTxt) + '. 오늘은 ' +
        '<b class="' + cls(instM.t) + '">' + eok(instM.t) + '</b>']);
    }

    if (!lines.length) return '';
    return '<ul class="vsx-why">' + lines.map(function (l) {
      return '<li><span class="k">' + esc(l[0]) + '</span><span>' + l[1] + '</span></li>';
    }).join('') + '</ul>';
  }

  // 시간대별 카드 규칙(설계 §3.2) — pre·weekend는 카드 없음, close는 메인 곡선만, night도 카드 없음(2026-09-17 — 밤사이 미국 반도체 섹션만 남긴다).
  function slotOf(d) {
    var k = new Date(d.getTime() + 9 * 3600 * 1000);
    var day = k.getUTCDay(), hm = k.getUTCHours() * 100 + k.getUTCMinutes();
    if (day === 0 || day === 6) return 'weekend';
    if (hm >= 730 && hm < 900) return 'pre';
    if (hm >= 900 && hm <= 1530) return 'open';
    // 마감 곡선은 오늘 미국 브리핑이 발행될 때까지 둔다(2026-09-22 사용자 결정) — 발행 여부는 load()가 목록으로 판정한다.
    // 미국 휴장일처럼 발행이 없으면 자정까지 남는다(자정이 지나면 vs=close가 새 날짜로 closed를 준다).
    if (hm > 1530) return 'close';   // 15:31~15:39는 close지만 API가 early를 줘 카드가 안 그려진다
    return 'night';
  }

  // close(15:31~미국 브리핑 발행 전)는 메인 곡선(결론·곡선·근거)만(2026-09-17). 17:00부터는 '밤사이 미국 반도체 시황'이 위로 올라오고
  // 곡선은 섹터별 대표 종목 바로 위로 내려간다(stocks-home.js 국면 재배치, 2026-09-22).
  var CARDS = { pre: [], open: ['hero', 'heat', 'lead', 'flow'],
                close: ['hero'], night: [], weekend: [] };
  function cardsFor(slot) { return CARDS[slot] || []; }

  // 슬롯별 호출 엔드포인트 — pre·weekend는 아예 부르지 않는다(null).
  function endpointFor(slot) {
    if (slot === 'open') return '/api/intraday?vs=intraday';
    if (slot === 'close') return '/api/intraday?vs=close';   // night은 그릴 카드가 없어 부르지 않는다
    return null;
  }

  function render(d, slot) {
    slot = slot || slotOf(new Date());
    var cards = cardsFor(slot);
    function has(c) { return cards.indexOf(c) !== -1; }
    if (!root) return;
    if (!d || d.status !== 'ok' || !cards.length) { root.hidden = true; root.innerHTML = ''; paintTiles(null); return; }
    var rel = esc(d.prev.rel), html = '';
    if (has('hero')) {
      if (d.verdict) {
        html += '<div class="vs-hero"><p class="vs-eyebrow">🕘 ' + rel + ' ' + d.time + ' vs 오늘 ' + d.time +
          '<button type="button" class="help-q vs-help" aria-label="어제랑 비교해서 설명 보기">?</button></p>' +
          '<h2 class="' + (d.verdict.tone != null ? d.verdict.tone : d.verdict.judge === 'strong' ? 'up' : d.verdict.judge === 'weak' ? 'dn' : '') + '">' + esc(d.verdict.title) + '</h2>' +
          '<p class="vs-sub">' + esc(d.verdict.sub) + '</p></div>';
      }
      // 맨 위 세 칸(오늘·어제 같은 시각·차이)은 시안 B(2026-10-28)대로 코스피만 — 옛 3칸(외국인 누적·주도주 평균)은 F2로 뺀 그대로다.
      // 근거 4줄(heroWhy)은 마감 후에만 붙인다 — 장중엔 아래 강도·주도권·수급 카드가 같은 내용을 보여준다.
      var ov = chartOverlay(d.kospi.curveY, d.kospi.curveT, rel), lt = last(d.kospi.curveT);
      html += '<div class="vs-card">' + kpiRow(d) +
        '<div class="vs-legend"><span><i class="t ' + (lt ? cls(lt[1]) : '') + '"></i>오늘</span><span><i class="y"></i>' + rel + ' 같은 시각까지</span><span><i class="a"></i><i class="a dn"></i>0% 위 · 아래</span><span class="r">코스피 · 전일 종가 대비</span></div>' +
        '<div class="vs-chartbox">' + ov.left + '<div class="vs-plot">' + chartSvg(d.kospi.curveY, d.kospi.curveT) + ov.plot +
        '<i class="vs-guide" hidden></i><i class="vs-dot y" hidden></i><i class="vs-dot t" hidden></i><div class="vs-tip" hidden></div></div>' + ov.right + '</div>' +
        diffBox(d.kospi.curveY, d.kospi.curveT, d.prev.rel) +
        '<div class="vs-axis"><span style="left:0%">09:00</span><span style="left:30.77%">11:00</span><span style="left:61.54%">13:00</span><span style="right:0">15:30</span></div>' +
        (slot === 'open' ? '' : heroWhy(d, slot)) + '</div>';
    }

    // 렌더 순서 — 결론(위 곡선) → 강도 → 주도권 → 수급. 옛 '어제와 달라진 것' 가로 막대 카드는 누가 사는가와 겹쳐 뺐다(2026-09-17).
    if (has('heat')) html += heatCard(d.axes);
    if (has('lead')) html += leadCard(d.axes, d.kospi);

    if (has('flow')) html += flowCard(d.axes, slot, { rel: d.prev.rel, etc: d.flow ? { t: d.flow.t && d.flow.t.기타법인, y: d.flow.y && d.flow.y.기타법인 } : null });

    root.innerHTML = html;
    root.hidden = false;
    paintTiles(d);
    if (has('hero')) bindHover(root.querySelector ? root.querySelector('.vs-plot') : null, d);
  }

  // 곡선 위에서 포인터를 따라 안내선·점·말풍선을 옮긴다. 60초 폴링이 innerHTML을 갈아끼우면 새 요소에 다시 붙는다.
  function bindHover(plot, d) {
    if (!plot) return;
    var yP = d.kospi.curveY, tP = d.kospi.curveT, s = scale(yP, tP);
    var guide = plot.querySelector('.vs-guide'), dotY = plot.querySelector('.vs-dot.y'), dotT = plot.querySelector('.vs-dot.t'), tip = plot.querySelector('.vs-tip');
    function top(v) { return ((s.hi - v) / (s.hi - s.lo) * 100) + '%'; }
    function place(dot, v, left) { dot.hidden = v == null; if (v != null) { dot.style.left = left; dot.style.top = top(v); } }
    // 차이 줄은 색을 쓰지 않는다 — 빨강·파랑은 오르내림만 뜻한다(2026-10-28)
    function row(k, v, unit, c) { return '<p' + c + '><span>' + k + '</span><span class="' + (c ? '' : cls(v)) + '">' + (v != null ? f2(v) + unit : '—') + '</span></p>'; }
    function move(e) {
      var r = plot.getBoundingClientRect(), frac = (e.clientX - r.left) / r.width, h = hoverAt(yP, tP, frac);
      if (!h) return hide();
      var pct = h.m / 390 * 100, left = pct + '%';
      guide.hidden = false; guide.style.left = left;
      place(dotY, h.y, left); place(dotT, h.t, left);
      tip.innerHTML = '<b>' + h.time + '</b>' + row('오늘', h.t, '%', '') + row(esc(d.prev.rel), h.y, '%', '') + row('차이', h.diff, '%p', ' class="d"');
      tip.hidden = false;
      tip.style.left = left;
      tip.style.transform = pct > 55 ? 'translateX(calc(-100% - 10px))' : 'translateX(10px)';
    }
    function hide() { guide.hidden = dotY.hidden = dotT.hidden = tip.hidden = true; }
    plot.addEventListener('pointermove', move);
    plot.addEventListener('pointerdown', move);
    plot.addEventListener('pointerleave', hide);
  }

  // 주도주 타일(#us-linked-widget) 안 '어제 같은 시각' 블록 — 대결판 카드의 표 대신 각 타일에 그린다(§49).
  // 타일 위 큰 가격은 실시간이라 블록의 '오늘'과 다를 수 있다 — 그래서 블록 머리에 비교한 확정 분을 적는다.
  function paintTiles(d) {
    if (typeof document === 'undefined' || !document.querySelectorAll) return;
    var byCode = {};
    (d && d.status === 'ok' ? d.leaders || [] : []).forEach(function (l) { byCode[l.code] = l; });
    [].forEach.call(document.querySelectorAll('#us-linked-widget .us-tile[data-code] .vs-tb'), function (box) {
      var tile = box.closest('.us-tile'), l = tile && byCode[tile.getAttribute('data-code')];
      if (!l || l.t == null || l.y == null || l.diff == null) { box.hidden = true; box.innerHTML = ''; return; }
      var rel = esc(d.prev.rel);
      box.innerHTML = '<div class="vs-tb-h"><b>' + rel + ' 같은 시각</b><span>' + d.time + ' 기준</span></div>' +
        '<div class="vs-tb-g"><span class="k">' + rel + '</span><span class="v ' + cls(l.y) + '">' + f2(l.y) + '%</span>' +
        '<span class="k">오늘</span><span class="v ' + cls(l.t) + '">' + f2(l.t) + '%</span></div>' +
        '<div class="vs-tb-d"><span>' + rel + '보다</span><span class="p ' + cls(l.diff) + '">' + f2(l.diff) + '%p</span></div>';
      box.hidden = false;
    });
  }

  // 마지막 글자 받침 유무로 조사 짝을 고른다 — 한글이 아니면 받침 없는 쪽(without)을 쓴다.
  function josa(w, withBatchim, without) {
    var c = String(w).charCodeAt(String(w).length - 1) - 0xac00;
    return c >= 0 && c < 11172 && c % 28 ? withBatchim : without;
  }

  // 였어요/이었어요 — eok()가 내는 "조"(받침 없음)·"억"(받침 있음) 뒤에 붙는 계사를 맞춘다(§0 — 표기도 실측만큼 정확해야 한다).
  function wasKo(w) { return josa(w, '이었어요', '였어요'); }

  function shouldPoll() {
    var k = new Date(Date.now() + 9 * 3600 * 1000), dow = k.getUTCDay(), m = k.getUTCHours() * 60 + k.getUTCMinutes();
    return dow >= 1 && dow <= 5 && m >= 540 && m <= 931;
  }

  // 첫 응답 전 자리 — 결론+곡선 카드(장중 모양: 세 칸·범례·곡선·차이 막대·시각축)와 같은 높이를 먼저 잡아, 데이터가 도착할 때 아래 내용이 밀려 내려가지 않게 한다.
  // 숫자는 넣지 않는다(§0). 응답이 없거나 실패하면 render(null)이 영역째 숨긴다.
  function skeleton() {
    var line = function (w, cls) { return '<span class="skl skl-line' + (cls ? ' ' + cls : '') + '" style="width:' + w + '"></span>'; };
    root.innerHTML =
      '<div class="vs-hero vs-skel" aria-busy="true" aria-label="어제랑 비교해서 불러오는 중">' +
        '<p class="vs-eyebrow">' + line('190px') + '</p>' +
        line('58%', 'sk-h2') + line('86%', 'sk-sub') +
      '</div>' +
      '<div class="vs-card vs-skel" aria-hidden="true">' +
        '<div class="sk-kpis"><span class="skl"></span><span class="skl"></span><span class="skl"></span></div>' +
        '<div class="sk-legend">' + line('240px') + line('150px') + '</div>' +
        '<div class="skl sk-chart"></div><div class="skl sk-diff"></div>' +
        '<div class="sk-axis">' + line('34px') + line('34px') + line('34px') + line('34px') + '</div>' +
      '</div>';
    root.hidden = false;
  }

  // 슬롯에 따라 엔드포인트를 고르고(§3.2), pre·weekend는 아예 호출하지 않는다.
  // 오늘(KST) 미국 브리핑이 목록에서 ready인가. 미국 브리핑은 21:15에 도므로 21:00 전엔 조회하지 않는다.
  function kstNow() { var k = new Date(Date.now() + 9 * 3600 * 1000); return { ymd: k.toISOString().slice(0, 10), hm: k.getUTCHours() * 100 + k.getUTCMinutes() }; }
  function usPublished(list, ymd) {
    var s = list && list.slots && list.slots[ymd];
    return !!(s && s.us && s.us.state === 'ready');
  }

  function load() {
    var slot = slotOf(new Date()), url = endpointFor(slot);
    if (!url) { render(null, slot); return; }
    if (document.hidden) return;                       // 백그라운드 탭은 부르지 않는다(2026-08-16 차단 사고)
    var k = kstNow();
    if (slot === 'close' && k.hm >= 2100) {
      fetch('/data/briefings-list.json', { cache: 'no-store' })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (list) { if (usPublished(list, k.ymd)) render(null, slot); else fetchVs(url, slot); })
        .catch(function () { fetchVs(url, slot); });
      return;
    }
    fetchVs(url, slot);
  }
  function fetchVs(url, slot) {
    if (root && root.hidden && !root.innerHTML) skeleton();
    fetch(url, { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { render(d, slot); })
      .catch(function () { render(null, slot); });
  }

  // 결론 카드 오른쪽 ? — 누르면 이 영역이 무엇을 비교하는지 모달로 설명한다(기존 #help-modal 재사용).
  // 60초 폴링이 innerHTML을 갈아끼우므로 버튼마다 붙이지 않고 문서에 한 번만 위임한다.
  var HELP_HTML = '<div class="tt">어제랑 비교해서란?</div><div class="bd">' +
    '지금 코스피 흐름을 <b>직전 거래일 같은 시각</b>과 나란히 놓고 비교해요.<br><br>' +
    '<b>맨 위 결론</b> — 오늘 코스피가 오르는지 내리는지를 먼저 말하고, 직전 거래일 같은 시각과 비교해요. 예를 들어 둘 다 올랐는데 오늘이 덜 올랐으면 "오르고 있지만 어제보다 오름폭이 작아요"라고 적어요. 차이가 ±0.3%p 안이면 비슷한 것으로 봐요.<br><br>' +
    '<b>그래프</b> — 굵은 선이 오늘, 점선이 직전 거래일이에요. 오늘 선 아래 면은 전일 종가(0%)보다 위면 <b>빨간색</b>, 아래면 <b>파란색</b>이에요. ' +
    '색은 오늘의 오르내림만 뜻해요. 직전 거래일과의 차이는 맨 위 세 칸과 아래 <b>회색 막대</b>(5분마다 잰 오늘 − 직전 거래일, 선 위면 오늘이 높음)로 봐요. 오른쪽 회색 칸은 아직 남은 장이에요.<br><br>' +
    '<b>아래 카드</b><br>· 얼마나 뜨거운가 — 누적 거래량과 하루 진폭(고가−저가)<br>' +
    '· 어디가 이끄나 — 섹터 대표 3종목 평균. 점선은 코스피·코스닥 오늘 등락이고, 코스피 점선을 넘은 섹터가 시장보다 센 곳이에요<br>· 누가 사는가 — 판 쪽과 산 쪽, 기관 안 순매수 구성<br><br>' +
    '<b>기준 시각</b> — 다 끝난 1분봉만 써서 실제보다 2분쯤 늦게 따라와요. 그래서 위 LIVE 지수와 숫자가 조금 다를 수 있어요.<br><br>' +
    '<b>보이는 시간</b><br>· 장중 09:00~15:30 — 그래프와 강도·주도권·수급 카드<br>' +
    '· 마감 후 15:31~미국 브리핑 발행 전 — 그래프와 근거 네 줄(가격·강도·주도권·누가, 정규장 확정값). 17:00부터는 섹터별 대표 종목 바로 위에 있어요<br>· 미국 브리핑 발행 이후·장 전·주말 — 보이지 않아요<br><br>' +
    '수급은 코스피 시장 전체 합계예요. 투자 권유가 아닌 참고용 비교예요.</div>';
  function openHelp() {
    var bg = document.getElementById('help-modal-bg'), body = document.getElementById('help-modal-body');
    if (!bg || !body) return false;
    body.innerHTML = HELP_HTML;
    bg.classList.add('open');
    return true;
  }
  document.addEventListener('click', function (e) {
    var t = e.target;
    if (t && t.closest && t.closest('#vs-root .vs-help')) { e.preventDefault(); openHelp(); }
  });

  window.__vsIntraday = {
    render: render, openHelp: openHelp, HELP_HTML: HELP_HTML, shouldPoll: shouldPoll, slotOf: slotOf, cardsFor: cardsFor, endpointFor: endpointFor,
    usPublished: usPublished, chartSvg: chartSvg, bandRuns: bandRuns, diffSvg: diffSvg, diffPts: diffPts, chartOverlay: chartOverlay, hoverAt: hoverAt,
    heatCard: heatCard, leadCard: leadCard, flowCard: flowCard, heatWord: heatWord, kpiRow: kpiRow, heroWhy: heroWhy, wasKo: wasKo,
    josa: josa,
  };
  if (!root) return;
  load();
  setInterval(load, 60000);
  // 백그라운드에서 열린 탭은 load()가 요청을 건너뛴다 — 보이는 순간 바로 불러와 최대 60초 빈 화면을 없앤다.
  document.addEventListener('visibilitychange', function () { if (!document.hidden) load(); });
})();
