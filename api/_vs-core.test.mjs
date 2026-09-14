// '어제랑 비교해서' 공용 순수 함수 회귀 테스트 — 직전 거래일·판정·결론 문장(설계 §2·§5)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { TH, prevTradingDay, relLabel, withJosa, atOrBefore, pct, judge, eokText, tickOk, verdict } from './_vs-core.mjs';

test('직전 거래일 — 월요일은 금요일, 추석 연휴 뒤는 연휴 전 거래일', () => {
  assert.equal(prevTradingDay('2026-09-14'), '2026-09-11');
  assert.equal(prevTradingDay('2026-09-15'), '2026-09-14');
  assert.equal(prevTradingDay('2026-09-28'), '2026-09-23'); // 9/24~26 휴장 + 주말
});

test('상대 라벨은 날짜로 계산한다', () => {
  assert.equal(relLabel('2026-09-14', '2026-09-15'), '어제');
  assert.equal(relLabel('2026-09-11', '2026-09-14'), '지난 금요일');
  assert.equal(relLabel('2026-09-23', '2026-09-28'), '지난 수요일');
});

test('조사는 받침으로 고른다', () => {
  assert.equal(withJosa('어제', '와과'), '어제와');
  assert.equal(withJosa('지난 금요일', '와과'), '지난 금요일과');
});

test('날짜 고정 조회 — 시각 이하 마지막 봉, 없으면 null', () => {
  const bars = [{ t: '0900', v: 1 }, { t: '1059', v: 2 }, { t: '1101', v: 3 }];
  assert.deepEqual(atOrBefore(bars, '1100'), { t: '1059', v: 2 });
  assert.equal(atOrBefore(bars, '0859'), null);
  assert.equal(atOrBefore([], '1100'), null);
});

test('등락률은 소수 둘째 자리, 기준이 없으면 null', () => {
  assert.equal(pct(6732.94, 6909.91), -2.56);
  assert.equal(pct(6863.70, 7033.92), -2.42);
  assert.equal(pct(100, null), null);
});

test('판정 — 경계값은 비슷해요', () => {
  assert.equal(judge(0.3, TH.pctPoint), 'same');
  assert.equal(judge(-0.31, TH.pctPoint), 'weak');
  assert.equal(judge(1001, TH.eok), 'strong');
  assert.equal(judge(null, TH.eok), null);
});

test('억 표기', () => {
  assert.equal(eokText(-8693), '8,693억');
  assert.equal(eokText(-20900), '2.09조');
});

test('호가 단위 — 1분봉 off-tick 값은 화면 숫자로 쓰지 않는다', () => {
  assert.equal(tickOk(259250), false); // 9/11 삼성전자 1분봉 실측
  assert.equal(tickOk(252000), true);
  assert.equal(tickOk(1733000), true);
  assert.equal(tickOk(1733500), false);
});

test('결론 문장 — 9/14 11:00 실측 리플레이', () => {
  const v = verdict({ yLabel: '지난 금요일', kospiDiff: -0.14, foreignDiff: -8693 });
  assert.equal(v.judge, 'same');
  assert.equal(v.title, '지난 금요일과 비슷해요');
  assert.equal(v.sub, '코스피가 같은 시각 기준 거의 같은 자리예요(−0.14%p) · 외국인 누적 순매수는 8,693억 원 적어요');
});

test('결론 문장 — 코스피가 없으면 결론을 만들지 않는다', () => {
  assert.equal(verdict({ yLabel: '어제', kospiDiff: null, foreignDiff: -5000 }), null);
});

test('결론 문장 — 외국인이 비슷하면 근거 줄에 붙이지 않는다', () => {
  const v = verdict({ yLabel: '어제', kospiDiff: 0.52, foreignDiff: 300 });
  assert.equal(v.title, '오늘이 어제보다 세요');
  assert.equal(v.sub, '코스피가 같은 시각 기준 0.52%p 높아요');
});
