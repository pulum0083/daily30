// 장중 이슈 시각 필터·키워드 대조 회귀 테스트 — 9/11·9/14 실제 아카이브 리플레이(설계 §4.2·§5)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { issuesUntil, keywordDiff } from './_vs-issues.mjs';

const read = (f) => JSON.parse(readFileSync(new URL(`../web/data/${f}`, import.meta.url), 'utf8'));
const WORDS = read('issue-keywords.json').keywords;

test('그 시각 이하 이슈만, market·stock 제목을 모두', () => {
  const a = { history: [
    { time: '11:01', market: { title: '늦은 이슈' }, stock: { title: '늦은 종목' } },
    { time: '10:00', market: { title: '시장 A' }, stock: { title: '종목 A' } },
    { time: 'x', market: { title: '시각 없음' } },
  ] };
  assert.deepEqual(issuesUntil(a, '1100'), [{ t: '10:00', title: '시장 A' }, { t: '10:00', title: '종목 A' }]);
  assert.deepEqual(issuesUntil(null, '1100'), []);
});

test('9/11 vs 9/14 11:00 — 중동·AI 속도 조절론이 새로 떠올랐다(시안 v4와 같은 결과)', () => {
  const y = issuesUntil(read('kospi-news-2026-09-11.json'), '1100');
  const t = issuesUntil(read('kospi-news-2026-09-14.json'), '1100');
  const d = keywordDiff(y, t, WORDS);
  assert.deepEqual(d.new, ['AI 속도 조절론', '중동']);
  for (const w of ['유가', '금리', '외국인', '기관', '매도', '삼성전자', 'SK하이닉스']) assert.ok(d.keep.includes(w), w);
});

test('어제에만 있던 소재는 gone', () => {
  const d = keywordDiff([{ t: '10:00', title: '관세 우려' }], [{ t: '10:00', title: '금리 부담' }], ['관세', '금리']);
  assert.deepEqual(d, { new: ['금리'], keep: [], gone: ['관세'] });
});
