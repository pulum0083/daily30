// 종목 시그널 서브 네비게이션 — 탭 정의·현재 탭 판정을 한 곳에 두는 공용 스크립트
// (렌더·클릭 가로채기는 Task 3에서 이 파일에 추가된다).
//
// 왜 공용 파일인가
//   탭 바는 최종적으로 /stocks/·/themes/·/calendar/ 세 곳에 똑같이 떠야 한다. 그런데
//   /stocks/index.html은 손으로 쓴 정적 HTML이고 신규 두 페이지는 generate_html.py가 만든다.
//   마크업을 양쪽에 복사하면 한쪽만 고쳐지고 다른 쪽이 방치돼도 겉보기엔 둘 다 정상으로
//   보인다(SERVICE_RULES §30 이중 구현). 각 페이지엔 빈 껍데기만 두고 정의는 여기 한 곳에 둔다.
//
// 이 컴포넌트는 없어도 기존 기능이 전부 동작해야 한다 — 홈 블록의 "전체 보기 →" 링크가
// 그대로 살아 있으므로 탭 바는 부가 경로다.
(function () {
  'use strict';

  // 이 파일이 같은 페이지에 두 번 로드돼도(예: 템플릿 중복 include) 초기화는 한 번만 한다.
  // 가드 없이 두 번 실행되면 #ds-subnav의 click 리스너·window의 hashchange·popstate 리스너가
  // 매번 새로 쌓여, 탭 클릭 한 번에 go()가 여러 번 불려 history.pushState도 여러 번 쌓인다
  // (뒤로가기 한 번으로 안 돌아옴). window.dsSubnavSync·window.__dsSubnav는 첫 실행에서
  // 이미 정상 동작하는 클로저로 설정돼 있으므로, 두 번째 실행은 통째로 건너뛰어도 안전하다.
  if (window.__dsSubnavInited) return;
  window.__dsSubnavInited = true;

  // 점등하는 탭은 이번 범위인 5개뿐이다. 테마·일정은 각 기능이 완성될 때 그 작업에서
  // 주석을 푼다 — 빈 탭을 먼저 만들지 않는다.
  // screen이 있으면 /stocks/ 내부 화면, 없으면 독립 페이지다. Task 3의 클릭 동작이 이
  // 필드로 화면 전환 여부를 가른다.
  var TABS = [
    { id: 'home',    label: '전체',     href: '/stocks/',             screen: 'home' },
    { id: 'signals', label: '특이신호', href: '/stocks/#signals-all', screen: 'signals-all' },
    // { id: 'themes',   label: '테마', href: '/themes/' },    // 테마 타임라인 완성 시 점등
    { id: 'sector',  label: '섹터',     href: '/stocks/#sector',      screen: 'sector' },
    { id: 'flow',    label: '자금 지도', href: '/stocks/#flow-map',    screen: 'flow-map' },
    { id: 'etf',     label: 'ETF',      href: '/stocks/#etf-rank',    screen: 'etf-rank' },
    // { id: 'calendar', label: '일정', href: '/calendar/' },  // 실적 캘린더 완성 시 점등
  ];

  var STOCKS_HOME_RE = /^\/stocks\/?(index\.html)?$/;

  function isStocksHome(pathname) {
    return STOCKS_HOME_RE.test(pathname || '');
  }

  /** 해시(소문자) → 탭 id. TABS를 손으로 유지하는 두 번째 표로 옮겨 적지 않고, 매 호출마다
      TABS를 그대로 훑어서 만든다 — 별도 표를 두면 TABS에 탭을 추가할 때 그 표만 깜빡하고
      갱신 안 해도 아무 에러 없이 조용히 어긋난다(§30, 이 파일이 애초에 막으려는 사고).
      캐시하지 않으므로 TABS에 탭 하나를 추가하는 것만으로 해시 판정도 즉시 따라온다 —
      추가 배선이 필요 없다. */
  function hashToTabId(hash) {
    for (var i = 0; i < TABS.length; i++) {
      if (TABS[i].screen && TABS[i].screen.toLowerCase() === hash) return TABS[i].id;
    }
    return null;
  }

  /** 현재 탭 판정. DOM·전역 상태를 안 읽는 순수 함수라 테스트가 쉽다.
      해시는 대소문자를 구분하지 않는다 — 이 파일이 만드는 href는 전부 소문자지만, 손으로
      친 링크·옛 북마크 등 다른 출처의 해시가 다른 대소문자로 들어와도 같은 탭으로 판정한다. */
  function resolveActiveTab(pathname, hash) {
    var id = null;
    if (/^\/themes(\/|$)/.test(pathname)) id = 'themes';
    else if (/^\/calendar(\/|$)/.test(pathname)) id = 'calendar';
    else if (isStocksHome(pathname)) id = hashToTabId((hash || '').replace(/^#/, '').toLowerCase()) || 'home';
    if (!id) return null;
    // 정의에 없는 탭으로 해석되면 null — 아직 점등하지 않은 테마·일정 경로로 들어와도 깨지지 않는다.
    for (var i = 0; i < TABS.length; i++) if (TABS[i].id === id) return id;
    return null;
  }

  function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function tabById(id) {
    for (var i = 0; i < TABS.length; i++) if (TABS[i].id === id) return TABS[i];
    return null;
  }

  function host() {
    return document.getElementById('ds-subnav');
  }

  /** 현재 위치로 강조를 다시 계산해 반영한다. 껍데기가 없는 페이지에서는 조용히 아무것도 안 한다. */
  function render() {
    var el = host();
    if (!el) return;
    var active = resolveActiveTab(location.pathname, location.hash);
    el.innerHTML = TABS.map(function (t) {
      var on = t.id === active;
      return '<a class="ds-subnav__tab' + (on ? ' is-active' : '') + '"'
        + ' href="' + esc(t.href) + '" data-tab="' + esc(t.id) + '"'
        + (on ? ' aria-current="page"' : '') + '>' + esc(t.label) + '</a>';
    }).join('');
  }

  function onClick(e) {
    var a = e.target && e.target.closest ? e.target.closest('.ds-subnav__tab') : null;
    if (!a) return;
    var tab = tabById(a.getAttribute('data-tab'));
    // 독립 페이지이거나, /stocks/가 아니거나, go()가 없는 페이지면 기본 링크 이동에 맡긴다.
    if (!tab || !tab.screen) return;
    if (!isStocksHome(location.pathname)) return;
    if (typeof window.go !== 'function') return;
    e.preventDefault();
    window.go(tab.screen);
    render();
  }

  function init() {
    var el = host();
    if (el) el.addEventListener('click', onClick);
    render();
  }

  window.dsSubnavSync = render;
  window.__dsSubnav = { TABS: TABS, resolveActiveTab: resolveActiveTab };

  window.addEventListener('hashchange', render);   // 주소창 직접 수정·외부 앵커 링크
  window.addEventListener('popstate', render);     // 뒤로/앞으로 가기

  // defer 스크립트는 DOMContentLoaded 전에 실행되지만, 다른 로드 경로도 견디게 둔다.
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
