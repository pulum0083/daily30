// 종목 시그널 첫 화면 시간대 카드 — 지금 시각에 맞는 브리핑 카드(아침 예측·마감·미국·주말)를 맨 위에 그린다(SERVICE_RULES §68)
/* 시간대(KST)
     평일 07:30~09:00  코스피 시초가 예측 카드
     09:00~15:30       어제랑 비교 곡선 — 기존 대결판(#vs-root, §49·§54)이 그대로 맡는다
     15:31~미국 발행 전 코스피 마감 카드 — 마감 브리핑이 ready 전이면 기존 마감 곡선(#vs-root)이 그 자리를 맡는다
     미국 발행 후~다음 날 07:30  미국 브리핑 카드
     주말·한국 휴장일   이번 주 정리 카드(한국 휴장일이어도 미국 브리핑이 나오면 미국 카드)
   오늘 브리핑이 ready가 아니면 옛 날짜로 대체하지 않고 카드를 뺀다(§13·§16).
   헤드라인·보조 문장은 그날 브리핑 스냅샷 그대로다 — 새 문장을 만들지 않는다. */
(function () {
  var DOWS = ['일', '월', '화', '수', '목', '금', '토'];

  function kst(d) {
    var k = new Date(d.getTime() + 9 * 3600 * 1000);
    return { ymd: k.toISOString().slice(0, 10), dow: k.getUTCDay(), m: k.getUTCHours() * 60 + k.getUTCMinutes() };
  }
  function shiftYmd(ymd, days) {
    var p = ymd.split('-');
    return new Date(Date.UTC(+p[0], +p[1] - 1, +p[2] + days)).toISOString().slice(0, 10);
  }

  // 시간대 판정 — opts.krHoliday(ymd)·opts.usReady(ymd)는 주입(테스트·브라우저 공용).
  function homeSlot(d, opts) {
    opts = opts || {};
    var hol = opts.krHoliday || function () { return false; };
    var usReady = opts.usReady || function () { return false; };
    var k = kst(d);
    if (k.m < 450) {                                   // 07:30 전 — 전날(KST 평일) 밤 미국 브리핑
      var ydow = (k.dow + 6) % 7;
      return (ydow >= 1 && ydow <= 5) ? { slot: 'evening', date: shiftYmd(k.ymd, -1) } : { slot: 'weekend', date: k.ymd };
    }
    if (k.dow === 0 || k.dow === 6) return { slot: 'weekend', date: k.ymd };
    if (hol(k.ymd)) return usReady(k.ymd) ? { slot: 'evening', date: k.ymd } : { slot: 'weekend', date: k.ymd };
    if (k.m < 540) return { slot: 'morning', date: k.ymd };
    if (k.m <= 930) return { slot: 'intraday', date: k.ymd };   // 15:30까지 장중(대결판 slotOf와 같은 경계)
    return usReady(k.ymd) ? { slot: 'evening', date: k.ymd } : { slot: 'close', date: k.ymd };
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; });
  }
  // dek는 스냅샷이 <b> 강조만 담는다 — <b>·</b> 말고는 전부 이스케이프한다.
  function dekHtml(s) { return esc(s).replace(/&lt;(\/?)b&gt;/g, '<$1b>'); }
  function pct(v) { return (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(2) + '%'; }
  function cls(v) { return v > 0 ? 'up' : v < 0 ? 'dn' : ''; }
  function hm(iso) { var m = /T(\d{2}:\d{2})/.exec(String(iso || '')); return m ? m[1] : ''; }
  function dayLabel(ymd, today) {
    if (ymd === today) return '오늘';
    var p = ymd.split('-'), w = new Date(Date.UTC(+p[0], +p[1] - 1, +p[2])).getUTCDay();
    return (+p[1]) + '/' + (+p[2]) + '(' + DOWS[w] + ')';
  }
  function head(label, ymd, today, time) {
    return '<div class="hh-k"><span>' + esc(dayLabel(ymd, today) + (time ? ' ' + time : '') + ' · ' + label) + '</span>' +
           (ymd === today ? '<span class="hh-new">새 브리핑</span>' : '') + '</div>';
  }

  function cardMorning(snap, ymd, today, acc, item) {
    var p = snap.prediction || {}, tv = snap.todays_view || {};
    var dir = p.direction || '', up = dir.indexOf('상승') >= 0, dn = dir.indexOf('하락') >= 0;
    var prob = up ? p.up_pct : dn ? p.down_pct : p.up_pct;
    if (!tv.view_title || prob == null) return '';
    var trust = (acc && acc.basis === 'open' && acc.scored >= 5)
      ? '<div class="hh-trust">시초가 예측 적중 <b>' + acc.hit + '/' + acc.scored + '</b> (' + acc.pct + '%) · 매일 07:25·16:25·21:15 발행</div>' : '';
    return '<div class="hh ' + (up ? 'is-up' : dn ? 'is-dn' : '') + '">' +
      head('코스피 시초가 예측', ymd, today, (item && item.time) || hm(snap.generated_at)) +
      '<div class="hh-m"><b class="hh-d">' + (up ? '↑ ' : dn ? '↓ ' : '') + esc(dir) + '</b>' +
      '<b class="hh-p">' + prob + '%<small>' + (up || dn ? '' : '위로 열릴 확률 · ') + '신뢰도 ' + esc(p.confidence) + '%</small></b></div>' +
      '<h2 class="hh-h">' + esc(tv.view_title) + '</h2>' +
      (tv.dek ? '<p class="hh-dek">' + dekHtml(tv.dek) + '</p>' : '') +
      '<a class="hh-cta" href="/briefings/' + ymd + '/kospi/">' + (ymd === today ? '오늘 ' : '') + '코스피 브리핑 보기 →</a>' + trust + '</div>';
  }

  // 마감 카드의 아침 예측 채점 — home-summary.json(마감 잡이 쓴다)에서 그날 기록만 쓴다.
  function morningChip(summary, ymd) {
    var s = summary && (summary.scores || []).filter(function (x) { return x.date === ymd; })[0];
    if (!s || typeof s.open_pct !== 'number') return '';
    return '<div class="hh-chip ' + (s.ok ? 'ok' : 'miss') + '">📝 아침 시초가 예측 ' + esc(s.direction) +
      ' → 시초가 <b class="' + cls(s.open_pct) + '">' + pct(s.open_pct) + '</b> ' + (s.ok ? '✓ 적중' : '✗ 빗나감') + '</div>';
  }

  function cardClose(snap, ymd, today, summary, item) {
    var title = snap.market_title || snap.reason_title || (item && item.headline);
    if (!title) return '';
    return '<div class="hh">' + head('코스피 마감', ymd, today, hm(snap.generated_at)) +
      '<h2 class="hh-h">' + esc(title) + '</h2>' +
      (snap.dek ? '<p class="hh-dek">' + dekHtml(snap.dek) + '</p>' : '') + morningChip(summary, ymd) +
      '<a class="hh-cta" href="/briefings/' + ymd + '/close/">마감 브리핑 보기 →</a></div>';
  }

  function nasdaqChip(nq) {
    if (!nq || typeof nq.gap_pct !== 'number') return '';
    // 미국 브리핑 페이지와 같이 주의(60%)·경고(70%)일 때만 칩을 단다 — 정상이 매일 반복되면 뜻이 없다(§65).
    var g = nq.gap_pct;
    if (g < 60) return '';
    var lv = g >= 70 ? ['warn', '🚨 경고'] : ['caution', '⚠️ 주의'];
    return '<div class="hh-chip nq-' + lv[0] + '">나스닥 체크 <b>' + (g >= 0 ? '+' : '') + g.toFixed(1) + '%</b> · ' + lv[1] + '</div>';
  }

  function cardEvening(snap, ymd, today) {
    var p = snap.prediction || {}, tv = snap.todays_view || {};
    if (!tv.view_title) return '';
    var u = p.up_pct, d = p.down_pct, m = '';
    if (typeof u === 'number' && typeof d === 'number') {
      var side = u === d ? 0 : (u > d ? 1 : -1);
      m = '<div class="hh-m"><b class="hh-d">' + (side > 0 ? '↑ 상승 우위' : side < 0 ? '↓ 하락 우위' : '중립') + '</b>' +
          '<b class="hh-p">' + Math.max(u, d) + '%</b></div>';
    }
    var side2 = (u > d) ? 'is-up' : (d > u) ? 'is-dn' : '';
    return '<div class="hh ' + side2 + '">' + head('미국 시장 브리핑', ymd, today, hm(snap.generated_at)) + m +
      '<h2 class="hh-h">' + esc(tv.view_title) + '</h2>' +
      (tv.dek ? '<p class="hh-dek">' + dekHtml(tv.dek) + '</p>' : '') + nasdaqChip(snap.nasdaq_overheat) +
      '<a class="hh-cta" href="/briefings/' + ymd + '/us/">미국 브리핑 보기 →</a></div>';
  }

  // 주말 카드(§68 ⑥) — home-summary.json(마감 잡이 쓴다)의 가장 최근 거래 주. 헤드라인·계단 그림은 결정론으로 만든다.
  function weekRows(rows) {
    if (!rows || !rows.length) return { week: [], prev: null };
    var last = rows[rows.length - 1].date, p = last.split('-');
    var dow = new Date(Date.UTC(+p[0], +p[1] - 1, +p[2])).getUTCDay();
    var monday = shiftYmd(last, -((dow + 6) % 7));
    var week = rows.filter(function (r) { return r.date >= monday; });
    var before = rows.filter(function (r) { return r.date < monday; });
    return { week: week, prev: before.length ? before[before.length - 1] : null, monday: monday };
  }
  // 계단 그림 — 지난주 종가에서 하루씩 쌓아 이번 주 종가까지(2026-11-01 B안, 시안 docs/prototypes/2026-11-01-weekend-week-infographic.html)
  function dowOf(ymd) { var p = ymd.split('-'); return DOWS[new Date(Date.UTC(+p[0], +p[1] - 1, +p[2])).getUTCDay()]; }
  // SVG로 그리면 PC 폭(880px)에서 글자·높이까지 같이 커진다 — HTML 칸으로 그려 가로만 늘고 높이·글자는 고정한다.
  function weekSteps(prev, week) {
    var pts = [prev.close].concat(week.map(function (r) { return r.close; }));
    var lo = Math.min.apply(null, pts), hi = Math.max.apply(null, pts), pad = (hi - lo) * 0.12 || 1;
    lo -= pad; hi += pad;
    var y = function (v) { return ((hi - v) / (hi - lo) * 100).toFixed(1) + '%'; };
    var f0 = function (v) { return Math.round(v).toLocaleString('en-US'); };
    var cn = function (v) { return '<i class="st-cn" style="top:' + y(v) + '"></i>'; };
    var lv = function (v) { return '<i class="st-lv" style="top:' + y(v) + '"></i><span class="st-v" style="top:' + y(v) + '">' + f0(v) + '</span>'; };
    var cols = '<div class="st-c">' + lv(prev.close) + '</div>', keys = '<span><b>지난주</b>종가</span>', pv = prev.close;
    week.forEach(function (r) {
      var a = (hi - Math.max(pv, r.close)) / (hi - lo) * 100, h = Math.abs(r.close - pv) / (hi - lo) * 100;
      var up = r.close >= pv;
      cols += '<div class="st-c">' + cn(pv) +
        '<i class="st-b ' + (up ? 'up' : 'dn') + '" style="top:' + a.toFixed(1) + '%;height:' + h.toFixed(1) + '%"></i>' +
        '<span class="st-p ' + cls(r.pct) + (r.pct >= 0 ? ' a' : ' u') + '" style="top:' + (r.pct >= 0 ? a : a + h).toFixed(1) + '%">' + pct(r.pct) + '</span></div>';
      keys += '<span class="on"><b>' + dowOf(r.date) + '</b>' + md(r.date) + '</span>';
      pv = r.close;
    });
    cols += '<div class="st-c">' + cn(pv) + lv(pv) + '</div>';
    keys += '<span><b>이번 주</b>종가</span>';
    return '<div class="st-plot" style="grid-template-columns:repeat(' + (week.length + 2) + ',1fr)" role="img" aria-label="지난주 종가 ' + f0(prev.close) +
      '에서 이번 주 종가 ' + f0(pv) + '까지 일별 등락"><i class="st-base" style="top:' + y(prev.close) + '"></i>' + cols + '</div>' +
      '<div class="st-x" style="grid-template-columns:repeat(' + (week.length + 2) + ',1fr)">' + keys + '</div>';
  }
  // 헤드라인 — 시작·끝 종가와 가장 크게 움직인 날의 포인트 변화(결정론)
  function weekStepHead(prev, week) {
    var bi = 0;
    week.forEach(function (r, i) { if (Math.abs(r.pct) > Math.abs(week[bi].pct)) bi = i; });
    var pt = week[bi].close - (bi ? week[bi - 1].close : prev.close);
    var f0 = function (v) { return Math.round(v).toLocaleString('en-US'); };
    return f0(prev.close) + ' → ' + f0(week[week.length - 1].close) + ', ' + dowOf(week[bi].date) + '요일 하루에 <span class="' + cls(pt) + '">' +
      (pt > 0 ? '+' : pt < 0 ? '−' : '') + f0(Math.abs(pt)) + 'p</span>';
  }
  function md(ymd) { var p = ymd.split('-'); return (+p[1]) + '/' + (+p[2]); }

  // 미국 지수 요일 계단(2026-11-09 사용자 결정, 시안 docs/prototypes/2026-11-09-weekly-market.html A안).
  //   주간 장기 리포트가 토요일 아침 저장한 /weekly/{금요일}/data.json을 읽는다 — 리포트가 아직 없으면(금요일 밤~토요일 아침) 빠진다.
  //   지수마다 한 줄, 월~금 다섯 칸에 그날 오르내린 만큼 계단을 이어 쌓는다. 네 지수가 같은 눈금이고, 거래가 없던 요일은 '휴장'.
  var US_WEEK = [['^SOX', '반도체(SOX)'], ['^IXIC', '나스닥'], ['^GSPC', 'S&P 500'], ['^DJI', '다우']];
  function usWeekSteps(wk, monday) {
    if (!wk || wk.monday !== monday || !wk.idx) return '';
    var rows = [], cums = [0];
    US_WEEK.forEach(function (x) {
      var s = wk.idx[x[0]];
      if (!Array.isArray(s) || s.length < 2) return;
      var base = s[0][1], prev = base, cells = [null, null, null, null, null];
      for (var i = 1; i < s.length; i++) {
        var k = daysBetween(monday, s[i][0]);
        if (k >= 0 && k < 5) {
          cells[k] = { pct: (s[i][1] / prev - 1) * 100, a: (prev / base - 1) * 100, b: (s[i][1] / base - 1) * 100 };
          cums.push(cells[k].b);
        }
        prev = s[i][1];
      }
      rows.push({ name: x[1], from: base, to: s[s.length - 1][1], wk: (s[s.length - 1][1] / base - 1) * 100, cells: cells });
    });
    if (!rows.length) return '';
    var lo = Math.floor(Math.min.apply(null, cums) - 2), hi = Math.ceil(Math.max.apply(null, cums) + 2);
    var Y = function (v) { return (hi - v) / (hi - lo) * 100; };
    var sg = function (v, d) { return (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(d); };
    var f2 = function (v) { return v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); };
    var html = rows.map(function (r) {
      var cells = r.cells.map(function (c, i) {
        if (!c) return '<div><span class="uwk-off">휴장</span></div>';
        var top = Y(Math.max(c.a, c.b)), h = Math.max(Y(Math.min(c.a, c.b)) - top, 0.6), up = c.pct >= 0;
        return '<div><i class="' + (up ? 'u' : 'd') + '" style="top:' + top.toFixed(2) + '%;height:' + h.toFixed(2) + '%"></i>' +
          '<em class="' + (up ? 'up' : 'dn') + '" style="top:calc(' + (up ? top.toFixed(2) + '% - 13px' : (top + h).toFixed(2) + '% + 1px') + ')">' + sg(c.pct, 1) + '</em>' +
          (i < 4 ? '<u style="top:' + Y(c.b).toFixed(2) + '%"></u>' : '') + '</div>';
      }).join('');
      return '<div class="uwk-r"><div class="uwk-n">' + esc(r.name) + '<small>' + f2(r.from) + ' → ' + f2(r.to) + '</small></div>' +
        '<div class="uwk-s" style="--z:' + Y(0).toFixed(2) + '%">' + cells + '</div>' +
        '<div class="uwk-t ' + cls(r.wk) + '">' + sg(r.wk, 2) + '%</div></div>';
    }).join('');
    return '<div class="uwk"><div class="uwk-h">미국 지수 · 이번 주<span>점선 = 지난주 금요일 종가</span></div>' + html +
      '<div class="uwk-x"><span></span><div><span>월</span><span>화</span><span>수</span><span>목</span><span>금</span></div><span></span></div></div>';
  }

  function cardWeekend(summary, ymd, today, holiday, wk) {
    var w = weekRows(summary && summary.kospi_days);
    if (!w.week.length || !w.prev) return '';
    var last = w.week[w.week.length - 1];
    if (last.date > ymd || daysBetween(last.date, ymd) > 7) return '';           // 지난 주 요약을 이번 주로 보이지 않게
    var total = (last.close / w.prev.close - 1) * 100;
    var pcts = w.week.map(function (r) { return r.pct; });
    var up = pcts.filter(function (v) { return v > 0; }).length, dn = pcts.filter(function (v) { return v < 0; }).length;
    var dates = w.week.map(function (r) { return r.date; });
    var sc = ((summary && summary.scores) || []).filter(function (x) { return dates.indexOf(x.date) >= 0; });
    var hit = sc.filter(function (x) { return x.ok; }).length;
    var top = (summary && summary.sectors_week || [])[0];
    // 숫자 줄은 한 줄로 간단히 — 시작·끝 종가는 바로 아래 헤드라인·계단 그림이 보여준다(2026-11-01)
    var tile = function (k, v) { return '<span><i>' + k + '</i>' + v + '</span>'; };
    var us = usWeekSteps(wk, w.monday);
    return '<div class="hh">' +
      '<div class="hh-k"><span>이번 주 정리 · ' + md(dates[0]) + '~' + md(last.date) + '</span><span class="hh-new wk">' + (holiday ? '휴장' : '주말') + '</span></div>' +
      '<div class="hh-wk3">' +
        tile('코스피 주간', '<b class="' + cls(total) + '">' + pct(total) + '</b>') +
        (sc.length ? tile('시초가 예측', '<b>' + hit + '/' + sc.length + '</b> 적중') : '') +
        (top ? tile('강했던 섹터', '<b>' + esc(top.label) + '</b> <b class="' + cls(top.pct) + '">' + pct(top.pct) + '</b>') : '') +
      '</div>' +
      '<h2 class="hh-h st-h">' + weekStepHead(w.prev, w.week) + '</h2>' +
      '<div class="hh-steps">' + weekSteps(w.prev, w.week) + '</div>' +
      '<p class="hh-dek">코스피는 이번 주 ' + w.week.length + '거래일 중 ' + up + '일 오르고 ' + dn + '일 내려 주간 <b class="' + cls(total) + '">' + pct(total) + '</b>로 마쳤어요.</p>' +
      (us ? us + '<a class="hh-cta ghost" href="/weekly/' + wk.end + '/">주간 장기 리포트 →</a>' : '') +
      '<a class="hh-cta ghost" href="/briefings/">이번 주 브리핑 다시 보기 →</a></div>';
  }

  // ── 구조 신호(§68 ⑤) — 월봉 기준 신호 두 줄(값은 브리핑마다 다시 계산한다). 가장 최근 발행 스냅샷에서만 읽고(옛 날짜로 거슬러 가지 않는다),
  //    그 발행이 STRUCT_MAX_AGE일보다 오래됐으면 수집이 멈춘 것으로 보고 뺀다(§20). 기준 브리핑 날짜를 줄마다 밝힌다.
  var STRUCT_MAX_AGE = 10;
  function daysBetween(a, b) {
    var pa = a.split('-'), pb = b.split('-');
    return Math.round((Date.UTC(+pb[0], +pb[1] - 1, +pb[2]) - Date.UTC(+pa[0], +pa[1] - 1, +pa[2])) / 86400000);
  }
  function latestReady(slots, type, today) {
    var ds = Object.keys(slots || {}).filter(function (d) { return d <= today; }).sort().reverse();
    for (var i = 0; i < ds.length; i++) {
      var it = slots[ds[i]] && slots[ds[i]][type];
      if (it && it.state === 'ready') return daysBetween(ds[i], today) <= STRUCT_MAX_AGE ? ds[i] : null;
    }
    return null;
  }

  // ── 장기 신호(2026-11-09 §68 ⑤ 개정, 시안 docs/prototypes/2026-11-09-home-longterm-entry.html) ──
  //   줄마다 이름·큰 숫자·한 줄 설명·작은 그래프 — 깊은 그래프는 상세 페이지에 있다. 순서: 나스닥 체크 → S&P 500 200일선 → 코스피 체크(사용자 결정).
  //   하루 종일 보인다(장중·마감엔 맨 아래). 값이 없거나 오래된 줄만 빠진다.
  function sg1(v) { return (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(1); }
  // 작은 선 그래프 — zero가 있으면 그 높이에 점선(코스피 0% · S&P 50%). 마지막 점을 찍는다.
  function ltSpark(vals, zero) {
    vals = (vals || []).filter(function (v) { return typeof v === 'number' && isFinite(v); });
    if (vals.length < 2) return '<span class="lt-g"></span>';
    var all = zero == null ? vals : vals.concat([zero]);
    var lo = Math.min.apply(null, all), hi = Math.max.apply(null, all), n = vals.length;
    if (hi === lo) hi = lo + 1;
    var Y = function (v) { return ((hi - v) / (hi - lo) * 100).toFixed(2); };
    var d = vals.map(function (v, i) { return (i ? 'L' : 'M') + (i / (n - 1) * 100).toFixed(2) + ' ' + Y(v); }).join(' ');
    return '<span class="lt-g"><svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">' +
      (zero == null ? '' : '<line x1="0" x2="100" y1="' + Y(zero) + '" y2="' + Y(zero) + '"/>') +
      '<path class="a" d="' + d + ' L100 100 L0 100 Z"/><path class="l" d="' + d + '"/></svg><i style="top:' + Y(vals[n - 1]) + '%"></i></span>';
  }
  function ltRow(href, k, d, v, desc, graph) {
    return '<a class="lt-r" href="' + href + '"><span class="lt-t"><span class="lt-k">' + k + (d ? '<em>' + d + '</em>' : '') + '</span>' +
      '<span class="lt-v">' + v + '</span><span class="lt-d">' + desc + '</span></span>' + graph + '<span class="lt-go" aria-hidden="true">›</span></a>';
  }

  // 나스닥 체크 기준일 — 홈용 작은 파일(asof)·브리핑 스냅샷(last_date) 중 있는 것
  function nqAsof(nq) { var d = nq && (nq.asof || nq.last_date); return /^\d{4}-\d{2}-\d{2}$/.test(d || '') ? d : ''; }
  // 홈용 파일(/data/nasdaq-home.json — 미국 잡·주간 리포트가 씀)과 최근 미국 브리핑 스냅샷 중 기준일이 더 최근인 쪽(2026-11-09).
  // 주말엔 주간 리포트가 금요일 종가로 다시 써서, 장기 신호 세 줄이 같은 날 종가를 보게 된다.
  function pickNasdaq(home, snapNq) {
    var a = nqAsof(home), b = nqAsof(snapNq);
    if (a && (!b || a >= b) && typeof home.gap_pct === 'number') return home;
    return snapNq || (a ? home : null);
  }

  // 나스닥 체크 — 60개월선 대비 월봉 고점 이격. 0·60(주의)·70(경고) 미니 게이지(§65).
  function nasdaqRow(nq, today) {
    if (!nq || typeof nq.gap_pct !== 'number' || !isFinite(nq.gap_pct)) return '';
    var asof = nqAsof(nq);
    if (asof && today && daysBetween(asof, today) > STRUCT_MAX_AGE) return '';   // 수집이 멈췄으면 옛 값을 보여주지 않는다(§20)
    var g = nq.gap_pct, lv = g >= 70 ? ['warn', '🚨 경고', '경고 구간(70% 이상)이에요'] : g >= 60 ? ['caution', '⚠️ 주의', '주의 구간(60~70%)이에요'] : ['ok', '✓ 정상', '주의 기준 60%보다 아래예요'];
    var top = Math.max(80, Math.ceil((g + 5) / 10) * 10);
    var x = function (v) { return (Math.max(0, Math.min(v, top)) / top * 100).toFixed(1) + '%'; };
    var gauge = '<span class="lt-g lt-gg"><span class="t"><i class="z1" style="left:' + x(60) + ';width:' + (10 / top * 100).toFixed(1) + '%"></i>' +
      '<i class="z2" style="left:' + x(70) + ';right:0"></i><u class="' + lv[0] + '" style="left:' + x(g) + '"></u></span>' +
      '<span class="s"><b style="left:0">0</b><b style="left:' + x(60) + '">60</b></span></span>';
    return ltRow('/stocks/nasdaq-check/', '나스닥 체크 · 60개월선 대비 월봉 고점', asof ? md(asof) + '(' + dowOf(asof) + ') 종가' : '',
      sg1(g) + '%<span class="pill ' + lv[0] + '">' + lv[1] + '</span>', lv[2], gauge);
  }

  // S&P 500 200일선 위 종목 비율 — 미국 잡이 쓰는 /data/sp500-home.json(최근 120거래일 흐름). 10일 넘게 멈췄으면 뺀다(§20).
  function sp500Row(sp, today) {
    if (!sp || typeof sp.pct !== 'number' || !/^\d{4}-\d{2}-\d{2}$/.test(sp.asof || '')) return '';
    if (daysBetween(sp.asof, today) > STRUCT_MAX_AGE) return '';
    var med = typeof sp.median_all === 'number' ? sp.median_all : null;
    var cmp = med == null ? '' : '보통(' + med.toFixed(1) + '%)보다 ' + (Math.abs(sp.pct - med) < 1 ? '비슷해요' : sp.pct > med ? '높아요' : '낮아요');
    var cnt = typeof sp.hot === 'number' && typeof sp.deep === 'number' ? '과열 ' + sp.hot + '개, 20%↓ ' + sp.deep + '개' : '';
    return ltRow('/stocks/sp500-200/', 'S&amp;P 500 · 200일선 위 종목 비율', md(sp.asof) + '(' + dowOf(sp.asof) + ') 종가',
      sp.pct.toFixed(1) + '%' + (sp.week && typeof sp.week.pct === 'number' ? '<small>한 주 전 ' + sp.week.pct.toFixed(1) + '%</small>' : ''),
      [cmp, cnt].filter(Boolean).join(' · '), ltSpark(sp.spark, 50));
  }

  // 코스피 체크 — 종가 ÷ 5년(60개월) 평균. 정상·주의·경고를 판정하지 않는다(§68 ⑤). 25년 흐름을 작게.
  function kospiRow(kc, today) {
    if (!kc || typeof kc.gap_pct !== 'number' || !isFinite(kc.gap_pct) || !/^\d{4}-\d{2}-\d{2}$/.test(kc.asof || '')) return '';
    if (daysBetween(kc.asof, today) > STRUCT_MAX_AGE) return '';   // 수집이 멈췄으면 옛 값을 보여주지 않는다(§20)
    var g = kc.gap_pct, ym = kc.year_max && typeof kc.year_max.gap === 'number' ? kc.year_max : null;
    var desc = ym && ym.gap > g + 0.05 ? '올해 ' + (+String(ym.m).slice(5, 7)) + '월 ' + sg1(ym.gap) + '%에서 좁혀졌어요'
             : ym ? '올해 들어 가장 멀어요' : '';
    var series = (Array.isArray(kc.series) ? kc.series : []).map(function (p) { return p && p[1]; });
    return ltRow('/stocks/kospi-check/', '코스피 체크 · 5년 평균과의 거리', md(kc.asof) + '(' + dowOf(kc.asof) + ') 종가',
      sg1(g) + '%', desc, ltSpark(series, 0));
  }

  // 월봉 5개월선 안착 — 첫 종목의 최근 6개월 이격 막대(안착 구간은 파랑, 이번 달은 옅게). 종목이 없으면 줄을 뺀다.
  function ma5Row(m5, ymd, today) {
    if (!m5 || !Array.isArray(m5.items)) return '';
    var head = '<div class="ss-h"><span class="ss-k">월봉 5개월선 안착</span><span class="ss-d">' + esc(dayLabel(ymd, today)) + ' 코스피 브리핑</span></div>';
    var it = m5.items[0];
    if (!it) return '';   // 실을 종목이 없으면 줄째 뺀다 — '없어요' 같은 빈 문구를 쓰지 않는다(사용자 결정 2026-10-27)
    var strip = (it.strip || []).filter(function (s) { return typeof s.gap_pct === 'number'; }).slice(-6);
    var mx = Math.max.apply(null, strip.map(function (s) { return Math.abs(s.gap_pct); }).concat([1]));
    var bars = strip.map(function (s) {
      var h = (Math.abs(s.gap_pct) / mx * 100).toFixed(0);
      return '<span class="m5b' + (s.run ? ' run' : '') + (s.cur ? ' cur' : '') + '" title="' + esc(s.label) + ' ' + pct(s.gap_pct) + '">' +
        '<span class="m5b-u">' + (s.gap_pct > 0 ? '<i style="height:' + h + '%"></i>' : '') + '</span>' +
        '<span class="m5b-d">' + (s.gap_pct < 0 ? '<i style="height:' + h + '%"></i>' : '') + '</span>' +
        '<small>' + esc(s.label) + '</small></span>';
    }).join('');
    var more = m5.items.length > 1 ? ' 외 ' + (m5.items.length - 1) + '종목' : '';
    var now = typeof it.now_gap_pct === 'number' ? '지금 이격 ' + (it.now_gap_pct >= 0 ? '+' : '') + it.now_gap_pct.toFixed(1) + '%' : '';
    return '<a class="ss" href="/briefings/' + ymd + '/kospi/">' + head +
      '<div class="ss-m"><b>' + esc(it.name) + more + '</b>' + (it.streak ? '<span class="pill nb">' + it.streak + '개월째</span>' : '') + '</div>' +
      (strip.length ? '<div class="m5bars">' + bars + '</div>' : '') +
      '<em>월말 종가 ÷ 5개월 평균' + (now ? ' · ' + now : '') + '</em></a>';
  }

  function structHtml(nq, sp, kc, m5, m5Date, today) {
    var rows = nasdaqRow(nq, today) + sp500Row(sp, today) + kospiRow(kc, today) + (m5Date ? ma5Row(m5, m5Date, today) : '');
    return rows ? '<div class="block__h"><span class="block__t"><span class="ic">📐</span>장기 신호</span><span class="block__s">미국 07:30 · 코스피 16:30 갱신</span></div>' +
      rows + '<div class="lt-f"><span>매주 토요일 한 주 정리</span><a href="/weekly/">주간 장기 리포트 ›</a></div>' : '';
  }

  var structEl = document.getElementById('struct-sig');
  // 시간대와 상관없이 같은 줄을 그린다 — 위치만 시간대별로 다르다(stocks-home.css #home.slot-*).
  function loadStruct(slots, today) {
    if (!structEl) return;
    var usD = latestReady(slots, 'us', today), krD = latestReady(slots, 'kospi', today);
    var snap = function (d, t) { return d ? json('/briefings/' + d + '/' + t + '/analysis_snapshot.json') : Promise.resolve(null); };
    return Promise.all([snap(usD, 'us'), snap(krD, 'kospi'), json('/data/home-summary.json'), json('/data/sp500-home.json'),
                        json('/data/nasdaq-home.json')]).then(function (r) {
      var html = structHtml(pickNasdaq(r[4], r[0] && r[0].nasdaq_overheat), r[3], r[2] && r[2].kospi_check, r[1] && r[1].monthly_ma5, krD, today);
      structEl.innerHTML = html;
      structEl.hidden = !html;
    });
  }

  function json(url) {
    return fetch(url, { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; });
  }

  // 개발용 — ?slot=morning|intraday|close|evening|weekend & ?d=YYYY-MM-DD 로 시간대를 바꿔 본다(표시만 바뀐다).
  function devOverride() {
    try {
      var q = new URLSearchParams(location.search), s = q.get('slot');
      return s ? { slot: s, date: q.get('d') || kst(new Date()).ymd } : null;
    } catch (e) { return null; }
  }

  // 개발용 시간대 전환 막대 — ?slot=이 있을 때만 페이지 맨 위에 나온다(운영 화면엔 없다). 누르면 그 시간대로 다시 연다.
  //   날짜는 각 브리핑의 가장 최근 ready 날짜(장중은 날짜 없음, 주말은 오늘).
  var DEV_SLOTS = [['morning', '아침 07:30', 'kospi'], ['intraday', '장중', ''], ['close', '마감 15:30', 'close'],
                   ['evening', '미국 21:15', 'us'], ['weekend', '주말', '']];
  function devBar(cur, slots, today) {
    if (document.getElementById('dev-slot-bar')) return;
    var wrap = document.querySelector('.wrap');
    if (!wrap) return;
    var bar = document.createElement('div');
    bar.id = 'dev-slot-bar';
    bar.innerHTML = '<span>미리보기 · 시간대</span>' + DEV_SLOTS.map(function (d) {
      var ymd = d[2] ? latestReady(slots, d[2], today) : (d[0] === 'weekend' ? today : '');
      var href = '?slot=' + d[0] + (ymd ? '&d=' + ymd : '');
      return '<a href="' + href + '"' + (d[0] === cur ? ' class="on"' : '') + '>' + d[1] + '</a>';
    }).join('');
    wrap.insertBefore(bar, wrap.firstChild);
  }

  var root = document.getElementById('home-hero');
  var home = document.getElementById('home');
  function show(html, slot) {
    if (home) {
      ['morning', 'intraday', 'close', 'evening', 'weekend'].forEach(function (s) { home.classList.toggle('slot-' + s, s === slot); });
      home.classList.toggle('hero-on', !!html);       // 카드가 있으면 대결판(#vs-root)을 숨긴다(CSS)
    }
    if (!root) return;
    root.innerHTML = html || '';
    root.hidden = !html;
  }

  function load() {
    if (document.hidden) return;
    return json('/data/briefings-list.json').then(function (list) {
      var slots = (list && list.slots) || {};
      var ready = function (ymd, t) { return !!(slots[ymd] && slots[ymd][t] && slots[ymd][t].state === 'ready'); };
      var today = kst(new Date()).ymd;
      var info = devOverride() || homeSlot(new Date(), {
        krHoliday: function (ymd) { return !!(window.krIsKospiHolidayOn && window.krIsKospiHolidayOn(ymd)); },
        usReady: function (ymd) { return ready(ymd, 'us'); },
      });
      window.__homeSlot = info.slot;
      if (devOverride()) devBar(info.slot, slots, today);
      loadStruct(slots, today);
      if (info.slot === 'weekend') {
        var p = info.date.split('-'), wd = new Date(Date.UTC(+p[0], +p[1] - 1, +p[2])).getUTCDay();
        var hol = wd >= 1 && wd <= 5 && !!(window.krIsKospiHolidayOn && window.krIsKospiHolidayOn(info.date));
        // 미국 지수 계단은 그 주 금요일의 주간 장기 리포트 데이터에서 읽는다 — 없으면 코스피만 그린다
        return json('/data/home-summary.json').then(function (sm) {
          var w = weekRows(sm && sm.kospi_days);
          var fri = w.monday ? shiftYmd(w.monday, 4) : '';
          return (fri ? json('/weekly/' + fri + '/data.json') : Promise.resolve(null)).then(function (wk) {
            show(cardWeekend(sm, info.date, today, hol, wk), info.slot);
          });
        });
      }
      var type = { morning: 'kospi', close: 'close', evening: 'us' }[info.slot];
      if (!type || !ready(info.date, type)) { show('', info.slot); return; }   // 장중·주말·미발행 — 카드 없음
      var item = slots[info.date][type];
      var snapUrl = '/briefings/' + info.date + '/' + type + '/analysis_snapshot.json';
      var extra = info.slot === 'morning' ? json('/data/accuracy-summary.json') : info.slot === 'close' ? json('/data/home-summary.json') : Promise.resolve(null);
      return Promise.all([json(snapUrl), extra]).then(function (r) {
        var snap = r[0];
        if (!snap) { show('', info.slot); return; }
        var html = info.slot === 'morning' ? cardMorning(snap, info.date, today, r[1] && r[1].kospi, item)
                 : info.slot === 'close' ? cardClose(snap, info.date, today, r[1], item)
                 : cardEvening(snap, info.date, today);
        show(html, info.slot);
      });
    }).catch(function () { show('', null); });
  }

  window.__homeHero = { homeSlot: homeSlot, cardMorning: cardMorning, cardClose: cardClose, cardEvening: cardEvening,
                        morningChip: morningChip, nasdaqChip: nasdaqChip, dekHtml: dekHtml, dayLabel: dayLabel,
                        latestReady: latestReady, nasdaqRow: nasdaqRow, pickNasdaq: pickNasdaq, sp500Row: sp500Row, cardWeekend: cardWeekend, weekSteps: weekSteps, usWeekSteps: usWeekSteps, weekStepHead: weekStepHead, ma5Row: ma5Row, kospiRow: kospiRow, structHtml: structHtml };
  if (!root) return;
  load();
  setInterval(load, 5 * 60 * 1000);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) load(); });
})();
