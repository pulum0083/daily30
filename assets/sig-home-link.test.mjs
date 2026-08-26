// 특이 신호 행의 존재-게이트 회귀 테스트 — 상세 페이지가 있는 종목만 링크한다(§36)
//
// 신호 스캔 유니버스는 46종목이고 상세 페이지는 3종목뿐이다. 전부 <a>로 그리면 대부분의
// 클릭이 막다른 길이 되므로, 페이지가 없는 종목은 링크가 아닌 <div>로 그리고 화살표도 뺀다.
// sector-screen.test.mjs와 같은 node:vm 패턴 — 프로덕션 파일을 그대로 실행해 훅을 꺼낸다.
//
// 실행: node --test web/assets/sig-home-link.test.mjs
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
  try { runInContext(readFileSync(join(HERE,'stocks-home.js'),'utf8'), ctx); } catch { /* 로드 시 DOM 접근 실패 무시 — 훅만 필요 */ }
  return win.__sigHome;
}

const sig = (code) => ({code, name:'테스트', sector:'반도체', pct:3.2, dir:'up', badges:['거래량 급증'], why:'왜'});

test('상세 페이지가 있는 종목은 링크로 그린다', () => {
  const { sigItemHtml } = load();
  for (const code of ['005930', '000660', '005380']) {
    const hero = sigItemHtml(sig(code), 0);
    const row  = sigItemHtml(sig(code), 1);
    assert.match(hero, /^<a class="sig-hero"/, `${code} 히어로가 <a>여야 한다`);
    assert.match(row,  /^<a class="sig-row"/,  `${code} 행이 <a>여야 한다`);
    assert.ok(hero.includes(`goStock('${code}')`));
    assert.ok(row.includes('sig-go'), '링크 행에는 화살표가 있어야 한다');
  }
});

test('상세 페이지가 없는 종목은 링크로 그리지 않는다', () => {
  const { sigItemHtml } = load();
  // 042700(한미반도체)·000270(기아) 등 43종목은 랭킹·신호에는 나오지만 상세 페이지가 없다.
  for (const code of ['042700', '000270', '035420', '068270']) {
    const hero = sigItemHtml(sig(code), 0);
    const row  = sigItemHtml(sig(code), 1);
    assert.match(hero, /^<div class="sig-hero is-nolink"/, `${code} 히어로가 <div>여야 한다`);
    assert.match(row,  /^<div class="sig-row is-nolink"/,  `${code} 행이 <div>여야 한다`);
    assert.ok(!hero.includes('goStock'), '링크 아닌 행에 onclick이 남으면 안 된다');
    assert.ok(!row.includes('sig-go'), '링크 아닌 행에는 화살표가 없어야 한다');
    assert.ok(!hero.includes('<a '), '링크 아닌 행에 <a>가 섞이면 안 된다');
  }
});

test('닫는 태그가 여는 태그와 일치한다', () => {
  const { sigItemHtml } = load();
  assert.ok(sigItemHtml(sig('005930'), 0).endsWith('</a>'));
  assert.ok(sigItemHtml(sig('042700'), 0).endsWith('</div>'));
  assert.ok(sigItemHtml(sig('005930'), 2).endsWith('</a>'));
  assert.ok(sigItemHtml(sig('042700'), 2).endsWith('</div>'));
});

test('STOCK_PAGES는 stocks.json의 detail_page 종목과 같아야 한다', () => {
  const { STOCK_PAGES } = load();
  const cfg = JSON.parse(readFileSync(join(HERE, '..', '..', 'scripts', 'config', 'stocks.json'), 'utf8'));
  const list = Array.isArray(cfg) ? cfg : (cfg.stocks || []);
  const expected = list.filter((s) => s.detail_page).map((s) => s.code).sort();
  assert.deepEqual(Object.keys(STOCK_PAGES).sort(), expected,
    'STOCK_PAGES와 stocks.json의 detail_page가 어긋나면 존재하지 않는 페이지로 링크한다(§36)');
});
