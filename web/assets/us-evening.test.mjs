// 밤사이 미국 두 묶음 회귀 테스트 — 코스피 선행 ETF 3칸 + AI 인프라 3갈래, SOXX는 한 번만(§68 ④)
// sig-home-link.test.mjs와 같은 node:vm 패턴 — 프로덕션 파일을 그대로 실행해 훅을 꺼낸다.
// 실행: node --test web/assets/us-evening.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { createContext, runInContext } from 'node:vm';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const noop = () => {};
function mkEl() {
  return {
    classList:{add:noop,remove:noop,toggle:noop,contains:()=>false}, dataset:{}, style:{}, children:[],
    innerHTML:'', textContent:'', hidden:false, addEventListener:noop, removeEventListener:noop,
    appendChild:noop, insertBefore:noop, setAttribute:noop, getAttribute:()=>null, remove:noop,
    closest:()=>null, contains:()=>false, getBoundingClientRect:()=>({top:0,left:0,width:0,height:0}),
    querySelector:()=>null, querySelectorAll:()=>[], parentNode:{insertBefore:noop,removeChild:noop,appendChild:noop},
  };
}
function load() {
  const els = {};
  const win = {
    location:{pathname:'/stocks/', hash:'', href:'https://x/stocks/', search:''},
    addEventListener:noop, removeEventListener:noop, setInterval:()=>0, clearInterval:noop, setTimeout:()=>0, clearTimeout:noop,
    fetch:()=>Promise.reject(new Error('no network in test')), matchMedia:()=>({matches:false, addEventListener:noop}),
    sessionStorage:{getItem:()=>null, setItem:noop}, localStorage:{getItem:()=>null, setItem:noop},
    Intl, Date, Math, JSON, console:{log:noop, warn:noop, error:noop}, navigator:{userAgent:'node'},
    history:{pushState:noop, replaceState:noop},
    document:{ readyState:'complete', getElementById:(id)=>(els[id] ||= mkEl()), querySelector:()=>mkEl(), querySelectorAll:()=>[],
      createElement:()=>mkEl(), addEventListener:noop, body:mkEl(), documentElement:mkEl(), head:mkEl() },
  };
  win.window = win;
  try { runInContext(readFileSync(join(HERE,'stocks-home.js'),'utf8'), createContext(win)); } catch { /* 훅만 필요 */ }
  return win.__usEvening;
}
const D = {'EWY.O':{price:151.26,changePct:1.48}, 'DRAM.K':{price:47.06,changePct:3.02}, 'SOXX.O':{price:478.2,changePct:0.53},
  'SKHY.O':{price:137.02,changePct:4.05}, 'MU.O':{price:877.55,changePct:2.46}, 'SNDK.O':{price:1238.03,changePct:-1.82},
  'NVDA.O':{price:210.96,changePct:-0.59}, 'AMD.O':{price:516.79,changePct:1.74}, 'AVGO.O':{price:321.68,changePct:-0.48},
  'TSM.N':{price:418.51,changePct:1.49}, 'ASML.O':{price:1571.8,changePct:0.72}, 'QQQ.O':{price:600,changePct:-0.01}};

test('두 묶음 구성 — 선행 ETF는 EWY·DRAM·SOXX, AI 인프라는 8종목이고 SOXX는 한 번만 나온다', () => {
  const ue = load();
  assert.deepEqual(Array.from(ue.LEAD, t => t.tk), ['EWY', 'DRAM', 'SOXX']);
  assert.deepEqual(Array.from(ue.AI_GROUPS, g => g.g), ['메모리', 'AI 칩', '파운드리·장비']);
  assert.deepEqual(Array.from(ue.AI_GROUPS).flatMap(g => Array.from(g.items, t => t.tk)), ['SKHY','MU','SNDK','NVDA','AMD','AVGO','TSM','ASML']);
  ue.set(D, {price:19.45, changePct:2.21}, 1326.9);
  ue.render();
  const html = ue.gridEl.innerHTML;
  assert.equal((html.match(/data-sym="SOXX\.O"/g) || []).length, 1);
  assert.match(html, /3개 중 <b class="up">3 상승<\/b>/);
  assert.match(html, /8개 중 <b class="up">5 상승<\/b> · <b class="dn">3 하락<\/b>/);
});

test('막대 폭은 AI 인프라 최대 절대 등락(SKHY 4.05%) 대비 비율이고 방향 색을 따른다', () => {
  const ue = load();
  ue.set(D, null, 1326.9);
  ue.render();
  const html = ue.gridEl.innerHTML;
  assert.match(html, /<i class="up" style="width:100%"><\/i>/);           // SKHY
  assert.match(html, /<i class="dn" style="width:45%"><\/i>/);           // SNDK 1.82/4.05
});

test('맨 위 한 줄은 QQQ·VIX만 — 값이 없으면 대시로 비운다', () => {
  const ue = load();
  ue.set(D, null, 1326.9);
  ue.render();
  assert.match(ue.macroEl.innerHTML, /나스닥 QQQ/);
  assert.match(ue.macroEl.innerHTML, /VIX <span class="cg" style="color:var\(--muted\)">—<\/span>/);
  assert.ok(!/SOXX/.test(ue.macroEl.innerHTML));
});

test('원화/달러 전환 — 원화는 환율 곱, 환율이 없으면 대시', () => {
  const ue = load();
  ue.set(D, null, 1326.9, 'krw'); ue.render();
  assert.match(ue.gridEl.innerHTML, /200,707원/);                       // EWY 151.26 × 1326.9 = 200,706.9
  ue.set(D, null, null, 'krw'); ue.render();
  assert.ok(!/원</.test(ue.gridEl.innerHTML.replace(/한국|원화/g, '')));
  ue.set(D, null, 1326.9, 'usd'); ue.render();
  assert.match(ue.gridEl.innerHTML, /\$151\.26/);
});

test('링크는 상세 페이지가 실제로 있는 종목만(§36)', () => {
  const ue = load();
  for (const t of ue.TICKERS) {
    if (!t.href) continue;
    const m = /^\/stocks\/(us\/[a-z]+|\d{6})\/$/.exec(t.href);
    assert.ok(m, t.href);
    assert.ok(existsSync(join(HERE, '..', 'stocks', m[1], 'index.html')), `${t.tk} 상세 페이지 없음`);
  }
  assert.equal(ue.LEAD.find(t => t.tk === 'EWY').href, undefined);       // EWY 상세는 없다
});
