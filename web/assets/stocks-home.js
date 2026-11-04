// 종목 시그널 허브(/stocks/) 스크립트 — 2026-07-21 index.html 인라인 <script> 8블록에서 추출.
// 문서 등장 순서대로 이어붙였다. 전역 var/함수 공유 구조가 그대로라 동작 동일.
// head에서 defer로 로드되므로 DOM 파싱 완료 후 순서대로 실행된다(기존보다 늦게 = 더 안전).

/* ── 블록 1 (원본 index.html) ── */
/* 코스피 거래일 판별(허브 전역) — 주말+공휴일이면 비거래일. 공휴일 목록은 api/_market-calendar.mjs(서버 권위)의 미러.
       서버 API의 open 필드는 이미 휴일을 반영하지만, 라벨·폴링 여부를 시간만으로 판단하던 클라이언트 체크들이
       평일 공휴일을 장중으로 오판(●실시간·오늘 실시간·장중 추적 표기)하던 것을 막는다. */
    (function(){
      var H=new Set(['2026-01-01','2026-02-16','2026-02-17','2026-02-18','2026-03-02','2026-05-01','2026-05-05','2026-05-25','2026-06-03','2026-07-17','2026-08-17','2026-09-24','2026-09-25','2026-09-26','2026-10-05','2026-10-09','2026-12-25','2026-12-31','2025-12-25','2025-12-31']);
      window.krIsKospiHoliday=function(){
        var d=new Date(Date.now()+9*3600*1000), wd=d.getUTCDay();
        return wd===0||wd===6||H.has(d.toISOString().slice(0,10));
      };
      // 임의 날짜(YYYY-MM-DD) 판별 — 수급 히스토리에서 '거래일인데 데이터가 빠진 날'을 가려낼 때 쓴다.
      window.krIsKospiHolidayOn=function(ymd){
        var p=String(ymd).split('-');
        var d=new Date(Date.UTC(+p[0],+p[1]-1,+p[2])), wd=d.getUTCDay();
        return wd===0||wd===6||H.has(ymd);
      };
    })();

/* ── 블록 2 — 코스피 주도주 (2026-11-04 B안, SERVICE_RULES §79) ──
   세 종목을 한 줄씩: 지금 가격 · 오늘 · 어제 · 차이. 아래는 세 종목 섞은 관련 뉴스 7개.
   지금 가격 — 장중 09:00~15:30 실시간(/api/stocks-live) → 15:30~20:00 애프터장 실시간(같은 API의 after)
             → 20:00~다음 날 09:00·휴장일 하이퍼리퀴드 24h 추정가(/api/hl-night).
   비교 칸 — 장중엔 같은 확정 분의 오늘·어제 등락(/api/intraday?vs=intraday의 leaders, vs-yesterday.js가 받아 'vs:data'로 넘긴다).
            장 마감 뒤엔 직전 세션 공식 종가 등락 vs 그 전 세션 공식 종가 등락(1분봉 15:30 봉, 날짜와 함께).
   어제와의 차이(%p)는 빨강·파랑을 쓰지 않는다 — 오르내림과 헷갈린다(§49). */
