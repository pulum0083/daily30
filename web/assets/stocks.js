// 종목 상세 페이지의 sparkline 렌더를 담당하는 스크립트

// ── 국내 거래일 판정 (장중 곡선·야간 추정가가 공유) ──
// 목록은 api/_market-calendar.mjs 미러. 두 곳에서 쓰므로 파일 스코프에 둔다(맵 중복 금지).
var KR_HOL={'2026-01-01':1,'2026-02-16':1,'2026-02-17':1,'2026-02-18':1,'2026-03-02':1,'2026-05-01':1,'2026-05-05':1,'2026-05-25':1,'2026-06-03':1,'2026-07-17':1,'2026-08-17':1,'2026-09-24':1,'2026-09-25':1,'2026-09-26':1,'2026-10-05':1,'2026-10-09':1,'2026-12-25':1,'2026-12-31':1,'2025-12-25':1,'2025-12-31':1};
function krTradingDay(){var d=new Date(Date.now()+9*3600*1000),wd=d.getUTCDay();return !(wd===0||wd===6||KR_HOL[d.toISOString().slice(0,10)]);}
function krMinNow(){var k=new Date(Date.now()+9*3600*1000);return k.getUTCHours()*60+k.getUTCMinutes();}

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
  // 좌우 여백 — 20일 종가(hasDates)는 '오늘 장중' SVG(viewBox 640×180·height 160·meet)의
  // 좌우 여백과 일치시켜 탭 전환 시 곡선 좌우 폭이 달라 덜컹이는 현상을 제거한다.
  var sideInset = 10;
  if (hasDates) {
    var s = Math.min(W / 640, 160 / 180);
    sideInset = (W - 640 * s) / 2 + 14 * s;
  }
  var pad = { t: 28, b: hasDates ? 24 : 8, l: sideInset, r: sideInset };
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

// data-spark 컨테이너 전체를 현재 폭 기준으로 재렌더 (초기 로드·리사이즈·탭 전환 공용)
function redrawAllSparks() {
  document.querySelectorAll('[data-spark]').forEach(function(container) {
    var raw = (container.getAttribute('data-spark') || '').trim();
    if (!raw) return;
    var closes = raw.split(',').map(Number).filter(function(v) { return !isNaN(v) && isFinite(v); });
    drawSparkCanvas(container, closes);
  });
}
window.redrawAllSparks = redrawAllSparks;

