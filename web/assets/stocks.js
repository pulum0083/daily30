// 종목 상세 페이지의 sparkline 렌더와 기간탭 토글을 담당하는 스크립트

// 네비게이션 — 종목 상세는 standalone 페이지로 실제 이동, 허브/섹터는 /stocks/ 해시 라우팅
// 제너레이터가 모든 종목에 /stocks/{code}/ 페이지를 생성하므로 무조건 클린 URL 사용
function goStock(code){location.href='/stocks/'+code+'/';}
function goHub(screen){location.href='/stocks/'+(screen?'#'+screen:'');}
function goBack(){if(history.length>1)history.back();else goHub();}
function switchTab(hero,tab,el){document.querySelectorAll("#hero-"+hero+" .ctabs a").forEach(a=>a.classList.remove("on"));el.classList.add("on");["5d","1m","3m","1y"].forEach(t=>{var p=document.getElementById(hero+"-"+t);if(p)p.classList.toggle("hidden",t!==tab);});}

// 헤더 sparkline 렌더 — [data-spark] 속성의 쉼표 구분 종가 배열로 SVG 폴리라인 생성
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('[data-spark]').forEach(function(container) {
    var raw = (container.getAttribute('data-spark') || '').trim();
    if (!raw) return;
    // NaN/Infinity만 제거 — 도메인상 가격은 양수지만 0을 무시하면 안 됨
    var closes = raw.split(',').map(Number).filter(function(v) { return !isNaN(v) && isFinite(v); });
    if (closes.length < 2) return;

    var W = 740, H = 80, PAD = 2;
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

    var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none" style="width:100%;height:80px;display:block;overflow:visible;">'
      + '<defs><linearGradient id="' + gradId + '" x1="0" y1="0" x2="0" y2="1">'
      + '<stop offset="0%" stop-color="' + color + '" stop-opacity="0.18"/>'
      + '<stop offset="100%" stop-color="' + color + '" stop-opacity="0"/>'
      + '</linearGradient></defs>'
      + '<polygon points="' + areaPoints + '" fill="url(#' + gradId + ')"/>'
      + '<polyline fill="none" stroke="' + color + '" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round" points="' + pts.join(' ') + '"/>'
      + '<circle cx="' + fx.toFixed(1) + '" cy="' + firstPt[1] + '" r="3.5" fill="#fff" stroke="#9CA3AF" stroke-width="2"/>'
      + '<circle cx="' + lx.toFixed(1) + '" cy="' + ly.toFixed(1) + '" r="3.5" fill="#fff" stroke="' + color + '" stroke-width="2"/>'
      + '</svg>';

    container.innerHTML = svg;
  });
});

// 차트 호버 — 가장 가까운 일봉 꼭짓점에 크로스헤어·종가·일자 툴팁 표시
(function(){
  function initChart(wrap){
    var poly=wrap.querySelector('polyline'),svg=wrap.querySelector('svg');
    if(!poly||!svg)return;
    var vbH=svg.viewBox.baseVal.height,svgH=80,PAD=14;
    var pts=poly.getAttribute('points').trim().split(/\s+/).map(function(p){var a=p.split(',');return{x:+a[0],y:+a[1]};});
    var ys=pts.map(function(p){return p.y;}),yMin=Math.min.apply(null,ys),yMax=Math.max.apply(null,ys);
    var lo=+wrap.dataset.lo,hi=+wrap.dataset.hi;
    var labels=[].map.call(wrap.querySelectorAll('.taxis span'),function(s){return s.textContent;});
    var cross=document.createElement('div');cross.className='chart-cross';
    var dot=document.createElement('div');dot.style.cssText='position:absolute;width:7px;height:7px;border-radius:50%;background:#fff;border:2px solid var(--up);transform:translate(-50%,-50%);pointer-events:none;display:none;z-index:11;';
    var tt=document.createElement('div');tt.className='chart-tt';
    wrap.appendChild(cross);wrap.appendChild(dot);wrap.appendChild(tt);
    wrap.addEventListener('mousemove',function(e){
      var r=wrap.getBoundingClientRect(),plotW=r.width-PAD*2;if(plotW<=0)return;
      var cx=Math.max(0,Math.min(plotW,e.clientX-r.left-PAD)),vx=cx/plotW*740;
      var best=pts[0],bd=1e9;pts.forEach(function(p){var d=Math.abs(p.x-vx);if(d<bd){bd=d;best=p;}});
      var sx=PAD+best.x/740*plotW,sy=8+best.y/vbH*svgH;
      var price=Math.round((hi-(best.y-yMin)/((yMax-yMin)||1)*(hi-lo))/100)*100;
      var li=Math.round(best.x/740*(labels.length-1)),dl=labels[Math.max(0,Math.min(labels.length-1,li))]||'';
      cross.style.left=sx+'px';cross.style.display='block';
      dot.style.left=sx+'px';dot.style.top=sy+'px';dot.style.display='block';
      tt.innerHTML=price.toLocaleString()+'<span style="font-size:11px;font-weight:600;color:var(--muted);margin-left:2px;">원</span>';
      tt.style.left=Math.max(44,Math.min(r.width-44,sx))+'px';tt.style.display='block';
    });
    wrap.addEventListener('mouseleave',function(){cross.style.display='none';dot.style.display='none';tt.style.display='none';});
  }
  document.querySelectorAll('.chart-wrap[data-lo]').forEach(initChart);
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

// 차트 색상 — 당일 등락(.cg ▲/▼) 기준: 상승 빨강, 하락 파랑
(function applyChartColors() {
  const cg = document.querySelector('.cg');
  const color = (cg && cg.textContent.includes('▲')) ? '#E03131' : '#2775ED';
  document.querySelectorAll('.chart-wrap').forEach(function(pane) {
    const polyline = pane.querySelector('polyline');
    if (!polyline) return;
    polyline.setAttribute('stroke', color);
    pane.querySelectorAll('linearGradient stop').forEach(function(s) {
      s.setAttribute('stop-color', color);
    });
    const circles = pane.querySelectorAll('circle');
    if (circles.length) circles[circles.length - 1].setAttribute('stroke', color);
  });
})();
