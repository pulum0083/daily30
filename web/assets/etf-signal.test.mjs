// stocks-home.js의 ETF 요약 블록 포맷터 회귀 테스트 — node:vm에서 실제 프로덕션 파일 로드
//
// 순수 함수를 테스트 파일에 복제하면 사본이 원본과 어긋나므로(SERVICE_RULES §20류),
// 실제 파일을 최소 DOM 스텁과 함께 실행하고 window.__etfSignal로 꺼내 검증한다.
// stocks-home.test.mjs·ds-subnav.test.mjs와 같은 패턴.
//
// 실행: node --test web/assets/etf-signal.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createContext, runInContext } from 'node:vm';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const noop = () => {};

// appendChild가 실제로 children에 쌓이고 parentElement를 연결해야 renderEtfSignal의 DOM 출력
// (레버리지 행 숨김·극단값 컨테이너 비움)을 진짜로 검증할 수 있다 — 순수 포맷터만 볼 땐 no-op으로
// 충분했지만, DOM 결과 자체를 보려면 최소한의 실제 트리 동작이 필요하다(코드리뷰 재검토).
function mkEl() {
  const e = {
    classList:{add:noop,remove:noop,toggle:noop,contains:()=>false},
    dataset:{}, style:{}, children:[], innerHTML:'', textContent:'', hidden:false,
    parentElement:null, parentNode:null,
    addEventListener:noop, removeEventListener:noop,
    appendChild(child){ this.children.push(child); child.parentElement = this; child.parentNode = this; return child; },
    insertBefore:noop,
    setAttribute:noop, getAttribute:()=>null, remove:noop, focus:noop,
    closest:()=>null, contains:()=>false,
    getBoundingClientRect:()=>({top:0,left:0,width:0,height:0}),
    querySelector:()=>null, querySelectorAll:()=>[],
  };
  return e;
}

function load() {
  const win = {
    location:{pathname:'/stocks/', hash:'', href:'https://x/stocks/'},
    addEventListener:noop, removeEventListener:noop,
    setInterval:()=>0, clearInterval:noop, setTimeout:()=>0, clearTimeout:noop,
    fetch:()=>Promise.reject(new Error('no network in test')),
    matchMedia:()=>({matches:false, addEventListener:noop}),
    sessionStorage:{getItem:()=>null, setItem:noop},
    localStorage:{getItem:()=>null, setItem:noop},
    Intl, Date, Math, JSON, console:{log:noop, warn:noop, error:noop},
    navigator:{userAgent:'node'},
    history:{pushState:noop, replaceState:noop},
    document:{
      readyState:'complete',
      getElementById:()=>mkEl(), querySelector:()=>mkEl(), querySelectorAll:()=>[],
      createElement:()=>mkEl(), addEventListener:noop,
      body:mkEl(), documentElement:mkEl(), head:mkEl(),
    },
  };
  win.window = win;
  const ctx = createContext(win);
  try { runInContext(readFileSync(join(HERE,'stocks-home.js'),'utf8'), ctx); } catch (e) { /* 로드 시점 DOM 접근 실패는 무시 — 훅만 필요 */ }
  return win.__etfSignal;
}