(function(){
  var CODES=['005930','000660','005380'], NAMES={'005930':'삼성전자','000660':'SK하이닉스','005380':'현대차'};
  var ENT={'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'};
  function esc(s){ return String(s==null?'':s).replace(/[&<>"']/g,function(c){return ENT[c];}); }
  // http(s)만 허용 — javascript: 같은 스킴이 href/src로 들어가는 것을 막는다.
  function safeUrl(u){ return (typeof u==='string'&&/^https?:\/\//i.test(u))?u:''; }
  function f2(n){ return n==null?'—':(n>0?'+':n<0?'−':'')+Math.abs(n).toFixed(2); }
  function cls(n){ return n==null?'':n>0?'up':n<0?'dn':'zr'; }
  function won(n){ return n==null?'—':Math.round(n).toLocaleString('en-US'); }
  function r2(x){ return Math.round(x*100)/100; }
  function kst(ms){ return new Date((ms==null?Date.now():ms)+9*3600*1000); }
  function md8(y8){ var s=String(y8||''); return s.length===8?(+s.slice(4,6))+'/'+(+s.slice(6,8)):''; }

  // 지금 가격을 무엇으로 보일지 — 휴장일은 하루 종일 추정가.
  function phase(ms){
    var k=kst(ms), m=k.getUTCHours()*60+k.getUTCMinutes();
    var off=window.krIsKospiHolidayOn?window.krIsKospiHolidayOn(k.toISOString().slice(0,10)):(k.getUTCDay()===0||k.getUTCDay()===6);
    if(off) return 'night';
    if(m>=540&&m<=930) return 'open';
    if(m<1200&&m>930) return 'after';
    return 'night';
  }
  // 장 마감 뒤 비교 — 1분봉 15:30 봉 세 개(그 세션·직전·그 전). 하나라도 없으면 비운다(§0).
  function closeCmp(p){
    if(!p||!(p.price>0)||!(p.prevSessionClose>0)||!(p.prev2SessionClose>0)||!p.sessionDate||!p.prevSessionDate) return null;
    var t=r2((p.price/p.prevSessionClose-1)*100), y=r2((p.prevSessionClose/p.prev2SessionClose-1)*100);
    return {date:String(p.sessionDate), prevDate:String(p.prevSessionDate), t:t, y:y, diff:r2(t-y)};
  }
  // 세 종목 뉴스 섞기 — 종목마다 가장 최신 1건을 먼저 넣고 나머지는 발행 시각 순(한 종목 뉴스로만 차지 않게).
  function mixNews(stocks, n){
    var pub=function(x){ return Date.parse(x.published)||0; };
    var lists=CODES.map(function(c){ return ((stocks&&stocks[c])||[]).map(function(x){ var o={code:c}; for(var k in x) o[k]=x[k]; return o; }); });
    var out=[], seen={};
    lists.forEach(function(l){ if(l[0]){ out.push(l[0]); seen[l[0].url]=1; } });
    var rest=[].concat.apply([],lists).filter(function(x){ return !seen[x.url]; }).sort(function(a,b){ return pub(b)-pub(a); });
    var dedup={}, picked=out.concat(rest).filter(function(x){ var k=x.url||x.title; if(dedup[k]) return false; dedup[k]=1; return true; });
    return picked.slice(0,n).sort(function(a,b){ return pub(b)-pub(a); });
  }
  // 발행 시각 라벨은 저장값이 아니라 지금 기준으로 만든다(§20) — 오늘이면 시:분, 아니면 월/일 시:분.
  function newsTime(iso, nowMs){
    var t=Date.parse(String(iso||'')); if(isNaN(t)) return '';
    var k=kst(t), now=kst(nowMs);
    var hm=String(k.getUTCHours()).padStart(2,'0')+':'+String(k.getUTCMinutes()).padStart(2,'0');
    return k.toISOString().slice(0,10)===now.toISOString().slice(0,10)?hm:(k.getUTCMonth()+1)+'/'+k.getUTCDate()+' '+hm;
  }
  window.__leaders={phase:phase, closeCmp:closeCmp, mixNews:mixNews, newsTime:newsTime, f2:f2};

  var ST={ph:null, now:{}, cmp:{}, labels:null, vs:null, closedAt:0};

  function model(){
    var ph=ST.ph, L={};
    if(ph==='open'){
      var vs=ST.vs&&ST.vs.status==='ok'&&Array.isArray(ST.vs.leaders)?ST.vs:null, by={};
      (vs?vs.leaders:[]).forEach(function(l){ by[l.code]=l; });
      var rel=vs&&vs.prev?vs.prev.rel:'어제', tm=vs?vs.time:'';
      L={sub:vs?rel+'('+String(vs.prev.label||'').replace(/\(.\)$/,'')+') '+tm+'와 비교':'어제 같은 시각과 비교',
         now:'지금 · 실시간', t:vs?'오늘 '+tm:'오늘', y:vs?rel+' '+tm:'어제'};
      CODES.forEach(function(c){ var l=by[c]; ST.cmp[c]=l&&l.t!=null&&l.y!=null&&l.diff!=null?{t:l.t,y:l.y,diff:l.diff}:null; });
    } else {
      var head=null;
      CODES.forEach(function(c){ var x=ST.cmp[c]; if(x&&!head) head=x; });
      // 세션 날짜가 다른 종목은 같은 칸에 놓지 않는다.
      CODES.forEach(function(c){ var x=ST.cmp[c]; if(x&&head&&(x.date!==head.date||x.prevDate!==head.prevDate)) ST.cmp[c]=null; });
      L={sub:ph==='after'?'애프터장 실시간 · 비교는 종가 기준':'하이퍼리퀴드 24h 추정가 · 실제 체결가 아님',
         now:ph==='after'?'지금 · 애프터장':'지금 · 추정',
         t:head?md8(head.date)+' 종가':'종가', y:head?md8(head.prevDate)+' 종가':'전날 종가'};
    }
    return L;
  }

  function render(){
    var box=document.getElementById('ld-list'); if(!box) return;
    var L=model();
    var sub=document.getElementById('ld-sub'); if(sub) sub.textContent=L.sub;
    var max=0; CODES.forEach(function(c){ var x=ST.cmp[c]; if(x) max=Math.max(max,Math.abs(x.diff)); });
    var rows=CODES.map(function(c){
      var n=ST.now[c]||{}, x=ST.cmp[c];
      var pill=n.pill?'<span class="ldl-pill '+n.pill[0]+'" title="'+esc(n.pill[2])+'">'+esc(n.pill[1])+'</span>':'';
      var w=x&&max?Math.abs(x.diff)/max*50:0;
      var bar=x?'<span class="ldl-trk"><i style="'+(x.diff>=0?'left:50%':'right:50%')+';width:'+w.toFixed(1)+'%"></i></span>':'';
      return '<div class="ldl-row"><div class="ldl-nm"><b>'+NAMES[c]+'</b><small class="num">'+won(n.px)+
          (n.pc!=null?' <span class="'+cls(n.pc)+'">'+f2(n.pc)+'%</span>':'')+pill+'</small></div>'+
        '<div class="ldl-c t num '+cls(x&&x.t)+'">'+(x?f2(x.t)+'%':'—')+'<small class="m-k">'+esc(L.t)+'</small></div>'+
        '<div class="ldl-c y num '+cls(x&&x.y)+'" data-k="'+esc(L.y)+'">'+(x?f2(x.y)+'%':'—')+'</div>'+
        '<div class="ldl-d">'+bar+'<em class="num">'+(x?f2(x.diff)+'%p':'—')+'</em></div></div>';
    }).join('');
    box.innerHTML='<div class="ldl-row ldl-hd"><span>종목 · '+esc(L.now)+'</span><span>'+esc(L.t)+'</span><span>'+esc(L.y)+'</span><span>차이</span></div>'+rows;
  }

  function json(u){ return fetch(u,{cache:'no-store'}).then(function(r){ return r.ok?r.json():null; }).catch(function(){ return null; }); }
  // 장 마감 뒤 가격·비교 — 같은 응답의 1분봉 정규장 값. 밤엔 비교만 필요해 30분에 한 번만 받는다.
  function applyClosed(d){
    if(!d||!Array.isArray(d.prices)) return;
    d.prices.forEach(function(p){
      var x=closeCmp(p); ST.cmp[p.code]=x;
      if(ST.ph!=='after') return;
      var a=p.after&&p.after.price>0?p.after.price:null;
      ST.now[p.code]=a!=null
        ? {px:a, pc:r2((a/p.price-1)*100), pill:['aft','애프터','오늘 종가 대비']}
        : {px:p.price, pc:x?x.t:null, pill:['cls','종가','오늘 정규장 종가']};
    });
  }
  function poll(){
    // 보이지 않는 탭에서는 서버리스 함수를 깨우지 않는다(2026-08-16 Vercel 차단 사고).
    // 복귀 시 아래 visibilitychange가 인터벌을 기다리지 않고 즉시 다시 받는다.
    if(document.hidden) return;
    var ph=phase(); if(ph!==ST.ph){ ST.ph=ph; ST.cmp={}; ST.now={}; ST.closedAt=0; setNewsCycle(ph!=='open'); }
    var q='/api/stocks-live?codes='+CODES.join(',');
    if(ph==='open'){
      json(q).then(function(d){
        if(d&&Array.isArray(d.prices)) d.prices.forEach(function(p){ if(p.price!=null) ST.now[p.code]={px:p.price, pc:p.changePct}; });
        render();
      });
    } else if(ph==='after'){
      json(q).then(function(d){ applyClosed(d); render(); });
    } else {
      json('/api/hl-night').then(function(d){
        if(d&&Array.isArray(d.items)) d.items.forEach(function(it){
          if(it.krw!=null) ST.now[it.code]={px:it.krw, pc:it.changePct, pill:['est','추정','종가 × 하이퍼리퀴드 야간 변동 · 실제 체결가 아님']};
        });
        render();
      });
      if(Date.now()-ST.closedAt>30*60000){ ST.closedAt=Date.now(); json(q).then(function(d){ applyClosed(d); render(); }); }
    }
  }
  // 장중 비교 — vs-yesterday.js가 받은 대결판 응답을 같이 쓴다(같은 API를 두 번 부르지 않는다).
  function onVs(d){ ST.vs=d&&Array.isArray(d.leaders)?d:(ST.ph==='open'?null:ST.vs); if(ST.ph==='open') render(); }
  if(document.addEventListener) document.addEventListener('vs:data', function(e){ onVs(e&&e.detail); });
  if(window.__vsLast) onVs(window.__vsLast);

  // 뉴스 갱신 주기 표기 — 실제 수집 스케줄과 1:1로 맞춘다(없는 주기를 적지 않는다):
  //   평일 장중 09:00~15:30 → 30분  | 평일 그 외 → 1시간   : kospi-news-live.yml(cron-job.org)
  //   주말 09~21시          → 3시간                        : stock-news-weekend.yml(GHA native cron)
  //   주말 21시~익일 09시   → 수집 없음 → 주기 표기 생략
  // 공휴일엔 두 스케줄 모두 발화하지 않으므로 주말과 달리 주기를 적지 않는다.
  function setNewsCycle(night){
    var upd=document.getElementById('lw-upd'); if(!upd) return;
    var k=kst(), kstH=k.getUTCHours(), wd=k.getUTCDay();
    var isWeekend=(wd===0||wd===6), isHoliday=window.krIsKospiHoliday&&window.krIsKospiHoliday();
    var label;
    if(isWeekend) label=(kstH>=9&&kstH<21)?'세 종목 · 최신순 · 3시간 주기':'세 종목 · 최신순';
    else if(isHoliday) label='세 종목 · 최신순';
    else label=night?'세 종목 · 최신순 · 1시간 주기':'세 종목 · 최신순 · 30분 주기';
    upd.textContent=label;
  }

  function renderNews(d){
    var el=document.getElementById('lw-news'); if(!el) return;
    var list=mixNews(d&&d.stocks, 7);
    if(!list.length){ el.innerHTML='<div class="lw-empty">수집된 뉴스가 없어요.</div>'; return; }
    el.innerHTML=list.map(function(n){
      var href=safeUrl(n.url), th=safeUrl(n.thumb);
      return (href?'<a href="'+esc(href)+'" target="_blank" rel="noopener noreferrer">':'<a>')+
        '<div class="bd"><div class="nh"><span class="chip">'+esc(NAMES[n.code])+'</span>'+esc(n.title)+'</div>'+
        '<div class="mt">'+esc(newsTime(n.published))+(n.source?' · '+esc(n.source):'')+'</div></div>'+
        (th?'<img src="'+esc(th)+'" alt="" loading="lazy" onerror="this.remove()">':'')+'</a>';
    }).join('');
  }
  window.addEventListener('load', function(){ json('/data/stock-news.json').then(renderNews); });

  poll();
  setInterval(poll, 60000);
  document.addEventListener('visibilitychange', function(){ if(!document.hidden) poll(); });
})();
/* (2026-09-11) 선택 종목 1분봉 곡선·장중 지표 모듈 제거 — 장중 지표(당일 레인지·52주 위치)는
   코스피 주도주 타일 안으로 옮겼다. 레인지는 이제 1분봉 누적이 아니라 원천의 확정 고가·저가다. */

/* (2026-09-17) 블록 3 상승 모멘텀 종목 장중 추적 제거 — 사용자 결정. 픽 가격 폴링(/api/stocks-live 90초)도 함께 사라진다. */

/* ── 블록 4 (원본 index.html) ── */
(function(){
  var box=document.getElementById('us-evening');
  if(!box) return;
  var gridEl=document.getElementById('ue-grid'), macroEl=document.getElementById('ue-macro');
  // 밤사이 미국 두 묶음(§68 ④) — 코스피 선행 ETF 3칸 + AI 인프라 주식 3갈래. SOXX는 선행 ETF에만 한 번.
  // 종목 상세 페이지가 없어(2026-10-26 제거) 행은 링크하지 않는다.
  var LEAD=[
    {tk:'EWY',  sym:'EWY.O',  nm:'한국 ETF',   desc:'코스피 추종'},
    {tk:'DRAM', sym:'DRAM.K', nm:'메모리·HBM', desc:'삼성·하이닉스 선행'},
    {tk:'SOXX', sym:'SOXX.O', nm:'반도체 ETF', desc:'미 반도체 전체'}
  ];
  var AI_GROUPS=[
    {g:'메모리', items:[{nm:'SK하이닉스', tk:'SKHY', sym:'SKHY.O'},
                        {nm:'마이크론', tk:'MU', sym:'MU.O'},
                        {nm:'샌디스크', tk:'SNDK', sym:'SNDK.O'}]},
    {g:'AI 칩', items:[{nm:'엔비디아', tk:'NVDA', sym:'NVDA.O'},
                       {nm:'AMD', tk:'AMD', sym:'AMD.O'},
                       {nm:'브로드컴', tk:'AVGO', sym:'AVGO.O'}]},
    {g:'파운드리·장비', items:[{nm:'TSMC', tk:'TSM', sym:'TSM.N'},
                              {nm:'ASML', tk:'ASML', sym:'ASML.O'}]}
  ];
  var TICKERS=LEAD.concat([].concat.apply([], AI_GROUPS.map(function(g){ return g.items; })));
  var NASDAQ='QQQ.O';
  var cur='krw', fx=null, vix=null, dataBySym={}, loaded=false, isLive=false, sessionState='', basisAt=null;
  /* 가격 변동 시 상단 대표주 위젯과 동일한 카운트업(odometer) + 방향색 플래시 */
  (function injectUeFlash(){
    var st=document.createElement('style');
    st.textContent='@keyframes ueFlashUp{0%{background:rgba(224,49,49,.16)}100%{background:transparent}}'
      +'@keyframes ueFlashDn{0%{background:rgba(39,117,237,.16)}100%{background:transparent}}'
      +'#us-evening .px.ue-flash-up{animation:ueFlashUp .6s ease-out;border-radius:6px;}'
      +'#us-evening .px.ue-flash-dn{animation:ueFlashDn .6s ease-out;border-radius:6px;}';
    document.head.appendChild(st);
  })();
  function fmtPx(usd){
    if(typeof usd!=='number'||!isFinite(usd)) return '—';
    if(cur==='usd') return '$'+usd.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});
    if(!fx) return '—';
    return Math.round(usd*fx).toLocaleString('en-US')+'원';
  }
  function cgHtml(pct){
    if(typeof pct!=='number'||!isFinite(pct)) return '<span class="cg" style="color:var(--muted)">—</span>';
    var up=pct>0, col=up?'#E03131':(pct<0?'#2775ED':'#64748B'), s=up?'+':'';
    return '<span class="cg" style="color:'+col+'">'+s+pct.toFixed(2)+'%</span>';
  }
  function skeleton(){
    gridEl.innerHTML='<div class="ue-leads">'+LEAD.map(function(){ return '<div class="ue-lead"><span class="ue-skel" style="width:60px"></span><span class="ue-skel" style="width:48px;margin-top:6px"></span></div>'; }).join('')+'</div>';
    macroEl.innerHTML='<span class="ue-skel" style="display:inline-block;width:180px;"></span>';
  }
  function cls(p){ return typeof p==='number'&&isFinite(p) ? (p>0?'up':p<0?'dn':'') : ''; }
  function upCount(list){
    var up=0,dn=0,n=0;
    list.forEach(function(t){ var d=dataBySym[t.sym]; if(!d||typeof d.changePct!=='number'||!isFinite(d.changePct)) return; n++; if(d.changePct>0) up++; else if(d.changePct<0) dn++; });
    return {up:up, dn:dn, n:n};
  }
  function leadHtml(t){
    var d=dataBySym[t.sym]||{};
    var inner='<span class="ue-tk">'+t.tk+'</span><span class="ue-ln">'+t.nm+'</span>'+cgHtml(d.changePct)
      +'<span class="px ue-lp" data-sym="'+t.sym+'" data-usd="'+(d.price!=null?d.price:'')+'">'+fmtPx(d.price)+'</span><span class="ue-ld">'+t.desc+'</span>';
    return '<div class="ue-lead">'+inner+'</div>';
  }
  function aiRowHtml(t, mx){
    var d=dataBySym[t.sym]||{}, p=d.changePct, w=(typeof p==='number'&&isFinite(p)&&mx)?Math.round(Math.abs(p)/mx*100):0;
    return '<div class="ue-row"><span class="ue-n">'+t.nm+' <em>'+t.tk+'</em></span>'
      +'<span class="px ue-p" data-sym="'+t.sym+'" data-usd="'+(d.price!=null?d.price:'')+'">'+fmtPx(d.price)+'</span>'
      +'<span class="ue-bar"><i class="'+cls(p)+'" style="width:'+w+'%"></i></span>'+cgHtml(p)+'</div>';
  }
  function renderGrid(){
    var lc=upCount(LEAD), ai=[].concat.apply([], AI_GROUPS.map(function(g){ return g.items; })), ac=upCount(ai);
    var mx=Math.max.apply(null, ai.map(function(t){ var d=dataBySym[t.sym]; return d&&typeof d.changePct==='number'&&isFinite(d.changePct)?Math.abs(d.changePct):0; }))||0;
    gridEl.innerHTML=''
      +'<div class="ue-sec"><div class="ue-st"><h4>코스피 선행 ETF</h4>'+(lc.n?'<span>'+lc.n+'개 중 <b class="up">'+lc.up+' 상승</b></span>':'')+'</div>'
      +'<p class="ue-sd">한국 장이 열리기 전에 코스피 방향을 먼저 보여주는 ETF예요.</p>'
      +'<div class="ue-leads">'+LEAD.map(leadHtml).join('')+'</div></div>'
      +'<div class="ue-sec"><div class="ue-st"><h4>AI 인프라 주식</h4>'+(ac.n?'<span>'+ac.n+'개 중 <b class="up">'+ac.up+' 상승</b> · <b class="dn">'+ac.dn+' 하락</b></span>':'')+'</div>'
      +'<div class="ue-ais">'+AI_GROUPS.map(function(g){ return '<div class="ue-g"><div class="ue-gt">'+g.g+'</div>'+g.items.map(function(t){ return aiRowHtml(t, mx); }).join('')+'</div>'; }).join('')+'</div></div>';
  }
  // 맨 위 한 줄 — 나스닥 QQQ·VIX(§68 ④). SOXX는 선행 ETF 칸에만 한 번 둔다.
  function renderMacro(){
    var qq=dataBySym[NASDAQ]||{};
    macroEl.innerHTML='<span>나스닥 QQQ '+cgHtml(qq.changePct)+'</span>'
      +'<span>VIX '+((vix&&typeof vix.price==='number')?'<b>'+vix.price.toFixed(2)+'</b> '+cgHtml(vix.changePct):'<span class="cg" style="color:var(--muted)">—</span>')+'</span>';
    var cap=document.getElementById('ue-cap');
    if(cap) cap.textContent=(fx?'환율 '+fx.toLocaleString('en-US')+'원 적용 · ':'')+'미국 장 시작 전엔 직전 종가, 장중엔 실시간';
  }
  function renderBreadth(){ var el=document.getElementById('ue-breadth'); if(el){ el.classList.remove('has-data'); el.innerHTML=''; } }
  function render(){ renderGrid(); renderMacro(); renderBreadth(); }
  /* 실시간 기준 배지 — 정규장/프리장/애프터장이면 LIVE, 그 외엔 전일 종가 표시 */
  function updateLiveBadge(){
    var b=document.getElementById('ue-live'); if(!b) return;
    var label={open:'정규장',pre:'프리장',post:'애프터장'}[sessionState];
    if(isLive && label){
      b.classList.remove('closed');
      // 꼬리(· 60초 갱신)는 폰에서 숨긴다 — 머리 줄에 원화/달러 토글까지 한 줄로 넣기 위해(2026-10-28)
      b.innerHTML='<span class="dot"></span>LIVE · '+label+'<span class="ue-live-tail"> · 60초 갱신</span>';
    }else{
      b.classList.add('closed');
      var dt='';
      if(basisAt){
        var d=new Date(basisAt);
        // 미국 장 마감 시각을 KST(브라우저 로컬)로 표시하면 새벽 마감이 다음날 날짜로 밀려 보인다(예: 목요일 마감이 금요일로 표기).
        // 실제 거래일은 뉴욕 현지 날짜 기준이라 America/New_York 타임존으로 월/일을 뽑는다.
        if(!isNaN(d)){
          var p=new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',month:'numeric',day:'numeric'}).formatToParts(d);
          var mo=p.find(function(x){return x.type==='month';}), da=p.find(function(x){return x.type==='day';});
          if(mo&&da) dt=mo.value+'.'+da.value+' ';
        }
      }
      b.innerHTML='<span class="dot"></span>장 마감 · '+dt.trim()+'<span class="ue-live-tail"> 종가 기준</span>';
    }
  }
  /* 폴링 후 행 가격을 in-place 갱신 — 카운트업 + 방향색 플래시(상단 대표주 위젯과 동일 효과) */
  function animatePx(el, toUsd){
    var from=parseFloat(el.getAttribute('data-usd'));
    el.setAttribute('data-usd', toUsd);
    if(!isFinite(from) || from===toUsd){ el.textContent=fmtPx(toUsd); return; }
    var dir=toUsd>from?1:-1;
    el.classList.remove('ue-flash-up','ue-flash-dn'); void el.offsetWidth;
    el.classList.add(dir>0?'ue-flash-up':'ue-flash-dn');
    var start=performance.now(), dur=550;
    function step(now){
      var t=Math.min(1,(now-start)/dur), e=1-Math.pow(1-t,3); // easeOutCubic
      el.textContent=fmtPx(from+(toUsd-from)*e);
      if(t<1) requestAnimationFrame(step); else el.textContent=fmtPx(toUsd);
    }
    requestAnimationFrame(step);
  }
  function patch(){
    // 가격은 data-sym 칸을 그 자리에서 카운트업, 등락·막대·상승 개수는 다시 그린다(행 순서에 기대지 않는다)
    var pxs={};
    gridEl.querySelectorAll('.px[data-sym]').forEach(function(el){ pxs[el.getAttribute('data-sym')]=el.getAttribute('data-usd'); });
    renderGrid();
    gridEl.querySelectorAll('.px[data-sym]').forEach(function(el){
      var sym=el.getAttribute('data-sym'), d=dataBySym[sym]||{};
      if(pxs[sym]!=null && typeof d.price==='number'){ el.setAttribute('data-usd', pxs[sym]); animatePx(el, d.price); }
    });
    renderMacro();
  }
  function load(){
    if(!loaded) skeleton();
    var syms=TICKERS.map(function(t){return t.sym;}).concat([NASDAQ]).join(',');
    Promise.all([
      fetch('/api/stocks-live?us='+encodeURIComponent(syms),{cache:'no-store'}).then(function(r){return r.ok?r.json():null;}).catch(function(){return null;}),
      fetch('/api/market',{cache:'no-store'}).then(function(r){return r.ok?r.json():null;}).catch(function(){return null;})
    ]).then(function(res){
      var live=res[0], mkt=res[1];
      if(live&&Array.isArray(live.us)){
        live.us.forEach(function(x){ dataBySym[x.sym]={price:x.price,changePct:x.changePct,state:x.state,tradedAt:x.tradedAt}; });
        var rep=null;
        live.us.forEach(function(x){ if(x.sym===NASDAQ) rep=x; });
        if(!rep) rep=live.us[0]||{};
        sessionState=rep.state||'closed';
        basisAt=rep.tradedAt||null;
        // 하나라도 정규장·프리장·애프터장이면 라이브로 간주
        isLive=live.us.some(function(x){ return x.state==='open'||x.state==='pre'||x.state==='post'; });
      }
      if(mkt&&mkt.forex&&typeof mkt.forex.price==='number') fx=mkt.forex.price;
      if(mkt&&mkt.vix&&typeof mkt.vix.price==='number') vix=mkt.vix;
      if(!fx&&!loaded){ cur='usd'; syncToggle(); }
      if(!loaded){ loaded=true; render(); }
      else patch();
      updateLiveBadge();
      setPoll(isLive ? POLL_LIVE : POLL_IDLE);
    });
  }
  var pollId=null, POLL_LIVE=60000, POLL_IDLE=60000, curPoll=0;
  function setPoll(ms){
    if(pollId && curPoll===ms) return;
    if(pollId) clearInterval(pollId);
    curPoll=ms; pollId=setInterval(load, ms);
  }
  window.__ueLoad=function(){
    load();
    if(!pollId) setPoll(POLL_LIVE);
  };
  window.__ueStop=function(){ if(pollId){ clearInterval(pollId); pollId=null; curPoll=0; } };
  // 테스트 훅 — 데이터를 주입하고 두 묶음 렌더 결과를 본다(us-evening.test.mjs)
  window.__usEvening={LEAD:LEAD, AI_GROUPS:AI_GROUPS, TICKERS:TICKERS, gridEl:gridEl, macroEl:macroEl,
    set:function(d,v,f,c){ dataBySym=d||{}; vix=v||null; fx=f||null; cur=c||'krw'; }, render:render};
  function syncToggle(){
    document.querySelectorAll('#ue-toggle button').forEach(function(b){
      b.classList.toggle('on', b.getAttribute('data-cur')===cur);
    });
  }
  document.querySelectorAll('#ue-toggle button').forEach(function(b){
    b.addEventListener('click',function(){ cur=b.getAttribute('data-cur'); syncToggle(); render(); });
  });
  syncToggle();
  function kstNow(){ return new Date(Date.now()+9*3600*1000); }
  var todayKospiReady=null;   // null=미확인. 평일 공휴일이면 오늘 코스피 브리핑이 ready가 아님 → 비거래일로 보고 종일 노출.
  // 노출 조건: 평일 17:00~익일 09:00(코스피 개장 전까지 — §68 ⑦, 아침 카드 아래 밤사이 미국). 주말(토·일)·평일 공휴일은 종일 노출.
  function isEvening(d){
    var wd=d.getUTCDay();
    if(wd===0||wd===6) return true;                    // 주말 종일
    var hm=d.getUTCHours()*60+d.getUTCMinutes();
    if(hm>=1020 || hm<540) return true;                // 평일 17:00~익일 09:00
    return todayKospiReady===false;                    // 평일 공휴일(오늘 코스피 미생성) = 비거래일 → 종일 노출
  }
  // 개발용 ?slot=(home-hero.js와 같은 값) — 시간대별 화면을 지금 시각과 상관없이 보려고 노출만 따라간다(§68).
  function devSlot(){ try{ return new URLSearchParams(location.search).get('slot'); }catch(e){ return null; } }
  window.ueGate=function(){
    var dev=devSlot();
    var ev=dev ? /^(morning|evening|weekend)$/.test(dev) : isEvening(kstNow());
    box.style.display = ev ? '' : 'none';
    var home=document.getElementById('home');
    if(home) home.classList.toggle('ue-on', ev);   // 마감 시간대 블록 순서(stocks-home.css slot-close.ue-on)
    if(ev) window.__ueLoad(); else window.__ueStop();
  };
  // 오늘 코스피 브리핑 ready 여부로 비거래일(공휴일) 판별 — 서버 휴일 로직과 정합. 확인 후 게이트 재평가.
  fetch('/data/briefings-list.json',{cache:'no-store'}).then(function(r){return r.ok?r.json():null;}).then(function(j){
    var today=kstNow().toISOString().slice(0,10), s=j&&j.slots&&j.slots[today];
    todayKospiReady = !!(s&&s.kospi&&s.kospi.state==='ready');
    window.ueGate();
  }).catch(function(){});
  window.ueGate();
  setInterval(window.ueGate, 5*60*1000);
})();

/* 국면별 섹션 순서 — 코스피가 닫혀 있으면 '밤사이 미국 반도체 시황'이 주인공.

   국면 (KST)                                히어로             근거
   ─────────────────────────────────────────────────────────────────────────────
   day  거래일 07:30~17:00                   (원래 순서)        코스피 실시간이 주인공
   그 외 전부(평일 저녁·심야·주말·공휴일)     밤사이 미국 반도체  코스피가 닫힌 뒤엔 미국 시황이 주인공

   17:00(거래일 종료)부터 바로 올린다 — 사용자 지시(2026-07-27). 이전에는 미국 정규장
   (22:30~05:00)에만 올리고 그 전 평일 저녁엔 '지금 이시각 추정가'(HL 24h)를 위에 뒀는데,
   프리마켓이 얇다는 이유로 5시간 넘게 미국 시황이 아래에 깔려 있는 게 실제 관심 흐름과 어긋났다.
   주말·공휴일도 같은 규칙으로 묶는다 — 이때 위에 오는 건 직전 미국장(금요일) 시황이라
   HL 24h 추정가보다 주말 방문자에게 읽을거리가 된다.

   phase()의 us_open/quiet 구분은 순서 결정에는 더 이상 쓰이지 않지만, 국면 판정 자체를
   회귀 테스트(stocks-home.test.mjs)가 고정하고 있어 그대로 둔다.

   상단 코스피 지수 스트립(배지줄·strip·수급)은 국면과 무관하게 항상 최상단 고정 —
   한때 us_open·quiet에서 아래로 내렸으나, 화면 중앙에 떠 있는 게 어색하다는 피드백(2026-07-26)으로
   되돌림. 주말·야간에도 이 자리를 지킨다.

   ⚠️ 재배치는 페이지 로드 시점 1회만. 국면 경계(22:30·05:00 등)가 보는 도중 지나가도
   블록이 튀지 않게 한다 — 인터벌 재평가를 넣지 말 것. */
(function(){
  // 한국 거래일 낮 — 코스피 실시간이 주인공인 구간.
  function krxDay(){
    if(window.krIsKospiHoliday&&window.krIsKospiHoliday()) return false;
    var d=new Date(Date.now()+9*3600*1000), wd=d.getUTCDay();
    if(wd===0||wd===6) return false;
    var t=d.getUTCHours()*60+d.getUTCMinutes();
    return t>=450&&t<1020;                       // 07:30~17:00
  }
  // 미국 정규장 — 서머타임 때문에 KST 고정 시각(22:30/23:30)으로 잡으면 반년마다 틀린다.
  // 뉴욕 현지 시각으로 직접 판정한다. 미국 공휴일은 여기서 거르지 않지만(장 마감 데이터가
  // 그대로 보일 뿐 순서만 바뀜) 배지·수치는 stocks-live의 세션 판정이 정확히 표시한다.
  function usRegularOpen(){
    var p=new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',weekday:'short',hour:'2-digit',minute:'2-digit',hour12:false}).formatToParts(new Date());
    function v(t){var x=p.find(function(e){return e.type===t;});return x?x.value:'';}
    var wd=v('weekday');
    if(wd==='Sat'||wd==='Sun') return false;
    var t=(+v('hour'))*60+(+v('minute'));
    return t>=570&&t<960;                        // 09:30~16:00 ET
  }
  function phase(){
    if(krxDay()) return 'day';
    if(usRegularOpen()) return 'us_open';
    return 'quiet';
  }
  // 회귀 테스트 훅 — stocks-home.test.mjs가 시각별 국면 판정을 고정한다(DOM 이동은 여기서 검증 못 함).
  // DOM 조회보다 앞에 둔다. 아래 가드에 걸려 조기 return하면 훅이 안 걸린다.
  window.__layoutPhase=phase;

  var ph=phase();
  if(ph==='day') return;                         // 원래 순서 그대로

  var usEve=document.getElementById('us-evening');
  var usLinked=document.getElementById('us-linked-widget');
  var why=document.getElementById('why-moved');
  // (2026-09-17) 기준점이던 모멘텀 블록이 사라져 바로 뒤 섹터·특이 신호 묶음(.home-cols) 앞으로 꽂는다.
  var anchor=document.querySelector('#home .home-cols');
  if(!usEve||!usLinked||!why||!anchor) return;
  // (2026-09-11) 장중 곡선 블록이 사라져 뉴스·곡선 자리바꿈은 더 이상 없다. 섹션 순서만 바꾼다.
  // 곡선 조회에 실패하면 여기서 return해 아래 재배치까지 막히던 의존도 함께 걷어냈다.
  // anchor 앞에 원하는 순서대로 다시 꽂는다. 위쪽 시간대 카드(#home-hero)·지수 스트립은 건드리지 않는다.
  // day가 아닌 국면(= 코스피가 닫혀 있음)은 전부 '밤사이 미국 반도체 시황'을 위로 — 17:00부터 적용.
  // (2026-09-22) '어제랑 비교해서' 마감 곡선(#vs-root)은 오늘 미국 브리핑이 발행될 때까지 남으므로 섹터별 대표 종목 바로 위에 둔다.
  // 발행 뒤엔 vs-yesterday.js가 영역을 숨겨 자리만 옮겨진 채 보이지 않는다.
  [usEve, usLinked, document.getElementById('vs-root')]
    .forEach(function(n){ if(n) anchor.parentNode.insertBefore(n, anchor); });
})();

/* ── 블록 5 (원본 index.html) ── */
/* 날짜 규칙(허브 전역) — 장중=오늘, 마감/주말/휴일=M/D(요일). 기준일은 스냅샷 generated_at. */
var _asOfYmd=null; // 마지막 거래일(스냅샷 날짜). SNAP 로드 시 주입.
function hubMarketOpen(){if(window.krIsKospiHoliday&&window.krIsKospiHoliday())return false;var d=new Date(Date.now()+9*3600*1000);var m=d.getUTCHours()*60+d.getUTCMinutes();return m>=540&&m<=930;}
function fmtKoDate(ymd){if(!ymd)return '';var p=ymd.split('-');var dt=new Date(+p[0],+p[1]-1,+p[2]);return (+p[1])+'/'+(+p[2])+'('+'일월화수목금토'[dt.getDay()]+')';}
function lastTradingDay(ymd){
  if(!ymd)return ymd;
  var p=ymd.split('-'),dt=new Date(+p[0],+p[1]-1,+p[2]);
  var d=dt.getDay();
  if(d===0) dt.setDate(dt.getDate()-2);
  else if(d===6) dt.setDate(dt.getDate()-1);
  return dt.getFullYear()+'-'+String(dt.getMonth()+1).padStart(2,'0')+'-'+String(dt.getDate()).padStart(2,'0');
}
function applyAsOf(){
  var open=hubMarketOpen();
  var todayYmd=new Date(Date.now()+9*3600*1000).toISOString().slice(0,10);
  var baseYmd=lastTradingDay(_asOfYmd||todayYmd);
  var plain=open?'오늘':fmtKoDate(baseYmd);
  document.querySelectorAll('.ds-date').forEach(function(e){e.textContent=plain;});
  var asof=fmtKoDate(baseYmd)+' 종가';
  document.querySelectorAll('.ds-asof').forEach(function(e){e.textContent=open?'오늘 실시간':asof;});
  var sigT=document.getElementById('sig-title');
  if(sigT) sigT.textContent=(open?'오늘의':plain)+' 특이 신호';
}
applyAsOf();
const navHistory=[];
/* ── URL 체계 (실서비스 라우팅 기준) ──────────────────────────────
   /stocks/                        홈 허브 (랭킹 + 섹터 + 검색)
   /stocks/etf/{code}/             ETF 상세    예) /stocks/etf/069500/
   /stocks/sectors/{key}/          섹터 페이지 예) /stocks/sectors/semicon/
     keys: semicon | power | defense | ship | battery | auto | bio | finance
   /stocks/volume/                 거래량 랭킹 전체
   /stocks/gainers/                상승 랭킹 전체
   /stocks/losers/                 하락 랭킹 전체
   /stocks/passive/                패시브 민감주 랭킹
   /stocks/income/                 배당 인컴 설계기
   /chips/                         AI 반도체 칩보드 (외부 chipboard.vercel.app)
   /briefings/                     브리핑 허브 (기존 서비스)
─────────────────────────────────────────────────────────────── */
let _stockToastT=null;
function _stockToast(msg){
  let t=document.getElementById('stock-toast');
  if(!t){t=document.createElement('div');t.id='stock-toast';
    t.style.cssText='position:fixed;left:50%;bottom:32px;transform:translateX(-50%);background:rgba(17,24,39,.92);color:#fff;font-size:13px;font-weight:600;padding:10px 16px;border-radius:10px;z-index:9999;opacity:0;transition:opacity .2s;pointer-events:none;';
    document.body.appendChild(t);}
  t.textContent=msg;t.style.opacity='1';
  clearTimeout(_stockToastT);_stockToastT=setTimeout(()=>{t.style.opacity='0';},1800);
}
// 종목 클릭 → 그 종목의 섹터 페이지(2026-10-26 종목 상세 페이지 제거 — 사용자 결정, §36).
// 홈의 종목 클릭 진입점(검색·특이신호·섹터 카드 등)이 전부 이 함수를 지난다. 섹터는 스냅샷(STOCK_LIST)에서 찾고,
// 아직 못 불러왔거나 유니버스 밖 종목이면 막지 않고 안내만 띄운다.
// 섹터 키 → 이름. goStock이 전역 함수라 이 표도 전역에 둔다 — 아래 IIFE 안에만 있으면 검색에서 종목을 눌렀을 때
// ReferenceError로 이동하지 못했다(2026-10-27 발견).
var SECTOR_LABELS={semicon:'반도체',battery:'2차전지',auto:'자동차',defense:'방산',ship:'조선',bio:'바이오',finance:'금융',power:'전력기기'};
function goStock(code){
  var s=STOCK_LIST.find(function(x){return x.code===code;});
  if(s&&s.sector&&SECTOR_LABELS[s.sector]){
    dsTrackEvent('stock_sector_open',{stock_code:code,sector:s.sector});
    location.href='/stocks/sector/'+s.sector+'/';
  }else{
    _stockToast('섹터 정보를 불러오는 중이에요. 잠시 뒤 다시 눌러 주세요.');
  }
}
// 허브 내부 화면 전환 — 유효한 screen이면 그 화면, 섹터 키 등은 반도체 섹터로
function goHub(screen){if(!screen){go('home');return;}if(document.getElementById(screen))go(screen);else go('home');}
// 탭·화면별 트래픽을 GA4에서 구분해 볼 수 있도록 가상 pageview를 보낸다.
// index.html의 gtag config에 send_page_view:false를 줘서 자동 최초 pageview를 껐고,
// 이 함수가 최초 진입(아래 해시 복원 IIFE)과 이후 모든 화면 전환(go()) 양쪽에서 한 번씩만 호출되므로
// 실제 조회 1회당 정확히 pageview 1건이 잡힌다(자동 pageview와의 중복 없음).
function dsTrackPageview(){
  if(typeof gtag!=='function')return;
  gtag('event','page_view',{page_title:document.title,page_location:location.href,page_path:location.pathname+location.hash});
}
// 행동 이벤트 공용 진입점. gtag가 없으면(차단·로드 실패) 조용히 넘어간다 —
// 계측 실패가 기능을 막으면 안 된다. 개인 식별 정보는 절대 넣지 않는다(종목코드·검색어만).
function dsTrackEvent(name,params){
  if(typeof gtag!=='function')return;
  gtag('event',name,params||{});
}
function go(id,noHistory){
  const el=document.getElementById(id);if(!el||!el.classList.contains('screen'))return;
  if(!noHistory){const cur=document.querySelector('.screen.on');if(cur&&cur.id!==id)navHistory.push(cur.id);}
  document.querySelectorAll('.screen').forEach(s=>s.classList.remove('on'));
  el.classList.add('on');
  window.scrollTo({top:0,behavior:'smooth'});
  history.pushState({screen:id},'','#'+id);
  // pushState는 hashchange를 발생시키지 않으므로 서브탭 강조를 직접 갱신한다.
  // 프로젝트의 옵셔널 호출 관례를 따라 결합을 최소로 둔다 — 없으면 그냥 넘어간다.
  if(typeof window.dsSubnavSync==='function')window.dsSubnavSync();
  dsTrackPageview();
}
function goBack(){const prev=navHistory.pop();go(prev||'home',true);}
window.addEventListener('popstate',e=>{const id=(e.state&&e.state.screen)||(location.hash.slice(1)||'home');go(id,true);});
// 진입 시 해시(#signals-all 등)가 있으면 해당 화면 복원 — standalone에서 돌아올 때 사용
(function(){const h=location.hash.slice(1);if(!h){dsTrackPageview();return;}document.getElementById(h)?go(h,true):go('home',true);})();
function switchTab(hero,tab,el){
  const prefix=hero+'-';
  document.querySelectorAll('#hero-'+hero+' .ctabs a').forEach(a=>a.classList.remove('on'));
  el.classList.add('on');
  ['5d','1m','3m','1y'].forEach(t=>{
    const p=document.getElementById(prefix+t);
    if(p) p.classList.toggle('hidden',t!==tab);
  });
}

/* 차트 툴팁 */
const CHART_DATA={
  'etf-5d':{dates:['06-06','06-09','06-10','06-11','06-12'],prices:[36150,36250,36380,36500,36610],fmt:v=>'종가 : ₩'+v.toLocaleString()},
  'etf-1m':{dates:['05-14','05-21','05-28','06-04','06-12'],prices:[34800,35200,35600,36100,36610],fmt:v=>'종가 : ₩'+v.toLocaleString()},
  'etf-3m':{dates:['03-14','04-04','04-25','05-16','06-12'],prices:[33200,34000,34800,35600,36610],fmt:v=>'종가 : ₩'+v.toLocaleString()},
  'etf-1y':{dates:['25.06','25.09','25.12','26.03','26.06'],prices:[29800,31000,33500,34200,36610],fmt:v=>'종가 : ₩'+v.toLocaleString()},
};
document.querySelectorAll('.chart-wrap').forEach(wrap=>{
  const tt=document.createElement('div');tt.className='chart-tt';
  const cross=document.createElement('div');cross.className='chart-cross';
  wrap.appendChild(tt);wrap.appendChild(cross);
  wrap.addEventListener('mousemove',e=>{
    const svg=wrap.querySelector('.chart-svg');if(!svg)return;
    const svgRect=svg.getBoundingClientRect();
    const wrapRect=wrap.getBoundingClientRect();
    const frac=Math.max(0,Math.min(1,(e.clientX-svgRect.left)/svgRect.width));
    const pane=wrap.closest('.cpane');if(!pane||pane.classList.contains('hidden'))return;
    const d=CHART_DATA[pane.id];if(!d)return;
    const n=d.dates.length;
    const idx=Math.min(n-1,Math.max(0,Math.round(frac*(n-1))));
    tt.innerHTML=`<div class="ttd">${d.dates[idx]}</div>${d.fmt(d.prices[idx])}`;
    const xInWrap=e.clientX-wrapRect.left;
    tt.style.left=xInWrap+'px';
    tt.style.display='block';
    cross.style.left=xInWrap+'px';
    cross.style.display='block';
  });
  wrap.addEventListener('mouseleave',()=>{tt.style.display='none';cross.style.display='none';});
});

/* 특이 신호 화면 상태 */
let SIGNALS_HOME=[];  // 홈 특이신호 (정렬 재적용용)
let SIGNALS_ALL=[];   // 특이 신호 전체(더보기 화면용) — /api/signals.signalsAll
let SIG_ASOF=null;    // 신호 기준일 메타(제목 prefix용)

/* AI 뱃지 툴팁 — position:fixed (카드 overflow에 안 잘림) */
const tip=document.getElementById('tip');
function tipHTML(el){
  if(el.dataset.tip)
    return `<div class="tt">${el.dataset.tipTitle||'안내'}</div><div class="bd">${el.dataset.tip}</div>`;
  if(el.classList.contains('badge-info-btn'))
    return `<div class="tt">AI 뱃지 안내</div><div class="bd" style="line-height:1.6">
      <div style="display:flex;align-items:flex-start;gap:7px;margin-bottom:6px"><span class="aip" style="font-size:11px;padding:2px 7px;flex:none">AI 78</span><span><b>Claude 픽</b> — AI 브리핑이 오늘 선택한 종목</span></div>
      <div style="display:flex;align-items:flex-start;gap:7px;margin-bottom:6px"><span class="ais" style="font-size:11px;padding:2px 7px;flex:none">신호 64</span><span><b>기술신호 상승</b> — 이평선·모멘텀 종합 58↑</span></div>
      <div style="display:flex;align-items:flex-start;gap:7px;margin-bottom:6px"><span class="aid" style="font-size:11px;padding:2px 7px;flex:none">신호 42</span><span><b>기술신호 약세</b> — 이평선 아래 42↓</span></div>
      <div style="display:flex;align-items:flex-start;gap:7px"><span class="ax" style="font-size:11px;flex:none">—</span><span><b>신호 없음</b> — 데이터 부족(상장 200일↓)</span></div>
    </div>`;
  const n=(el.textContent.match(/\d+/)||['?'])[0];
  if(el.classList.contains('vol-surge-badge')){
    const m=el.textContent.match(/×([\d.]+)/);const mult=m?m[1]:'N';
    return `<div class="tt" style="color:#E8590C">🔶 거래량 ×${mult} 급증</div><div class="bd">오늘 거래량이 <b>최근 20일 평균 대비 ${mult}배</b>예요. 수치가 높을수록 <b>이례적인 거래 폭증</b>이에요. 외국인·기관 수급이 함께 들어왔다면 의미 있는 수급 유입 신호로 볼 수 있어요.</div>`;
  }
  if(el.classList.contains('aip'))
    return `<div class="tt" style="color:#006EFF">🔵 AI 상승확률 ${n}%</div><div class="bd">오늘 AI 브리핑이 <b>픽한 종목</b>이에요. Claude가 <b>뉴스·수급·차트를 종합 분석</b>해 상승 방향에 둔 확률이에요. 신뢰도 ${n}%. 더블샷의 프리미엄 신호예요.</div>`;
  if(el.classList.contains('ais'))
    return `<div class="tt" style="color:#006EFF">⚪ 기술신호 ${n}점</div><div class="bd"><b>전 종목</b>에 매기는 규칙 기반 점수(0~100)예요. <b>20일선·200일선 위치 + 골든크로스 + 최근 5일 모멘텀</b>을 합산해요. AI 예측이 아닌 <b>기술적 참고 신호</b>예요. 58점↑은 상승 우위.</div>`;
  if(el.classList.contains('aid'))
    return `<div class="tt" style="color:#E03131">🔴 기술신호 ${n}점 · 약세</div><div class="bd">이동평균선 아래 등 <b>약세 신호가 우세</b>한 구간이에요. 42점↓은 약세로 분류돼요. 규칙 기반 참고 신호예요.</div>`;
  return `<div class="tt" style="color:#6B7280">— 신호 없음</div><div class="bd">상장·거래일이 <b>200일 미만</b>이거나 데이터가 부족해 점수를 산출하지 못했어요.</div>`;
}
function showTip(e){
  tip.innerHTML=tipHTML(e.currentTarget);tip.style.display='block';moveTip(e);
}
function moveTip(e){
  const pad=14,w=tip.offsetWidth,h=tip.offsetHeight;
  let x=e.clientX+16,y=e.clientY+16;
  if(x+w+pad>innerWidth)x=e.clientX-w-16;
  if(y+h+pad>innerHeight)y=e.clientY-h-16;
  tip.style.left=Math.max(pad,x)+'px';tip.style.top=Math.max(pad,y)+'px';
}
function hideTip(){tip.style.display='none';}
document.querySelectorAll('.aip,.ais,.aid,.ax,.badge-info-btn,.vol-surge-badge').forEach(el=>{
  el.addEventListener('mouseenter',showTip);
  el.addEventListener('mousemove',moveTip);
  el.addEventListener('mouseleave',hideTip);
});
// 물음표(help-q) 안내 — 호버 가능한 기기(마우스)는 기존 툴팁, 그 외(터치)는 탭 시 모달.
// hover:none 기기에서도 mouseenter가 "고스트 이벤트"로 한 번 발화해 툴팁이 붙어버리는 걸 막기 위해
// help-q만 별도로 분기하고, 호버 리스너 자체를 붙이지 않는다(모바일).
(function(){
  const canHover=matchMedia('(hover:hover) and (pointer:fine)').matches;
  const bg=document.getElementById('help-modal-bg'), body=document.getElementById('help-modal-body');
  function openHelpModal(el){
    if(!bg||!body) return;
    body.innerHTML=tipHTML(el);
    bg.classList.add('open');
  }
  function closeHelpModal(){ if(bg) bg.classList.remove('open'); }
  document.querySelectorAll('.help-q').forEach(el=>{
    if(canHover){
      el.addEventListener('mouseenter',showTip);
      el.addEventListener('mousemove',moveTip);
      el.addEventListener('mouseleave',hideTip);
    }else{
      el.addEventListener('click',e=>{ e.preventDefault(); openHelpModal(el); });
    }
  });
  if(bg){
    bg.addEventListener('click',e=>{ if(e.target===bg) closeHelpModal(); });
    document.getElementById('help-modal-close')?.addEventListener('click',closeHelpModal);
    document.addEventListener('keydown',e=>{ if(e.key==='Escape') closeHelpModal(); });
  }
})();
// 검색 유니버스 — 스냅샷 로드 시 채움. [{code,name,sector}]
let STOCK_LIST=[];
let _sqSel=0;
const _SECKO={semicon:'반도체',battery:'2차전지',auto:'자동차',defense:'방산',ship:'조선',bio:'바이오',finance:'금융',power:'전력기기'};
function renderSearch(){
  const q=(document.getElementById('sq').value||'').trim().toLowerCase();
  const arr=STOCK_LIST.filter(s=>!q||s.name.toLowerCase().includes(q)||s.code.includes(q)).slice(0,12);
  _sqSel=0;
  const box=document.getElementById('sq-results');
  if(!arr.length){box.innerHTML='<div class="grp__t">종목</div><div class="res" style="cursor:default;color:var(--muted);font-size:13px;">'+(STOCK_LIST.length?'검색 결과가 없어요.':'종목을 불러오는 중…')+'</div>';return;}
  box.innerHTML='<div class="grp__t">종목</div>'+arr.map((s,i)=>
    '<a class="res'+(i===0?' sel':'')+'" data-code="'+s.code+'" onclick="closeSearch();goStock(\''+s.code+'\')">'
    +'<span class="ico num">'+s.name.slice(0,1)+'</span>'
    +'<span class="n3">'+s.name+' <small class="num">'+s.code+' · '+(_SECKO[s.sector]||s.sector||'')+'</small></span></a>').join('');
}
function _sqMove(d){
  const rows=document.querySelectorAll('#sq-results .res[data-code]');if(!rows.length)return;
  if(rows[_sqSel])rows[_sqSel].classList.remove('sel');
  _sqSel=(_sqSel+d+rows.length)%rows.length;
  rows[_sqSel].classList.add('sel');rows[_sqSel].scrollIntoView({block:'nearest'});
}
function _sqEnter(){const r=document.querySelectorAll('#sq-results .res[data-code]')[_sqSel];if(r){closeSearch();goStock(r.getAttribute('data-code'));}}
function openSearch(){document.getElementById('ov').classList.add('on');renderSearch();setTimeout(()=>document.getElementById('sq').focus(),50);}
function closeSearch(){document.getElementById('ov').classList.remove('on');document.getElementById('sq').value='';}
(function(){const sq=document.getElementById('sq');if(!sq)return;
  sq.addEventListener('input',renderSearch);
  // 검색은 키 입력마다 renderSearch가 도는데, 그때마다 이벤트를 쏘면 한 번의 검색이
  // 글자 수만큼 집계된다. 타이핑이 멎은 뒤 한 번만 보낸다.
  let _sqTrackT;
  sq.addEventListener('input',()=>{
    clearTimeout(_sqTrackT);
    _sqTrackT=setTimeout(()=>{
      const q=(sq.value||'').trim();
      if(q.length<2)return;
      const hits=STOCK_LIST.filter(s=>s.name.toLowerCase().includes(q.toLowerCase())||s.code.includes(q)).length;
      dsTrackEvent('search',{search_term:q,result_count:hits});
    },800);
  });
  sq.addEventListener('keydown',e=>{
    if(e.key==='ArrowDown'){e.preventDefault();_sqMove(1);}
    else if(e.key==='ArrowUp'){e.preventDefault();_sqMove(-1);}
    else if(e.key==='Enter'){e.preventDefault();_sqEnter();}
  });
})();
document.addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();openSearch();}if(e.key==='Escape')closeSearch();});

