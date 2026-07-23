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
  function drawSparkline(id, data, hoverIdx) {
    const c = document.getElementById(id);
    if (!c || !data || data.length < 2) return;
    const dpr = window.devicePixelRatio || 1, W = c.offsetWidth || 80, H = c.offsetHeight || 44;
    c.width = W * dpr; c.height = H * dpr;
    const ctx = c.getContext('2d'); ctx.scale(dpr, dpr);

    const cur   = data[data.length - 1];
    const isUp  = cur >= data[0];
    const color = isUp ? '#E03131' : '#2775ED';
    // 우측 포지션 바 공간 확보 (바 4px + 양쪽 여백 3+2px)
    const pad   = { t: 5, b: 5, l: 2, r: 11 };
    const pW    = W - pad.l - pad.r, pH = H - pad.t - pad.b;
    const min   = Math.min(...data), max = Math.max(...data);
    const range = max - min || data[0] * 0.001 || 1;
    const xf    = i => pad.l + (i / (data.length - 1)) * pW;
    const yf    = v => pad.t + (1 - (v - min) / range) * pH;
    const pts   = data.map((v, i) => ({ x: xf(i), y: yf(v) }));

    // 시작가 기준선
    const refY = yf(data[0]);
    ctx.beginPath(); ctx.setLineDash([3, 3]);
    ctx.strokeStyle = color + '55'; ctx.lineWidth = 0.8;
    ctx.moveTo(pad.l, refY); ctx.lineTo(W - pad.r, refY);
    ctx.stroke(); ctx.setLineDash([]);

    // 그라디언트 면
    const grad = ctx.createLinearGradient(0, 0, 0, H);
    grad.addColorStop(0, color + '40'); grad.addColorStop(1, color + '00');
    ctx.beginPath(); ctx.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) { const cx = (pts[i-1].x + pts[i].x) / 2; ctx.bezierCurveTo(cx, pts[i-1].y, cx, pts[i].y, pts[i].x, pts[i].y); }
    ctx.lineTo(pts.at(-1).x, H - pad.b); ctx.lineTo(pts[0].x, H - pad.b); ctx.closePath();
    ctx.fillStyle = grad; ctx.fill();

    // 라인
    ctx.beginPath(); ctx.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) { const cx = (pts[i-1].x + pts[i].x) / 2; ctx.bezierCurveTo(cx, pts[i-1].y, cx, pts[i].y, pts[i].x, pts[i].y); }
    ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.stroke();

    // 현재값 도트 — 흰 테두리 + 컬러 채움
    const lx = pts.at(-1).x, ly = pts.at(-1).y;
    ctx.beginPath(); ctx.arc(lx, ly, 4,   0, Math.PI * 2); ctx.fillStyle = '#fff';   ctx.fill();
    ctx.beginPath(); ctx.arc(lx, ly, 2.5, 0, Math.PI * 2); ctx.fillStyle = color; ctx.fill();

    // 호버 크로스헤어
    if (hoverIdx !== undefined) {
      const hx = xf(hoverIdx), hy = yf(data[hoverIdx]);
      ctx.beginPath(); ctx.setLineDash([3, 3]);
      ctx.strokeStyle = 'rgba(120,120,120,0.4)'; ctx.lineWidth = 1;
      ctx.moveTo(hx, pad.t); ctx.lineTo(hx, H - pad.b);
      ctx.stroke(); ctx.setLineDash([]);
      ctx.beginPath(); ctx.arc(hx, hy, 4, 0, Math.PI * 2); ctx.fillStyle = '#fff'; ctx.fill();
      ctx.beginPath(); ctx.arc(hx, hy, 2.5, 0, Math.PI * 2); ctx.fillStyle = color; ctx.fill();
    }

    // 포지션 바 — 현재가가 세션 범위에서 어느 위치인지
    const bx = W - 5, bTop = pad.t, bH = pH;
    const curPct = (cur - min) / range;
    const curY   = bTop + (1 - curPct) * bH;
    // 트랙 (전체 범위)
    ctx.fillStyle = 'rgba(150,150,150,0.18)';
    ctx.fillRect(bx - 2, bTop, 4, bH);
    // 현재 위치 이하 채움
    const fillH = bTop + bH - curY;
    if (fillH > 0) { ctx.fillStyle = color + '55'; ctx.fillRect(bx - 2, curY, 4, fillH); }
    // 현재 위치 마커 (가로 선)
    ctx.beginPath();
    ctx.moveTo(bx - 4, curY); ctx.lineTo(bx + 2, curY);
    ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.stroke();

    // 호버 인터랙션 연결 (최초 1회)
    c._sparkData = data.slice();
    if (!c._hoverAttached) { c._hoverAttached = true; attachSparkHover(c); }
  }

  // 전역 툴팁 — body에 단 하나, position:fixed로 뷰포트 기준 위치 잡아 잘림 방지
  function getGlobalSparkTip() {
    var tip = document.getElementById('spark-tip-global');
    if (!tip) {
      tip = document.createElement('div');
      tip.id = 'spark-tip-global';
      tip.className = 'spark-tip';
      document.body.appendChild(tip);
    }
    return tip;
  }

  function attachSparkHover(c) {
    function fmtNum(v) {
      return v.toLocaleString('ko-KR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    c.addEventListener('mousemove', function(e) {
      var data = c._sparkData;
      if (!data || data.length < 2) return;
      var rect = c.getBoundingClientRect();
      var mx   = e.clientX - rect.left;
      var W    = c.offsetWidth || 80;
      var pad  = { l: 2, r: 11 };
      var pW   = W - pad.l - pad.r;
      var idx  = Math.round((mx - pad.l) / pW * (data.length - 1));
      idx = Math.max(0, Math.min(data.length - 1, idx));

      var val   = data[idx];
      var start = data[0];
      var delta = (val - start) / start * 100;
      var sign  = delta >= 0 ? '+' : '';
      var color = delta >= 0 ? '#E03131' : '#2775ED';

      // 크로스헤어 재드로우
      drawSparkline(c.id, data, idx);

      // 전역 툴팁 내용 업데이트
      var tip = getGlobalSparkTip();
      tip.innerHTML =
        '<span class="spark-tip-val" style="color:' + color + '">' + fmtNum(val) + '</span>' +
        '<span class="spark-tip-delta" style="color:' + color + '">' + sign + delta.toFixed(2) + '%</span>';
      tip.style.display = 'flex';

      // 크로스헤어 x 기준으로 fixed 위치 계산
      var xRatio = (data.length > 1) ? idx / (data.length - 1) : 0;
      var canvasX = rect.left + pad.l + xRatio * pW;
      var tipW = tip.offsetWidth || 88;
      var tipH = tip.offsetHeight || 36;
      var left = canvasX - tipW / 2;
      // 뷰포트 좌우 클램프
      left = Math.max(4, Math.min(window.innerWidth - tipW - 4, left));
      var top = rect.top - tipH - 6;
      // 위쪽 공간 없으면 아래로
      if (top < 4) top = rect.bottom + 6;
      tip.style.left = left + 'px';
      tip.style.top  = top + 'px';
    });

    c.addEventListener('mouseleave', function() {
      var tip = document.getElementById('spark-tip-global');
      if (tip) tip.style.display = 'none';
      if (c._sparkData) drawSparkline(c.id, c._sparkData);
    });
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
  var BL_SCHEDULE = { kospi: '07:30', close: '16:00', us: '21:45' };
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
  function _blIsWeekend(dateStr) {
    var p = dateStr.split('-');
    var dow = new Date(Date.UTC(+p[0], +p[1] - 1, +p[2])).getUTCDay();
    return dow === 0 || dow === 6;
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
            var s = todaySlots[t] || (_blIsWeekend(today) ? { state: 'empty' } : { state: 'pending', scheduled_time: BL_SCHEDULE[t] });
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
      .then(function(r) {
        if (!r.ok) throw new Error('api error ' + r.status);
        return r.json();
      })
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

  /* ── 예측 로직 개선 안내 토스트 (브리핑 상세 진입 시 1회, 닫으면 영구 비표시) ── */
  function initPredictionToast() {
    // 브리핑 상세 페이지(/briefings/YYYY-MM-DD/type/)에서만 노출
    if (!/\/briefings\/\d{4}-\d{2}-\d{2}\//.test(location.pathname)) return;
    // 노출 기간: 2026-07-05 ~ 2026-07-07 11:00 KST. 이후엔 표시하지 않으며, 만료 후 이 함수는 삭제해도 됨.
    if (Date.now() > Date.parse('2026-07-07T11:00:00+09:00')) return;
    var KEY = 'ds-toast-pred-v3';
    try { if (localStorage.getItem(KEY)) return; } catch (e) {}

    if (!document.getElementById('ds-toast-style')) {
      var st = document.createElement('style');
      st.id = 'ds-toast-style';
      st.textContent =
        '.ds-toast{position:fixed;left:50%;bottom:24px;transform:translate(-50%,140%);z-index:9999;' +
        'display:flex;align-items:flex-start;gap:10px;max-width:380px;width:calc(100% - 32px);' +
        'background:#16181d;color:#fff;border:1px solid rgba(255,255,255,.12);border-radius:14px;' +
        'padding:14px 14px 14px 16px;box-shadow:0 12px 32px rgba(0,0,0,.30);opacity:0;' +
        'transition:transform .35s cubic-bezier(.2,.8,.2,1),opacity .35s;}' +
        '.ds-toast.show{transform:translate(-50%,0);opacity:1;}' +
        '.ds-toast-body{display:flex;gap:10px;align-items:flex-start;flex:1;}' +
        '.ds-toast-emoji{font-size:20px;line-height:1.3;}' +
        '.ds-toast-text{display:flex;flex-direction:column;gap:3px;}' +
        '.ds-toast-text b{font-size:14px;font-weight:700;}' +
        '.ds-toast-text span{font-size:12.5px;color:#b8bdc7;line-height:1.45;}' +
        '.ds-toast-close{flex:none;background:none;border:none;color:#9aa0aa;font-size:20px;' +
        'line-height:1;cursor:pointer;padding:0 2px;margin-left:4px;}' +
        '.ds-toast-close:hover{color:#fff;}';
      document.head.appendChild(st);
    }

    var toast = document.createElement('div');
    toast.className = 'ds-toast';
    toast.setAttribute('role', 'status');
    toast.innerHTML =
      '<div class="ds-toast-body">' +
        '<span class="ds-toast-emoji">🎯</span>' +
        '<div class="ds-toast-text">' +
          '<b>하락 예측 정확도를 개선했어요.</b>' +
          '<span>원/달러 환율 신호를 추가하고, 하락 판정 기준을 더 엄격하게 조정해 예측 편향을 교정했어요.</span>' +
        '</div>' +
      '</div>' +
      '<button class="ds-toast-close" type="button" aria-label="닫기">×</button>';

    // 한 번 노출되면 다시 보지 않도록, 표시 시점에 바로 seen 기록
    try { localStorage.setItem(KEY, '1'); } catch (e) {}

    function dismiss() {
      toast.classList.remove('show');
      setTimeout(function () { toast.remove(); }, 350);
    }
    toast.querySelector('.ds-toast-close').addEventListener('click', dismiss);

    document.body.appendChild(toast);
    requestAnimationFrame(function () {
      requestAnimationFrame(function () { toast.classList.add('show'); });
    });
  }

  /* ── 초기화 ── */
  // 레이아웃을 정의하는 라이브 패널(지금 코스피 밴드·스코어보드·사이드바 특이신호)은
  // window.load(이미지·위젯까지 로드 완료)까지 기다리지 않고 파싱 직후 즉시 노출한다.
  // 이 스크립트는 <body> 끝에 있어 이 시점에 대상 DOM이 이미 준비돼 있으며, 노출 판정은
  // fetch 없이 KST 시각·URL 날짜만으로 동기 결정되므로, 본문이 먼저 그려진 뒤 밴드가
  // 뒤늦게 끼어들며 267px 밀려나는 레이아웃 튐(CLS)을 방지한다.
  initLiveScoreboard();
  initLiveMarketPanel();
  initNowBand();
  initSidebarSignals();

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
    initPredictionToast();
    renderSupplyFlows();
    loadLeadersWidget();
    loadIncomeWidget();
    loadVisitorCount();
    patchBriefingList();
    patchBriefingNav();
  });

  /* ── 코스피 주도주 위젯 — 실시간 시세 + 왜 움직였나(장중 곡선·뉴스 핀) + 증권사 목표주가 (월배당 위젯 위 사이드바) ── */
  function loadLeadersWidget() {
    var anchor = document.querySelector('.sidebar-cta');
    if (!anchor || document.querySelector('.leaders-widget')) return;
    var STOCKS = [
      { code: '005930', name: '삼성전자' },
      { code: '000660', name: 'SK하이닉스' },
      { code: '005380', name: '현대차' }
    ];
    var w = document.createElement('div');
    w.className = 'leaders-widget';
    w.innerHTML =
      '<div class="leaders-widget__header"><span class="leaders-widget__ic">📈</span>' +
        '<span class="leaders-widget__title">코스피 주도주</span>' +
        '<span class="leaders-widget__badge-24h" title="장중엔 실시간 시세, 마감 후엔 24시간 글로벌 파생 시세로 자동 갱신돼요">24H 갱신</span>' +
        '<span class="leaders-widget__live" id="lw-live" style="display:none"><span class="leaders-widget__live-dot"></span>LIVE</span>' +
        '<button class="leaders-widget__refresh" id="lw-refresh" type="button" aria-label="새로고침" title="새로고침"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg></button>' +
        '<span class="leaders-widget__pill" id="lw-pill">🌙 HL 24h</span></div>' +
      '<div class="leaders-widget__tiles" id="lw-tiles">' +
        STOCKS.map(function (s, i) {
          return '<div class="leaders-widget__tile' + (i === 0 ? ' on' : '') + '" data-code="' + s.code + '">' +
            '<span class="leaders-widget__tile-name">' + s.name + '</span>' +
            '<span class="leaders-widget__tile-price">—</span>' +
            '<span class="leaders-widget__tile-chg">—</span></div>';
        }).join('') +
      '</div>' +
      '<div class="leaders-widget__curve">' +
        '<div class="leaders-widget__curve-h">📊 <b id="lw-name">' + STOCKS[0].name + '</b> 직전 세션 장중 흐름 <span class="leaders-widget__curve-badge">● 실측 1분봉</span></div>' +
        '<svg id="lw-svg" viewBox="0 0 300 110" role="img" aria-label="장중 1분봉 곡선"></svg>' +
      '</div>' +
      '<div class="leaders-widget__news" id="lw-news"></div>' +
      '<div class="leaders-widget__stats" id="lw-stats">' +
        '<div id="lw-vol" style="display:none"></div>' +
        '<div id="lw-range" style="display:none"></div>' +
      '</div>' +
      '<a class="leaders-widget__more" href="https://doubleshot.space/stocks/" target="_blank" rel="noopener">종목 시그널에서 자세히 보기 →</a>';
    anchor.insertAdjacentElement('beforebegin', w);

    var codes = STOCKS.map(function (s) { return s.code; });
    var got = false;
    var X0 = 8, X1 = 292, YT = 12, YB = 86;
    var buf = {}, buft = {}, whyData = {}, snapW = {}, backfilled = {}, curCode = STOCKS[0].code;
    var bufDay = todayKST();   // buf가 담은 거래일(KST) — 자정 넘겨 탭을 열어두면 전일 곡선이 오늘 타일과 어긋나므로 날짜가 바뀌면 재백필한다.
    var prevPrice = {};
    // 날짜 롤오버 방어 — 자정을 넘겼으면 전일 곡선 버퍼를 버리고 오늘 곡선으로 재백필한다.
    function leadersDayRoll() {
      if (todayKST() === bufDay) return;
      bufDay = todayKST(); buf = {}; buft = {}; backfilled = {};
      try { sessionStorage.removeItem('lw-intra-v1'); } catch (e) {}
      backfill(curCode);
    }

    function fmt(v) { return v >= 1000 ? v.toLocaleString('ko-KR') : v; }
    function timeToX(t) {
      var p = (t || '09:00').split(':'), mm = (+p[0]) * 60 + (+p[1]);
      return X0 + (X1 - X0) * Math.min(1, Math.max(0, (mm - 540) / (930 - 540)));
    }

    // KR 정규장(평일 09:00~15:30 KST) 여부 — 마감 후엔 HL 24h 환산가로 전환
    function krOpen() {
      var m = ((new Date().getUTCHours() * 60 + new Date().getUTCMinutes()) + 9 * 60) % (24 * 60);
      var kd = new Date(Date.now() + 9 * 3600 * 1000).getUTCDay();
      if (kd === 0 || kd === 6) return false;
      return m >= 540 && m <= 930;
    }
    function paintTile(code, price, chg) {
      var t = w.querySelector('.leaders-widget__tile[data-code="' + code + '"]');
      if (!t || price == null) return;
      got = true;
      var priceEl = t.querySelector('.leaders-widget__tile-price');
      priceEl.textContent = Math.round(price).toLocaleString('ko-KR');
      var prev = prevPrice[code];
      if (prev != null && prev !== price) {
        priceEl.classList.remove('mkt-flash-up', 'mkt-flash-dn');
        void priceEl.offsetWidth;
        priceEl.classList.add(price > prev ? 'mkt-flash-up' : 'mkt-flash-dn');
      }
      prevPrice[code] = price;
      var c = t.querySelector('.leaders-widget__tile-chg');
      if (chg == null) { c.textContent = '—'; c.className = 'leaders-widget__tile-chg'; }
      else { var up = chg >= 0; c.textContent = (up ? '▲' : '▼') + Math.abs(chg).toFixed(2) + '%'; c.className = 'leaders-widget__tile-chg ' + (up ? 'up' : 'dn'); }
    }
    function pollDay() {
      fetch('/api/stocks-live?codes=' + codes.join(','), { cache: 'no-store', signal: AbortSignal.timeout(5000) })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) { if (d && Array.isArray(d.prices)) d.prices.forEach(function (p) { paintTile(p.code, p.price, p.changePct); }); })
        .catch(function () {});
    }
    function pollNight() {
      fetch('/api/hl-night', { cache: 'no-store', signal: AbortSignal.timeout(5000) })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (d) { if (d && Array.isArray(d.items)) d.items.forEach(function (it) { paintTile(it.code, it.krw, it.changePct); }); })
        .catch(function () {});
    }
    var pill = w.querySelector('#lw-pill');
    var liveBadge = w.querySelector('#lw-live');
    function pollTiles() {
      leadersDayRoll();   // 자정 넘긴 오래 켜둔 탭이 전일 곡선을 계속 그리지 않도록 매 폴링마다 날짜 확인
      var night = !krOpen();
      if (pill) pill.style.display = night ? '' : 'none';
      if (liveBadge) liveBadge.style.display = night ? 'none' : '';
      if (night) pollNight(); else pollDay();
    }
    pollTiles();
    setInterval(pollTiles, 10000);
    // 탭에 다시 돌아왔을 때(오래 켜뒀다 재방문) 날짜가 바뀌었으면 즉시 곡선을 새 거래일로 복구한다.
    document.addEventListener('visibilitychange', function () { if (!document.hidden) leadersDayRoll(); });

    w.querySelectorAll('.leaders-widget__tile').forEach(function (t) {
      t.addEventListener('click', function () {
        w.querySelectorAll('.leaders-widget__tile').forEach(function (o) { o.classList.toggle('on', o === t); });
        select(t.getAttribute('data-code'));
      });
    });

    var refreshBtn = w.querySelector('#lw-refresh');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', function () {
        if (refreshBtn.classList.contains('spin')) return;
        refreshBtn.classList.add('spin');
        pollTiles();
        backfill(curCode);
        loadWhy();
        loadSnap();
        setTimeout(function () { refreshBtn.classList.remove('spin'); }, 700);
      });
    }

    /* ── 곡선 + 뉴스 핀 (/stocks 허브 "왜 움직였나" 로직과 동일, 사이드바 폭에 맞춰 300×110로 축소) ── */
    function loadWhy() {
      var d = new Date(Date.now() + 9 * 3600 * 1000).toISOString().slice(0, 10);
      fetch('/api/data?f=movers-why', { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; })
        .then(function (j) { return j || fetch('/data/movers-why-' + d + '.json').then(function (r) { return r.ok ? r.json() : null; }); })
        .then(function (j) { return j || fetch('/data/movers-why-live.json').then(function (r) { return r.ok ? r.json() : null; }); })
        .then(function (j) { if (j && j.stocks) { j.stocks.forEach(function (s) { whyData[s.code] = s.events || []; }); if (buf[curCode]) draw(curCode); } })
        .catch(function () {});
    }
    function loadSnap() {
      fetch('/data/stocks-snapshot.json', { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; })
        .then(function (j) { if (j && j.stocks) { snapW = j.stocks; renderStats(curCode); } }).catch(function () {});
    }
    function renderStats(code) {
      var s = snapW[code];
      var vol = w.querySelector('#lw-vol');
      if (vol) {
        if (s && s.vol && s.vol_avg20) {
          var surge = s.vol / s.vol_avg20;
          var vcol = surge >= 1.5 ? 'var(--up)' : (surge >= 1.0 ? '#F59E0B' : 'var(--muted)'), vlbl = surge >= 1.5 ? '급증' : (surge >= 1.0 ? '보통' : '한산');
          var fillPct = Math.max(5, Math.min(100, surge / 2 * 100));
          vol.style.display = '';
          vol.innerHTML = '<div class="leaders-widget__stat-h">🔥 거래량<b style="color:' + vcol + '">×' + surge.toFixed(2) + '</b></div>' +
            '<div class="leaders-widget__bar"><div class="leaders-widget__bar-fill" style="width:' + fillPct.toFixed(0) + '%;background:' + vcol + '"></div><div class="leaders-widget__bar-base"></div></div>' +
            '<div class="leaders-widget__stat-note"><span>20일 평균 대비</span><span>' + vlbl + '</span></div>';
        } else { vol.style.display = 'none'; }
      }
      var rng = w.querySelector('#lw-range');
      if (rng) {
        var rv = buf[code] || [];
        if (rv.length > 4) {
          var rlo = Math.min.apply(null, rv), rhi = Math.max.apply(null, rv), rcur = rv[rv.length - 1], rspan = (rhi - rlo) || 1;
          var rpos = Math.max(0, Math.min(100, (rcur - rlo) / rspan * 100));
          rng.style.display = '';
          rng.innerHTML = '<div class="leaders-widget__stat-h">📊 직전 세션 레인지 위치<b>' + rpos.toFixed(0) + '%</b></div>' +
            '<div class="leaders-widget__bar" style="background:linear-gradient(90deg,var(--dn-bg),var(--up-bg));"><div style="position:absolute;left:' + rpos.toFixed(0) + '%;top:-3px;width:12px;height:12px;border-radius:50%;background:var(--ink);border:2px solid var(--canvas);transform:translateX(-50%);"></div></div>' +
            '<div class="leaders-widget__stat-note"><span>저 ' + fmt(rlo) + '</span><span>고 ' + fmt(rhi) + '</span></div>';
        } else { rng.style.display = 'none'; }
      }
    }
    function pathFrom(vals, times) {
      if (!vals || vals.length < 2) return null;
      var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals), span = (hi - lo) || 1, n = vals.length;
      var useT = times && times.length === n;
      return vals.map(function (v, i) {
        var x = useT ? timeToX(times[i]) : X0 + (X1 - X0) * (i / (n - 1));
        var y = YB - (YB - YT) * ((v - lo) / span);
        return { x: x, y: y };
      });
    }
    // 좌표 배열을 부드러운 곡선 path로 변환 — drawSparkline()의 캔버스 bezier 스무딩과 동일한
    // 중간점 앵커 방식(각 구간의 x 중간값을 컨트롤포인트로 사용). 폭 넓은 화면에서 직선 폴리라인이
    // 각져 보이는 문제를 해결한다.
    function smoothD(coords) {
      var d = 'M' + coords[0].x.toFixed(1) + ',' + coords[0].y.toFixed(1);
      for (var i = 1; i < coords.length; i++) {
        var cx = ((coords[i - 1].x + coords[i].x) / 2).toFixed(1);
        d += ' C' + cx + ',' + coords[i - 1].y.toFixed(1) + ' ' + cx + ',' + coords[i].y.toFixed(1) + ' ' + coords[i].x.toFixed(1) + ',' + coords[i].y.toFixed(1);
      }
      return d;
    }
    function draw(code) {
      var vals = buf[code] || [], svg = w.querySelector('#lw-svg');
      if (!svg) return;
      var nm = w.querySelector('#lw-name'); var meta = STOCKS.filter(function (s) { return s.code === code; })[0]; if (nm && meta) nm.textContent = meta.name;
      var coords = pathFrom(vals, buft[code]);
      if (!coords) { svg.innerHTML = '<text x="150" y="55" text-anchor="middle" font-size="11" fill="var(--muted)">실측 데이터 없음</text>'; return; }
      var up = vals[vals.length - 1] >= vals[0], colHex = up ? '#E03131' : '#2775ED';
      var last = coords[coords.length - 1];
      var lineD = smoothD(coords);
      var areaD = lineD + ' L' + last.x.toFixed(1) + ',' + YB + ' L' + X0.toFixed(1) + ',' + YB + ' Z';
      var hiIdx = 0, loIdx = 0;
      for (var i = 1; i < vals.length; i++) { if (vals[i] > vals[hiIdx]) hiIdx = i; if (vals[i] < vals[loIdx]) loIdx = i; }
      var hiC = coords[hiIdx], loC = coords[loIdx];
      var gradId = 'lw-grad-' + code;
      var s = '<defs><linearGradient id="' + gradId + '" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="' + colHex + '" stop-opacity=".18"/><stop offset="100%" stop-color="' + colHex + '" stop-opacity=".02"/></linearGradient></defs>' +
        '<line x1="' + X0 + '" y1="' + YB + '" x2="' + X1 + '" y2="' + YB + '" stroke="var(--hairline)" stroke-width="1"/>' +
        '<path d="' + areaD + '" fill="url(#' + gradId + ')"/>' +
        '<path d="' + lineD + '" fill="none" stroke="' + colHex + '" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>' +
        '<circle cx="' + last.x.toFixed(1) + '" cy="' + last.y.toFixed(1) + '" r="3" fill="' + colHex + '"/>';
      if (vals.length > 4 && hiIdx !== loIdx) {
        var hAnc = hiC.x < 150 ? 'start' : 'end', lAnc = loC.x < 150 ? 'start' : 'end';
        var hOff = hAnc === 'start' ? 5 : -5, lOff = lAnc === 'start' ? 5 : -5;
        var hLabY = (hiC.y - 6 < YT + 2) ? (hiC.y + 13) : (hiC.y - 6);
        var lLabY = (loC.y + 13 > YB - 4) ? (loC.y - 8) : (loC.y + 13);
        s += '<circle cx="' + hiC.x.toFixed(1) + '" cy="' + hiC.y.toFixed(1) + '" r="3" fill="#E03131"/>' +
          '<text x="' + (hiC.x + hOff).toFixed(1) + '" y="' + hLabY.toFixed(1) + '" font-size="9" font-weight="800" fill="#E03131" stroke="#fff" stroke-width="2.5" paint-order="stroke" text-anchor="' + hAnc + '">고 ' + fmt(vals[hiIdx]) + '</text>' +
          '<circle cx="' + loC.x.toFixed(1) + '" cy="' + loC.y.toFixed(1) + '" r="3" fill="#2775ED"/>' +
          '<text x="' + (loC.x + lOff).toFixed(1) + '" y="' + lLabY.toFixed(1) + '" font-size="9" font-weight="800" fill="#2775ED" stroke="#fff" stroke-width="2.5" paint-order="stroke" text-anchor="' + lAnc + '">저 ' + fmt(vals[loIdx]) + '</text>';
      }
      s += '<text x="' + X0 + '" y="102" font-size="9" fill="var(--muted)">09:00</text><text x="' + (X1 - 24) + '" y="102" font-size="9" fill="var(--muted)">15:30</text>';
      svg.innerHTML = s;
      function yAtX(x) { var b = coords[0]; for (var i = 0; i < coords.length; i++) { if (Math.abs(coords[i].x - x) < Math.abs(b.x - x)) b = coords[i]; } return b.y; }
      var evs = whyData[code] || [], pinSvg = '', placedPx = [];
      evs.forEach(function (e, i) {
        var ax = timeToX(e.time), ay = yAtX(ax), f = e.tier === 'why' ? '#E03131' : '#fff', st = e.tier === 'why' ? '#E03131' : '#94A3B8', tc = e.tier === 'why' ? '#fff' : '#64748B';
        var px = Math.min(X1 - 8, Math.max(X0 + 8, ax));
        for (var gi = 0; gi < placedPx.length; gi++) { if (Math.abs(px - placedPx[gi]) < 16) { px = Math.min(X1 - 8, placedPx[gi] + 16); } }
        placedPx.push(px);
        var up2 = (ay - 24) >= YT, cy = up2 ? ay - 16 : ay + 16;
        pinSvg += '<line x1="' + ax.toFixed(1) + '" y1="' + ay.toFixed(1) + '" x2="' + px.toFixed(1) + '" y2="' + cy.toFixed(1) + '" stroke="' + st + '" stroke-width="1"/>' +
          '<circle cx="' + px.toFixed(1) + '" cy="' + cy.toFixed(1) + '" r="7" fill="' + f + '" stroke="' + st + '" stroke-width="1.3"/>' +
          '<text x="' + px.toFixed(1) + '" y="' + (cy + 2.5).toFixed(1) + '" font-size="8" font-weight="800" fill="' + tc + '" text-anchor="middle">' + (i + 1) + '</text>';
      });
      if (pinSvg) { var g = document.createElementNS('http://www.w3.org/2000/svg', 'g'); g.innerHTML = pinSvg; svg.appendChild(g); }
      renderStats(code);
      renderNews(code);
    }
    function renderNews(code) {
      var wrap = w.querySelector('#lw-news'); if (!wrap) return;
      var evs = whyData[code] || [];
      wrap.innerHTML = evs.length ? evs.map(function (e, i) {
        var isWhy = e.tier === 'why';
        return '<div class="leaders-widget__news-row"><div class="leaders-widget__news-badge' + (isWhy ? '' : ' related') + '">' + (i + 1) + '</div>' +
          '<div style="flex:1;min-width:0;"><span class="leaders-widget__news-time">' + e.time + (isWhy ? ' · 왜' : ' · 관련') + '</span>' +
          '<a class="leaders-widget__news-headline" href="' + e.url + '" target="_blank" rel="noopener">' + e.headline + '</a>' +
          '<div class="leaders-widget__news-why">' + e.why + '</div></div></div>';
      }).join('') : '<div class="leaders-widget__news-empty">📭 직전 세션 관련 뉴스 없음 · 수급/테마 추정</div>';
    }
    function todayKST() { return new Date(Date.now() + 9 * 3600 * 1000).toISOString().slice(0, 10); }
    function readCache() { try { var raw = sessionStorage.getItem('lw-intra-v1'); if (!raw) return {}; var o = JSON.parse(raw); return (o && o.date === todayKST() && o.data) ? o.data : {}; } catch (e) { return {}; } }
    function writeCache(code, d) {
      try {
        var raw = sessionStorage.getItem('lw-intra-v1'), o = {}; try { o = raw ? JSON.parse(raw) : {}; } catch (_) { o = {}; }
        if (!o || o.date !== todayKST()) o = { date: todayKST(), data: {} }; if (!o.data) o.data = {};
        o.data[code] = { minutes: d.minutes || [], times: d.times || [] };
        sessionStorage.setItem('lw-intra-v1', JSON.stringify(o));
      } catch (e) {}
    }
    function showSkeleton() {
      var svg = w.querySelector('#lw-svg'); if (!svg) return;
      svg.innerHTML = '<rect class="leaders-widget__skel" x="2" y="8" width="296" height="80" rx="8" fill="var(--surface-soft)"/><text x="150" y="52" text-anchor="middle" font-size="10" font-weight="700" fill="var(--muted)">실측 1분봉 불러오는 중…</text>';
    }
    function backfill(code) {
      var cached = readCache()[code];
      if (cached && cached.minutes && cached.minutes.length >= 2) { buf[code] = cached.minutes.slice(); buft[code] = (cached.times || []).slice(); draw(code); }
      else if (code === curCode) { showSkeleton(); }
      fetch('/api/intraday?code=' + code).then(function (r) { return r.json(); }).then(function (d) {
        if (d && d.minutes && d.minutes.length) { buf[code] = d.minutes.slice(); buft[code] = (d.times || []).slice(); backfilled[code] = true; writeCache(code, d); if (code === curCode) draw(code); }
      }).catch(function () {});
    }
    function select(code) {
      curCode = code;
      var meta = STOCKS.filter(function (s) { return s.code === code; })[0];
      var nm = w.querySelector('#lw-name'); if (nm && meta) nm.textContent = meta.name;
      renderStats(code); renderNews(code);
      if (backfilled[code]) draw(code); else { if (!(buf[code] && buf[code].length >= 2)) showSkeleton(); backfill(code); }
    }
    backfill(curCode); loadWhy(); loadSnap();

    // 8초 내 아무 실측도 못 받으면 위젯 제거 — 가짜 값 노출 금지(정합성)
    setTimeout(function () { if (!got) w.remove(); }, 8000);
  }

  /* ── 월배당 ETF 계산기 위젯 — /data/income_etfs.json (텔레그램 CTA 위 사이드바) ── */
  function loadIncomeWidget() {
    var anchor = document.querySelector('.sidebar-cta');
    if (!anchor || document.querySelector('.income-widget')) return;
    var COIN = '<svg viewBox="0 0 24 24" fill="none">' +
      '<ellipse cx="12" cy="16.5" rx="6.4" ry="2.3" fill="#fff" opacity=".5"/>' +
      '<ellipse cx="12" cy="12.5" rx="6.4" ry="2.3" fill="#fff" opacity=".75"/>' +
      '<ellipse cx="12" cy="8.5" rx="6.4" ry="2.3" fill="#fff"/></svg>';
    var w = document.createElement('div');
    w.className = 'income-widget';
    w.innerHTML =
      '<a class="income-widget__header" href="/stocks/income-designer/" target="_blank" rel="noopener">' +
        '<div class="income-widget__left"><div class="income-widget__badge">' + COIN + '</div>' +
        '<span class="income-widget__title">월배당 ETF 계산기</span></div>' +
        '<span class="income-widget__more">→</span>' +
      '</a>' +
      '<div class="income-widget__list" id="income-rows"></div>' +
      '<a class="income-widget__foot" href="/stocks/income-designer/" target="_blank" rel="noopener">분배율·건전성 한눈에 · 내 배당 계산하기 →</a>';
    anchor.insertAdjacentElement('beforebegin', w);

    var rows = w.querySelector('#income-rows');
    fetch('/data/income_etfs.json', { signal: AbortSignal.timeout(5000) })
      .then(function(r) { return r.ok ? r.json() : Promise.reject(); })
      .then(function(d) {
        var list = (d && d.etfs) || [];
        if (!list.length) throw new Error();
        list.slice()
          .sort(function(a, b) { return (b.yield_ttm || 0) - (a.yield_ttm || 0); })
          .slice(0, 3)
          .forEach(function(e) {
            var health = ['ok', 'warn', 'bad', 'na'].indexOf(e.health) >= 0 ? e.health : 'na';
            var row = document.createElement('div');
            row.className = 'income-row';
            row.innerHTML =
              '<span class="income-row__dot ' + health + '"></span>' +
              '<span class="income-row__name">' + e.name + '</span>' +
              '<span class="income-row__y">연 ' + (e.yield_ttm || 0).toFixed(1) + '%</span>';
            rows.appendChild(row);
          });
      })
      .catch(function() { w.remove(); });
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

    // 당일이면 장 시간 기반, 과거 브리핑이면 정적 결과 표시
    var m = location.pathname.match(/\/briefings\/(\d{4}-\d{2}-\d{2})\//);
    var isPast = false;
    if (m) {
      var k0 = kstNow();
      var todayKst = k0.getUTCFullYear() + '-' +
        String(k0.getUTCMonth() + 1).padStart(2, '0') + '-' +
        String(k0.getUTCDate()).padStart(2, '0');
      if (m[1] > todayKst) return;        // 미래 날짜는 표시 안 함
      if (m[1] < todayKst) isPast = true; // 과거 브리핑
    }

    if (!isPast && !isMarketHours() && !isAfterMarket()) return;
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
               '예측이 맞아떨어지는 중', '오늘 전망 적중', '오늘 AI 컨디션 좋네요', '예측대로 움직이고 있어요',
               '오늘은 AI가 읽었어요', '흐름을 제대로 잡았어요', '예측이 살아있어요',
               '상승 흐름 그대로예요', '오늘 예측은 맞는 방향이에요', '장이 예측 손을 들어줬어요',
               '시장이 오늘은 고분고분하네요', '예측 방향으로 착실하게 가는 중'],
        miss: ['빗나가는 중', '예상 밖 흐름', '예측과 반대로 흘러가는 중',
               '오늘은 시장이 다른 말을 하고 있어요', '변수가 생긴 것 같아요', '시장이 예측을 무시하고 있어요',
               '오늘은 시장이 반기를 들었어요', '예상과 다른 방향으로 가고 있어요',
               '시장이 오늘은 제 갈 길 가고 있어요', 'AI가 놓친 게 있는 것 같아요',
               '이런 날도 있어요', '변수가 시장을 움직이고 있어요'],
      },
      dn: {
        hit:  ['예측대로 흘러가는 중', '분석대로네요', '예측대로 움직이고 있어요',
               '하락 예측이 맞아가는 중', '오늘은 조심해야 할 날이에요', '시장이 조심스러운 하루예요'],
        miss: ['빗나가는 중, 다행이예요', '예상 밖 흐름', '예측과 반대로 오르는 중',
               '변수가 생긴 것 같아요, 좋은 징조', '예측은 틀렸지만 반가운 흐름',
               '오늘은 틀려서 기분 좋은 날', '시장이 좋은 의미로 예측을 깨고 있어요',
               '하락 예측이지만 시장은 반가운 반란 중', '틀렸는데 기쁜 날',
               '이런 날은 틀려도 괜찮아요', '예측보다 시장이 더 건강하네요', '나쁜 예측이 틀려서 다행이에요',
               '시장이 걱정보다 강해요', '예측을 뚫고 올라가는 중', '오늘은 AI가 너무 걱정했나봐요',
               '매수 세력이 예측을 이겼어요', '하락을 예상했는데, 좋은 의미로 빗나가는 중'],
      },
      tight: ['팽팽한 접전', '박빙 승부', '아슬아슬한 줄타기', '오차 범위 안에서 흘러가는 중', '중립 부근 공방 중',
              '방향을 아직 모르겠어요', '시장이 눈치를 보는 중', '상승도 하락도 아닌 줄다리기',
              '어느 방향으로 튈지 모르는 순간', '팽팽한 균형이 언제 깨질지'],
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
      return;
    }

    // ── 과거 브리핑 — 정적 결과 표시 (폴링 없음) ──
    if (isPast) {
      var badge3 = document.getElementById('lsb-badge');
      if (badge3) { badge3.className = 'lsb-closed-badge'; badge3.textContent = '마감'; }
      var footElPast = document.getElementById('lsb-foot');
      if (footElPast) footElPast.innerHTML = '<strong>마감</strong>';

      var actualPct = parseFloat(el.dataset.actualPct);
      var emElPast  = document.getElementById('lsb-head-em');
      var subElPast = document.getElementById('lsb-sub');

      if (!isNaN(actualPct)) {
        var verdictPast = calcVerdict(actualPct);
        var signPast = actualPct >= 0 ? '+' : '';
        var pctPast  = signPast + actualPct.toFixed(2) + '%';
        var closedMsg =
          verdictPast === 'tight' ? '박빙으로 마감했어요.' :
          verdictPast === 'hit'   ? (dir === 'dn' ? '하락 예측이 맞았어요. 아쉬운 하루였어요.' : '상승 예측이 맞았어요.') :
                                    (dir === 'dn' ? '틀려서 다행인 날이에요.' : '아쉽게도 예측이 빗나갔어요.');
        if (emElPast)  { emElPast.textContent = closedMsg; emElPast.style.color = ''; emElPast.style.fontWeight = '700'; }
        if (subElPast) { subElPast.textContent = pctPast + (actualPct >= 0 ? ' 상승 마감이에요.' : ' 하락 마감이에요.'); }

        var chgElPast = document.getElementById('lsb-chg');
        if (chgElPast) { chgElPast.textContent = signPast + actualPct.toFixed(2) + '%'; chgElPast.style.color = actualPct >= 0 ? 'var(--up)' : 'var(--dn)'; }

        var needleElPast = document.getElementById('lsb-needle');
        var rawPosPast = dir === 'up'
          ? Math.max(0, Math.min(100, (actualPct + 2) / 4 * 100))
          : Math.max(0, Math.min(100, (-actualPct + 2) / 4 * 100));
        if (needleElPast) needleElPast.style.left = rawPosPast + '%';

        var predTagElPast = document.getElementById('lsb-pred-tag');
        if (predTagElPast) {
          predTagElPast.style.background = dir === 'dn' ? 'var(--dn-bg)' : 'var(--up-bg)';
          predTagElPast.style.color      = dir === 'dn' ? 'var(--dn)'    : 'var(--up)';
        }
      } else {
        if (emElPast)  { emElPast.textContent = '결과 집계 중…'; emElPast.style.color = 'var(--muted)'; emElPast.style.fontWeight = ''; }
        if (subElPast) { subElPast.textContent = '다음 날 오전 정확도 체크 후 결과가 표시됩니다.'; }
      }

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
    updateCountdown();

    if (isMarketHours()) {
      setInterval(fetchKospi, 10000);
      setInterval(updateCountdown, 1000);
      setInterval(tickRefreshCount, 1000);
    }
  }

  /* ── 장 중 실시간 시장 지표 패널 ── */
  function initLiveMarketPanel() {
    var panel = document.getElementById('market-data-panel');
    if (!panel) return;
    // 장중 '오늘의 특이 신호' 위젯이 있으면(코스피 당일 브리핑) 라이브 시장 지표 패널은 비활성화 —
    // initSidebarSignals()가 장중에 시장 지표를 특이신호로 완전 교체하기 때문(2026-07-13).
    if (document.getElementById('signals-today')) return;
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

    // 과거 브리핑 판단 — URL 날짜가 오늘보다 이전이면 과거 모드
    var mktUrlMatch = location.pathname.match(/\/briefings\/(\d{4}-\d{2}-\d{2})\//);
    var mktIsPast = false;
    if (mktUrlMatch) {
      var mktNow = new Date(Date.now() + 9 * 3600 * 1000);
      var mktToday = mktNow.getUTCFullYear() + '-' +
        String(mktNow.getUTCMonth() + 1).padStart(2, '0') + '-' +
        String(mktNow.getUTCDate()).padStart(2, '0');
      if (mktUrlMatch[1] < mktToday) mktIsPast = true;
    }

    if (!mktIsPast && !isLiveMode()) return;

    // 모바일(≤900px)에서 스코어보드 바로 아래로 패널 이동 — 이후 위치 유지
    if (window.innerWidth <= 900) {
      var sb = document.getElementById('live-scoreboard');
      if (sb) sb.insertAdjacentElement('afterend', panel);
      panel.classList.add('mkt-panel-inline');
      panel.style.marginTop = '16px';
    }

    var SPARK_KEY = 'mkt-spark-v1';
    var sparkData = (function() {
      try {
        var saved = JSON.parse(sessionStorage.getItem(SPARK_KEY) || 'null');
        if (saved && Array.isArray(saved.kosdaq)) return saved;
      } catch (e) {}
      return { kosdaq: [], kospi200: [], forex: [] };
    })();
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

    function injectMktHelpModal() {
      if (document.getElementById('mkt-help-modal')) return;
      var m = document.createElement('div');
      m.className = 'info-modal-backdrop';
      m.id = 'mkt-help-modal';
      m.innerHTML =
        '<div class="info-modal" role="dialog" aria-modal="true">' +
        '<button class="info-modal__close" id="mkt-help-close" aria-label="닫기">' +
        '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M1 1l12 12M13 1L1 13" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>' +
        '</button>' +
        '<div class="info-modal__title">시장 지표 읽는 법</div>' +
        '<div class="info-modal__body">' +
        '<p><b style="color:var(--ink)">수급 바</b><br>' +
        '개인·기관·외국인의 순사기/팔기 강도를 막대로 표시해요. 오른쪽으로 길수록 사기 우세, 왼쪽으로 길수록 팔기 우세예요.</p>' +
        '<p><b style="color:var(--ink)">흐르는 선 (스파크라인)</b><br>' +
        '장 시작(09:00)부터 지금까지 1분마다 쌓이는 가격 흐름이에요. ' +
        '점선은 시초가 기준선으로, 선이 점선 위에 있으면 시초가 대비 상승 중이에요. ' +
        '<span style="color:#E03131;font-weight:600">빨강</span> = 시초가 대비 상승, ' +
        '<span style="color:#2775ED;font-weight:600">파랑</span> = 하락.</p>' +
        '<p><b style="color:var(--ink)">포지션 바 (우측 세로 막대)</b><br>' +
        '오늘 고점~저점 범위에서 지금 가격이 어디에 있는지 보여줘요. 마커가 위에 있을수록 오늘 고점에 가깝고, 아래일수록 저점에 가까워요.</p>' +
        '</div>' +
        '</div>';
      document.body.appendChild(m);

      m.addEventListener('click', function(e) { if (e.target === m) closeMktHelpModal(); });
      m.querySelector('#mkt-help-close').addEventListener('click', closeMktHelpModal);
    }

    function openMktHelpModal() {
      var m = document.getElementById('mkt-help-modal');
      if (m) m.classList.add('is-open');
    }

    function closeMktHelpModal() {
      var m = document.getElementById('mkt-help-modal');
      if (m) m.classList.remove('is-open');
    }

    function buildPanel() {
      var header = panel.querySelector('.panel-header');
      if (header) {
        var during = isDuringMarket();
        header.querySelector('.pub-time').outerHTML =
          '<div style="display:flex;align-items:center;gap:4px;">' +
          '<span class="pub-time mkt-live-time">' +
          '<span class="mkt-live-dot"' + (during ? '' : ' style="display:none"') + '></span>' +
          '<span class="mkt-live-label">' + (during ? '실시간' : '장 마감') + '</span>' +
          '</span>' +
          '<button class="mkt-refresh-btn" title="페이지 새로고침" onclick="window.location.reload()">' +
          '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' +
          '<path d="M13.5 8A5.5 5.5 0 1 1 10 3.07"/>' +
          '<polyline points="10 1 10 4 13 4"/>' +
          '</svg>' +
          '</button>' +
          '</div>';
        // ? 도움말 버튼 — section-title 안에 append (inline-flex gap으로 바로 옆에 붙음)
        var titleEl = header.querySelector('.section-title');
        if (titleEl && !titleEl.querySelector('.mkt-help-btn')) {
          var helpBtn = document.createElement('button');
          helpBtn.className = 'info-icon-btn';
          helpBtn.title = '그래프 읽는 법';
          helpBtn.textContent = '?';
          helpBtn.addEventListener('click', openMktHelpModal);
          titleEl.appendChild(helpBtn);
        }
      }
      injectMktHelpModal();

      var list = panel.querySelector('.mkt-list');
      list.innerHTML =
        // 수급
        '<div class="mkt-section-label">오늘 수급 · 코스피</div>' +
        '<div class="mkt-list" id="mkt-live-supply" style="padding:0 14px">' +
        mkSupplyRow('indv', '개인') +
        mkSupplyRow('inst', '기관') +
        mkSupplyRow('frgn', '외국인') +
        '</div>' +
        // 국내 지수
        '<div class="mkt-section-label">국내 지수</div>' +
        '<div id="mkt-live-rows">' +
        mkIndexRow('kosdaq',  '코스닥',         '') +
        mkIndexRow('kospi200','코스피200', '') +
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
        '<span style="color:var(--dn)">팔기</span>' +
        '<span style="color:var(--up)">사기</span>' +
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
        if (sparkData[key].length > 500) sparkData[key].shift();
        if (sparkData[key].length >= 2) drawSparkline('ml-' + key + '-spark', sparkData[key]);
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
        if (sparkData.forex.length > 500) sparkData.forex.shift();
        if (sparkData.forex.length >= 2) drawSparkline('ml-fx-spark', sparkData.forex);
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

    function saveSparkData() {
      try { sessionStorage.setItem(SPARK_KEY, JSON.stringify(sparkData)); } catch (e) {}
    }

    function poll() {
      fetch('/api/market', { signal: AbortSignal.timeout(8000) })
        .then(function(r) { return r.ok ? r.json() : Promise.reject(); })
        .then(function(d) { applyData(d); saveSparkData(); })
        .catch(function() {});
    }

    buildPanel();

    // 과거 브리핑: market-{date}.json 으로 정적 표시, 폴링 없음
    if (mktIsPast) {
      var mktLabelEl = panel.querySelector('.mkt-live-label');
      var mktDotEl   = panel.querySelector('.mkt-live-dot');
      if (mktLabelEl) mktLabelEl.textContent = '마감';
      if (mktDotEl)   mktDotEl.style.display = 'none';
      fetch('/data/market-' + mktUrlMatch[1] + '.json', { signal: AbortSignal.timeout(5000) })
        .then(function(r) { return r.ok ? r.json() : Promise.reject(); })
        .then(function(d) { applyData(d); })
        .catch(function() {});
      return;
    }

    // 복원된 sessionStorage 데이터로 즉시 표시 (인트라데이 로드 전 임시)
    ['kosdaq', 'kospi200'].forEach(function(key) {
      if (sparkData[key].length >= 2) drawSparkline('ml-' + key + '-spark', sparkData[key]);
    });
    if (sparkData.forex.length >= 2) drawSparkline('ml-fx-spark', sparkData.forex);

    // 일중 전체 흐름 초기화 — 오늘 09:00부터 현재까지 데이터로 교체
    function fetchIntraday() {
      fetch('/api/intraday', { signal: AbortSignal.timeout(12000) })
        .then(function(r) { return r.ok ? r.json() : Promise.reject(); })
        .then(function(d) {
          ['kosdaq', 'kospi200', 'forex'].forEach(function(key) {
            var arr = d[key];
            if (arr && arr.length >= 2) {
              sparkData[key] = arr;
              var canvasId = key === 'forex' ? 'ml-fx-spark' : 'ml-' + key + '-spark';
              drawSparkline(canvasId, arr);
            }
          });
          saveSparkData();
        })
        .catch(function() {});
    }
    fetchIntraday();

    poll();
    if (isDuringMarket()) {
      polling = setInterval(poll, 60000);
      scheduleCloseLabel();
    }
  }

  /* ── 지금 코스피 밴드 — 본문 최상단 라이브 지표. 코스피 브리핑 전용 ──────────
     상태: 장전(08:50~08:59)·장중(09:00~15:29 폴링)·장후(15:30~ 최종값)·과거(정적)·숨김.
     데이터: /api/kospi-live(지수)·/api/market(코스닥·원달러·수급)·kospi-news(장중 이슈).
     실측만 채우고, 없으면 해당 영역 숨김(데이터 정합성). 날짜는 URL에서 파싱. */
  function initNowBand() {
    var band = document.getElementById('now-band');
    if (!band) return;

    function kstNow()  { return new Date(Date.now() + 9 * 3600 * 1000); }
    function kstMins() { var k = kstNow(); return k.getUTCHours() * 60 + k.getUTCMinutes(); }

    var k0 = kstNow();
    var todayKst = k0.getUTCFullYear() + '-' +
      String(k0.getUTCMonth() + 1).padStart(2, '0') + '-' +
      String(k0.getUTCDate()).padStart(2, '0');
    var m       = location.pathname.match(/\/briefings\/(\d{4}-\d{2}-\d{2})\//);
    var urlDate = m ? m[1] : todayKst;
    if (urlDate > todayKst) return;                 // 미래: 숨김
    var isPast  = urlDate < todayKst;

    // 상태 판정 (당일)
    var mins = kstMins(), day = k0.getUTCDay(), weekend = (day === 0 || day === 6);
    var mode = null;                                // 'past' | 'pre' | 'live' | 'after'
    if (isPast)              mode = 'past';
    else if (weekend)        return;                // 주말 당일: 숨김
    else if (mins < 530)     return;                // 08:50 이전: 숨김
    else if (mins < 540)     mode = 'pre';          // 08:50~08:59
    else if (mins < 930)     mode = 'live';         // 09:00~15:29
    else                     mode = 'after';        // 15:30~

    // 헤더 세팅
    var dot = document.getElementById('nb-dot');
    var titleWrap = document.getElementById('nb-title');
    var titleText = document.getElementById('nb-title-text');
    var subEl = document.getElementById('nb-sub');
    var kospiTag = document.getElementById('nb-kospi-tag');
    if (mode === 'live') {
      titleWrap.classList.add('live');
      titleText.textContent = '지금 코스피';
      subEl.textContent = '09:00부터 실시간 갱신 · LIVE';
    } else {
      dot.classList.add('pre');
      if (mode === 'after') {
        titleText.textContent = '지금 코스피';
        subEl.textContent = '장 마감 · 최종 종가';
      } else if (mode === 'pre') {
        titleText.textContent = '시장 현황';
        subEl.textContent = '장 시작 전 · 지난 종가 기준';
        if (kospiTag) kospiTag.hidden = false;
      } else { // past
        titleText.textContent = '시장 현황';
        subEl.textContent = urlDate + ' 마감 기준';
        if (kospiTag) kospiTag.hidden = false;
        var sub = document.getElementById('nb-subline');
        if (sub) sub.hidden = true;                 // 과거: 코스닥·원달러 데이터 없음
      }
    }
    band.hidden = false;

    // 표시 헬퍼
    function fmt(n, dp) { return Number(n).toLocaleString('ko-KR', { minimumFractionDigits: dp, maximumFractionDigits: dp }); }
    function setChg(el, pct) {
      if (!el) return;
      var p = Number(pct) || 0;
      el.className = p > 0 ? 'up' : (p < 0 ? 'dn' : '');
      el.textContent = (p > 0 ? '▲ ' : (p < 0 ? '▼ ' : '')) + Math.abs(p).toFixed(2) + '%';
    }

    // 스파크라인 누적 (코스피 지수)
    var SPARK_KEY = 'nb-spark-v1';
    var sparkArr = (function () {
      try { var s = JSON.parse(sessionStorage.getItem(SPARK_KEY) || 'null'); return Array.isArray(s) ? s : []; }
      catch (e) { return []; }
    })();

    function applyKospi(price, pct) {
      if (price == null) return;
      var v = document.getElementById('nb-kospi-val');
      if (v) v.textContent = fmt(price, 2);
      setChg(document.getElementById('nb-kospi-chg'), pct);
      if (mode === 'live') {                          // 스파크는 장중 누적만
        sparkArr.push(Number(price));
        if (sparkArr.length > 400) sparkArr.shift();
        try { sessionStorage.setItem(SPARK_KEY, JSON.stringify(sparkArr)); } catch (e) {}
      }
      if (sparkArr.length >= 2) drawSparkline('nb-spark', sparkArr);
    }
    function applyMarket(d) {
      if (!d) return;
      if (d.kosdaq) {
        var kv = document.getElementById('nb-kosdaq-val');
        if (kv) kv.textContent = fmt(d.kosdaq.price, 2);
        setChg(document.getElementById('nb-kosdaq-chg'), d.kosdaq.changePct);
      }
      if (d.forex) {
        var fv = document.getElementById('nb-fx-val');
        if (fv) fv.textContent = fmt(d.forex.price, 2);
        setChg(document.getElementById('nb-fx-chg'), d.forex.changePct);
      }
      if (d.investor) {
        var sup = document.getElementById('nb-supply'), any = false;
        var map = { 'nb-indv': d.investor.individual, 'nb-inst': d.investor.institution, 'nb-frgn': d.investor.foreign };
        Object.keys(map).forEach(function (id) {
          var val = map[id], el = document.getElementById(id);
          if (!el || val == null) return;
          any = true;
          el.textContent = (val >= 0 ? '+' : '') + Math.round(val).toLocaleString();
          el.className = val >= 0 ? 'up' : 'dn';
        });
        if (any && sup) sup.hidden = false;
      }
    }
    function applyIssues(data) {
      if (!data) return;
      if (data.date && data.date !== urlDate) return;   // 당일 첫 수집 전 어제 데이터 노출 방지
      var box = document.getElementById('nb-issues');
      if (!box) return;
      var hist = (data.history || []).filter(function (it) {
        var p = (it.time || '').split(':'); if (p.length < 2) return false;
        var mm = parseInt(p[0], 10) * 60 + parseInt(p[1], 10);
        return mm >= 540 && mm < 930;                     // MARKET 슬롯
      });
      var rows = [];
      hist.slice(0, 3).forEach(function (it) {
        var title = (it.market && it.market.title) || (it.stock && it.stock.title) || '';
        title = title.replace(/\[.*?\]/g, '').replace(/\s*[-–—]\s*[가-힣A-Za-z0-9·]{2,15}\s*$/u, '').trim();
        if (title) rows.push('<div class="nb-issue"><span class="nb-issue__t">' + escHtml(it.time || '') + '</span><span>' + escHtml(title) + '</span></div>');
      });
      if (rows.length) { box.innerHTML = rows.join(''); box.hidden = false; }
    }

    // fetch
    function pollKospi() {
      fetch('/api/kospi-live').then(function (r) { return r.ok ? r.json() : Promise.reject(); })
        .then(function (d) { if (d) applyKospi(d.price, d.changePct || 0); }).catch(function () {});
    }
    function pollMarket() {
      fetch('/api/market', { signal: AbortSignal.timeout(8000) }).then(function (r) { return r.ok ? r.json() : Promise.reject(); })
        .then(applyMarket).catch(function () {});
    }
    function loadIssues() {
      fetch('/data/kospi-news-' + urlDate + '.json').then(function (r) { return r.ok ? r.json() : Promise.reject(); })
        .then(applyIssues)
        .catch(function () {
          fetch('/data/kospi-news-live.json').then(function (r) { return r.ok ? r.json() : null; }).then(applyIssues).catch(function () {});
        });
    }

    if (mode === 'past') {
      fetch('/data/market-' + urlDate + '.json').then(function (r) { return r.ok ? r.json() : Promise.reject(); })
        .then(function (d) { if (d && d.kospi) applyKospi(d.kospi.price, d.kospi.changePct || 0); }).catch(function () {});
      loadIssues();
    } else if (mode === 'pre') {
      pollKospi(); pollMarket();                         // 장전: API가 전일 종가/수급 반환
    } else if (mode === 'live') {
      pollKospi(); pollMarket(); loadIssues();
      setInterval(pollKospi, 10000);
      setInterval(pollMarket, 60000);
      setInterval(loadIssues, 300000);
    } else { // after
      pollKospi(); pollMarket(); loadIssues();           // 최종값 1회
    }
  }

  /* ── 장중 '오늘의 특이 신호' 사이드바 위젯 — 장중(/api/signals phase==='intraday')에만
     노출하며 시장 지표 패널(#market-data-panel)을 완전히 대체한다. 장외·과거/미래 브리핑·
     데이터 없음이면 위젯을 숨기고 시장 지표를 그대로 둔다. 코스피 당일 브리핑 전용. ── */
  function initSidebarSignals() {
    var box = document.getElementById('signals-today');
    if (!box) return;
    var list = document.getElementById('signals-today-list');
    var mktPanel = document.getElementById('market-data-panel');

    function kstNow() { return new Date(Date.now() + 9 * 3600 * 1000); }
    var k0 = kstNow();
    var todayKst = k0.getUTCFullYear() + '-' +
      String(k0.getUTCMonth() + 1).padStart(2, '0') + '-' +
      String(k0.getUTCDate()).padStart(2, '0');
    var m = location.pathname.match(/\/briefings\/(\d{4}-\d{2}-\d{2})\//);
    var urlDate = m ? m[1] : todayKst;
    if (urlDate !== todayKst) return;   // 과거·미래 브리핑: 장중 신호는 '오늘'만 의미 → 시장 지표 유지

    var SIDEBAR_MAX = 6;   // 사이드바 컴팩트 노출 개수 (API는 최대 8개 내려줌)
    function rowHtml(s) {
      var pct = Number(s.pct) || 0;
      var dir = pct >= 0 ? 'up' : 'dn';
      var pctTxt = (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%';
      var badges = (s.badges || []).slice(0, 2).map(function (b) {
        var flow = /^(외국인|기관)/.test(b);
        return '<span class="ssig-bdg' + (flow ? ' flow' : '') + '">' + escHtml(b) + '</span>';
      }).join('');
      return '<a class="ssig-row ssig-row--sig" href="/stocks/' + encodeURIComponent(s.code) + '/">'
        + '<span class="ssig-sig-main"><span class="ssig-name">' + escHtml(s.name || '') + '</span>'
        + (badges ? '<span class="ssig-bdgs">' + badges + '</span>' : '') + '</span>'
        + '<span class="ssig-chg ' + dir + '">' + pctTxt + '</span></a>';
    }

    var scheduled = false;
    function poll() {
      fetch('/api/signals', { signal: AbortSignal.timeout(8000) })
        .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
        .then(function (data) {
          // 장외(마감·주말·휴장)이거나 신호가 없으면 특이신호를 숨기고 시장 지표를 유지한다.
          if (!data || data.phase !== 'intraday' || !Array.isArray(data.signals) || !data.signals.length) {
            box.hidden = true;
            if (mktPanel) mktPanel.style.display = '';
            return;
          }
          if (list) list.innerHTML = data.signals.slice(0, SIDEBAR_MAX).map(rowHtml).join('');
          box.hidden = false;
          if (mktPanel) mktPanel.style.display = 'none';   // 장중: 시장 지표 완전 교체
          if (!scheduled) { scheduled = true; setInterval(poll, 60000); }
        })
        .catch(function () {});
    }
    poll();
  }

  /* ── 이슈 브리핑 동적 fetch (B안) ──────────────────────────────────────
     kospi-news-{date}.json 을 fetch → data-slot 필터링 → 렌더링
     발행 시점과 무관하게 페이지 로드 시 최신 이슈를 표시한다.
     history 1개 이상일 때만 섹션을 표시하고, 0개면 wrap 을 숨긴다.

     슬롯별 수록 시각:
       MARKET      → 09:00~15:29 수집분 (코스피 예측 브리핑)
       POST_MARKET → 16:35~21:29 수집분 (코스피 마감 브리핑)
       US_MARKET   → 21:30~01:00 수집분 (미국 시장 브리핑)
  ── */
  function initIssueBriefing() {
    var wrap = document.getElementById('issue-briefing-wrap');
    if (!wrap) return;

    var date = wrap.dataset.date;   // YYYY-MM-DD
    var slot = wrap.dataset.slot;   // MARKET | POST_MARKET | US_MARKET
    if (!date || !slot) return;

    var anchorScrolled = false;     // #issue-briefing-wrap 앵커 진입 시 최초 1회만 수동 스크롤

    // 슬롯별 허용 시각 범위 (KST, 분 단위)
    var SLOT_RANGE = {
      MARKET:      { from: 540,  to: 930  },   // 09:00~15:29
      POST_MARKET: { from: 995,  to: 1290 },   // 16:35~21:29
      US_MARKET:   { from: 1290, to: 1500 },   // 21:30~24:59  (+익일 00:00~01:00)
    };

    function timeToMins(timeStr) {
      // "HH:MM" → 분
      var parts = (timeStr || '').split(':');
      if (parts.length < 2) return -1;
      return parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10);
    }

    function inSlot(timeStr) {
      var m = timeToMins(timeStr);
      if (m < 0) return false;
      var r = SLOT_RANGE[slot];
      if (!r) return true;  // 알 수 없는 슬롯은 전부 허용
      if (slot === 'US_MARKET') {
        // 21:30~23:59 또는 00:00~01:00(익일 = 0~60분)
        return m >= r.from || m <= 60;
      }
      return m >= r.from && m < r.to;
    }

    function cleanBrackets(text) {
      if (!text) return text;
      return text.replace(/\[.*?\]/g, '').replace(/\(.*?\)/g, '').replace(/\s{2,}/g, ' ').trim();
    }

    function cleanTitle(text) {
      if (!text) return text;
      // 대괄호·소괄호 제거 후 끝의 "- 언론사명" 패턴 제거 (2~15자 단어)
      return text.replace(/\[.*?\]/g, '').replace(/\(.*?\)/g, '')
        .replace(/\s*[-–—]\s*[가-힣A-Za-z0-9·]{2,15}\s*$/u, '')
        .replace(/\s{2,}/g, ' ').trim();
    }

    function tlIssue(issue, type) {
      if (!issue || !issue.title) return '';
      var label = type === 'market' ? '시장' : '종목';
      return '<div class="ib-line">'
        + '<span class="ib-badge ' + type + '">' + label + '</span>'
        + '<span class="ib-hl">' + escHtml(cleanTitle(issue.title)) + '</span>'
        + '</div>';
    }

    function render(data) {
      if (!data) return;
      // JSON 날짜가 브리핑 날짜와 다르면 표시하지 않음 (당일 첫 수집 전 어제 데이터 노출 방지)
      if (data.date && data.date !== date) {
        wrap.style.display = 'none';
        return;
      }

      // history에서 슬롯에 해당하는 항목만 필터링
      var hist = (data.history || []).filter(function(item) {
        return inSlot(item.time);
      });

      if (hist.length === 0) {
        wrap.style.display = 'none';
        return;
      }

      // 메타(업데이트 시각) 갱신
      var metaEl = document.getElementById('issue-briefing-meta');
      if (metaEl && data.updated_at) metaEl.textContent = data.updated_at + ' 업데이트';

      // 타임라인 렌더링 (B안 — 컴팩트 피드)
      var tlEl = document.getElementById('issue-briefing-tl');
      if (!tlEl) return;

      tlEl.innerHTML = hist.map(function(item, i) {
        var isLatest = (i === 0);
        var mIssue = item.market || null;
        var sIssue = item.stock  || null;
        var hasBoth = mIssue && sIssue;

        return '<div class="ib-item' + (isLatest ? ' is-latest' : '') + '">'
          + '<span class="ib-time">' + escHtml(item.time || '') + '</span>'
          + '<div class="ib-body">'
          + tlIssue(mIssue, 'market')
          + (hasBoth ? '<div class="ib-sep"></div>' : '')
          + tlIssue(sIssue, 'stock')
          + '</div>'
          + '</div>';
      }).join('');

      wrap.style.display = '';

      // 종목 홈 브리핑 커넥터에서 #issue-briefing-wrap 앵커로 진입한 경우:
      // 이 섹션은 로드 시 display:none이라 브라우저 기본 앵커 스크롤이 동작하지 않는다.
      // 표시로 전환된 직후 최초 1회만 수동 스크롤(스티키 GNB 높이만큼 오프셋).
      if (!anchorScrolled && location.hash === '#issue-briefing-wrap') {
        anchorScrolled = true;
        wrap.style.scrollMarginTop = '72px';
        requestAnimationFrame(function() {
          wrap.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
      }
    }

    // 오늘 날짜 판별
    var kstNow = new Date(Date.now() + 9 * 3600 * 1000);
    var todayKst = kstNow.getUTCFullYear() + '-'
      + String(kstNow.getUTCMonth() + 1).padStart(2, '0') + '-'
      + String(kstNow.getUTCDate()).padStart(2, '0');
    var isToday = (date === todayKst);

    function tryFetch(url, timeout) {
      return fetch(url, { signal: AbortSignal.timeout(timeout || 6000) })
        .then(function(r) { return r.ok ? r.json() : Promise.reject(); });
    }

    function fetchAndRender() {
      if (isToday) {
        // 오늘은 live.json → 실패 시 /api/news-live fallback (사내망 /data/ 차단 대응)
        tryFetch('/data/kospi-news-live.json?t=' + Date.now(), 4000)
          .catch(function() { return tryFetch('/api/data?f=news-live', 8000); })
          .then(render)
          .catch(function() { wrap.style.display = 'none'; });
      } else {
        // 과거 날짜는 아카이브 JSON
        tryFetch('/data/kospi-news-' + date + '.json', 6000)
          .then(render)
          .catch(function() { wrap.style.display = 'none'; });
      }
    }

    fetchAndRender();

    // 장중(09:00~15:30 KST) 5분마다 자동 갱신
    if (isToday) {
      var kstMins = kstNow.getUTCHours() * 60 + kstNow.getUTCMinutes();
      if (kstMins >= 540 && kstMins < 930) {
        setInterval(fetchAndRender, 5 * 60 * 1000);
      }
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
  window.initIssueBriefing = initIssueBriefing;
})();
