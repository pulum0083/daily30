// 자금 지도 탭(#flow-map) 화면 — /data/flow-map.json을 받아 테마 바 리스트와 테마 상세를 그린다
//
// 이 파일이 stocks-home.js가 아니라 별도 파일인 이유: stocks-home.js는 이미 3,300줄이 넘어
// 화면 하나를 더 얹으면 읽기도 테스트하기도 어려워진다. ds-subnav.js가 만든 선례를 따른다.
(function () {
  'use strict';

  // 같은 페이지에 두 번 로드돼도 리스너가 겹쳐 쌓이지 않게 한다(ds-subnav.js와 같은 가드).
  if (window.__flowMapInited) return;
  window.__flowMapInited = true;

  var DATA = null, DATES = [], MKT = [], TH = [], sortKey = 'size';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  /** 억원 → 표시 문자열. 1조 이상은 조 단위로 접는다. 마이너스는 U+2212(−). */
  function eok(v) {
    var a = Math.abs(v), sg = v > 0 ? '+' : (v < 0 ? '−' : '');
    if (a >= 10000) return sg + (a / 10000).toFixed(a >= 100000 ? 0 : 1).replace(/\.0$/, '') + '조';
    return sg + a.toLocaleString('en-US') + '억';
  }

  /** 총량 표시 — 부호를 떼고 절대값만. */
  function amt(v) { return eok(Math.abs(v)).replace(/^[+−]/, ''); }

  function md(d) { return String(d).slice(5).replace('-', '/'); }

  /** 요일. Date.UTC로 조립한 뒤 getUTCDay()를 쓴다 —
      'YYYY-MM-DDT00:00:00+09:00' 파싱은 KST 자정이 전날 15:00 UTC라 요일이 하루 밀린다. */
  function wd(d) {
    var p = String(d).split('-');
    return ['일', '월', '화', '수', '목', '금', '토'][
      new Date(Date.UTC(+p[0], +p[1] - 1, +p[2])).getUTCDay()];
  }

  /** 회전율 — 테마 안에서 돈이 얼마나 돌았나. 분모는 gross가 아니라 |net|이다. */
  function churn(t) { return t.gross_eok / Math.max(Math.abs(t.flow_eok), 1); }

  var SORTS = {
    size: function (a, b) { return Math.abs(b.flow_eok) - Math.abs(a.flow_eok); },
    net: function (a, b) { return b.flow_eok - a.flow_eok; },        // 유입 위 → 유출 아래
    churn: function (a, b) { return churn(b) - churn(a); }
  };

  /** 막대 폭(%). 0축이 가운데라 한쪽 최대 50%. 제곱근으로 부풀리지 않는다 — 상위 몇 개가
      사실상 전부라는 게 이 데이터의 진실이고 그대로 보이는 편이 정직하다. */
  function barPct(v, mx) { return (Math.abs(v) / (mx || 1) * 50).toFixed(2); }

  /** 가장 많은 테마가 한꺼번에 움직인 날. 기준은 금액이 아니라 **동조 테마 수(breadth)** —
      절대금액 최대일로 고르면 "15/16개가 동시에 뒤집힌 날"을 놓친다. 이 화면의 주제는
      규모가 아니라 폭이다. 동수면 금액으로 타이브레이크. 반환 {i, same}. */
  function pivot(mkt, themes) {
    var n = (mkt || []).length;
    if (!n) return { i: -1, same: 0 };
    var same = mkt.map(function (m, i) {
      return themes.filter(function (t) {
        var v = (t.daily || [])[i];
        return m >= 0 ? v > 0 : v < 0;
      }).length;
    });
    var p = 0;
    for (var i = 1; i < n; i++) {
      if (same[i] > same[p] || (same[i] === same[p] && Math.abs(mkt[i]) > Math.abs(mkt[p]))) p = i;
    }
    return { i: p, same: same[p] };
  }

  /** 마지막 갱신 이후 경과 일수. 파싱 실패면 null(판단하지 않는다). 미래 시각(시계 오차 등)은
      0으로 clamp — 음수 "−1일 지났어요" 같은 표시를 UI에 만들지 않는다. */
  function staleDays(iso, nowMs) {
    var t = Date.parse(iso);
    if (!isFinite(t)) return null;
    return Math.max(0, Math.floor(((nowMs == null ? Date.now() : nowMs) - t) / 864e5));
  }

  window.__flowMap = {
    esc: esc, eok: eok, amt: amt, md: md, wd: wd,
    churn: churn, SORTS: SORTS, barPct: barPct, pivot: pivot, staleDays: staleDays
  };
})();
