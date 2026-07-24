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

/* ── 블록 2 (원본 index.html) ── */
function usSel(code){
  document.querySelectorAll('#us-linked-widget .us-tile').forEach(function(t){t.classList.toggle('on',t.getAttribute('data-code')===code);});
  if(window.whyMovedRender) window.whyMovedRender(code);
  window.__lwCode = code;
  if(window.lwRenderAll) window.lwRenderAll(code);
}
/* 진입·새로고침마다 주도주 3종목 중 하나를 랜덤 선택 — 삼성전자에만 노출이 쏠리는 것을 막는다.
   curCode·__lwCode 초기값으로도 쓰이므로 위젯 렌더러들보다 먼저 정해둔다. */
window.__lwCode = ['005930','000660','005380'][Math.floor(Math.random()*3)];
usSel(window.__lwCode);   // 타일 선택 표시를 즉시 맞춰 깜빡임을 없앤다(렌더러는 아직 없어 no-op).
window.addEventListener('load', function(){ usSel(window.__lwCode); });
/* 주도주 위젯 — 목표주가·관련뉴스·외국계 시각 렌더러.
   제목·요약·출처는 외부 RSS에서 온 값이라 innerHTML에 넣기 전 반드시 이스케이프한다. */
(function(){
  var LW={targets:null,news:null,ib:null};
  var ENT={'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'};
  function esc(s){ return String(s==null?'':s).replace(/[&<>"']/g,function(c){return ENT[c];}); }
  // http(s)만 허용 — javascript: 같은 스킴이 href/src로 들어가는 것을 막는다.
  function safeUrl(u){ return (typeof u==='string'&&/^https?:\/\//i.test(u))?u:''; }
  function num(n){ return (n==null)?'—':Number(n).toLocaleString('ko-KR'); }
  // 네이버 리포트는 투자의견을 영문·국문 혼용으로 준다(Buy / StrongBuy / 매수 / 중립).
  // 한 목록에 섞여 보이면 지저분하므로 표시용으로만 통일한다. 모르는 값은 원문 그대로 둔다.
  function opinionKo(op){
    var s=String(op||'').trim();
    if(!s) return '';
    if(/^strong\s*buy$/i.test(s)||/적극\s*매수/.test(s)) return '적극매수';
    if(/^buy$/i.test(s)||/^매수$/.test(s)) return '매수';
    if(/^(hold|neutral|marketperform)$/i.test(s)||/^중립$/.test(s)) return '중립';
    if(/^(sell|underperform|reduce)$/i.test(s)||/^매도$/.test(s)) return '매도';
    return s;
  }
  // '26.07.08' → '7/08'. 연도는 최근 3개월치라 불필요하고 월 앞자리 0도 뗀다.
  function shortDate(d){
    var m=/^\d{2}\.(\d{2})\.(\d{2})$/.exec(String(d||''));
    return m ? String(Number(m[1]))+'/'+m[2] : String(d||'');
  }
  // ISO 발행일시 → 표시 라벨을 '지금 이 순간' 기준으로 계산한다.
  // time_label을 JSON에 박아두면(예: 생성 당시 '어제 12:46') 며칠 뒤엔 거짓이 되므로,
  // 저장값은 쓰지 않고 published_at으로 매 렌더마다 다시 만든다. 오늘/어제만 시:분, 그 이전은 날짜.
  function relTime(iso){
    var t=Date.parse(String(iso||''));
    if(isNaN(t)) return '';
    var toKstDay=function(ms){ return Math.floor((ms+9*3600*1000)/(24*3600*1000)); };
    var diff=toKstDay(Date.now())-toKstDay(t);
    var kst=new Date(t+9*3600*1000);
    var hh=String(kst.getUTCHours()).padStart(2,'0'), mm=String(kst.getUTCMinutes()).padStart(2,'0');
    if(diff<=0) return '오늘 '+hh+':'+mm;
    if(diff===1) return '어제 '+hh+':'+mm;
    return (kst.getUTCMonth()+1)+'/'+kst.getUTCDate();
  }

  function renderTargets(code){
    var b=LW.targets&&LW.targets.stocks&&LW.targets.stocks[code];
    var cnt=document.getElementById('lw-tp-cnt');
    if(!cnt) return;
    if(!b){ cnt.textContent='수집 중'; return; }
    var close=b.close_price||null, hist=b.history||[];
    // 추이 그래프가 뜨면 리포트 8건, 숨겨지면 10건으로 늘려 우측 여백을 메운다.
    var reports=(b.reports||[]).slice(0, hist.length>=20?8:10);
    cnt.textContent='리포트 '+reports.length+'건';
    document.getElementById('lw-tp-val').textContent=num(b.consensus);
    var up=document.getElementById('lw-tp-up');
    if(b.consensus&&close){
      var pct=(b.consensus-close)/close*100;
      up.textContent=(pct>=0?'+':'')+pct.toFixed(1)+'%';
      document.getElementById('lw-tp-cur').style.width=Math.max(0,Math.min(100,close/b.consensus*100))+'%';
    } else { up.textContent=''; document.getElementById('lw-tp-cur').style.width='0%'; }
    document.getElementById('lw-tp-meta').textContent=
      (close?'종가 '+num(close)+' 기준 · ':'')+'3개월 '+(b.firm_count||0)+'개사 평균';
    document.getElementById('lw-brk').innerHTML=reports.map(function(r){
      var op=opinionKo(r.opinion), neu=/중립|매도/.test(op)?' neu':'';
      return '<div class="lw-brk"><span class="f">'+esc(r.firm)+'</span>'+
        (op?'<span class="o'+neu+'">'+esc(op)+'</span>':'')+
        '<span class="t">'+num(r.target_price)+'</span>'+
        '<span class="d">'+esc(shortDate(r.date))+'</span></div>';
    }).join('');
    drawTrend(hist);
    var link=document.getElementById('lw-detail-link');
    if(link) link.setAttribute('href','/stocks/'+encodeURIComponent(code)+'/');
  }

  function drawTrend(hist){
    var wrap=document.getElementById('lw-tr');
    if(!wrap) return;
    if(!hist||hist.length<20){ wrap.style.display='none'; return; }  // 데이터 부족 시 숨김
    wrap.style.display='';
    var p=hist.map(function(h){return h.value;});
    var W=240,H=60,PT=8,PB=14,PL=4,PR=4;
    var mn=Math.min.apply(null,p),mx=Math.max.apply(null,p),span=(mx-mn)||1;
    var X=function(i){return PL+(W-PL-PR)*(i/(p.length-1));};
    var Y=function(v){return PT+(H-PT-PB)*(1-(v-mn)/span);};
    var line=p.map(function(v,i){return X(i).toFixed(1)+','+Y(v).toFixed(1);}).join(' ');
    var rising=p[p.length-1]>=p[0];
    var col=rising?'#E03131':'#2775ED', fill=rising?'rgba(224,49,49,.12)':'rgba(39,117,237,.12)';
    var base=H-PB;
    document.getElementById('lw-tr-svg').innerHTML=
      '<polygon points="'+X(0)+','+base+' '+line+' '+X(p.length-1)+','+base+'" fill="'+fill+'"/>'+
      '<polyline points="'+line+'" fill="none" stroke="'+col+'" stroke-width="1.8" stroke-linejoin="round"/>'+
      '<circle cx="'+X(p.length-1)+'" cy="'+Y(p[p.length-1])+'" r="2.8" fill="'+col+'"/>'+
      '<text x="'+PL+'" y="'+(H-3)+'" font-size="9" fill="#94A3B8" font-weight="600">'+num(p[0])+'</text>'+
      '<text x="'+(W-PR)+'" y="'+(H-3)+'" font-size="9" fill="#94A3B8" font-weight="600" text-anchor="end">'+num(p[p.length-1])+'</text>';
    var pct=(p[p.length-1]-p[0])/p[0]*100;
    var d=document.getElementById('lw-tr-d');
    d.textContent=(pct>=0?'+':'')+pct.toFixed(1)+'%'; d.style.color=col;
    var lb=document.getElementById('lw-tr-label');
    if(lb) lb.textContent='컨센서스 추이 · '+p.length+'거래일';
  }

  function renderNews(code){
    var el=document.getElementById('lw-news');
    if(!el) return;
    var list=LW.news&&LW.news.stocks&&LW.news.stocks[code];
    if(!list||!list.length){
      el.innerHTML='<div style="font-size:11.5px;color:#94A3B8;padding:8px 2px">수집된 뉴스가 없어요.</div>';
      return;
    }
    el.innerHTML=list.map(function(n){
      var href=safeUrl(n.url), th=safeUrl(n.thumb);
      var img=th?'<img class="nimg" src="'+esc(th)+'" alt="" loading="lazy" onerror="this.style.visibility=\'hidden\'">':'';
      var open=href?'<a href="'+esc(href)+'" target="_blank" rel="noopener noreferrer">':'<a>';
      return open+'<div style="flex:1 1 auto;min-width:0">'+
        '<div class="nt">'+esc(n.time)+'</div>'+
        '<div class="nh">'+esc(n.title)+'</div>'+
        (n.summary?'<div class="ns">'+esc(n.summary)+'</div>':'')+
        '<div class="nsrc">'+esc(n.source)+'</div></div>'+img+'</a>';
    }).join('');
  }

  function renderIB(){
    var wrap=document.getElementById('lw-ib');
    if(!wrap) return;
    var views=(LW.ib&&(LW.ib.views||LW.ib))||[];
    if(!Array.isArray(views)||!views.length){ wrap.style.display='none'; return; }  // 없으면 섹션 생략
    wrap.style.display='';
    // 발행일시 내림차순(최신 먼저). published_at이 없는 항목은 뒤로.
    views=views.slice().sort(function(a,b){ return (Date.parse(b.published_at)||0)-(Date.parse(a.published_at)||0); });
    document.getElementById('lw-ib-list').innerHTML=views.map(function(v){
      // 실제 JSON 필드명은 sentiment다 (stance 아님). 로고는 initials를 쓰고 없으면 하우스명을 자른다.
      var st=(v.sentiment==='bull'||v.sentiment==='bear')?v.sentiment:'neu';
      var label=st==='bull'?'강세':(st==='bear'?'약세':'중립');
      var href=safeUrl(v.url);
      // time_label(생성 당시 박제값)은 시간이 지나면 거짓이 되므로 쓰지 않고 published_at으로 현재 기준 재계산.
      var tm=relTime(v.published_at)||esc(v.time_label);
      // 출처를 단독 줄로 두지 않고 행 전체를 링크로 만든다 — 하우스명 옆 화살표가 hover 시 나타나
      // 이동 가능함을 알린다. 출처명은 날짜 아래 작게 남겨 귀속(attribution)은 유지한다.
      // 아이콘(하우스 이니셜)을 좌측 별도 열이 아니라 하우스명 앞 작은 뱃지로 인라인 배치 →
      // 본문 텍스트가 좌우 열에 눌리지 않고 한 행 전체를 좌측 정렬로 사용한다.
      var body='<div class="bd">'+
        '<div class="hd"><span class="lg">'+esc(v.initials||String(v.house||'').slice(0,4))+'</span>'+
        '<span class="nm">'+esc(v.house)+'</span>'+
        '<span class="tg '+st+'">'+label+'</span>'+
        '<span class="tm">'+esc(tm)+'</span>'+
        (href?'<span class="go" aria-hidden="true">›</span>':'')+'</div>'+
        '<div class="tx">'+esc(v.summary)+'</div>'+
        (v.source?'<div class="src">출처 · '+esc(v.source)+'</div>':'')+
        '</div>';
      return href
        ? '<a class="lw-ib-row lw-ib-row--link" href="'+esc(href)+'" target="_blank" rel="noopener noreferrer">'+body+'</a>'
        : '<div class="lw-ib-row">'+body+'</div>';
    }).join('');
  }

  window.lwRenderAll=function(code){ renderTargets(code); renderNews(code); };

  function load(){
    var j=function(u){ return fetch(u,{cache:'no-store'}).then(function(r){return r.ok?r.json():null;}).catch(function(){return null;}); };
    Promise.all([j('/data/stock-targets.json'),j('/data/stock-news.json'),j('/data/ib_korea_views.json')])
      .then(function(res){
        LW.targets=res[0]; LW.news=res[1]; LW.ib=res[2];
        window.lwRenderAll(window.__lwCode||'005930');
        renderIB();
      });
  }
  window.addEventListener('load',load);
})();
(function(){
  var X0=14,X1=626,YT=22,YB=150;
  var buf={};
  var buft={};   // buf와 병렬: 각 포인트의 실제 시각 'HH:MM' (장중 부분 데이터를 시간축에 정확히 배치)
  var bufv={};   // buf와 병렬: 각 포인트의 누적 거래량 (VWAP 계산용, backfill 시점 스냅샷)
  var bufDay=todayKST();   // buf가 담고 있는 거래일(KST). 페이지를 자정 넘겨 열어두면 전일 곡선에 오늘 실측이 이어붙어(시간축이 HH:MM만 써 날짜를 무시) 곡선이 대각선으로 깨진다 → 날짜가 바뀌면 버퍼를 전량 무효화한다.
  var curCode=window.__lwCode||'005930';
  var whyData={};
  var snapW={};
  function timeToX(t){var p=(t||'09:00').split(':'),mm=(+p[0])*60+(+p[1]);return X0+(X1-X0)*Math.min(1,Math.max(0,(mm-540)/(930-540)));}
  function loadWhy(){
    var d=new Date(Date.now()+9*3600*1000).toISOString().slice(0,10);
    // 라이브 데이터는 /api/data(raw main) 우선 — 데이터 전용 커밋은 재배포 안 되므로 정적 /data는 stale일 수 있음
    fetch('/api/data?f=movers-why',{cache:'no-store'}).then(function(r){return r.ok?r.json():null;})
      .then(function(j){ return j||fetch('/data/movers-why-'+d+'.json').then(function(r){return r.ok?r.json():null;}); })
      .then(function(j){ return j||fetch('/data/movers-why-live.json').then(function(r){return r.ok?r.json():null;}); })
      .then(function(j){ if(j&&j.stocks){ j.stocks.forEach(function(s){ whyData[s.code]=s.events||[]; }); if(buf[curCode])draw(curCode); } }).catch(function(){});
  }
  function loadSnap(){
    fetch('/data/stocks-snapshot.json',{cache:'no-store'}).then(function(r){return r.ok?r.json():null;})
      .then(function(j){ if(j&&j.stocks){ snapW=j.stocks; renderRight(curCode); } }).catch(function(){});
  }
  function frSpark(arr){
    var lo=Math.min.apply(null,arr),hi=Math.max.apply(null,arr),sp=(hi-lo)||1,n=arr.length,W=120,H=34,P=3;
    var pts=arr.map(function(v,i){var x=P+(W-2*P)*(i/(n-1));var y=H-P-(H-2*P)*((v-lo)/sp);return x.toFixed(1)+','+y.toFixed(1);}).join(' ');
    var c=arr[n-1]>arr[0]?'#E03131':(arr[n-1]<arr[0]?'#2775ED':'#64748B'),last=pts.split(' ').pop().split(',');
    return '<svg viewBox="0 0 '+W+' '+H+'" width="108" height="31" style="flex:none;"><polyline points="'+pts+'" fill="none" stroke="'+c+'" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/><circle cx="'+last[0]+'" cy="'+last[1]+'" r="2.6" fill="#fff" stroke="'+c+'" stroke-width="1.6"/></svg>';
  }
  function renderRight(code){
    var fr=document.getElementById('wm-fr'), s=snapW[code];
    if(fr){
      if(s&&typeof s.foreign_rate==='number'&&Array.isArray(s.foreign_spark)&&s.foreign_spark.length>1){
        var arr=s.foreign_spark,chg=arr[arr.length-1]-arr[arr.length-2];
        var ccol=chg>0?'#E03131':(chg<0?'#2775ED':'#94A3B8'),csign=chg>0?'+':(chg<0?'-':'');
        fr.style.display='';
        fr.innerHTML='<div class="wm-card-h">🌐 외국인 보유율</div>'
          +'<div style="display:flex;align-items:center;gap:10px;">'+frSpark(arr)
          +'<div style="margin-left:auto;text-align:right;white-space:nowrap;line-height:1.25;">'
          +'<b style="font-size:18px;font-weight:900;color:#0F172A;">'+s.foreign_rate.toFixed(2)+'<span style="font-size:12px;color:#94A3B8;font-weight:700;">%</span></b>'
          +'<div style="font-size:12px;font-weight:700;color:'+ccol+'">'+csign+Math.abs(chg).toFixed(2)+'%p</div>'
          +'</div></div>';
      } else { fr.style.display='none'; }
    }
    var rng=document.getElementById('wm-range');
    if(rng){
      var rv=buf[code]||[];
      if(rv.length>4){
        var rlo=Math.min.apply(null,rv),rhi=Math.max.apply(null,rv),rcur=rv[rv.length-1],rspan=(rhi-rlo)||1;
        var rpos=Math.max(0,Math.min(100,(rcur-rlo)/rspan*100));
        var fromLo=(rcur-rlo)/rlo*100, fromHi=(rcur-rhi)/rhi*100;
        rng.style.display='';
        rng.innerHTML='<div class="wm-card-h">📊 당일 레인지 위치<b style="margin-left:auto;font-size:18px;font-weight:900;color:#0F172A">'+rpos.toFixed(0)+'%</b></div>'
          +'<div style="position:relative;height:8px;border-radius:5px;background:linear-gradient(90deg,#DBEAFE,#FECACA);">'
          +'<div style="position:absolute;left:'+rpos.toFixed(0)+'%;top:-3px;width:14px;height:14px;border-radius:50%;background:#0F172A;border:2px solid #fff;transform:translateX(-50%);"></div></div>'
          +'<div style="display:flex;justify-content:space-between;font-size:11px;color:#94A3B8;margin-top:5px;"><span>저 '+fmt(rlo)+'</span><span>고 '+fmt(rhi)+'</span></div>'
          +'<div class="wm-bell-note">저점서 +'+fromLo.toFixed(1)+'% 회복 · 고점 대비 '+fromHi.toFixed(1)+'%</div>';
      } else { rng.style.display='none'; }
    }
    var wk52=document.getElementById('wm-wk52');
    if(wk52){
      if(s&&s.wk52_high!=null&&s.wk52_low!=null&&s.wk52_high>s.wk52_low&&s.close!=null){
        var yspan=s.wk52_high-s.wk52_low;
        var ypos=Math.max(0,Math.min(100,(s.close-s.wk52_low)/yspan*100));
        var yFromHi=(s.close-s.wk52_high)/s.wk52_high*100;
        var yDiv=(rng&&rng.style.display!=='none');   // 당일 레인지 카드가 보일 때만 구분선
        wk52.style.display='';
        wk52.style.borderTop=yDiv?'1px solid #F1F5F9':'none';
        wk52.style.marginTop=yDiv?'12px':'0';
        wk52.style.paddingTop=yDiv?'12px':'0';
        wk52.innerHTML='<div class="wm-card-h">📅 52주 레인지 위치<b style="margin-left:auto;font-size:18px;font-weight:900;color:#0F172A">'+ypos.toFixed(0)+'%</b></div>'
          +'<div style="position:relative;height:8px;border-radius:5px;background:linear-gradient(90deg,#DBEAFE,#FECACA);">'
          +'<div style="position:absolute;left:'+ypos.toFixed(0)+'%;top:-3px;width:14px;height:14px;border-radius:50%;background:#0F172A;border:2px solid #fff;transform:translateX(-50%);"></div></div>'
          +'<div style="display:flex;justify-content:space-between;font-size:11px;color:#94A3B8;margin-top:5px;"><span>1년 최저 '+fmt(s.wk52_low)+'</span><span>최고 '+fmt(s.wk52_high)+'</span></div>'
          +'<div class="wm-bell-note">52주 고점 대비 <b style="color:#2775ED">'+yFromHi.toFixed(0)+'%</b></div>';
      } else { wk52.style.display='none'; }
    }
    var vw=document.getElementById('wm-vwap');
    if(vw){
      var pv=buf[code]||[], vv=bufv[code]||[];
      // VWAP = Σ(종가×구간거래량)/Σ(구간거래량). 누적 거래량을 차분해 구간 거래량 산출.
      var num=0, den=0, i;
      if(vv.length>4 && pv.length>=vv.length){
        for(i=0;i<vv.length;i++){ var dv=(i===0)?vv[0]:Math.max(0,vv[i]-vv[i-1]); num+=pv[i]*dv; den+=dv; }
      }
      if(den>0){
        var vwap=num/den, cur=pv[pv.length-1], diff=(cur-vwap)/vwap*100;
        var dcol=diff>=0?'#E03131':'#2775ED';
        vw.style.display='';
        vw.innerHTML='<div class="wm-card-h">🎯 평균체결가(VWAP)<b style="margin-left:auto;font-size:13px;font-weight:900;color:'+dcol+'">현재 '+(diff>=0?'+':'')+diff.toFixed(1)+'%</b></div>'
          +'<div style="display:flex;align-items:baseline;gap:6px;"><b style="font-size:18px;font-weight:900;color:#0F172A">'+fmt(Math.round(vwap))+'</b>'
          +'<span style="font-size:11px;color:#94A3B8;">원 · 평균보다 '+(diff>=0?'비싸게':'싸게')+' 매수 중</span></div>';
      } else { vw.style.display='none'; }
    }
  }
  function pathFrom(vals,times){
    if(!vals||vals.length<2) return null;
    var lo=Math.min.apply(null,vals),hi=Math.max.apply(null,vals),span=(hi-lo)||1,n=vals.length;
    var useT=times&&times.length===n;  // 실제 시각이 있으면 시간축 배치, 없으면 균등 분포(폴백)
    return vals.map(function(v,i){var x=useT?timeToX(times[i]):X0+(X1-X0)*(i/(n-1));var y=YB-(YB-YT)*((v-lo)/span);return x.toFixed(1)+','+y.toFixed(1);}).join(' ');
  }
  function fmt(v){return v>=1000?v.toLocaleString():v;}
  function idxToTime(i,n){var mm=540+Math.round((390)*i/(n-1));var h=Math.floor(mm/60),m=mm%60;return (h<10?'0':'')+h+':'+(m<10?'0':'')+m;}
  function wmSetOpen(open){
    // 곡선 블록만 숨긴다. 같은 #why-moved 안의 목표주가·관련뉴스·외국계 시각은
    // 장중 실측과 무관하게 항상 유효하므로 곡선이 없다고 함께 사라지면 안 된다.
    var blk=document.getElementById('wm-curve-block'); if(!blk) return;
    blk.style.display = open ? '' : 'none';
    // 곡선이 숨겨졌음을 CSS에 알린다 — 아래 행의 구분선을 같이 없애 이중선을 막는다.
    var wm=document.getElementById('why-moved');
    if(wm) wm.classList.toggle('lw-nocurve', !open);
  }
  // 곡선·거래량·레인지 상세 영역(#wm-body) 접힘/펼침 — 밤사이 미국 반도체 시황(#us-evening, 17:00~익일 07:30)과
  // 같은 시간대엔 자동으로 접히고 07:30(오전 브리핑 발행)에 펼쳐진다. 사용자가 수동으로 펼치거나 접으면 그 선택을
  // localStorage에 저장해 같은 시간대(밤/낮)가 유지되는 동안은 자동 스케줄보다 우선한다 — 시간대가 바뀌면(예: 다음날
  // 아침) 저장된 값은 더 이상 유효하지 않은 것으로 간주하고 새 기본값을 따른다.
  var WM_OVERRIDE_KEY='ds-wm-body-open-v1';
  function wmNightCollapsed(){
    var d=new Date(Date.now()+9*3600*1000), wd=d.getUTCDay();
    if(wd===0||wd===6) return true;
    var hm=d.getUTCHours()*60+d.getUTCMinutes();
    return hm>=1020 || hm<450;
  }
  function wmReadOverride(){
    try{
      var raw=localStorage.getItem(WM_OVERRIDE_KEY); if(!raw) return null;
      var o=JSON.parse(raw);
      return (o && typeof o.night==='boolean' && typeof o.open==='boolean') ? o : null;
    }catch(e){ return null; }
  }
  function wmWriteOverride(open){
    try{ localStorage.setItem(WM_OVERRIDE_KEY, JSON.stringify({night:wmNightCollapsed(),open:open})); }catch(e){}
  }
  function wmBodyGate(){
    var body=document.getElementById('wm-body'), btn=document.getElementById('wm-toggle');
    if(!body) return;
    var night=wmNightCollapsed(), ov=wmReadOverride();
    var open = (ov && ov.night===night) ? ov.open : !night;
    body.style.display = open ? '' : 'none';
    if(btn) btn.classList.toggle('is-collapsed', !open);
  }
  function wmToggleManual(){
    var body=document.getElementById('wm-body');
    var isOpen = !body || body.style.display !== 'none';
    wmWriteOverride(!isOpen);
    wmBodyGate();
  }
  function draw(code){
    var vals=buf[code]||[], svg=document.getElementById('wm-svg'), wm=document.getElementById('why-moved');
    if(!svg||!wm) return;
    var meta=document.querySelector('#why-moved [data-code="'+code+'"]');
    var nm=document.getElementById('wm-name'); if(nm&&meta) nm.textContent=meta.getAttribute('data-name')||'';
        var pts=pathFrom(vals,buft[code]);
    if(!pts){ wmSetOpen(false); return; }
    wmSetOpen(true);
    var up=vals[vals.length-1]>=vals[0], col=up?'#E03131':'#2775ED';
    var colA=up?'rgba(224,49,49,.18)':'rgba(39,117,237,.18)', colB=up?'rgba(224,49,49,.02)':'rgba(39,117,237,.02)';
    var coords=pts.split(' ').map(function(p){var a=p.split(',');return {x:+a[0],y:+a[1]};});
    var last=coords[coords.length-1];
    var gradId='wm-grad-'+code;
    // 면적 폴리곤은 마지막 포인트의 x에서 닫는다 — 장중엔 곡선이 현재 시각까지만 그려지고 이후 축은 빈다
    var areaPath=pts+' '+last.x.toFixed(1)+','+YB+' '+X0.toFixed(1)+','+YB;
    var hiIdx=0,loIdx=0;
    for(var i=1;i<vals.length;i++){if(vals[i]>vals[hiIdx])hiIdx=i;if(vals[i]<vals[loIdx])loIdx=i;}
    var hiC=coords[hiIdx],loC=coords[loIdx];
    var s='<defs><linearGradient id="'+gradId+'" x1="0" y1="0" x2="0" y2="1">'
      +'<stop offset="0%" stop-color="'+colA+'"/><stop offset="100%" stop-color="'+colB+'"/></linearGradient></defs>'
      +'<line x1="'+X0+'" y1="'+YB+'" x2="'+X1+'" y2="'+YB+'" stroke="#E5E7EB" stroke-width="1"/>'
      +'<polygon points="'+areaPath+'" fill="url(#'+gradId+')"/>'
      +'<polyline points="'+pts+'" fill="none" stroke="'+col+'" stroke-width="2" stroke-linejoin="round"/>'
      +'<circle cx="'+last.x.toFixed(1)+'" cy="'+last.y.toFixed(1)+'" r="3.5" fill="'+col+'"/>';
    if(vals.length>4&&hiIdx!==loIdx){
      var hAnc=hiC.x<320?'start':'end', lAnc=loC.x<320?'start':'end';
      var hOff=hAnc==='start'?6:-6, lOff=lAnc==='start'?6:-6;
      var hLabY=(hiC.y-8 < YT+2)?(hiC.y+16):(hiC.y-8);   // 상단 붙으면 점 아래로
      var lLabY=(loC.y+16 > YB-6)?(loC.y-10):(loC.y+16);  // 하단(축 라벨) 겹치면 점 위로
      s+='<circle cx="'+hiC.x.toFixed(1)+'" cy="'+hiC.y.toFixed(1)+'" r="4" fill="#E03131"/>'
        +'<text x="'+(hiC.x+hOff).toFixed(1)+'" y="'+hLabY.toFixed(1)+'" font-size="11" font-weight="800" fill="#E03131" stroke="#fff" stroke-width="3" paint-order="stroke" stroke-linejoin="round" text-anchor="'+hAnc+'">고점 '+fmt(vals[hiIdx])+'</text>'
        +'<circle cx="'+loC.x.toFixed(1)+'" cy="'+loC.y.toFixed(1)+'" r="4" fill="#2775ED"/>'
        +'<text x="'+(loC.x+lOff).toFixed(1)+'" y="'+lLabY.toFixed(1)+'" font-size="11" font-weight="800" fill="#2775ED" stroke="#fff" stroke-width="3" paint-order="stroke" stroke-linejoin="round" text-anchor="'+lAnc+'">저점 '+fmt(vals[loIdx])+'</text>';
    }
    s+='<text x="'+X0+'" y="170" font-size="10" fill="#9CA3AF">09:00</text>'
      +'<text x="'+(X1-30)+'" y="170" font-size="10" fill="#9CA3AF">15:30</text>';
    s+='<line id="wm-cross" x1="0" y1="'+YT+'" x2="0" y2="'+YB+'" stroke="#94A3B8" stroke-width="0.8" stroke-dasharray="3,3" opacity="0"/>'
      +'<circle id="wm-dot" cx="0" cy="0" r="4" fill="'+col+'" stroke="#fff" stroke-width="1.5" opacity="0"/>'
      +'<rect id="wm-hit" x="'+X0+'" y="0" width="'+(X1-X0)+'" height="'+YB+'" fill="transparent" style="cursor:crosshair"/>';
    svg.innerHTML=s;
    var evs=whyData[code]||[];
    // 곡선 위 번호 핀(①②…)은 허브에서 제거했다. 곡선은 가격 흐름만 보여주고,
    // 뉴스는 아래 '관련 뉴스' 목록이 담당한다 — 같은 정보를 두 군데서 다르게 보여주지 않는다.
    renderRight(code);
    // tooltip
    var tip=document.getElementById('wm-tip');
    if(!tip){tip=document.createElement('div');tip.id='wm-tip';tip.style.cssText='position:absolute;pointer-events:none;background:#0F172A;color:#fff;font-size:12px;font-weight:700;padding:5px 10px;border-radius:8px;opacity:0;transition:opacity .12s;white-space:nowrap;z-index:5;';svg.parentNode.style.position='relative';svg.parentNode.appendChild(tip);}
    var hit=document.getElementById('wm-hit'),cross=document.getElementById('wm-cross'),dot=document.getElementById('wm-dot');
    if(hit){
      var n=vals.length, tms=buft[code];
      hit.addEventListener('mousemove',function(ev){
        var rect=svg.getBoundingClientRect(),mx=ev.clientX-rect.left,sx=640/rect.width;
        var px=mx*sx;
        // 시간축 비균등 배치이므로 x가 가장 가까운 포인트를 찾는다
        var idx=0,bd=1e9;for(var k=0;k<coords.length;k++){var dd=Math.abs(coords[k].x-px);if(dd<bd){bd=dd;idx=k;}}
        var cx=coords[idx].x,cy=coords[idx].y;
        cross.setAttribute('x1',cx);cross.setAttribute('x2',cx);cross.setAttribute('opacity','1');
        dot.setAttribute('cx',cx);dot.setAttribute('cy',cy);dot.setAttribute('opacity','1');
        var pxX=cx/640*rect.width, pxY=cy/180*rect.height;
        tip.style.opacity='1';tip.style.left=pxX+'px';tip.style.top=(pxY-38)+'px';tip.style.transform='translateX(-50%)';
        tip.textContent=((tms&&tms[idx])?tms[idx]:idxToTime(idx,n))+' · '+fmt(vals[idx]);
      });
      hit.addEventListener('mouseleave',function(){cross.setAttribute('opacity','0');dot.setAttribute('opacity','0');tip.style.opacity='0';});
    }
    var tl=document.getElementById('wm-tl');
    if(tl){ tl.innerHTML = evs.length ? evs.map(function(e,i){var lbl=e.tier==='why'?'why':'관련',nbg=e.tier==='why'?'background:#E03131;color:#fff;':'background:#fff;color:#64748B;border:1.5px solid #CBD5E1;',tcss=e.tier==='why'?'color:#E03131;background:#FEF2F2;':'color:#64748B;background:#F1F5F9;';
      return '<div style="display:flex;gap:9px;padding:7px 0;border-bottom:1px solid #F1F5F9;"><div style="flex:none;width:20px;height:20px;border-radius:50%;font-size:11px;font-weight:800;display:flex;align-items:center;justify-content:center;'+nbg+'">'+(i+1)+'</div><div style="flex:1;min-width:0;"><div style="font-size:11px;font-weight:700;color:#94A3B8;">'+e.time+'</div><div style="font-size:13px;font-weight:700;line-height:1.4;margin:1px 0 2px;"><a href="'+e.url+'" target="_blank" rel="noopener" style="color:#0F172A;text-decoration:none;">'+e.headline+'</a><span style="font-size:10px;font-weight:800;border-radius:5px;padding:1px 6px;margin-left:6px;'+tcss+'">'+lbl+'</span></div><div style="font-size:12px;color:#334155;">'+e.why+'</div><div style="font-size:11px;color:#94A3B8;margin-top:2px;">출처 · '+e.source+'</div></div></div>';}).join('')
      : '<div style="font-size:12px;color:#64748B;padding:10px 2px;text-align:center;">📭 오늘 관련 뉴스 없음 · 수급/테마 추정</div>'; }
  }
  function nowHHMM(){var d=new Date(Date.now()+9*3600*1000);var h=d.getUTCHours(),m=d.getUTCMinutes();return (h<10?'0':'')+h+':'+(m<10?'0':'')+m;}
  var backfilled={};   // 코드별 전일 1분봉 백필 완료 여부 — 라이브 폴러가 buf를 미리 채워도 첫 조회 시 풀 곡선 로드
  // 로딩 자리표시(스켈레톤) — 캐시 없는 첫 진입에서 곡선 영역이 빈 칸으로 깨져 보이지 않도록 펄스 placeholder 표시
  function ensureSkelCSS(){
    if(document.getElementById('wm-skel-css')) return;
    var st=document.createElement('style'); st.id='wm-skel-css';
    st.textContent='@keyframes wmPulse{0%,100%{opacity:.45}50%{opacity:.9}}.wm-skel{animation:wmPulse 1.1s ease-in-out infinite}';
    document.head.appendChild(st);
  }
  function showSkeleton(){
    var svg=document.getElementById('wm-svg'), wm=document.getElementById('why-moved');
    if(!svg||!wm) return;
    ensureSkelCSS(); wmSetOpen(true);
    svg.innerHTML='<rect class="wm-skel" x="2" y="14" width="636" height="132" rx="10" fill="#EEF2F7"/>'
      +'<line x1="14" y1="150" x2="626" y2="150" stroke="#E5E7EB" stroke-width="1"/>'
      +'<text class="wm-skel" x="320" y="88" text-anchor="middle" font-size="12" font-weight="700" fill="#94A3B8">실측 1분봉 불러오는 중…</text>';
  }
  // 세션 캐시 — 같은 날 직전 fetch한 실측 1분봉을 보관해 새로고침 시 곡선을 즉시 복원(날짜 다르면 자동 무효화)
  function todayKST(){ return new Date(Date.now()+9*3600*1000).toISOString().slice(0,10); }
  function readCache(){
    try{ var raw=sessionStorage.getItem('wm-intra-v1'); if(!raw) return {}; var o=JSON.parse(raw); return (o&&o.date===todayKST()&&o.data)?o.data:{}; }catch(e){ return {}; }
  }
  function writeCache(code,d){
    try{ var raw=sessionStorage.getItem('wm-intra-v1'),o={}; try{ o=raw?JSON.parse(raw):{}; }catch(_){ o={}; }
      if(!o||o.date!==todayKST()) o={date:todayKST(),data:{}}; if(!o.data) o.data={};
      o.data[code]={minutes:d.minutes||[],times:d.times||[],volumes:d.volumes||[]};
      sessionStorage.setItem('wm-intra-v1',JSON.stringify(o)); }catch(e){}
  }
  function backfill(code){
    // ① 세션 캐시 즉시 복원 — 같은 날 직전 실측값으로 먼저 그린다(빈 칸 방지). ② 없으면 스켈레톤.
    var cached=readCache()[code];
    if(cached&&cached.minutes&&cached.minutes.length>=2){
      buf[code]=cached.minutes.slice(); buft[code]=(cached.times||[]).slice(); bufv[code]=(cached.volumes||[]).slice(); draw(code);
    } else if(code===curCode){ showSkeleton(); }
    // ③ 라이브 fetch로 최신값 갱신(캐시도 새로 저장)
    fetch('/api/intraday?code='+code).then(function(r){return r.json();}).then(function(d){
      if(d&&d.minutes&&d.minutes.length){ buf[code]=d.minutes.slice(); buft[code]=(d.times||[]).slice(); bufv[code]=(d.volumes||[]).slice(); backfilled[code]=true; writeCache(code,d); draw(code); }
      else if(!(buf[code]&&buf[code].length>=2)){ if(code===curCode) wmSetOpen(false); }
    }).catch(function(){ if(!(buf[code]&&buf[code].length>=2)){ if(code===curCode) wmSetOpen(false); } });
  }
  // 날짜 롤오버 방어 — 자정 넘겨 열어둔 탭에서 전일 buf에 오늘 실측이 이어붙지 않도록 전량 리셋 후 재백필한다.
  function resetForNewDay(){
    bufDay=todayKST();
    buf={}; buft={}; bufv={}; backfilled={};
    try{ sessionStorage.removeItem('wm-intra-v1'); }catch(e){}
    backfill(curCode);
  }
  window.whyMovedPush=function(code, price){
    if(typeof price!=='number'||!isFinite(price)) return;
    if(todayKST()!==bufDay){ resetForNewDay(); return; }   // 자정 넘겨 열어둔 경우 전일 곡선에 오늘 값을 이어붙이지 않는다
    // 장중(평일 09:00~15:30 KST)만 곡선 버퍼에 반영. 마감 후·주말·공휴일 HL 24h 환산가가 섞여 시간축·스케일을 깨뜨리는 것을 차단.
    // 주말·공휴일 09:00~15:30엔 krOpen()이 false라 pollNight(HL)이 돌므로, 시각뿐 아니라 비거래일도 막아야 한다.
    var _kd=new Date(Date.now()+9*3600*1000),_km=_kd.getUTCHours()*60+_kd.getUTCMinutes();
    if((window.krIsKospiHoliday&&window.krIsKospiHoliday())||_km<540||_km>930) return;
    if(!buf[code]) buf[code]=[];
    if(!buft[code]) buft[code]=[];
    var b=buf[code];
    if(!b.length||b[b.length-1]!==price){ b.push(price); buft[code].push(nowHHMM()); if(b.length>120){ b.shift(); buft[code].shift(); } }
    if(code===curCode) draw(code);
  };
  window.whyMovedRender=function(code){ curCode=code; if(backfilled[code]) draw(code); else backfill(code); };
  backfill(curCode);
  loadWhy();
  loadSnap();
  var wmHeaderToggle=document.getElementById('wm-h-toggle');
  if(wmHeaderToggle) wmHeaderToggle.addEventListener('click', wmToggleManual);
  wmBodyGate();
  // 밤사이 미국 반도체 시황(17:00)~오전 브리핑 발행(07:30) 경계를 놓치지 않도록 1분마다 재평가.
  // + 날짜 롤오버(자정)도 함께 감시 — 오래 켜둔 탭이 전일 곡선을 계속 그리는 것을 자가 치유한다.
  setInterval(function(){ wmBodyGate(); if(todayKST()!==bufDay) resetForNewDay(); }, 60000);
  // 탭에 다시 돌아왔을 때(오래 켜뒀다 재방문) 날짜가 바뀌었으면 즉시 곡선을 새 거래일로 복구한다.
  document.addEventListener('visibilitychange', function(){ if(!document.hidden && todayKST()!==bufDay) resetForNewDay(); });
})();

/* ── 블록 3 (원본 index.html) ── */
/* 더블샷 모멘텀 픽 장중 추적 — 커밋된 kospi 스냅샷 stock_picks(진입·목표·손절) + /api/stocks-live 라이브 가격 */
    (function(){
      var box=document.getElementById('mom-track'), grid=document.getElementById('mt-grid');
      if(!box||!grid) return;
      function won(s){ return parseInt(String(s).replace(/[^0-9]/g,''),10)||0; }
      function fmt(n){ return (n||0).toLocaleString('en-US'); }
      function parseEntry(s){ var parts=String(s).replace(/원/g,'').split('~'); return parts.length===2?{lo:won(parts[0]),hi:won(parts[1])}:{lo:won(s),hi:0}; }
      function fmtEntry(p){ return p.entry_hi?fmt(p.entry)+' ~ '+fmt(p.entry_hi):fmt(p.entry); }
      function kstDate(){ return new Date(Date.now()+9*3600*1000).toISOString().slice(0,10); }
      function briefDate(){
        var s=document.getElementById('brief-strip');
        var m=s&&(s.getAttribute('data-href')||'').match(/(\d{4}-\d{2}-\d{2})/);
        return m?m[1]:kstDate();
      }
      function krOpen(){ if(window.krIsKospiHoliday&&window.krIsKospiHoliday()) return false; var m=((new Date().getUTCHours()*60+new Date().getUTCMinutes())+540)%1440; return m>=540&&m<=930; }
      /* 모멘텀 추적 상태 — prep(07:30~09:00 장 준비) · open(09:00~15:30 장중) · closed(그 외 장 마감) */
      function momPhase(){ if(window.krIsKospiHoliday&&window.krIsKospiHoliday()) return 'closed'; var m=((new Date().getUTCHours()*60+new Date().getUTCMinutes())+540)%1440;
        if(m>=450&&m<540) return 'prep'; if(m>=540&&m<=930) return 'open'; return 'closed'; }
      function setMomStatus(){
        var lv=document.getElementById('mt-live'); if(!lv) return;
        var ph=momPhase();
        if(ph==='open'){ lv.textContent='●장중 추적'; lv.style.color='#16A34A'; lv.style.background='#ECFDF3'; }
        else if(ph==='prep'){ lv.textContent='●장 준비 중'; lv.style.color='#B45309'; lv.style.background='#FEF3C7'; }
        else { lv.textContent='●장 마감'; lv.style.color='#94A3B8'; lv.style.background='#F1F5F9'; }
      }
      var PICKS=[];
      function cardHTML(p){
        return '<a class="mt-card" onclick="goStock(\''+p.code+'\')" id="mt-'+p.code+'">'
          +'<div class="mt-top"><div><span class="mt-nm">'+p.name+'</span>'+(p.tag?'<span class="mt-tag">'+p.tag+'</span>':'')+'<div style="font-size:10px;color:#94A3B8;margin-top:3px" class="num">'+p.code+'</div></div>'
          +'<div style="text-align:right"><div class="mt-px num" data-px>—</div><div class="mt-cg num" data-cg></div></div></div>'
          +'<div class="mt-bar"><div class="fill" data-fill></div><div class="entry" data-entry style="left:0"></div><div class="dot" data-dot style="left:0"></div></div>'
          +'<div class="mt-lvls">손절 <b class="num">'+fmt(p.stop)+'</b> · 진입 <b class="num">'+fmtEntry(p)+'</b> · 목표 <b class="num">'+fmt(p.target)+'</b> <span style="color:#16A34A;font-weight:700">'+(p.target_pct||'')+'</span></div>'
          +'<div class="mt-foot"><span class="mt-rtn num" data-rtn style="color:#94A3B8">진입가 대비 —</span><span class="mt-st track" data-st>추적 중</span></div></a>';
      }
      function applyLive(prices){
        var byc={}; (prices||[]).forEach(function(x){byc[x.code]=x;});
        PICKS.forEach(function(p){
          var card=document.getElementById('mt-'+p.code); if(!card) return;
          var d=byc[p.code]; if(!d||d.price==null) return;
          var live=d.price, pct=d.changePct==null?0:d.changePct;
          var up=pct>0,dn=pct<0,col=up?'#E03131':dn?'#2775ED':'#64748B';
          card.querySelector('[data-px]').textContent=fmt(live);
          var cg=card.querySelector('[data-cg]'); cg.style.color=col;
          cg.textContent=(up?'▲ +':dn?'▼ ':'– ')+Math.abs(pct).toFixed(2)+'%';
          var rtn=(live-p.entry)/p.entry*100;
          var rEl=card.querySelector('[data-rtn]'); rEl.style.color=rtn>0?'#E03131':rtn<0?'#2775ED':'#64748B';
          rEl.textContent='진입가 대비 '+(rtn>=0?'+':'')+rtn.toFixed(2)+'%';
          var span=(p.target-p.stop)||1;
          var pos=Math.max(0,Math.min(1,(live-p.stop)/span))*100;
          var ent=Math.max(0,Math.min(1,(p.entry-p.stop)/span))*100;
          card.querySelector('[data-fill]').style.width=pos+'%';
          card.querySelector('[data-dot]').style.left=pos+'%';
          card.querySelector('[data-entry]').style.left=ent+'%';
          var st=card.querySelector('[data-st]');
          if(live>=p.target){st.className='mt-st hit';st.textContent='🎯 목표 도달';}
          else if(live<=p.stop){st.className='mt-st loss';st.textContent='손절 이탈';}
          else{st.className='mt-st track';st.textContent='추적 중';}
        });
      }
      function poll(){
        if(!PICKS.length) return;
        fetch('/api/stocks-live?codes='+PICKS.map(function(p){return p.code;}).join(','),{cache:'no-store'})
          .then(function(r){return r.ok?r.json():null;})
          .then(function(d){ if(d&&d.prices) applyLive(d.prices); }).catch(function(){});
      }
      function loadPicks(date){
        fetch('/briefings/'+date+'/kospi/analysis_snapshot.json',{cache:'no-store'})
          .then(function(r){return r.ok?r.json():null;})
          .then(function(snap){
            var picks=(snap&&snap.stock_picks)||[];
            PICKS=picks.map(function(p){var e=parseEntry(p.entry);return {code:String(p.ticker||'').replace(/\.(KS|KQ)$/i,''),name:p.name,tag:p.scenario_tag||p.signal||'',entry:e.lo,entry_hi:e.hi,target:won(p.target),stop:won(p.stop),target_pct:p.target_pct||''};})
              .filter(function(p){return p.code&&p.entry&&p.target&&p.stop;});
            window.__momHasPicks = PICKS.length>0;
            if(!PICKS.length){ window.ueGate&&window.ueGate(); return; }
            grid.innerHTML=PICKS.map(cardHTML).join('');
            window.ueGate ? window.ueGate() : (box.style.display='');
            document.getElementById('mt-sub').textContent=date+' 코스피 픽 '+PICKS.length+'종목 · 진입/목표/손절 추적';
            // 장 준비 중(07:30~09:00)엔 아직 오늘 거래가 없어 전일 종가가 내려온다 — 방금 나온 픽에
            // 이미 가격이 붙어있는 것처럼 보여 혼동을 준다. 이 구간엔 가격을 아예 띄우지 않고 종목 정보만 둔다.
            if(momPhase()!=='prep') poll();
            setMomStatus();
            // 페이지를 열어둔 채 07:30·09:00·15:30 경계를 넘으면 상태·폴링을 자동 전환
            var momTimer=null;
            function ensurePolling(){
              if(momPhase()==='open'){ if(!momTimer) momTimer=setInterval(poll,45000); }
              else if(momTimer){ clearInterval(momTimer); momTimer=null; }
            }
            ensurePolling();
            setInterval(function(){ setMomStatus(); ensurePolling(); }, 60000);
          }).catch(function(){ window.__momHasPicks=false; window.ueGate&&window.ueGate(); });
      }
      // 최신 kospi 브리핑 날짜를 briefings-list.json에서 권위있게 해석 — DOM에 박힌 stale data-href(생성 시점 고정) 의존 제거
      function latestKospiDate(list){
        var slots=list&&list.slots; if(!slots) return null;
        var today=kstDate();
        if(slots[today]&&slots[today].kospi&&slots[today].kospi.state==='ready') return today;
        var dates=Object.keys(slots).sort().reverse();
        for(var i=0;i<dates.length;i++){ var k=slots[dates[i]].kospi; if(k&&k.state==='ready') return dates[i]; }
        return null;
      }
      fetch('/data/briefings-list.json',{cache:'no-store'})
        .then(function(r){return r.ok?r.json():null;})
        .then(function(list){ loadPicks(latestKospiDate(list)||briefDate()); })
        .catch(function(){ loadPicks(briefDate()); });
    })();

/* ── 블록 4 (원본 index.html) ── */
(function(){
  var box=document.getElementById('us-evening');
  if(!box) return;
  var gridEl=document.getElementById('ue-grid'), macroEl=document.getElementById('ue-macro');
  var TICKERS=[
    {nm:'메모리·HBM', tk:'DRAM',  sym:'DRAM.K', lead:true},
    {nm:'한국ETF',    tk:'EWY',   sym:'EWY.O', noLink:true},
    // SKHY(OTC ADR)는 미국 상세 페이지를 만들지 않는다 — yfinance에 6영업일치밖에 없어
    // MA20·MA200이 안 나오고, fetch_us_financials가 SK하이닉스 원화 실적을 돌려줘 USD로 찍힌다.
    // 실측이 온전한 한국 상세 페이지로 보낸다(운영규칙 0).
    {nm:'SK하이닉스', tk:'SKHY', sym:'SKHY.O', href:'/stocks/000660/'},
    {nm:'브로드컴',   tk:'AVGO',  sym:'AVGO.O'},
    {nm:'엔비디아',   tk:'NVDA',  sym:'NVDA.O'},
    {nm:'AMD',       tk:'AMD',   sym:'AMD.O'},
    {nm:'ASML',      tk:'ASML',  sym:'ASML.O'},
    // 파운드리·AI 반도체 벨웨더 — 밤사이 반도체 심리 최대 선행 지표. 상세 페이지 없어 noLink(추후 생성 시 해제).
    {nm:'TSMC',      tk:'TSM',   sym:'TSM.N', noLink:true},
    {nm:'마이크론',   tk:'MU',    sym:'MU.O'},
    // 순수 NAND 플래시 — 삼성·SK하이닉스 NAND read-through. 상세 페이지 없어 noLink(추후 생성 시 해제).
    {nm:'샌디스크',   tk:'SNDK',  sym:'SNDK.O', noLink:true},
    {nm:'반도체ETF',  tk:'SOXX',  sym:'SOXX.O'}
  ];
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
    if(typeof pct!=='number'||!isFinite(pct)) return '<span class="cg" style="color:#94A3B8">—</span>';
    var up=pct>0, col=up?'#E03131':(pct<0?'#2775ED':'#64748B'), s=up?'+':'';
    return '<span class="cg" style="color:'+col+'">'+s+pct.toFixed(2)+'%</span>';
  }
  function skeleton(){
    gridEl.innerHTML=TICKERS.map(function(){return '<div class="ue-row"><span class="nm"><span class="ue-skel" style="display:inline-block;width:90px;"></span></span><span class="ue-skel" style="width:70px;"></span></div>';}).join('');
    macroEl.innerHTML=['나스닥 QQQ','필라델피아 반도체','변동성 VIX'].map(function(l){return '<div class="ue-mtile"><div class="l">'+l+'</div><div class="v"><span class="ue-skel" style="display:inline-block;width:54px;"></span></div></div>';}).join('');
  }
  function renderGrid(){
    gridEl.innerHTML=TICKERS.map(function(t){
      var d=dataBySym[t.sym]||{};
      var inner='<span class="nm">'+t.nm+' <span class="tk">'+t.tk+'</span>'+(t.lead?' <span class="lead">선행</span>':'')+'</span>'
        +'<span class="px" data-usd="'+(d.price!=null?d.price:'')+'">'+fmtPx(d.price)+'</span>'+cgHtml(d.changePct);
      if(t.noLink) return '<div class="ue-row">'+inner+'<svg class="ue-go" width="14" height="14" viewBox="0 0 20 20" fill="none" style="visibility:hidden"><path d="M8 5l5 5-5 5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></div>';
      // href가 지정된 항목은 그쪽으로(예: SK하이닉스 → 한국 상세), 없으면 미국 상세 규칙 경로
      return '<a class="ue-row ue-row--link" href="'+(t.href||('/stocks/us/'+t.tk.toLowerCase()+'/'))+'">'+inner+'<svg class="ue-go" width="14" height="14" viewBox="0 0 20 20" fill="none"><path d="M8 5l5 5-5 5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></a>';
    }).join('');
  }
  function renderMacro(){
    var qq=dataBySym[NASDAQ]||{}, soxx=dataBySym['SOXX.O']||{};
    var vixHtml=(vix&&typeof vix.price==='number')
      ? vix.price.toFixed(2)+' <span style="font-size:12px">'+cgHtml(vix.changePct)+'</span>'
      : '<span class="cg" style="color:#94A3B8">—</span>';
    macroEl.innerHTML=''
      +'<div class="ue-mtile"><div class="l">나스닥 QQQ</div><div class="v">'+cgHtml(qq.changePct)+'</div></div>'
      +'<div class="ue-mtile"><div class="l">필라델피아 반도체</div><div class="v">'+cgHtml(soxx.changePct)+'</div></div>'
      +'<div class="ue-mtile"><div class="l">변동성 VIX</div><div class="v">'+vixHtml+'</div></div>';
    var cap=document.getElementById('ue-cap');
    if(cap) cap.textContent=(fx?'환율 '+fx.toLocaleString('en-US')+'원 적용 · ':'')+'미국 장 시작 전엔 전일 종가, 장중엔 실시간 · DRAM ETF는 메모리·HBM 선행지표';
  }
  // 11개 종목 상승/하락 요약(마켓 브레드스) — PC·모바일 모두 노출(원화/달러 토글과 같은 줄).
  // 여기선 데이터 유무만 has-data 클래스로 표시하고, 실제 표시 여부는 CSS가 결정한다(display를 JS가 직접 건드리지 않음).
  function renderBreadth(){
    var el=document.getElementById('ue-breadth'); if(!el) return;
    var up=0,down=0,flat=0,n=0;
    TICKERS.forEach(function(t){
      var d=dataBySym[t.sym];
      if(!d||typeof d.changePct!=='number'||!isFinite(d.changePct)) return;
      n++; if(d.changePct>0) up++; else if(d.changePct<0) down++; else flat++;
    });
    if(!n){ el.classList.remove('has-data'); el.innerHTML=''; return; }
    var p=['<b style="color:#E03131">'+up+' 상승</b>','<b style="color:#2775ED">'+down+' 하락</b>'];
    if(flat) p.push('<b style="color:#64748B">'+flat+' 보합</b>');
    el.innerHTML=n+'개 중&nbsp;'+p.join(' · ');
    el.classList.add('has-data');
  }
  function render(){ renderGrid(); renderMacro(); renderBreadth(); }
  /* 실시간 기준 배지 — 정규장/프리장/애프터장이면 LIVE, 그 외엔 전일 종가 표시 */
  function updateLiveBadge(){
    var b=document.getElementById('ue-live'); if(!b) return;
    var label={open:'정규장',pre:'프리장',post:'애프터장'}[sessionState];
    if(isLive && label){
      b.classList.remove('closed');
      b.innerHTML='<span class="dot"></span>LIVE · '+label+' · 10초 갱신';
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
      b.innerHTML='<span class="dot"></span>장 마감 · '+dt+'종가 기준';
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
    var rows=gridEl.querySelectorAll('.ue-row');
    TICKERS.forEach(function(t,i){
      var row=rows[i]; if(!row) return;
      var d=dataBySym[t.sym]||{};
      var px=row.querySelector('.px');
      if(px && typeof d.price==='number') animatePx(px, d.price);
      var cg=row.querySelector('.cg');
      if(cg && typeof d.changePct==='number'){
        var up=d.changePct>0;
        cg.style.color=up?'#E03131':(d.changePct<0?'#2775ED':'#64748B');
        cg.textContent=(up?'+':'')+d.changePct.toFixed(2)+'%';
      }
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
  var pollId=null, POLL_LIVE=10000, POLL_IDLE=60000, curPoll=0;
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
  // 노출 조건: 평일 17:00~익일 07:30. 주말(토·일)·평일 공휴일은 코스피 모멘텀이 갱신되지 않으므로 종일 노출.
  function isEvening(d){
    var wd=d.getUTCDay();
    if(wd===0||wd===6) return true;                    // 주말 종일
    var hm=d.getUTCHours()*60+d.getUTCMinutes();
    if(hm>=1020 || hm<450) return true;                // 평일 17:00~익일 07:30
    return todayKospiReady===false;                    // 평일 공휴일(오늘 코스피 미생성) = 비거래일 → 종일 노출
  }
  window.ueGate=function(){
    var ev=isEvening(kstNow());
    box.style.display = ev ? '' : 'none';
    var mt=document.getElementById('mom-track');
    if(mt) mt.style.display = ev ? 'none' : (window.__momHasPicks ? '' : 'none');
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
   /stocks/{code}/                 종목 상세   예) /stocks/000660/
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
// 종목 상세 — standalone 페이지로 실제 이동 (생성된 종목만, 나머지는 "준비 중" 토스트)
// 시드 3종목은 스냅샷 로드 전 즉시 클릭 대비. 나머지는 스냅샷 로드 시 유니버스 전체로 자동 채움
// (build_all_stocks가 유니버스 종목 페이지를 일괄 빌드하므로 스냅샷=빌드된 페이지 목록).
const STOCK_PAGES={'005930':1,'000660':1,'005380':1};
let _stockToastT=null;
function _stockToast(msg){
  let t=document.getElementById('stock-toast');
  if(!t){t=document.createElement('div');t.id='stock-toast';
    t.style.cssText='position:fixed;left:50%;bottom:32px;transform:translateX(-50%);background:rgba(17,24,39,.92);color:#fff;font-size:13px;font-weight:600;padding:10px 16px;border-radius:10px;z-index:9999;opacity:0;transition:opacity .2s;pointer-events:none;';
    document.body.appendChild(t);}
  t.textContent=msg;t.style.opacity='1';
  clearTimeout(_stockToastT);_stockToastT=setTimeout(()=>{t.style.opacity='0';},1800);
}
function goStock(code){if(STOCK_PAGES[code])location.href='/stocks/'+code+'/';else _stockToast('해당 종목 상세 페이지는 준비 중이에요.');}
// 허브 내부 화면 전환 — 유효한 screen이면 그 화면, 섹터 키 등은 반도체 섹터로
function goHub(screen){if(!screen){go('home');return;}if(document.getElementById(screen))go(screen);else go('sector');}
function go(id,noHistory){
  const el=document.getElementById(id);if(!el||!el.classList.contains('screen'))return;
  if(!noHistory){const cur=document.querySelector('.screen.on');if(cur&&cur.id!==id)navHistory.push(cur.id);}
  document.querySelectorAll('.screen').forEach(s=>s.classList.remove('on'));
  el.classList.add('on');
  window.scrollTo({top:0,behavior:'smooth'});
  history.pushState({screen:id},'','#'+id);
}
function goBack(){const prev=navHistory.pop();go(prev||'home',true);}
window.addEventListener('popstate',e=>{const id=(e.state&&e.state.screen)||(location.hash.slice(1)||'home');go(id,true);});
// 진입 시 해시(#sector 등)가 있으면 해당 화면 복원 — standalone에서 돌아올 때 사용
(function(){const h=location.hash.slice(1);if(!h)return;document.getElementById(h)?go(h,true):go('sector',true);})();
// #mom-track 앵커 — 코스피 브리핑 "종목 시그널에서 트래킹" CTA 진입 시 상승 모멘텀 종목 섹션으로 스크롤.
// 데이터 fetch·시간대 게이트(ueGate)로 표시가 비동기라 표시될 때까지 잠깐 폴링한다.
(function(){
  if(location.hash!=='#mom-track')return;
  let tries=0;
  const iv=setInterval(()=>{
    tries++;
    const el=document.getElementById('mom-track');
    if(el&&el.offsetParent!==null){el.scrollIntoView({behavior:'smooth',block:'start'});clearInterval(iv);}
    else if(tries>20)clearInterval(iv);
  },500);
})();
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

/* 거래량 순위 화면 — vol-top all 실데이터(탭 거래량/상승률/하락률 + 섹터필터 + 더보기). */
let RANK_ALL=[];      // vol-top all (실측 ~40종목)
let SIG_BY_CODE={};   // signals 보유 종목 code→true (AI신호 열)
let SIGNALS_HOME=[];  // 홈 특이신호 (정렬 재적용용)
let SIGNALS_ALL=[];   // 특이 신호 전체(더보기 화면용) — /api/signals.signalsAll
let SIG_ASOF=null;    // 신호 기준일 메타(제목 prefix용)
let sigHomeSort='up'; // score | up
let sigAllSort='up'; // score | up | dn
let rankTab='vol';    // vol | up | dn
let rankSector='전체';
let rankShown=10;
let _rankMax=1;
function rankSecKo(s){return (typeof _SECKO!=='undefined'&&_SECKO[s])?_SECKO[s]:(s||'');}
function fmtVol(v){return Math.round((v||0)/10000).toLocaleString('en-US')+'만주';}
function rankSorted(){
  var arr=RANK_ALL.filter(function(x){return rankSector==='전체'||rankSecKo(x.sector)===rankSector;});
  if(rankTab==='up')return arr.filter(function(x){return x.changePct>0;}).sort(function(a,b){return b.changePct-a.changePct;});
  if(rankTab==='dn')return arr.filter(function(x){return x.changePct<0;}).sort(function(a,b){return a.changePct-b.changePct;});
  return arr.slice().sort(function(a,b){return (b.vol||0)-(a.vol||0);});
}
function rankRow(x,i){
  var rank=i+1,top3=rank<=3,pct=x.changePct||0,dir=pct>0?'up':pct<0?'dn':'';
  var pctTxt=(pct>0?'+':pct<0?'−':'')+Math.abs(pct).toFixed(1)+'%';
  var bar=rankTab==='vol'?Math.round((x.vol||0)/(_rankMax||1)*100):Math.round(Math.abs(pct)/(_rankMax||1)*100);
  var badge=SIG_BY_CODE[x.code]?'<span class="ais">신호</span>':'<span class="ax">—</span>';
  return '<a class="trow" onclick="goStock(\''+x.code+'\')"><span class="rk'+(top3?' t':'')+' num">'+rank+'</span><div class="nm"><b>'+x.name+'</b><small class="num">'+x.code+' · '+rankSecKo(x.sector)+'</small></div><div class="barwrap"><div class="bar vol" style="width:'+bar+'%"></div></div><span class="barval num">'+fmtVol(x.vol)+'</span><span class="tchg '+dir+' num">'+pctTxt+'</span><div class="ai">'+badge+'</div></a>';
}
function rankRender(){
  var box=document.getElementById('rank-rows');if(!box)return;
  var cnt=document.getElementById('rank-count');if(cnt)cnt.textContent='추적 '+RANK_ALL.length+'종목';
  var arr=rankSorted();
  _rankMax=arr.length?(rankTab==='vol'?Math.max.apply(null,arr.map(function(x){return x.vol||0;})):Math.max.apply(null,arr.map(function(x){return Math.abs(x.changePct||0);}))):1;
  var btn=document.getElementById('rank-more');
  if(!arr.length){box.innerHTML='<div style="padding:18px 16px;font-size:12px;color:#94A3B8;">'+(RANK_ALL.length?'해당 조건의 종목이 없어요.':'종목을 불러오는 중…')+'</div>';if(btn)btn.style.display='none';return;}
  box.innerHTML=arr.slice(0,rankShown).map(rankRow).join('');
  if(!btn)return;
  if(rankShown>=arr.length){btn.style.display='none';}
  else{btn.style.display='';btn.textContent='더보기 · '+(Math.min(rankShown+10,arr.length)-rankShown)+'개 더 ('+(arr.length-rankShown)+'개 남음)';}
}
function rankLoadMore(){rankShown=Math.min(rankShown+10,rankSorted().length);rankRender();}
function rankSetTab(tab,el){rankTab=tab;rankShown=10;if(el){[].forEach.call(el.parentNode.children,function(a){a.classList.remove('on');});el.classList.add('on');}rankRender();}
function rankSetSector(sec,el){rankSector=sec;rankShown=10;if(el){[].forEach.call(el.parentNode.children,function(a){a.classList.remove('on');});el.classList.add('on');}rankRender();}
rankRender();

/* ETF 전체 랭킹 화면 — vol-top etf 실데이터(등락률순). */
let ETF_ALL=[];
function etfRankTag(name){
  if(/레버리지|2X|2x/.test(name))return '<span style="font-size:10px;font-weight:800;padding:1px 6px;border-radius:999px;background:var(--up-bg);color:var(--up)">레버리지</span>';
  if(/인버스|곱버스/.test(name))return '<span style="font-size:10px;font-weight:800;padding:1px 6px;border-radius:999px;background:var(--dn-bg);color:var(--dn)">인버스</span>';
  return '';
}
function fmtVolShort(v){if(v>=100000000)return (v/100000000).toFixed(1)+'억주';return Math.round(v/10000).toLocaleString('en-US')+'만주';}
let etfTab='vol';
let etfShown=10;
function etfSorted(){
  if(etfTab==='up')return ETF_ALL.filter(function(x){return x.changePct>0;}).sort(function(a,b){return b.changePct-a.changePct;});
  if(etfTab==='dn')return ETF_ALL.filter(function(x){return x.changePct<0;}).sort(function(a,b){return a.changePct-b.changePct;});
  return ETF_ALL.slice().sort(function(a,b){return (b.vol||0)-(a.vol||0);});
}
function etfRankRender(){
  var box=document.getElementById('etf-rank-rows');if(!box)return;
  var cnt=document.getElementById('etf-rank-count');if(cnt)cnt.textContent=ETF_ALL.length+'개 ETF';
  if(!ETF_ALL.length){box.innerHTML='<div style="padding:18px 16px;font-size:12px;color:#94A3B8;">ETF를 불러오는 중…</div>';var btn=document.getElementById('etf-rank-more');if(btn)btn.style.display='none';return;}
  var arr=etfSorted();
  var maxVal=arr.length?(etfTab==='vol'?Math.max.apply(null,arr.map(function(x){return x.vol||0;})):Math.max.apply(null,arr.map(function(x){return Math.abs(x.changePct||0);}))):1;
  if(!maxVal)maxVal=1;
  var btn=document.getElementById('etf-rank-more');
  if(!arr.length){box.innerHTML='<div style="padding:18px 16px;font-size:12px;color:#94A3B8;">'+(etfTab==='up'?'상승 ETF가 없어요.':'하락 ETF가 없어요.')+'</div>';if(btn)btn.style.display='none';return;}
  box.innerHTML=arr.map(function(x,i){
    var rank=i+1,top3=rank<=3,pct=x.changePct||0,dir=pct>0?'up':pct<0?'dn':'';
    var pctTxt=(pct>0?'+':pct<0?'−':'')+Math.abs(pct).toFixed(2)+'%';
    var barW=etfTab==='vol'?Math.round((x.vol||0)/maxVal*100):Math.round(Math.abs(pct)/maxVal*100);
    var tag=etfRankTag(x.name);
    var avg20=x.vol_avg20||0;
    var mult=avg20>0?((x.vol||0)/avg20):0;
    var multTxt=mult>0?mult.toFixed(1)+'×':'—';
    var multCls=mult>=1.5?'color:var(--up);font-weight:800':'color:var(--muted)';
    return '<a class="trow trow--static" style="cursor:default">'
      +'<span class="rk'+(top3?' t':'')+' num">'+rank+'</span>'
      +'<div class="nm"><b>'+x.name+'</b><small class="num">'+x.code+(tag?' · ':'')+'</small>'+tag+'</div>'
      +'<div class="barwrap"><div class="bar vol" style="width:'+barW+'%"></div></div>'
      +'<span class="barval num">'+fmtVolShort(x.vol||0)+'</span>'
      +'<span class="num" style="width:56px;text-align:right;flex:none;font-size:11px;font-weight:700;'+multCls+'">'+multTxt+'</span>'
      +'<span class="tchg '+dir+' num" style="width:72px;text-align:right;flex:none;">'+pctTxt+'</span>'
      +'</a>';
  }).join('');
}
function etfSetTab(tab,el){etfTab=tab;etfShown=10;if(el){[].forEach.call(el.parentNode.children,function(a){a.classList.remove('on');});el.classList.add('on');}etfRankRender();}
function etfLoadMore(){etfShown=Math.min(etfShown+10,30);etfRankRender();}
/* 우측 사이드 — 하락률 순(상위 10) */
function etfDnSorted(){return ETF_ALL.filter(function(x){return (x.changePct||0)<0;}).sort(function(a,b){return a.changePct-b.changePct;});}
function etfDnRender(){
  var box=document.getElementById('etf-dn-rows');if(!box)return;
  if(!ETF_ALL.length){box.innerHTML='<div style="padding:18px 16px;font-size:12px;color:#94A3B8;">불러오는 중…</div>';return;}
  var arr=etfDnSorted().slice(0,10);
  if(!arr.length){box.innerHTML='<div style="padding:18px 16px;font-size:12px;color:#94A3B8;">하락 ETF가 없어요.</div>';return;}
  box.innerHTML=arr.map(function(x,i){
    var pct=x.changePct||0,tag=etfRankTag(x.name);
    return '<div class="etf-row">'
      +'<span class="num" style="width:15px;text-align:center;font-size:11px;font-weight:800;color:#94A3B8;flex-shrink:0;">'+(i+1)+'</span>'
      +'<span class="etf-nm" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'+x.name+(tag?' ':'')+tag+'</span>'
      +'<span class="etf-pct dn num">−'+Math.abs(pct).toFixed(2)+'%</span>'
      +'</div>';
  }).join('');
}
etfRankRender();
etfDnRender();

/* 더보기 자동 트리거 — 스크롤 시 버튼이 뷰포트 근처면 자동 확장 (500ms 쓰로틀) */
(function(){
  function isNearViewport(el){var r=el.getBoundingClientRect();return r.top<window.innerHeight+200&&r.bottom>-200;}
  var _t=0;
  function check(){
    var rm=document.getElementById('rank-more');
    if(rm&&getComputedStyle(rm).display!=='none'&&isNearViewport(rm)) rankLoadMore();
    var em=document.getElementById('etf-rank-more');
    if(em&&getComputedStyle(em).display!=='none'&&isNearViewport(em)) etfLoadMore();
  }
  window.addEventListener('scroll',function(){
    if(_t) return;
    _t=setTimeout(function(){_t=0;check();},500);
  },{passive:true});
})();

/* 섹터 종목 랭킹 — 15개 기본 + 10개씩 더보기 (시총순, 바=등락률) */
const SECTOR_RANK=[
  [1,'삼성전자','005930','dn','−6.4%',100,'ais','신호 58'],
  [2,'SK하이닉스','000660','up','+3.4%',62,'aip','AI 78'],
  [3,'한미반도체','042700','up','+1.8%',40,'ais','신호 71'],
  [4,'DB하이텍','000990','up','+1.8%',38,'ais','신호 64'],
  [5,'리노공업','058470','up','+0.9%',26,'ais','신호 60'],
  [6,'이오테크닉스','039030','up','+2.1%',44,'ais','신호 62'],
  [7,'주성엔지니어링','036930','up','+9.4%',96,'ais','신호 69'],
  [8,'원익IPS','240810','up','+1.4%',32,'ais','신호 55'],
  [9,'ISC','095340','up','+0.6%',20,'ax','—'],
  [10,'솔브레인','357780','dn','−1.2%',28,'aid','신호 47'],
  [11,'HPSP','403870','up','+3.1%',56,'ais','신호 67'],
  [12,'테스','095610','up','+2.7%',50,'ais','신호 58'],
  [13,'하나마이크론','067310','dn','−2.4%',46,'aid','신호 44'],
  [14,'동진쎄미켐','005290','up','+0.4%',16,'ax','—'],
  [15,'티씨케이','064760','dn','−0.8%',22,'ais','신호 52'],
  [16,'고영','098460','up','+1.1%',28,'ais','신호 56'],
  [17,'피에스케이','319660','up','+4.2%',70,'ais','신호 65'],
  [18,'유진테크','084370','up','+1.6%',34,'ais','신호 59'],
  [19,'네패스','033640','dn','−3.1%',54,'aid','신호 39'],
  [20,'심텍','222800','up','+5.5%',82,'ais','신호 68'],
  [21,'가온칩스','399720','up','+2.0%',42,'ais','신호 61'],
  [22,'에스앤에스텍','101490','up','+1.3%',30,'ais','신호 54'],
  [23,'케이씨텍','281820','up','+0.7%',20,'ax','—'],
  [24,'코미코','183300','dn','−1.5%',32,'aid','신호 46'],
  [25,'대주전자재료','078600','up','+6.8%',88,'ais','신호 66'],
  [26,'월덱스','101160','up','+0.5%',18,'ax','—'],
  [27,'엘오티베큠','083310','dn','−0.6%',18,'ais','신호 50'],
  [28,'어보브반도체','102120','up','+1.9%',40,'ais','신호 57'],
];
let secShown=15;
function secRow(r){
  const top3=r[0]<=3;
  const badge=r[6]==='ax'?`<span class="ax">—</span>`:`<span class="${r[6]}">${r[7]}</span>`;
  return `<a class="row" onclick="goStock('000660')"><span class="rk${top3?' t':''} num">${r[0]}</span><div class="nm"><b>${r[1]}</b><small class="num">${r[2]}</small></div><div class="barwrap"><div class="bar ${r[3]}" style="width:${r[5]}%"></div></div><span class="barval ${r[3]} num">${r[4]}</span><div class="ai">${badge}</div></a>`;
}
function secRender(){
  const wrap=document.getElementById('sec-rows');
  if(!wrap)return;
  wrap.innerHTML=SECTOR_RANK.slice(0,secShown).map(secRow).join('');
  const btn=document.getElementById('sec-more');
  if(secShown>=SECTOR_RANK.length){btn.textContent=`반도체 ${SECTOR_RANK.length}종목 전체 →`;btn.setAttribute('onclick',"go('ranking')");}
  else{btn.textContent=`더보기 · ${Math.min(secShown+10,SECTOR_RANK.length)-secShown}개 더 (${SECTOR_RANK.length-secShown}개 남음)`;btn.setAttribute('onclick','secLoadMore()');}
}
function secLoadMore(){secShown=Math.min(secShown+10,SECTOR_RANK.length);secRender();}
secRender();

/* AI 뱃지 툴팁 — position:fixed (카드 overflow에 안 잘림) */
const tip=document.getElementById('tip');
function tipHTML(el){
  if(el.dataset.tip)
    return `<div class="tt">${el.dataset.tipTitle||'안내'}</div><div class="bd">${el.dataset.tip}</div>`;
  if(el.classList.contains('badge-info-btn'))
    return `<div class="tt">AI 뱃지 안내</div><div class="bd" style="line-height:1.6">
      <div style="display:flex;align-items:flex-start;gap:7px;margin-bottom:6px"><span class="aip" style="font-size:10px;padding:2px 7px;flex:none">AI 78</span><span><b>Claude 픽</b> — AI 브리핑이 오늘 선택한 종목</span></div>
      <div style="display:flex;align-items:flex-start;gap:7px;margin-bottom:6px"><span class="ais" style="font-size:10px;padding:2px 7px;flex:none">신호 64</span><span><b>기술신호 상승</b> — 이평선·모멘텀 종합 58↑</span></div>
      <div style="display:flex;align-items:flex-start;gap:7px;margin-bottom:6px"><span class="aid" style="font-size:10px;padding:2px 7px;flex:none">신호 42</span><span><b>기술신호 약세</b> — 이평선 아래 42↓</span></div>
      <div style="display:flex;align-items:flex-start;gap:7px"><span class="ax" style="font-size:11px;flex:none">—</span><span><b>신호 없음</b> — 데이터 부족(상장 200일↓)</span></div>
    </div>`;
  const n=(el.textContent.match(/\d+/)||['?'])[0];
  if(el.classList.contains('vol-surge-badge')){
    const m=el.textContent.match(/×([\d.]+)/);const mult=m?m[1]:'N';
    return `<div class="tt" style="color:#E8590C">🔶 거래량 ×${mult} 급증</div><div class="bd">오늘 거래량이 <b>최근 20일 평균 대비 ${mult}배</b>예요. 수치가 높을수록 <b>이례적인 거래 폭증</b>이에요. 외국인·기관 수급이 함께 들어왔다면 의미 있는 수급 유입 신호로 볼 수 있어요.</div>`;
  }
  if(el.classList.contains('pbdg')&&el.classList.contains('high'))
    return `<div class="tt" style="color:#92400E">🟡 패시브 노출 高</div><div class="bd">코스피200·반도체 등 주요 ETF가 <b>구조적으로 대량 보유</b>하는 종목이에요. 분기 말·지수 변경일마다 ETF 기계매매가 자동으로 대규모 수급을 만들어요. <b>리밸런싱 시즌에 변동성이 커질 수 있어요.</b></div>`;
  if(el.classList.contains('pbdg')&&el.classList.contains('mid'))
    return `<div class="tt" style="color:#065F46">🟢 패시브 노출 中</div><div class="bd">ETF 기계매매 노출이 <b>중간 수준</b>인 종목이에요. 패시브 수급 영향을 받지만 高보다는 낮아요. 리밸런싱 영향이 있을 때 단기 수급 변화를 참고하세요.</div>`;
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
document.querySelectorAll('.aip,.ais,.aid,.ax,.badge-info-btn,.vol-surge-badge,.pbdg,.help-q').forEach(el=>{
  el.addEventListener('mouseenter',showTip);
  el.addEventListener('mousemove',moveTip);
  el.addEventListener('mouseleave',hideTip);
});
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
  sq.addEventListener('keydown',e=>{
    if(e.key==='ArrowDown'){e.preventDefault();_sqMove(1);}
    else if(e.key==='ArrowUp'){e.preventDefault();_sqMove(-1);}
    else if(e.key==='Enter'){e.preventDefault();_sqEnter();}
  });
})();
document.addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();openSearch();}if(e.key==='Escape')closeSearch();});

/* ── 패시브 민감주 랭킹 ── */
const PASSIVE_DATA=[
  {code:'039030',name:'이오테크닉스',sector:'반도체',conc:20.2,dov:15.0,score:98,badge:'high',etf:'TIGER 반도체TOP10'},
  {code:'058140',name:'리노공업',sector:'반도체',conc:21.0,dov:13.9,score:96,badge:'high',etf:'TIGER 반도체TOP10'},
  {code:'240810',name:'원익IPS',sector:'반도체',conc:18.9,dov:10.5,score:80,badge:'high',etf:'TIGER 반도체TOP10'},
  {code:'000990',name:'DB하이텍',sector:'반도체',conc:18.0,dov:9.2,score:74,badge:'high',etf:'KODEX 반도체'},
  {code:'042700',name:'한미반도체',sector:'반도체',conc:12.3,dov:8.7,score:58,badge:'high',etf:'KODEX 반도체'},
  {code:'095340',name:'ISC',sector:'반도체',conc:10.4,dov:7.6,score:50,badge:'mid',etf:'TIGER 반도체TOP10'},
  {code:'247540',name:'에코프로비엠',sector:'2차전지',conc:6.0,dov:6.8,score:37,badge:'mid',etf:'TIGER 2차전지테마'},
  {code:'357780',name:'솔브레인',sector:'반도체',conc:6.8,dov:6.3,score:37,badge:'mid',etf:'TIGER 반도체TOP10'},
  {code:'086520',name:'에코프로',sector:'2차전지',conc:6.4,dov:4.8,score:31,badge:'mid',etf:'TIGER 2차전지테마'},
];
let pSortKey='dov';
const maxDov=15.0;
function passiveRow(r,i){
  const pct=Math.round(r.dov/maxDov*100);
  const badgeHtml=r.badge==='high'?'<span class="pbdg high">高</span>':'<span class="pbdg mid">中</span>';
  const barVal=pSortKey==='conc'?r.conc+'%':pSortKey==='score'?r.score:r.dov+'일';
  const barPct=pSortKey==='conc'?Math.round(r.conc/21*100):pSortKey==='score'?r.score:pct;
  return `<a class="prank-row" onclick="goStock('000660')">
    <span class="rk2 num">${i+1}</span>
    <div class="nm" style="width:136px;flex-shrink:0;"><b style="font-size:13px;">${r.name}</b><small class="num" style="font-size:10px;color:var(--muted);">${r.code} · ${r.sector}</small></div>
    <div class="dov-bar"><div class="fill" style="width:${barPct}%"></div><span class="val">${barVal}</span></div>
    <span class="conc-col num">${r.conc}%</span>
    <span class="score-col num">${r.score}</span>
    <div style="width:36px;text-align:right;flex-shrink:0;">${badgeHtml}</div>
  </a>`;
}
function passiveRender(){
  const sorted=[...PASSIVE_DATA].sort((a,b)=>b[pSortKey]-a[pSortKey]);
  document.getElementById('passive-rows').innerHTML=sorted.map((r,i)=>passiveRow(r,i)).join('');
  const labels={dov:'거래일수 (ETF 물량 소화일)',conc:'집중도 (시총 대비 패시브 자금)',score:'민감도 점수 (0~100)'};
  document.getElementById('pbar-label').textContent=labels[pSortKey];
}
function passiveSort(key,el){
  pSortKey=key;
  document.querySelectorAll('#psort-tabs a').forEach(a=>a.classList.remove('on'));
  el.classList.add('on');
  passiveRender();
}
passiveRender();

/* ── 배당 인컴 설계기 (보유=주 단위, 주가 기반 인컴 계산) ── */
// 국내 18종 = data/income_etfs.json 실측(2026-06-11 기준, build_income_etfs.py). US 3종은 해외 직상장 데모용 샘플.
const INCOME_UNIVERSE=[
  {code:'494300',name:'KODEX 미국나스닥100데일리커버드콜OTM',aum:0.88,price:10835,y:18.48,r:42.93,mk:'KR'},
  {code:'498410',name:'KODEX 금융고배당TOP10타겟위클리커버드콜',aum:0.77,price:11925,y:16.4,r:16.35,mk:'KR'},
  {code:'490590',name:'RISE 미국AI밸류체인데일리고정커버드콜',aum:0.75,price:16510,y:15.87,r:89.59,mk:'KR'},
  {code:'472150',name:'TIGER 배당커버드콜액티브',aum:1.93,price:25580,y:14.68,r:177.47,mk:'KR'},
  {code:'475720',name:'RISE 200위클리커버드콜',aum:0.92,price:15065,y:14.61,r:100.36,mk:'KR'},
  {code:'486290',name:'TIGER 미국나스닥100타겟데일리커버드콜',aum:1.89,price:11970,y:13.48,r:44.7,mk:'KR'},
  {code:'476550',name:'TIGER 미국30년국채커버드콜액티브(H)',aum:0.9,price:7240,y:13.02,r:1.85,mk:'KR'},
  {code:'481060',name:'KODEX 미국30년국채타겟커버드콜(합성 H)',aum:0.84,price:7750,y:12.94,r:1.67,mk:'KR'},
  {code:'498400',name:'KODEX 200타겟위클리커버드콜',aum:6.74,price:25050,y:11.23,r:174.81,mk:'KR'},
  {code:'329200',name:'TIGER 리츠부동산인프라',aum:1.47,price:4075,y:9.54,r:6.03,mk:'KR'},
  {code:'458760',name:'TIGER 미국배당다우존스타겟커버드콜2호',aum:0.73,price:11670,y:9.15,r:35.42,mk:'KR'},
  {code:'441640',name:'KODEX 미국배당커버드콜액티브',aum:1.62,price:13395,y:8.7,r:29.7,mk:'KR'},
  {code:'441800',name:'TIME Korea플러스배당액티브',aum:0.95,price:34340,y:5.31,r:137.48,mk:'KR'},
  {code:'161510',name:'PLUS 고배당주',aum:2.49,price:26330,y:3.77,r:47.47,mk:'KR'},
  {code:'466940',name:'TIGER 은행고배당플러스TOP10',aum:0.8,price:25865,y:3.66,r:50.98,mk:'KR'},
  {code:'446720',name:'SOL 미국배당다우존스',aum:1.01,price:14360,y:2.76,r:37.41,mk:'KR'},
  {code:'402970',name:'ACE 미국배당다우존스',aum:0.92,price:15900,y:2.73,r:37.68,mk:'KR'},
  {code:'458730',name:'TIGER 미국배당다우존스',aum:3.9,price:15670,y:2.69,r:37.49,mk:'KR'},
  {code:'JEPI',name:'JPMorgan 에쿼티프리미엄 (JEPI)',aum:0,price:78000,y:7.8,r:9.5,mk:'US'},
  {code:'SCHD',name:'Schwab 미국배당 (SCHD)',aum:0,price:38000,y:3.5,r:12.0,mk:'US'},
  {code:'QYLD',name:'Global X 나스닥커버드콜 (QYLD)',aum:0,price:24000,y:11.8,r:2.5,mk:'US'},
];
const UNIV={};INCOME_UNIVERSE.forEach(d=>UNIV[d.code]=d);
function incomeHealth(d){const e=d.r-d.y;if(e>=0)return['ok','건전',e];if(e>=-d.y/2)return['warn','주의',e];return['bad','원금성',e];}

/* 사이드바: 인컴 ETF 전체 (국내 1조+) */
const BADGE_TIPS={ok:'총수익이 분배율을 웃돌아요. 분배하면서도 자산이 불어나는 구조예요.',warn:'총수익이 분배율보다 약간 낮아요. 분배금 일부에 원금이 섞여 있을 수 있어요.',bad:'총수익이 분배율을 크게 밑돌아요. 분배금 상당 부분이 원금 반환 구조예요.'};
function incomeRow(d,i){
  const[hc,hl,e]=incomeHealth(d);
  const rk=i+1,rkCls=rk<=3?'rk top':'rk';
  const rTxt=`${d.r>=0?'+':''}${d.r}%`;
  const eTxt=e>=0?`<span style="color:#00ae1a">가격 +${e.toFixed(0)}%</span>`:`<span style="color:#f33942">가격 ${e.toFixed(0)}%</span>`;
  const bdgTip=BADGE_TIPS[hc]?`<span class="hbdg-tip">${BADGE_TIPS[hc]}</span>`:'';
  return `<a class="irow" onclick="addFromRanking('${d.code}')">
    <div class="it"><span class="${rkCls}"><span class="rk-n">${rk}</span><span class="rk-p">+</span></span><b>${d.name}</b><span class="hbdg-w"><span class="hbdg ${hc}">${hl}</span>${bdgTip}</span></div>
    <div class="imeta num">${d.code} · 순자산 ${d.aum.toFixed(1)}조</div>
    <div class="imx"><span class="yv num">${d.y}%</span> 분배 · 총수익 <b class="num" style="color:var(--ink)">${rTxt}</b> · ${eTxt}</div>
  </a>`;
}
let iSortKey='y';
function incomeRender(){
  const excludeCC=document.getElementById('cc-exclude')?.checked;
  let arr=INCOME_UNIVERSE.filter(d=>d.mk==='KR');
  if(excludeCC)arr=arr.filter(d=>!d.name.includes('커버드콜'));
  if(iSortKey==='y')arr.sort((a,b)=>b.y-a.y);
  else arr.sort((a,b)=>(b.r-b.y)-(a.r-a.y));
  arr=arr.slice(0,15);
  document.getElementById('income-rows').innerHTML=arr.map(incomeRow).join('');
}
function incomeSort(k,el){
  iSortKey=k;
  document.querySelectorAll('#isort-tabs a').forEach(a=>a.classList.remove('on'));el.classList.add('on');
  document.getElementById('icap-y').style.display=k==='y'?'':'none';
  document.getElementById('icap-h').style.display=k==='health'?'':'none';
  incomeRender();
}
incomeRender();

/* 메인: 인컴 시뮬레이터 — 보유(주) 입력 → 인컴·원금성 경고·종합과세·갭 */
const SIM_KEY='ds-income-holdings-v1';
function saveHoldings(){try{localStorage.setItem(SIM_KEY,JSON.stringify(simHoldings));}catch(e){}}
function loadHoldings(){try{const s=localStorage.getItem(SIM_KEY);if(s){const p=JSON.parse(s);if(Array.isArray(p)&&p.length)return p;}}catch(e){}return null;}
let simHoldings=loadHoldings()||[{code:'476550',qty:2000},{code:'458760',qty:3000},{code:'JEPI',qty:200}];
function simIncome(h){const d=UNIV[h.code];return h.qty*d.price*d.y/100/10000;}  // 만원/년
function simRowsRender(){
  document.getElementById('sim-rows').innerHTML=simHoldings.map((h,i)=>{
    const d=UNIV[h.code],inc=simIncome(h),val=h.qty*d.price/10000;
    return `<div class="simrow">
      <div class="snm">${d.name}<span class="mk">${d.mk}</span></div>
      <div class="qty"><input type="number" value="${h.qty}" oninput="simSet(${i},this.value)"><span>주</span></div>
      <div class="sinc" id="sinc-${i}"><b class="num">${inc.toFixed(0)}만원</b><small>평가 ${val.toFixed(0)}만 · 분배 ${d.y}%</small></div>
      <div class="sx" onclick="simDel(${i})">×</div>
    </div>`;
  }).join('');
}
function simSet(i,v){
  simHoldings[i].qty=Math.max(0,parseInt(v)||0);saveHoldings();
  const h=simHoldings[i],d=UNIV[h.code],inc=simIncome(h),val=h.qty*d.price/10000;
  const el=document.getElementById('sinc-'+i);
  if(el)el.innerHTML=`<b class="num">${inc.toFixed(0)}만원</b><small>평가 ${val.toFixed(0)}만 · 분배 ${d.y}%</small>`;
  simOut();
}
function simDel(i){simHoldings.splice(i,1);saveHoldings();simRowsRender();simOut();}
/* 사이드바 행 클릭 → 시뮬레이터에 바로 담기 */
function addFromRanking(code){
  const ex=simHoldings.findIndex(h=>h.code===code);
  if(ex>=0)simHoldings[ex].qty+=100; else simHoldings.push({code,qty:100});
  saveHoldings();simRowsRender();simOut();
  const rows=document.querySelectorAll('#sim-rows .simrow');
  const idx=ex>=0?ex:simHoldings.length-1,el=rows[idx];
  if(el){
    el.style.transition='background .4s';el.style.background='#EEF2FF';
    setTimeout(()=>el.style.background='',700);
    el.scrollIntoView({block:'nearest'});
    const inp=el.querySelector('.qty input');
    if(inp){inp.focus();inp.select();}
  }
}

/* 콤보박스: 순자산 톱20 기본 + 이름·코드 검색 */
let comboSel=null,comboCur=[],comboIdx=-1;
function comboItems(q){
  q=(q||'').trim().toLowerCase();
  if(!q)return[...INCOME_UNIVERSE].sort((a,b)=>b.aum-a.aum).slice(0,20);
  return INCOME_UNIVERSE.filter(d=>d.name.toLowerCase().includes(q)||d.code.toLowerCase().includes(q));
}
function comboRender(q){
  const arr=comboItems(q),list=document.getElementById('combo-list');comboCur=arr;
  if(!arr.length){list.innerHTML='<div class="combo__none">검색 결과 없음</div>';return;}
  const hd=(q||'').trim()?'':'<div class="combo__hd">순자산 톱20</div>';
  list.innerHTML=hd+arr.map((d,i)=>`<div class="combo__item${i===comboIdx?' sel':''}" onmousedown="comboPick('${d.code}')"><span class="ci-nm">${d.name}<small class="num">${d.code}</small></span><span class="ci-mk">${d.mk}</span><span class="ci-y num">${d.y}%</span></div>`).join('');
}
function comboOpen(){comboRender(document.getElementById('sim-search').value);document.getElementById('combo-list').classList.add('on');}
function comboFilter(){comboSel=null;comboIdx=-1;comboOpen();}
function comboClose(){setTimeout(()=>document.getElementById('combo-list').classList.remove('on'),150);}
function comboPick(code){comboSel=code;document.getElementById('sim-search').value=UNIV[code].name;document.getElementById('combo-list').classList.remove('on');}
function comboHighlight(){
  const items=document.querySelectorAll('#combo-list .combo__item');
  items.forEach((el,i)=>el.classList.toggle('sel',i===comboIdx));
  if(comboIdx>=0&&items[comboIdx])items[comboIdx].scrollIntoView({block:'nearest'});
}
function comboKey(e){
  const list=document.getElementById('combo-list');
  if(!list.classList.contains('on')){if(e.key==='ArrowDown')comboOpen();return;}
  if(e.key==='ArrowDown'){e.preventDefault();comboIdx=Math.min(comboCur.length-1,comboIdx+1);comboHighlight();}
  else if(e.key==='ArrowUp'){e.preventDefault();comboIdx=Math.max(0,comboIdx-1);comboHighlight();}
  else if(e.key==='Enter'){if(comboIdx>=0&&comboCur[comboIdx]){e.preventDefault();comboPick(comboCur[comboIdx].code);}}
  else if(e.key==='Escape'){list.classList.remove('on');}
}
function simAdd(){
  if(!comboSel){const q=document.getElementById('sim-search').value.trim().toLowerCase();const m=INCOME_UNIVERSE.find(d=>d.name.toLowerCase()===q||d.code.toLowerCase()===q);if(m)comboSel=m.code;}
  const qty=parseInt(document.getElementById('sim-amt').value)||0;
  if(comboSel&&qty>0){
    simHoldings.push({code:comboSel,qty});
    comboSel=null;document.getElementById('sim-search').value='';
    saveHoldings();simRowsRender();simOut();
    const rows=document.querySelectorAll('#sim-rows .simrow');
    const el=rows[simHoldings.length-1];
    if(el){el.scrollIntoView({block:'nearest'});const inp=el.querySelector('.qty input');if(inp){inp.focus();inp.select();}}
  }
}
const DONUT_COLORS=['#4F46E5','#2775ED','#10B981','#8B5CF6','#D97706','#EF4444','#EC4899','#6366F1','#F59E0B'];
const GAP_COLOR='#E5E7EB';

function buildDonut(segs, monthly){
  const CX=70,CY=70,R=50,W=18,circ=2*Math.PI*R;
  const gap=segs.length>1?1.5:0;
  let offset=0;
  const arcs=segs.map((s,i)=>{
    const len=Math.max(0,s.pct*circ-gap);
    const el=`<circle cx="${CX}" cy="${CY}" r="${R}" fill="none" stroke="${s.color}" stroke-width="${W}" stroke-linecap="butt" stroke-dasharray="${len.toFixed(2)} ${(circ-len).toFixed(2)}" stroke-dashoffset="${(-offset).toFixed(2)}" class="donut-arc" data-i="${i}" transform="rotate(-90 ${CX} ${CY})"/>`;
    offset+=s.pct*circ;
    return el;
  }).join('');
  return `<svg class="donut-svg" viewBox="0 0 140 140" width="140" height="140">
    <circle cx="${CX}" cy="${CY}" r="${R}" fill="none" stroke="var(--hair)" stroke-width="${W}"/>
    ${arcs}
    <text x="${CX}" y="${CY-5}" text-anchor="middle" font-size="17" font-weight="700" fill="var(--ink)" font-family="inherit">${monthly.toFixed(0)}</text>
    <text x="${CX}" y="${CY+12}" text-anchor="middle" font-size="10" fill="var(--muted)" font-family="inherit">만원/월</text>
  </svg>`;
}

function setupDonutTip(segs){
  const tip=document.getElementById('donut-tip');
  if(!tip)return;
  document.querySelectorAll('.donut-arc').forEach(el=>{
    el.addEventListener('mousemove',e=>{
      const i=parseInt(el.dataset.i),s=segs[i];
      if(!s)return;
      const pct=(s.pct*100).toFixed(1);
      tip.innerHTML=s.code
        ?`<b>${s.name}</b><br>월 인컴 <b>${s.inc.toFixed(1)}만원</b> · ${pct}%`
        :`<b>${s.name}</b><br>${s.inc.toFixed(1)}만원 더 필요해요`;
      tip.style.display='block';
      tip.style.left=(e.clientX+14)+'px';
      tip.style.top=(e.clientY-10)+'px';
    });
    el.addEventListener('mouseleave',()=>{tip.style.display='none';});
  });
}

const PRESETS=[50,100,200,300,500];
function targetPreset(v){
  document.getElementById('sim-target').value=v;
  document.querySelectorAll('#target-presets a').forEach((el,i)=>el.classList.toggle('on',PRESETS[i]===v));
  simOut();
}
function targetInput(){
  const v=parseInt(document.getElementById('sim-target').value)||0;
  document.querySelectorAll('#target-presets a').forEach((el,i)=>el.classList.toggle('on',PRESETS[i]===v));
  simOut();
}
function simOut(){
  let totalDiv=0;const bad=[],slices=[];
  simHoldings.forEach(h=>{
    const d=UNIV[h.code],inc=simIncome(h);
    totalDiv+=inc;
    slices.push({name:d.name,code:h.code,inc});
    const[hc,,e]=incomeHealth(d);
    if(hc==='bad')bad.push({code:h.code,name:d.name,y:d.y,e,val:h.qty*d.price/10000});
  });
  const monthly=totalDiv/12,target=parseInt(document.getElementById('sim-target').value)||0,gap=target-monthly;

  // 도넛 세그먼트 구성
  const total=Math.max(monthly,target,0.01);
  const segs=slices.map((s,i)=>({name:s.name,code:s.code,inc:s.inc/12,pct:s.inc/12/total,color:DONUT_COLORS[i%DONUT_COLORS.length]}));
  if(gap>0)segs.push({name:'목표까지 부족',code:'',inc:gap,pct:gap/total,color:GAP_COLOR});

  const donut=simHoldings.length?buildDonut(segs,monthly):'';
  const legend=segs.filter(s=>s.code).map(s=>`<span class="dl-item"><i style="background:${s.color}"></i>${s.name}<b class="num">${s.inc.toFixed(0)}만</b></span>`).join('');

  let html=`<div class="sim-out-row">
    ${donut?`<div class="donut-wrap">${donut}<div id="donut-tip" class="donut-tip"></div></div>`:''}
    <div style="flex:1;min-width:0;">
      <div class="sim-kpi">
        <div class="k"><div class="l">현재 월 인컴</div><div class="v num">${monthly.toFixed(0)}만원</div></div>
        <div class="k"><div class="l">목표</div><div class="v num">${target}만원</div></div>
        <div class="k"><div class="l">${gap>0?'부족':'초과'}</div><div class="v num" style="color:${gap>0?'#f33942':'#00ae1a'}">${gap>0?'−':'+'}${Math.abs(gap).toFixed(0)}만원</div></div>
      </div>
      <div class="donut-legend">${legend}</div>
    </div>
  </div>`;

  // 리포트 카드 조립
  const cards=[];
  if(bad.length){
    cards.push(`<div class="rc open">
      <div class="rc-head" onclick="toggleRc(this)"><span class="rci">⚠️</span><span class="rct">원금성 분배 주의</span><span class="rcb red">${bad.length}종목</span><span class="rc-chev">▾</span></div>
      <div class="rc-body">${bad.map(b=>`<b>${b.name}</b>는 분배율 <b class="rc-num">${b.y}%</b>인데 가격은 <b class="rc-num" style="color:#f33942">${b.e.toFixed(0)}%</b> 하락했어요. 분배금에 원금이 섞여 있어 표면 수치만큼 번 게 아니에요.`).join('<br><br>')}</div>
    </div>`);
    const worst=[...bad].sort((a,b)=>a.e-b.e)[0];
    const alt=[...INCOME_UNIVERSE].filter(d=>incomeHealth(d)[0]==='ok'&&d.code!==worst.code).sort((a,b)=>b.y-a.y)[0];
    if(alt){
      const ae=incomeHealth(alt)[2],curM=worst.val*worst.y/100/12,altM=worst.val*alt.y/100/12;
      cards.push(`<div class="rc open">
        <div class="rc-head" onclick="toggleRc(this)"><span class="rci">🔄</span><span class="rct">갈아타기 제안</span><span class="rcb green">월 ${altM.toFixed(1)}만원</span><span class="rc-chev">▾</span></div>
        <div class="rc-body">
          <div class="rc-flow">
            <span class="rc-from">${worst.name} <span class="rc-num">(분배 ${worst.y}% · 가격 ${worst.e.toFixed(0)}%)</span></span>
            <span class="rc-dest"><span class="rc-arr">→</span><span class="rc-to">${alt.name} <span class="rc-num" style="color:#4F46E5">(분배 ${alt.y}% · 가격 +${ae.toFixed(0)}%)</span></span></span>
          </div>
          같은 평가금액 <b class="rc-num">${worst.val.toFixed(0)}만원</b> 기준으로 월 인컴이 <b class="rc-num">${curM.toFixed(1)}만원 → ${altM.toFixed(1)}만원</b>으로 ${altM<curM?'줄지만, 가격이 녹지 않아 실질 수익은 더 안정적이에요':'늘고, 가격도 유지돼 실질 수익이 개선돼요'}.
          <div class="rc-actions">
            <a class="rc-act pri" onclick="addFromRanking('${alt.code}')">시뮬레이터에 추가</a>
            <a class="rc-act sec" onclick="simDel(simHoldings.findIndex(h=>h.code==='${worst.code}'))">기존 종목 제거</a>
          </div>
        </div>
      </div>`);
    }
  }
  const taxWarn=totalDiv>=2000;
  cards.push(`<div class="rc">
    <div class="rc-head" onclick="toggleRc(this)"><span class="rci">${taxWarn?'⚠️':'✅'}</span><span class="rct">금융소득종합과세</span><span class="rcb ${taxWarn?'red':'green'}">${taxWarn?'과세 대상':'안전'}</span><span class="rc-chev">▾</span></div>
    <div class="rc-body">${taxWarn
      ?`연 분배금 <b class="rc-num">${totalDiv.toFixed(0)}만원</b>이 기준(2,000만원)을 초과해요. 초과분 <b class="rc-num" style="color:#f33942">${(totalDiv-2000).toFixed(0)}만원</b>이 다른 소득에 합산돼 세율이 높아질 수 있어요.`
      :`연 분배금 <b class="rc-num">${totalDiv.toFixed(0)}만원</b>으로 기준(2,000만원) 이하예요. 현재 보유 조합에서는 금융소득종합과세 대상이 아니에요.`}
    </div>
  </div>`);
  if(gap>0){
    const f=UNIV['458760'],need=gap*12/(f.y/100),needTxt=need>=10000?(need/10000).toFixed(1)+'억원':need.toFixed(0)+'만원';
    cards.push(`<div class="rc">
      <div class="rc-head" onclick="toggleRc(this)"><span class="rci">📈</span><span class="rct">목표 달성 전략</span><span class="rcb amber">월 ${gap.toFixed(0)}만원 부족</span><span class="rc-chev">▾</span></div>
      <div class="rc-body">건전 등급 <b>${f.name}</b><span class="rc-num">(분배 ${f.y}% · 가격 +${(f.r-f.y).toFixed(0)}%)</span>을 약 <b class="rc-num">${needTxt}</b> 더 담으면 목표 월 <b class="rc-num">${target}만원</b>에 도달할 수 있어요.
        <div class="rc-actions"><a class="rc-act pri" onclick="addFromRanking('${f.code}')">시뮬레이터에 추가</a></div>
      </div>
    </div>`);
  }

  html+=`<div class="sim-report-title">📋 진단 리포트</div><div class="sim-report">${cards.join('')}</div>`;

  document.getElementById('sim-out').innerHTML=html;
  if(simHoldings.length)setupDonutTip(segs);
}
function openIncomeModal(){document.getElementById('income-modal-bg').classList.add('open');document.body.style.overflow='hidden';}
function closeIncomeModal(){document.getElementById('income-modal-bg').classList.remove('open');document.body.style.overflow='';}
function copyPrompt(){
  const txt=document.getElementById('income-prompt').textContent;
  navigator.clipboard.writeText(txt).then(()=>{
    const ok=document.getElementById('copy-ok');ok.style.display='inline';
    setTimeout(()=>ok.style.display='none',2000);
  });
}
function toggleRc(head){head.closest('.rc').classList.toggle('open');}
try{ simRowsRender();simOut(); }catch(e){ /* 인컴 설계기 초기화 실패가 이후 코드(브리핑 커넥터 등)를 막지 않도록 격리 */ console.warn('[income] init skipped', e); }

/* 패시브 뱃지 툴팁 */
const passBtn=document.getElementById('badge-pass-btn');
if(passBtn){
  passBtn.addEventListener('mouseenter',e=>{
    tip.innerHTML=`<div class="tt" style="color:#0284C7;">🧲 패시브 민감주 뱃지</div><div class="bd" style="line-height:1.9;">
      <span style="display:inline-flex;align-items:center;gap:6px;margin-bottom:4px"><span class="pbdg high" style="font-size:10px;">高</span> <b>거래일수 ≥ 8일 AND 집중도 ≥ 10%</b></span><br>
      <span style="display:inline-flex;align-items:center;gap:6px;margin-bottom:4px"><span class="pbdg mid" style="font-size:10px;">中</span> <b>거래일수 ≥ 4일 AND 집중도 ≥ 5%</b></span><br>
      거래일수 = 패시브 자금 ÷ 20일 평균 거래대금<br>집중도 = 패시브 자금 ÷ 시가총액<br><b>인과 아님 — 구조적 노출도 지표예요.</b>
    </div>`;
    tip.style.display='block';moveTip(e);
  });
  passBtn.addEventListener('mousemove',moveTip);
  passBtn.addEventListener('mouseleave',hideTip);
}

/* ── 블록 6 (원본 index.html) ── */
/* ── 더블샷 브리핑 커넥터 ── */
/* 브리핑 타임테이블(KST, 평일): 07:30 코스피 예측 → 09:00~16:30 장중 이슈(실시간)
   → 16:30 코스피 마감 → 21:20~23:50 미국 예측. 활성 슬롯에 해당할 때만 노출하고,
   장중에는 실시간 이슈를 우선 노출한다.
   미국 예측 종료(23:50) 이후 심야·주말 등 활성 슬롯 밖에서는 폴백 없이 영역을 숨긴다. */
(function(){
  var el = document.getElementById('brief-strip');
  if (!el) return;
  var TYPE = {
    kospi: { cls:'bc-kospi', icon:'📈', label:'코스피 예측 브리핑', pub:450 },   // 07:30
    close: { cls:'bc-close', icon:'🏁', label:'코스피 마감 브리핑', pub:990 },   // 16:30
    us:    { cls:'bc-us',    icon:'🌙', label:'미국 시장 예측 브리핑', pub:1280 } // 21:20
  };
  function kstNow(){ return new Date(Date.now() + 9 * 3600000); }
  function kstDate(){ return kstNow().toISOString().slice(0, 10); }
  function nowMin(){ var k = kstNow(); return k.getUTCHours() * 60 + k.getUTCMinutes(); }
  // 거래일(평일·비공휴일)만 브리핑 슬롯 활성. 공휴일이면 슬롯 없음 → 스트립 숨김(주말과 동일 처리).
  function isWeekday(){ if(window.krIsKospiHoliday && window.krIsKospiHoliday()) return false; var d = kstNow().getUTCDay(); return d >= 1 && d <= 5; }

  function paint(o){
    el.className = 'brief-card ' + o.cls;
    el.href = o.url; el.dataset.href = o.url;
    document.getElementById('bc-ico').textContent = o.icon;
    document.getElementById('bc-type').innerHTML = (o.live ? '<span class="live-dot"></span>' : '') + o.type;
    document.getElementById('bc-time').textContent = o.time || '';
    document.getElementById('bc-head').textContent = o.head;
    var pill = document.getElementById('bc-pill');
    if (o.pill && o.pillCls) { pill.textContent = o.pill; pill.className = 'bc-pill ' + o.pillCls; pill.style.display = ''; }
    else { pill.style.display = 'none'; }
  }

  function safeJSON(url){
    return Promise.race([
      fetch(url, {cache:'no-store'}).then(function(r){ return r.ok ? r.json() : null; }).catch(function(){ return null; }),
      new Promise(function(res){ setTimeout(function(){ res(null); }, 4000); })
    ]);
  }

  function fromSlot(date, type, s){
    var m = TYPE[type];
    var arrow = (s.pill_text || '').trim().charAt(0);
    var pillCls = (arrow === '▲') ? 'up' : (arrow === '▼' ? 'dn' : '');
    var pill = pillCls ? s.pill_text.trim() : '';
    return {
      cls: m.cls, icon: m.icon, type: m.label,
      time: s.time ? (s.time + ' 발행') : '',
      head: s.headline || (s.title && s.title !== '—' ? s.title : '') || '오늘 브리핑 보기',
      url: s.url || ('/briefings/' + date + '/' + type + '/'),
      pill: pill, pillCls: pillCls
    };
  }

  // 가장 최근 '발행된' 브리핑 선택 (오늘은 발행시각 지난 것만, 없으면 이전 날짜의 최신)
  function pickLatest(list){
    var slots = list && list.slots; if (!slots) return null;
    var dates = Object.keys(slots).sort().reverse();
    var today = kstDate(), nm = nowMin();
    for (var i = 0; i < dates.length; i++){
      var date = dates[i], day = slots[date], best = null;
      ['kospi','close','us'].forEach(function(t){
        var s = day[t];
        if (!s || s.state !== 'ready') return;
        if (date === today && nm < TYPE[t].pub) return; // 오늘 아직 발행 전
        if (!best || TYPE[t].pub > TYPE[best].pub) best = t;
      });
      if (best) return { date:date, type:best, s:day[best] };
    }
    return null;
  }

  // 현재 KST 시각의 브리핑 타임슬롯. 슬롯 밖(심야·주말)은 null.
  function slotNow(){
    var nm = nowMin();
    var d = kstNow().getUTCDay();
    var isKstWeekday = (d >= 1 && d <= 5);
    // 코스피 브리핑(예측·장중이슈·마감)은 한국 거래일(평일·비공휴일)에만 노출
    if (isWeekday()){
      if (nm >= 450 && nm < 540)  return 'kospi'; // 07:30~09:00 코스피 예측
      if (nm >= 540 && nm < 990)  return 'issue'; // 09:00~16:30 장중 이슈
      if (nm >= 990 && nm < 1280) return 'close'; // 16:30~21:20 마감
    }
    // 미국 예측은 한국 공휴일(예: 제헌절)이어도 미국장이 열리면 발행되므로, 한국 휴일 여부와
    // 무관하게 KST 평일이면 슬롯을 연다. 실제 노출은 render()의 s.state==='ready'가 최종 판정
    // (미국 휴장일엔 당일 us가 ready가 아니라 자동으로 숨겨진다).
    if (isKstWeekday && nm >= 1280 && nm < 1430) return 'us'; // 21:20~23:50 미국 예측
    return null;
  }

  /* 슬롯별 이슈 피드 제목·갱신 주기 표기.
     실제로 수집이 도는 주기만 적는다 — POST_MARKET(16:35~21:00)은 fetch_news_live.py가 즉시 종료해
     신규 수집이 아예 없으므로 주기를 광고하지 않는다(운영규칙 0, §10 "화면 표기와 스케줄의 1:1 대응").
     history에는 하루치 전 슬롯이 섞여 있으므로 반드시 수집 시각(inSlot)으로 걸러낸다 —
     안 그러면 장중에 어젯밤 미국장 헤드라인이 뜬다. */
  function inMarket(mm){ return mm >= 540 && mm < 930; }    // MARKET     09:00~15:30
  function inUsMarket(mm){ return mm >= 1290 || mm < 60; }  // US_MARKET  21:30~01:00
  var FEED = {
    kospi: null,                                        // 07:30~09:00 — 당일 이슈가 아직 없다
    issue: { title:'장중 이슈',      cadence:'30분 갱신',    inSlot:inMarket },
    close: { title:'오늘 장중 이슈', cadence:'장 마감 기준', inSlot:inMarket },
    us:    { title:'직전 이슈',      cadence:'1시간 갱신',   inSlot:inUsMarket }
  };

  var feedEl = document.getElementById('bc-feed');
  var subEl  = document.getElementById('bc-sub');

  function hideFeed(){ if(feedEl){ feedEl.classList.add('is-hidden'); feedEl.classList.remove('bc-feed--lead','bc-feed--solo'); feedEl.textContent=''; } }
  function hideSub(){ if(subEl) subEl.classList.add('is-hidden'); }

  // 타임테이블 기준 즉시 표시 — fetch 실패(PC 네트워크 차단)에도 슬롯이 맞게 보이도록 동기 렌더
  function paintDefault(slot, today){
    if (!slot){ el.classList.add('is-hidden'); return; } // 활성 슬롯 밖(미국 예측 23:50 종료 이후 심야·주말) → 폴백 없이 영역 제거
    if (slot === 'issue'){ el.classList.add('is-hidden'); return; } // 장중엔 카드 대신 이슈 피드가 主
    var m = TYPE[slot];
    paint({ cls:m.cls, icon:m.icon, type:m.label, time:'', head:'오늘 브리핑 보기',
            url:'/briefings/' + today + '/' + slot + '/' });
  }

  /* 브리핑 카드(主) — 장중 외 슬롯에서만 그린다. 반환값은 카드가 가리키는 URL. */
  async function renderCard(slot, today){
    paintDefault(slot, today);
    if (!slot || slot === 'issue') return null;

    var list = await safeJSON('/data/briefings-list.json') || await safeJSON('/api/data?f=briefings-list');
    if (!list) return el.dataset.href;   // fetch 실패(PC 차단) → 타임테이블 기본 유지

    var s = list.slots && list.slots[today] && list.slots[today][slot];
    if (s && s.state === 'ready'){ paint(fromSlot(today, slot, s)); return el.dataset.href; }
    var pick = pickLatest(list);
    if (pick) paint(fromSlot(pick.date, pick.type, pick.s));
    return el.dataset.href;
  }

  /* 장중(09:00~16:30) 부(副) 줄 — 오늘 코스피 예측 브리핑. ready가 아니면 줄을 숨긴다(폴백 없음). */
  async function renderSub(today){
    if (!subEl) return false;
    var list = await safeJSON('/data/briefings-list.json') || await safeJSON('/api/data?f=briefings-list');
    var s = list && list.slots && list.slots[today] && list.slots[today].kospi;
    if (!s || s.state !== 'ready'){ hideSub(); return false; }
    // pill_text는 화살표만("▼"), 방향 문구는 title("하락 우위")에 있다 — 둘을 합쳐야 뜻이 통한다.
    var dir = ((s.pill_text || '') + ' ' + (s.title && s.title !== '—' ? s.title : '')).trim();
    var head = s.headline || '';
    subEl.href = s.url || ('/briefings/' + today + '/kospi/');
    document.getElementById('bc-sub-tx').textContent =
      (dir && head) ? (dir + ' — ' + head) : (dir || head || '오늘 예측 브리핑 보기');
    subEl.classList.remove('is-hidden');
    return true;
  }

  /* 이슈 헤드라인 피드 — 브리핑 페이지와 같은 데이터(kospi-news-{date}.json)를 종목 메인에도 노출한다.
     각 행은 fetch_news_live.py가 리졸브해 저장한 원문 기사 url로 새 탭 이동한다.
     url이 없는(과거 데이터·리졸브 실패) 행만 그 시간대 브리핑 URL로 폴백(같은 탭, 아직 발행 안 된 날짜로
     나가는 것 방지). 오늘 날짜 데이터가 아니면 표시하지 않는다. lead=true면 카드 자리를 대신하는 主 모드. */
  async function renderFeed(slot, today, href, lead){
    if (!feedEl) return false;
    var cfg = FEED[slot];
    if (!cfg) { hideFeed(); return false; }

    // 라이브 데이터는 /api/data(raw main)를 우선 조회 — 데이터 전용 커밋은 재배포되지 않아 정적 /data는 stale일 수 있음
    var nj = await safeJSON('/api/data?f=news-live')
          || await safeJSON('/data/kospi-news-' + today + '.json')
          || await safeJSON('/data/kospi-news-live.json');
    if (!nj || nj.date !== today){ hideFeed(); return false; }   // 어제 데이터를 오늘인 척 보여주지 않는다

    var rows = [], seen = {};
    (nj.history || []).forEach(function(h){
      if (rows.length >= 3) return;
      var p = (h.time || '').split(':');
      if (p.length < 2) return;
      if (!cfg.inSlot(parseInt(p[0],10) * 60 + parseInt(p[1],10))) return;   // 다른 슬롯 이슈 배제
      var picked = (h.market && h.market.title) ? h.market : ((h.stock && h.stock.title) ? h.stock : null);
      if (!picked || seen[picked.title]) return;
      seen[picked.title] = 1;
      rows.push({ time: h.time || '', title: picked.title, url: picked.url || '' });
    });
    if (!rows.length){ hideFeed(); return false; }

    feedEl.textContent = '';
    var head = document.createElement('div');
    head.className = 'bc-feed-h';
    if (lead){ var dot = document.createElement('span'); dot.className = 'live-dot'; head.appendChild(dot); }
    head.appendChild(document.createTextNode(cfg.title));
    var n = document.createElement('span');
    n.className = 'n'; n.textContent = cfg.cadence;
    head.appendChild(n);
    feedEl.appendChild(head);
    rows.forEach(function(r){
      var a = document.createElement('a');
      a.className = 'bc-fi';
      if (r.url){ a.href = r.url; a.target = '_blank'; a.rel = 'noopener noreferrer'; }
      else { a.href = href || '/briefings/'; }
      var tm = document.createElement('span'); tm.className = 't'; tm.textContent = r.time;
      var hd = document.createElement('span'); hd.className = 'h'; hd.textContent = r.title;
      a.appendChild(tm); a.appendChild(hd);
      feedEl.appendChild(a);
    });
    feedEl.classList.toggle('bc-feed--lead', !!lead);
    if (!lead) feedEl.classList.remove('bc-feed--solo');
    feedEl.classList.remove('is-hidden');
    return true;
  }

  /* 시간대별 구성 (KST, 평일) — docs/prototypes/2026-07-19-brief-strip-supply.html 참조
       07:30~09:00  코스피 예측 카드 (이슈 없음)
       09:00~16:30  장중 이슈 3건이 主 · 예측 브리핑이 副 한 줄     ← 이 슬롯만 위아래가 뒤집힌다
       16:30~21:20  마감 카드 主 · 장 마감까지의 이슈 3건이 副
       21:20~23:50  미국 예측 카드 主 · 미국장 이슈 3건이 副
       그 외(심야·주말·휴일)  전체 숨김 (과거 날짜 폴백 없음) */
  async function render(){
    var today = kstDate(), slot = slotNow();

    if (!slot){ el.classList.add('is-hidden'); hideFeed(); hideSub(); return; }

    if (slot === 'issue'){
      el.classList.add('is-hidden');   // 장중엔 카드 대신 이슈 피드가 主
      var kospiUrl = '/briefings/' + today + '/kospi/';
      var hasFeed = await renderFeed('issue', today, kospiUrl, true);
      var hasSub  = await renderSub(today);
      if (!hasFeed){
        // 이슈 미수집(09:00~첫 수집 전) → 예측 카드로 폴백해 영역이 비지 않게 한다
        hideSub(); hideFeed();
        await renderCard('kospi', today);
        return;
      }
      feedEl.classList.toggle('bc-feed--solo', !hasSub);
      return;
    }

    hideSub();
    var href = await renderCard(slot, today);
    await renderFeed(slot, today, href, false);
  }
  render();
  setInterval(render, 5 * 60 * 1000); // 5분마다 재평가 — 슬롯 전환·이슈 갱신 반영
})();

/* ── 블록 7 (원본 index.html) ── */
/* 미국 연동 대표주 — 실측 스냅샷 baseline + 라이브 폴링(stocks-live).
   시세·실시간 수치는 stocks-snapshot.json(실측 종가)으로 채우고,
   /api/stocks-live(서버리스, 커밋 안 함) 폴링으로 장중 가격을 덮어쓴다. */
(function(){
  var KR_UP='#E03131', KR_DN='#2775ED', KR_FLAT='#64748B';
  function fmt(n){ return Math.round(n).toLocaleString('en-US'); }
  /* 가격이 바뀔 때 이전값→새값으로 카운트업(odometer) + 방향색 플래시 */
  (function injectFlash(){
    var st=document.createElement('style');
    st.textContent='@keyframes usFlashUp{0%{background:rgba(224,49,49,.16)}100%{background:transparent}}'
      +'@keyframes usFlashDn{0%{background:rgba(39,117,237,.16)}100%{background:transparent}}'
      +'.us-flash-up{animation:usFlashUp .6s ease-out;border-radius:6px;}'
      +'.us-flash-dn{animation:usFlashDn .6s ease-out;border-radius:6px;}';
    document.head.appendChild(st);
  })();
  function countUp(el, to, dir){
    var from = parseFloat((el.textContent||'').replace(/[^0-9.\-]/g,''));
    if(!isFinite(from) || from===to){ el.textContent = fmt(to); return; }
    if(dir){ el.classList.remove('us-flash-up','us-flash-dn'); void el.offsetWidth;
      el.classList.add(dir>0?'us-flash-up':'us-flash-dn'); }
    var start = performance.now(), dur = 550;
    function step(now){
      var t = Math.min(1,(now-start)/dur), e = 1-Math.pow(1-t,3); // easeOutCubic
      el.textContent = fmt(from + (to-from)*e);
      if(t<1) requestAnimationFrame(step); else el.textContent = fmt(to);
    }
    requestAnimationFrame(step);
  }
  function paintTile(tile, close, pct, animate){
    if(close==null) return;
    var els = tile.children; // [KOSPI 라벨, 종목명, 가격, 등락]
    if(els.length < 4) return;
    var prevShown = parseFloat((els[2].textContent||'').replace(/[^0-9.\-]/g,''));
    var dir = isFinite(prevShown) ? (close>prevShown?1:close<prevShown?-1:0) : 0;
    if(animate) countUp(els[2], close, dir);
    else els[2].textContent = fmt(close);
    if(pct==null) return; // 가격만 갱신, 등락 표시는 유지
    var prev = close/(1+pct/100);
    var delta = Math.abs(close-prev);
    var up = pct>0, dn = pct<0;
    els[3].textContent = (up?'▲':dn?'▼':'–')+' '+fmt(delta)+' ('+Math.abs(pct).toFixed(2)+'%)';
    els[3].style.color = up?KR_UP:dn?KR_DN:KR_FLAT;
  }
  function applySnapshot(snap){
    document.querySelectorAll('#us-linked-widget .us-tile[data-code]').forEach(function(tile){
      var s = snap.stocks && snap.stocks[tile.getAttribute('data-code')];
      if(s) paintTile(tile, s.close, s.change_pct, false); // 최초 baseline은 즉시
    });
  }
  fetch('/data/stocks-snapshot.json',{cache:'no-store'})
    .then(function(r){return r.ok?r.json():null;})
    .then(function(snap){ if(snap) applySnapshot(snap); })
    .catch(function(){});

  /* 라이브 폴링(KR 10초) — /api/stocks-live(네이버 종목 시세, 서버리스, 커밋 안 함).
     타일 data-code를 codes로, 벨웨더를 us(네이버 해외 심볼)로 넘겨 실측을 받아 패치한다. */
  var liveCodes = [].map.call(
    document.querySelectorAll('#us-linked-widget .us-tile[data-code]'),
    function(t){ return t.getAttribute('data-code'); }
  );
  /* KR 정규장 개장 여부(09:00~15:30 평일). 마감 후엔 HL 24h 무기한선물로 전환. */
  function krOpen(){
    if(window.krIsKospiHoliday&&window.krIsKospiHoliday()) return false; // 주말·공휴일
    var m=((new Date().getUTCHours()*60+new Date().getUTCMinutes())+9*60)%(24*60);
    return m>=540 && m<=930;
  }
  var uswWidget=document.getElementById('us-linked-widget');
  var uswHdr=uswWidget?uswWidget.firstElementChild:null;
  function setNight(on){
    if(!uswWidget) return;
    var pills=uswWidget.querySelectorAll('.usw-pill'), sub=uswWidget.querySelector('.usw-sub');
    if(!pills.length||!sub) return;
    if(on===uswWidget._night) return; uswWidget._night=on;
    var title=uswWidget.querySelector('#usw-title');
    if(title) title.textContent=on?'📈 지금 이시각 추정가':'📈 코스피 주도주';
    pills.forEach(function(pill){
      if(on){
        pill.textContent='🌙 HL 24h'; pill.style.color='#6D28D9'; pill.style.background='#EDE9FE';
      }else{
        pill.textContent='●실시간'; pill.style.color='#16A34A'; pill.style.background='#ECFDF3';
      }
    });
    sub.textContent=on?'하이퍼리퀴드 24h 무기한선물 환산 · 실제 체결가 아님':'코스피 시총 상위 3 · 마감 후 미국 LIVE';
    // 곡선·장중지표는 정규장 실측이라 그대로 두고, 뉴스 갱신 주기 표기만 시간대에 맞춘다.
    // 표기는 실제 수집 스케줄과 1:1로 맞춰야 한다(없는 주기를 적지 않는다):
    //   평일 장중 09:00~15:30 → 30분  | 평일 그 외 → 1시간   : kospi-news-live.yml(cron-job.org)
    //   주말 09~21시          → 3시간                        : stock-news-weekend.yml(GHA native cron)
    //   주말 21시~익일 09시   → 수집 없음 → 주기 표기 생략
    // 공휴일엔 두 스케줄 모두 발화하지 않으므로 주말과 달리 주기를 적지 않는다.
    var upd=document.getElementById('lw-upd');
    if(upd){
      var kstH=(new Date().getUTCHours()+9)%24;
      var wd=new Date(Date.now()+9*3600*1000).getUTCDay();
      var isWeekend=(wd===0||wd===6);
      var isHoliday=window.krIsKospiHoliday&&window.krIsKospiHoliday();
      var label;
      if(isWeekend) label=(kstH>=9&&kstH<21)?'최신순 · 3시간 주기':'최신순';
      else if(isHoliday) label='최신순';           // 평일 공휴일 — 어느 스케줄도 안 돎
      else label=on?'최신순 · 1시간 주기':'최신순 · 30분 주기';
      upd.textContent=label;
    }
  }
  /* 장중: 네이버 실측 KRW(stocks-live)로 타일 갱신 */
  function pollDay(){
    fetch('/api/stocks-live?codes='+liveCodes.join(','),{cache:'no-store'})
      .then(function(r){return r.ok?r.json():null;})
      .then(function(d){
        if(!d) return;
        if(Array.isArray(d.prices)) d.prices.forEach(function(p){
          var tile = document.querySelector('#us-linked-widget .us-tile[data-code="'+p.code+'"]');
          if(tile && p.price!=null){ paintTile(tile, p.price, p.changePct, true); if(window.whyMovedPush) window.whyMovedPush(p.code, p.price); }
        });
      })
      .catch(function(){});
  }
  /* 마감 후: HL 24h perp의 USD가격×환율 KRW 환산으로 타일 갱신 */
  function pollNight(){
    fetch('/api/hl-night',{cache:'no-store'})
      .then(function(r){return r.ok?r.json():null;})
      .then(function(d){
        if(!d||!Array.isArray(d.items)) return;
        d.items.forEach(function(it){
          var tile = document.querySelector('#us-linked-widget .us-tile[data-code="'+it.code+'"]');
          if(tile && it.krw!=null){ paintTile(tile, it.krw, it.changePct, true); if(window.whyMovedPush) window.whyMovedPush(it.code, it.krw); }
        });
      })
      .catch(function(){});
  }
  function poll(){
    if(!liveCodes.length) return;
    var night=!krOpen();
    setNight(night);
    if(night) pollNight(); else pollDay();
  }
  poll();
  setInterval(poll, 10000);
})();

/* ── 블록 8 (원본 index.html) ── */
/* 거래량·상승·하락 톱 — /api/vol-top 라이브(41종목). 급증배수는 스냅샷 vol_avg20 병합.
   외국인 보유율·ETF 거래량 — stocks-snapshot.json 실측 배선 */
(function(){
  var SNAP=null;
  var SIG_SECTORS=null, SIG_KOSPI=null; // /api/signals가 내려주는 전 섹터 라이브 평균·코스피% (장중 2분 갱신)
  var SECTOR_LABELS={semicon:'반도체',battery:'2차전지',auto:'자동차',defense:'방산',ship:'조선',bio:'바이오',finance:'금융',power:'전력기기'};
  function manju(v){ return Math.round(v/10000).toLocaleString('en-US')+'만주'; }
  function sparkSvg(vals,color){
    if(!vals||vals.length<2) return '';
    var n=vals.length,min=Math.min.apply(null,vals),max=Math.max.apply(null,vals),rng=(max-min)||1;
    var pts=vals.map(function(v,i){var x=(i/(n-1))*78;var y=19-((v-min)/rng)*16;return x.toFixed(1)+','+y.toFixed(1);}).join(' ');
    var last=pts.split(' ').pop().split(',');
    return '<svg viewBox="0 0 78 22" style="width:78px;height:22px;display:block;overflow:visible;"><polyline points="'+pts+'" fill="none" stroke="'+color+'" stroke-width="1.5"/><circle cx="'+last[0]+'" cy="'+last[1]+'" r="2.2" fill="#fff" stroke="'+color+'" stroke-width="1.5"/></svg>';
  }
  function secLbl(s){ return SECTOR_LABELS[s]||s||''; }
  function surgeBadge(code,vol){
    if(!SNAP||!SNAP.stocks||!SNAP.stocks[code]) return '';
    var avg=SNAP.stocks[code].vol_avg20; if(!avg) return '';
    var s=vol/avg; return s>=1.5?'<span class="vol-surge-badge">×'+s.toFixed(1)+' 급증</span>':'';
  }
  function nearHighBadge(code,price){
    if(!SNAP||!SNAP.stocks||!SNAP.stocks[code]||price==null) return '';
    var hi=SNAP.stocks[code].wk52_high; if(!hi) return '';
    return price>=hi*0.98?'<span class="hi-badge">52주 신고가</span>':'';
  }
  function volRow(x,i){
    return '<a class="row" onclick="goStock(\''+x.code+'\')"><span class="'+(i<3?'rk t num':'rk num')+'">'+(i+1)+'</span><div class="nm"><b>'+x.name+'</b><small class="num">'+x.code+' · '+secLbl(x.sector)+'</small></div><div class="barwrap"><div class="bar vol" style="width:'+(x.barPct||0)+'%"></div></div><span class="barval num">'+manju(x.vol)+'</span>'+surgeBadge(x.code,x.vol)+nearHighBadge(x.code,x.price)+'</a>';
  }
  function chgRow(x,i,cls,barPct){
    return '<a class="row" onclick="goStock(\''+x.code+'\')"><span class="'+(i<3?'rk t num':'rk num')+'">'+(i+1)+'</span><div class="nm"><b>'+x.name+'</b><small class="num">'+x.code+' · '+secLbl(x.sector)+'</small></div><div class="barwrap"><div class="bar '+cls+'" style="width:'+barPct+'%"></div></div><span class="barval '+cls+' num">'+(x.changePct>=0?'+':'')+x.changePct.toFixed(1)+'%</span>'+nearHighBadge(x.code,x.price)+surgeBadge(x.code,x.vol)+'</a>';
  }
  function etfVolRow(x,i){
    var pc=x.changePct>=0?'var(--up)':'var(--dn)',sg=x.changePct>=0?'+':'';
    return '<div class="row etf-top5">'
      +'<span class="'+(i<3?'rk t num':'rk num')+'">'+(i+1)+'</span>'
      +'<span class="etf-top5-nm">'+x.name+'</span>'
      +'<span class="etf-top5-vol num">'+manju(x.vol)+'</span>'
      +'<span class="etf-top5-pct num" style="color:'+pc+'">'+sg+x.changePct.toFixed(1)+'%</span>'
      +'</div>';
  }
  function etfChgRow(x,i,cls,barPct){
    return '<a class="row" onclick="go(\'etf-detail\')"><span class="'+(i<3?'rk t num':'rk num')+'">'+(i+1)+'</span><div class="nm"><b>'+x.name+'</b><small class="num">'+x.code+' · ETF</small></div><div class="barwrap"><div class="bar '+cls+'" style="width:'+barPct+'%"></div></div><span class="barval '+cls+' num">'+(x.changePct>=0?'+':'')+x.changePct.toFixed(1)+'%</span></a>';
  }
  function renderEtf(etf){
    if(!etf||!etf.length) return;
    var byVol=etf.filter(function(x){return x.vol>0;}).sort(function(a,b){return b.vol-a.vol;}).slice(0,5);
    var mv=byVol[0]?byVol[0].vol:1;
    var w1=document.getElementById('etf-top-rows'); if(w1) w1.innerHTML=byVol.map(function(x,i){return etfVolRow(Object.assign({},x,{barPct:Math.round(x.vol/mv*100)}),i);}).join('');
    var up=etf.filter(function(x){return x.changePct>0;}).sort(function(a,b){return b.changePct-a.changePct;}).slice(0,5);
    var um=up[0]?Math.abs(up[0].changePct):1;
    var w2=document.getElementById('etf-rise-rows'); if(w2) w2.innerHTML=up.length?up.map(function(x,i){return etfChgRow(x,i,'up',Math.round(Math.abs(x.changePct)/um*100));}).join(''):emptyRow('상승 ETF가 없어요');
    var dn=etf.filter(function(x){return x.changePct<0;}).sort(function(a,b){return a.changePct-b.changePct;}).slice(0,5);
    var dm=dn[0]?Math.abs(dn[0].changePct):1;
    var w3=document.getElementById('etf-fall-rows'); if(w3) w3.innerHTML=dn.length?dn.map(function(x,i){return etfChgRow(x,i,'dn',Math.round(Math.abs(x.changePct)/dm*100));}).join(''):emptyRow('하락 ETF가 없어요');
  }
  function emptyRow(msg){ return '<div style="padding:14px 16px;font-size:12px;color:#94A3B8;">'+msg+'</div>'; }
  function renderTops(d){
    var volWrap=document.getElementById('vol-top-rows');
    if(volWrap&&d.top&&d.top.length) volWrap.innerHTML=d.top.map(volRow).join('');
    var all=(d.all||[]).slice();
    RANK_ALL=all; rankRender();
    var up=all.filter(function(x){return x.changePct>0;}).sort(function(a,b){return b.changePct-a.changePct;}).slice(0,5);
    var upMax=up[0]?Math.abs(up[0].changePct):1;
    var upWrap=document.getElementById('rise-top-rows');
    if(upWrap) upWrap.innerHTML=up.length?up.map(function(x,i){return chgRow(x,i,'up',Math.round(Math.abs(x.changePct)/upMax*100));}).join(''):emptyRow('상승 종목이 없어요');
    var dn=all.filter(function(x){return x.changePct<0;}).sort(function(a,b){return a.changePct-b.changePct;}).slice(0,5);
    var dnMax=dn[0]?Math.abs(dn[0].changePct):1;
    var dnWrap=document.getElementById('fall-top-rows');
    if(dnWrap) dnWrap.innerHTML=dn.length?dn.map(function(x,i){return chgRow(x,i,'dn',Math.round(Math.abs(x.changePct)/dnMax*100));}).join(''):emptyRow('하락 종목이 없어요');
    if(d.etf){
      renderEtf(d.etf);
      ETF_ALL=(d.etf||[]).map(function(e){var se=SNAP&&SNAP.etfs&&SNAP.etfs[e.code];return Object.assign({},e,{vol_avg20:se?se.vol_avg20:0});});
      etfRankRender();
      etfDnRender();
    }
    renderSectorBreadth(all);
    bindSurgeTips();
  }
  function renderSectorBreadth(all){
    var sec=all.filter(function(x){return x.sector==='반도체'||x.sector==='semicon';});
    if(!sec.length) return;
    var upN=0,dnN=0,flatN=0,sum=0;
    sec.forEach(function(x){sum+=x.changePct;if(x.changePct>0)upN++;else if(x.changePct<0)dnN++;else flatN++;});
    var total=sec.length,avg=sum/total;
    var el=document.getElementById('sec-avg');
    if(el){el.textContent=(avg>=0?'+':'')+avg.toFixed(1)+'%';el.className='v num '+(avg>=0?'up':'dn');}
    var lbl=document.getElementById('sec-breadth-label');
    if(lbl)lbl.innerHTML=total+'종목 중 <b class="up num">'+upN+' 상승</b>';
    var bbar=document.getElementById('sec-bbar');
    if(bbar){var bu=Math.round(upN/total*1000)/10,bd=Math.round(dnN/total*1000)/10,bn=Math.round(flatN/total*1000)/10;bbar.innerHTML='<i class="bu" style="width:'+bu+'%"></i><i class="bd" style="width:'+bd+'%"></i><i class="bn" style="width:'+bn+'%"></i>';}
    var bk=document.getElementById('sec-bk');
    if(bk)bk.innerHTML='<span><i class="iu"></i>상승 <span class="num">'+upN+'</span></span><span><i class="id"></i>하락 <span class="num">'+dnN+'</span></span><span><i class="in"></i>보합 <span class="num">'+flatN+'</span></span>';
    var senti=document.getElementById('sec-senti');
    var pct=Math.round(upN/total*100);
    var slbl=document.getElementById('sec-senti-label');
    var needle=document.getElementById('sec-senti-needle');
    if(senti&&slbl&&needle){senti.style.display='';slbl.innerHTML=(pct>=55?'상승 우위':pct<=45?'하락 우위':'중립')+' <b class="num">'+pct+'%</b>';needle.style.left=pct+'%';}
    var leaders=['005930','000660','042700'];
    var lw=document.getElementById('sec-leaders');
    if(lw){var lmap={};sec.forEach(function(x){lmap[x.code]=x;});
      lw.innerHTML=leaders.map(function(c,i){var x=lmap[c];if(!x)return '';var cls=x.changePct>=0?'up':'dn';var sign=x.changePct>=0?'+':'';return '<a class="srow" onclick="goStock(\''+c+'\')"><span class="n2">'+['①','②','③'][i]+' '+x.name+' <small class="num">'+c+'</small></span><span class="c '+cls+' num">'+sign+x.changePct.toFixed(2)+'%</span></a>';}).join('');}
  }
  function bindSurgeTips(){
    if(typeof showTip!=='function') return;
    document.querySelectorAll('.vol-surge-badge').forEach(function(el){
      if(el._b) return; el._b=1;
      el.addEventListener('mouseenter',showTip); el.addEventListener('mousemove',moveTip); el.addEventListener('mouseleave',hideTip);
    });
  }
  /* ── 오늘의 특이 신호 · 신호별 랭킹 · ETF 4카드 — /api/signals 실측 배선 ── */
  function phaseLabel(phase){ return phase==='intraday' ? '<span class="dot"></span>장중 실시간 · 2분 간격' : '장 마감 기준'; }
  function setBadge(id, phase){ var b=document.getElementById(id); if(!b) return; b.className=phase==='intraday'?'upd-badge is-live':'close-pill'; b.innerHTML=phaseLabel(phase); }
  function badgeHtml(b){ var flow=/^(외국인|기관)/.test(b); return '<span class="bdg'+(flow?' flow':'')+'">'+b+'</span>'; }
  function asOfPrefix(asOf){ return (asOf && !asOf.isToday && asOf.label) ? asOf.label : '오늘의'; }
  // 신호 1건 → D안 마크업(i===0이면 히어로, 나머지는 컴팩트 행). 홈·더보기 화면 공용.
  function sigItemHtml(s,i,heroFlag){
    var lc=s.dir==='up'?'var(--up)':'var(--dn)', sign=s.pct>=0?'+':'';
    var badges=(s.badges||[]).map(badgeHtml).join('');
    var goArrow='<svg class="sig-go" width="14" height="14" viewBox="0 0 20 20" fill="none"><path d="M8 5l5 5-5 5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    if(i===0){
      return '<a class="sig-hero" onclick="goStock(\''+s.code+'\')">'
        +'<span class="sig-flag">'+(heroFlag||'오늘 가장 눈에 띄는 신호')+'</span>'
        +'<div class="sig-htop"><span class="sig-hnm">'+s.name+' <small>'+s.code+' · '+s.sector+'</small></span>'
        +'<span class="sig-hpct" style="color:'+lc+';">'+sign+s.pct.toFixed(1)+'%</span></div>'
        +'<div class="sig-hbadges">'+badges+'</div>'
        +'<div class="sig-hwhy">'+(s.why||'')+'</div>'+goArrow+'</a>';
    }
    return '<a class="sig-row" onclick="goStock(\''+s.code+'\')">'
      +'<span class="sig-rmain"><span class="sig-rnm">'+s.name+' <small>'+s.code+' · '+s.sector+'</small></span>'
      +'<span class="sig-rbadges">'+badges+'</span></span>'
      +'<span class="sig-rpct" style="color:'+lc+';">'+sign+s.pct.toFixed(1)+'%</span>'+goArrow+'</a>';
  }
  function sigHomeRender(){
    var w=document.getElementById('sig-rows'); if(!w) return;
    // 강도순은 API가 내려준 상위 N(SIGNALS_HOME) 유지, 상승률순은 전체 신호(SIGNALS_ALL) 기준으로 정렬 후 상위 N — 더보기와 정합성 유지
    var arr = (sigHomeSort==='up')
      ? SIGNALS_ALL.slice().sort(function(a,b){return b.pct-a.pct;}).slice(0, SIGNALS_HOME.length||10)
      : SIGNALS_HOME.slice();
    w.innerHTML=arr.length?arr.map(function(s,i){return sigItemHtml(s,i);}).join(''):'';
    w.classList.remove('sig-updated'); void w.offsetWidth; w.classList.add('sig-updated');
    setTimeout(function(){w.classList.remove('sig-updated');}, 600);
  }
  function sigHomeSetSort(sort,el){
    sigHomeSort=sort;
    if(el){[].forEach.call(el.parentNode.children,function(a){a.classList.remove('on');});el.classList.add('on');}
    sigHomeRender();
  }
  window.sigHomeSetSort=sigHomeSetSort;
  function applySignals(d){
    setBadge('sig-upd-badge', d.phase);
    SIG_BY_CODE={}; (d.signals||[]).forEach(function(s){SIG_BY_CODE[s.code]=true;}); rankRender();
    SIGNALS_HOME=d.signals||[];
    SIGNALS_ALL=d.signalsAll||d.signals||[]; SIG_ASOF=d.asOf; sigAllRender(); sigAllDnRender();
    var st=document.getElementById('sig-title'); if(st) st.textContent=asOfPrefix(d.asOf)+' 특이 신호';
    sigHomeRender();
    // 전 섹터 라이브 평균·코스피%를 배너에 반영 — 장중에도 버틴/밀린 섹터가 후행하지 않는다
    if(d.sectors) SIG_SECTORS=d.sectors;
    if(typeof d.kospiPct==='number') SIG_KOSPI=d.kospiPct;
    renderTodayLine();
    sbxRenderTabs(); sbxRenderBody(); // 전 섹터 라이브 값 도착 시 탭 전체를 즉시 갱신(클릭 전에도 최신값)
  }
  /* 특이 신호 전체(더보기) — D안 UI 유지 + 정렬 3종(강도/상승률/하락률) */
  function sigAllSorted(){
    var arr=SIGNALS_ALL.slice();
    if(sigAllSort==='up') arr.sort(function(a,b){return b.pct-a.pct;});
    else if(sigAllSort==='dn') arr.sort(function(a,b){return a.pct-b.pct;});
    // 'score'는 API가 이미 강도순으로 내려준 순서를 유지
    return arr;
  }
  function sigAllRender(){
    var box=document.getElementById('sigall-rows'); if(!box) return;
    var arr=sigAllSorted();
    var flag={score:'신호 강도 1위',up:'오늘 최고 상승',dn:'오늘 최대 하락'}[sigAllSort];
    box.innerHTML=arr.length?arr.map(function(s,i){return sigItemHtml(s,i,flag);}).join(''):'<p class="sig-intro" style="padding:24px 16px;text-align:center;color:#94A3B8;">표시할 특이 신호가 없어요.</p>';
    var cnt=document.getElementById('sigall-count'); if(cnt) cnt.textContent=arr.length+'종목';
    var t=document.getElementById('sigall-title'); if(t) t.textContent=asOfPrefix(SIG_ASOF)+' 특이 신호';
  }
  function sigAllSetSort(sort,el){
    sigAllSort=sort;
    if(el){[].forEach.call(el.parentNode.children,function(a){a.classList.remove('on');});el.classList.add('on');}
    sigAllRender();
  }
  // 정렬 탭은 정적 HTML의 인라인 onclick에서 호출 → 클로저 밖(전역)에서 접근 가능해야 함
  window.sigAllSetSort=sigAllSetSort;
  /* 우측 사이드 — 하락률 순(신호 종목 중 하락 상위 10) */
  function sigAllDnSorted(){ return SIGNALS_ALL.filter(function(s){return (s.pct||0)<0;}).sort(function(a,b){return a.pct-b.pct;}); }
  function sigAllDnRender(){
    var box=document.getElementById('sigall-dn-rows'); if(!box) return;
    if(!SIGNALS_ALL.length){ box.innerHTML=''; return; }
    var arr=sigAllDnSorted().slice(0,10);
    if(!arr.length){ box.innerHTML='<p class="sig-intro" style="padding:20px 16px;text-align:center;color:#94A3B8;">하락 중인 신호 종목이 없어요.</p>'; return; }
    var goArrow='<svg class="sig-go" width="14" height="14" viewBox="0 0 20 20" fill="none"><path d="M8 5l5 5-5 5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    // 좌측 색 막대 대신 순위 숫자로 표기
    box.innerHTML=arr.map(function(s,i){
      var lc=s.dir==='up'?'var(--up)':'var(--dn)', sign=s.pct>=0?'+':'';
      var badges=(s.badges||[]).map(badgeHtml).join('');
      return '<a class="sig-row" onclick="goStock(\''+s.code+'\')">'
        +'<span class="num" style="min-width:16px;text-align:center;align-self:center;color:#94A3B8;font-weight:800;font-size:12px;flex-shrink:0;">'+(i+1)+'</span>'
        +'<span class="sig-rmain"><span class="sig-rnm">'+s.name+' <small>'+s.code+' · '+s.sector+'</small></span>'
        +'<span class="sig-rbadges">'+badges+'</span></span>'
        +'<span class="sig-rpct" style="color:'+lc+';">'+sign+s.pct.toFixed(1)+'%</span>'+goArrow+'</a>';
    }).join('');
  }
  function clearSkel(){ ['sig-rows'].forEach(function(id){var e=document.getElementById(id); if(e&&e.querySelector('.skl')) e.innerHTML='';}); }
  function loadSignals(){
    fetch('/api/signals',{cache:'no-store'}).then(function(r){return r.ok?r.json():null;})
      .then(function(d){ if(d&&!d.error){ applySignals(d); } else { clearSkel(); } })
      .catch(function(){ clearSkel(); });
  }
  function pollVolTop(){
    fetch('/api/vol-top',{cache:'no-store'})
      .then(function(r){return r.ok?r.json():null;})
      .then(function(d){
        if(d&&(d.top||d.all)) renderTops(d);
        var badge=document.getElementById('vol-upd-badge');
        if(badge) badge.title='최근 갱신: '+new Date().toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit'});
      })
      .catch(function(){});
  }
  function krMarketOpen(){
    if(window.krIsKospiHoliday&&window.krIsKospiHoliday()) return false; // 주말·공휴일
    var m=((new Date().getUTCHours()*60+new Date().getUTCMinutes())+9*60)%(24*60);
    return m>=540&&m<=930;
  }
  function renderTopsFromSnap(){
    if(!SNAP||!SNAP.stocks) return;
    var list=Object.keys(SNAP.stocks).map(function(c){var s=SNAP.stocks[c];return {code:c,name:s.name,sector:s.sector,vol:s.vol||0,changePct:s.change_pct||0,price:s.close||null};});
    var byVol=list.filter(function(x){return x.vol>0;}).sort(function(a,b){return b.vol-a.vol;}).slice(0,5);
    var maxv=byVol[0]?byVol[0].vol:1;
    var etf=SNAP.etfs?Object.keys(SNAP.etfs).map(function(c){var e=SNAP.etfs[c];return {code:c,name:e.name,sector:'ETF',vol:e.vol||0,changePct:e.change_pct||0,price:null};}):[];
    renderTops({top:byVol.map(function(x){return Object.assign({},x,{barPct:Math.round(x.vol/maxv*100)});}),all:list,etf:etf});
  }

  /* ── 섹터별 종목 브라우저 (홈 중앙) — stocks-snapshot.json + /api/stocks-live 배선 ── */
  var SBX_ORDER=['semicon','battery','auto','defense','ship','bio','finance','power'];
  var SBX_EMOJI={semicon:'🔬',battery:'🔋',auto:'🚗',defense:'🛡️',ship:'🚢',bio:'🧬',finance:'🏦',power:'⚡'};
  var sbxActiveKey='semicon';
  function sbxPctCls(p){return p>0?'up':(p<0?'down':'flat');}
  function sbxPctFmt(p){return (p>0?'+':'')+p.toFixed(2)+'%';}
  function sbxWon(n){return Math.round(n).toLocaleString();}
  // 섹터 상세 페이지(sector/*/index.html)와 동일한 곡선 스파크 양식 — 중간점 앵커 베지어 + 그라디언트 채움
  function sbxSpark(vals, isLive){
    if(!vals||vals.length<2) return '';
    var W=240,H=34,padT=3,padB=3,n=vals.length;
    var min=Math.min.apply(null,vals),max=Math.max.apply(null,vals),rng=(max-min)||1;
    var up=vals[n-1]>=vals[0], col=up?'#E03131':'#2775ED';
    // 장중 곡선은 정적 20일 곡선과 똑같이 카드 폭을 꽉 채우면 "실시간 갱신 중"인지 구분이 안 간다.
    // 09:00~15:30 경과 비율만큼만 폭을 채우고 나머지는 점선으로 비워, 하루가 진행 중임을 시각적으로 드러낸다.
    var drawW=W;
    if(isLive){
      var k=new Date(Date.now()+9*3600*1000), kmin=k.getUTCHours()*60+k.getUTCMinutes();
      var elapsed=Math.max(0,Math.min(390,kmin-540)); // 09:00(540분) 기준 경과분, 15:30(930분)에 390
      drawW=Math.max(W*(elapsed/390), W*(1/n));
    }
    function x(i){return (i/(n-1))*drawW;}
    function y(v){return padT+(1-(v-min)/rng)*(H-padT-padB);}
    var d='M'+x(0).toFixed(1)+','+y(vals[0]).toFixed(1);
    for(var i=1;i<n;i++){
      var cx=((x(i-1)+x(i))/2).toFixed(1);
      d+=' C'+cx+','+y(vals[i-1]).toFixed(1)+' '+cx+','+y(vals[i]).toFixed(1)+' '+x(i).toFixed(1)+','+y(vals[i]).toFixed(1);
    }
    var lastX=x(n-1).toFixed(1), lastY=y(vals[n-1]).toFixed(1);
    var gid='sbx-grad-'+Math.random().toString(36).slice(2,8);
    // 실시간 진행 표시: 마지막 값에서 카드 끝까지 점선 가이드(장 마감 전까지 "여기까지 진행 중")
    var trail=(isLive&&drawW<W-2) ? ('<line x1="'+lastX+'" y1="'+((H-padT-padB)/2+padT).toFixed(1)+'" x2="'+W+'" y2="'+((H-padT-padB)/2+padT).toFixed(1)+'" stroke="#94A3B8" stroke-opacity="0.35" stroke-width="1" stroke-dasharray="2,2"/>') : '';
    // data-curve: live(오늘 장중 1분봉)/static(20거래일 종가) 구분 — DOM에서 확인 가능하게
    var svg='<svg viewBox="0 0 '+W+' '+H+'" preserveAspectRatio="none" data-curve="'+(isLive?'live':'static')+'" aria-label="'+(isLive?'오늘 장중 추이':'최근 20거래일 종가 추이')+'">'
      +'<defs><linearGradient id="'+gid+'" x1="0" y1="0" x2="0" y2="1">'
      +'<stop offset="0" stop-color="'+col+'" stop-opacity="0.14"/>'
      +'<stop offset="1" stop-color="'+col+'" stop-opacity="0"/></linearGradient></defs>'
      +trail
      +'<path d="'+d+' L'+lastX+','+H+' L0,'+H+' Z" fill="url(#'+gid+')"/>'
      +'<path d="'+d+'" fill="none" stroke="'+col+'" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/>'
      +'</svg>';
    // 맥동하는 점은 SVG 밖의 일반 HTML 원으로 — preserveAspectRatio:none의 가로 스케일에 영향받지 않아 항상 정원이다.
    var liveDot=isLive ? ('<span class="spark-livedot" style="left:'+(lastX/W*100).toFixed(2)+'%;top:'+(lastY/H*100).toFixed(2)+'%;background:'+col+';"></span>') : '';
    return svg+liveDot;
  }
  // 오늘 장중 1분봉 캐시 (code → minutes[]). 있으면 곡선을 정적 20일 대신 실시간 흐름으로 그린다.
  var sbxIntraday={};
  // 섹터별 라이브 시세 응답을 한 번이라도 받았는지(성공·실패·휴장 무관). 미해결이면 카드 숫자에 빗금 placeholder를 그린다.
  var sbxLiveTried={};
  // 장중인데 현재 탭 섹터의 라이브 응답이 아직 안 온 상태 — 스냅샷(전일 종가) 숫자를 노출하지 않고 빗금으로 대기.
  function sbxPending(){ return krMarketOpen() && !sbxLiveTried[sbxActiveKey]; }
  function sbxSkel(w,h){ return '<span class="scard__skel" style="width:'+w+'px;height:'+h+'px;"></span>'; }
  function sbxCurve(s){var iv=sbxIntraday[s.code]; return (iv&&iv.length>=2)?iv:s.spark20;}
  function sbxCurveIsLive(s){var iv=sbxIntraday[s.code]; return !!(iv&&iv.length>=2);}
  function sbxTodayYMD(){var k=new Date(Date.now()+9*3600*1000);return ''+k.getUTCFullYear()+String(k.getUTCMonth()+1).padStart(2,'0')+String(k.getUTCDate()).padStart(2,'0');}
  // 장중인데 아직 이 종목의 실시간 곡선을 못 받아온 상태 — 이럴 때 20일 정적 곡선(꽉 찬 폭)을
  // 먼저 그렸다가 잠시 후 장중 곡선(짧은 폭)으로 교체하면 폭이 갑자기 줄어드는 "버벅임"으로 보인다.
  // 그래서 로딩 중엔 폭이 없는 얇은 점선 placeholder만 보여주고, 실제 곡선은 최종 크기로 한 번에 그린다.
  function sbxSparkSkeleton(){
    return '<svg viewBox="0 0 240 34" preserveAspectRatio="none" aria-hidden="true">'
      +'<line x1="0" y1="17" x2="240" y2="17" stroke="#CBD5E1" stroke-width="1.4" stroke-dasharray="3,3">'
      +'<animate attributeName="stroke-opacity" values="0.25;0.55;0.25" dur="1.1s" repeatCount="indefinite"/>'
      +'</line></svg>';
  }
  // 현재 섹터 종목들의 오늘 장중 곡선을 /api/intraday(CDN 30초 캐시)로 받아 해당 카드 곡선만 교체.
  function sbxLoadIntraday(){
    if(!SNAP) return;
    var today=sbxTodayYMD();
    sbxSectorStocks(sbxActiveKey).forEach(function(s){
      var code=s.code;
      fetch('/api/intraday?code='+code,{cache:'no-store'})
        .then(function(r){return r.ok?r.json():null;})
        .then(function(d){
          var el=document.querySelector('.scard[data-code="'+code+'"] .scard__spark');
          if(!d||!Array.isArray(d.minutes)||d.minutes.length<2||d.date!==today){
            if(el&&!sbxIntraday[code]) el.innerHTML=sbxSpark(s.spark20,false); // 오늘 세션 없으면 정적 곡선으로 폴백
            return;
          }
          sbxIntraday[code]=d.minutes;
          if(el) el.innerHTML=sbxSpark(d.minutes, true);
        }).catch(function(){
          var el=document.querySelector('.scard[data-code="'+code+'"] .scard__spark');
          if(el&&!sbxIntraday[code]) el.innerHTML=sbxSpark(s.spark20,false);
        });
    });
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
    if(SIG_SECTORS&&SIG_SECTORS[key]&&SIG_SECTORS[key].total) return SIG_SECTORS[key];
    var arr=sbxSectorStocks(key), sum=0,up=0,dn=0;
    arr.forEach(function(s){var p=s.change_pct||0; sum+=p; if(p>0)up++; else if(p<0)dn++;});
    return {avg:arr.length?sum/arr.length:0, up:up, dn:dn, total:arr.length};
  }
  // 상단 스트립의 코스피 등락률을 읽는다(유니코드 마이너스·기호 정규화). 못 읽으면 null.
  function tlKospiPct(){
    var el=document.getElementById('h-kospi-c'); if(!el) return null;
    var v=parseFloat((el.textContent||'').replace(/[−–—]/g,'-').replace(/[^0-9.\-]/g,''));
    return isFinite(v)?v:null;
  }
  // ── '오늘의 한 줄' 요약 배너 ──
  // 섹터 소스 우선순위: /api/signals가 내려준 전 섹터 라이브 평균(장중 2분 갱신) > 스냅샷(전일 종가).
  // 문구는 맥락(장중/마감·리더/래거드 유무)에 맞는 템플릿 풀에서 하나를 골라 채운다 — 매 방문마다 달라져 지루하지 않게.
  // 슬롯: {tone}=당일 장세(상승 우위 등) · {lead}=주도 섹터 · {lag}=부진 섹터 · {kp}=코스피% · {when}=장중/오늘
  // 조사 토큰: {lead:이}=이/가, {lead:은}=은/는, {lead:을}=을/를, {lead:으로}=으로/로, {lead:이에요}=이에요/예요, {tone:이지만}=이지만/지만 (받침 자동)
  // 케이스는 톤 방향(상승/하락/보합) × 분산 여부로 나눠, 문구 프레이밍이 톤과 절대 어긋나지 않게 한다.
  // 각 케이스는 phase(live=장중 진행형 / closed=마감 완료형)로 다시 나뉜다 — 장중에 "밀렸어요"(완료)처럼
  // 아직 끝나지 않은 하루를 과거형으로 단정하면 안 되기 때문. live는 "~하고 있어요" 계열, closed만 "~했어요" 계열을 쓴다.
  var TL_TPL={
    // 상승일, 일부 섹터는 뒤처짐 — 주도/소외 프레이밍 (버틴·발목·방어 금지)
    up_mix:{
      live:[
        '{tone:이에요}. {lead:이} 상승을 주도하고 있고, {lag:은} 따라오지 못하고 있어요.',
        '{lead:으로} 매수세가 몰리고 있어요. {lag:은} 상대적으로 소외되고 있고요. {tone:이에요}.',
        '{when} {tone} — 지금 주역은 {lead}, {lag:은} 뒤처지고 있어요.',
        '코스피 {kp}. 강세는 {lead}, 부진은 {lag:으로} 갈리는 중이에요.',
        '{lead:이} 지수를 끌어올리고 있어요. {lag:은} 힘을 보태지 못하고 있고요.',
        '{tone:이지만} {lead:은} 특히 뜨겁고, {lag:은} 미지근해요.'
      ],
      closed:[
        '{tone:이에요}. {lead:이} 상승을 주도했고, {lag:은} 따라오지 못했어요.',
        '{lead:으로} 매수세가 몰렸어요. {lag:은} 상대적으로 소외됐고요. {tone:이에요}.',
        '{when} {tone} — 오늘의 주역은 {lead}, {lag:은} 뒤처졌어요.',
        '코스피 {kp}. 강세는 {lead}, 부진은 {lag:으로} 갈렸어요.',
        '{lead:이} 지수를 끌어올렸어요. {lag:은} 힘을 보태지 못했고요.',
        '{tone:이지만} {lead:은} 특히 뜨거웠어요. {lag:은} 미지근했고요.'
      ]
    },
    // 전면 상승 (부진 섹터 없음)
    up:{
      live:[
        '{tone:이에요}. {lead:이} 상승을 이끌고 있어요.',
        '고르게 초록불이 켜지고 있어요. 특히 {lead:이} 앞장서고 있고요. {tone:이에요}.',
        '{when} {tone} — 지금 대장은 {lead:이에요}.',
        '위험자산 선호가 살아나고 있어요. {lead:이} 특히 강하고요.',
        '코스피 {kp}. {lead:이} 랠리를 주도하고 있어요.',
        '매수 심리가 붙고 있어요. {lead:이} 가장 뜨겁고요. {tone:이에요}.'
      ],
      closed:[
        '{tone:이에요}. {lead:이} 상승을 이끌었어요.',
        '고르게 초록불이 켜졌어요. 특히 {lead:이} 앞장섰고요. {tone:이에요}.',
        '{when} {tone} — 오늘의 대장은 {lead:이에요}.',
        '위험자산 선호가 살아났어요. {lead:이} 특히 강했고요.',
        '코스피 {kp}. {lead:이} 랠리를 주도했어요.',
        '매수 심리가 붙었어요. {lead:이} 가장 뜨거웠고요. {tone:이에요}.'
      ]
    },
    // 하락일, 일부 섹터는 방어 — 버틴·발목·방어 프레이밍은 여기만
    dn_mix:{
      live:[
        '{tone:이에요}. {lead:이} 버티고 있고, {lag:은} 크게 밀리고 있어요.',
        '{when} {tone} 속에서 {lead}만 초록불을 지키고 있어요. {lag:은} 낙폭이 커지고 있고요.',
        '{lead:이} 방어선, {lag:이} 뇌관이에요. {tone:이에요}.',
        '{tone} — 그나마 버티는 건 {lead}, 발목 잡는 건 {lag:이에요}.',
        '{lag:이} 지수를 끌어내리는 사이 {lead:이} 홀로 버티고 있어요.',
        '코스피 {kp}. {lag:이} 지수를 누르고 있고, {lead:은} 방어하고 있어요.',
        '{tone:이지만} {lead:은} 견조하고, 반대로 {lag:은} 부진해요.'
      ],
      closed:[
        '{tone:이에요}. {lead:이} 버텼고, {lag:은} 크게 밀렸어요.',
        '{when} {tone} 속에서 {lead}만 초록불을 지켰어요. {lag:은} 낙폭이 컸고요.',
        '{lead:이} 방어선, {lag:이} 뇌관이었어요. {tone:이에요}.',
        '{tone} — 그나마 버틴 건 {lead}, 발목 잡은 건 {lag:이에요}.',
        '{lag:이} 지수를 끌어내리는 사이 {lead:이} 홀로 버텼어요.',
        '코스피 {kp}. {lag:이} 지수를 눌렀고, {lead:은} 방어했어요.',
        '{tone:이지만} {lead:은} 견조했어요. 반대로 {lag:은} 부진했고요.'
      ]
    },
    // 전면 하락 (방어 섹터 없음)
    dn:{
      live:[
        '{tone:이에요}. 대부분 약세이고 {lag:이} 특히 부진해요.',
        '{when} 숨을 곳이 없어요. {lag:이} 낙폭 상위이고요. {tone:이에요}.',
        '위험회피가 짙어지고 있어요. {lag:이} 가장 크게 밀리고 있고요.',
        '전반적으로 무거워요. {lag:이} 하락을 주도하고 있어요.',
        '코스피 {kp}. {lag:이} 지수를 끌어내리고 있어요.',
        '매도세가 우위예요. {lag}에서 낙폭이 두드러지고 있고요. {tone:이에요}.'
      ],
      closed:[
        '{tone:이에요}. 대부분 약세였고 {lag:이} 특히 부진했어요.',
        '{when} 숨을 곳이 없었어요. {lag:이} 낙폭 상위였고요. {tone:이에요}.',
        '위험회피가 짙었어요. {lag:이} 가장 크게 밀렸고요.',
        '전반적으로 무거웠어요. {lag:이} 하락을 주도했어요. {tone:이에요}.',
        '코스피 {kp}. {lag:이} 지수를 끌어내렸어요.',
        '매도세가 우위였어요. {lag}에서 낙폭이 두드러졌고요. {tone:이에요}.'
      ]
    },
    // 보합일, 섹터별 온도차 — 방향 단정 없는 중립 프레이밍
    flat_mix:{
      live:[
        '오늘의 온도차예요. {lead:은} 따뜻하고 {lag:은} 싸늘해요.',
        '희비가 갈리고 있어요. {lead:은} 웃고 {lag:은} 울고 있어요. {tone:이에요}.',
        '{lead:이} 상대적 강세, {lag:이} 상대적 약세예요. {tone:이에요}.',
        '쏠림이 뚜렷해요. {lead}엔 온기, {lag}엔 한기가 돌고 있어요.',
        '{when} 기준 {tone}. 강세는 {lead}, 약세는 {lag:으로} 갈리는 중이에요.',
        '돈은 {lead:으로}, 매물은 {lag:으로} 쏠리고 있어요. {tone:이에요}.'
      ],
      closed:[
        '오늘의 온도차예요. {lead:은} 따뜻했고 {lag:은} 싸늘했어요.',
        '희비가 갈렸어요. {lead:은} 웃고 {lag:은} 울었어요. {tone:이에요}.',
        '{lead:이} 상대적 강세, {lag:이} 상대적 약세예요. {tone:이에요}.',
        '쏠림이 뚜렷했어요. {lead}엔 온기, {lag}엔 한기가 돌았어요.',
        '{when} 기준 {tone}. 강세는 {lead}, 약세는 {lag:으로} 갈렸어요.',
        '돈은 {lead:으로}, 매물은 {lag:으로} 쏠렸어요. {tone:이에요}.'
      ]
    },
    // 분산조차 없음 (거의 안 뜨는 안전 케이스)
    flat:{
      live:[
        '{tone:이에요}. 뚜렷한 주도 섹터 없이 눈치보기 장세예요.',
        '{when} 방향을 정하지 못하고 있어요. 관망세가 짙어요.',
        '코스피 {kp}. 섹터별 등락이 엇갈린 보합 흐름이에요.',
        '{tone:이에요}. 매수도 매도도 뚜렷하지 않아요.'
      ],
      closed:[
        '{tone:이에요}. 뚜렷한 주도 섹터 없이 눈치보기 장세였어요.',
        '{when} 방향을 정하지 못했어요. 관망세가 짙어요.',
        '코스피 {kp}. 섹터별 등락이 엇갈린 보합 흐름이에요.',
        '{tone:이에요}. 매수도 매도도 뚜렷하지 않았어요.'
      ]
    }
  };
  var _tlCase=null, _tlPick=null; // 로드 세션 동안 문구 고정(데이터만 갱신), 구조(case+phase)가 바뀌면 재추첨
  function tlPick(caseKey, hasKp, phase){
    var stateKey=caseKey+'|'+phase;
    if(_tlCase===stateKey && _tlPick) return _tlPick;
    var pool=TL_TPL[caseKey][phase].filter(function(t){ return hasKp || t.indexOf('{kp}')<0; });
    if(!pool.length) pool=TL_TPL[caseKey][phase];
    _tlPick=pool[Math.floor(Math.random()*pool.length)]; _tlCase=stateKey;
    return _tlPick;
  }
  // 받침 유무에 따른 조사 꼬리만 반환 (섹터명 span 바깥에 붙여 조사는 색/굵기 없이 표기)
  function josaTail(word, type){
    var last=word.charCodeAt(word.length-1), isHan=last>=0xAC00&&last<=0xD7A3;
    var bat=isHan?((last-0xAC00)%28):0, hasBat=bat!==0, isRieul=bat===8;
    if(type==='이') return hasBat?'이':'가';
    if(type==='은') return hasBat?'은':'는';
    if(type==='을') return hasBat?'을':'를';
    if(type==='으로') return (!hasBat||isRieul)?'로':'으로';
    if(type==='이에요') return hasBat?'이에요':'예요';
    if(type==='이지만') return hasBat?'이지만':'지만';
    return '';
  }
  function tlFill(tpl, c){
    var leadSpan='<span class="tl-lead"><b>'+c.lead+'</b></span>', lagSpan='<span class="tl-lag"><b>'+c.lag+'</b></span>';
    var toneSpan='<span class="tl-tone '+c.cls+'">'+c.tone+'</span>';
    return tpl
      .replace(/\{tone(?::([^}]+))?\}/g, function(_m,t){ return toneSpan+(t?josaTail(c.tone,t):''); })
      .replace(/\{lead(?::([^}]+))?\}/g, function(_m,t){ return leadSpan+(t?josaTail(c.lead,t):''); })
      .replace(/\{lag(?::([^}]+))?\}/g, function(_m,t){ return lagSpan+(t?josaTail(c.lag,t):''); })
      .replace(/\{kp\}/g, c.kp!=null ? '<b>'+(c.kp>=0?'+':'')+c.kp.toFixed(2)+'%</b>' : '')
      .replace(/\{when\}/g, c.when);
  }
  // 섹터 통계 소스 — 라이브(SIG_SECTORS) 우선, 없으면 스냅샷 기반
  function tlSectorStats(){
    if(SIG_SECTORS){
      return SBX_ORDER.map(function(k){var s=SIG_SECTORS[k]; return (s&&s.total)?{label:SECTOR_LABELS[k],avg:s.avg,total:s.total}:null;}).filter(Boolean);
    }
    return SBX_ORDER.map(function(k){var st=sbxSectorStat(k); return st.total?{label:SECTOR_LABELS[k],avg:st.avg,total:st.total}:null;}).filter(Boolean);
  }
  function renderTodayLine(){
    var wrap=document.getElementById('today-line'); if(!wrap) return;
    var stats=tlSectorStats();
    if(!stats.length){ wrap.style.display='none'; return; }
    var leaders=stats.filter(function(s){return s.avg>0;}).sort(function(a,b){return b.avg-a.avg;}).slice(0,2);
    var lags=stats.filter(function(s){return s.avg<0;}).sort(function(a,b){return a.avg-b.avg;}).slice(0,2);
    var kp = (SIG_KOSPI!=null) ? SIG_KOSPI : tlKospiPct();
    var basis = kp!=null ? kp : (stats.reduce(function(a,s){return a+s.avg;},0)/stats.length);
    var tone, cls='', ic='📊';
    if(basis<=-2){tone='급락장';cls='dn';ic='🔻';}
    else if(basis<=-0.5){tone='하락 우위';cls='dn';ic='🔻';}
    else if(basis>=2){tone='급등장';cls='up';ic='🔺';}
    else if(basis>=0.5){tone='상승 우위';cls='up';ic='🔺';}
    else {tone='보합권';cls='';ic='➖';}
    var hasL=leaders.length, hasG=lags.length;
    var caseKey = (hasL&&hasG)
      ? (cls==='up'?'up_mix':cls==='dn'?'dn_mix':'flat_mix')
      : (hasL?'up':hasG?'dn':'flat');
    var phase=krMarketOpen()?'live':'closed';
    var ctx={
      tone:tone, cls:cls, kp:kp, when:phase==='live'?'장중':'오늘',
      lead:leaders.map(function(s){return s.label;}).join('·'),
      lag:lags.map(function(s){return s.label;}).join('·')
    };
    wrap.innerHTML='<span class="tl-ic">'+ic+'</span><span>'+tlFill(tlPick(caseKey, kp!=null, phase), ctx)+'</span>';
    wrap.style.display='';
  }
  function sbxCardHtml(s){
    var wk52Pct=(s.wk52_high>s.wk52_low)?Math.max(0,Math.min(100,(s.close-s.wk52_low)/(s.wk52_high-s.wk52_low)*100)):null;
    var extra='';
    if(s.wk52_high!=null&&s.wk52_low!=null) extra+='<div class="scard__range">52주 '+sbxWon(s.wk52_low)+' – '+sbxWon(s.wk52_high)+'</div>';
    if(wk52Pct!=null){
      extra+='<div class="scard__posbar"><div class="scard__posfill '+(s.change_pct>0?'up':'')+'" style="width:'+wk52Pct.toFixed(1)+'%"></div><div class="scard__pos" style="left:'+wk52Pct.toFixed(1)+'%"></div></div>'
        +'<div class="scard__poslbl">52주 중 '+Math.round(wk52Pct)+'% 지점</div>';
    }
    // 장중인데 아직 이 종목의 실시간 곡선을 못 받아온 상태면, 나중에 폭이 줄어드는 정적 곡선 대신
    // placeholder를 먼저 보여준다 — sbxLoadIntraday가 도착하면 최종 크기로 한 번에 교체한다.
    var sparkHtml = (krMarketOpen()&&!sbxIntraday[s.code]) ? sbxSparkSkeleton() : sbxSpark(sbxCurve(s), sbxCurveIsLive(s));
    // 외국인 보유율은 카드 하단에선 눈에 잘 안 띄어 타이틀 줄 우측으로 이동
    var frHtml = s.foreign_rate!=null ? '<span class="scard__fr-h">외국인 '+s.foreign_rate.toFixed(1)+'%</span>' : '';
    // 라이브 미해결이면 가격·등락률을 스냅샷 숫자 대신 빗금으로 — 도착 즉시 최종값으로 교체돼 "튐"이 사라진다.
    var priceHtml = sbxPending()
      ? '<span class="scard__close">'+sbxSkel(72,19)+'</span><span class="scard__pct flat">'+sbxSkel(46,13)+'</span>'
      : '<span class="scard__close">'+sbxWon(s.close)+'</span><span class="scard__pct '+sbxPctCls(s.change_pct)+'">'+sbxPctFmt(s.change_pct)+'</span>';
    return '<a class="scard" data-code="'+s.code+'" onclick="goStock(\''+s.code+'\')">'
      +'<div class="scard__head"><span class="scard__name">'+s.name+'</span><span class="scard__code">'+s.code+'</span>'+frHtml+'</div>'
      +'<div class="scard__price">'+priceHtml+'</div>'
      +'<div class="scard__spark">'+sparkHtml+'</div>'
      +extra+'</a>';
  }
  function sbxRenderTabs(){
    var box=document.getElementById('sbx-tabs'); if(!box||!SNAP) return;
    box.innerHTML=SBX_ORDER.map(function(key){
      var st=sbxSectorStat(key), cls=sbxPctCls(st.avg);
      return '<span class="sbx-tab'+(key===sbxActiveKey?' on':'')+'" data-key="'+key+'">'+SBX_EMOJI[key]+' '+SECTOR_LABELS[key]+'<span class="rt '+cls+'">'+sbxPctFmt(st.avg)+'</span></span>';
    }).join('');
    [].slice.call(box.querySelectorAll('.sbx-tab')).forEach(function(el){
      el.onclick=function(){ sbxActiveKey=el.getAttribute('data-key'); sbxRenderTabs(); sbxRenderBody(); sbxUpdateLive(); sbxLoadIntraday(); };
    });
  }
  function sbxRenderBody(){
    var body=document.getElementById('sbx-body'); if(!body||!SNAP) return;
    var arr=sbxSectorStocks(sbxActiveKey), st=sbxSectorStat(sbxActiveKey);
    var avgCls=sbxPctCls(st.avg), upFlex=st.up||0.001, dnFlex=st.dn||0.001;
    // 집계값(평균·상승·하락·시장폭)도 카드와 같은 라이브 데이터에서 나오므로, 미해결이면 빗금으로 대기해 튐을 막는다.
    var pend=sbxPending();
    var statBlock = pend
      ? '<div class="sbx-stat">'
          +'<div class="sbx-stat__box"><div class="sbx-stat__label">섹터 평균</div><div class="sbx-stat__val flat">'+sbxSkel(56,17)+'</div></div>'
          +'<div class="sbx-stat__box"><div class="sbx-stat__label">상승</div><div class="sbx-stat__val flat">'+sbxSkel(28,17)+'</div></div>'
          +'<div class="sbx-stat__box"><div class="sbx-stat__label">하락</div><div class="sbx-stat__val flat">'+sbxSkel(28,17)+'</div></div>'
        +'</div>'
        +'<div class="sbx-breadth"><div class="sbx-breadth__label">시장폭 — 집계 중…</div>'
          +'<div class="sbx-breadth__bar"><span class="scard__skel" style="flex:1;height:8px;border-radius:4px;"></span></div></div>'
      : '<div class="sbx-stat">'
          +'<div class="sbx-stat__box"><div class="sbx-stat__label">섹터 평균</div><div class="sbx-stat__val '+avgCls+'">'+sbxPctFmt(st.avg)+'</div></div>'
          +'<div class="sbx-stat__box"><div class="sbx-stat__label">상승</div><div class="sbx-stat__val up">'+st.up+'</div></div>'
          +'<div class="sbx-stat__box"><div class="sbx-stat__label">하락</div><div class="sbx-stat__val down">'+st.dn+'</div></div>'
        +'</div>'
        +'<div class="sbx-breadth"><div class="sbx-breadth__label">시장폭 — '+st.total+'종목 중 상승 '+st.up+'</div>'
          +'<div class="sbx-breadth__bar"><div class="sbx-breadth__up" style="flex:'+upFlex+'"></div><div class="sbx-breadth__dn" style="flex:'+dnFlex+'"></div></div>'
          +'<div class="sbx-breadth__legend"><span><i class="iu"></i>상승 '+st.up+'</span><span><i class="id"></i>하락 '+st.dn+'</span></div></div>';
    body.innerHTML=
      statBlock
      +'<div class="sbx-list-head"><span class="sbx-list-head__t">종목 '+arr.length+'</span><span class="sbx-list-head__sort">등락률 높은 순 ↓</span></div>'
      +'<div class="sbx-list">'+arr.map(sbxCardHtml).join('')+'</div>';
  }
  function sbxSetLiveBadge(open){
    var el=document.getElementById('sbx-live'); if(!el) return;
    if(open){ el.className='sbx-live on'; el.innerHTML='<span class="sl-dot"></span>실시간 장중 · 30초 갱신'; }
    else { el.className='sbx-live off'; el.innerHTML='<span class="sl-dot"></span>장마감 · '+(_asOfYmd||'')+' 종가 기준'; }
  }
  function sbxUpdateLive(){
    if(!SNAP||!krMarketOpen()) { sbxSetLiveBadge(false); return; }
    var key=sbxActiveKey; // 응답 도착 전 탭이 바뀔 수 있어 요청 시점 섹터를 고정
    var codes=sbxSectorStocks(key).map(function(s){return s.code;});
    if(!codes.length) return;
    // 응답이 성공이든 실패든(휴장·API 장애 포함) 일단 시도가 끝나면 빗금을 풀고 가진 값(라이브 또는 스냅샷)을 노출한다.
    function resolve(){
      sbxLiveTried[key]=true;
      if(key===sbxActiveKey){ sbxRenderTabs(); sbxRenderBody(); renderTodayLine(); }
    }
    fetch('/api/stocks-live?codes='+encodeURIComponent(codes.join(',')),{cache:'no-store'})
      .then(function(r){return r.ok?r.json():null;})
      .then(function(d){
        if(d){
          sbxSetLiveBadge(!!d.open);
          if(Array.isArray(d.prices)){
            d.prices.forEach(function(p){
              var s=SNAP.stocks[p.code]; if(!s) return;
              if(isFinite(p.price)) s.close=p.price;
              if(p.changePct!=null) s.change_pct=p.changePct;
            });
          }
        }
        resolve();
      }).catch(function(){ resolve(); });
  }
  loadSignals();
  fetch('/data/stocks-snapshot.json',{cache:'no-store'})
    .then(function(r){return r.ok?r.json():null;})
    .then(function(snap){
      SNAP=snap;
      if(SNAP&&SNAP.stocks){
        var _ks=Object.keys(SNAP.stocks);
        _ks.forEach(function(c){STOCK_PAGES[c]=1;});
        STOCK_LIST=_ks.map(function(c){return {code:c,name:SNAP.stocks[c].name,sector:SNAP.stocks[c].sector};});
      }
      if(SNAP&&SNAP.generated_at){_asOfYmd=String(SNAP.generated_at).slice(0,10);applyAsOf();}
      pollVolTop();
      // 기본 탭 = 오늘 평균 등락률이 가장 높은 섹터. 매일 반도체로 고정돼 급락일엔 첫 화면이
      // 온통 빨강으로 열리고 옆 특이신호(초록)와 모순돼 보이던 문제 해결 — 세 섹션이 같은 방향을 가리킨다.
      var _best=sbxActiveKey, _bestAvg=-Infinity;
      SBX_ORDER.forEach(function(k){var st=sbxSectorStat(k); if(st.total&&st.avg>_bestAvg){_bestAvg=st.avg;_best=k;}});
      sbxActiveKey=_best;
      renderTodayLine();
      sbxRenderTabs(); sbxRenderBody(); sbxUpdateLive(); sbxLoadIntraday();
      if(krMarketOpen()){
        setInterval(pollVolTop,120000);
        setInterval(loadSignals,120000); // 장중 2분마다 특이신호 자동 갱신
        setInterval(sbxUpdateLive,30000); // 장중 30초마다 섹터 브라우저 실시간 시세 갱신
        setInterval(sbxLoadIntraday,30000); // 장중 30초마다 섹터 브라우저 곡선(장중 1분봉) 갱신
      }
    })
    .catch(function(){ pollVolTop(); });
})();

// 상단 스트립 실시간 갱신 — 코스피(/api/kospi-live) + 코스닥·환율(/api/market)
(function(){
  // 히어로 상단 배지 — 장중이면 LIVE, 마감·주말·공휴일이면 종가 기준. 정적 'LIVE' 고정으로 휴일에도 실시간처럼 보이던 문제 교정.
  (function(){
    var b=document.getElementById('kospi-live-badge'); if(!b) return;
    var open=(typeof hubMarketOpen==='function')?hubMarketOpen():false;
    if(open){ b.classList.remove('closed'); b.innerHTML='<span class="dot"></span>LIVE · 10초 갱신'; }
    else{ b.classList.add('closed'); b.style.color='#94A3B8'; b.innerHTML='<span class="dot" style="background:#94A3B8;animation:none"></span>장 마감 · 종가 기준'; }
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
      return '<span style="color:#94A3B8;'+(bold?'font-weight:800':'')+'">'+md+'</span>'
           + '<span style="text-align:right;font-variant-numeric:tabular-nums;font-weight:'+(bold?'800':'700')+'">'+cv+'</span>'
           + '<span style="text-align:right;font-variant-numeric:tabular-nums">'+chg+'</span>';
    }).join('');
    return '<div style="display:grid;grid-template-columns:auto 1fr auto;column-gap:14px;row-gap:3px;align-items:baseline">'+cells+'</div>';
  }
  fetch('/api/kospi-live',{cache:'no-store',signal:AbortSignal.timeout(6000)})
    .then(function(r){return r.ok?r.json():null;})
    .then(function(d){
      if(!d||!d.price) return;
      var el=document.getElementById('h-kospi'),ec=document.getElementById('h-kospi-c');
      if(el) el.textContent=Math.round(d.price).toLocaleString('ko-KR');
      if(ec){ec.textContent=fmtPct(d.changePct||0);ec.className='vc '+dirClass(d.changePct||0)+' num';}
    }).catch(function(){});
  function pollMarket(){
  fetch('/api/market',{cache:'no-store',signal:AbortSignal.timeout(6000)})
    .then(function(r){return r.ok?r.json():null;})
    .then(function(d){
      if(!d) return;
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
          e.textContent=(v>=0?'+':'−')+Math.abs(Math.round(v)).toLocaleString('ko-KR');
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
            u.innerHTML = open
              ? '<span class="live">● 60초 갱신</span>'
              : (label ? label+' 마감 기준' : '직전 거래일 마감 기준');
          }
        }
      }
    }).catch(function(){});
  }
  pollMarket();
  // 장중에만 폴링 — 코스닥·환율·수급을 60초 주기로 갱신(브리핑 시장 지표 패널과 동일 주기).
  if(typeof hubMarketOpen==='function'&&hubMarketOpen()) setInterval(pollMarket,60000);
})();

