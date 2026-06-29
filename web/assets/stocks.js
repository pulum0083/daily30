// 종목 상세 페이지의 sparkline 렌더를 담당하는 스크립트

// 네비게이션 — 종목 상세는 standalone 페이지로 실제 이동, 허브/섹터는 /stocks/ 해시 라우팅
// 제너레이터가 모든 종목에 /stocks/{code}/ 페이지를 생성하므로 무조건 클린 URL 사용
function goStock(code){location.href='/stocks/'+code+'/';}
function goHub(screen){location.href='/stocks/'+(screen?'#'+screen:'');}
function goBack(){if(history.length>1)history.back();else goHub();}

// 헤더 sparkline 렌더 — Canvas 베지어 방식 (마감 브리핑 drawCloseChart와 동일 스타일)
function drawSparkCanvas(container, closes) {
  if (!closes || closes.length < 2) return;
  // 곡선 하단에 표기할 대략적인 날짜 축 (data-dates가 종가 개수와 일치할 때만)
  var dates = (container.getAttribute('data-dates') || '').split(',').map(function (s) { return s.trim(); }).filter(Boolean);
  var hasDates = dates.length === closes.length;
  var H = hasDates ? 156 : 140;
  // 콘텐츠 폭 기준(패딩 제외) — offsetWidth로 잡으면 캔버스가 컨테이너 패딩을 넘어가 우측이 잘린다
  var cstyle = getComputedStyle(container);
  var W = (container.clientWidth || container.offsetWidth || 600)
        - parseFloat(cstyle.paddingLeft || 0) - parseFloat(cstyle.paddingRight || 0);
  if (!W || W < 50) W = 600;
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
  var pad = { t: 28, b: hasDates ? 24 : 8, l: 10, r: 10 };
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

  // 하단 날짜 축 — 너비에 맞춰 3~6개만 대략적으로 표기(양끝은 안쪽 정렬로 잘림 방지)
  if (hasDates) {
    ctx.font = "600 10px 'Pretendard Variable',Pretendard,sans-serif";
    ctx.fillStyle = '#9CA3AF';
    ctx.textBaseline = 'alphabetic';
    var dy = H - 8;
    var want = Math.max(3, Math.min(6, Math.floor(W / 110)));
    var seen = {};
    for (var t = 0; t < want; t++) {
      var di = Math.round(t * (n - 1) / (want - 1));
      if (seen[di]) continue;
      seen[di] = 1;
      var dx;
      if (di === 0) { ctx.textAlign = 'left'; dx = pad.l; }
      else if (di === n - 1) { ctx.textAlign = 'right'; dx = W - pad.r; }
      else { ctx.textAlign = 'center'; dx = xf(di); }
      ctx.fillText(dates[di], dx, dy);
    }
  }
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

// 오늘 장중 1분봉 곡선 — /api/intraday?code= 실측 데이터로 차트 탭(오늘 장중)에 렌더(데이터 있을 때만 탭 노출·기본 활성화)
// 세션이 '오늘'이면 헤더 시세(현재가·등락률)도 장중 실시간으로 갱신하고, 장중에는 폴링으로 계속 업데이트한다.
(function(){
  var pane=document.getElementById('pane-intra');
  if(!pane) return;
  var code=pane.getAttribute('data-code');
  var pxEl=document.querySelector('.px.num');
  var cgEl=document.querySelector('.cg.num');
  var metaEl=document.querySelector('#hero-stock .meta');
  var prevClose=pxEl?parseFloat((pxEl.textContent||'').replace(/,/g,'')):0; // 직전 거래일 종가(서버 렌더 실측) — 등락률 기준
  var metaOrig=metaEl?metaEl.innerHTML:'';
  var pinsLoaded=false;
  function todayKST(){return new Date(Date.now()+9*3600*1000).toISOString().slice(0,10).replace(/-/g,'');}

  function render(d){
    var vals=(d&&d.minutes)||[];
    if(vals.length<2) return;            // 데이터 없으면 숨김 유지(정합성)
    var times=(d&&d.times)||[];
    var X0=14,X1=626,YT=22,YB=150;
    function t2x(t){var p=(t||'09:00').split(':'),mm=(+p[0])*60+(+p[1]);return X0+(X1-X0)*Math.min(1,Math.max(0,(mm-540)/(930-540)));}
    var lo=Math.min.apply(null,vals),hi=Math.max.apply(null,vals),span=(hi-lo)||1,n=vals.length;
    var useT=times.length===n;  // 실제 시각 있으면 시간축 배치, 없으면 균등 분포(폴백)
    function px2(i){return useT?t2x(times[i]):X0+(X1-X0)*(i/(n-1));}
    var pts=vals.map(function(v,i){var x=px2(i);var y=YB-(YB-YT)*((v-lo)/span);return x.toFixed(1)+','+y.toFixed(1);}).join(' ');
    var up=vals[n-1]>=vals[0], col=up?'#E03131':'#2775ED', last=pts.split(' ').pop().split(',');
    document.getElementById('intra-svg').innerHTML=
      '<line x1="14" y1="150" x2="626" y2="150" stroke="#E5E7EB" stroke-width="1"/>'+
      '<polyline points="'+pts+'" fill="none" stroke="'+col+'" stroke-width="2" stroke-linejoin="round"/>'+
      '<circle cx="'+last[0]+'" cy="'+last[1]+'" r="3.5" fill="'+col+'"/>'+
      '<text x="14" y="170" font-size="10" fill="#9CA3AF">09:00</text><text x="595" y="170" font-size="10" fill="#9CA3AF">15:30</text>';
    // 장중 데이터 확보 → '오늘 장중' 탭 노출 + 기본 활성화
    var tabBtn=document.getElementById('ctab-intra');
    if(tabBtn) tabBtn.style.display='';
    if(!pinsLoaded && window.switchChartTab) window.switchChartTab('pane-intra'); // 최초 1회만 자동 전환(이후 탭 선택 유지)

    // ── 헤더 시세 실시간 갱신 (세션이 오늘일 때만 — 휴장·전일 데이터로 덮어쓰기 방지) ──
    if(d&&d.date===todayKST()&&prevClose>0){
      var cur=vals[n-1], chg=(cur-prevClose)/prevClose*100, u=chg>=0;
      if(pxEl) pxEl.textContent=Math.round(cur).toLocaleString();
      if(cgEl){cgEl.style.color=u?'var(--up)':'var(--dn)';cgEl.textContent=(u?'▲ +':'▼ ')+chg.toFixed(2)+'%';}
      if(metaEl){var lt=times[n-1]||'';metaEl.innerHTML=metaOrig.replace(/(·\s*)\d{2}-\d{2}\s*종가/, '$1오늘 장중 '+lt);}
    }

    // ── 뉴스 핀(movers-why)은 최초 1회만 로드 ──
    if(pinsLoaded) return;
    pinsLoaded=true;
    var coords2=vals.map(function(v,i){return {x:px2(i),y:YB-(YB-YT)*((v-lo)/span)};});
    function yAtX2(x){var b=coords2[0];for(var i=0;i<coords2.length;i++){if(Math.abs(coords2[i].x-x)<Math.abs(b.x-x))b=coords2[i];}return b.y;}
    var dnow=new Date(Date.now()+9*3600*1000).toISOString().slice(0,10);
    fetch('/data/movers-why-'+dnow+'.json').then(function(r){return r.ok?r.json():fetch('/data/movers-why-live.json').then(function(x){return x.ok?x.json():null;});}).then(function(j){
      if(!j||!j.stocks)return;
      var me=j.stocks.filter(function(s){return s.code===code;})[0];
      var evs=(me&&me.events)||[];
      var svgEl=document.getElementById('intra-svg'),add='';
      evs.forEach(function(e,i){var ax=t2x(e.time),ay=yAtX2(ax),f=e.tier==='why'?'#E03131':'#fff',st=e.tier==='why'?'#E03131':'#94A3B8',tc=e.tier==='why'?'#fff':'#64748B';
        var px=Math.min(X1-12,Math.max(X0+12,ax)),up=(ay-41)>=YT&&(ay-31-10)>=0,cy=up?ay-31:ay+31,sy=up?ay-24:ay+24,ty=up?ay-27:ay+35;
        add+='<line x1="'+ax.toFixed(1)+'" y1="'+ay.toFixed(1)+'" x2="'+px.toFixed(1)+'" y2="'+sy.toFixed(1)+'" stroke="'+st+'" stroke-width="1.3"/><circle cx="'+px.toFixed(1)+'" cy="'+cy.toFixed(1)+'" r="10" fill="'+f+'" stroke="'+st+'" stroke-width="1.6"/><text x="'+px.toFixed(1)+'" y="'+ty.toFixed(1)+'" font-size="11" font-weight="800" fill="'+tc+'" text-anchor="middle">'+(i+1)+'</text>';});
      svgEl.innerHTML+=add;
      var tl=document.getElementById('intra-tl');
      if(tl&&evs.length){
        // 좌측 정렬 기준 = 그래프 09:00 지점(viewBox 640 중 X0=14). svg 실제 렌더 너비에 비례해 들여쓰기.
        var sw=(svgEl.getBoundingClientRect().width)||640;
        tl.style.paddingLeft=(14/640*sw).toFixed(1)+'px';
        tl.innerHTML=evs.map(function(e,i){var lbl=e.tier==='why'?'why':'관련',nbg=e.tier==='why'?'background:#E03131;color:#fff;':'background:#fff;color:#64748B;border:1.5px solid #CBD5E1;',tcss=e.tier==='why'?'color:#E03131;background:#FEF2F2;':'color:#64748B;background:#F1F5F9;';
        return '<div style="display:flex;flex-direction:column;align-items:flex-start;text-align:left;gap:3px;padding:10px 0;border-bottom:1px solid #F1F5F9;"><div style="width:20px;height:20px;border-radius:50%;font-size:11px;font-weight:800;display:flex;align-items:center;justify-content:center;'+nbg+'">'+(i+1)+'</div><div style="font-size:11px;font-weight:700;color:#94A3B8;">'+e.time+'</div><div style="font-size:13px;font-weight:700;line-height:1.4;"><a href="'+e.url+'" target="_blank" rel="noopener" style="color:#0F172A;text-decoration:none;">'+e.headline+'</a><span style="font-size:10px;font-weight:800;border-radius:5px;padding:1px 6px;margin-left:6px;'+tcss+'">'+lbl+'</span></div><div style="font-size:12px;color:#334155;">'+e.why+'</div><div style="font-size:11px;color:#94A3B8;">출처 · '+e.source+'</div></div>';}).join(''); }
    }).catch(function(){});
  }

  function tick(){fetch('/api/intraday?code='+code).then(function(r){return r.json();}).then(render).catch(function(){});}
  tick();
  // 장중(09:00~15:35 KST)에만 45초 폴링 — 헤더 시세·곡선 실시간 갱신
  var km=new Date(Date.now()+9*3600*1000),kmin=km.getUTCHours()*60+km.getUTCMinutes();
  if(kmin>=540&&kmin<=935) setInterval(tick,45000);
})();

// 외국인 보유율 스파크라인 — 직선 폴리라인을 부드러운 곡선 + 그라디언트로 재렌더
(function(){
  document.querySelectorAll('.frw svg.sp').forEach(function(svg){
    var pl=svg.querySelector('polyline');
    if(!pl) return;
    var raw=(pl.getAttribute('points')||'').trim().split(/\s+/).map(function(p){
      var xy=p.split(','); return {x:parseFloat(xy[0]),y:parseFloat(xy[1])};
    }).filter(function(p){return !isNaN(p.x)&&!isNaN(p.y);});
    if(raw.length<2) return;
    var W=svg.clientWidth||160, H=36, padT=5, padB=5, n=raw.length;
    var ys=raw.map(function(p){return p.y;});
    var ymin=Math.min.apply(null,ys), ymax=Math.max.apply(null,ys), yspan=(ymax-ymin)||1;
    var pts=raw.map(function(p,i){
      return {x:(i/(n-1))*W, y:padT+((p.y-ymin)/yspan)*(H-padT-padB)};
    });
    var d='M'+pts[0].x.toFixed(1)+','+pts[0].y.toFixed(1);
    for(var i=1;i<n;i++){
      var cx=((pts[i-1].x+pts[i].x)/2).toFixed(1);
      d+=' C'+cx+','+pts[i-1].y.toFixed(1)+' '+cx+','+pts[i].y.toFixed(1)+' '+pts[i].x.toFixed(1)+','+pts[i].y.toFixed(1);
    }
    var col='#2775ED', gid='fo-grad-'+Math.random().toString(36).slice(2,7);
    svg.setAttribute('viewBox','0 0 '+W+' '+H);
    svg.removeAttribute('preserveAspectRatio');
    svg.innerHTML='<defs><linearGradient id="'+gid+'" x1="0" y1="0" x2="0" y2="1">'+
      '<stop offset="0" stop-color="'+col+'" stop-opacity="0.13"/>'+
      '<stop offset="1" stop-color="'+col+'" stop-opacity="0"/></linearGradient></defs>'+
      '<path d="'+d+' L'+W.toFixed(1)+','+H+' L0,'+H+' Z" fill="url(#'+gid+')"/>'+
      '<path d="'+d+'" fill="none" stroke="'+col+'" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>';
  });
})();

// 트랙레코드 ? 툴팁 바인딩 — stocks.js는 defer라 DOM 파싱 후 실행돼 body 끝의 #tr-tip을 항상 찾는다
// (페이지 인라인 스크립트는 #tr-tip보다 먼저 실행돼 바인딩에 실패하므로 여기서 처리)
(function(){
  var btn=document.getElementById('tr-help-btn');
  var tip=document.getElementById('tr-tip');
  if(!btn||!tip) return;
  function move(e){
    var pad=14,w=tip.offsetWidth,h=tip.offsetHeight;
    var x=e.clientX+18,y=e.clientY+14;
    if(x+w+pad>innerWidth) x=e.clientX-w-14;
    if(y+h+pad>innerHeight) y=e.clientY-h-14;
    tip.style.left=Math.max(pad,x)+'px';
    tip.style.top=Math.max(pad,y)+'px';
  }
  btn.addEventListener('mouseenter',function(e){tip.style.display='block';move(e);});
  btn.addEventListener('mousemove',move);
  btn.addEventListener('mouseleave',function(){tip.style.display='none';});
})();

