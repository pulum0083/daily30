// 장중 이슈 아카이브에서 그 시각까지의 제목을 뽑고 키워드 사전으로 두 날을 대조한다(설계 §5)
export function issuesUntil(archive, hhmm) {
  const out = [];
  for (const h of (archive && archive.history) || []) {
    const t = String(h.time || '');
    if (!/^\d{2}:\d{2}$/.test(t) || t.replace(':', '') > hhmm) continue;
    for (const k of ['market', 'stock']) {
      const title = h[k] && h[k].title;
      if (title) out.push({ t, title: String(title) });
    }
  }
  return out.sort((a, b) => (a.t < b.t ? -1 : a.t > b.t ? 1 : 0));
}

export function keywordDiff(yItems, tItems, words, exclude = {}) {
  const has = (items, w) => {
    const excl = exclude[w] || [];
    return items.some((i) => {
      let title = i.title;
      for (const phrase of excl) {
        title = title.split(phrase).join(' ');
      }
      return title.includes(w);
    });
  };
  const res = { new: [], keep: [], gone: [] };
  for (const w of words || []) {
    const y = has(yItems, w), t = has(tItems, w);
    if (t && !y) res.new.push(w);
    else if (t && y) res.keep.push(w);
    else if (y) res.gone.push(w);
  }
  return res;
}
