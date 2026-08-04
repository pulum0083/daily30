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

function mkEl() {
  const e = {
    classList:{add:noop,remove:noop,toggle:noop,contains:()=>false},
    dataset:{}, style:{}, children:[], innerHTML:'', textContent:'', hidden:false,
    addEventListener:noop, removeEventListener:noop, appendChild:noop, insertBefore:noop,
    setAttribute:noop, getAttribute:()=>null, remove:noop, focus:noop,
    closest:()=>null, contains:()=>false,
    getBoundingClientRect:()=>({top:0,left:0,width:0,height:0}),
    querySelector:()=>null, querySelectorAll:()=>[],
  };
  e.parentNode = {insertBefore:noop, removeChild:noop, appendChild:noop};
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
