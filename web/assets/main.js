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

  /* ── 접힘 토글 (장 시작 전 섹션) ── */
  function togglePreOpen() {
    const content = document.getElementById('pre-open-content');
    const chevron = document.getElementById('pre-open-chevron');
    if (!content) return;
    const collapsed = content.classList.contains('collapsed');
    content.classList.toggle('collapsed', !collapsed);
    if (chevron) chevron.classList.toggle('open', !collapsed);
  }
  function applyTimeCollapse() {
    // 예측 섹션은 항상 열린 상태 유지
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
    applyTimeCollapse();
    initModals();
    renderSupplyFlows();
  });

  /* ── 전역 노출 (인라인 핸들러·섹션 템플릿용) ── */
  window.toggleTheme = toggleTheme;
  window.togglePreOpen = togglePreOpen;
  window.openModal = openModal;
  window.closeModal = closeModal;
  window.drawSparkline = drawSparkline;
  window.drawMiniChart = drawMiniChart;
  window.drawCloseChart = drawCloseChart;
  window.renderInstList = renderInstList;
})();