/* ── 수급 10거래일 추이 (수급 행 '10일 추이' 토글) ──────────────────────────────
   데이터: /data/supply-history.json — generate_html.update_supply_history()가 매일 미러링.
   억원 단위 실측. 값이 없으면 버튼째 숨긴다(운영규칙 0).
   기하는 컨테이너 실제 폭(px)으로 계산한다 — 고정 viewBox 균일 스케일로 두면 좁은 화면에서
   행 높이까지 같이 줄어 막대가 실오라기가 되고, preserveAspectRatio="none"으로 늘리면
   둥근 막대 끝이 타원으로 찌그러진다. */
(function(){
  var sup=document.getElementById('h-supply'), btn=document.getElementById('sup-more'),
      panel=document.getElementById('sup-panel');
  if(!sup||!btn||!panel) return;

  var SERIES=[['individual','개인'],['institution','기관'],['foreign','외국인']];
  var ROWS=[], maxAbs=0, W=600, H=60, ZERO=H/2, PAD=2, n=0, slot=0, bw=30;

  function fmt(v){ return (v>=0?'+':'−')+Math.abs(Math.round(v)).toLocaleString('ko-KR'); }
  function md(d){ return d.slice(5).replace('-','/'); }
  function kday(d){ var p=d.split('-'); return '일월화수목금토'[new Date(+p[0],+p[1]-1,+p[2]).getDay()]; }
  function ymdAdd(ymd,k){
    var p=ymd.split('-'), d=new Date(Date.UTC(+p[0],+p[1]-1,+p[2]));
    d.setUTCDate(d.getUTCDate()+k);
    return d.toISOString().slice(0,10);
  }

  /* 최근 10거래일 슬롯 구성 — 데이터가 있는 날 10개를 뒤에서 세되, 그 구간 안의 거래일인데
     데이터가 없는 날(수집 실패)은 빈 슬롯으로 남긴다. 당겨 붙이면 없던 연속성이 생긴다. */
  function buildRows(hist){
    var have=Object.keys(hist).sort();
    if(have.length<2) return [];
    var take=have.slice(-10);
    var start=take[0], end=take[take.length-1], out=[];
    for(var d=start; d<=end; d=ymdAdd(d,1)){
      if(window.krIsKospiHolidayOn && window.krIsKospiHolidayOn(d)) continue;  // 주말·공휴일은 슬롯 자체가 없다
      var r=hist[d]||null;
      out.push({d:d, individual:r?r.individual:null, institution:r?r.institution:null, foreign:r?r.foreign:null});
    }
    return out;
  }

  function rowSvg(key){
    var bars=ROWS.map(function(r,i){
      var x=i*slot+(slot-bw)/2, v=r[key];
      if(v==null){
        return '<rect class="sp-hit" x="'+x+'" y="'+(ZERO-7)+'" width="'+bw+'" height="14" fill="#F1F5F9" rx="3"'
             + ' data-d="'+r.d+'" data-v="na" tabindex="0"></rect>';
      }
      var h=Math.max(1.5, Math.abs(v)/maxAbs*(ZERO-PAD));
      var y=v>=0?ZERO-h:ZERO;
      var c=v>=0?'#E03131':'#2775ED';
      var r4=Math.min(4,bw/2,h);
      var path=v>=0
        ? 'M'+x+','+(y+h)+'V'+(y+r4)+'a'+r4+','+r4+' 0 0 1 '+r4+',-'+r4+'h'+(bw-2*r4)+'a'+r4+','+r4+' 0 0 1 '+r4+','+r4+'V'+(y+h)+'Z'
        : 'M'+x+','+y+'V'+(y+h-r4)+'a'+r4+','+r4+' 0 0 0 '+r4+','+r4+'h'+(bw-2*r4)+'a'+r4+','+r4+' 0 0 0 '+r4+',-'+r4+'V'+y+'Z';
      return '<path d="'+path+'" fill="'+c+'"></path>'
           + '<rect class="sp-hit" x="'+(i*slot)+'" y="0" width="'+slot+'" height="'+H+'" fill="transparent"'
           + ' data-d="'+r.d+'" data-v="'+v+'" data-k="'+key+'" tabindex="0"></rect>';
    }).join('');
    return '<svg viewBox="0 0 '+W+' '+H+'" width="'+W+'" height="'+H+'" role="img">'
         + '<line x1="0" y1="'+ZERO+'" x2="'+W+'" y2="'+ZERO+'" stroke="#E2E8F0" stroke-width="1"></line>'
         + bars + '</svg>';
  }

  function draw(){
    document.getElementById('sup-rows').innerHTML = SERIES.map(function(s){
      var t=ROWS.reduce(function(a,r){ return a+(r[s[0]]||0); },0);
      return '<div class="sp-row"><span class="who">'+s[1]+'</span>'
           + '<span class="plot">'+rowSvg(s[0])+'</span>'
           + '<span class="sum"><span class="k">10일 합</span><span class="v '+(t>=0?'up':'dn')+'">'+fmt(t)+'</span></span></div>';
    }).join('');
    document.getElementById('sup-xax').innerHTML = ROWS.map(function(r,i){
      if(i!==0 && i!==n-1 && !(i%3===0 && i<n-2)) return '';
      if(i===0)   return '<span style="left:0">'+md(r.d)+'</span>';
      if(i===n-1) return '<span style="right:0;left:auto">'+md(r.d)+'</span>';
      return '<span style="left:'+((i+0.5)/n*100)+'%;transform:translateX(-50%)">'+md(r.d)+'</span>';
    }).join('');
  }

  function measure(){
    var probe=panel.querySelector('.sp-axis .plot');
    var w=probe?probe.clientWidth:0;
    if(!w||!n) return;
    W=w; slot=W/n; bw=Math.max(5, Math.min(34, slot*0.42));
    draw();
  }

  function init(hist){
    ROWS=buildRows(hist); n=ROWS.length;
    if(n<2) return;                                   // 시계열이 안 되면 기능 자체를 노출하지 않는다
    maxAbs=0;
    ROWS.forEach(function(r){ SERIES.forEach(function(s){ var v=r[s[0]]; if(v!=null) maxAbs=Math.max(maxAbs,Math.abs(v)); }); });
    if(!maxAbs) return;

    document.getElementById('sup-tbody').innerHTML = ROWS.slice().reverse().map(function(r){
      var cells=SERIES.map(function(s){
        var v=r[s[0]];
        return v==null?'<td class="na">수집 없음</td>':'<td class="'+(v>=0?'up':'dn')+'">'+fmt(v)+'</td>';
      }).join('');
      return '<tr><td>'+md(r.d)+'('+kday(r.d)+')</td>'+cells+'</tr>';
    }).join('');

    // 제목·푸터가 같은 n을 쓰게 한다 — 공백 슬롯 때문에 구간 길이가 데이터 일수보다 클 수 있다
    document.getElementById('sup-title').textContent='최근 '+n+'거래일 순매수';
    var missing=ROWS.filter(function(r){ return r.individual==null; }).map(function(r){ return md(r.d); });
    document.getElementById('sup-foot').innerHTML =
      '단위 억원 · 코스피 투자자별 순매수'
      + (missing.length?' · <b>'+missing.join(', ')+'</b>는 수집 데이터가 없어 비워 뒀어요(0이라는 뜻이 아니에요)':'');

    btn.hidden=false;
    draw();
  }

  btn.addEventListener('click',function(){
    var open=panel.hidden;
    panel.hidden=!open; sup.classList.toggle('is-open',open); btn.setAttribute('aria-expanded',String(open));
    if(open) measure();                               // 열린 뒤라야 폭이 잡힌다(hidden이면 clientWidth가 0)
  });
  var rt;
  window.addEventListener('resize',function(){ clearTimeout(rt); rt=setTimeout(function(){ if(!panel.hidden) measure(); },120); });

  var tblBtn=document.getElementById('sup-tbl-btn'), cv=document.getElementById('sup-chart'), tv=document.getElementById('sup-table');
  tblBtn.addEventListener('click',function(){
    var toTable=tv.hidden;
    tv.hidden=!toTable; cv.hidden=toTable;
    tblBtn.setAttribute('aria-pressed',String(toTable));
    tblBtn.textContent=toTable?'그래프로 보기':'표로 보기';
    if(!toTable) measure();
  });

  /* 툴팁 — hover와 keyboard focus가 같은 내용을 낸다. 기존 전역 툴팁(showTip)은
     data-tip 속성 기반이라 여기선 쓰지 않고 제목/값을 직접 만든다. */
  var NAME={individual:'개인',institution:'기관',foreign:'외국인'};
  var tipEl=null;
  function tip(){ if(!tipEl){ tipEl=document.createElement('div');
    tipEl.style.cssText='position:fixed;z-index:60;pointer-events:none;background:#0F172A;color:#fff;border-radius:8px;padding:7px 10px;font-size:11.5px;line-height:1.55;box-shadow:0 6px 20px rgba(15,23,42,.22);opacity:0;transition:opacity .12s;white-space:nowrap;';
    document.body.appendChild(tipEl); } return tipEl; }
  panel.addEventListener('mouseover',onIn); panel.addEventListener('focusin',onIn);
  panel.addEventListener('mouseout',onOut); panel.addEventListener('focusout',onOut);
  function onIn(e){
    var t=e.target; if(!t.classList||!t.classList.contains('sp-hit')) return;
    var d=t.getAttribute('data-d'), v=t.getAttribute('data-v'), k=t.getAttribute('data-k'), el=tip();
    el.innerHTML = v==='na'
      ? '<span style="color:#94A3B8;font-size:10.5px">'+md(d)+'('+kday(d)+')</span><br>수집 데이터 없음'
      : '<span style="color:#94A3B8;font-size:10.5px">'+md(d)+'('+kday(d)+') · '+NAME[k]+'</span><br>'
        +'<b style="font-variant-numeric:tabular-nums;color:'+(+v>=0?'#F87171':'#93C5FD')+'">'+fmt(+v)+'</b> <span style="color:#94A3B8">억원</span>';
    var r=t.getBoundingClientRect();
    el.style.left=Math.max(8,Math.min(window.innerWidth-170, r.left+r.width/2-70))+'px';
    el.style.top=Math.max(8, r.top-54)+'px';
    el.style.opacity='1';
  }
  function onOut(){ if(tipEl) tipEl.style.opacity='0'; }

  fetch('/data/supply-history.json',{cache:'no-store'})
    .then(function(r){ return r.ok?r.json():null; })
    .then(function(h){ if(h&&Object.keys(h).length) init(h); })
    .catch(function(){});
})();

