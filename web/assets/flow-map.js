// 자금 지도 탭(#flow-map) 화면 — /data/flow-map.json을 받아 테마 바 리스트와 테마 상세를 그린다
//
// 이 파일이 stocks-home.js가 아니라 별도 파일인 이유: stocks-home.js는 이미 3,300줄이 넘어
// 화면 하나를 더 얹으면 읽기도 테스트하기도 어려워진다. ds-subnav.js가 만든 선례를 따른다.
(function () {
  'use strict';

  // 같은 페이지에 두 번 로드돼도 리스너가 겹쳐 쌓이지 않게 한다(ds-subnav.js와 같은 가드).
  if (window.__flowMapInited) return;
  window.__flowMapInited = true;

  var DATA = null, DATES = [], MKT = [], TH = [], sortKey = 'size', selected = null;

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

  function $(id) { return document.getElementById(id); }

  function setText(id, s) { var el = $(id); if (el) el.textContent = s; }
  function setHtml(id, s) { var el = $(id); if (el) el.innerHTML = s; }

  /* ── 시장 요약 ── */
  function renderMarket() {
    var cum = MKT.reduce(function (a, b) { return a + b; }, 0);
    var pv = pivot(MKT, TH);
    var inn = TH.filter(function (t) { return t.flow_eok > 0; }).length;
    var pvCell = pv.i < 0 ? '<div class="v">—</div><div class="s">데이터 부족</div>'
      : '<div class="v ' + (MKT[pv.i] >= 0 ? 'up' : 'dn') + '">'
        + md(DATES[pv.i]) + '(' + wd(DATES[pv.i]) + ')</div>'
        + '<div class="s">' + pv.same + '/' + TH.length + '개 동시 '
        + (MKT[pv.i] < 0 ? '유출' : '유입') + ' · ' + eok(MKT[pv.i]) + '</div>';
    setHtml('fmap-mkt',
      '<div class="fmap-mk"><div class="k">' + DATES.length + '거래일 누적</div>'
      + '<div class="v ' + (cum >= 0 ? 'up' : 'dn') + '">' + eok(cum) + '</div>'
      + '<div class="s">전 테마 합계</div></div>'
      + '<div class="fmap-mk"><div class="k">가장 많은 테마가 한꺼번에 움직인 날</div>' + pvCell + '</div>'
      + '<div class="fmap-mk"><div class="k">유입 / 유출 테마</div>'
      + '<div class="v">' + inn + ' <span style="color:var(--muted);font-size:13px">/ '
      + (TH.length - inn) + '</span></div>'
      + '<div class="s">' + DATES.length + '일 누적 기준</div></div>');
  }

  /* ── 좌: 발산 바 리스트 ── */
  function renderList() {
    // 막대 기준값은 정렬과 무관하게 항상 전체 최대치 — 정렬마다 최대치를 다시 잡으면
    // 같은 테마의 막대 길이가 들쭉날쭉해져 비교가 깨진다.
    var mx = Math.max.apply(null, TH.map(function (t) { return Math.abs(t.flow_eok); }));
    // 선택 상태는 DOM이 아니라 selected 변수가 정본이다 — 다시 그려도 그대로 살아남고,
    // 정렬만 바뀌고 우측 상세는 유지된다.
    var sel = selected;
    setHtml('fmap-list', TH.slice().sort(SORTS[sortKey]).map(function (t) {
      var pos = t.flow_eok >= 0;
      // 회전율 정렬일 때만 배수를 이름 옆에 붙인다 — 왜 이 순서인지 근거를 보여준다.
      var sub = sortKey === 'churn' ? ' <em>' + churn(t).toFixed(1) + '배</em>' : '';
      return '<div class="fmap-r' + (t.theme === sel ? ' on' : '') + '" data-th="' + esc(t.theme)
        + '" title="' + esc(t.theme) + ' · ETF ' + t.etf_count + '개">'
        + '<span class="fmap-nm">' + esc(t.theme) + sub + '</span>'
        + '<span class="fmap-bw"><i class="fmap-ax"></i>'
        + '<i class="fmap-bar ' + (pos ? 'p' : 'm') + '" style="width:'
        + barPct(t.flow_eok, mx) + '%"></i></span>'
        + '<span class="fmap-v ' + (pos ? 'up' : 'dn') + '">' + eok(t.flow_eok) + '</span></div>';
    }).join(''));
  }

  /* ── 우: 상세 ── */
  function etfGroup(title, list, cls) {
    if (!list.length) return '';
    var sum = list.reduce(function (s, e) { return s + e.flow; }, 0);
    return '<div class="fmap-gh ' + cls + '"><i class="dot"></i>' + title + ' ' + list.length + '개'
      + '<span class="sum">' + eok(sum) + '</span></div>'
      + list.map(function (e) {
        var emx = Math.max.apply(null, e.daily.map(Math.abs)) || 1;   // 자기 기준 정규화
        var sp = e.daily.map(function (v) {
          var hh = Math.max(1, Math.abs(v) / emx * 7);
          var bg = v >= 0 ? 'rgba(224,49,49,.85)' : 'rgba(39,117,237,.85)';
          return '<div class="c"><div class="h u">'
            + (v >= 0 ? '<i style="height:' + hh + 'px;background:' + bg + '"></i>' : '')
            + '</div><div class="z"></div><div class="h">'
            + (v < 0 ? '<i style="height:' + hh + 'px;background:' + bg + '"></i>' : '')
            + '</div></div>';
        }).join('');
        // 덩치 대비 % — 큰 ETF의 큰 금액보다 작은 ETF가 덩치 대비 크게 움직인 게 더 드문 신호.
        // 10% 미만은 노이즈라 뱃지를 달지 않는다.
        var pl = (e.pct != null && Math.abs(e.pct) >= 10)
          ? '<span class="fmap-pill ' + (e.pct > 0 ? 'hot' : 'cold') + '">'
            + (e.pct > 0 ? '+' : '−') + Math.abs(Math.round(e.pct)) + '%</span>' : '';
        return '<div class="fmap-er"><span class="en">' + esc(e.name) + '</span>'
          + '<span class="eaum">AUM ' + amt(e.aum) + pl + '</span>'
          + '<span class="fmap-sp">' + sp + '</span>'
          + '<span class="efl ' + (e.flow >= 0 ? 'up' : 'dn') + '">' + eok(e.flow) + '</span></div>';
      }).join('');
  }

  function detail(theme) {
    var t = TH.filter(function (x) { return x.theme === theme; })[0];
    if (!t) return;
    selected = theme;
    var ch = Math.abs(t.flow_eok) ? t.gross_eok / Math.abs(t.flow_eok) : 0;
    var shown = t.etfs.reduce(function (s, e) { return s + Math.abs(e.flow); }, 0);
    var conc = t.gross_eok ? Math.max(0, Math.min(100, Math.round(shown / t.gross_eok * 100))) : 0;

    var h = '<div class="fmap-dh"><div class="r1"><span class="fmap-tt">' + esc(t.theme) + '</span>'
      + '<span class="fmap-amt ' + (t.flow_eok >= 0 ? 'up' : 'dn') + '">' + eok(t.flow_eok) + '</span></div>'
      + '<div class="fmap-kpis">'
      + '<div class="fmap-kpi"><div class="k">오간 돈</div><div class="v">' + amt(t.gross_eok) + '</div></div>'
      + '<div class="fmap-kpi"><div class="k">회전율</div><div class="v">' + ch.toFixed(1) + '배</div></div>'
      + '<div class="fmap-kpi"><div class="k">ETF</div><div class="v">' + t.etf_count + '개</div></div>'
      + '</div></div><div class="fmap-pad" style="padding:12px 16px 14px">';

    var dmx = Math.max.apply(null, t.daily.map(Math.abs)) || 1;
    h += '<div class="fmap-st">일별 순유입 <span class="n">막대 합 = 위 누적값</span></div>'
      + '<div class="fmap-days">';
    t.daily.forEach(function (v, i) {
      var pos = v >= 0, ht = Math.max(3, Math.round(Math.abs(v) / dmx * (pos ? 50 : 34)));
      // 시장 파도를 기준선으로 먼저 세워야 "그 파도 대비 무엇이 버텼는지"라는 신호가 남는다.
      var opp = (MKT[i] > 0 && v < 0) || (MKT[i] < 0 && v > 0);
      h += '<div class="fmap-dy"><div class="u">'
        + (pos ? '<span class="v up">' + eok(v) + '</span><i class="b p" style="height:' + ht + 'px"></i>' : '')
        + '</div><div class="z"></div><div class="d">'
        + (pos ? '' : '<i class="b m" style="height:' + ht + 'px"></i><span class="v dn">' + eok(v) + '</span>')
        + '</div><span class="lb">' + md(DATES[i]) + '(' + wd(DATES[i]) + ')<br>'
        + '<span class="q ' + (opp ? 'opp' : 'same') + '">' + (opp ? '시장 반대' : '시장 동조')
        + '</span></span></div>';
    });
    h += '</div>';

    h += etfGroup('유입', t.etfs.filter(function (e) { return e.flow >= 0; }), 'i')
      + etfGroup('유출', t.etfs.filter(function (e) { return e.flow < 0; }), 'o');

    // 절단은 숨기지 않는다 — 목록에서 빠졌을 뿐 위 누적값에는 포함돼 있다(운영규칙 0).
    if (t.rest_n) {
      h += '<div class="fmap-rest">그 외 <b>' + t.rest_n + '개</b> 합계 <b>' + eok(t.rest_flow)
        + '</b> — 금액이 작아 목록에선 생략했지만 위 누적값에는 포함돼 있어요.</div>';
    }
    h += '<div class="fmap-conc">위 <b>' + t.etfs.length + '개</b>가 이 테마에서 오간 돈의 <b>'
      + conc + '%</b>를 차지해요. <span style="color:var(--muted)">%는 AUM 대비 증감</span></div>';

    setHtml('fmap-detail', h + '</div>');

    var rows = document.querySelectorAll('.fmap-r');
    for (var i = 0; i < rows.length; i++) {
      rows[i].classList.toggle('on', rows[i].getAttribute('data-th') === theme);
    }
  }

  function setSort(key) {
    if (!SORTS[key]) return;
    sortKey = key;
    var tabs = $('fmap-sorttabs');
    if (tabs && tabs.querySelectorAll) {
      var as = tabs.querySelectorAll('a');
      for (var i = 0; i < as.length; i++) {
        as[i].classList.toggle('on', as[i].getAttribute('data-sort') === key);
      }
    }
    renderList();   // 선택된 테마는 renderList가 읽어 유지한다 — 정렬만 바뀌고 상세는 그대로
  }

  function showEmpty(msg) {
    var c = $('fmap-content'), e = $('fmap-empty');
    if (c) c.style.display = 'none';
    if (e) { e.style.display = ''; e.textContent = msg; }
  }

  function render(data) {
    DATA = data || {};
    TH = (DATA.themes || []).slice().sort(SORTS.size);
    DATES = DATA.dates || [];
    MKT = DATA.market_daily || [];
    if (!TH.length || !DATES.length) {
      showEmpty('자금 지도 데이터를 준비 중이에요. 평일 18:00에 갱신돼요.');
      return;
    }
    var c = $('fmap-content'), e = $('fmap-empty');
    if (c) c.style.display = '';
    if (e) e.style.display = 'none';

    setText('fmap-sub', md(DATES[0]) + '~' + md(DATES[DATES.length - 1]) + ' 누적 · '
      + 'ETF 설정/환매 실측 · ' + DATES.length + '거래일');
    setText('fmap-win', '· ' + md(DATES[0]) + '~' + md(DATES[DATES.length - 1]) + ' 누적');
    setText('fmap-legn', TH.length + '개 전부 · 막대 길이는 실제 비례');

    // 오래된 데이터도 감추지 않고 그대로 보여주되 언제 것인지 명시한다 — 사용자가 직접 눌러
    // 들어온 화면이라, 날짜를 밝히고 보여주는 편이 통째로 숨기는 것보다 정직하다.
    var sd = staleDays(DATA.source_generated_at || DATA.generated_at);
    var stale = $('fmap-stale');
    if (stale) {
      if (sd != null && sd >= 5) {
        stale.style.display = '';
        stale.textContent = '마지막 갱신이 ' + sd + '일 전(' + String(DATA.source_generated_at || '').slice(0, 10)
          + ')이에요. 평일 18:00에 갱신돼요.';
      } else {
        stale.style.display = 'none';
      }
    }

    // 빈 상태를 두지 않는다 — 규모 1위 테마를 먼저 편다.
    // selected를 renderList 앞에서 정해야 첫 렌더부터 선택 행에 음영이 들어간다.
    selected = TH[0].theme;
    renderMarket();
    renderList();
    detail(selected);
  }

  function boot() {
    if (!$('flow-map')) return;   // 이 화면이 없는 페이지에서는 아무것도 하지 않는다
    var tabs = $('fmap-sorttabs');
    if (tabs) {
      tabs.addEventListener('click', function (ev) {
        var a = ev.target && ev.target.closest ? ev.target.closest('a[data-sort]') : null;
        if (a) setSort(a.getAttribute('data-sort'));
      });
    }
    // 리스트는 매번 innerHTML로 다시 그리므로 리스너는 개별 행이 아니라 컨테이너에 건다.
    var list = $('fmap-list');
    if (list) {
      list.addEventListener('click', function (ev) {
        var el = ev.target && ev.target.closest ? ev.target.closest('.fmap-r') : null;
        if (el) detail(el.getAttribute('data-th'));
      });
    }
    window.fetch('/data/flow-map.json', { cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (d) render(d);
        else showEmpty('자금 지도 데이터를 불러오지 못했어요. 잠시 뒤 다시 시도해 주세요.');
      })
      .catch(function () {
        showEmpty('자금 지도 데이터를 불러오지 못했어요. 잠시 뒤 다시 시도해 주세요.');
      });
  }

  window.__flowMap = {
    esc: esc, eok: eok, amt: amt, md: md, wd: wd,
    churn: churn, SORTS: SORTS, barPct: barPct, pivot: pivot, staleDays: staleDays,
    render: render, select: detail, setSort: setSort
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