/* 배당 인컴 설계기는 /stocks/income-designer/ 전용 페이지로 이관됨(d52a4ca8).
   홈에 남아 있던 원본 마크업·로직은 도달 경로가 없어 2026-08-23에 제거했다.
   하드코딩된 INCOME_UNIVERSE(2026-06-11 스냅샷)도 함께 사라졌다 — §20 정적 데이터 금지. */


/* ── 블록 6 (원본 index.html) ── */
/* 더블샷 브리핑 커넥터(#brief-strip)는 2026-10-26 시간대 카드(home-hero.js, §68)로 바뀌었다. */

/* ── 블록 7 (원본 index.html) ── */


/* ── 블록 8 (원본 index.html) ── */
/* 외국인 보유율·섹터 브라우저·특이 신호 — stocks-snapshot.json·/api/signals 실측 배선 */
(function(){
  var SNAP=null;
  var SIG_SECTORS=null; // /api/signals가 내려주는 전 섹터 라이브 평균 (장중 5분 갱신)
  function sparkSvg(vals,color){
    if(!vals||vals.length<2) return '';
    var n=vals.length,min=Math.min.apply(null,vals),max=Math.max.apply(null,vals),rng=(max-min)||1;
    var pts=vals.map(function(v,i){var x=(i/(n-1))*78;var y=19-((v-min)/rng)*16;return x.toFixed(1)+','+y.toFixed(1);}).join(' ');
    var last=pts.split(' ').pop().split(',');
    return '<svg viewBox="0 0 78 22" style="width:78px;height:22px;display:block;overflow:visible;"><polyline points="'+pts+'" fill="none" stroke="'+color+'" stroke-width="1.5"/><circle cx="'+last[0]+'" cy="'+last[1]+'" r="2.2" fill="#fff" stroke="'+color+'" stroke-width="1.5"/></svg>';
  }
  function secLbl(s){ return SECTOR_LABELS[s]||s||''; }
  var SECTOR_KEY_OF={}; Object.keys(SECTOR_LABELS).forEach(function(k){ SECTOR_KEY_OF[SECTOR_LABELS[k]]=k; });
  // 섹터 화면(#sector)은 2026-09-02에 제거됐다. 홈에서 섹터 상세 페이지로 가는 링크가
  // 0개였고(JS도 주입하지 않았다) '패시브 쏠림'은 실측 소스 없는 자리표시자였다.
  // 섹터 상세는 /stocks/sector/{key}/ 정적 페이지가 계속 담당한다.
  // SECTOR_LABELS는 전역(goStock 위)에 있다 — 특이 신호·섹터 막대·goStock이 같이 쓴다.
  /* ── 오늘의 특이 신호 · 신호별 랭킹 · ETF 4카드 — /api/signals 실측 배선 ── */
  function phaseLabel(phase){ return phase==='intraday' ? '<span class="dot"></span>장중 실시간 · 2분 간격' : '장 마감 기준'; }
  function setBadge(id, phase){ var b=document.getElementById(id); if(!b) return; b.className=phase==='intraday'?'upd-badge is-live':'close-pill'; b.innerHTML=phaseLabel(phase); }
  function badgeHtml(b){ var flow=/^(외국인|기관)/.test(b); return '<span class="bdg'+(flow?' flow':'')+'">'+b+'</span>'; }
  function asOfPrefix(asOf){ return (asOf && !asOf.isToday && asOf.label) ? asOf.label : '오늘의'; }
  // 신호 1건 → D안 마크업(i===0이면 히어로, 나머지는 컴팩트 행). 홈·더보기 화면 공용.
  // 종목 상세 페이지는 없다(2026-10-26 제거) — 그 종목의 섹터 페이지로 보내고, 섹터를 모르면 링크하지 않는다.
  function sigItemHtml(s,i,heroFlag){
    var flat=Math.abs(s.pct)<0.05;   // 0.0%로 보이는 값은 회색(2026-10-29)
    var lc=flat?'var(--muted)':s.dir==='up'?'var(--up)':'var(--dn)', sign=!flat&&s.pct>0?'+':'';
    var badges=(s.badges||[]).map(badgeHtml).join('');
    var secKey=SECTOR_KEY_OF[s.sector];
    var tag=secKey?'a':'div';
    var attrs=secKey?' href="/stocks/sector/'+secKey+'/"':'';
    var nolink=secKey?' is-sector':' is-nolink';
    var goArrow=secKey?'<span class="sig-sec">'+SECTOR_LABELS[secKey]+' 보기 →</span>':'';   // 라벨은 우리 상수라 이스케이프 불필요
    if(i===0){
      return '<'+tag+' class="sig-hero'+nolink+'"'+attrs+'>'
        +'<span class="sig-flag">'+(heroFlag||'오늘 가장 눈에 띄는 신호')+'</span>'
        +'<div class="sig-htop"><span class="sig-hnm">'+s.name+' <small>'+s.code+' · '+s.sector+'</small></span>'
        +'<span class="sig-hpct" style="color:'+lc+';">'+sign+s.pct.toFixed(1)+'%</span></div>'
        +'<div class="sig-hbadges">'+badges+'</div>'
        +'<div class="sig-hwhy">'+(s.why||'')+'</div>'+goArrow+'</'+tag+'>';
    }
    return '<'+tag+' class="sig-row'+nolink+'"'+attrs+'>'
      +'<span class="sig-rmain"><span class="sig-rnm">'+s.name+' <small>'+s.code+' · '+s.sector+'</small></span>'
      +'<span class="sig-rbadges">'+badges+'</span></span>'
      +'<span class="sig-rpct" style="color:'+lc+';">'+sign+s.pct.toFixed(1)+'%</span>'+goArrow+'</'+tag+'>';
  }
  // 특이 신호는 상승률순(많이 오른 종목이 위) 하나로만 보여준다(2026-10-27). 홈은 그중 위 3개.
  var SIG_HOME_N=3;
  function sigByRise(list){ return (list||[]).slice().sort(function(a,b){return (b.pct||0)-(a.pct||0);}); }
  function sigHomeRender(){
    var w=document.getElementById('sig-rows'); if(!w) return;
    var arr = sigByRise(SIGNALS_HOME).slice(0, SIG_HOME_N);
    w.innerHTML=arr.length?arr.map(function(s,i){return sigItemHtml(s,i,'오늘 가장 많이 오른 신호');}).join(''):'';
    w.classList.remove('sig-updated'); void w.offsetWidth; w.classList.add('sig-updated');
    setTimeout(function(){w.classList.remove('sig-updated');}, 600);
  }
  // 테스트 훅 — 존재-게이트(상세 페이지 있는 종목만 링크) 회귀 검증용.
  window.__sigHome={sigItemHtml:sigItemHtml, SIG_HOME_N:SIG_HOME_N, sigByRise:sigByRise};

  function applySignals(d){
    setBadge('sig-upd-badge', d.phase);
    SIGNALS_HOME=d.signals||[];
    SIGNALS_ALL=d.signalsAll||d.signals||[]; SIG_ASOF=d.asOf; sigAllRender();
    var st=document.getElementById('sig-title'); if(st) st.textContent=asOfPrefix(d.asOf)+' 특이 신호';
    sigHomeRender();
    // 전 섹터 라이브 평균을 섹터 막대에 반영
    if(d.sectors) SIG_SECTORS=d.sectors;
    renderSectorBars(); renderSectorBadge();
  }
  /* 특이 신호 전체(더보기) — 상승률순 하나(2026-10-27). 정렬 탭·하락률 순 목록은 뺐다. */
  function sigAllRender(){
    var box=document.getElementById('sigall-rows'); if(!box) return;
    var arr=sigByRise(SIGNALS_ALL);
    box.innerHTML=arr.length?arr.map(function(s,i){return sigItemHtml(s,i,'오늘 최고 상승');}).join(''):'<p class="sig-intro" style="padding:24px 16px;text-align:center;color:var(--muted);">표시할 특이 신호가 없어요.</p>';
    var cnt=document.getElementById('sigall-count'); if(cnt) cnt.textContent=arr.length+'종목';
    var t=document.getElementById('sigall-title'); if(t) t.textContent=asOfPrefix(SIG_ASOF)+' 특이 신호';
  }
  function clearSkel(){ ['sig-rows'].forEach(function(id){var e=document.getElementById(id); if(e&&e.querySelector('.skl')) e.innerHTML='';}); }
  function loadSignals(){
    fetch('/api/signals',{cache:'no-store'}).then(function(r){return r.ok?r.json():null;})
      .then(function(d){ if(d&&!d.error){ applySignals(d); } else { clearSkel(); } })
      .catch(function(){ clearSkel(); });
  }
  function krMarketOpen(){
    if(window.krIsKospiHoliday&&window.krIsKospiHoliday()) return false; // 주말·공휴일
    var m=((new Date().getUTCHours()*60+new Date().getUTCMinutes())+9*60)%(24*60);
    return m>=540&&m<=930;
  }
  /* ── 섹터 한눈에 막대 — /api/signals 섹터 평균, 없으면 stocks-snapshot.json ──
     '섹터별 대표 종목 펼치기'(섹터 탭·종목 카드·한 줄 요약)와 그 영역 전용 조회(/api/stocks-live·/api/intraday)는
     2026-10-27에 뺐다. 막대는 신호 응답이 오면 그 값을, 아니면 스냅샷으로 섹터 평균을 낸다. */
  var SBX_ORDER=['semicon','battery','auto','defense','ship','bio','finance','power'];
  // 장 마감(15:30) 뒤 마감 잡이 스냅샷을 갱신하기(~16:31) 전 — 스냅샷은 어제 종가지만 /api/signals는 장 마감 뒤에도
  // 오늘 정규장 공식 종가(§48)로 섹터 평균을 낸다. 그래서 신호 날짜가 스냅샷보다 새로우면 신호 값을 쓰고, 배지에도 그 날짜를 적는다.
  // 신호 응답이 없거나 스냅샷보다 오래됐을 때만 스냅샷으로 그린다(2026-09-23 날짜 섞임 사고 — 막대 하나는 한 날짜만 쓴다).
  // 예전엔 이 구간에 무조건 스냅샷을 썼는데, 섹터 카드가 빠진(2026-10-27) 뒤로는 어제 값만 남아 마감 직후 한 시간 동안 어제 막대가 보였다(2026-10-29 사용자 지적).
  function sbxSigDate(){ return SIG_ASOF&&SIG_ASOF.date?String(SIG_ASOF.date):null; }
  function sbxSnapBehind(){
    if(!SNAP||!_asOfYmd||krMarketOpen()) return false;
    var sd=sbxSigDate();
    return !(SIG_SECTORS&&sd&&sd>=_asOfYmd);
  }
  function sbxSectorStocks(key){
    if(!SNAP||!SNAP.stocks) return [];
    var arr=[];
    Object.keys(SNAP.stocks).forEach(function(c){var s=SNAP.stocks[c]; if(s.sector===key) arr.push(Object.assign({code:c},s));});
    arr.sort(function(a,b){return (b.change_pct||0)-(a.change_pct||0);});
    return arr;
  }
  // 라이브(SIG_SECTORS, /api/signals가 전 섹터 동시에 내려줌) 우선 — 스냅샷 폴백은 클릭한 탭만
  // 실시간이고 나머지 탭은 정적 스냅샷에 머물러 있다가 클릭 시 갑자기 값이 바뀌는 불일치를 막는다.
  function sbxSectorStat(key){
    if(!sbxSnapBehind()&&SIG_SECTORS&&SIG_SECTORS[key]&&SIG_SECTORS[key].total) return SIG_SECTORS[key];
    var arr=sbxSectorStocks(key), sum=0,up=0,dn=0,wsum=0,wden=0;
    arr.forEach(function(s){
      var p=s.change_pct||0; sum+=p; if(p>0)up++; else if(p<0)dn++;
      var d=(typeof s.close==='number'&&typeof s.vol==='number')?s.close*s.vol:0;
      if(d>0){wsum+=p*d;wden+=d;}
    });
    var avg=arr.length?sum/arr.length:0;
    return {avg:avg, wavg:wden?wsum/wden:avg, up:up, dn:dn, total:arr.length};
  }
  // 화면에 쓰는 섹터 등락률. 거래대금 가중(wavg)이 정본이고 없으면 단순평균으로 폴백한다.
  // 단순평균을 그대로 쓰면 대장주가 끌어올린 날 섹터가 지수와 반대 부호로 뜬다(2026-08-21 반도체).
  function sbxAvgOf(st){ return st&&typeof st.wavg==='number'?st.wavg:((st&&st.avg)||0); }
  // 섹터 통계 소스 — 라이브(SIG_SECTORS) 우선, 없으면 스냅샷 기반
  function tlSectorStats(){
    if(SIG_SECTORS&&!sbxSnapBehind()){
      return SBX_ORDER.map(function(k){var s=SIG_SECTORS[k]; return (s&&s.total)?{key:k,label:SECTOR_LABELS[k],avg:s.avg,total:s.total}:null;}).filter(Boolean);
    }
    return SBX_ORDER.map(function(k){var st=sbxSectorStat(k); return st.total?{key:k,label:SECTOR_LABELS[k],avg:sbxAvgOf(st),total:st.total}:null;}).filter(Boolean);
  }
  // 섹터 8개 등락 막대(§68 ③) — 한 줄 요약과 같은 섹터 평균(tlSectorStats)을 쓴다. 누르면 섹터 페이지.
  function sectorBarsHtml(stats){
    var rows=stats.filter(function(s){ return typeof s.avg==='number'&&isFinite(s.avg); }).sort(function(a,b){ return b.avg-a.avg; });
    if(!rows.length) return '';
    var m=Math.max.apply(null, rows.map(function(r){ return Math.abs(r.avg); }))||1;
    return rows.map(function(r){
      var c=r.avg>0?'up':r.avg<0?'dn':'', w=(Math.abs(r.avg)/m*50).toFixed(1);
      return '<a class="sb" href="/stocks/sector/'+r.key+'/"><span class="sb-n">'+r.label+'</span>'
        +'<span class="sb-bar"><i class="'+c+'" style="width:'+w+'%;'+(r.avg>=0?'left:50%':'right:50%')+'"></i></span>'
        +'<b class="'+c+' num">'+(r.avg>0?'+':r.avg<0?'−':'')+Math.abs(r.avg).toFixed(2)+'%</b></a>';
    }).join('');
  }
  window.__sectorBars={sectorBarsHtml:sectorBarsHtml};
  function renderSectorBars(){
    var w=document.getElementById('sb-bars'); if(!w) return;
    var html=sectorBarsHtml(tlSectorStats());
    if(html) w.innerHTML=html;
  }
  // 막대 머리 배지 — 장중이면 신호 갱신 주기, 아니면 막대가 쓴 데이터의 날짜.
  function renderSectorBadge(){
    var el=document.getElementById('sbx-live'); if(!el) return;
    if(krMarketOpen()){ el.className='sbx-live on'; el.innerHTML='<span class="sl-dot"></span>실시간 장중 · 5분 갱신'; }
    else { var d=sbxSnapBehind()?_asOfYmd:(sbxSigDate()||_asOfYmd); el.className='sbx-live off'; el.innerHTML='<span class="sl-dot"></span>장마감 · '+(d||'')+' 종가 기준'; }
  }
  loadSignals();
  fetch('/data/stocks-snapshot.json',{cache:'no-store'})
    .then(function(r){return r.ok?r.json():null;})
    .then(function(snap){
      SNAP=snap;
      if(SNAP&&SNAP.stocks){
        var _ks=Object.keys(SNAP.stocks);
        STOCK_LIST=_ks.map(function(c){return {code:c,name:SNAP.stocks[c].name,sector:SNAP.stocks[c].sector};});
      }
      if(SNAP&&SNAP.generated_at){_asOfYmd=String(SNAP.generated_at).slice(0,10);applyAsOf();}
      // applyAsOf()는 특이 신호 제목을 스냅샷 날짜로 쓴다. 신호가 먼저 왔으면 그 날짜로 되돌린다 —
      // 장 마감 직후엔 스냅샷이 어제라 오늘 신호에 어제 날짜가 붙었다(2026-10-29).
      if(SIG_ASOF){var st=document.getElementById('sig-title'); if(st) st.textContent=asOfPrefix(SIG_ASOF)+' 특이 신호';}
      renderSectorBars(); renderSectorBadge();
      if(krMarketOpen()) setInterval(loadSignals,300000); // 장중 5분마다 특이신호·섹터 막대 갱신
    })
    .catch(function(){});
})();