/* ── 🧭 이번 주 자금 지도 (ETF 순유입·유출 히트맵) ── */
(function(){
  var block=document.getElementById('flow-block');
  if(!block) return;
  var body=document.getElementById('flow-body');
  var TIERS=[[0,2,98],[2,4,74],[4,7,60],[7,10,48]];  // [start,end,rowHeightPx]
  var ENT={'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'};
  function esc(s){ return String(s==null?'':s).replace(/[&<>"']/g,function(c){return ENT[c];}); }

  function fmtEok(v){
    var a=Math.abs(v), sign=v>0?'+':(v<0?'−':'');
    if(a>=10000) return sign+(a/10000).toFixed(1).replace(/\.0$/,'')+'조';
    return sign+a.toLocaleString('en-US')+'억';
  }
  function tileStyle(flow,maxFlow){
    var inten=maxFlow?Math.abs(flow)/maxFlow:0;
    var alpha=(0.15+0.85*inten).toFixed(2);
    var rgb=flow>=0?'224,49,49':'39,117,237';
    var fg=alpha>0.46?'#fff':'#0F172A';
    return 'background:rgba('+rgb+','+alpha+');color:'+fg+';';
  }
  function tileHtml(t,maxFlow){
    return '<div class="flow-tile" style="flex:'+Math.abs(t.flow_eok)+';'+tileStyle(t.flow_eok,maxFlow)
      +'" data-theme="'+t.theme+'">'
      +'<div class="ft-nm">'+t.theme+'</div><div class="ft-amt">'+fmtEok(t.flow_eok)+'</div></div>';
  }
  function expandHtml(t){
    var rows=(t.top_etfs||[]).map(function(e){
      return '<div class="ft-ex-row"><span>'+esc(e.name)+'</span><span class="'+(e.flow_eok>=0?'ft-in':'ft-out')+'">'
        +fmtEok(e.flow_eok)+'</span></div>';
    }).join('');
    return '<div class="ft-expand" data-for="'+t.theme+'">'+rows+'</div>';
  }

  function render(data){
    var themes=(data.themes||[]).slice();
    if(!themes.length){ block.style.display='none'; return; }
    var visible=themes.slice(0,10), rest=themes.slice(10);
    var maxFlow=Math.max.apply(null, visible.map(function(t){return Math.abs(t.flow_eok);}));
    if(!maxFlow){ block.style.display='none'; return; }  // 유의미한 자금 이동 없음 — 숨김

    var html='';
    TIERS.forEach(function(tier){
      var seg=visible.slice(tier[0],tier[1]);
      if(!seg.length) return;
      html+='<div class="flow-row" style="height:'+tier[2]+'px;">'
        +seg.map(function(t){return tileHtml(t,maxFlow);}).join('')+'</div>';
    });
    body.innerHTML=html;

    var win=document.getElementById('flow-window');
    if(win) win.textContent='최근 '+(data.window_days||1)+'거래일 · 실측 설정/환매';
    var quiet=document.getElementById('flow-quiet');
    if(quiet){
      quiet.textContent=rest.length
        ? '그 외 '+rest.length+'개 테마는 이번 주 자금 이동이 크지 않았어요.' : '';
      quiet.style.display=rest.length?'':'none';
    }
    // 타일 클릭 → 인라인 확장(상위 ETF). 다시 누르면 접힘.
    body.querySelectorAll('.flow-tile').forEach(function(el){
      el.addEventListener('click',function(){
        var theme=el.getAttribute('data-theme');
        var open=body.querySelector('.ft-expand[data-for="'+CSS.escape(theme)+'"]');
        body.querySelectorAll('.ft-expand').forEach(function(x){x.remove();});
        if(open) return;
        var t=visible.filter(function(x){return x.theme===theme;})[0];
        if(t) el.closest('.flow-row').insertAdjacentHTML('afterend',expandHtml(t));
      });
    });
    block.style.display='';
  }

  function isFresh(iso){
    if(!iso) return false;
    // 5일 = 평일 갱신 + 주말·연휴 버퍼(§20 밸류에이션 가드와 동일 기준).
    // 달력 2일로 잡으면 월요일마다 금요일 데이터(3일 전)를 stale로 오판해 꺼진다.
    var age=(Date.now()-new Date(iso).getTime())/86400000;  // 일
    if(isNaN(age)||age>5){ console.warn('[flow-map] etf-flows.json 타임스탬프 이상 또는 5일 넘게 안 갱신됨 — 블록 숨김'); return false; }
    return true;
  }

  fetch('/data/etf-flows.json',{cache:'no-store'})
    .then(function(r){return r.ok?r.json():null;})
    .then(function(data){
      if(!data || !isFresh(data.generated_at)){ block.style.display='none'; return; }
      render(data);
    })
    .catch(function(){ block.style.display='none'; });
})();
