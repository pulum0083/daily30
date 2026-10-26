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
    var g = nq.gap_pct, lv = g >= 70 ? ['warn', '🚨 경고'] : g >= 60 ? ['caution', '⚠️ 주의'] : ['ok', '✓ 정상'];
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

  // ── 구조 신호(§68 ⑤) — 월 단위로 바뀌는 신호 두 줄. 가장 최근 발행 스냅샷에서만 읽고(옛 날짜로 거슬러 가지 않는다),
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

  // 나스닥 체크 — 60개월선 대비 월봉 고점 이격. 눈금 0·60(주의)·70(경고), 막대는 이격까지, 색은 단계(§65).
  function nasdaqRow(nq, ymd, today) {
    if (!nq || typeof nq.gap_pct !== 'number' || !isFinite(nq.gap_pct)) return '';
    var g = nq.gap_pct, lv = g >= 70 ? ['warn', '🚨 경고'] : g >= 60 ? ['caution', '⚠️ 주의'] : ['ok', '✓ 정상'];
    var top = Math.max(80, Math.ceil((g + 5) / 10) * 10);
    var x = function (v) { return (Math.max(0, Math.min(v, top)) / top * 100).toFixed(1) + '%'; };
    return '<a class="ss" href="/briefings/' + ymd + '/us/">' +
      '<div class="ss-h"><span class="ss-k">나스닥 체크</span><span class="ss-d">' + esc(dayLabel(ymd, today)) + ' 미국 브리핑</span></div>' +
      '<div class="ss-m"><b>' + (g >= 0 ? '+' : '') + g.toFixed(1) + '%</b><span class="pill ' + lv[0] + '">' + lv[1] + '</span></div>' +
      '<div class="nqg"><div class="nqg-t"><i class="z1" style="left:' + x(60) + ';width:' + (10 / top * 100).toFixed(1) + '%"></i>' +
      '<i class="z2" style="left:' + x(70) + ';right:0"></i><i class="f ' + lv[0] + '" style="width:' + x(g) + '"></i>' +
      '<i class="dot ' + lv[0] + '" style="left:' + x(g) + '"></i></div>' +
      '<div class="nqg-l"><span style="left:0">0</span><span style="left:' + x(60) + '">60 주의</span><span style="left:' + x(70) + '">70 경고</span></div></div>' +
      '<em>60개월선 대비 ' + esc(/^\d{4}-\d{2}$/.test(nq.month || '') ? (+nq.month.slice(5)) + '월' : '이번 달') + ' 월봉 고점</em></a>';
  }

  // 월봉 5개월선 안착 — 첫 종목의 최근 6개월 이격 막대(안착 구간은 파랑, 이번 달은 옅게). 종목이 없으면 그 사실을 적는다.
  function ma5Row(m5, ymd, today) {
    if (!m5 || !Array.isArray(m5.items)) return '';
    var head = '<div class="ss-h"><span class="ss-k">월봉 5개월선 안착</span><span class="ss-d">' + esc(dayLabel(ymd, today)) + ' 코스피 브리핑</span></div>';
    var it = m5.items[0];
    if (!it) return '<a class="ss" href="/briefings/' + ymd + '/kospi/">' + head + '<em>조건을 채운 종목이 없어요</em></a>';
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

  function structHtml(nq, nqDate, m5, m5Date, today) {
    var rows = (nqDate ? nasdaqRow(nq, nqDate, today) : '') + (m5Date ? ma5Row(m5, m5Date, today) : '');
    return rows ? '<div class="block__h"><span class="block__t"><span class="ic">🧱</span>구조 신호</span>' +
      '<span class="block__s">월 단위로 바뀌는 신호</span></div>' + rows : '';
  }

  var structEl = document.getElementById('struct-sig');
  function loadStruct(slots, today) {
    if (!structEl) return;
    var usD = latestReady(slots, 'us', today), krD = latestReady(slots, 'kospi', today);
    var snap = function (d, t) { return d ? json('/briefings/' + d + '/' + t + '/analysis_snapshot.json') : Promise.resolve(null); };
    return Promise.all([snap(usD, 'us'), snap(krD, 'kospi')]).then(function (r) {
      var html = structHtml(r[0] && r[0].nasdaq_overheat, usD, r[1] && r[1].monthly_ma5, krD, today);
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
      loadStruct(slots, today);
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
                        latestReady: latestReady, nasdaqRow: nasdaqRow, ma5Row: ma5Row, structHtml: structHtml };
  if (!root) return;
  load();
  setInterval(load, 5 * 60 * 1000);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) load(); });
})();