// 상단 스트립 실시간 갱신 — 코스피(/api/kospi-live) + 코스닥·환율(/api/market)
(function(){
  // 히어로 상단 배지 — 장중이면 LIVE, 마감·주말·공휴일이면 종가 기준. 정적 'LIVE' 고정으로 휴일에도 실시간처럼 보이던 문제 교정.
  (function(){
    var b=document.getElementById('kospi-live-badge'); if(!b) return;
    var open=(typeof hubMarketOpen==='function')?hubMarketOpen():false;
    if(open){ b.classList.remove('closed'); b.innerHTML='<span class="dot"></span>LIVE · 60초 갱신'; }
    // 색은 CSS(.upd-badge.closed)에 맡긴다 — 인라인으로 박으면 토큰(--muted) 교정이 반영되지 않는다.
    else{ b.classList.add('closed'); b.innerHTML='<span class="dot"></span>장 마감 · 종가 기준'; }
  })();
  function fmtPct(pct){return (pct>=0?'+':'')+pct.toFixed(2)+'%';}
  function dirClass(pct){return pct>0?'up':pct<0?'dn':'';}
  // 최근 종가 배열 → 미니 스파크라인 (상승=빨강·하락=파랑, 첫 값 대비 마지막 값)
  function miniSpark(vals){
    if(!Array.isArray(vals)||vals.length<2) return '';
    var n=vals.length,min=Math.min.apply(null,vals),max=Math.max.apply(null,vals),rng=(max-min)||1;
    var color=vals[n-1]>=vals[0]?'#E03131':'#2775ED';
    var pts=vals.map(function(v,i){return ((i/(n-1))*36).toFixed(1)+','+(12-((v-min)/rng)*10).toFixed(1);}).join(' ');
    var last=pts.split(' ').pop().split(',');
    return '<svg viewBox="0 0 40 14"><polyline points="'+pts+'" fill="none" stroke="'+color+'" stroke-width="1.3" stroke-linejoin="round" stroke-linecap="round"/><circle cx="'+last[0]+'" cy="'+last[1]+'" r="1.8" fill="'+color+'"/></svg>';
  }
  // 종가 배열 → 툴팁 본문 (날짜 · 종가 · 전일대비 %) — 3열 그리드로 세로 정렬
  function buildSparkTip(rows){
    var cells=rows.map(function(r,i){
      var md=r.d.slice(4,6)+'/'+r.d.slice(6,8);
      var bold=i===rows.length-1;
      var cv=r.c.toLocaleString('ko-KR',{minimumFractionDigits:2,maximumFractionDigits:2});
      var chg='';
      if(i>0&&rows[i-1].c){
        var p=(r.c-rows[i-1].c)/rows[i-1].c*100;
        chg='<span style="color:'+(p>=0?'#E03131':'#2775ED')+';'+(bold?'font-weight:800':'')+'">'+(p>=0?'+':'')+p.toFixed(2)+'%</span>';
      }
      return '<span style="color:var(--muted);'+(bold?'font-weight:800':'')+'">'+md+'</span>'
           + '<span style="text-align:right;font-variant-numeric:tabular-nums;font-weight:'+(bold?'800':'700')+'">'+cv+'</span>'
           + '<span style="text-align:right;font-variant-numeric:tabular-nums">'+chg+'</span>';
    }).join('');
    return '<div style="display:grid;grid-template-columns:auto 1fr auto;column-gap:14px;row-gap:3px;align-items:baseline">'+cells+'</div>';
  }
  // 수급 금액(억원) → '−1.90조' · '+8,420억'. 단위를 붙여 짧게 쓴다(2026-10-28 — 예전엔 단위 없이 '−19,049'만 적었다).
  function eokTxt(v){var a=Math.abs(v),s=v>=0?'+':'−';return a>=10000?s+(a/10000).toFixed(2)+'조':s+Math.round(a).toLocaleString('ko-KR')+'억';}
  // 코스피는 머리의 'LIVE · 60초 갱신'과 같은 주기로 다시 받는다 — 예전엔 처음 한 번만 받아 표기와 실제가 어긋났다.
  function pollKospi(){
  fetch('/api/kospi-live',{cache:'no-store',signal:AbortSignal.timeout(6000)})
    .then(function(r){return r.ok?r.json():null;})
    .then(function(d){
      if(!d||!d.price) return;
      var el=document.getElementById('h-kospi'),ec=document.getElementById('h-kospi-c'),ea=document.getElementById('h-kospi-abs');
      if(el) el.textContent=Math.round(d.price).toLocaleString('ko-KR');
      if(ec){ec.textContent=fmtPct(d.changePct||0);ec.className='vc '+dirClass(d.changePct||0)+' num';}
      if(ea){
        var ab=typeof d.changeAbs==='number'?d.changeAbs:null;
        ea.textContent=ab?(ab>0?'▲':'▼')+Math.round(Math.abs(ab)).toLocaleString('ko-KR'):'';
        ea.className='ix-abs '+(ab?dirClass(ab):'')+' num';
      }
    }).catch(function(){});
  }
  function pollMarket(){
  fetch('/api/market',{cache:'no-store',signal:AbortSignal.timeout(6000)})
    .then(function(r){return r.ok?r.json():null;})
    .then(function(d){
      if(!d) return;
      // 장이 닫혀 있으면 지수 줄 배지에 어느 거래일 종가인지 밝힌다(§68 ⑦ — 그 시간대에 알 수 있는 것만).
      // 날짜는 같은 응답의 kospiSpark 마지막 영업일(실측). 못 읽으면 기존 문구 그대로.
      (function(){
        var b=document.getElementById('kospi-live-badge');
        var open=(typeof hubMarketOpen==='function')?hubMarketOpen():false;
        var sk=Array.isArray(d.kospiSpark)?d.kospiSpark[d.kospiSpark.length-1]:null;
        if(!b||open||!sk||typeof sk.d!=='string'||sk.d.length!==8||typeof fmtKoDate!=='function') return;
        b.innerHTML='<span class="dot"></span>'+fmtKoDate(sk.d.slice(0,4)+'-'+sk.d.slice(4,6)+'-'+sk.d.slice(6,8))+' 마감 · 종가 기준';
      })();
      if(Array.isArray(d.kospiSpark)&&d.kospiSpark.length>1){
        var sp=document.getElementById('h-kospi-spark');
        if(sp){
          sp.innerHTML=miniSpark(d.kospiSpark.map(function(x){return x.c;}));
          sp.dataset.tipTitle='코스피 최근 종가 · 8영업일';
          sp.dataset.tip=buildSparkTip(d.kospiSpark);
          if(!sp._tipBound&&typeof showTip==='function'){
            sp.addEventListener('mouseenter',showTip);
            sp.addEventListener('mousemove',moveTip);
            sp.addEventListener('mouseleave',hideTip);
            sp._tipBound=true;
          }
        }
      }
      if(d.kosdaq&&d.kosdaq.price){
        var el=document.getElementById('h-kosdaq'),ec=document.getElementById('h-kosdaq-c');
        if(el) el.textContent=d.kosdaq.price.toFixed(1);
        if(ec){ec.textContent=fmtPct(d.kosdaq.changePct||0);ec.className='vc '+dirClass(d.kosdaq.changePct||0)+' num';}
      }
      if(d.forex&&d.forex.price){
        var el2=document.getElementById('h-usd'),ec2=document.getElementById('h-usd-c');
        var p=d.forex.price,pct=d.forex.changePct||0;
        if(el2) el2.textContent=Math.round(p).toLocaleString('ko-KR');
        if(ec2){ec2.textContent=pct!==0?fmtPct(pct):'';ec2.className='vc '+dirClass(pct)+' num';}
      }
      // 수급 — 하나라도 실측이 들어와야 행을 연다. 수집 실패 시 행은 숨긴 채로 둔다(운영규칙 0).
      if(d.investor){
        var sup=document.getElementById('h-supply'), any=false;
        var map={'h-indv':d.investor.individual,'h-inst':d.investor.institution,'h-frgn':d.investor.foreign};
        Object.keys(map).forEach(function(id){
          var v=map[id], e=document.getElementById(id);
          if(!e||v==null) return;
          any=true;
          e.textContent=eokTxt(v);
          e.className='num '+(v>=0?'up':'dn');
        });
        if(any&&sup){
          sup.hidden=false;
          /* 기준 표기 — 이 값이 언제 것인지 화면에서 알 수 있어야 한다.
             장중이면 60초 갱신 중임을, 장 마감 뒤면 어느 거래일 마감 기준인지 날짜로 밝힌다.
             날짜는 같은 응답의 kospiSpark 마지막 영업일(실측)에서 가져온다 — 별도 추정 없음. */
          var u=sup.querySelector('.unit');
          if(u){
            var open=(typeof hubMarketOpen==='function')?hubMarketOpen():false;
            var sk=Array.isArray(d.kospiSpark)?d.kospiSpark[d.kospiSpark.length-1]:null;
            var ymd=(sk&&typeof sk.d==='string'&&sk.d.length===8)
              ? sk.d.slice(0,4)+'-'+sk.d.slice(4,6)+'-'+sk.d.slice(6,8) : '';
            var label=ymd&&typeof fmtKoDate==='function'?fmtKoDate(ymd):'';
            // 장중엔 머리 배지가 이미 'LIVE · 60초 갱신'이라 '오늘'만 적는다(두 번 쓰지 않는다).
            u.textContent = open ? '오늘' : (label ? label+' 마감 기준' : '직전 거래일 마감 기준');
          }
        }
      }
    }).catch(function(){});
  }
  pollKospi(); pollMarket();
  // 장중에만 폴링 — 코스피·코스닥·환율·수급을 60초 주기로 갱신(브리핑 시장 지표 패널과 동일 주기).
  if(typeof hubMarketOpen==='function'&&hubMarketOpen()) setInterval(function(){pollKospi();pollMarket();},60000);
})();

