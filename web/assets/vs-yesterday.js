// '어제랑 비교해서' 장중 대결판 — /api/intraday?vs=intraday 응답을 #vs-root에 그린다(설계 §4.2, 시안 v4)
(function () {
  var root = document.getElementById('vs-root');
  var JL = { same: '비슷해요', strong: '오늘이 셈', weak: '오늘이 약함' };
  var JC = { same: 'neutral', strong: 'up', weak: 'dn' };

  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function f2(n) { return n == null ? '—' : (n > 0 ? '+' : n < 0 ? '−' : '') + Math.abs(n).toFixed(2); }
  function cls(n) { return n > 0 ? 'up' : n < 0 ? 'dn' : ''; }
  function fmt(n) { return Number(n).toLocaleString('en-US'); }
  function eok(e) { var a = Math.abs(e), s = e > 0 ? '+' : e < 0 ? '−' : ''; return a >= 10000 ? s + (a / 10000).toFixed(2) + '조' : s + fmt(a) + '억'; }
  function pill(j) { return j ? '<span class="vs-pill ' + JC[j] + '">' + JL[j] + '</span>' : ''; }

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

  // 곡선 SVG(가로로 늘려 그린다 — 글자는 넣지 않는다). A안: 두 선 사이 색 띠, 눈금선, 지금 선·남은 장 음영.
  function chartSvg(yPts, tPts) {
    var W = 600, H = 180, s = scale(yPts, tPts), lo = s.lo, hi = s.hi;
    function x(m) { return (m / 390 * W).toFixed(1); }
    function y(v) { return ((hi - v) / (hi - lo) * H).toFixed(1); }
    function path(pts) { return pts.map(function (p, i) { return (i ? 'L' : 'M') + x(p[0]) + ' ' + y(p[1]); }).join(''); }
    var out = '', ys = {}, lt = last(tPts);
    ticks(lo, hi).forEach(function (v) { if (v !== 0) out += '<line x1="0" x2="' + W + '" y1="' + y(v) + '" y2="' + y(v) + '" class="vs-grid" vector-effect="non-scaling-stroke"/>'; });
    if (lt && lt[0] < 390) {
      out += '<rect x="' + x(lt[0]) + '" y="0" width="' + (W - x(lt[0])).toFixed(1) + '" height="' + H + '" class="vs-rest"/>' +
        '<line x1="' + x(lt[0]) + '" x2="' + x(lt[0]) + '" y1="0" y2="' + H + '" class="vs-now" vector-effect="non-scaling-stroke"/>';
    }
    out += '<line x1="0" x2="' + W + '" y1="' + y(0) + '" y2="' + y(0) + '" class="vs-zero" vector-effect="non-scaling-stroke"/>';
    // 색 띠 — 같은 분에 두 곡선 값이 모두 있는 구간만 채운다(없는 값을 이어 그리지 않는다, §0)
    (yPts || []).forEach(function (p) { ys[p[0]] = p[1]; });
    (tPts || []).forEach(function (b, i) {
      if (!i) return;
      var a = tPts[i - 1], c = ys[a[0]], d = ys[b[0]];
      if (c == null || d == null) return;
      out += '<polygon points="' + x(a[0]) + ',' + y(a[1]) + ' ' + x(b[0]) + ',' + y(b[1]) + ' ' + x(b[0]) + ',' + y(d) + ' ' + x(a[0]) + ',' + y(c) +
        '" class="vs-band ' + (a[1] + b[1] >= c + d ? 'up' : 'dn') + '"/>';
    });
    return '<svg class="vs-chart" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none" role="img" aria-label="코스피 곡선">' + out +
      '<path d="' + path(yPts || []) + '" class="vs-line-y" vector-effect="non-scaling-stroke"/>' +
      '<path d="' + path(tPts || []) + '" class="vs-line-t" vector-effect="non-scaling-stroke"/></svg>';
  }

  // 곡선 위에 겹치는 글자 — 왼쪽 여백 세로 눈금, 오른쪽 여백 선 끝 값, 곡선 안 차이 괄호·'남은 장'.
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
        '<span class="vs-end" style="top:' + ya.toFixed(2) + '%"><b class="' + cls(ly[1]) + '">' + f2(ly[1]) + '%</b>' + rel + '</span>';
      var diff = Math.round((lt[1] - ly[1]) * 100) / 100, xp = lt[0] / 390 * 100;
      if (gap >= 16 && diff !== 0) {                 // 괄호·차이 글자를 넣을 틈이 있을 때만
        plot += '<i class="vs-gapline ' + cls(diff) + '" style="left:' + xp.toFixed(2) + '%;top:' + Math.min(tt, yt).toFixed(2) + '%;height:' + gap.toFixed(2) + '%"></i>' +
          '<span class="vs-gap ' + cls(diff) + (xp > 70 ? ' l' : '') + '" style="left:' + xp.toFixed(2) + '%;top:' + ((tt + yt) / 2).toFixed(2) + '%">' + f2(diff) + '%p</span>';
      }
      if (lt[0] <= 330) plot += '<span class="vs-rest-l" style="left:' + xp.toFixed(2) + '%">남은 장</span>';
    }
    return { left: left, right: right, plot: plot };
  }

  // chart는 강도·주도권 카드가 쓰는 선택 인자(0축 막대) — 기존 호출부는 8개 인자만 넘겨 그대로 동작한다.
  function stat(title, j, yl, yv, yc, tv, tc, diff, chart) {
    return '<div class="vs-stat"><div class="vs-stat-h"><span>' + title + '</span>' + pill(j) + '</div>' +
      '<div class="vs-stat-r"><span>' + esc(yl) + '</span><b class="' + yc + '">' + yv + '</b></div>' +
      '<div class="vs-stat-r"><span>오늘</span><b class="vs-big ' + tc + '">' + tv + '</b></div>' +
      '<p class="vs-diff">차이 ' + diff + '</p>' + (chart || '') + '</div>';
  }

  // 0축 세로 막대 2칸 — 어제 옅게 · 오늘 진하게. zero:false는 방향 없는 양(거래량·진폭)이라 중립색.
  function miniBars(prev, now, opts) {
    var zero = !opts || opts.zero !== false;
    if (typeof prev !== 'number' || typeof now !== 'number') return '';
    var M = Math.max(Math.abs(prev), Math.abs(now)) || 1;
    function bar(v, isNow) {
      var h = Math.max(Math.abs(v) / M * (zero ? 18 : 36), 2);
      var st = zero ? (v >= 0 ? 'bottom:50%;height:' : 'top:50%;height:') + h + 'px'
                    : 'bottom:0;height:' + h + 'px';
      var c = zero ? (v >= 0 ? 'up' : 'dn') : 'mag';
      return '<span class="vsx-bar' + (isNow ? '' : ' prev') + '"><i class="' + c + '" style="' + st + '"></i></span>';
    }
    return '<div class="vsx-mini"><div class="vsx-bars ' + (zero ? 'zero' : 'base') + '">'
      + bar(prev, false) + bar(now, true) + '</div>'
      + '<div class="vsx-ax"><span>어제</span><span class="t">오늘</span></div></div>';
  }

  function pctTxt(n, unit) { return n == null ? '—' : f2(n) + unit; }

  // 강도 카드 — 코스피 누적 거래량·일중 진폭. 지수 1분봉엔 거래대금이 없어 거래량(천주)으로 비교한다.
  function heatCard(axes) {
    if (!axes || !axes.heat) return '';
    var vol = axes.heat.vol, amp = axes.heat.amp;
    if (!vol || !amp) return '';
    var rows = '<div class="vs-stats" style="grid-template-columns:repeat(2,minmax(0,1fr));margin-top:0">'
      + stat('코스피 누적 거래량', vol.judge, '어제', vol.y != null ? fmt(vol.y) + '<small> 천주</small>' : '—', cls(vol.y),
          vol.t != null ? fmt(vol.t) + '<small> 천주</small>' : '—', cls(vol.t), pctTxt(vol.diff, '%'), miniBars(vol.y, vol.t, { zero: false }))
      + stat('코스피 일중 진폭', amp.judge, '어제', amp.y != null ? amp.y.toFixed(2) + '%' : '—', '',
          amp.t != null ? amp.t.toFixed(2) + '%' : '—', '', pctTxt(amp.diff, '%p'), miniBars(amp.y, amp.t, { zero: false }))
      + '</div>';
    return '<div class="vs-card"><div class="vs-card-h"><p>얼마나 뜨거운가</p><span>새 축 · 강도</span></div>' + rows +
      '<p class="vs-sub">지수 1분봉에는 거래<b>대금</b>(원)이 없어요 — 현재값만 있고 과거 시각은 못 구합니다. ' +
      '그래서 거래<b>량</b>(천주)으로 비교해요.</p></div>';
  }

  // 코스닥·코스피200 한 줄 — 데이터가 없으면(§45) 그 지수 줄만 빠진다.
  function marketRow(label, ax) {
    if (!ax || ax.t == null) return '';
    return stat(label, ax.judge, '어제', ax.y != null ? f2(ax.y) + '%' : '—', cls(ax.y), f2(ax.t) + '%', cls(ax.t),
      pctTxt(ax.diff, '%p'), miniBars(ax.y, ax.t, { zero: true }));
  }

  // 섹터 대표 3종목 평균 한 행 — "섹터 평균"이 아니라 "대표 N종목 평균"임을 이름 나열로 드러낸다.
  // n이 3 미만이면(일부 종목 결측) 실제 조회된 종목 수를 그대로 적는다 — 3종목이라 지어내지 않는다.
  function sectorRow(s) {
    var badge = s.move == null ? '<span class="vs-pill neutral">—</span>'
      : s.move > 0 ? '<span class="vs-pill up">▲' + s.move + '</span>'
      : s.move < 0 ? '<span class="vs-pill dn">▼' + (-s.move) + '</span>'
      : '<span class="vs-pill neutral">─</span>';
    var n = s.n != null ? s.n : (s.names || []).length;
    return '<tr><td class="nm"><span class="vsx-rk' + (s.rank === 1 ? ' top' : '') + '">' + s.rank + '</span>' +
      esc(s.label) + '<small>대표 ' + n + '종목 · ' + esc((s.names || []).join('·')) + '</small></td>' +
      '<td class="' + cls(s.t) + '">' + f2(s.t) + '%</td><td>' + (s.y != null ? f2(s.y) + '%' : '—') + '</td>' +
      '<td class="' + cls(s.diff) + '">' + pctTxt(s.diff, '%p') + '</td><td>' + badge + '</td></tr>';
  }

  // 주도권 카드 — 코스피·코스피200·코스닥이 어제 같은 시각보다 세거나 약한지, 섹터 대표 3종목 평균 순위가
  // 어떻게 바뀌었는지. 코스피는 axes가 아니라 응답 최상위 kospi에 있다 — 없으면 그 칸만 뺀다(지어내지 않는다).
  function leadCard(axes, kospi) {
    if (!axes || !axes.sectors || !axes.sectors.length) return '';
    var mkt = axes.market || {};
    var stats = marketRow('코스피', kospi) + marketRow('코스피200', mkt.kospi200) + marketRow('코스닥', mkt.kosdaq);
    var rows = axes.sectors.map(sectorRow).join('');
    return '<div class="vs-card"><div class="vs-card-h"><p>어디가 끄는가</p><span>새 축 · 주도권</span></div>' +
      (stats ? '<div class="vs-stats" style="margin-top:0">' + stats + '</div>' : '') +
      '<p class="vs-lbl vsx-sec">대표 3종목 평균</p>' +
      '<table class="vsx-tbl" style="margin-top:0"><thead><tr><th>섹터</th><th>오늘</th><th>어제</th><th>차이</th><th>순위</th></tr></thead>' +
      '<tbody>' + rows + '</tbody></table>' +
      '<p class="vs-sub">각 섹터 <b>대표 3종목의 동일가중 평균</b>이에요(시총가중 아니에요).</p></div>';
  }

  // 개인·외국인·기관 부호가 뒤집혔는지(방향 전환)만 알린다 — judge('same'/'strong'/'weak')가 아니라 turned다.
  function turnPill(turned, t) {
    if (turned == null) return '';
    return turned ? '<span class="vs-pill ' + (t > 0 ? 'up' : 'dn') + '">방향 전환</span>' : '<span class="vs-pill neutral">같은 방향</span>';
  }

  function flowMainStat(title, m) {
    if (!m) return '';
    return '<div class="vs-stat"><div class="vs-stat-h"><span>' + title + '</span>' + turnPill(m.turned, m.t) + '</div>' +
      '<div class="vs-stat-r"><span>어제</span><b class="' + cls(m.y) + '">' + (m.y != null ? eok(m.y) : '—') + '</b></div>' +
      '<div class="vs-stat-r"><span>오늘</span><b class="vs-big ' + cls(m.t) + '">' + (m.t != null ? eok(m.t) : '—') + '</b></div>' +
      miniBars(m.y, m.t, { zero: true }) + '</div>';
  }

  // 기관 세부 6칸 짝 막대 — 왼쪽 옅은 막대가 어제, 오른쪽 진한 막대가 오늘. 두 값을 숫자로도 함께 적는다.
  // 값이 없으면(§0 — 0이나 다른 값으로 채우지 않는다) 그 칸엔 막대를 그리지 않는다 — 칸 자체는 정렬을 위해 남긴다.
  function flowInstPairs(inst) {
    var mx = 1;
    (inst || []).forEach(function (r) {
      if (typeof r.t === 'number') mx = Math.max(mx, Math.abs(r.t));
      if (typeof r.y === 'number') mx = Math.max(mx, Math.abs(r.y));
    });
    function bar(v, isNow) {
      if (typeof v !== 'number') return '<span class="vsx-bar' + (isNow ? '' : ' prev') + '"></span>';
      var h = Math.max(Math.abs(v) / mx * 34, 2);
      var st = v >= 0 ? 'bottom:50%;height:' + h + 'px' : 'top:50%;height:' + h + 'px';
      return '<span class="vsx-bar' + (isNow ? '' : ' prev') + '"><i class="' + (v >= 0 ? 'up' : 'dn') + '" style="' + st + '"></i></span>';
    }
    return (inst || []).map(function (r) {
      return '<div><div class="vsx-pbars">' + bar(r.y, false) + bar(r.t, true) + '</div>' +
        '<div class="vsx-pv ' + cls(r.t) + '">' + (r.t != null ? eok(r.t) : '—') + '</div>' +
        '<div class="vsx-pp">어제 ' + (r.y != null ? eok(r.y) : '—') + '</div>' +
        '<div class="vsx-pl">' + esc(r.key) + '</div></div>';
    }).join('');
  }

  // 수급 심층 카드 — 개인·외국인·기관 방향 전환 + 기관 안 6개 주체별 순매수 짝 막대.
  function flowCard(axes) {
    if (!axes || !axes.flow) return '';
    var flow = axes.flow, keys = ['개인', '외국인', '기관'];
    var stats = keys.map(function (k) { return flowMainStat(k, flow.main && flow.main[k]); }).join('');
    return '<div class="vs-card"><div class="vs-card-h"><p>누가 사는가</p><span>새 축 · 수급 심층</span></div>' +
      (stats ? '<div class="vs-stats" style="margin-top:0">' + stats + '</div>' : '') +
      '<p class="vs-lbl vsx-sec">기관 안에서 누가 바뀌었나</p>' +
      '<p class="vs-lbl-s">왼쪽 옅은 막대가 어제, 오른쪽이 오늘</p>' +
      '<div class="vsx-pairs">' + flowInstPairs(flow.inst) + '</div></div>';
  }

  function flowRows(d) {
    var keys = ['개인', '외국인', '기관'], mx = 1;
    keys.forEach(function (k) { mx = Math.max(mx, Math.abs(d.flow.t[k]), Math.abs(d.flow.y[k])); });
    function bar(v, kind) {
      var w = (Math.abs(v) / mx * 50).toFixed(2);
      return '<div class="vs-frow"><span class="vs-fl ' + (v < 0 ? (kind === 'now' ? 'dn' : 'muted') : '') + '">' + (v < 0 ? eok(v) : '') + '</span>' +
        '<div class="vs-ftrack"><i class="vs-fbar ' + kind + ' ' + cls(v) + '" style="' + (v >= 0 ? 'left' : 'right') + ':50%;width:' + w + '%"></i></div>' +
        '<span class="vs-fr ' + (v >= 0 ? (kind === 'now' ? 'up' : 'muted') : '') + '">' + (v >= 0 ? eok(v) : '') + '</span></div>';
    }
    return '<div class="vs-flow">' + keys.map(function (k) {
      return '<div class="vs-fgroup"><p class="vs-fname">' + k + '</p>' + bar(d.flow.t[k], 'now') + bar(d.flow.y[k], 'prev') + '</div>';
    }).join('') + '<p class="vs-flegend"><span><i class="now"></i>위 오늘 ' + d.flow.time + '</span><span><i></i>아래 ' + esc(d.prev.rel) + ' ' + d.flow.time + '</span></p></div>';
  }

  function render(d) {
    if (!root) return;
    if (!d || d.status !== 'ok') { root.hidden = true; root.innerHTML = ''; paintTiles(null); return; }
    var rel = esc(d.prev.rel), html = '';
    if (d.verdict) {
      html += '<div class="vs-hero"><p class="vs-eyebrow">🕘 ' + rel + ' ' + d.time + ' vs 오늘 ' + d.time + '</p>' +
        '<h2 class="' + (d.verdict.judge === 'strong' ? 'up' : d.verdict.judge === 'weak' ? 'dn' : '') + '">' + esc(d.verdict.title) + '</h2>' +
        '<p class="vs-sub">' + esc(d.verdict.sub) + '</p></div>';
    }
    var stats = '';
    if (d.kospi.diff != null) stats += stat('코스피', d.kospi.judge, d.prev.rel, f2(d.kospi.y) + '%', cls(d.kospi.y), f2(d.kospi.t) + '%', cls(d.kospi.t), f2(d.kospi.diff) + '%p');
    if (d.flow) stats += stat('외국인 누적 순매수', d.flow.judge, d.prev.rel, eok(d.flow.y['외국인']), cls(d.flow.y['외국인']), eok(d.flow.t['외국인']), cls(d.flow.t['외국인']), eok(d.flow.foreignDiff));
    if (d.avg) stats += stat('주도주 3종목 평균', d.avg.judge, d.prev.rel, f2(d.avg.y) + '%', cls(d.avg.y), f2(d.avg.t) + '%', cls(d.avg.t), f2(d.avg.diff) + '%p');
    var ov = chartOverlay(d.kospi.curveY, d.kospi.curveT, rel);
    html += '<div class="vs-card"><div class="vs-legend"><span><i class="t"></i>오늘</span><span><i class="y"></i>' + rel + ' 같은 시각까지</span><span><i class="a"></i>차이</span><span class="r">코스피 · 전일 종가 대비</span></div>' +
      '<div class="vs-chartbox">' + ov.left + '<div class="vs-plot">' + chartSvg(d.kospi.curveY, d.kospi.curveT) + ov.plot +
      '<i class="vs-guide" hidden></i><i class="vs-dot y" hidden></i><i class="vs-dot t" hidden></i><div class="vs-tip" hidden></div></div>' + ov.right + '</div>' +
      '<div class="vs-axis"><span style="left:0%">09:00</span><span style="left:30.77%">11:00</span><span style="left:61.54%">13:00</span><span style="right:0">15:30</span></div>' +
      (stats ? '<div class="vs-stats">' + stats + '</div>' : '') + '</div>';

    // 렌더 순서 — 결론(위 곡선) → 강도 → 주도권 → 수급(아래 이슈·수급 카드 + 기관 세부).
    html += heatCard(d.axes) + leadCard(d.axes, d.kospi);

    var changed = '';
    if (d.issues) {
      var mark = function (t) { var o = esc(t); d.issues.new.forEach(function (w) { o = o.split(esc(w)).join('<mark>' + esc(w) + '</mark>'); }); return o; };
      var list = function (a) { return a.length ? '<ul class="vs-issues">' + a.map(function (x) { return '<li><span>' + x.t + '</span><span>' + mark(x.title) + '</span></li>'; }).join('') + '</ul>' : '<p class="vs-empty">이 시각까지 수집된 이슈가 없어요.</p>'; };
      var chips = function (a, k) { return a.length ? a.map(function (w) { return '<span class="vs-chip ' + k + '">' + esc(w) + '</span>'; }).join('') : '<span class="vs-chip">없음</span>'; };
      changed += '<p class="vs-lbl">📰 장중 이슈</p>' +
        '<div class="vs-chips"><span class="vs-chips-k">새로 떠오름</span>' + chips(d.issues.new, 'new') + '</div>' +
        '<div class="vs-chips"><span class="vs-chips-k">계속 이어짐</span>' + chips(d.issues.keep, 'keep') + '</div>' +
        '<div class="vs-issue-cols"><div><p class="vs-col-h">' + rel + ' ' + esc(d.prev.label) + '</p>' + list(d.issues.y) + '</div>' +
        '<div><p class="vs-col-h">오늘 ' + esc(d.today.label) + '</p>' + list(d.issues.t) + '</div></div>';
    }
    if (d.flow) changed += '<p class="vs-lbl vs-center">코스피 전체 · 투자자별 누적 순매수</p><p class="vs-lbl-s">코스피 시장 전체 합계예요. 주도주 3종목만의 수급이 아니에요.</p>' + flowRows(d);
    if (changed) html += '<div class="vs-card"><div class="vs-card-h"><p>' + withJosa(d.prev.rel) + ' 달라진 것</p><span>' + d.time + '까지 기준</span></div>' + changed + '</div>';
    html += flowCard(d.axes);

    root.innerHTML = html;
    root.hidden = false;
    paintTiles(d);
    bindHover(root.querySelector ? root.querySelector('.vs-plot') : null, d);
  }

  // 곡선 위에서 포인터를 따라 안내선·점·말풍선을 옮긴다. 60초 폴링이 innerHTML을 갈아끼우면 새 요소에 다시 붙는다.
  function bindHover(plot, d) {
    if (!plot) return;
    var yP = d.kospi.curveY, tP = d.kospi.curveT, s = scale(yP, tP);
    var guide = plot.querySelector('.vs-guide'), dotY = plot.querySelector('.vs-dot.y'), dotT = plot.querySelector('.vs-dot.t'), tip = plot.querySelector('.vs-tip');
    function top(v) { return ((s.hi - v) / (s.hi - s.lo) * 100) + '%'; }
    function place(dot, v, left) { dot.hidden = v == null; if (v != null) { dot.style.left = left; dot.style.top = top(v); } }
    function row(k, v, unit, c) { return '<p' + c + '><span>' + k + '</span><span class="' + cls(v) + '">' + (v != null ? f2(v) + unit : '—') + '</span></p>'; }
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

  function withJosa(w) { var c = w.charCodeAt(w.length - 1) - 0xac00; return w + (c >= 0 && c < 11172 && c % 28 ? '과' : '와'); }

  function shouldPoll() {
    var k = new Date(Date.now() + 9 * 3600 * 1000), dow = k.getUTCDay(), m = k.getUTCHours() * 60 + k.getUTCMinutes();
    return dow >= 1 && dow <= 5 && m >= 540 && m <= 931;
  }

  function load() {
    if (!shouldPoll()) { render(null); return; }
    if (document.hidden) return;                       // 백그라운드 탭은 부르지 않는다(2026-08-16 차단 사고)
    fetch('/api/intraday?vs=intraday', { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(render)
      .catch(function () { render(null); });
  }

  window.__vsIntraday = {
    render: render, shouldPoll: shouldPoll, chartSvg: chartSvg, chartOverlay: chartOverlay, hoverAt: hoverAt,
    heatCard: heatCard, leadCard: leadCard, flowCard: flowCard, miniBars: miniBars,
  };
  if (!root) return;
  load();
  setInterval(load, 60000);
  // 백그라운드에서 열린 탭은 load()가 요청을 건너뛴다 — 보이는 순간 바로 불러와 최대 60초 빈 화면을 없앤다.
  document.addEventListener('visibilitychange', function () { if (!document.hidden) load(); });
})();
