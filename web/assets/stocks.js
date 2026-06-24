// 종목 상세 페이지의 sparkline 렌더를 담당하는 스크립트

// 네비게이션 — 종목 상세는 standalone 페이지로 실제 이동, 허브/섹터는 /stocks/ 해시 라우팅
// 제너레이터가 모든 종목에 /stocks/{code}/ 페이지를 생성하므로 무조건 클린 URL 사용
function goStock(code){location.href='/stocks/'+code+'/';}
function goHub(screen){location.href='/stocks/'+(screen?'#'+screen:'');}
function goBack(){if(history.length>1)history.back();else goHub();}

// 헤더 sparkline 렌더 — Canvas 베지어 방식 (마감 브리핑 drawCloseChart와 동일 스타일)
function drawSparkCanvas(container, closes) {
  if (!closes || closes.length < 2) return;
  var H = 140;
  var W = container.offsetWidth || 600;
  var dpr = window.devicePixelRatio || 1;
  var canvas = document.createElement('canvas');
  canvas.style.width = W + 'px';
  canvas.style.height = H + 'px';
  canvas.style.display = 'block';
  canvas.width = W * dpr;
  canvas.height = H * dpr;
  container.innerHTML = '';
  container.appendChild(canvas);
  var ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);

  var isUp = closes[closes.length - 1] >= closes[0];
  var color = isUp ? '#E03131' : '#2775ED';
  var pad = { t: 28, b: 8, l: 10, r: 10 };
  var pW = W - pad.l - pad.r, pH = H - pad.t - pad.b;

  var lo = Math.min.apply(null, closes);
  var hi = Math.max.apply(null, closes);
  var margin = (hi - lo) * 0.08 || hi * 0.01;
  var vMin = lo - margin, vMax = hi + margin;
  var range = vMax - vMin || 1;

  var n = closes.length;
  function xf(i) { return pad.l + (i / (n - 1)) * pW; }
  function yf(v) { return pad.t + (1 - (v - vMin) / range) * pH; }

  // 그라디언트 채우기
  var grad = ctx.createLinearGradient(0, pad.t, 0, H - pad.b);
  grad.addColorStop(0, isUp ? 'rgba(224,49,49,.15)' : 'rgba(39,117,237,.15)');
  grad.addColorStop(1, isUp ? 'rgba(224,49,49,.01)' : 'rgba(39,117,237,.01)');

  ctx.beginPath();
  ctx.moveTo(xf(0), yf(closes[0]));
  for (var i = 1; i < n; i++) {
    var cx = (xf(i - 1) + xf(i)) / 2;
    ctx.bezierCurveTo(cx, yf(closes[i - 1]), cx, yf(closes[i]), xf(i), yf(closes[i]));
  }
  ctx.lineTo(xf(n - 1), H - pad.b);
  ctx.lineTo(xf(0), H - pad.b);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();

  // 선
  ctx.beginPath();
  ctx.moveTo(xf(0), yf(closes[0]));
  for (var j = 1; j < n; j++) {
    var cxj = (xf(j - 1) + xf(j)) / 2;
    ctx.bezierCurveTo(cxj, yf(closes[j - 1]), cxj, yf(closes[j]), xf(j), yf(closes[j]));
  }
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.lineJoin = 'round';
  ctx.stroke();

  // 고점·저점 라벨 (halo 테두리로 가독성 확보)
  function drawLabel(x, y, label, lblColor) {
    var isDark = document.documentElement.classList.contains('dark');
    var halo = isDark ? 'rgba(28,29,31,.92)' : 'rgba(255,255,255,.95)';
    ctx.font = "bold 11px 'Pretendard Variable',Pretendard,sans-serif";
    ctx.textBaseline = 'alphabetic';
    var tw = ctx.measureText(label).width;
    var lx = Math.min(Math.max(x, tw / 2 + pad.l), W - tw / 2 - pad.r);
    var labelY = y < pad.t + 16 ? y + 18 : y - 8;
    ctx.lineJoin = 'round';
    ctx.lineWidth = 3;
    ctx.textAlign = 'center';
    ctx.strokeStyle = halo;
    ctx.strokeText(label, lx, labelY);
    ctx.fillStyle = lblColor;
    ctx.fillText(label, lx, labelY);
  }

  if (hi !== lo) {
    var hiIdx = closes.indexOf(hi), loIdx = closes.indexOf(lo);
    var upColor = '#E03131', dnColor = '#2775ED';
    // 고점 마커
    ctx.beginPath();
    ctx.arc(xf(hiIdx), yf(hi), 3.5, 0, Math.PI * 2);
    ctx.fillStyle = isUp ? upColor : dnColor;
    ctx.fill();
    drawLabel(xf(hiIdx), yf(hi), '최근 고점 ' + hi.toLocaleString(), isUp ? upColor : dnColor);
    // 저점 마커
    ctx.beginPath();
    ctx.arc(xf(loIdx), yf(lo), 3.5, 0, Math.PI * 2);
    ctx.fillStyle = isUp ? dnColor : upColor;
    ctx.fill();
    drawLabel(xf(loIdx), yf(lo), '최근 저점 ' + lo.toLocaleString(), isUp ? dnColor : upColor);
  }

  // 현재가 끝점 도트
  ctx.beginPath();
  ctx.arc(xf(n - 1), yf(closes[n - 1]), 4, 0, Math.PI * 2);
  ctx.fillStyle = '#fff';
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.fill();
  ctx.stroke();
}