/* ── 밤사이 브리지 (#overnight-bridge) ──────────────────────────────────────────
   간밤 미국 정규장 등락 vs 한국 직전 마감 등락을 섹터별 %p 갭으로 보여준다.
   등락 문자열·색 클래스(up/dn)·선반영/미반영/동조 판정은 파이썬
   (generate_html.build_overnight_bridge)이 전부 구워서 web/data/overnight-bridge.json으로
   내보낸다. 여기서는 렌더만 한다 — 경계 판정을 JS로 다시 구현하면 §30 이중 구현이 재현된다.

   노출 구간: 코스피 거래일 07:30~09:00 (KST).
     07:30 — 아침 시초가 예측 카드가 뜨는 시각. 2026-10-26부터 #us-evening('밤사이 미국')도
             09:00까지 함께 보이고, 브리지는 그 바로 아래에서 섹터별 갭을 덧붙인다(§68 ⑦).
     09:00 — 코스피 개장. 그 뒤로는 '한국 직전 마감'이 어제 종가가 되고 오늘 장은 따로
             움직인다. 그 상태로 갭을 계속 띄우면 오늘 등락과 이중으로 세게 되는데,
             그게 정확히 이 기능이 드러내려던 §24 사고다. 개장과 동시에 내린다.

   날짜 게이트: JSON의 date가 오늘(KST)이 아니면 아무것도 렌더하지 않는다. 이 파일은
   주말·공휴일에도 배포된 채 남아 있으므로, 실제로 그 날들을 막는 것은 요일 검사가 아니라
   이 날짜 게이트다(§0 — 완전성보다 정합성).

   재평가: ueGate(5분) 관례를 따라 1분마다 게이트만 다시 본다 — 탭을 열어둔
   채 09:00을 넘기면 스스로 내려간다. 섹션 재배치는 하지 않는다(위 phase() 주석의 '재배치는
   로드 1회' 원칙 유지). */
