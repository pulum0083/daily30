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
  win.__sigHome.__win = win;
  return win.__sigHome;
}

const sig = (code) => ({code, name:'테스트', sector:'반도체', pct:3.2, dir:'up', badges:['거래량 급증'], why:'왜'});

test('모든 종목을 섹터 페이지로 보낸다 — 종목 상세 페이지는 없다(2026-10-26 제거)', () => {
  const { sigItemHtml } = load();
  // 예전에 상세 페이지가 있던 3종목(005930·000660·005380)도 이제 섹터 페이지로 간다.
  for (const code of ['005930', '000660', '005380', '042700', '000270', '035420', '068270']) {
    const hero = sigItemHtml(sig(code), 0);
    const row  = sigItemHtml(sig(code), 1);
    assert.match(hero, /^<a class="sig-hero is-sector" href="\/stocks\/sector\/semicon\/"/, `${code} 히어로가 섹터 링크여야 한다`);
    assert.match(row,  /^<a class="sig-row is-sector" href="\/stocks\/sector\/semicon\/"/,  `${code} 행이 섹터 링크여야 한다`);
    assert.ok(!hero.includes('goStock') && !hero.includes(`/stocks/${code}/`), '상세 페이지 링크가 남으면 안 된다');
    assert.ok(row.includes('반도체 보기 →'));
  }
});

test('섹터를 모르면 예전처럼 막는다', () => {
  const { sigItemHtml } = load();
  const row = sigItemHtml({ ...sig('042700'), sector: '기타' }, 1);
  assert.match(row, /^<div class="sig-row is-nolink"/);
});

test('닫는 태그가 여는 태그와 일치한다', () => {
  const { sigItemHtml } = load();
  assert.ok(sigItemHtml(sig('005930'), 0).endsWith('</a>'));
  assert.ok(sigItemHtml(sig('042700'), 0).endsWith('</a>'));
  assert.ok(sigItemHtml(sig('005930'), 2).endsWith('</a>'));
  assert.ok(sigItemHtml({ ...sig('042700'), sector: '기타' }, 2).endsWith('</div>'));
});

test('홈은 신호 강도 상위 3개만', () => {
  assert.equal(load().SIG_HOME_N, 3);
});


test('섹터 막대 — 등락 큰 순, 섹터 페이지 링크, 0을 가운데 둔 막대(§68 ③)', () => {
  const { sectorBarsHtml } = load().__win.__sectorBars;
  const html = sectorBarsHtml([
    { key: 'semicon', label: '반도체', avg: -1.2 }, { key: 'defense', label: '방산', avg: 2.4 }, { key: 'bio', label: '바이오', avg: NaN },
  ]);
  assert.ok(html.indexOf('방산') < html.indexOf('반도체'), '등락 큰 순');
  assert.ok(html.includes('href="/stocks/sector/defense/"') && html.includes('href="/stocks/sector/semicon/"'));
  assert.ok(!html.includes('바이오'), '값이 없는 섹터는 그리지 않는다');
  assert.ok(html.includes('width:50.0%;left:50%') && html.includes('width:25.0%;right:50%'));
  assert.ok(html.includes('+2.40%') && html.includes('−1.20%'));
  assert.equal(sectorBarsHtml([]), '');
});