// renderEtfSignal이 실제로 만지는 ETF 블록 DOM을 index.html 마크업 그대로 최소 재현한다.
// id별로 항상 같은 엘리먼트를 돌려줘야(재조회 시 새 스텁이 아니라) 렌더 후 상태를 밖에서 확인할 수 있다.
// 특히 etfsig-inv·etfsig-lev는 각각 KPI 행(부모 div)에 미리 넣어둬 lev.parentElement가
// 실제 마크업처럼 그 행을 가리키게 한다 — 코드가 lev.parentElement.style로 행을 숨기기 때문이다.
function loadForRender() {
  const els = new Map();
  const put = (id, el) => { els.set(id, el); return el; };

  const invVal = put('etfsig-inv', mkEl());
  const invRow = mkEl(); invRow.appendChild(invVal);
  const levVal = put('etfsig-lev', mkEl());
  const levRow = mkEl(); levRow.appendChild(levVal);

  ['etf-signal','etfsig-asof','etfsig-title','etfsig-body','etfsig-dn-amt','etfsig-up-amt',
   'etfsig-dn-pct','etfsig-up-pct','etfsig-bar-dn','etfsig-ext'].forEach((id) => put(id, mkEl()));

  const win = {
    location:{pathname:'/stocks/', hash:'', href:'https://x/stocks/'},
    addEventListener:noop, removeEventListener:noop,
    setInterval:()=>0, clearInterval:noop, setTimeout:()=>0, clearTimeout:noop,
    fetch:()=>Promise.reject(new Error('no network in test')),
    matchMedia:()=>({matches:false, addEventListener:noop}),
    sessionStorage:{getItem:()=>null, setItem:noop},
    localStorage:{getItem:()=>null, setItem:noop},
    Intl, Date, Math, JSON, console:{log:noop, warn:noop, error:noop},
    navigator:{userAgent:'node'},
    history:{pushState:noop, replaceState:noop},
    document:{
      readyState:'complete',
      getElementById:(id) => { if(!els.has(id)) els.set(id, mkEl()); return els.get(id); },
      querySelector:()=>mkEl(), querySelectorAll:()=>[],
      createElement:()=>mkEl(), addEventListener:noop,
      body:mkEl(), documentElement:mkEl(), head:mkEl(),
    },
  };
  win.window = win;
  const ctx = createContext(win);
  try { runInContext(readFileSync(join(HERE,'stocks-home.js'),'utf8'), ctx); } catch (e) { /* 로드 시점 DOM 접근 실패는 무시 — 훅만 필요 */ }
  return { hook: win.__etfSignal, els, invRow, levRow };
}

// 실제 폴링 성공 시 나올 수 있는 완전한 정상 데이터 — DOM 테스트용 공통 픽스처.
const REAL_ETF = {
  lead:{title:'엇갈린 ETF 신호', body:'KODEX 인버스 거래량이 KODEX 200의 <b>52배</b>예요.'},
  betting:{downAmt:791944, upAmt:689872, downRatio:53, upRatio:47, invVolMultiple:52, levPct:-5.18},
  sector:[{label:'바이오', pct:7.04}, {label:'반도체', pct:-2.55}],
};
const REAL_ASOF = {label:'8/4(화)'};

test('백만원을 조·억 표기로 바꾼다', () => {
  const { fmtEok } = load();
  assert.equal(fmtEok(1985526), '1조 9,855억');   // 하락 베팅 실측값
  assert.equal(fmtEok(1992279), '1조 9,923억');   // 상승 베팅 실측값
  assert.equal(fmtEok(356700), '3,567억');
  assert.equal(fmtEok(1000000), '1조');           // 나머지가 0이면 '억'을 붙이지 않는다
});

test('섹터 ETF 최고·최저를 등락률로 고른다', () => {
  const { pickExtremes } = load();
  const rows = [
    {label:'바이오', pct:4.59}, {label:'건설', pct:2.87},
    {label:'반도체', pct:-6.92}, {label:'IT', pct:-7.06},
  ];
  const r = pickExtremes(rows);
  assert.equal(r.top.label, '바이오');
  assert.equal(r.bottom.label, 'IT');
});

test('섹터 배열이 비어 있으면 극단값이 없다', () => {
  const { pickExtremes } = load();
  assert.equal(pickExtremes([]), null);
  assert.equal(pickExtremes(null), null);
});

test('섹터가 1개뿐이면 최고=최저로 같은 종목이 중복 표시되지 않도록 극단값을 숨긴다 (코드리뷰 Minor)', () => {
  const { pickExtremes } = load();
  assert.equal(pickExtremes([{label:'바이오', pct:4.59}]), null);
});

