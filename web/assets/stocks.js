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

    var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none" style="width:100%;height:80px;display:block;overflow:visible;">'
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