document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('[data-spark]').forEach(function(container) {
    var raw = (container.getAttribute('data-spark') || '').trim();
    if (!raw) return;
    var closes = raw.split(',').map(Number).filter(function(v) { return !isNaN(v) && isFinite(v); });
    drawSparkCanvas(container, closes);
  });
  // 리사이즈 대응
  var resizeTimer;
  window.addEventListener('resize', function() {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function() {
      document.querySelectorAll('[data-spark]').forEach(function(container) {
        var raw = (container.getAttribute('data-spark') || '').trim();
        if (!raw) return;
        var closes = raw.split(',').map(Number).filter(function(v) { return !isNaN(v) && isFinite(v); });
        drawSparkCanvas(container, closes);
      });
    }, 100);
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

  // 1. 수급 동향 — 5일 외국인·기관 순매수 (중앙 기준 다이버징 바)
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
      // 최대 절대 순매수 (다이버징 스케일용)
      var maxAbs = 0;
      d.days.forEach(function (day) {
        maxAbs = Math.max(maxAbs,
          Math.abs(day.foreignBuy - day.foreignSell),
          Math.abs(day.institutionBuy - day.institutionSell));
      });
      maxAbs = maxAbs || 1;
      function divRow(label, net) {
        var buy = net >= 0;
        var w = Math.min(Math.abs(net) / maxAbs * 50, 50).toFixed(1);
        var cls = buy ? 'buy' : 'sell';
        var valCls = buy ? 'up' : 'dn';
        var sign = buy ? '+' : '';
        return '<div class="sd-row"><span class="sd-lbl">' + label + '</span>'
          + '<div class="sd-track"><div class="sd-zero"></div>'
          + '<div class="sd-fill ' + cls + '" style="width:' + w + '%"></div></div>'
          + '<span class="sd-val ' + valCls + '">' + sign + fmt만(net) + '</span></div>';
      }
      var days = d.days.map(function (day) {
        return '<div class="sd-day"><div class="sd-day-date">' + day.date + '</div>'
          + divRow('외', day.foreignBuy - day.foreignSell)
          + divRow('기', day.institutionBuy - day.institutionSell)
          + '</div>';
      }).join('');

      function sumBox(name, net) {
        var up = net >= 0;
        var cls = up ? 'up' : 'dn';
        var sign = up ? '+' : '';
        var tag = up ? '순매수' : '순매도';
        return '<div class="sd-sum-box"><div class="sd-sum-top">'
          + '<span class="sd-sum-name">' + name + ' · 5일</span>'
          + '<span class="sd-sum-tag ' + cls + '">' + tag + '</span></div>'
          + '<div class="sd-sum-val ' + cls + '">' + sign + fmt만(net) + '</div></div>';
      }
      body.innerHTML = '<div class="sd-sum">'
        + sumBox('외국인', d.summary.foreignNetBuy) + sumBox('기관', d.summary.institutionNetBuy)
        + '</div><div class="sd-axis"><span>◀ 순매도</span><span>순매수 ▶</span></div>' + days;
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

  // 3. 영업이익 분기 추이 (컬럼 차트 — 값 라벨·베이스라인·추정 해치)
  fetch('/chips/api/financials?ticker=' + ticker)
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if (!d.quarters || d.quarters.length === 0) return;
      // 영업이익 있는 분기만, 최근 8개
      var qs = d.quarters.filter(function (q) { return q.operatingIncome !== null; }).slice(-8);
      if (qs.length === 0) return;
      var sec = document.getElementById('sec-financials');
      var body = document.getElementById('financials-body');
      var absMax = Math.max.apply(null, qs.map(function (q) { return Math.abs(q.operatingIncome); })) || 1;
      var BARH = 140; // px
      var bars = qs.map(function (q) {
        var v = q.operatingIncome;
        var est = q.isEstimate;
        // 최소 14px 보장 — 작은 분기도 라벨과 함께 읽히도록
        var h = Math.max(Math.round(Math.abs(v) / absMax * BARH), 14);
        return '<div class="fin-col"><span class="fin-cap' + (est ? ' est' : '') + '">'
          + fmtAmt(v) + (est ? '(E)' : '') + '</span>'
          + '<div class="fin-bar ' + (est ? 'est' : 'actual') + '" style="height:' + h + 'px"></div></div>';
      }).join('');
      var xs = qs.map(function (q) {
        return '<span class="fin-x' + (q.isEstimate ? ' est' : '') + '">'
          + q.quarter.replace('Q', '<br>Q') + '</span>';
      }).join('');
      body.innerHTML = '<div class="fin-chart">' + bars + '</div>'
        + '<div class="fin-xrow">' + xs + '</div>'
        + '<div class="fin-foot"><div class="fin-legend">'
        + '<span><i style="background:var(--up)"></i>확정 실적</span>'
        + '<span><i class="est"></i>컨센서스 추정</span></div></div>';
      sec.style.display = '';
    }).catch(function () {});
})();

