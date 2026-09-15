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

  function chartSvg(yPts, tPts) {
    var W = 600, H = 180, s = scale(yPts, tPts), lo = s.lo, hi = s.hi;
    function x(m) { return (m / 390 * W).toFixed(1); }
    function y(v) { return ((hi - v) / (hi - lo) * H).toFixed(1); }
    function path(pts) { return pts.map(function (p, i) { return (i ? 'L' : 'M') + x(p[0]) + ' ' + y(p[1]); }).join(''); }
    var zero = '<line x1="0" x2="' + W + '" y1="' + y(0) + '" y2="' + y(0) + '" class="vs-zero"/>';
    return '<svg class="vs-chart" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none" role="img" aria-label="코스피 곡선">' + zero +
      '<path d="' + path(yPts || []) + '" class="vs-line-y" vector-effect="non-scaling-stroke"/>' +
      '<path d="' + path(tPts || []) + '" class="vs-line-t" vector-effect="non-scaling-stroke"/></svg>';
  }

  function stat(title, j, yl, yv, yc, tv, tc, diff) {
    return '<div class="vs-stat"><div class="vs-stat-h"><span>' + title + '</span>' + pill(j) + '</div>' +
      '<div class="vs-stat-r"><span>' + esc(yl) + '</span><b class="' + yc + '">' + yv + '</b></div>' +
      '<div class="vs-stat-r"><span>오늘</span><b class="vs-big ' + tc + '">' + tv + '</b></div>' +
      '<p class="vs-diff">차이 ' + diff + '</p></div>';
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
    html += '<div class="vs-card"><div class="vs-legend"><span><i class="y"></i>' + rel + ' 같은 시각까지</span><span><i class="t"></i>오늘</span><span class="r">코스피 · 전일 종가 대비</span></div>' +
      '<div class="vs-plot">' + chartSvg(d.kospi.curveY, d.kospi.curveT) +
      '<i class="vs-guide" hidden></i><i class="vs-dot y" hidden></i><i class="vs-dot t" hidden></i><div class="vs-tip" hidden></div></div>' +
      '<div class="vs-axis"><span style="left:0%">09:00</span><span style="left:30.77%">11:00</span><span style="left:61.54%">13:00</span><span style="right:0">15:30</span></div>' +
      (stats ? '<div class="vs-stats">' + stats + '</div>' : '') + '</div>';

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

  window.__vsIntraday = { render: render, shouldPoll: shouldPoll, chartSvg: chartSvg, hoverAt: hoverAt };
  if (!root) return;
  load();
  setInterval(load, 60000);
})();