(function(){
  var box=document.getElementById('overnight-bridge');
  if(!box) return;
  var ENT={'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'};
  function esc(s){ return String(s==null?'':s).replace(/[&<>"']/g,function(c){return ENT[c];}); }
  function kstNow(){ return new Date(Date.now()+9*3600*1000); }
  function todayKST(){ return kstNow().toISOString().slice(0,10); }
  // gap_cls는 '동조'(갭 0)일 때 빈 문자열로 온다 — 그때는 색 클래스를 붙이지 않는다.
  function cls(c){ return (c==='up'||c==='dn') ? ' '+c : ''; }

  /* 표시 구간(코스피 거래일 07:30~09:00) 안인가 — 데이터와 무관한 시계 판정만. */
  function inWindow(){
    if(window.krIsKospiHoliday && window.krIsKospiHoliday()) return false;   // 주말·공휴일 포함
    var d=kstNow(), t=d.getUTCHours()*60+d.getUTCMinutes();
    return t>=450 && t<540;                                                  // 07:30~09:00
  }

  /* 노출 여부 — (시각·요일·공휴일·데이터 날짜)만의 순수 판정. 회귀 테스트가 직접 호출한다. */
  function shouldShow(data){
    if(!inWindow()) return false;
    if(!data || data.date!==todayKST()) return false;                        // 어제 파일 금지
    // 비교 대상 거래일이 없으면 머리말의 날짜가 빈칸으로 나간다 — 상대어 금지(§24) 이전에
    // 날짜 자체가 없는 상태라 렌더하지 않는다.
    if(typeof data.kr_session_date!=='string' || !data.kr_session_date) return false;
    return Array.isArray(data.rows) && data.rows.length>0;                   // 빈 껍데기 금지
  }

  function rowHtml(r){
    if(!r) return '';
    return '<div class="ob-row">'
      + '<span class="ob-sec">'+esc(r.sector)+'</span>'
      + '<span class="ob-leg"><span class="ob-mk">미</span><b class="num'+cls(r.us_cls)+'">'+esc(r.us_change_fmt)+'</b><span class="ob-nm">'+esc(r.us_label)+'</span></span>'
      + '<span class="ob-leg"><span class="ob-mk">한</span><b class="num'+cls(r.kr_cls)+'">'+esc(r.kr_change_fmt)+'</b><span class="ob-nm">'+esc(r.kr_label)+'</span></span>'
      + '<span class="ob-gap"><span class="ob-pill'+cls(r.gap_cls)+'">'+esc(r.gap_word)+'</span><b class="num'+cls(r.gap_cls)+'">'+esc(r.gap_fmt)+'</b></span>'
      + '</div>';
  }

  // 회귀 테스트 훅 — 프로덕션 동작에는 영향 없음(읽기 전용 참조).
  window.__obShouldShow=shouldShow;
  window.__obRowHtml=rowHtml;

  var data=null, paintedDate='', fetching=false;
  function paint(){
    if(!data || paintedDate===data.date) return;
    var list=document.getElementById('ob-list'), dt=document.getElementById('ob-date');
    if(!list||!dt) return;
    // 비교 대상 한국 세션은 반드시 실제 날짜로 적는다 — '전일'·'어제' 같은 상대어 금지(§24).
    dt.textContent='한국 '+fmtKoDate(data.kr_session_date)+' 마감 vs 미국 직전 정규장';
    list.innerHTML=data.rows.map(rowHtml).join('');
    paintedDate=data.date;
  }
  function gate(){
    var ok=shouldShow(data);
    if(ok) paint();
    box.style.display = ok ? '' : 'none';
  }

  /* 데이터 획득 — 오늘자를 손에 넣기 전까지만 다시 받는다.
     밤새 켜둔 탭은 07:00에 받은 어제 파일(또는 404)을 그대로 들고 07:30을 맞는다. 날짜
     게이트가 그 stale 파일을 정확히 걷어내므로(§0) 다시 받지 않으면 그 탭에서는 브리지가
     그날 내내 안 뜬다 — 인터벌이 09:00에 내리기만 하고 07:30에 올리지는 못하는 비대칭이었다.
     파일은 하루 한 번(07:26경)만 바뀌므로 무조건 폴링하지 않는다. 도움이 될 수 있는
     구간(표시 구간 안) + 아직 오늘자가 없을 때만 재시도하고, 받는 즉시 멈춘다.
     실패(404·네트워크·JSON 아님)하면 data를 건드리지 않는다 — 이미 그려진 블록을 지우지 않는다. */
  function refresh(){
    if(fetching) return;
    if(data && data.date===todayKST()) return;   // 이미 오늘자 — 더 받을 이유가 없다
    fetching=true;
    fetch('/data/overnight-bridge.json',{cache:'no-store'})
      .then(function(r){ return r.ok?r.json():null; })
      .then(function(j){ fetching=false; if(j) data=j; gate(); })
      .catch(function(){ fetching=false; });     // 이전 상태 유지 — 조용히 넘어간다
  }

  refresh();
  gate();
  setInterval(function(){ if(inWindow()) refresh(); gate(); }, 60*1000);
  // 탭을 오래 켜뒀다 돌아왔을 때 인터벌(최대 1분)을 기다리지 않고 즉시 자가 치유한다.
  // 위 장중 곡선 블록의 visibilitychange 자가 치유와 같은 취지 — 거기선 날짜 롤오버,
  // 여기선 '표시 구간이 열렸는데 아직 오늘자 파일이 없는' 상태를 복구한다.
  document.addEventListener('visibilitychange', function(){
    if(document.hidden) return;
    if(inWindow()) refresh();
    gate();
  });
})();


/* ── 홈의 펼치기(<details>)는 아래로 펼친다 (2026-11-03) ──
   홈은 블록 순서를 CSS order로 바꿔 둬서, 펼칠 때 브라우저 스크롤 고정이 화면 아래쪽 블록을
   기준으로 잡는다. 그러면 그 블록은 제자리에 있고 펼친 내용이 위로 밀려 올라가, 누른 줄이
   화면 밖으로 사라졌다. 펼치거나 접은 뒤 누른 줄(summary)이 원래 자리에 오도록 스크롤을 되돌린다. */
(function(){
  document.querySelectorAll('#home details > summary').forEach(function(sum){
    var top=null;
    var root=document.documentElement;
    sum.addEventListener('click', function(){
      top=sum.getBoundingClientRect().top;
      root.style.overflowAnchor='none';     // 펼치는 동안만 스크롤 고정을 끈다 — 한 프레임 튀는 것까지 막는다
    });
    sum.parentElement.addEventListener('toggle', function(){
      if(top===null) return;
      var before=top; top=null;
      requestAnimationFrame(function(){
        var dy=sum.getBoundingClientRect().top-before;
        if(Math.abs(dy)>1) window.scrollBy(0, dy);   // 그래도 밀렸으면 되돌린다
        root.style.overflowAnchor='';
      });
    });
  });
})();
