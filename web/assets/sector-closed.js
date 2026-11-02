// 섹터 페이지가 장 마감 뒤 오늘 공식 종가를 쓸지 판정하는 순수 함수
// 마감 잡이 페이지를 다시 만들기 전(15:31~16:32)엔 정적 값이 직전 거래일이다.
// 모든 종목이 같은 새 세션을 가질 때만 쓴다 — 한 화면에 두 날짜를 섞지 않는다.
(function(root){
  root.sectorClosedUpdate=function(prices, codes, snapDate){
    if(!Array.isArray(prices)||!Array.isArray(codes)||!codes.length||!snapDate) return null;
    var byCode={};
    prices.forEach(function(p){ if(p&&p.code) byCode[p.code]=p; });
    var snap=String(snapDate).replace(/-/g,''), session=null, rows={};
    for(var i=0;i<codes.length;i++){
      var p=byCode[codes[i]];
      if(!p||!p.sessionDate||!(p.price>0)||!(p.prevSessionClose>0)) return null;
      if(session===null) session=p.sessionDate;
      if(p.sessionDate!==session) return null;
      rows[codes[i]]={price:p.price, pct:Math.round((p.price/p.prevSessionClose-1)*10000)/100};
    }
    if(session<=snap) return null;
    return {date:session.slice(0,4)+'-'+session.slice(4,6)+'-'+session.slice(6,8), rows:rows};
  };
})(globalThis);
