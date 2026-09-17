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

  // 곡선 SVG(가로로 늘려 그린다 — 글자는 넣지 않는다). H안(2026-09-17): 매끄러운 두 곡선 사이를 칠한다 —
  // 오늘이 어제보다 위면 빨강, 아래면 파랑. 면의 두께가 곧 차이이고, 아래 막대 칸(diffSvg)이 같은 차이를 분마다 보여준다.
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
    bandRuns(yPts, tPts).forEach(function (r) {
      var a = r.pts.map(function (q) { return [+x(q[0]), +y(q[1])]; }), b = r.pts.map(function (q) { return [+x(q[0]), +y(q[2])]; }).reverse();
      out += '<path d="M' + a[0][0].toFixed(1) + ' ' + a[0][1].toFixed(1) + smoothTail(a) + 'L' + b[0][0].toFixed(1) + ' ' + b[0][1].toFixed(1) + smoothTail(b) +
        'Z" class="vs-band ' + (r.sg > 0 ? 'up' : 'dn') + '"/>';
    });
    return '<svg class="vs-chart" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none" role="img" aria-label="코스피 곡선">' + out +
      '<path d="' + smoothPath(yPts || [], x, y) + '" class="vs-line-y" vector-effect="non-scaling-stroke"/>' +
      '<path d="' + smoothPath(tPts || [], x, y) + '" class="vs-line-t" vector-effect="non-scaling-stroke"/></svg>';
  }

  // 같은 분에 두 곡선 값이 모두 있는 점의 차이(오늘−어제). 한쪽만 있는 분은 뺀다(§0 — 채우지 않는다).
  function diffPts(yPts, tPts) {
    var ys = {};
    (yPts || []).forEach(function (p) { ys[p[0]] = p[1]; });
    return (tPts || []).filter(function (p) { return ys[p[0]] != null; })
      .map(function (p) { return [p[0], Math.round((p[1] - ys[p[0]]) * 100) / 100]; });
  }

  // 곡선 아래 차이 막대 칸 — 샘플 분마다 0축 세로 막대(오늘이 위면 빨강, 아래면 파랑). 없으면 칸째 생략.
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
        '" height="' + h.toFixed(1) + '" class="vs-dbar ' + cls(p[1]) + '"/>';
    });
    return '<svg class="vs-dchart" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none" role="img" aria-label="오늘과 어제의 차이 막대">' + out + '</svg>';
  }

  // 차이 막대 칸 — 왼쪽 '차이' 라벨, 오른쪽 지금 시각의 차이 %p
  function diffBox(yPts, tPts) {
    var ds = diffSvg(yPts, tPts), lp = last(diffPts(yPts, tPts));
    if (!ds) return '';
    return '<div class="vs-diffbox"><span class="vs-ytick" style="top:50%">차이</span><div class="vs-dplot">' + ds + '</div>' +
      '<span class="vs-end" style="top:50%"><b class="' + cls(lp[1]) + '">' + f2(lp[1]) + '%p</b></span></div>';
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
          // %p 글자는 남은 장 칸(지금 선 오른쪽)에만 둔다 — 왼쪽으로 넘기면 곡선을 덮는다. 장 끝 무렵엔 아래 차이 칸 끝 값이 대신한다.
          (xp <= 85 ? '<span class="vs-gap ' + cls(diff) + '" style="left:' + xp.toFixed(2) + '%;top:' + ((tt + yt) / 2).toFixed(2) + '%">' + f2(diff) + '%p</span>' : '');
      }
      plot += '<i class="vs-enddot y" style="left:' + xp.toFixed(2) + '%;top:' + yt.toFixed(2) + '%"></i><i class="vs-enddot t" style="left:' + xp.toFixed(2) + '%;top:' + tt.toFixed(2) + '%"></i>';
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
    if (vol.t == null && amp.t == null) return '';   // 오늘 값이 둘 다 없으면 카드째 생략한다(F5, §0)
    var rows = '<div class="vs-stats vsx-stats2">'
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
      (stats ? '<div class="vs-stats vsx-mt0">' + stats + '</div>' : '') +
      '<p class="vs-lbl vsx-sec">대표 3종목 평균</p>' +
      '<table class="vsx-tbl vsx-mt0"><thead><tr><th>섹터</th><th>오늘</th><th>어제</th><th>차이</th><th>순위</th></tr></thead>' +
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
  // slot이 close·night이면 카드 라벨을 "정규장 확정 15:40"으로 바꿔 애프터장이 섞인 홈 LIVE 바와 구분한다(F2).
  function flowCard(axes, slot) {
    if (!axes || !axes.flow) return '';
    var flow = axes.flow, keys = ['개인', '외국인', '기관'];
    var stats = keys.map(function (k) { return flowMainStat(k, flow.main && flow.main[k]); }).join('');
    var subLabel = (slot === 'close' || slot === 'night') ? '정규장 확정 15:40' : '새 축 · 수급 심층';
    return '<div class="vs-card"><div class="vs-card-h"><p>누가 사는가</p><span>' + subLabel + '</span></div>' +
      (stats ? '<div class="vs-stats vsx-mt0">' + stats + '</div>' : '') +
      '<p class="vs-lbl vsx-sec">기관 안에서 누가 바뀌었나</p>' +
      '<p class="vs-lbl-s">왼쪽 옅은 막대가 어제, 오른쪽이 오늘</p>' +
      '<div class="vsx-pairs">' + flowInstPairs(flow.inst) + '</div></div>';
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
    if (hm > 1530 && hm < 1700) return 'close';   // 15:31~15:39는 close지만 API가 early를 줘 카드가 안 그려진다
    return 'night';
  }

  // close(15:31~16:59)는 메인 곡선(결론·곡선·근거)만 — 17:00 '밤사이 미국 반도체 시황'이 올라오면 곡선은 빠진다(2026-09-17 사용자 결정).
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
        html += '<div class="vs-hero"><p class="vs-eyebrow">🕘 ' + rel + ' ' + d.time + ' vs 오늘 ' + d.time + '</p>' +
          '<h2 class="' + (d.verdict.judge === 'strong' ? 'up' : d.verdict.judge === 'weak' ? 'dn' : '') + '">' + esc(d.verdict.title) + '</h2>' +
          '<p class="vs-sub">' + esc(d.verdict.sub) + '</p></div>';
      }
      // 옛 3칸(오늘 코스피·외국인 누적·주도주 평균)은 LIVE 바·아래 축 카드와 중복이라 뺐다(F2) —
      // 곡선 다음은 heroWhy()의 근거 4줄로 이어진다.
      var ov = chartOverlay(d.kospi.curveY, d.kospi.curveT, rel);
      html += '<div class="vs-card"><div class="vs-legend"><span><i class="t"></i>오늘</span><span><i class="y"></i>' + rel + ' 같은 시각까지</span><span><i class="a"></i><i class="a dn"></i>오늘이 위 · 아래</span><span><i class="b"></i><i class="b dn"></i>차이(오늘−' + rel + ')</span><span class="r">코스피 · 전일 종가 대비</span></div>' +
        '<div class="vs-chartbox">' + ov.left + '<div class="vs-plot">' + chartSvg(d.kospi.curveY, d.kospi.curveT) + ov.plot +
        '<i class="vs-guide" hidden></i><i class="vs-dot y" hidden></i><i class="vs-dot t" hidden></i><div class="vs-tip" hidden></div></div>' + ov.right + '</div>' +
        diffBox(d.kospi.curveY, d.kospi.curveT) +
        '<div class="vs-axis"><span style="left:0%">09:00</span><span style="left:30.77%">11:00</span><span style="left:61.54%">13:00</span><span style="right:0">15:30</span></div>' +
        heroWhy(d, slot) + '</div>';
    }

    // 렌더 순서 — 결론(위 곡선) → 강도 → 주도권 → 수급. 옛 '어제와 달라진 것' 가로 막대 카드는 누가 사는가와 겹쳐 뺐다(2026-09-17).
    if (has('heat')) html += heatCard(d.axes);
    if (has('lead')) html += leadCard(d.axes, d.kospi);

    if (has('flow')) html += flowCard(d.axes, slot);

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

  // 슬롯에 따라 엔드포인트를 고르고(§3.2), pre·weekend는 아예 호출하지 않는다.
  function load() {
    var slot = slotOf(new Date()), url = endpointFor(slot);
    if (!url) { render(null, slot); return; }
    if (document.hidden) return;                       // 백그라운드 탭은 부르지 않는다(2026-08-16 차단 사고)
    fetch(url, { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { render(d, slot); })
      .catch(function () { render(null, slot); });
  }

  window.__vsIntraday = {
    render: render, shouldPoll: shouldPoll, slotOf: slotOf, cardsFor: cardsFor, endpointFor: endpointFor,
    chartSvg: chartSvg, bandRuns: bandRuns, diffSvg: diffSvg, diffPts: diffPts, chartOverlay: chartOverlay, hoverAt: hoverAt,
    heatCard: heatCard, leadCard: leadCard, flowCard: flowCard, miniBars: miniBars, heroWhy: heroWhy, wasKo: wasKo,
    josa: josa,
  };
  if (!root) return;
  load();
  setInterval(load, 60000);
  // 백그라운드에서 열린 탭은 load()가 요청을 건너뛴다 — 보이는 순간 바로 불러와 최대 60초 빈 화면을 없앤다.
  document.addEventListener('visibilitychange', function () { if (!document.hidden) load(); });
})();
