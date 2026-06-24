// 종목 상세 페이지의 sparkline 렌더를 담당하는 스크립트

// 네비게이션 — 종목 상세는 standalone 페이지로 실제 이동, 허브/섹터는 /stocks/ 해시 라우팅
// 제너레이터가 모든 종목에 /stocks/{code}/ 페이지를 생성하므로 무조건 클린 URL 사용
function goStock(code){location.href='/stocks/'+code+'/';}
function goHub(screen){location.href='/stocks/'+(screen?'#'+screen:'');}
function goBack(){if(history.length>1)history.back();else goHub();}

// 헤더 sparkline 렌더 — [data-spark] 속성의 쉼표 구분 종가 배열로 SVG 폴리라인 생성
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('[data-spark]').forEach(function(container) {
    var raw = (container.getAttribute('data-spark') || '').trim();
    if (!raw) return;
    // NaN/Infinity만 제거 — 도메인상 가격은 양수지만 0을 무시하면 안 됨
    var closes = raw.split(',').map(Number).filter(function(v) { return !isNaN(v) && isFinite(v); });
    if (closes.length < 2) return;

    var W = 740, H = 140, PAD = 4;
    var lo = Math.min.apply(null, closes);
    var hi = Math.max.apply(null, closes);
    var range = hi - lo || 1;
    var isUp = closes[closes.length - 1] >= closes[0];
    var color = isUp ? '#E03131' : '#2775ED';
    var gradId = 'spark-grad-' + Math.random().toString(36).slice(2);

    var n = closes.length;
    var pts = closes.map(function(v, i) {
      var x = (n === 1) ? W / 2 : (i / (n - 1)) * (W - PAD * 2) + PAD;
      var y = PAD + (1 - (v - lo) / range) * (H - PAD * 2);
      return x.toFixed(1) + ',' + y.toFixed(1);
    });

    var lastPt = pts[pts.length - 1].split(',');
    var firstPt = pts[0].split(',');

    // 마지막점 좌표
    var lx = parseFloat(lastPt[0]);
    var ly = parseFloat(lastPt[1]);
    // 첫번째점 좌표
    var fx = parseFloat(firstPt[0]);

    var areaPoints = pts.join(' ') + ' ' + lx.toFixed(1) + ',' + (H - PAD) + ' ' + fx.toFixed(1) + ',' + (H - PAD);

    // 실측 고점·저점 라벨 위치 계산
    var hiIdx = closes.indexOf(hi);
    var loIdx = closes.indexOf(lo);
    var hiPt = pts[hiIdx].split(',');
    var loPt = pts[loIdx].split(',');
    var hix = parseFloat(hiPt[0]);
    var hiy = parseFloat(hiPt[1]);
    var loxPt = parseFloat(loPt[0]);
    var loyPt = parseFloat(loPt[1]);
    var upColor = '#E03131';
    var dnColor = '#2775ED';
    var hiColor = isUp ? upColor : dnColor;
    var loColor = isUp ? dnColor : upColor;
    var hiLabel = '최근 고점 ' + hi.toLocaleString();
    var loLabel = '최근 저점 ' + lo.toLocaleString();
    // 라벨이 SVG 경계를 벗어나지 않도록 앵커 결정 (좌측 30% → start, 나머지 → end)
    var hiAnchor = hix < W * 0.3 ? 'start' : 'end';
    var loAnchor = loxPt < W * 0.3 ? 'start' : 'end';
    var hiDy = hiy < 18 ? 14 : -6;
    var loDy = loyPt > H - 18 ? -6 : 14;
    // 평탄(전 구간 동일가)하면 고점·저점이 한 점에 겹치므로 라벨 생략
    var labelSvg = hi === lo ? '' :
        '<text x="' + hix.toFixed(1) + '" y="' + (hiy + hiDy).toFixed(1) + '" text-anchor="' + hiAnchor + '" fill="' + hiColor + '" font-size="11" font-weight="700" font-family="inherit">' + hiLabel + '</text>'
      + '<text x="' + loxPt.toFixed(1) + '" y="' + (loyPt + loDy).toFixed(1) + '" text-anchor="' + loAnchor + '" fill="' + loColor + '" font-size="11" font-weight="700" font-family="inherit">' + loLabel + '</text>';

    var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none" style="width:100%;height:140px;display:block;overflow:visible;">'
      + '<defs><linearGradient id="' + gradId + '" x1="0" y1="0" x2="0" y2="1">'
      + '<stop offset="0%" stop-color="' + color + '" stop-opacity="0.18"/>'
      + '<stop offset="100%" stop-color="' + color + '" stop-opacity="0"/>'
      + '</linearGradient></defs>'
      + '<polygon points="' + areaPoints + '" fill="url(#' + gradId + ')"/>'
      + '<polyline fill="none" stroke="' + color + '" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" points="' + pts.join(' ') + '"/>'
      + '<circle cx="' + fx.toFixed(1) + '" cy="' + firstPt[1] + '" r="3.5" fill="#fff" stroke="#9CA3AF" stroke-width="2"/>'
      + '<circle cx="' + lx.toFixed(1) + '" cy="' + ly.toFixed(1) + '" r="3.5" fill="#fff" stroke="' + color + '" stroke-width="2"/>'
      + labelSvg
      + '</svg>';

    container.innerHTML = svg;
  });
});