// 정상 데이터 — 폴링이 실제로 성공했을 때 나올 수 있는 완전한 모양(참고: api/_signals-core.mjs etfBettingFlow()).
const REAL_BETTING = {downAmt:791944, upAmt:689872, downRatio:53, upRatio:47, invVolMultiple:52, levPct:-5.18};

test('lead·betting이 없으면 블록을 숨긴다 — 빈 껍데기를 노출하지 않는다(§0)', () => {
  const { shouldShowEtfSignal } = load();
  assert.equal(shouldShowEtfSignal({lead:{title:'t',body:'b'}, betting:REAL_BETTING}), true);
  assert.equal(shouldShowEtfSignal({betting:REAL_BETTING}), false);
  assert.equal(shouldShowEtfSignal({lead:{title:'t',body:'b'}}), false);
  assert.equal(shouldShowEtfSignal(null), false);
  assert.equal(shouldShowEtfSignal(undefined), false);
});

test('ETF 폴링이 전종목 실패해도 etfBettingFlow()는 완전한 모양의 0값 객체를 돌려준다 — ' +
     '그걸 "조용한 평온한 하루"로 보여주지 않고 블록을 숨긴다 (코드리뷰 Critical)', () => {
  const { shouldShowEtfSignal } = load();
  // api/_signals-core.mjs의 etfBettingFlow()가 byCode={}(전종목 폴링 실패)일 때 실제로 반환하는 모양 그대로.
  const degraded = {downAmt:0, upAmt:0, downRatio:0, upRatio:100, invVolMultiple:0, levPct:null};
  assert.equal(shouldShowEtfSignal({lead:{title:'ETF 시황', body:'오늘 ETF 흐름을 아래에서 나눠 봐요.'}, betting:degraded}), false);
});

test('betting 숫자 필드가 진짜 숫자가 아니면(null·undefined·문자열) 블록을 숨긴다', () => {
  const { shouldShowEtfSignal } = load();
  const base = {lead:{title:'t', body:'b'}};
  assert.equal(shouldShowEtfSignal({...base, betting:{...REAL_BETTING, downAmt:null}}), false);
  assert.equal(shouldShowEtfSignal({...base, betting:{...REAL_BETTING, upAmt:undefined}}), false);
  assert.equal(shouldShowEtfSignal({...base, betting:{...REAL_BETTING, downRatio:'53'}}), false);
  assert.equal(shouldShowEtfSignal({...base, betting:{...REAL_BETTING, invVolMultiple:NaN}}), false);
});

test('levPct가 숫자가 아니면(null·undefined) "+0.00%"를 지어내지 않는다 — 포맷·색 모두 반환하지 않는다 (코드리뷰 Critical)', () => {
  const { pctFmt, pctCls } = load();
  assert.equal(pctFmt(null), null);
  assert.equal(pctFmt(undefined), null);
  assert.equal(pctCls(null), '');
  assert.equal(pctCls(undefined), '');
  // 대조군 — 실제 0.00%(진짜 측정된 보합)는 정상 포맷된다. null과 혼동하면 안 된다.
  assert.equal(pctFmt(0), '+0.00%');
  assert.equal(pctCls(0), 'up');
  assert.equal(pctFmt(-5.18), '−5.18%');
  assert.equal(pctCls(-5.18), 'dn');
});

test('lead.body sanitizer는 <b>·</b>만 통과시키고 그 외 태그·속성은 제거한다 (코드리뷰 Important)', () => {
  const { sanitizeBodyHtml } = load();
  // 오늘 실제로 나오는 형태 — 그대로 통과.
  assert.equal(
    sanitizeBodyHtml('KODEX 인버스 거래량이 KODEX 200의 <b>52배</b>예요.'),
    'KODEX 인버스 거래량이 KODEX 200의 <b>52배</b>예요.'
  );
  // 속성이 붙은 <b>(예: onmouseover)까지 그대로 통과시키면 안 된다 — 여는 태그는 제거된다.
  // 짝 잃은 </b>가 남지만 HTML 파서는 대응하는 여는 태그 없는 종료 태그를 그냥 무시한다 —
  // 실행되거나 화면에 글자로 보이지 않으므로 무해하다.
  assert.equal(sanitizeBodyHtml('<b onmouseover="evil()">50%</b>'), '50%</b>');
  // <script>·<img onerror> 등 다른 태그는 태그만 제거되고 텍스트는 남는다(실행되지 않음).
  assert.equal(sanitizeBodyHtml('<script>alert(1)</script>안전'), 'alert(1)안전');
  assert.equal(sanitizeBodyHtml('<img src=x onerror=alert(1)>본문'), '본문');
  assert.equal(sanitizeBodyHtml(null), '');
  assert.equal(sanitizeBodyHtml(undefined), '');
});

