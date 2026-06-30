// 종목 상세 페이지의 sparkline 렌더를 담당하는 스크립트

// ── 미국 상세 전용: 원화/달러 전환 컨트롤러 ──
// 모든 표시 가격은 USD가 기준값. KRW 선택 시 환율(/api/market forex)로 곱해 표기한다.
var USCUR = (function(){
  var cur='usd', fx=null, subs=[];
  function emit(){ subs.forEach(function(f){ try{f();}catch(e){} }); }
  return {
    get cur(){ return cur; },
    get fx(){ return fx; },
    isKRW:function(){ return cur==='krw' && !!fx; },
    setCur:function(c){ cur=c; emit(); },
    setFx:function(v){ fx=v; emit(); },
    onChange:function(f){ subs.push(f); },
    // USD 값 → 가격 표기(통화기호 포함). 원화=정수+원, 달러=$소수2자리
    money:function(vUsd){ return (cur==='krw'&&fx) ? (Math.round(vUsd*fx).toLocaleString()+'원') : ('$'+vUsd.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})); },
    // USD 값 → 라벨용(달러는 기호 없이 숫자만 — 기존 라벨 스타일 유지)
    num:function(vUsd){ return (cur==='krw'&&fx) ? (Math.round(vUsd*fx).toLocaleString()+'원') : vUsd.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}); }
  };
})();
window.__USCUR = USCUR;

// 토글 배선(미국 상세에만 #cur-toggle 존재) + 환율 로드 + 20일 종가 스파크 통화 반영
(function(){
  var tg=document.getElementById('cur-toggle');
  if(!tg) return;
  fetch('/api/market',{cache:'no-store'}).then(function(r){return r.ok?r.json():null;}).then(function(m){
    if(m&&m.forex&&typeof m.forex.price==='number'){ USCUR.setFx(m.forex.price); tg.style.display=''; }
  }).catch(function(){});
  tg.querySelectorAll('button').forEach(function(b){
    b.addEventListener('click',function(){
      tg.querySelectorAll('button').forEach(function(x){ x.classList.toggle('on', x===b); });
      USCUR.setCur(b.getAttribute('data-cur'));
    });
  });
  // 20일 종가 스파크: data-spark를 표시통화 값으로 교체 후 재그리기 (원본 USD는 data-spark-usd에 보존)
  USCUR.onChange(function(){
    document.querySelectorAll('#pane-spark [data-spark]').forEach(function(c){
      if(!c.getAttribute('data-spark-usd')) c.setAttribute('data-spark-usd', c.getAttribute('data-spark')||'');
      var usd=(c.getAttribute('data-spark-usd')||'').split(',').map(Number).filter(function(v){return isFinite(v);});
      if(usd.length<2) return;
      var disp=USCUR.isKRW()? usd.map(function(v){return Math.round(v*USCUR.fx);}) : usd;
      c.setAttribute('data-spark', disp.join(','));
      if(typeof drawSparkCanvas==='function') drawSparkCanvas(c, disp);
    });
  });
})();

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

