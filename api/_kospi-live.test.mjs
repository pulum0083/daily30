import { test } from 'node:test';
import assert from 'node:assert/strict';
import handler from './kospi-live.mjs';

const BASIC = {
  closePrice: '5,500.25', fluctuationsRatio: '1.25', compareToPreviousClosePrice: '69.63',
  compareToPreviousPrice: { code: '5' }, marketStatus: 'CLOSE',
};

async function request(t, payloads, afterClose = false) {
  t.mock.method(Date, 'now', () => Date.parse(afterClose ? '2026-11-16T08:00:00Z' : '2026-11-16T01:00:00Z'));
  const urls = [];
  t.mock.method(globalThis, 'fetch', async (url) => {
    urls.push(url);
    assert.ok(payloads.length, `unexpected fetch: ${url}`);
    const body = payloads.shift();
    return { ok: true, json: async () => body };
  });
  const res = {
    statusCode: 200, setHeader() {},
    status(code) { this.statusCode = code; return this; },
    json(body) { this.body = body; return this; },
  };
  await handler({}, res);
  return { ...res, urls };
}

test('정상 장중 응답은 polling 값의 단위와 부호를 유지한다', async (t) => {
  const res = await request(t, [{ result: { areas: [{ datas: [{ nv: 550025, cr: -1.25, cv: -6963, ms: 'OPEN' }] }] } }]);
  assert.equal(res.statusCode, 200);
  assert.equal(res.body.price, 5500.25);
  assert.equal(res.body.changePct, -1.25);
  assert.equal(res.body.changeAbs, -70);
  assert.equal(res.urls.length, 1);
});

test('polling 가격이 잘못됐으면 basic 응답으로 폴백한다', async (t) => {
  const res = await request(t, [{ result: { areas: [{ datas: [{ nv: 'broken' }] }] } }, BASIC]);
  assert.equal(res.statusCode, 200);
  assert.equal(res.body.price, 5500.25);
  assert.equal(res.body.changePct, -1.25);
  assert.equal(res.body.changeAbs, -70);
  assert.equal(res.urls.length, 2);
});

test('장 마감 뒤에는 basic만 조회한다', async (t) => {
  const res = await request(t, [BASIC], true);
  assert.equal(res.body.price, 5500.25);
  assert.equal(res.urls.length, 1);
  assert.match(res.urls[0], /\/basic$/);
});

test('basic 가격도 잘못됐으면 정상 응답으로 발행하지 않는다', async (t) => {
  const res = await request(t, [{}, { ...BASIC, closePrice: 'broken' }]);
  assert.equal(res.statusCode, 502);
  assert.match(res.body.error, /invalid closePrice/);
});

test('장중 결측 등락은 0 대신 basic 실측값으로 폴백한다', async (t) => {
  const res = await request(t, [{ result: { areas: [{ datas: [{ nv: 550025, cr: null, cv: '' }] }] } }, BASIC]);
  assert.equal(res.body.price, 5500.25);
  assert.equal(res.body.changePct, -1.25);
  assert.equal(res.body.changeAbs, -70);
  assert.equal(res.urls.length, 2);
});
