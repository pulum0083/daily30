// 브리핑 공용 JS — 다크모드·GNB 시계·접힘 토글·모달·차트 프리미티브

(function () {
  'use strict';

  /* ── 다크모드 ── */
  const root = document.documentElement;
  if (localStorage.getItem('theme') === 'dark') {
    root.classList.replace('light', 'dark');
  }
  function toggleTheme() {
    if (root.classList.contains('dark')) {
      root.classList.replace('dark', 'light');
      localStorage.setItem('theme', 'light');
    } else {
      root.classList.replace('light', 'dark');
      localStorage.setItem('theme', 'dark');
    }
    // 다크모드 전환 시 차트 다시 그리기 (캔버스 색상 갱신)
    if (typeof window.redrawCharts === 'function') window.redrawCharts();
  }

  /* ── GNB 시계 ──
     #gnb-date가 비어 있으면 실시간 시계로 채운다.
     브리핑 페이지는 생성 시각을 미리 채우므로 덮어쓰지 않는다. */
  function updateGnbDate() {
    const el = document.getElementById('gnb-date');
    if (!el || el.textContent.trim()) return;
    const days = ['일', '월', '화', '수', '목', '금', '토'];
    const kst = new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Seoul' }));
    const pad = n => String(n).padStart(2, '0');
    el.textContent =
      `${kst.getFullYear()}.${pad(kst.getMonth() + 1)}.${pad(kst.getDate())} ` +
      `(${days[kst.getDay()]}) ${pad(kst.getHours())}:${pad(kst.getMinutes())}`;
  }

  /* ── 모달 (info-icon) ── */
  function openModal(id) {
    const el = document.getElementById(id);
    if (el) el.classList.add('is-open');
  }
  function closeModal(id) {
    const el = document.getElementById(id);
    if (el) el.classList.remove('is-open');
  }
  function initModals() {
    // [data-modal-open="id"] 클릭 → 열기, 백드롭/[data-modal-close] 클릭 → 닫기
    document.querySelectorAll('[data-modal-open]').forEach(btn => {
      btn.addEventListener('click', () => openModal(btn.dataset.modalOpen));
    });
    document.querySelectorAll('.info-modal-backdrop').forEach(bd => {
      bd.addEventListener('click', e => { if (e.target === bd) bd.classList.remove('is-open'); });
    });
    document.querySelectorAll('[data-modal-close]').forEach(btn => {
      btn.addEventListener('click', () => closeModal(btn.dataset.modalClose));
    });
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') {
        var np = document.getElementById('notice-panel');
        if (np && np.classList.contains('is-open')) { closeNoticePanel(); return; }
        document.querySelectorAll('.info-modal-backdrop.is-open')
          .forEach(bd => bd.classList.remove('is-open'));
      }
    });
  }

  /* ── 차트 프리미티브 ──
     섹션 템플릿이 실데이터를 주입해 호출한다. */
  // 미니 스파크라인 (시장 지표)
  function drawSparkline(id, data, color) {
    const c = document.getElementById(id);
    if (!c || !data || !data.length) return;
    const dpr = window.devicePixelRatio || 1, W = c.offsetWidth || 80, H = c.offsetHeight || 44;
    c.width = W * dpr; c.height = H * dpr;
    const ctx = c.getContext('2d'); ctx.scale(dpr, dpr);
    const min = Math.min(...data), max = Math.max(...data), range = max - min || 1, pad = 2;
    const pts = data.map((v, i) => ({ x: (i / (data.length - 1)) * W, y: H - pad - ((v - min) / range) * (H - pad * 2) }));
    const grad = ctx.createLinearGradient(0, 0, 0, H);
    grad.addColorStop(0, color + '38'); grad.addColorStop(1, color + '00');
    ctx.beginPath(); ctx.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) { const cx = (pts[i - 1].x + pts[i].x) / 2; ctx.bezierCurveTo(cx, pts[i - 1].y, cx, pts[i].y, pts[i].x, pts[i].y); }
    ctx.lineTo(pts.at(-1).x, H); ctx.lineTo(pts[0].x, H); ctx.closePath();
    ctx.fillStyle = grad; ctx.fill();
    ctx.beginPath(); ctx.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) { const cx = (pts[i - 1].x + pts[i].x) / 2; ctx.bezierCurveTo(cx, pts[i - 1].y, cx, pts[i].y, pts[i].x, pts[i].y); }
    ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.stroke();
    ctx.beginPath(); ctx.arc(pts.at(-1).x, pts.at(-1).y, 2.2, 0, Math.PI * 2); ctx.fillStyle = color; ctx.fill();
  }
  // 종목 미니차트 (주가 + 20일선 + 200일선)
  function drawMiniChart(id, prices, ma20, ma200) {
    const c = document.getElementById(id);
    if (!c || !prices || !prices.length) return;
    ma20 = ma20 || [];
    const dpr = window.devicePixelRatio || 1, W = c.offsetWidth || 88, H = c.offsetHeight || 52;
    c.width = W * dpr; c.height = H * dpr;
    const ctx = c.getContext('2d'); ctx.scale(dpr, dpr);
    const all = [...prices, ...ma20, ...(ma200 || [])], minV = Math.min(...all), maxV = Math.max(...all), rng = maxV - minV || 1;
    const pad = { t: 5, b: 5, l: 3, r: 3 }, pW = W - pad.l - pad.r, pH = H - pad.t - pad.b;
    const xf = (i, l) => pad.l + (i / (l - 1)) * pW, yf = v => pad.t + (1 - (v - minV) / rng) * pH;
    if (ma200 && ma200.length) {
      ctx.beginPath(); ctx.setLineDash([4, 3]); ctx.strokeStyle = '#7C3AED'; ctx.lineWidth = 1.8;
      ma200.forEach((v, i) => { i === 0 ? ctx.moveTo(xf(i, ma200.length), yf(v)) : ctx.lineTo(xf(i, ma200.length), yf(v)); });
      ctx.stroke(); ctx.setLineDash([]);
    }
    ctx.beginPath(); ctx.setLineDash([3, 2]); ctx.strokeStyle = '#D97706'; ctx.lineWidth = 1.2;
    ma20.forEach((v, i) => { i === 0 ? ctx.moveTo(xf(i, ma20.length), yf(v)) : ctx.lineTo(xf(i, ma20.length), yf(v)); });
    ctx.stroke(); ctx.setLineDash([]);
    ctx.beginPath();
    prices.forEach((v, i) => { i === 0 ? ctx.moveTo(xf(i, prices.length), yf(v)) : ctx.lineTo(xf(i, prices.length), yf(v)); });
    ctx.lineTo(xf(prices.length - 1, prices.length), H - pad.b); ctx.lineTo(pad.l, H - pad.b); ctx.closePath();
    const g = ctx.createLinearGradient(0, pad.t, 0, H - pad.b);
    g.addColorStop(0, 'rgba(224,49,49,.22)'); g.addColorStop(1, 'rgba(224,49,49,.02)');
    ctx.fillStyle = g; ctx.fill();
    ctx.beginPath(); ctx.strokeStyle = '#E03131'; ctx.lineWidth = 1.6;
    prices.forEach((v, i) => { i === 0 ? ctx.moveTo(xf(i, prices.length), yf(v)) : ctx.lineTo(xf(i, prices.length), yf(v)); });
    ctx.stroke();
    const lx = xf(prices.length - 1, prices.length), ly = yf(prices[prices.length - 1]);
    ctx.beginPath(); ctx.arc(lx, ly, 2.5, 0, Math.PI * 2); ctx.fillStyle = '#E03131'; ctx.fill();
  }

  // 마감 장중 흐름 차트 (고점·저점 라벨 포함)
  function drawCloseChart(id, prices, prevClose) {
    const canvas = document.getElementById(id);
    if (!canvas || !prices || !prices.length) return;
    const dpr = window.devicePixelRatio || 1, W = canvas.parentElement.offsetWidth || 600, H = 104;
    canvas.style.width = W + 'px'; canvas.style.height = H + 'px';
    canvas.width = W * dpr; canvas.height = H * dpr;
    const ctx = canvas.getContext('2d'); ctx.scale(dpr, dpr);
    const base = (prevClose != null) ? prevClose : prices[0];
    const min = Math.min(...prices, base) - 10, max = Math.max(...prices, base) + 10, range = max - min || 1;
    const pad = { t: 24, b: 6, l: 8, r: 8 }, pW = W - pad.l - pad.r, pH = H - pad.t - pad.b;
    const xf = i => pad.l + (i / (prices.length - 1)) * pW, yf = v => pad.t + (1 - (v - min) / range) * pH;
    ctx.beginPath(); ctx.setLineDash([3, 3]); ctx.strokeStyle = 'rgba(100,100,100,.2)'; ctx.lineWidth = 1;
    ctx.moveTo(pad.l, yf(base)); ctx.lineTo(W - pad.r, yf(base)); ctx.stroke(); ctx.setLineDash([]);
    const color = '#2775ED';
    const grad = ctx.createLinearGradient(0, pad.t, 0, H - pad.b);
    grad.addColorStop(0, 'rgba(39,117,237,.18)'); grad.addColorStop(1, 'rgba(39,117,237,.02)');
    ctx.beginPath(); ctx.moveTo(xf(0), yf(prices[0]));
    for (let i = 1; i < prices.length; i++) { const cx = (xf(i - 1) + xf(i)) / 2; ctx.bezierCurveTo(cx, yf(prices[i - 1]), cx, yf(prices[i]), xf(i), yf(prices[i])); }
    ctx.lineTo(xf(prices.length - 1), H - pad.b); ctx.lineTo(xf(0), H - pad.b); ctx.closePath();
    ctx.fillStyle = grad; ctx.fill();
    ctx.beginPath(); ctx.moveTo(xf(0), yf(prices[0]));
    for (let i = 1; i < prices.length; i++) { const cx = (xf(i - 1) + xf(i)) / 2; ctx.bezierCurveTo(cx, yf(prices[i - 1]), cx, yf(prices[i]), xf(i), yf(prices[i])); }
    ctx.strokeStyle = color; ctx.lineWidth = 1.8; ctx.stroke();
    function drawLabel(x, dotY, label, lblColor) {
      ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic';
      const isDark = root.classList.contains('dark');
      const halo = isDark ? 'rgba(28,29,31,0.92)' : 'rgba(255,255,255,0.95)';
      ctx.lineJoin = 'round'; ctx.lineWidth = 3;
      ctx.font = "bold 11px 'Pretendard Variable',sans-serif";
      const tw = ctx.measureText(label).width;
      const lx = Math.min(Math.max(x, tw / 2 + 4), W - tw / 2 - 4);
      ctx.strokeStyle = halo; ctx.strokeText(label, lx, dotY - 12);
      ctx.fillStyle = lblColor; ctx.fillText(label, lx, dotY - 12);
    }
    const hiIdx = prices.indexOf(Math.max(...prices)), loIdx = prices.indexOf(Math.min(...prices));
    ctx.beginPath(); ctx.arc(xf(hiIdx), yf(prices[hiIdx]), 4, 0, Math.PI * 2); ctx.fillStyle = '#E03131'; ctx.fill();
    drawLabel(xf(hiIdx), yf(prices[hiIdx]), '고점 ' + prices[hiIdx].toLocaleString('ko-KR', { minimumFractionDigits: 2 }), '#E03131');
    ctx.beginPath(); ctx.arc(xf(loIdx), yf(prices[loIdx]), 4, 0, Math.PI * 2); ctx.fillStyle = color; ctx.fill();
    drawLabel(xf(loIdx), yf(prices[loIdx]), '저점 ' + prices[loIdx].toLocaleString('ko-KR', { minimumFractionDigits: 2 }), color);
  }

  // 마감 7일 수급 막대 (.flow-chart[data-values] 요소를 렌더)
  function renderFlowChart(el, data) {
    if (!data || !data.length) return;
    const maxAbs = Math.max(...data.map(v => Math.abs(v)), 1);
    const bars = data.map((v, i) => {
      const isToday = i === data.length - 1, isZero = v === 0;
      const dir = isZero ? 'zero' : (v > 0 ? 'up' : 'down');
      const h = Math.round(Math.abs(v) / maxAbs * 100);
      const tip = `${(data.length - 1 - i)}일전: ${v > 0 ? '+' : ''}${v.toLocaleString('ko-KR')}억`;
      return `<div class="flow-bar ${isToday ? 'today' : ''}" title="${tip}"><div class="flow-bar__rect ${dir}" style="height:${isZero ? 2 : h / 2}%"></div></div>`;
    }).join('');
    const axis = data.map((_, i) => {
      const isToday = i === data.length - 1;
      const label = isToday ? '오늘' : (i === data.length - 2 ? '어제' : (data.length - 1 - i) + 'd');
      return `<span class="${isToday ? 'today' : ''}">${label}</span>`;
    }).join('');
    el.innerHTML = `<div class="flow-chart__header">최근 7일</div><div class="flow-chart__bars">${bars}</div><div class="flow-chart__axis">${axis}</div>`;
  }
  function renderSupplyFlows() {
    document.querySelectorAll('.flow-chart[data-values]').forEach(el => {
      try { renderFlowChart(el, JSON.parse(el.dataset.values)); } catch (e) { /* noop */ }
    });
  }

  // 마감 기관 세부 수평 막대
  function renderInstList(containerId, data) {
    const list = document.getElementById(containerId);
    if (!list || !data || !data.length) return;
    const sorted = data.slice().sort((a, b) => b.amt - a.amt);
    const maxAbs = Math.max(...sorted.map(d => Math.abs(d.amt)), 1);
    list.innerHTML = sorted.map(d => {
      const dir = d.amt > 0 ? 'up' : 'down';
      const pct = Math.round(Math.abs(d.amt) / maxAbs * 48);
      return `<div class="inst-bar-row"><span class="inst-bar-row__name">${d.label}</span><div class="inst-bar-row__track"><div class="inst-bar-row__fill ${dir}" style="width:${pct}%"></div></div><span class="inst-bar-row__amt ${dir}">${d.amt > 0 ? '+' : ''}${d.amt.toLocaleString('ko-KR')}억</span></div>`;
    }).join('');
  }

  /* ── 브리핑 목록 전체 동적 재구성 — /data/briefings-list.json (단일 진실원) ──
     정적 HTML에 박힌 "오늘" 날짜는 페이지 생성 시점마다 달라 불일치가 생긴다.
     실제 현재 KST 날짜를 기준으로 목록 전체를 다시 그려 모든 페이지가 동일·최신 상태를 갖게 한다. */
  var BL_LABELS   = { kospi: '코스피 예측', close: '코스피 마감', us: '미국 시장' };
  var BL_TYPES    = ['kospi', 'close', 'us'];
  var BL_SCHEDULE = { kospi: '07:30', close: '16:00', us: '21:20' };
  var BL_DAYS     = ['일', '월', '화', '수', '목', '금', '토'];

  function _blKstToday() {
    var kst = new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Seoul' }));
    return kst.getFullYear() + '-' + String(kst.getMonth() + 1).padStart(2, '0') + '-' + String(kst.getDate()).padStart(2, '0');
  }
  function _blDay(dateStr, full) {
    var p = dateStr.split('-');
    var label = BL_DAYS[new Date(Date.UTC(+p[0], +p[1] - 1, +p[2])).getUTCDay()];
    return full ? label + '요일' : label;
  }
  function _blCurrentPage() {
    var p = location.pathname, m;
    if ((m = p.match(/\/briefings\/(\d{4}-\d{2}-\d{2})\/(kospi|close|us)\//))) return { date: m[1], type: m[2] };
    if ((m = p.match(/\/briefings\/(ko|us|ko-close)\/(\d{4}-\d{2}-\d{2})\//)))
      return { date: m[2], type: m[1] === 'ko' ? 'kospi' : (m[1] === 'us' ? 'us' : 'close') };
    return null;
  }

  function _blSlot(s, lbl, isCurrent) {
    s = s || { state: 'empty' };
    if (s.state === 'pending') {
      return '<div class="bl-slot is-pending"><div class="bl-slot__label">' + lbl + '</div>' +
        '<div class="bl-slot__title">생성 예정</div>' +
        '<div class="bl-slot__meta"><span class="bl-slot__time"><span class="bl-dot"></span> ' + s.scheduled_time + ' 예정</span></div></div>';
    }
    if (s.state === 'ready') {
      var pill = s.pill_text ? '<span class="bl-pill ' + s.pill_cls + '">' + s.pill_text + '</span>' : '';
      var inner = '<div class="bl-slot__label">' + lbl + '</div><div class="bl-slot__title">' + s.title + '</div>' +
        '<div class="bl-slot__meta">' + pill + '<span class="bl-slot__time">' + s.time + '</span></div>';
      return isCurrent
        ? '<div class="bl-slot is-current">' + inner + '</div>'
        : '<a class="bl-slot is-ready" href="' + s.url + '">' + inner + '</a>';
    }
    return '<div class="bl-slot"><div class="bl-slot__label">' + lbl + '</div><div class="bl-slot__title">—</div></div>';
  }
  function _blCell(s, lbl, isCurrent) {
    s = s || { state: 'empty' };
    if (s.state === 'ready') {
      var pill = s.pill_text ? '<span class="bl-pill ' + s.pill_cls + '">' + s.pill_text + '</span>' : '';
      var titleHtml = s.price ? '<div class="bl-cell__title">' + s.price + '</div>' : '';
      var inner = '<div class="bl-cell__label">' + lbl + '</div>' + titleHtml + '<div class="bl-cell__bottom">' + pill + '<span class="bl-cell__time">' + s.time + '</span></div>';
      return isCurrent
        ? '<div class="bl-cell is-current">' + inner + '</div>'
        : '<a class="bl-cell is-ready" href="' + s.url + '">' + inner + '</a>';
    }
    return '<div class="bl-cell is-empty"><div class="bl-cell__label">' + lbl + '</div><div class="bl-cell__bottom"><span class="bl-cell__empty">미생성</span></div></div>';
  }

  function patchBriefingList() {
    var section = document.querySelector('.bottom-list');
    if (!section) return;
    fetch('/data/briefings-list.json', { signal: AbortSignal.timeout(5000) })
      .then(function(r) { return r.ok ? r.json() : Promise.reject(); })
      .then(function(data) {
        var slots = data.slots || {};
        var today = _blKstToday();
        var cur = _blCurrentPage();

        // 오늘 카드 — 현재 KST 날짜 기준 (JSON에 없으면 스케줄 기반 pending)
        var todaySlots = slots[today] || {};
        var todayHtml =
          '<div class="bl-today"><div class="bl-today__head">' +
          '<span class="bl-today__date">' + today + '</span>' +
          '<span class="bl-today__day">' + _blDay(today, true) + '</span></div>' +
          '<div class="bl-today__body">' +
          BL_TYPES.map(function(t) {
            var s = todaySlots[t] || { state: 'pending', scheduled_time: BL_SCHEDULE[t] };
            return _blSlot(s, BL_LABELS[t], cur && cur.date === today && cur.type === t);
          }).join('') +
          '</div></div>';

        // 과거 행 — 오늘 이전 + ready 1개 이상, 최근 10일, 월별 그룹
        var pastDates = Object.keys(slots).filter(function(d) {
          return d < today && BL_TYPES.some(function(t) { return slots[d][t] && slots[d][t].state === 'ready'; });
        }).sort().reverse().slice(0, 10);

        var prevMonth = null, rowsHtml = '';
        pastDates.forEach(function(d) {
          var p = d.split('-');
          var month = (+p[0]) + '년 ' + (+p[1]) + '월';
          if (month !== prevMonth) { rowsHtml += '<div class="bl-month">' + month + '</div>'; prevMonth = month; }
          rowsHtml +=
            '<div class="bl-row"><div class="bl-row__date">' +
            '<span class="bl-row__num">' + d.slice(5) + '</span>' +
            '<span class="bl-row__day">' + _blDay(d, false) + '</span></div>' +
            BL_TYPES.map(function(t) {
              return _blCell(slots[d][t], BL_LABELS[t], cur && cur.date === d && cur.type === t);
            }).join('') +
            '</div>';
        });

        var divider = section.querySelector('.bl-divider');
        section.innerHTML = (divider ? divider.outerHTML : '') + todayHtml + rowsHtml;
      })
      .catch(function() {});
  }

  /* ── 브리핑 페이지 이전/다음 네비게이션 동적 패치 ──
     HTML 생성 시점에 박힌 prev/next URL은 이후 생성된 브리핑을 가리키지 못한다.
     briefings-list.json에서 같은 타입의 ready 날짜 목록을 읽어 버튼을 갱신한다. */
  function patchBriefingNav() {
    var btnPrev = document.getElementById('btn-prev');
    var btnNext = document.getElementById('btn-next');
    if (!btnPrev && !btnNext) return;
    var cur = _blCurrentPage();
    if (!cur) return;

    fetch('/data/briefings-list.json', { signal: AbortSignal.timeout(5000) })
      .then(function(r) { return r.ok ? r.json() : Promise.reject(); })
      .then(function(data) {
        var slots = data.slots || {};
        // 현재 타입의 ready 날짜들을 최신순 정렬
        var dates = Object.keys(slots).filter(function(d) {
          return slots[d][cur.type] && slots[d][cur.type].state === 'ready';
        }).sort().reverse();

        var idx = dates.indexOf(cur.date);
        if (idx === -1) return;

        // 최신순 기준: idx-1 = 더 최신(newer) → btn-next(>), idx+1 = 더 오래됨(older) → btn-prev(<)
        var newerDate = idx > 0 ? dates[idx - 1] : null;
        var olderDate = idx < dates.length - 1 ? dates[idx + 1] : null;

        function applyNav(btn, targetDate) {
          if (!btn) return;
          if (targetDate) {
            btn.href = slots[targetDate][cur.type].url;
            btn.classList.remove('disabled');
          } else {
            btn.setAttribute('href', '#');
            btn.classList.add('disabled');
          }
        }

        applyNav(btnPrev, olderDate);
        applyNav(btnNext, newerDate);
      })
      .catch(function() {});
  }

  /* ── 공지사항 패널 ── */
  function escHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  var NOTICES_URL = '/data/notices.json';
  var NOTICES_LS_KEY = 'ds_read_notices';

  function getReadIds() {
    try { return JSON.parse(localStorage.getItem(NOTICES_LS_KEY) || '[]'); } catch(_) { return []; }
  }
  function saveReadIds(ids) {
    try { localStorage.setItem(NOTICES_LS_KEY, JSON.stringify(ids)); } catch(_) {}
  }

  function noticeBadgeHtml(type) {
    var map = { update: ['업데이트', 'update'], ops: ['운영공지', 'ops'], urgent: ['긴급', 'urgent'] };
    var pair = map[type] || map['update'];
    return '<span class="notice-badge notice-badge--' + pair[1] + '">' + pair[0] + '</span>';
  }

  function renderNotices(notices) {
    var readIds = getReadIds();
    if (!notices.length) {
      return '<p class="notice-panel__empty">공지사항이 없습니다.</p>';
    }
    return notices.slice(0, 10).map(function(n) {
      var unread = readIds.indexOf(n.id) === -1;
      return '<div class="notice-card' + (unread ? ' is-unread' : '') + '">' +
        (unread ? '<div class="notice-card__dot"></div>' : '') +
        '<div class="notice-card__meta">' + noticeBadgeHtml(n.type) +
        '<span class="notice-card__date">' + escHtml(n.date) + '</span></div>' +
        '<div class="notice-card__title">' + escHtml(n.title) + '</div>' +
        '<div class="notice-card__body">' + escHtml(n.body) + '</div>' +
        '</div>';
    }).join('');
  }

  function injectNoticePanel() {
    if (document.getElementById('notice-panel')) return;
    var overlay = document.createElement('div');
    overlay.className = 'notice-overlay';
    overlay.id = 'notice-overlay';
    overlay.addEventListener('click', closeNoticePanel);

    var panel = document.createElement('div');
    panel.className = 'notice-panel';
    panel.id = 'notice-panel';
    panel.innerHTML =
      '<div class="notice-panel__header">' +
        '<span class="notice-panel__title">공지 · 게시판</span>' +
        '<button class="notice-panel__close" onclick="closeNoticePanel()">✕</button>' +
      '</div>' +
      '<div class="notice-panel__tabs">' +
        '<button class="notice-tab is-active" id="tab-btn-notice" onclick="switchPanelTab(\'notice\')">공지사항</button>' +
        '<button class="notice-tab" id="tab-btn-board" onclick="switchPanelTab(\'board\')">게시판</button>' +
      '</div>' +
      '<div class="notice-panel__body" id="notice-panel-body"><p class="notice-panel__empty">불러오는 중...</p></div>' +
      '<div class="board-panel" id="board-panel-body" style="display:none"></div>' +
      '<div class="board-input" id="board-input-area" style="display:none">' +
        '<textarea class="board-input__textarea" id="board-textarea" placeholder="자유롭게 의견을 남겨주세요..."></textarea>' +
        '<button class="board-input__submit" id="board-submit" onclick="submitBoardPost()">등록</button>' +
      '</div>';

    document.body.appendChild(overlay);
    document.body.appendChild(panel);
  }

  function openNoticePanel() {
    injectNoticePanel();
    switchPanelTab('notice');
    var overlay = document.getElementById('notice-overlay');
    var panel = document.getElementById('notice-panel');
    if (overlay) overlay.classList.add('is-open');
    if (panel) panel.classList.add('is-open');
    fetch(NOTICES_URL, { signal: AbortSignal.timeout(5000) })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        var notices = (data && data.notices) || [];
        var body = document.getElementById('notice-panel-body');
        if (body) body.innerHTML = renderNotices(notices);
        var ids = notices.map(function(n) { return n.id; });
        saveReadIds(ids);
        var dot = document.getElementById('gnb-notif-dot');
        if (dot) dot.classList.remove('is-visible');
      })
      .catch(function() {
        var body = document.getElementById('notice-panel-body');
        if (body) body.innerHTML = '<p class="notice-panel__empty">공지를 불러오지 못했습니다.</p>';
      });
  }

  function closeNoticePanel() {
    var overlay = document.getElementById('notice-overlay');
    var panel = document.getElementById('notice-panel');
    if (overlay) overlay.classList.remove('is-open');
    if (panel) panel.classList.remove('is-open');
  }

  var BOARD_JSON_URL   = '/api/board';
  var BOARD_POST_URL   = '/api/board';
  var BOARD_AUTHOR_KEY = 'ds_board_author';
  var BOARD_SEEN_KEY   = 'ds_board_last_seen';

  function getBoardAuthor() {
    var stored = localStorage.getItem(BOARD_AUTHOR_KEY);
    if (stored) return stored;
    var rnd    = Math.random().toString(16).slice(2, 5);
    var author = '익명_' + rnd;
    localStorage.setItem(BOARD_AUTHOR_KEY, author);
    return author;
  }

  function fmtBoardDate(iso) {
    var d   = new Date(iso);
    var kst = new Date(d.getTime() + 9 * 60 * 60 * 1000);
    return (kst.getUTCMonth() + 1) + '/' + kst.getUTCDate() + ' ' +
      String(kst.getUTCHours()).padStart(2, '0') + ':' +
      String(kst.getUTCMinutes()).padStart(2, '0');
  }

  function renderBoardPosts(posts) {
    var originals = posts.filter(function(p) { return !p.parent_id; });
    var replies   = posts.filter(function(p) { return  p.parent_id; });
    if (!originals.length) {
      return '<p class="notice-panel__empty">아직 등록된 글이 없어요.<br>첫 번째 의견을 남겨보세요!</p>';
    }
    return originals.slice().reverse().map(function(p) {
      var myReplies = replies.filter(function(r) { return r.parent_id === p.id; });
      var replyHtml = myReplies.map(function(r) {
        return '<div class="board-reply">' +
          '<div class="board-reply__author">운영AI봇</div>' +
          '<div class="board-reply__content">' + escHtml(r.content) + '</div>' +
          '<div class="board-reply__time">' + fmtBoardDate(r.created_at) + '</div>' +
        '</div>';
      }).join('');
      return '<div class="board-post">' +
        '<div class="board-post__header">' +
          '<span class="board-post__author">' + escHtml(p.author) + '</span>' +
          '<span class="board-post__time">' + fmtBoardDate(p.created_at) + '</span>' +
        '</div>' +
        '<div class="board-post__content">' + escHtml(p.content) + '</div>' +
      '</div>' + replyHtml;
    }).join('');
  }

  function fetchBoard() {
    var body = document.getElementById('board-panel-body');
    if (!body) return;
    body.innerHTML = '<p class="notice-panel__empty">불러오는 중...</p>';
    fetch(BOARD_JSON_URL + '?t=' + Date.now(), { signal: AbortSignal.timeout(8000) })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        var posts = (data && data.posts) || [];
        if (body) body.innerHTML = renderBoardPosts(posts);
        localStorage.setItem(BOARD_SEEN_KEY, new Date().toISOString());
        checkAndShowDot();
      })
      .catch(function() {
        if (body) body.innerHTML = '<p class="notice-panel__empty">불러오지 못했습니다.</p>';
      });
  }

  function switchPanelTab(tab) {
    var noticeBody = document.getElementById('notice-panel-body');
    var boardBody  = document.getElementById('board-panel-body');
    var boardInput = document.getElementById('board-input-area');
    var btnNotice  = document.getElementById('tab-btn-notice');
    var btnBoard   = document.getElementById('tab-btn-board');
    if (!noticeBody || !boardBody) return;

    if (tab === 'board') {
      noticeBody.style.display = 'none';
      boardBody.style.display  = '';
      boardInput.style.display = '';
      if (btnNotice) btnNotice.classList.remove('is-active');
      if (btnBoard)  btnBoard.classList.add('is-active');
      fetchBoard();
    } else {
      noticeBody.style.display = '';
      boardBody.style.display  = 'none';
      boardInput.style.display = 'none';
      if (btnBoard)  btnBoard.classList.remove('is-active');
      if (btnNotice) btnNotice.classList.add('is-active');
    }
  }

  function submitBoardPost() {
    var ta      = document.getElementById('board-textarea');
    var btn     = document.getElementById('board-submit');
    var content = ta ? ta.value.trim() : '';
    if (!content) { if (ta) ta.focus(); return; }
    if (btn) { btn.disabled = true; btn.textContent = '전송 중...'; }

    var author = getBoardAuthor();
    fetch(BOARD_POST_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: content, author: author }),
    })
      .then(function(r) {
        if (!r.ok) throw new Error('fail');
        return r.json();
      })
      .then(function(data) {
        if (ta) ta.value = '';
        if (btn) { btn.disabled = false; btn.textContent = '등록'; }
        // 낙관적 업데이트 — Vercel 재배포 대기 없이 즉시 DOM에 표시
        var body = document.getElementById('board-panel-body');
        if (body && data && data.post) {
          var p = data.post;
          var postHtml =
            '<div class="board-post">' +
              '<div class="board-post__header">' +
                '<span class="board-post__author">' + escHtml(p.author) + '</span>' +
                '<span class="board-post__time">' + fmtBoardDate(p.created_at) + '</span>' +
              '</div>' +
              '<div class="board-post__content">' + escHtml(p.content) + '</div>' +
            '</div>';
          // 빈 목록 메시지를 지우고 새 글 prepend
          var empty = body.querySelector('.notice-panel__empty');
          if (empty) body.innerHTML = '';
          body.insertAdjacentHTML('afterbegin', postHtml);
        }
      })
      .catch(function() {
        if (btn) { btn.disabled = false; btn.textContent = '다시 시도'; }
      });
  }

  function checkAndShowDot() {
    var dot = document.getElementById('gnb-notif-dot');
    if (!dot) return;

    fetch(NOTICES_URL, { signal: AbortSignal.timeout(5000) })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        var notices   = (data && data.notices) || [];
        var readIds   = getReadIds();
        var hasUnread = notices.some(function(n) { return readIds.indexOf(n.id) === -1; });
        if (hasUnread) { dot.classList.add('is-visible'); return; }

        fetch(BOARD_JSON_URL, { signal: AbortSignal.timeout(5000) })
          .then(function(r) { return r.json(); })
          .then(function(boardData) {
            var posts  = (boardData && boardData.posts) || [];
            var seen   = localStorage.getItem(BOARD_SEEN_KEY);
            var hasNew = posts.some(function(p) {
              return !p.parent_id && (!seen || p.created_at > seen);
            });
            if (hasNew) dot.classList.add('is-visible');
          })
          .catch(function() {});
      })
      .catch(function() {
        // 공지 fetch 실패해도 게시판 새글 배지는 확인
        fetch(BOARD_JSON_URL, { signal: AbortSignal.timeout(5000) })
          .then(function(r) { return r.json(); })
          .then(function(boardData) {
            var posts = (boardData && boardData.posts) || [];
            var seen  = localStorage.getItem(BOARD_SEEN_KEY);
            var hasNew = posts.some(function(p) {
              return !p.parent_id && (!seen || p.created_at > seen);
            });
            if (hasNew) dot.classList.add('is-visible');
          })
          .catch(function() {});
      });
  }

  function initNotices() {
    checkAndShowDot();
  }

  /* ── 초기화 ── */
  window.addEventListener('load', () => {
    const params = new URLSearchParams(location.search);
    if (params.get('embed') === '1') document.body.classList.add('is-embed');
    if (params.get('mode') === 'latest') {
      const next = document.getElementById('btn-next');
      if (next) next.classList.add('disabled');
    }
    updateGnbDate();
    setInterval(updateGnbDate, 30000);
    initModals();
    initNotices();
    renderSupplyFlows();
    initLiveScoreboard();
    initLiveMarketPanel();
    loadChipWidget();
    loadVisitorCount();
    patchBriefingList();
    patchBriefingNav();
  });

  /* ── 칩보드 위젯 — /chips/api/prices ── */
  var CHIP_FALLBACK = [
    { flag: '🇰🇷', name: '삼성전자',  market: 'KOSPI' },
    { flag: '🇰🇷', name: 'SK하이닉스', market: 'KOSPI' },
    { flag: '🇺🇸', name: 'Micron',     market: 'NASDAQ' },
    { flag: '🇺🇸', name: 'AMD',        market: 'NASDAQ' },
    { flag: '🇺🇸', name: 'Intel',      market: 'NASDAQ' },
  ];
  function formatChipPrice(price, market) {
    if (price == null) return '—';
    if (market === 'KOSPI') return price.toLocaleString('ko-KR');
    return '$' + price.toFixed(2);
  }
  function renderChipRow(flag, name, price, chg, dir) {
    const row = document.createElement('div');
    row.className = 'chip-row';
    row.innerHTML =
      '<span class="chip-row__flag">' + flag + '</span>' +
      '<span class="chip-row__name">' + name + '</span>' +
      '<span class="chip-row__price">' + price + '</span>' +
      '<span class="chip-row__chg ' + dir + '">' + chg + '</span>';
    return row;
  }
  function loadVisitorCount() {
    var opinionBtn = document.querySelector('.sidebar-opinion-btn');
    if (!opinionBtn) return;
    fetch('/api/visitors', { signal: AbortSignal.timeout(5000) })
      .then(function(r) { return r.ok ? r.json() : Promise.reject(); })
      .then(function(data) {
        if (!data.pageViews) return;
        var existing = document.getElementById('sidebar-visitors');
        if (!existing) {
          var wrap = document.createElement('div');
          wrap.id = 'sidebar-visitors';
          wrap.className = 'sidebar-visitors';
          wrap.innerHTML =
            '<span class="sidebar-visitors__label">누적 페이지뷰</span>' +
            '<span class="sidebar-visitors__count" id="sidebar-visitors-count"></span>';
          opinionBtn.closest('.sidebar-footer').insertAdjacentElement('afterend', wrap);
          existing = wrap;
        }
        var countEl = existing.querySelector('.sidebar-visitors__count') || document.getElementById('sidebar-visitors-count');
        if (countEl) countEl.textContent = data.pageViews.toLocaleString('ko-KR') + '회';
        existing.style.display = '';
      })
      .catch(function() {});
  }

  /* ── 라이브 스코어보드 아코디언 ── */
  function lsbToggleAccordion() {
    var btn  = document.getElementById('lsb-accordion-btn');
    var body = document.getElementById('lsb-accordion-body');
    if (!btn || !body) return;
    var isOpen = body.classList.contains('open');
    body.classList.toggle('open', !isOpen);
    btn.classList.toggle('open', !isOpen);
    var left = btn.querySelector('.lsb-ac-left');
    if (!left) return;
    if (!isOpen) {
      // 열기 — 현재 표시 중인 time/title을 dataset에 저장 후 레이블 교체
      var t = left.querySelector('.lsb-ac-prev-time, #lsb-ac-prev-time');
      var ti = left.querySelector('.lsb-ac-prev-title, #lsb-ac-prev-title');
      btn.dataset.savedTime  = t  ? t.textContent  : (btn.dataset.savedTime  || '');
      btn.dataset.savedTitle = ti ? ti.textContent : (btn.dataset.savedTitle || '');
      left.innerHTML = '<span class="lsb-ac-collapse-label">목록 닫기</span>';
    } else {
      // 닫기 — 고정 레이블
      left.innerHTML = '<span class="lsb-ac-collapse-label">이슈 히스토리 보기</span>';
    }
  }
  window.lsbToggleAccordion = lsbToggleAccordion;

  /* ── 라이브 스코어보드 초기화 ── */
  function initLiveScoreboard() {
    var el = document.getElementById('live-scoreboard');
    if (!el) return;

    var dir     = el.dataset.dir || 'up';   // 'up' | 'dn'

    function kstNow() {
      return new Date(Date.now() + 9 * 3600 * 1000);
    }
    function isPreOpen() {
      var k = kstNow(), day = k.getUTCDay();
      if (day === 0 || day === 6) return false;
      var mins = k.getUTCHours() * 60 + k.getUTCMinutes();
      return mins >= 530 && mins < 540;   // 08:50~08:59
    }
    function isMarketHours() {
      var k = kstNow(), day = k.getUTCDay();
      if (day === 0 || day === 6) return false;
      var mins = k.getUTCHours() * 60 + k.getUTCMinutes();
      return mins >= 530 && mins < 930;   // 08:50~15:29 (준비 중 포함)
    }
    function isAfterMarket() {
      var k = kstNow(), day = k.getUTCDay();
      if (day === 0 || day === 6) return false;
      var mins = k.getUTCHours() * 60 + k.getUTCMinutes();
      return mins >= 930;
    }

    // 당일 브리핑에서만 표시 — URL의 날짜와 오늘 KST 날짜 비교
    var m = location.pathname.match(/\/briefings\/(\d{4}-\d{2}-\d{2})\//);
    if (m) {
      var k = kstNow();
      var todayKst = k.getUTCFullYear() + '-' +
        String(k.getUTCMonth() + 1).padStart(2, '0') + '-' +
        String(k.getUTCDate()).padStart(2, '0');
      if (m[1] !== todayKst) return;
    }

    if (!isMarketHours() && !isAfterMarket()) return;
    el.style.display = '';

    // isAfterMarket() 조기 return 이전에 선언 — updateDisplay() 콜백에서 참조하므로 반드시 앞에 있어야 함
    function calcVerdict(changePct) {
      if (Math.abs(changePct) <= 0.1) return 'tight';
      if (dir === 'up'  && changePct >  0.1) return 'hit';
      if (dir === 'dn'  && changePct < -0.1) return 'hit';
      return 'miss';
    }
    var VERDICT_MSGS = {
      up: {
        hit:  ['예측대로 흘러가는 중', '시나리오대로 전개 중', '방향 정확히 맞아가는 중', '분석대로네요',
               '예측이 맞아떨어지는 중', '오늘 전망 적중', '오늘 AI 컨디션 좋네요', '예측대로 움직이고 있어요'],
        miss: ['빗나가는 중', '예상 밖 흐름', '예측과 반대로 흘러가는 중',
               '오늘은 시장이 다른 말을 하고 있어요', '변수가 생긴 것 같아요', '시장이 예측을 무시하고 있어요'],
      },
      dn: {
        hit:  ['예측대로 흘러가는 중', '분석대로네요', '예측대로 움직이고 있어요'],
        miss: ['빗나가는 중, 다행이예요', '예상 밖 흐름', '예측과 반대로 오르는 중',
               '변수가 생긴 것 같아요, 좋은 징조', '예측은 틀렸지만 반가운 흐름',
               '오늘은 틀려서 기분 좋은 날', '시장이 좋은 의미로 예측을 깨고 있어요',
               '하락 예측이지만 시장은 반가운 반란 중', '틀렸는데 기쁜 날',
               '이런 날은 틀려도 괜찮아요', '예측보다 시장이 더 건강하네요', '나쁜 예측이 틀려서 다행이에요'],
      },
      tight: ['팽팽한 접전', '박빙 승부', '아슬아슬한 줄타기', '오차 범위 안에서 흘러가는 중', '중립 부근 공방 중'],
    };
    var VERDICT_META = {
      hit:   { prefix: '',          color: 'var(--up)',   bg: 'var(--up-bg)' },
      tight: { prefix: '',          color: 'var(--gold)', bg: 'var(--gold-bg)' },
      miss:  { prefix: '',          color: 'var(--dn)',   bg: 'var(--dn-bg)' },
    };

    // ── 마감 후 상태 ──
    if (isAfterMarket()) {
      var badge = document.getElementById('lsb-badge');
      if (badge) { badge.className = 'lsb-closed-badge'; badge.textContent = '마감'; }
      var footElC = document.getElementById('lsb-foot');
      if (footElC) footElC.innerHTML = '<strong>마감</strong>';
      // fetchKospi 실패 시 폴백 — 먼저 세팅 후 데이터 오면 덮어씀
      var emElA = document.getElementById('lsb-head-em');
      if (emElA) { emElA.textContent = '오늘 장이 종료됐어요.'; emElA.style.color = ''; emElA.style.fontWeight = '700'; }
      var subElA = document.getElementById('lsb-sub');
      if (subElA) subElA.textContent = '최종 종가 확인 중…';
      fetchKospi();
      fetchNews();
      return;
    }

    // ── 준비 중 상태 (08:50~08:59) ──
    if (isPreOpen()) {
      var badge2 = document.getElementById('lsb-badge');
      if (badge2) { badge2.className = 'lsb-pre-badge'; badge2.textContent = '준비 중'; }
      var headEl0 = document.getElementById('lsb-headline');
      if (headEl0) { headEl0.textContent = '장 시작 준비 중'; headEl0.style.color = 'var(--muted)'; }
      var subEl0 = document.getElementById('lsb-sub');
      if (subEl0) subEl0.textContent = '09:00 장 시작과 함께 실시간 추적을 시작합니다.';
      function updatePreOpenTimer() {
        var kp = kstNow();
        var open = new Date(kp);
        open.setUTCHours(9, 0, 0, 0);
        if (open <= kp) { window.location.reload(); return; }
        var diff2 = open - kp;
        var mm = Math.floor(diff2 / 60000);
        var ss = Math.floor((diff2 % 60000) / 1000);
        var footElP = document.getElementById('lsb-foot');
        if (footElP) footElP.innerHTML = '장 시작까지 <strong>' + mm + ':' + String(ss).padStart(2, '0') + '</strong>';
      }
      updatePreOpenTimer();
      setInterval(updatePreOpenTimer, 1000);
      fetchNews();
      return;
    }

    function pickMsg(verdict) {
      if (verdict === 'tight') {
        var t = VERDICT_MSGS.tight;
        return t[Math.floor(Math.random() * t.length)];
      }
      var list = VERDICT_MSGS[dir][verdict];
      return list[Math.floor(Math.random() * list.length)];
    }

    var odoState = null;
    var odoReady = false;

    function odometerUpdate(container, numStr) {
      var chars = numStr.split('');
      var fmt   = numStr.replace(/[0-9]/g, 'D');

      if (!odoState || odoState.fmt !== fmt) {
        container.innerHTML = '';
        odoState = { fmt: fmt, inners: [] };
        odoReady = false;
        for (var i = 0; i < chars.length; i++) {
          var ch = chars[i];
          if (ch >= '0' && ch <= '9') {
            var col   = document.createElement('span');
            col.className = 'lsb-odo-digit';
            var inner = document.createElement('span');
            inner.className = 'lsb-odo-inner';
            for (var d = 0; d <= 9; d++) {
              var s = document.createElement('span');
              s.textContent = d;
              inner.appendChild(s);
            }
            col.appendChild(inner);
            container.appendChild(col);
            odoState.inners.push(inner);
          } else {
            var sep = document.createElement('span');
            sep.className = 'lsb-odo-sep';
            sep.textContent = ch;
            container.appendChild(sep);
          }
        }
      }

      var innerIdx = 0;
      for (var j = 0; j < chars.length; j++) {
        if (chars[j] >= '0' && chars[j] <= '9') {
          var digit = parseInt(chars[j]);
          var inn   = odoState.inners[innerIdx++];
          inn.style.transition = odoReady ? 'transform 0.55s cubic-bezier(0.22,0.68,0,1.2)' : 'none';
          inn.style.transform  = 'translateY(-' + (digit * 10) + '%)';
        }
      }
      if (!odoReady) { requestAnimationFrame(function() { odoReady = true; }); }
    }

    function updateDisplay(price, changePct) {
      var verdict = calcVerdict(changePct);
      var v = VERDICT_META[verdict];
      var em = pickMsg(verdict);

      var idxEl     = document.getElementById('lsb-idx');
      var chgEl     = document.getElementById('lsb-chg');
      var headEl    = document.getElementById('lsb-headline');
      var needleEl  = document.getElementById('lsb-needle');
      var predTagEl = document.getElementById('lsb-pred-tag');

      if (idxEl) {
        odometerUpdate(idxEl, price.toLocaleString('ko-KR', {minimumFractionDigits:2, maximumFractionDigits:2}));
      }

      var sign = changePct >= 0 ? '+' : '';
      if (chgEl) {
        chgEl.textContent = sign + changePct.toFixed(2) + '%';
        chgEl.style.color = changePct >= 0 ? 'var(--up)' : 'var(--dn)';
      }

      var prefixEl = document.getElementById('lsb-head-prefix');
      var emEl     = document.getElementById('lsb-head-em');
      if (isAfterMarket()) {
        // 장 마감: 메인=예측 결과 요약, 보조=등락률 한 줄
        if (prefixEl) prefixEl.textContent = '';
        if (headEl)   headEl.style.color = '';
        var sign = changePct >= 0 ? '+' : '';
        var pct  = sign + changePct.toFixed(2) + '%';
        // 대표 타이틀(emEl)과 서브 타이틀(subElU)을 각각 분리 관리
        // hit.dn(하락 예측 적중)은 아쉬움 표현을 대표 타이틀 뒤에 붙인다
        var CLOSE_MSGS = {
          hit: {
            up: {
              title: ['상승 예측이 맞았어요.',
                      '예측대로 올랐어요.',
                      'AI가 맞혔어요.',
                      '오늘은 시장이 예측을 따랐어요.',
                      '기분 좋은 적중이에요.',
                      '예측 적중, 좋은 하루였어요.'],
              sub:   [pct + ' 상승 마감이에요.', pct + ' 상승으로 마감했어요.'],
            },
            dn: {
              title: ['하락 예측이 맞았어요. 아쉬운 하루였어요.',
                      '하락 예측이 맞았어요. 내일은 반등을 기대해요.',
                      '하락 예측이 맞았어요. 오늘은 아쉬운 날이에요.',
                      '하락 예측이 맞았어요. 그래도 내일이 있어요.',
                      '하락 예측이 맞았어요. 시장이 참 야속하네요.',
                      '하락 예측이 맞았어요. 이런 날도 있는 법이에요.',
                      '하락 예측이 맞았어요. 내일은 더 나아지길 바라요.',
                      '하락 예측이 맞았어요. 쉬어가는 하루였어요.'],
              sub:   [pct + ' 하락 마감이에요.', pct + ' 하락으로 마감했어요.'],
            },
          },
          miss: {
            up: {
              title: ['아쉽게도 예측이 빗나갔어요.',
                      '상승을 기대했는데 빗나갔어요.',
                      '오늘은 AI도 시장을 못 이겼어요.',
                      '시장이 예측을 무시했어요.',
                      '예측이 틀렸어요. 다음엔 더 잘 볼게요.',
                      '상승을 봤는데 시장은 반대로 갔어요.'],
              sub:   [pct + ' 하락 마감이에요.',
                      pct + ' 하락으로 마감했어요.',
                      pct + ' 하락이에요. 시장이 더 강했어요.'],
            },
            dn: {
              title: ['이번엔 AI가 틀렸어요.',
                      '예측은 빗나갔지만 좋은 결과예요.',
                      '틀려서 다행인 날이에요.',
                      '하락을 경고했는데 시장이 반란을 일으켰어요.',
                      'AI가 틀렸고 시장이 올랐어요.',
                      '기분 좋은 오답이에요.',
                      '이런 오답이라면 언제든 환영해요.'],
              sub:   [pct + ' 상승 마감이에요.',
                      pct + ' 올랐어요. 기분 좋은 오답이에요.',
                      pct + ' 상승으로 마감했어요.'],
            },
          },
          tight: {
            title: ['박빙으로 마감했어요.',
                    '오차 범위 안에서 마감했어요.',
                    '예측과 거의 일치했어요.',
                    '시장이 방향을 못 정한 하루였어요.',
                    '팽팽하게 맞섰어요.'],
            sub:   [pct + '로 중립에 가까웠어요.',
                    pct + ' 변동으로 중립 마감했어요.',
                    pct + ', 상승도 하락도 아닌 하루였어요.'],
          },
        };
        var pool = verdict === 'tight' ? CLOSE_MSGS.tight : CLOSE_MSGS[verdict][dir];
        var idx = Math.floor(Math.random() * pool.title.length);
        var closeTitle = pool.title[idx];
        var closeSub   = pool.sub[idx % pool.sub.length];
        if (emEl) { emEl.textContent = closeTitle; emEl.style.color = ''; emEl.style.fontWeight = '700'; }
        var subElU = document.getElementById('lsb-sub');
        if (subElU) { subElU.textContent = closeSub; subElU.style.color = ''; subElU.style.fontWeight = ''; }
      } else {
        if (prefixEl) prefixEl.textContent = v.prefix;
        if (emEl)     { emEl.textContent = em; emEl.style.color = v.color; emEl.style.fontWeight = '600'; }
        if (headEl)   headEl.style.color = '';
      }

      // 바늘 위치: 예측 방향 기준으로 0(이탈)~100(적중) 매핑, ±2% 포화
      var rawPos;
      if (dir === 'up') {
        rawPos = Math.max(0, Math.min(100, (changePct + 2) / 4 * 100));
      } else {
        rawPos = Math.max(0, Math.min(100, (-changePct + 2) / 4 * 100));
      }
      if (needleEl) needleEl.style.left = rawPos + '%';

      if (predTagEl) {
        var predBg  = dir === 'dn' ? 'var(--dn-bg)' : 'var(--up-bg)';
        var predClr = dir === 'dn' ? 'var(--dn)'    : 'var(--up)';
        predTagEl.style.background = predBg;
        predTagEl.style.color = predClr;
      }
    }

    var refreshSecs = 10;

    function tickRefreshCount() {
      var el = document.getElementById('lsb-refresh-count');
      if (!el) return;
      refreshSecs = Math.max(0, refreshSecs - 1);
      el.textContent = refreshSecs + '초';
    }

    function fetchKospi() {
      refreshSecs = 10;
      var el = document.getElementById('lsb-refresh-count');
      if (el) el.textContent = '10초';
      fetch('/api/kospi-live')
        .then(function(r) { return r.ok ? r.json() : Promise.reject(); })
        .then(function(d) { if (d && d.price) updateDisplay(d.price, d.changePct || 0); })
        .catch(function() {});
    }

    function renderNews(d) {
      if (!d || !d.latest) return;
      var stampEl    = document.getElementById('lsb-news-stamp');
      var latestEl   = document.getElementById('lsb-news-latest');
      var accordionEl = document.getElementById('lsb-accordion');
      var bodyEl     = document.getElementById('lsb-accordion-body');
      var prevTimeEl = document.getElementById('lsb-ac-prev-time');
      var prevTitleEl= document.getElementById('lsb-ac-prev-title');

      if (stampEl) {
        stampEl.innerHTML = '<span style="color:var(--primary);font-weight:700">방금 업데이트</span>'
          + ' · ' + escHtml(d.updated_at) + ' 기준 · 매 30분 갱신';
      }
      if (latestEl) {
        latestEl.innerHTML = '<div class="lsb-news-card">'
          + '<div class="lsb-news-title">' + escHtml(d.latest.title) + '</div>'
          + '<div class="lsb-news-body">'  + escHtml(d.latest.summary) + '</div>'
          + '</div>';
      }

      var hist = (d.history || []).filter(function(item) {
        return item.title && item.title !== '오늘의 이슈 준비 중';
      });
      if (accordionEl) {
        accordionEl.style.display = '';
        if (hist.length > 0) {
          if (prevTimeEl)  prevTimeEl.textContent  = hist[0].time;
          if (prevTitleEl) prevTitleEl.textContent = hist[0].title;
          // 이전 이슈 기본 펼침
          var btnEl = document.getElementById('lsb-accordion-btn');
          if (bodyEl && btnEl && !bodyEl.classList.contains('open')) {
            bodyEl.classList.add('open');
            btnEl.classList.add('open');
            var leftEl = btnEl.querySelector('.lsb-ac-left');
            if (leftEl) leftEl.innerHTML = '<span class="lsb-ac-collapse-label">목록 닫기</span>';
          }
          if (bodyEl) {
            bodyEl.innerHTML = hist.map(function(item) {
              return '<div class="lsb-news-item">'
                + '<span class="lsb-ni-time">' + escHtml(item.time) + '</span>'
                + '<div class="lsb-ni-content">'
                + '<div class="lsb-ni-title">' + escHtml(item.title) + '</div>'
                + (item.summary ? '<div class="lsb-ni-body">' + escHtml(item.summary) + '</div>' : '')
                + '</div>'
                + '</div>';
            }).join('');
          }
        } else {
          if (prevTimeEl)  prevTimeEl.textContent  = '';
          if (prevTitleEl) prevTitleEl.textContent = '이슈 히스토리';
          if (bodyEl) bodyEl.innerHTML = '<div style="padding:12px 0;font-size:13px;color:var(--muted)">이전 이슈 내용이 쌓이게 되어요.</div>';
        }
      }
    }

    function fetchNews() {
      fetch('/data/kospi-news-live.json?t=' + Date.now())
        .then(function(r) { return r.ok ? r.json() : Promise.reject(); })
        .then(renderNews)
        .catch(function() {});
    }

    function updateCountdown() {
      var k = kstNow();
      var close = new Date(k);
      close.setUTCHours(15, 30, 0, 0);   // 15:30 KST = shifted space 15:30
      var cdEl = document.getElementById('lsb-countdown');
      if (close <= k) {
        if (cdEl) cdEl.textContent = '마감';
        return;
      }
      var diff = close - k;
      var h = Math.floor(diff / 3600000);
      var m = Math.floor((diff % 3600000) / 60000);
      var s = Math.floor((diff % 60000) / 1000);
      if (cdEl) cdEl.textContent = h + ':' + String(m).padStart(2,'0') + ':' + String(s).padStart(2,'0');
    }

    fetchKospi();
    fetchNews();
    updateCountdown();

    if (isMarketHours()) {
      setInterval(fetchKospi, 10000);
      setInterval(fetchNews, 5 * 60000);
      setInterval(updateCountdown, 1000);
      setInterval(tickRefreshCount, 1000);
    }
  }

  function loadChipWidget() {
    var container = document.getElementById('chip-stocks');
    if (!container) return;
    fetch('/chips/api/prices', { signal: AbortSignal.timeout(5000) })
      .then(function(r) { return r.ok ? r.json() : Promise.reject(); })
      .then(function(stocks) {
        if (!Array.isArray(stocks) || !stocks.length) throw new Error();
        stocks.slice(0, 5).forEach(function(s) {
          var rate  = typeof s.changeRate === 'number' ? s.changeRate : 0;
          var dir   = rate > 0 ? 'up' : rate < 0 ? 'down' : 'flat';
          var arrow = rate > 0 ? '▲' : rate < 0 ? '▼' : '';
          var chg   = arrow + Math.abs(rate).toFixed(2) + '%';
          var flag  = s.market === 'KOSPI' ? '🇰🇷' : '🇺🇸';
          container.appendChild(renderChipRow(flag, s.name, formatChipPrice(s.price, s.market), chg, dir));
        });
      })
      .catch(function() {
        CHIP_FALLBACK.forEach(function(s) {
          container.appendChild(renderChipRow(s.flag, s.name, '—', '—', 'flat'));
        });
      });
  }

  /* ── 장 중 실시간 시장 지표 패널 ── */
  function initLiveMarketPanel() {
    var panel = document.getElementById('market-data-panel');
    if (!panel) return;
    // 코스피 아침 브리핑(live-scoreboard 포함)에서만 활성화
    if (!document.getElementById('live-scoreboard')) return;

    // KST 기준 오늘 평일 09:00 이후인지 확인
    function isLiveMode() {
      var k = new Date(Date.now() + 9 * 3600 * 1000);
      var day = k.getUTCDay();
      if (day === 0 || day === 6) return false;
      return k.getUTCHours() * 60 + k.getUTCMinutes() >= 530; // 08:50 KST
    }
    function isDuringMarket() {
      var k = new Date(Date.now() + 9 * 3600 * 1000);
      var mins = k.getUTCHours() * 60 + k.getUTCMinutes();
      return mins >= 530 && mins < 930; // 08:50~15:29
    }

    if (!isLiveMode()) return;

    var sparkData = { kosdaq: [], kospi200: [], forex: [] };
    var polling = null;

    function fmt(n, dp) {
      return n.toLocaleString('ko-KR', { minimumFractionDigits: dp, maximumFractionDigits: dp });
    }
    function chgClass(pct) { return pct > 0 ? 'up' : pct < 0 ? 'down' : ''; }
    function chgText(pct)  { return (pct > 0 ? '+' : '') + pct.toFixed(2) + '%'; }
    function supplyBarPct(val, maxAbs) { return Math.min(48, Math.abs(val) / maxAbs * 48); }

    function updateStatusLabel() {
      var labelEl = panel.querySelector('.mkt-live-label');
      var dotEl   = panel.querySelector('.mkt-live-dot');
      if (!labelEl) return;
      var during = isDuringMarket();
      labelEl.textContent = during ? '실시간' : '장 마감';
      if (dotEl) dotEl.style.display = during ? '' : 'none';
    }

    function scheduleCloseLabel() {
      var k    = new Date(Date.now() + 9 * 3600 * 1000);
      var mins = k.getUTCHours() * 60 + k.getUTCMinutes();
      var msLeft = (930 - mins) * 60 * 1000 - (k.getUTCSeconds() * 1000);
      if (msLeft > 0) setTimeout(updateStatusLabel, msLeft);
    }

    function buildPanel() {
      var header = panel.querySelector('.panel-header');
      if (header) {
        var during = isDuringMarket();
        header.querySelector('.pub-time').outerHTML =
          '<span class="pub-time mkt-live-time">' +
          '<span class="mkt-live-dot"' + (during ? '' : ' style="display:none"') + '></span>' +
          '<span class="mkt-live-label">' + (during ? '실시간' : '장 마감') + '</span>' +
          '</span>';
      }

      var list = panel.querySelector('.mkt-list');
      list.innerHTML =
        // 수급
        '<div class="mkt-section-label">오늘 수급 · 코스피</div>' +
        '<div class="mkt-list" id="mkt-live-supply" style="padding:0 14px">' +
        mkSupplyRow('frgn', '외국인') +
        mkSupplyRow('inst', '기관') +
        mkSupplyRow('indv', '개인') +
        '</div>' +
        // 국내 지수
        '<div class="mkt-section-label">국내 지수</div>' +
        '<div id="mkt-live-rows">' +
        mkIndexRow('kosdaq',  '코스닥',         '') +
        mkIndexRow('kospi200','코스피200', '<span class="mkt-name-badge futures">IDX</span>') +
        '</div>' +
        // 환율
        '<div class="mkt-section-label">환율</div>' +
        '<div id="mkt-live-fx">' +
        '<div class="mkt-row">' +
        '<div class="mkt-row-info">' +
        '<span class="mkt-name" style="display:flex;align-items:center;gap:4px">' +
        '원/달러<span class="mkt-name-badge fx">FX</span></span>' +
        '<div class="mkt-vals">' +
        '<div class="mkt-val" id="ml-fx-val">—</div>' +
        '<div class="mkt-chg" id="ml-fx-chg">—</div>' +
        '</div></div>' +
        '<div class="mkt-spark"><canvas id="ml-fx-spark"></canvas></div>' +
        '</div></div>';
    }

    function mkIndexRow(key, label, badge) {
      return '<div class="mkt-row">' +
        '<div class="mkt-row-info">' +
        '<span class="mkt-name" style="display:flex;align-items:center;gap:4px">' + label + badge + '</span>' +
        '<div class="mkt-vals">' +
        '<div class="mkt-val" id="ml-' + key + '-val">—</div>' +
        '<div class="mkt-chg" id="ml-' + key + '-chg">—</div>' +
        '</div></div>' +
        '<div class="mkt-spark"><canvas id="ml-' + key + '-spark"></canvas></div>' +
        '</div>';
    }

    function mkSupplyRow(key, label) {
      return '<div class="supply-row">' +
        '<div class="supply-info">' +
        '<div class="supply-name">' + label + '</div>' +
        '<div class="supply-vals">' +
        '<span class="supply-val" id="ml-' + key + '-val">—</span>' +
        '<span class="supply-unit">억</span>' +
        '</div></div>' +
        '<div class="supply-bar-outer">' +
        '<div class="supply-bar-center">' +
        '<div class="supply-bar-fill2" id="ml-' + key + '-bar" style="width:0%"></div>' +
        '</div>' +
        '<div class="supply-bar-labels">' +
        '<span style="color:var(--dn)">매도</span>' +
        '<span style="color:var(--up)">매수</span>' +
        '</div></div></div>';
    }

    function applyData(d) {
      // 지수
      ['kosdaq', 'kospi200'].forEach(function(key) {
        var src = d[key];
        if (!src) return;
        var valEl = document.getElementById('ml-' + key + '-val');
        var chgEl = document.getElementById('ml-' + key + '-chg');
        if (!valEl) return;
        var prev = parseFloat(valEl.textContent.replace(/[,—]/g, '')) || 0;
        var newVal = src.price;
        valEl.textContent = fmt(newVal, 2);
        chgEl.textContent = chgText(src.changePct);
        chgEl.className   = 'mkt-chg ' + chgClass(src.changePct);
        if (prev) {
          valEl.classList.remove('mkt-flash-up', 'mkt-flash-dn');
          void valEl.offsetWidth;
          valEl.classList.add(newVal > prev ? 'mkt-flash-up' : 'mkt-flash-dn');
        }
        sparkData[key].push(newVal);
        if (sparkData[key].length > 30) sparkData[key].shift();
        if (sparkData[key].length >= 2) drawSparkline('ml-' + key + '-spark', sparkData[key], '#2775ED');
      });

      // 환율
      if (d.forex) {
        var fxVal = document.getElementById('ml-fx-val');
        var fxChg = document.getElementById('ml-fx-chg');
        if (fxVal) {
          var prevFx = parseFloat(fxVal.textContent.replace(/[,—]/g, '')) || 0;
          fxVal.textContent = fmt(d.forex.price, 2);
          fxChg.textContent = chgText(d.forex.changePct);
          fxChg.className   = 'mkt-chg ' + chgClass(d.forex.changePct);
          if (prevFx) {
            fxVal.classList.remove('mkt-flash-up', 'mkt-flash-dn');
            void fxVal.offsetWidth;
            fxVal.classList.add(d.forex.price > prevFx ? 'mkt-flash-up' : 'mkt-flash-dn');
          }
        }
        sparkData.forex.push(d.forex.price);
        if (sparkData.forex.length > 30) sparkData.forex.shift();
        if (sparkData.forex.length >= 2) drawSparkline('ml-fx-spark', sparkData.forex, '#B7791F');
      }

      // 수급
      if (d.investor) {
        var map = { frgn: d.investor.foreign, inst: d.investor.institution, indv: d.investor.individual };
        var maxAbs = Math.max(500, Math.abs(map.frgn || 0), Math.abs(map.inst || 0), Math.abs(map.indv || 0));
        Object.keys(map).forEach(function(key) {
          var val = map[key];
          if (val == null) return;
          var valEl = document.getElementById('ml-' + key + '-val');
          var barEl = document.getElementById('ml-' + key + '-bar');
          if (!valEl) return;
          valEl.textContent = (val >= 0 ? '+' : '') + Math.round(val).toLocaleString();
          valEl.className   = 'supply-val ' + (val >= 0 ? 'buying' : 'selling');
          if (barEl) {
            barEl.style.width = supplyBarPct(val, maxAbs) + '%';
            barEl.className   = 'supply-bar-fill2 ' + (val >= 0 ? 'buy' : 'sell');
          }
        });
      }
    }

    function poll() {
      fetch('/api/market', { signal: AbortSignal.timeout(8000) })
        .then(function(r) { return r.ok ? r.json() : Promise.reject(); })
        .then(applyData)
        .catch(function() {});
    }

    buildPanel();
    poll();
    if (isDuringMarket()) {
      polling = setInterval(poll, 60000);
      scheduleCloseLabel();
    }
  }

  /* ── 전역 노출 (인라인 핸들러·섹션 템플릿용) ── */
  window.toggleTheme = toggleTheme;
  window.openModal = openModal;
  window.closeModal = closeModal;
  window.drawSparkline = drawSparkline;
  window.drawMiniChart = drawMiniChart;
  window.drawCloseChart = drawCloseChart;
  window.renderInstList = renderInstList;
  window.openNoticePanel = openNoticePanel;
  window.closeNoticePanel = closeNoticePanel;
  window.switchPanelTab  = switchPanelTab;
  window.submitBoardPost = submitBoardPost;
})();
