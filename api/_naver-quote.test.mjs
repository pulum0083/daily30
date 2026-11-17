import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseBasicIndex, signedChange, toNum } from './_naver-quote.mjs';

test('실측 숫자와 쉼표·부호 문자열을 읽고 실제 0은 보존한다', () => {
  for (const [value, expected] of [[0, 0], ['0', 0], ['  +1,234.50 ', 1234.5], ['-3.53', -3.53], [0.0000001, 0.0000001]]) {
    assert.equal(toNum(value), expected);
  }
});

test('결측·비정상 숫자·숫자 접두사만 있는 문자열은 시세로 쓰지 않는다', () => {
  for (const value of [null, undefined, '', ' ', '-', 'N/A', '123error', '12%', NaN, Infinity, 'Infinity', true, [], [123], {}]) {
    assert.equal(toNum(value), null, String(value));
  }
});

test('상승·하락·보합 부호 코드를 적용하고 지수 단위 반올림을 유지한다', () => {
  for (const code of ['1', '2']) assert.equal(signedChange('-1.235', code), 1.24);
  for (const code of ['4', '5']) assert.equal(signedChange('1.23', code), -1.23);
  assert.equal(signedChange('0', '3'), 0);
  assert.equal(signedChange('9.4', '5', 0), -9);
});

test('등락 수치나 부호가 없으면 보합 0으로 채우지 않는다', () => {
  assert.equal(signedChange(null, '3'), null);
  assert.equal(signedChange('1.2', undefined), null);
  assert.equal(signedChange('1.2', 'unknown'), null);
});

test('지수 기본 응답은 문자열·숫자 가격을 같은 방식으로 읽는다', () => {
  for (const closePrice of ['5,500.25', 5500.25]) {
    assert.deepEqual(parseBasicIndex({ closePrice, fluctuationsRatio: '1.2', compareToPreviousPrice: { code: '5' } }), {
      price: 5500.25, changePct: -1.2,
    });
  }
  assert.throws(() => parseBasicIndex({ closePrice: 5500 }), /invalid changePct/);
});

test('필수 가격이 없거나 잘못된 응답은 실패해 호출자의 폴백으로 넘긴다', () => {
  for (const data of [null, {}, { closePrice: 'garbage' }, { closePrice: 0 }, { closePrice: -1 }]) {
    assert.throws(() => parseBasicIndex(data), /invalid closePrice/);
  }
});
