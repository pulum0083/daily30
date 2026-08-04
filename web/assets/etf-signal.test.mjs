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

test('lead·betting이 없으면 블록을 숨긴다 — 빈 껍데기를 노출하지 않는다(§0)', () => {
  const { shouldShowEtfSignal } = load();
  assert.equal(shouldShowEtfSignal({lead:{title:'t',body:'b'}, betting:{downRatio:50,upRatio:50}}), true);
  assert.equal(shouldShowEtfSignal({betting:{downRatio:50,upRatio:50}}), false);
  assert.equal(shouldShowEtfSignal({lead:{title:'t',body:'b'}}), false);
  assert.equal(shouldShowEtfSignal(null), false);
  assert.equal(shouldShowEtfSignal(undefined), false);
});