// ── chipboard 실시간 데이터 (수급·목표주가·영업이익) ──
(function () {
  var meta = document.getElementById('chips-meta');
  if (!meta) return;
  var ticker = meta.getAttribute('data-chips-ticker');
  if (!ticker) return;

  function fmt만(v) {
    var abs = Math.abs(v);
    if (abs >= 10000) return (v / 10000).toFixed(1) + '만';
    return v.toLocaleString();
  }
  function fmtAmt(v) { // 억원 단위 → 조 or 억
    if (v === null || v === undefined) return '—';
    var abs = Math.abs(v);
    if (abs >= 10000) return (v / 10000).toFixed(1) + '조';
    return Math.round(v).toLocaleString() + '억';
  }

  // 1. 수급 동향
  fetch('/chips/api/supply-demand?ticker=' + ticker)
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if (!d.days || d.days.length === 0) return;
      var sec = document.getElementById('sec-supply');
      var body = document.getElementById('supply-body');
      var upd = document.getElementById('supply-updated');
      if (d.updatedAt) {
        var dt = new Date(d.updatedAt);
        upd.textContent = (dt.getMonth() + 1) + '/' + dt.getDate() + ' 기준 5일';
      }
      // 최대값 (바 스케일용)
      var maxVal = 0;
      d.days.forEach(function (day) {
        ['foreignBuy', 'foreignSell', 'institutionBuy', 'institutionSell'].forEach(function (k) {
          if (day[k] > maxVal) maxVal = day[k];
        });
      });
      maxVal = maxVal || 1;
      var rows = d.days.map(function (day) {
        function bar(buy, sell, label) {
          var net = buy - sell;
          var isUp = net >= 0;
          var fillVal = Math.abs(net);
          var pct = Math.min(fillVal / maxVal * 100, 100).toFixed(1);
          var cls = isUp ? 'buy' : 'sell';
          var valCls = isUp ? 'up' : 'dn';
          var sign = isUp ? '+' : '';
          return '<div class="sup5-bar">'
            + '<span class="sup5-label">' + label + '</span>'
            + '<div class="sup5-track"><div class="sup5-fill ' + cls + '" style="width:' + pct + '%"></div></div>'
            + '<span class="sup5-val ' + valCls + '">' + sign + fmt만(net) + '</span>'
            + '</div>';
        }
        return '<div class="sup5-row">'
          + '<span class="sup5-date">' + day.date + '</span>'
          + '<div class="sup5-bars">'
          + bar(day.foreignBuy, day.foreignSell, '외국인')
          + bar(day.institutionBuy, day.institutionSell, '기관')
          + '</div></div>';
      }).join('');

      var fNet = d.summary.foreignNetBuy;
      var iNet = d.summary.institutionNetBuy;
      function sumBox(label, net) {
        var cls = net >= 0 ? 'up' : 'dn';
        var sign = net >= 0 ? '+' : '';
        return '<div class="sup5-sum-box">'
          + '<div class="sup5-sum-label">' + label + ' 5일 순매수</div>'
          + '<div class="sup5-sum-val ' + cls + '">' + sign + fmt만(net) + '</div>'
          + '</div>';
      }
      body.innerHTML = rows
        + '<div class="sup5-summary">' + sumBox('외국인', fNet) + sumBox('기관', iNet) + '</div>';
      sec.style.display = '';
    }).catch(function () {});

  // 2. 증권사 목표주가
  fetch('/chips/api/analyst-targets?ticker=' + ticker)
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if (!d || d.length === 0) return;
      var sec = document.getElementById('sec-targets');
      var body = document.getElementById('targets-body');
      var avgEl = document.getElementById('targets-avg');
      var prices = d.filter(function (t) { return t.targetPrice; }).map(function (t) { return t.targetPrice; });
      var avg = prices.length ? Math.round(prices.reduce(function (a, b) { return a + b; }, 0) / prices.length) : null;
      var curPrice = parseFloat(document.querySelector('.px.num')?.textContent.replace(/,/g, '')) || 0;
      if (avg) {
        var upside = curPrice ? ((avg - curPrice) / curPrice * 100).toFixed(1) : null;
        var upsideCls = upside >= 0 ? 'up' : 'dn';
        var upsideSign = upside >= 0 ? '+' : '';
        avgEl.innerHTML = '평균 목표가 <b class="num" style="color:var(--ink)">' + avg.toLocaleString() + '</b>'
          + (upside !== null ? ' <span class="' + upsideCls + '">(' + upsideSign + upside + '%)</span>' : '');
        body.innerHTML = '<div class="tgt-avg">'
          + '<span class="tgt-avg-price">' + avg.toLocaleString() + '</span>'
          + '<span class="tgt-avg-label">컨센서스 평균</span>'
          + (upside !== null ? '<span class="tgt-avg-upside ' + upsideCls + '">' + upsideSign + upside + '%</span>' : '')
          + '</div>';
      }
      var rows = d.slice(0, 8).map(function (t) {
        var opCls = t.opinion === 'BUY' ? '' : 'hold';
        return '<div class="tgt-row">'
          + '<span class="tgt-firm">' + t.firm + '</span>'
          + '<span class="tgt-price num">' + (t.targetPrice ? t.targetPrice.toLocaleString() : '—') + '</span>'
          + '<span class="tgt-op ' + opCls + '">' + (t.opinion || '—') + '</span>'
          + '<span class="tgt-date">' + (t.date || '') + '</span>'
          + '</div>';
      }).join('');
      body.innerHTML = (body.innerHTML || '') + rows;
      sec.style.display = '';
    }).catch(function () {});

  // 3. 영업이익 추이
  fetch('/chips/api/financials?ticker=' + ticker)
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if (!d.quarters || d.quarters.length === 0) return;
      // 영업이익 있는 분기만, 최근 8개
      var qs = d.quarters.filter(function (q) { return q.operatingIncome !== null; }).slice(-8);
      if (qs.length === 0) return;
      var sec = document.getElementById('sec-financials');
      var body = document.getElementById('financials-body');
      var vals = qs.map(function (q) { return q.operatingIncome; });
      var absMax = Math.max.apply(null, vals.map(Math.abs)) || 1;
      var BARH = 80; // px
      var bars = qs.map(function (q) {
        var v = q.operatingIncome;
        var isEst = q.isEstimate;
        var isPos = v >= 0;
        var pct = Math.min(Math.abs(v) / absMax * 100, 100).toFixed(1);
        var h = Math.max(Math.round(Math.abs(v) / absMax * BARH), 2);
        var cls = isEst ? (isPos ? 'estimate' : 'neg-est') : (isPos ? 'positive' : 'negative');
        return '<div class="fin-bar-wrap">'
          + '<div class="fin-val ' + (isPos ? 'up' : 'dn') + '">' + fmtAmt(v) + '</div>'
          + '<div class="fin-bar ' + cls + '" style="height:' + h + 'px"></div>'
          + '<div class="fin-qx">' + q.quarter.replace('Q', '<br>Q') + '</div>'
          + '</div>';
      }).join('');
      body.innerHTML = '<div class="fin-bars">' + bars + '</div>'
        + '<div class="fin-legend">'
        + '<span><i style="background:var(--up)"></i>실적</span>'
        + '<span><i style="background:var(--up);opacity:.45;border:1px dashed var(--up)"></i>추정</span>'
        + '</div>';
      sec.style.display = '';
    }).catch(function () {});
})();

// 실적 차트 툴팁 (body-fixed — .sc overflow:hidden 우회)
(function(){
  const tt = document.createElement('div');
  tt.className = 'qf-tt';
  tt.style.display = 'none';
  document.body.appendChild(tt);
  document.querySelectorAll('#qf-earnings .q').forEach(function(q) {
    q.addEventListener('mouseenter', function() {
      const r = q.getBoundingClientRect();
      tt.innerHTML = '<b>' + q.dataset.qx + '</b>'
        + '<span class="tt-rev">매출&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;' + q.dataset.rev + '조원</span><br>'
        + '<span class="tt-op">영업이익&nbsp;' + q.dataset.op + '조원</span>';
      tt.style.display = 'block';
      tt.style.left = (r.left + r.width / 2) + 'px';
      tt.style.top  = (r.top - 6) + 'px';
    });
    q.addEventListener('mouseleave', function() { tt.style.display = 'none'; });
  });
})();

