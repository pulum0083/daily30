import { test } from 'node:test';
import assert from 'node:assert/strict';
import { SECTOR_REPS, sectorRows } from './_vs-sectors.mjs';

test('8섹터 × 대표 3종목', () => {
  assert.equal(SECTOR_REPS.length, 8);
  for (const s of SECTOR_REPS) {
    assert.equal(s.codes.length, 3, s.key);
    assert.equal(s.names.length, 3, s.key);
  }
});

test('오늘 등락률 내림차순 정렬과 순위 이동', () => {
  const by = {};
  // 반도체는 오늘 1위·어제 2위, 금융은 오늘 2위·어제 1위가 되게 채운다
  const semi = SECTOR_REPS.find((s) => s.key === 'semicon');
  const fin = SECTOR_REPS.find((s) => s.key === 'finance');
  semi.codes.forEach((c) => { by[c] = { t: 2, y: 0 }; });
  fin.codes.forEach((c) => { by[c] = { t: 1, y: 1 }; });
  const rows = sectorRows(by);
  assert.equal(rows[0].key, 'semicon');
  assert.equal(rows[0].rank, 1);
  assert.equal(rows[0].prevRank, 2);
  assert.equal(rows[0].move, 1);
  assert.equal(rows[1].key, 'finance');
  assert.equal(rows[1].move, -1);
});

test('일부 종목이 없으면 있는 것만 평균 내고 n을 남긴다', () => {
  const semi = SECTOR_REPS.find((s) => s.key === 'semicon');
  const by = { [semi.codes[0]]: { t: 3, y: 1 }, [semi.codes[1]]: { t: 1, y: 1 } };
  const row = sectorRows(by).find((r) => r.key === 'semicon');
  assert.equal(row.t, 2);
  assert.equal(row.n, 2);
});

test('오늘 값이 하나도 없는 섹터는 빠진다', () => {
  const semi = SECTOR_REPS.find((s) => s.key === 'semicon');
  const by = {}; semi.codes.forEach((c) => { by[c] = { t: null, y: 1 }; });
  assert.equal(sectorRows(by).find((r) => r.key === 'semicon'), undefined);
});

test('차이는 반올림 전 값으로 계산한다', () => {
  const semi = SECTOR_REPS.find((s) => s.key === 'semicon');
  const by = {}; semi.codes.forEach((c) => { by[c] = { t: 1.035, y: -0.775 }; });
  assert.equal(sectorRows(by).find((r) => r.key === 'semicon').diff, 1.81);
});
