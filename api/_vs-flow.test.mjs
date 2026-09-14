// 네이버 시간대별 투자자 매매동향 파서·시각 조회 회귀 테스트(설계 §6 #4)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseInvestorTimePage, lastPage, flowAt } from './_vs-flow.mjs';

function row(t, v) { return `<tr><td class="date">${t}</td>${v.map((x) => `<td class="rate_up">${x}</td>`).join('')}</tr>`; }
function page(rows, last = 3) {
  return '<table><tr><th>시간</th><th>개인</th><th>외국인</th><th>기관계</th><th colspan="6">기관</th><th>기타법인</th></tr>'
    + rows.join('') + '</table>' + Array.from({ length: last }, (_, i) => `<a href="?page=${i + 1}">${i + 1}</a>`).join('');
}
// 합계 0: 18675 − 22984 − 12184 + 16493 = 0 (9/11 18:06 실측)
const OK = ['18,675', '-22,984', '-12,184', '-10,345', '-17', '-4,703', '7', '216', '2,659', '16,493'];

test('열 순서대로 개인·외국인·기관계를 읽는다', () => {
  assert.deepEqual(parseInvestorTimePage(page([row('18:06', OK)])), [{ t: '18:06', 개인: 18675, 외국인: -22984, 기관: -12184 }]);
});

test('합계 0 검사를 통과하지 못한 행은 버린다(열 밀림 방어)', () => {
  const broken = ['18,675', '-22,984', '-12,184', '-10,345', '-17', '-4,703', '7', '216', '2,659', '99,999'];
  assert.deepEqual(parseInvestorTimePage(page([row('18:05', broken), row('18:04', OK)])).map((r) => r.t), ['18:04']);
});

test('머리글·빈 행은 건너뛴다', () => {
  assert.deepEqual(parseInvestorTimePage('<tr><td></td></tr>' + page([])), []);
});

test('마지막 페이지 번호', () => {
  assert.equal(lastPage(page([], 37)), 37);
  assert.equal(lastPage('<table></table>'), 1);
});

test('시각 이하 마지막 행을 페이지 이진 탐색으로 찾는다', async () => {
  // 1페이지 11:30~11:02 · 2페이지 11:01~10:59 · 3페이지 10:58~09:01
  const pages = {
    1: page([row('11:30', OK), row('11:02', OK)]),
    2: page([row('11:01', OK), row('10:59', OK)]),
    3: page([row('10:58', OK), row('09:01', OK)]),
  };
  const seen = [];
  const fetchText = async (url) => { const p = Number(url.match(/page=(\d+)/)[1]); seen.push(p); return pages[p]; };
  const hit = await flowAt('20260914', '1100', fetchText);
  assert.equal(hit.t, '10:59');
  assert.ok(seen.length <= 4, `페이지를 ${seen.length}번 읽었다`);
});

test('그 시각 이전 행이 없으면 null — 다른 시각으로 폴백하지 않는다', async () => {
  const fetchText = async () => page([row('09:05', OK)], 1);
  assert.equal(await flowAt('20260914', '0900', fetchText), null);
});

test('URL에 날짜·코스피(sosok=01)를 고정한다', async () => {
  let u = '';
  await flowAt('20260911', '1100', async (url) => { u = url; return page([row('10:00', OK)], 1); });
  assert.match(u, /bizdate=20260911&sosok=01&page=1$/);
});
