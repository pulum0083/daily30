// 폴링 API가 엣지 공유 캐시를 설정하는지 검증하는 회귀 테스트 — 2026-08-16 Vercel 차단 사고 방지
//
// 배경: 2026-08-16 01:58 KST에 Vercel 팀이 FAIR_USE_LIMITS_EXCEEDED(fluidCpuDuration)로
// 소프트 차단돼 doubleshot.space 전체가 402를 반환했다. 클라이언트가 10~120초 주기로 때리는
// 엔드포인트 중 6개가 Cache-Control: no-store 여서, 폴링 1회 = 서버리스 함수 실행 1회로
// 직결돼 있었다. 엣지 캐시가 걸리면 동시 접속자 N명의 요청이 함수 실행 1회로 합쳐진다.
//
// s-maxage를 폴링 주기 이하로 잡으므로 단일 뷰어 기준 추가 지연은 0이다 —
// 클라이언트가 그보다 빨리 새 값을 받아갈 일이 애초에 없다.
//
// 실행: node --test api/_cache-headers.test.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';

// 검증 대상 — 클라이언트가 주기적으로 폴링하는 읽기 전용 엔드포인트.
// board.mjs는 폴링 대상이 아니고 POST 쓰기를 겸하므로 제외한다.
const POLLED = [
  { name: 'stocks-live', mod: './stocks-live.mjs', pollSec: 20,  req: { query: { codes: '005930', us: '' } } },
  { name: 'hl-night',    mod: './hl-night.mjs',    pollSec: 10,  req: { query: {} } },
  { name: 'signals',     mod: './signals.mjs',     pollSec: 120, req: { query: {} } },
  { name: 'vol-top',     mod: './vol-top.mjs',     pollSec: 120, req: { query: {} } },
  { name: 'data',        mod: './data.mjs',        pollSec: 300, req: { query: { f: 'news-live' } } },
];

// 상류 fetch를 즉시 실패시켜 네트워크 없이 핸들러를 끝까지 돌린다.
// 캐시 헤더는 성공·실패 경로 양쪽에서 설정돼야 한다 — 상류가 흔들릴 때야말로
// 엣지 캐시(stale-while-revalidate)가 함수 폭주를 막아주는 구간이기 때문이다.
function fakeRes() {
  const headers = {};
  const res = {
    statusCode: null,
    setHeader(k, v) { headers[k.toLowerCase()] = String(v); },
    status(c) { res.statusCode = c; return res; },
    json() { return res; },
    end() { return res; },
    get(k) { return headers[k.toLowerCase()]; },
  };
  return res;
}

async function callHandler(modPath, req) {
  const { default: handler } = await import(modPath);
  const realFetch = globalThis.fetch;
  globalThis.fetch = async () => { throw new Error('offline (test stub)'); };
  const res = fakeRes();
  try {
    await handler({ headers: { host: 'doubleshot.space' }, method: 'GET', ...req }, res);
  } finally {
    globalThis.fetch = realFetch;
  }
  return res;
}

for (const { name, mod, pollSec, req } of POLLED) {
  test(`${name}: 엣지 공유 캐시를 설정한다 (no-store 금지)`, async () => {
    const res = await callHandler(mod, req);
    const cc = res.get('cache-control');

    assert.ok(cc, `${name}이 Cache-Control을 설정하지 않았다`);
    assert.ok(
      !/no-store/i.test(cc),
      `${name}이 no-store다 — 폴링 1회마다 함수가 깨어난다: "${cc}"`,
    );

    const m = /s-maxage=(\d+)/i.exec(cc);
    assert.ok(m, `${name}에 s-maxage가 없다 — 엣지 캐시가 걸리지 않는다: "${cc}"`);
    assert.ok(Number(m[1]) >= 1, `${name}의 s-maxage가 0이다: "${cc}"`);
  });

  test(`${name}: s-maxage가 폴링 주기(${pollSec}초)를 넘지 않는다`, async () => {
    const res = await callHandler(mod, req);
    const cc = res.get('cache-control');
    const ttl = Number(/s-maxage=(\d+)/i.exec(cc)?.[1] ?? -1);

    // 폴링 주기보다 길게 잡으면 사용자가 보는 값이 실제로 낡는다(§0 실측 원칙).
    // 주기 이하면 클라이언트가 어차피 그 사이에 다시 묻지 않으므로 체감 지연이 0이다.
    assert.ok(
      ttl > 0 && ttl <= pollSec,
      `${name}의 s-maxage(${ttl}s)가 폴링 주기(${pollSec}s)를 초과한다 — 화면 값이 낡는다`,
    );
  });
}
