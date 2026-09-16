import { test } from 'node:test';
import assert from 'node:assert/strict';
import { regularFlowRow, buildCloseVs } from './_vs-close.mjs';

const r = (t) => ({ t, 개인: 0, 외국인: 0, 기관: 0, inst: {} });

test('15:31~15:40 사이 마지막 행을 고른다 — 애프터장 행은 쓰지 않는다', () => {
  const rows = [r('17:10'), r('16:05'), r('15:40'), r('15:35'), r('15:30')];
  assert.equal(regularFlowRow(rows).t, '15:40');
});

test('15:31 이전 행뿐이면 null — 장이 아직 안 끝난 것이다', () => {
  assert.equal(regularFlowRow([r('15:30'), r('15:20')]), null);
});

test('15:30~15:40 사이엔 early — 마감 카드를 만들지 않는다', async () => {
  const res = await buildCloseVs({ now: Date.parse('2026-09-16T06:35:00Z') }); // 15:35 KST
  assert.equal(res.status, 'early');
});

test('09:00~15:30 장중엔 closed — 장중 대결판이 담당한다', async () => {
  const res = await buildCloseVs({ now: Date.parse('2026-09-16T04:30:00Z') }); // 13:30 KST
  assert.equal(res.status, 'closed');
});