test('renderEtfSignal(DOM): 정상 데이터면 블록을 보여주고 레버리지·극단값 행을 모두 채운다 (회귀 대조군)', () => {
  const { hook, els, invRow, levRow } = loadForRender();
  hook.renderEtfSignal(REAL_ETF, REAL_ASOF);
  assert.equal(els.get('etf-signal').style.display, '');
  assert.equal(els.get('etfsig-lev').textContent, '−5.18%');
  assert.equal(els.get('etfsig-lev').className, 'v num dn');
  assert.equal(levRow.style.display, '');           // 레버리지 행이 보인다
  assert.equal(invRow.style.gridColumn, '');         // 정상일 땐 1fr 1fr 그대로 — 폭을 넓히지 않는다
  assert.equal(els.get('etfsig-ext').children.length, 2);   // 최고·최저 두 행
});

test('renderEtfSignal(DOM): levPct가 숫자가 아니면 레버리지 행 자체를 숨긴다 — "+0.00%"·"null%"로 남지 않는다 (코드리뷰 재검토 Critical 추적)', () => {
  const { hook, els, invRow, levRow } = loadForRender();
  const etf = { ...REAL_ETF, betting:{...REAL_ETF.betting, levPct:null} };
  hook.renderEtfSignal(etf, REAL_ASOF);
  assert.equal(els.get('etf-signal').style.display, '');   // 나머지 데이터는 정상이라 블록 자체는 보인다
  assert.equal(els.get('etfsig-lev').textContent, '');     // "+0.00%"·"null%" 둘 다 아님 — 빈 문자열
  assert.equal(levRow.style.display, 'none');               // 행 자체가 숨는다(display:none)
});

test('renderEtfSignal(DOM): 레버리지 행이 숨으면 옆 칸(인버스 거래량)이 전체 폭으로 넓어져 빈 격자칸을 남기지 않는다 (코드리뷰 재검토 gap 수정)', () => {
  const { hook, invRow } = loadForRender();
  const etf = { ...REAL_ETF, betting:{...REAL_ETF.betting, levPct:undefined} };
  hook.renderEtfSignal(etf, REAL_ASOF);
  assert.equal(invRow.style.gridColumn, '1 / -1');
});

test('renderEtfSignal(DOM): 섹터가 1개면 극단값 컨테이너를 비운다 — 반쪽짜리 단일 행을 남기지 않는다 (코드리뷰 재검토 Minor 추적)', () => {
  const { hook, els } = loadForRender();
  const etf = { ...REAL_ETF, sector:[{label:'바이오', pct:7.04}] };
  hook.renderEtfSignal(etf, REAL_ASOF);
  assert.equal(els.get('etfsig-ext').children.length, 0);
});

test('renderEtfSignal(DOM): ETF 폴링 전종목 실패(§0 Critical 열화 데이터)면 블록 자체를 display:none으로 숨긴다', () => {
  const { hook, els } = loadForRender();
  const degraded = { lead:{title:'ETF 시황', body:'오늘 ETF 흐름을 아래에서 나눠 봐요.'},
    betting:{downAmt:0, upAmt:0, downRatio:0, upRatio:100, invVolMultiple:0, levPct:null} };
  hook.renderEtfSignal(degraded, REAL_ASOF);
  assert.equal(els.get('etf-signal').style.display, 'none');
});
