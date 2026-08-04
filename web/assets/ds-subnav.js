// 종목 시그널 서브 네비게이션 — 탭 정의·현재 탭 판정·렌더를 한 곳에 두는 공용 스크립트.
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

  // 점등하는 탭은 이번 범위인 4개뿐이다. 테마·일정은 각 기능이 완성될 때 그 작업에서
  // 주석을 푼다 — 빈 탭을 먼저 만들지 않는다.
  // screen이 있으면 /stocks/ 내부 화면, 없으면 독립 페이지다. 이 한 필드가 클릭 동작을 가른다.
  var TABS = [
    { id: 'home',    label: '전체',     href: '/stocks/',             screen: 'home' },
    { id: 'signals', label: '특이신호', href: '/stocks/#signals-all', screen: 'signals-all' },
    // { id: 'themes',   label: '테마', href: '/themes/' },    // 테마 타임라인 완성 시 점등
    { id: 'sector',  label: '섹터',     href: '/stocks/#sector',      screen: 'sector' },
    { id: 'etf',     label: 'ETF',      href: '/stocks/#etf-rank',    screen: 'etf-rank' },
    // { id: 'calendar', label: '일정', href: '/calendar/' },  // 실적 캘린더 완성 시 점등
  ];

  // 해시 → 탭 id. 여기 없는 해시(#passive·#ranking 등)는 '전체'로 떨어진다 — 아무 탭도
  // 활성이 아닌 것보다 시그널 영역 안에 있다는 사실을 유지하는 쪽이 방향 감각에 낫다.
  var HASH_TO_TAB = { 'signals-all': 'signals', 'sector': 'sector', 'etf-rank': 'etf' };

  var STOCKS_HOME_RE = /^\/stocks\/?(index\.html)?$/;

  function isStocksHome(pathname) {
    return STOCKS_HOME_RE.test(pathname || '');
  }

  /** 현재 탭 판정. DOM·전역 상태를 안 읽는 순수 함수라 테스트가 쉽다. */
  function resolveActiveTab(pathname, hash) {
    var id = null;
    if (/^\/themes(\/|$)/.test(pathname)) id = 'themes';
    else if (/^\/calendar(\/|$)/.test(pathname)) id = 'calendar';
    else if (isStocksHome(pathname)) id = HASH_TO_TAB[(hash || '').replace(/^#/, '')] || 'home';
    if (!id) return null;
    // 정의에 없는 탭으로 해석되면 null — 아직 점등하지 않은 테마·일정 경로로 들어와도 깨지지 않는다.
    for (var i = 0; i < TABS.length; i++) if (TABS[i].id === id) return id;
    return null;
  }

  window.__dsSubnav = { TABS: TABS, resolveActiveTab: resolveActiveTab };
})();
