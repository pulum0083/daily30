// 네이버의 숫자/쉼표 문자열을 공통으로 읽는다. 결측값·잘못된 값은 0으로 채우지 않는다.
export function toNum(value) {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value !== 'string') return null;
  const text = value.replace(/,/g, '').trim();
  if (!text || !/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(text)) return null;
  const number = Number(text);
  return Number.isFinite(number) ? number : null;
}

const CHANGE_SIGN = { '1': 1, '2': 1, '3': 0, '4': -1, '5': -1 };

export function signedChange(value, code, digits = 2) {
  const number = toNum(value);
  const sign = CHANGE_SIGN[code];
  if (number == null || typeof sign !== 'number') return null;
  const scale = 10 ** digits;
  return Math.round(sign * Math.abs(number) * scale) / scale;
}

export function parseBasicIndex(data) {
  const price = toNum(data?.closePrice);
  if (price == null || price <= 0) throw new Error('index: invalid closePrice');
  const changePct = signedChange(data.fluctuationsRatio, data.compareToPreviousPrice?.code);
  // 지수 소비자는 가격·등락률을 한 쌍으로 표시한다. 불완전하면 지수 전체를 생략한다.
  if (changePct == null) throw new Error('index: invalid changePct');
  return { price, changePct };
}