// 오늘 장중 1분봉 곡선 — /api/intraday?code= 실측 데이터를 20일 종가 스파크라인과 동일한 스타일
// (그라디언트 채움 + 베지어 곡선 + 장중 고점·저점 라벨 + 끝점 도트 + 마우스오버 툴팁)로 렌더.
// 세션이 '오늘'이면 헤더 시세(현재가·등락률)도 장중 실시간으로 갱신하고, 장중에는 폴링으로 계속 업데이트한다.
(function(){
  var pane=document.getElementById('pane-intra');
  if(!pane) return;
  var code=pane.getAttribute('data-code');
  var ticker=pane.getAttribute('data-ticker');
  var isUS=!!ticker, idKey=isUS?ticker:(code||'');   // 그라디언트 id(gid)용 키
  var apiURL=isUS?('/api/intraday?us='+encodeURIComponent(ticker)):('/api/intraday?code='+code);
  var pxEl=document.querySelector('.px.num');
  var cgEl=document.querySelector('.cg.num');
  var metaEl=document.querySelector('#hero-stock .meta');
  var prevClose=pxEl?parseFloat((pxEl.textContent||'').replace(/[^0-9.\-]/g,'')):0; // 직전 거래일 종가(서버 렌더 실측) — 등락률 기준 ($·콤마 제거)
  var metaOrig=metaEl?metaEl.innerHTML:'';
  var X0=14,X1=626,YT=26,YB=148; // viewBox 640×180 기준 플롯 영역
  function t2x(t){var p=(t||'09:00').split(':'),mm=(+p[0])*60+(+p[1]);return X0+(X1-X0)*Math.min(1,Math.max(0,(mm-540)/(930-540)));}
  // 가격 표기: 미국=통화 컨트롤러(원화/달러), 국내=정수+콤마
  function fmtPx(v){ return isUS ? USCUR.money(v) : Math.round(v).toLocaleString(); }
  function fmtNum(v){ return isUS ? USCUR.num(v) : Math.round(v).toLocaleString(); }
  var headerUsd = isUS ? prevClose : 0;   // 헤더 가격의 USD 기준값(통화 전환 시 재포맷)
  function applyHeaderCurrency(){ if(isUS && pxEl && headerUsd) pxEl.textContent=fmtPx(headerUsd); }
  var pinsLoaded=false, pinsHTML='', lastCoords=[], lastTimes=[], lastVals=[], lastCol='#E03131', hoverBound=false;
  function todayKST(){return new Date(Date.now()+9*3600*1000).toISOString().slice(0,10).replace(/-/g,'');}
  // 거래일 'YYYYMMDD' → 'M/D(요일)' (장 마감 후 '오늘 장중' 대체 표기)
  function fmtTradeDate(ymd){
    ymd=String(ymd||''); if(ymd.length<8) return '';
    var mo=+ymd.slice(4,6), da=+ymd.slice(6,8);
    var dt=new Date(+ymd.slice(0,4), mo-1, da);
    if(isNaN(dt.getTime())) return '';
    var w=['일','월','화','수','목','금','토'][dt.getDay()];
    return mo+'/'+da+'('+w+')';
  }

  // ── 라이브 여부·세션 (현재 시각 기준) ──
  // 미국: ET 04:00~20:00(프리~애프터) / 국내: KST 09:00~15:35
  function etNowMin(){var s=new Date().toLocaleTimeString('en-US',{timeZone:'America/New_York',hour12:false,hour:'2-digit',minute:'2-digit'}).split(':');return (parseInt(s[0],10)%24)*60+parseInt(s[1],10);}
  var nowMin = isUS
    ? etNowMin()
    : (function(){var k=new Date(Date.now()+9*3600*1000);return k.getUTCHours()*60+k.getUTCMinutes();})();
  var isLive = isUS ? (nowMin>=240&&nowMin<=1200) : (nowMin>=540&&nowMin<=935);
  // 현재 미국 세션 구간 (라이브 아닐 땐 본장 기준)
  function curSeg(){ if(!isLive) return 'regular'; var m=etNowMin(); return m<570?'pre':(m<960?'regular':'post'); }
  function segLabel(seg){ return seg==='pre'?'프리장':(seg==='post'?'애프터장':'오늘 장중'); }
  function liveLabel(){
    if(isUS){var s=curSeg();var nm=s==='pre'?'프리장':(s==='post'?'애프터장':'정규장');return 'LIVE · '+nm+' · 20초 갱신';}
    return 'LIVE · 장중 · 45초 갱신';
  }

  // ── 첫 로드 시 한 번만 탭을 결정 → '20일 종가'에서 '오늘 장중'으로 튕기는 현상 제거 ──
  var decided=false;
  function decide(showIntra){
    if(decided) return; decided=true;
    var ld=document.getElementById('chart-loading'); if(ld) ld.style.display='none';
    var tb=document.getElementById('ctabs'); if(tb) tb.style.visibility='';
    if(showIntra){
      var bi=document.getElementById('ctab-intra'); if(bi) bi.style.display='';
      if(window.switchChartTab) window.switchChartTab('pane-intra');
      if(isLive){var lv=document.getElementById('intra-live');if(lv){var tx=document.getElementById('intra-live-tx');if(tx)tx.textContent=liveLabel();lv.style.display='';}}
    } else {
      if(window.switchChartTab) window.switchChartTab('pane-spark');
    }
  }

  // 마우스오버 툴팁 — svg 위 가이드선·도트 + 시각·가격 표시 (틱 사이 데이터는 last* 클로저로 공유)
  function bindHover(){
    if(hoverBound) return; hoverBound=true;
    var svg=document.getElementById('intra-svg'); if(!svg) return;
    var wrap=svg.parentNode; wrap.style.position='relative';
    var tip=document.createElement('div'); tip.id='intra-tip';
    tip.style.cssText='position:absolute;display:none;pointer-events:none;background:var(--ink,#1C1D1F);color:#fff;font-size:11px;font-weight:700;padding:4px 8px;border-radius:5px;white-space:nowrap;transform:translate(-50%,-100%);z-index:6;';
    wrap.appendChild(tip);
    svg.addEventListener('mousemove',function(ev){
      if(!lastCoords.length) return;
      var rect=svg.getBoundingClientRect();
      var vbx=(ev.clientX-rect.left)/rect.width*640;
      var best=0,bd=1e9; for(var i=0;i<lastCoords.length;i++){var dx=Math.abs(lastCoords[i].x-vbx);if(dx<bd){bd=dx;best=i;}}
      var c=lastCoords[best];
      var g=document.getElementById('intra-hover');
      if(g) g.innerHTML='<line x1="'+c.x.toFixed(1)+'" y1="'+YT+'" x2="'+c.x.toFixed(1)+'" y2="'+YB+'" stroke="#CBD5E1" stroke-width="1" stroke-dasharray="3 3"/>'+
        '<circle cx="'+c.x.toFixed(1)+'" cy="'+c.y.toFixed(1)+'" r="4" fill="#fff" stroke="'+lastCol+'" stroke-width="2"/>';
      var wr=wrap.getBoundingClientRect();
      tip.style.left=(rect.left+c.x/640*rect.width-wr.left)+'px';
      tip.style.top=(rect.top+c.y/180*rect.height-wr.top-10)+'px';
      tip.style.display='';
      tip.textContent=(lastTimes[best]||'')+' · '+fmtNum(lastVals[best]);
    });
    svg.addEventListener('mouseleave',function(){tip.style.display='none';var g=document.getElementById('intra-hover');if(g)g.innerHTML='';});
  }

  function smoothPath(co){var d='M'+co[0].x.toFixed(1)+','+co[0].y.toFixed(1);for(var i=1;i<co.length;i++){var mx=((co[i-1].x+co[i].x)/2).toFixed(1);d+=' C'+mx+','+co[i-1].y.toFixed(1)+' '+mx+','+co[i].y.toFixed(1)+' '+co[i].x.toFixed(1)+','+co[i].y.toFixed(1);}return d;}

  function render(d){
    var vals=(d&&d.minutes)||[];
    if(vals.length<2){ decide(false); return; }   // 장중 데이터 없음 → 20일 종가 먼저 표시
    var times=(d&&d.times)||[];
    var seg='regular', tsv=null;
    if(isUS){
      // 현재 세션 구간만 표시 (프리장/본장/애프터 분리) — 프리장 데이터가 본장에 섞이지 않게
      seg=curSeg();
      var sess=(d&&d.sessions)||[], tsa=(d&&d.ts)||[], idx=[];
      for(var k=0;k<vals.length;k++){ if(sess[k]===seg) idx.push(k); }
      if(idx.length<2){ idx=[]; for(var k2=0;k2<vals.length;k2++) idx.push(k2); } // 구간 데이터 부족 시 전체
      vals=idx.map(function(i){return d.minutes[i];});
      times=idx.map(function(i){return d.times[i];});
      tsv=idx.map(function(i){return tsa[i];});
      // 탭 라벨/라이브 배지 — 미국 세션 라벨 갱신
      var lvtx=document.getElementById('intra-live-tx'); if(lvtx&&isLive) lvtx.textContent=liveLabel();
    }
    // 탭 라벨 — 라이브: 세션명(오늘 장중/프리장/애프터장) · 장 마감 후: 거래일 날짜 M/D(요일)
    var ci=document.getElementById('ctab-intra');
    if(ci) ci.textContent = isLive ? segLabel(seg) : (fmtTradeDate(d&&d.date) || segLabel(seg));
    var n=vals.length;
    if(n<2){ decide(false); return; }
    var useT=times.length===n;
    // 미국: epoch(ts)로 x 배치 → KST 자정 넘김에도 정렬 안정 / 국내: 09:00~15:30 고정 프레임(t2x)
    var wlo=0,whi=1;
    if(isUS&&tsv){wlo=Math.min.apply(null,tsv);whi=Math.max.apply(null,tsv);}
    function px2(i){
      if(isUS&&tsv){return X0+(X1-X0)*((tsv[i]-wlo)/((whi-wlo)||1));}
      return useT?t2x(times[i]):X0+(X1-X0)*(i/(n-1));
    }
    var lo=Math.min.apply(null,vals),hi=Math.max.apply(null,vals);
    var margin=(hi-lo)*0.10||hi*0.005, vMin=lo-margin, vMax=hi+margin, range=(vMax-vMin)||1;
    function yf(v){return YT+(1-(v-vMin)/range)*(YB-YT);}
    var coords=vals.map(function(v,i){return {x:px2(i),y:yf(v)};});
    var up=vals[n-1]>=vals[0], col=up?'#E03131':'#2775ED';
    lastCoords=coords; lastTimes=times; lastVals=vals; lastCol=col;

    var isDark=document.documentElement.classList.contains('dark');
    var halo=isDark?'#1C1D1F':'#fff';
    var gid='ig-'+idKey, line=smoothPath(coords);
    function labelTxt(x,y,txt,c){
      var lx=Math.min(Math.max(x,X0+48),X1-48), ly=y<YT+14?y+16:y-9;
      return '<text x="'+lx.toFixed(1)+'" y="'+ly.toFixed(1)+'" font-size="11" font-weight="700" text-anchor="middle" fill="'+c+'" stroke="'+halo+'" stroke-width="3" paint-order="stroke" style="stroke-linejoin:round;">'+txt+'</text>';
    }
    var svgHTML=
      '<defs><linearGradient id="'+gid+'" x1="0" y1="0" x2="0" y2="1">'+
        '<stop offset="0" stop-color="'+col+'" stop-opacity="0.15"/><stop offset="1" stop-color="'+col+'" stop-opacity="0.01"/></linearGradient></defs>'+
      '<line x1="'+X0+'" y1="'+YB+'" x2="'+X1+'" y2="'+YB+'" stroke="#E5E7EB" stroke-width="1"/>'+
      '<path d="'+line+' L'+coords[n-1].x.toFixed(1)+','+YB+' L'+coords[0].x.toFixed(1)+','+YB+' Z" fill="url(#'+gid+')"/>'+
      '<path d="'+line+'" fill="none" stroke="'+col+'" stroke-width="2" stroke-linejoin="round"/>';
    if(hi!==lo){
      var hiI=vals.indexOf(hi), loI=vals.indexOf(lo), hc=up?'#E03131':'#2775ED', lc=up?'#2775ED':'#E03131';
      svgHTML+='<circle cx="'+coords[hiI].x.toFixed(1)+'" cy="'+coords[hiI].y.toFixed(1)+'" r="3.5" fill="'+hc+'"/>'+labelTxt(coords[hiI].x,coords[hiI].y,'장중 고점 '+fmtNum(hi),hc)+
        '<circle cx="'+coords[loI].x.toFixed(1)+'" cy="'+coords[loI].y.toFixed(1)+'" r="3.5" fill="'+lc+'"/>'+labelTxt(coords[loI].x,coords[loI].y,'장중 저점 '+fmtNum(lo),lc);
    }
    // x축 라벨: 미국=데이터 시작/중간/끝 ET 시각 / 국내=09:00·12:00·15:30 고정
    var axis;
    if(isUS&&useT){
      var mid=Math.floor((n-1)/2);
      axis='<text x="'+X0+'" y="168" font-size="10" fill="#9CA3AF" text-anchor="start">'+(times[0]||'')+'</text>'+
        '<text x="'+px2(mid).toFixed(1)+'" y="168" font-size="10" fill="#9CA3AF" text-anchor="middle">'+(times[mid]||'')+'</text>'+
        '<text x="'+X1+'" y="168" font-size="10" fill="#9CA3AF" text-anchor="end">'+(times[n-1]||'')+'</text>';
    } else {
      axis='<text x="'+X0+'" y="168" font-size="10" fill="#9CA3AF" text-anchor="start">09:00</text>'+
        '<text x="320" y="168" font-size="10" fill="#9CA3AF" text-anchor="middle">12:00</text>'+
        '<text x="'+X1+'" y="168" font-size="10" fill="#9CA3AF" text-anchor="end">15:30</text>';
    }
    svgHTML+='<circle cx="'+coords[n-1].x.toFixed(1)+'" cy="'+coords[n-1].y.toFixed(1)+'" r="4" fill="#fff" stroke="'+col+'" stroke-width="2"/>'+
      axis+pinsHTML+'<g id="intra-hover"></g>';
    document.getElementById('intra-svg').innerHTML=svgHTML;

    // 장중 데이터 확보 → '오늘 장중' 탭 노출·활성화(최초 1회, decide) + 툴팁 바인딩
    decide(true);
    bindHover();

    // ── 헤더 시세 실시간 갱신 (국내=오늘 세션일 때만 / 미국=12h 이내 fresh일 때 — 휴장·전일 데이터 덮어쓰기 방지) ──
    if(d&&((isUS&&d.fresh)||(!isUS&&d.date===todayKST()))&&prevClose>0){
      var cur=vals[n-1], chg=(cur-prevClose)/prevClose*100, u=chg>=0;
      if(isUS) headerUsd=cur;   // 라이브 가격(USD) 기준값 보존 → 통화 전환 시 재포맷
      if(pxEl) pxEl.textContent=fmtPx(cur);
      if(cgEl){cgEl.style.color=u?'var(--up)':'var(--dn)';cgEl.textContent=(u?'▲ +':'▼ ')+chg.toFixed(2)+'%';}
      if(metaEl){
        var lt=times[n-1]||'';
        var label;
        if(isLive){ var ms=seg==='pre'?'프리장':(seg==='post'?'애프터장':'장중'); label=isUS?(ms+' '+lt):('오늘 장중 '+lt); }
        else { label=fmtTradeDate(d&&d.date) || (isUS?'장중':'오늘 장중'); } // 장 마감 후: 거래일 날짜
        metaEl.innerHTML=metaOrig.replace(/(·\s*)\d{2}-\d{2}\s*종가/, '$1'+label);
      }
    }

    // ── 뉴스 핀(movers-why)은 최초 1회만 로드 → pinsHTML에 캐시해 매 틱 곡선과 함께 재합성 ──
    if(pinsLoaded) return;
    pinsLoaded=true;
    if(isUS) return;                     // 미국은 movers-why 뉴스 핀 없음
    function yAtX(x){var b=coords[0];for(var i=0;i<coords.length;i++){if(Math.abs(coords[i].x-x)<Math.abs(b.x-x))b=coords[i];}return b.y;}
    var dnow=new Date(Date.now()+9*3600*1000).toISOString().slice(0,10);
    fetch('/data/movers-why-'+dnow+'.json').then(function(r){return r.ok?r.json():fetch('/data/movers-why-live.json').then(function(x){return x.ok?x.json():null;});}).then(function(j){
      if(!j||!j.stocks)return;
      var me=j.stocks.filter(function(s){return s.code===code;})[0];
      var evs=(me&&me.events)||[], add='';
      evs.forEach(function(e,i){var ax=t2x(e.time),ay=yAtX(ax),f=e.tier==='why'?'#E03131':'#fff',st=e.tier==='why'?'#E03131':'#94A3B8',tc=e.tier==='why'?'#fff':'#64748B';
        var px=Math.min(X1-12,Math.max(X0+12,ax)),top=(ay-41)>=YT&&(ay-31-10)>=0,cy=top?ay-31:ay+31,sy=top?ay-24:ay+24,ty=top?ay-27:ay+35;
        add+='<line x1="'+ax.toFixed(1)+'" y1="'+ay.toFixed(1)+'" x2="'+px.toFixed(1)+'" y2="'+sy.toFixed(1)+'" stroke="'+st+'" stroke-width="1.3"/><circle cx="'+px.toFixed(1)+'" cy="'+cy.toFixed(1)+'" r="10" fill="'+f+'" stroke="'+st+'" stroke-width="1.6"/><text x="'+px.toFixed(1)+'" y="'+ty.toFixed(1)+'" font-size="11" font-weight="800" fill="'+tc+'" text-anchor="middle">'+(i+1)+'</text>';});
      pinsHTML=add;
      var svgEl=document.getElementById('intra-svg');
      // 핀을 hover 그룹 앞에 삽입(곡선 위, 가이드 아래)
      var hg=document.getElementById('intra-hover');
      if(hg) hg.insertAdjacentHTML('beforebegin',add); else svgEl.innerHTML+=add;
      var tl=document.getElementById('intra-tl');
      if(tl&&evs.length){
        // 좌측 정렬 기준 = 그래프 09:00 지점(viewBox 640 중 X0=14). svg 실제 렌더 너비에 비례해 들여쓰기.
        var sw=(svgEl.getBoundingClientRect().width)||640;
        tl.style.paddingLeft=(14/640*sw).toFixed(1)+'px';
        tl.innerHTML=evs.map(function(e,i){var lbl=e.tier==='why'?'why':'관련',nbg=e.tier==='why'?'background:#E03131;color:#fff;':'background:#fff;color:#64748B;border:1.5px solid #CBD5E1;',tcss=e.tier==='why'?'color:#E03131;background:#FEF2F2;':'color:#64748B;background:#F1F5F9;';
        return '<div style="display:flex;flex-direction:column;align-items:flex-start;text-align:left;gap:3px;padding:10px 0;border-bottom:1px solid #F1F5F9;"><div style="width:20px;height:20px;border-radius:50%;font-size:11px;font-weight:800;display:flex;align-items:center;justify-content:center;'+nbg+'">'+(i+1)+'</div><div style="font-size:11px;font-weight:700;color:#94A3B8;">'+e.time+'</div><div style="font-size:13px;font-weight:700;line-height:1.4;"><a href="'+e.url+'" target="_blank" rel="noopener" style="color:#0F172A;text-decoration:none;">'+e.headline+'</a><span style="font-size:10px;font-weight:800;border-radius:5px;padding:1px 6px;margin-left:6px;'+tcss+'">'+lbl+'</span></div><div style="font-size:12px;color:#334155;">'+e.why+'</div><div style="font-size:11px;color:#94A3B8;">출처 · '+e.source+'</div></div>';}).join(''); }
    }).catch(function(){});
  }

  var lastD=null;
  function tick(){fetch(apiURL).then(function(r){return r.json();}).then(function(d){lastD=d;render(d);}).catch(function(){decide(false);});}
  tick();
  setTimeout(function(){decide(false);},3500); // 응답 지연·실패 안전장치 → 20일 종가로 폴백
  // 통화 전환(원화/달러) 시 헤더·장중 곡선 라벨 재포맷
  if(isUS) USCUR.onChange(function(){ if(lastD) render(lastD); applyHeaderCurrency(); });
  if(isUS){
    // 미국: 프리장(04:00 ET)~애프터장(20:00 ET)에만 20초 폴링
    if(isLive) setInterval(tick,20000);
  } else {
    // 국내: 장중(09:00~15:35 KST)에만 45초 폴링 — 헤더 시세·곡선 실시간 갱신
    if(isLive) setInterval(tick,45000);
  }
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