document.addEventListener('DOMContentLoaded', function() {
  redrawAllSparks();
  // 리사이즈 대응 (윈도우 리사이즈는 100ms 디바운스)
  var resizeTimer;
  window.addEventListener('resize', function() {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(redrawAllSparks, 100);
  });
  // 차트 탭 전환 '덜컹임' 제거 — '20일 종가' 패널은 숨김(display:none, 폭 0) 상태에서
  // 600px 폴백으로 그려져 있다가, 기존엔 resize 이벤트(100ms 디바운스)로 뒤늦게 올바른
  // 폭으로 다시 그려져 한 번 덜컹였다. 탭 전환 직후 동기로 재렌더하면 패널이 보이기 전
  // 같은 프레임에 올바른 폭으로 그려져 stale 캔버스가 화면에 노출되지 않는다.
  if (typeof window.switchChartTab === 'function') {
    var _origSwitchChartTab = window.switchChartTab;
    window.switchChartTab = function(pane) {
      _origSwitchChartTab(pane);
      if (pane === 'pane-spark') redrawAllSparks();
    };
  }
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
  // 직전 거래일 종가 — pxEl 렌더값은 '최신 종가/현재가'라 그대로 쓰면 등락률이 0%로 뭉개진다.
  // 국내는 '20일 종가' 스파크(spark-main)의 마지막-전 값을 대신 쓴다. 미국은 render()에서 응답의 d.prevClose로 채운다.
  function sparkPrevClose(){
    var sp=document.getElementById('spark-main');
    var arr=sp?(sp.getAttribute('data-spark')||'').split(',').map(Number).filter(function(v){return isFinite(v);}):[];
    return arr.length>=2 ? arr[arr.length-2] : 0;
  }
  var prevClose = isUS ? 0 : sparkPrevClose();
  var metaOrig=metaEl?metaEl.innerHTML:'';
  // 탭 전환 시 헤더로 복원할 원본(SSR) 시세 — '20일 종가' 탭 선택 시 이 값으로 되돌린다.
  var origPxText=pxEl?pxEl.textContent:'', origCgText=cgEl?cgEl.textContent:'', origCgColor=cgEl?cgEl.style.color:'';
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
  // 국내: 주말·공휴일이면 장중 아님(비거래일에 '오늘 장중'·실시간 헤더로 오판 방지). krTradingDay는 파일 스코프.
  var isLive = isUS ? (nowMin>=240&&nowMin<=1200) : (krTradingDay() && nowMin>=540 && nowMin<=935);
  // 현재 미국 세션 구간 (라이브 아닐 땐 본장 기준)
  function curSeg(){ if(!isLive) return 'regular'; var m=etNowMin(); return m<570?'pre':(m<960?'regular':'post'); }
  function segLabel(seg){ return seg==='pre'?'프리장':(seg==='post'?'애프터장':'오늘 장중'); }
  function liveLabel(){
    if(isUS){var s=curSeg();var nm=s==='pre'?'프리장':(s==='post'?'애프터장':'정규장');return 'LIVE · '+nm+' · 20초 갱신';}
    return 'LIVE · 장중 · 45초 갱신';
  }

  // ── 세션 고정 프레임 (실시간 곡선 표기 규격 — 홈 섹터 카드 sbxSpark와 동일) ──
  // x축 기준을 '수집된 데이터 범위'가 아니라 '세션 전체 길이'로 잡는다. 데이터 범위에 맞추면
  // 장 시작 30분이든 6시간이든 곡선이 항상 폭을 꽉 채워, 하루가 어디까지 진행됐는지가 화면에서 사라진다.
  // 국내는 t2x()가 이미 09:00~15:30 고정 프레임이고, 미국만 데이터 범위 정규화라 여기서 교정한다.
  function usSegBounds(seg){ return seg==='pre'?[240,570]:(seg==='post'?[960,1200]:[570,960]); } // ET 분
  function etMinOfTs(tsSec){
    var s=new Date(tsSec*1000).toLocaleTimeString('en-US',{timeZone:'America/New_York',hour12:false,hour:'2-digit',minute:'2-digit'}).split(':');
    return (parseInt(s[0],10)%24)*60+parseInt(s[1],10);
  }
  // 데이터 한 점의 epoch와 그 시점 ET 분으로 세션 시작·끝 epoch를 역산 (세션 중 DST 전환은 없다)
  function usSegWindow(seg, anchorTs){
    var b=usSegBounds(seg), start=anchorTs-(etMinOfTs(anchorTs)-b[0])*60;
    return [start, start+(b[1]-b[0])*60];
  }
  function kstHM(tsSec){
    var s=new Date(tsSec*1000).toLocaleTimeString('en-US',{timeZone:'Asia/Seoul',hour12:false,hour:'2-digit',minute:'2-digit'}).split(':');
    return String((parseInt(s[0],10)%24)).padStart(2,'0')+':'+s[1];
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
    // 기준가는 세션별로 다르다 — 프리·애프터장엔 prevClose가 한 세션 과거라 -7%대 허수가 나온다(§30).
    // 서버(_us-session.mjs)가 세션을 보고 정해준 baseClose를 우선 쓰고, 없으면 prevClose로 폴백한다.
    if(isUS && d){
      var b=(typeof d.baseClose==='number'&&d.baseClose>0)?d.baseClose
           :((typeof d.prevClose==='number'&&d.prevClose>0)?d.prevClose:0);
      if(b>0) prevClose=b;
    }
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
    // 미국도 세션 고정 프레임(프리/정규/애프터 각 구간의 시작~끝)을 폭으로 쓴다 — 경과분만큼만 채워진다.
    var wlo=0,whi=1,useFrame=false;
    if(isUS&&tsv&&tsv.length){
      var win=usSegWindow(seg, tsv[0]);
      if(win[1]>win[0]){ wlo=win[0]; whi=win[1]; useFrame=true; }
      else { wlo=Math.min.apply(null,tsv); whi=Math.max.apply(null,tsv); }
    }
    function px2(i){
      if(isUS&&tsv){return X0+(X1-X0)*Math.min(1,Math.max(0,(tsv[i]-wlo)/((whi-wlo)||1)));}
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
    // x축 라벨: 미국=세션 프레임 시작/중간/끝(KST) / 국내=09:00·12:00·15:30 고정
    // 데이터 마지막 시각을 오른쪽 끝에 찍으면 "장이 여기서 끝났다"로 읽혀 진행형 곡선과 어긋난다.
    var axis;
    if(isUS&&useFrame){
      axis='<text x="'+X0+'" y="168" font-size="10" fill="#9CA3AF" text-anchor="start">'+kstHM(wlo)+'</text>'+
        '<text x="320" y="168" font-size="10" fill="#9CA3AF" text-anchor="middle">'+kstHM((wlo+whi)/2)+'</text>'+
        '<text x="'+X1+'" y="168" font-size="10" fill="#9CA3AF" text-anchor="end">'+kstHM(whi)+'</text>';
    } else if(isUS&&useT){
      var mid=Math.floor((n-1)/2);
      axis='<text x="'+X0+'" y="168" font-size="10" fill="#9CA3AF" text-anchor="start">'+(times[0]||'')+'</text>'+
        '<text x="'+px2(mid).toFixed(1)+'" y="168" font-size="10" fill="#9CA3AF" text-anchor="middle">'+(times[mid]||'')+'</text>'+
        '<text x="'+X1+'" y="168" font-size="10" fill="#9CA3AF" text-anchor="end">'+(times[n-1]||'')+'</text>';
    } else {
      axis='<text x="'+X0+'" y="168" font-size="10" fill="#9CA3AF" text-anchor="start">09:00</text>'+
        '<text x="320" y="168" font-size="10" fill="#9CA3AF" text-anchor="middle">12:00</text>'+
        '<text x="'+X1+'" y="168" font-size="10" fill="#9CA3AF" text-anchor="end">15:30</text>';
    }
    // 끝점 — 장중이면 오른쪽 끝까지 점선 가이드("여기까지 진행 중") + 맥동하는 라이브 도트.
    // 홈 섹터 카드(.spark-livedot)와 같은 규격이되, 이 SVG는 preserveAspectRatio 기본값(meet)이라
    // 가로만 늘어나는 왜곡이 없어 SVG 안의 <circle>로 그린다(별도 CSS 없이 SMIL로 맥동).
    var lx=coords[n-1].x, ly=coords[n-1].y;
    if(isLive && lx<X1-4){
      svgHTML+='<line x1="'+lx.toFixed(1)+'" y1="'+ly.toFixed(1)+'" x2="'+X1+'" y2="'+ly.toFixed(1)+'" stroke="'+col+'" stroke-opacity="0.3" stroke-width="1" stroke-dasharray="3,3"/>';
    }
    if(isLive){
      svgHTML+='<circle cx="'+lx.toFixed(1)+'" cy="'+ly.toFixed(1)+'" r="4" fill="'+col+'">'+
        '<animate attributeName="r" values="4;11;4" dur="1.8s" repeatCount="indefinite"/>'+
        '<animate attributeName="opacity" values="0.38;0;0.38" dur="1.8s" repeatCount="indefinite"/></circle>';
    }
    svgHTML+='<circle cx="'+lx.toFixed(1)+'" cy="'+ly.toFixed(1)+'" r="4" fill="#fff" stroke="'+col+'" stroke-width="2"/>'+
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

  // 탭 전환 시 헤더 시세도 함께 전환 — '20일 종가' 탭은 가격은 원본(SSR) 그대로 두되
  // 등락률만 20일 누적 변동으로 바꿔 어떤 탭을 보고 있는지 구분되게 한다. '오늘 장중' 탭은 최신 장중 시세.
  function spark20Chg(){
    var sp=document.getElementById('spark-main');
    var arr=sp?(sp.getAttribute('data-spark')||'').split(',').map(Number).filter(function(v){return isFinite(v);}):[];
    return arr.length>=2 ? (arr[arr.length-1]-arr[0])/arr[0]*100 : null;
  }
  if(typeof window.switchChartTab==='function'){
    var _origTabForHeader=window.switchChartTab;
    window.switchChartTab=function(pane){
      _origTabForHeader(pane);
      if(pane==='pane-spark'){
        if(pxEl) pxEl.textContent=origPxText;
        if(metaEl) metaEl.innerHTML=metaOrig;
        var chg20=spark20Chg();
        if(cgEl){
          if(chg20===null){ cgEl.style.color=origCgColor; cgEl.textContent=origCgText; }
          else { var u20=chg20>=0; cgEl.style.color=u20?'var(--up)':'var(--dn)'; cgEl.textContent=(u20?'▲ +':'▼ ')+chg20.toFixed(2)+'% (20일)'; }
        }
      } else if(pane==='pane-intra'){
        if(lastD) render(lastD);
        // 마감 후·주말엔 render()의 '오늘 세션' 가드로 헤더가 갱신되지 않아, 직전에 '20일 종가'
        // 탭이 세팅한 '(20일)' 라벨이 그대로 남는다 → SSR(최신 종가) 헤더로 복원해 거래일 탭과 일치시킨다.
        if(!(lastD && lastD.date===todayKST())){
          if(pxEl) pxEl.textContent=origPxText;
          if(cgEl){ cgEl.style.color=origCgColor; cgEl.textContent=origCgText; }
          if(metaEl) metaEl.innerHTML=metaOrig;
        }
      }
    };
  }
})();

// '같은 섹터' 사이드바(US 상세) peer 등락률 실시간 갱신 — SSR 값은 전일 배치 스냅샷이라
// 장중엔 히어로(실시간)와 기준 세션이 달라 보인다. /api/stocks-live로 라이브 값을 받아 덮어쓴다.
(function(){
  var panel=document.getElementById('peers-panel'); if(!panel) return;
  var rows=[].slice.call(panel.querySelectorAll('.srow[data-ticker]'));
  if(!rows.length) return;
  var syms=rows.map(function(r){return r.getAttribute('data-ticker');});
  function poll(){
    fetch('/api/stocks-live?us='+encodeURIComponent(syms.join(',')),{cache:'no-store'})
      .then(function(r){return r.ok?r.json():null;})
      .then(function(d){
        if(!d||!Array.isArray(d.us)) return;
        var bySym={}; d.us.forEach(function(x){bySym[x.sym]=x;});
        rows.forEach(function(row){
          var x=bySym[row.getAttribute('data-ticker')];
          if(!x||typeof x.changePct!=='number') return;
          var el=row.querySelector('.c'); if(!el) return;
          var pct=x.changePct, up=pct>0, cls=up?'up':(pct<0?'dn':'');
          el.className='c num'+(cls?' '+cls:'');
          el.style.color= cls? '' : 'var(--muted)';
          el.textContent=(up?'+':'')+pct.toFixed(2)+'%';
        });
      }).catch(function(){});
  }
  poll();
  setInterval(poll, 20000);
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

// ? 도움말 툴팁 바인딩 — stocks.js는 defer라 DOM 파싱 후 실행돼 body 끝의 #*-tip을 항상 찾는다.
// (페이지 인라인 스크립트는 tip 요소보다 먼저 실행돼 바인딩에 실패하므로 여기서 처리)
(function(){
  function bindTip(btnId, tipId){
    var btn=document.getElementById(btnId);
    var tip=document.getElementById(tipId);
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
  }
  bindTip('tr-help-btn','tr-tip'); // 더블샷 트랙레코드
  bindTip('fo-label','fo-tip');    // 외국인 보유율
})();

// 증권사 목표주가 '현재가' 라벨 — 현재가가 최저가 근처/아래면 라벨이 중앙정렬(translateX(-50%))로
// 패널 밖으로 나가 잘린다. 라벨은 레인지 안에 머물게 클램프하고, 아래 화살표만 실제 현재가를 가리킨다.
(function(){
  function clampTgtCur(){
    document.querySelectorAll('.tgt-cur').forEach(function(el){
      var range=el.parentNode; if(!range) return;        // .tgt-range
      var rw=range.offsetWidth; if(!rw) return;
      // 원본 위치(%)는 최초 1회 data 속성에 보존 (이후 left를 px로 덮어쓰므로)
      var pct;
      if(el.dataset.curPct!=null) pct=parseFloat(el.dataset.curPct);
      else { pct=parseFloat(el.style.left); el.dataset.curPct=pct; }
      if(isNaN(pct)) return;
      var dotX=pct/100*rw;                                // 실제 현재가 위치(px, range 기준)
      var lw=el.offsetWidth, half=lw/2, pad=4;
      var center=Math.min(Math.max(dotX, half+pad), rw-half-pad); // 라벨 중심 클램프
      el.style.left=center+'px';
      var arrowPct=(dotX-(center-half))/lw*100;           // 라벨 내 화살표 상대 위치(%)
      el.style.setProperty('--arrow-left', Math.min(Math.max(arrowPct,6),94)+'%');
    });
  }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',clampTgtCur);
  else clampTgtCur();
  window.addEventListener('resize',clampTgtCur);
})();

// ── 야간 추정가 (국내장 마감 후) ─────────────────────────────────────────────
// /api/hl-night = 하이퍼리퀴드 xyz dex의 24h 무기한선물 USD가 × 환율. 마감 후에도 움직이는 참고가다.
// 마크업은 HL 상장 3종목(삼성전자·SK하이닉스·현대차)에만 렌더된다(generate_html.HL_NIGHT_CODES).
//
// 표시 규칙 (전부 운영 규칙 0에서 나온다):
//  · 히어로의 큰 숫자는 KRX 실측 종가다. 덮어쓰지 않고 별도 행으로 붙여 실측/참고 경계를 유지한다.
//  · 등락률은 응답의 changePct(HL 자체 24시간 전 mark 대비)를 쓰지 않는다 — 화면의 KRX 일간
//    등락률과 기준이 달라 나란히 놓으면 오독된다. 실측 종가(data-close) 대비로 다시 계산하고
//    라벨에 '종가 대비'를 명시한다.
//  · adjusted:true는 HL 합성가가 실제가 대비 5% 넘게 벗어나 서버가 '실제 종가로 대체'한 값이다.
//    그걸 '추정가'라 부르면 종가를 추정가라고 말하는 게 되므로 표시하지 않는다.
(function(){
  var box=document.getElementById('night-px'); if(!box) return;
  var code=box.getAttribute('data-code');
  if(!code) return;
  var valEl=document.getElementById('night-px-val'), chgEl=document.getElementById('night-px-chg');

  // 비교 기준은 '화면에 실제로 보이는 종가'다. 장중 곡선 IIFE가 실측 1분봉 마지막 값으로 히어로를
  // 보정하는 경우가 있어(SSR 값과 다를 수 있다), data-close만 믿으면 사용자가 못 보는 숫자를
  // 기준으로 '종가 대비'를 말하게 된다. 히어로를 먼저 읽고, 못 읽을 때만 SSR 값으로 폴백한다.
  function closePx(){
    var el=document.querySelector('#hero-stock .px.num');
    var shown=el?parseFloat((el.textContent||'').replace(/[^\d.]/g,'')):NaN;
    if(isFinite(shown)&&shown>0) return shown;
    var ssr=parseFloat(box.getAttribute('data-close'));
    return isFinite(ssr)&&ssr>0?ssr:0;
  }

  // 마감 상태 = 비거래일(주말·공휴일)이거나 09:00~15:30 밖
  function krClosed(){ if(!krTradingDay()) return true; var m=krMinNow(); return m<540||m>930; }

  function hide(){ box.style.display='none'; }

  function poll(){
    if(!krClosed()){ hide(); return; }
    fetch('/api/hl-night',{cache:'no-store'})
      .then(function(r){return r.ok?r.json():null;})
      .then(function(d){
        var it=(d&&d.items||[]).filter(function(x){return x.code===code;})[0];
        if(!it||it.krw==null||it.adjusted){ hide(); return; }   // 값 없음·실제가로 대체됨 → 표시 안 함
        var close=closePx();
        if(!close){ hide(); return; }                           // 비교 기준을 못 구하면 % 를 지어내지 않는다
        var pct=(it.krw-close)/close*100;
        valEl.textContent=Math.round(it.krw).toLocaleString('ko-KR');
        var up=pct>0;
        chgEl.textContent=(up?'▲ +':(pct<0?'▼ ':'— '))+Math.abs(pct).toFixed(2)+'% (종가 대비)';
        chgEl.style.color=up?'var(--up)':(pct<0?'var(--dn)':'var(--muted)');
        box.style.display='flex';   // 숨김 해제 시 flex — ''로 두면 div 기본값 block이라 정렬이 깨진다
      })
      .catch(hide);
  }
  poll();
  setInterval(poll,30000);   // 문구의 '30초 갱신'과 반드시 일치시킬 것
})();

