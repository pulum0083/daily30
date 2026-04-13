/* ============================================================
     Accordion logic — with scroll-position compensation
  ============================================================ */
  function toggleMktGroup(id) {
    const el = document.getElementById(id);
    if (el) el.classList.toggle('is-collapsed');
  }

  function switchItemTab(key, tab) {
    ['kospi', 'us'].forEach(t => {
      const isActive = t === tab;
      const tabEl   = document.getElementById('itab-'   + key + '-' + t);
      const panelEl = document.getElementById('ipanel-' + key + '-' + t);
      if (tabEl)   tabEl.classList.toggle('is-active', isActive);
      if (panelEl) panelEl.classList.toggle('is-active', isActive);
    });
  }

  function toggleAccordionUs(index) {
    const items = document.querySelectorAll('#accordion-us .accordion-item');
    const item  = [...items].find(el => el.dataset.indexUs === String(index)) || items[index];
    if (!item) return;
    const isOpen = item.classList.contains('is-open');
    items.forEach(el => el.classList.remove('is-open'));
    if (!isOpen) item.classList.add('is-open');
  }

  function toggleTheme() {
    const html = document.documentElement;
    if (html.classList.contains('dark')) {
      html.classList.remove('dark');
      html.classList.add('light');
      localStorage.setItem('theme', 'light');
    } else {
      html.classList.remove('light');
      html.classList.add('dark');
      localStorage.setItem('theme', 'dark');
    }
  }
  /* Theme init — default: light. Respect saved preference. */
  (function() {
    const saved = localStorage.getItem('theme');
    const html = document.documentElement;
    if (saved === 'dark') {
      html.classList.remove('light');
      html.classList.add('dark');
    } else {
      /* light is default — remove dark class that HTML might have */
      html.classList.remove('dark');
      html.classList.add('light');
    }
  })();

  function toggleAccordion(index) {
    const items     = document.querySelectorAll('.accordion-item');
    const item      = [...items].find(el => el.dataset.index === String(index)) || items[index];

    /* Snapshot the clicked item's top before any DOM change */
    const headerTop = item.querySelector('.accordion-header').getBoundingClientRect().top;

    /* Toggle only the clicked item — others stay as-is */
    item.classList.toggle('is-open');

    /* Restore the item's visual position so content above doesn't jump */
    requestAnimationFrame(() => {
      const newTop  = item.querySelector('.accordion-header').getBoundingClientRect().top;
      const delta   = newTop - headerTop;
      if (Math.abs(delta) > 1) window.scrollBy({ top: delta, behavior: 'instant' });
    });
  }

  /* ============================================================
     GNB clock
  ============================================================ */
  function updateClock() {
    const now = new Date();
    const days = ['일','월','화','수','목','금','토'];
    const day = days[now.getDay()];
    const y = now.getFullYear();
    const m = String(now.getMonth()+1).padStart(2,'0');
    const d = String(now.getDate()).padStart(2,'0');
    const hh = String(now.getHours()).padStart(2,'0');
    const mm = String(now.getMinutes()).padStart(2,'0');
    document.getElementById('gnb-date').textContent =
      `${y}.${m}.${d} (${day}) ${hh}:${mm}`;
  }
  updateClock();
  setInterval(updateClock, 30000);

  /* ============================================================
     Area Sparkline — compact 64×28 canvas
  ============================================================ */
  const UP_COLOR   = '#E03131';
  const DOWN_COLOR = '#2563EB';

  function drawSparkline(canvasId, data, color) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const W = canvas.offsetWidth  || 64;
    const H = canvas.offsetHeight || 36;
    canvas.width  = W * dpr;
    canvas.height = H * dpr;
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);

    const min = Math.min(...data), max = Math.max(...data);
    const range = max - min || 1;
    const pad = 2;

    const pts = data.map((v, i) => ({
      x: (i / (data.length - 1)) * W,
      y: H - pad - ((v - min) / range) * (H - pad * 2)
    }));

    /* Area fill */
    const grad = ctx.createLinearGradient(0, 0, 0, H);
    grad.addColorStop(0, color + '38');
    grad.addColorStop(1, color + '00');
    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) {
      const cx = (pts[i-1].x + pts[i].x) / 2;
      ctx.bezierCurveTo(cx, pts[i-1].y, cx, pts[i].y, pts[i].x, pts[i].y);
    }
    ctx.lineTo(pts.at(-1).x, H);
    ctx.lineTo(pts[0].x, H);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    /* Line */
    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) {
      const cx = (pts[i-1].x + pts[i].x) / 2;
      ctx.bezierCurveTo(cx, pts[i-1].y, cx, pts[i].y, pts[i].x, pts[i].y);
    }
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.lineJoin = 'round';
    ctx.stroke();

    /* End dot */
    ctx.beginPath();
    ctx.arc(pts.at(-1).x, pts.at(-1).y, 2.2, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
  }

  /* ============================================================
     Fear & Greed mini gauge (canvas semicircle)
  ============================================================ */
  function fgMeta(v) {
    if (v <= 25) return { color:'#1D4ED8', label:'극단적 공포', badge:'xfear' };
    if (v <= 45) return { color:'#2563EB', label:'공포',       badge:'fear'  };
    if (v <= 55) return { color:'#CA8A04', label:'중립',       badge:'neutral'};
    if (v <= 75) return { color:'#E03131', label:'탐욕',       badge:'greed' };
    return            { color:'#B91C1C', label:'극단적 탐욕',  badge:'greed' };
  }

  function drawFGGauge(value) {
    const canvas = document.getElementById('fg-gauge-canvas');
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const cssW = canvas.offsetWidth  || 118;
    const cssH = canvas.offsetHeight || 64;
    canvas.width  = cssW * dpr;
    canvas.height = cssH * dpr;
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);

    const cx     = cssW / 2;
    const cy     = cssH * 0.82;
    const outerR = cssW * 0.44;
    const innerR = outerR * 0.60;
    const midR   = (outerR + innerR) / 2;
    const trkW   = outerR - innerR;

    ctx.clearRect(0, 0, cssW, cssH);

    const isDark = document.documentElement.classList.contains('dark');
    const trackBg    = isDark ? '#3A3C3E' : '#E5E5E6';
    const pivotFill  = isDark ? '#1C1D1F' : '#FFFFFF';
    const pivotStroke= isDark ? '#3C3E40' : '#D0D1D2';

    /* Background track */
    ctx.beginPath();
    ctx.arc(cx, cy, midR, Math.PI, 0, false);
    ctx.strokeStyle = trackBg;
    ctx.lineWidth = trkW + 2;
    ctx.lineCap = 'butt';
    ctx.stroke();

    /* 5 color segments: angle = π*(1 + pct/100) */
    const SEGS = [
      [0, 20,  '#1D4ED8'],
      [20,40,  '#3B82F6'],
      [40,60,  '#CA8A04'],
      [60,80,  '#EF4444'],
      [80,100, '#B91C1C'],
    ];
    SEGS.forEach(([from, to, col]) => {
      ctx.beginPath();
      ctx.arc(cx, cy, midR, Math.PI*(1+from/100), Math.PI*(1+to/100), false);
      ctx.strokeStyle = col;
      ctx.lineWidth = trkW;
      ctx.lineCap = 'butt';
      ctx.stroke();
    });

    /* Separator ticks */
    [20,40,60,80].forEach(pct => {
      const a = Math.PI*(1+pct/100);
      ctx.beginPath();
      ctx.moveTo(cx+(innerR-1)*Math.cos(a), cy+(innerR-1)*Math.sin(a));
      ctx.lineTo(cx+(outerR+1)*Math.cos(a), cy+(outerR+1)*Math.sin(a));
      ctx.strokeStyle = pivotFill;
      ctx.lineWidth = 1.2;
      ctx.stroke();
    });

    /* Needle — thin tapered pointer reaching arc midpoint */
    const needleA  = Math.PI * (1.5 + value/100);
    const nTip     = midR + 2;   /* tip lands just past arc midpoint */
    const nTail    = trkW * 0.3; /* short tail below pivot */
    const nHalfW   = 2;          /* half-width at widest (near pivot) */
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(needleA);
    ctx.beginPath();
    ctx.moveTo(-nHalfW,  nTail);   /* base left */
    ctx.lineTo( nHalfW,  nTail);   /* base right */
    ctx.lineTo( 0.6,    -nTip);    /* tip right */
    ctx.lineTo(-0.6,    -nTip);    /* tip left */
    ctx.closePath();
    ctx.fillStyle = isDark ? '#E8EAEB' : '#1A1B1D';
    ctx.shadowColor = 'rgba(0,0,0,0.55)';
    ctx.shadowBlur  = 4;
    ctx.fill();
    ctx.shadowBlur = 0;
    ctx.restore();

    /* Pivot — drawn after needle so it caps the base cleanly */
    const pivR = trkW * 0.38;
    ctx.beginPath();
    ctx.arc(cx, cy, pivR, 0, Math.PI*2);
    ctx.fillStyle = pivotFill;
    ctx.fill();
    ctx.strokeStyle = pivotStroke;
    ctx.lineWidth = 1.5;
    ctx.stroke();

    /* Axis labels */
    ctx.font = `600 ${Math.round(cssW*0.072)}px system-ui,sans-serif`;
    ctx.fillStyle = '#9CA3AF';
    ctx.textBaseline = 'middle';
    ctx.textAlign = 'right';
    ctx.fillText('0',   cx - outerR - 3, cy);
    ctx.textAlign = 'left';
    ctx.fillText('100', cx + outerR + 3, cy);
    ctx.textAlign = 'center';
    ctx.fillText('50',  cx, cy - outerR - 3);
  }

  function setFearGreed(value) {
    drawFGGauge(value);
    const m = fgMeta(value);
    const valEl = document.getElementById('fg-value');
    const lblEl = document.getElementById('fg-label');
    const bdgEl = document.getElementById('fg-badge');
    if (valEl) { valEl.textContent = value; valEl.style.color = m.color; }
    if (lblEl) { lblEl.textContent = m.label; lblEl.style.color = m.color; }
    if (bdgEl) {
      bdgEl.className = `fg-badge ${m.badge}`;
      const labels = { xfear:'EXTREME FEAR', fear:'FEAR', neutral:'NEUTRAL', greed:'GREED' };
      bdgEl.textContent = labels[m.badge] || m.badge.toUpperCase();
    }
  }

  /* ============================================================
     Market data — loaded from window.MARKET_DATA (set by agent)
  ============================================================ */
  const _defaults = {
    kospi:  { base: 0, chg: 0, data:[0], valId:'kospi-val',  badgeId:'kospi-badge',  canvasId:'c-kospi'  },
    kosdaq: { base: 0, chg: 0, data:[0], valId:'kosdaq-val', badgeId:'kosdaq-badge', canvasId:'c-kosdaq' },
    nasdaq: { base: 0, chg: 0, data:[0], valId:'nasdaq-val', badgeId:'nasdaq-badge', canvasId:'c-nasdaq' },
    nq:     { base: 0, chg: 0, data:[0], valId:'nq-val',    badgeId:'nq-badge',    canvasId:'c-nq'    },
    dji:    { base: 0, chg: 0, data:[0], valId:'dji-val',   badgeId:'dji-badge',   canvasId:'c-dji'   },
    sox:    { base: 0, chg: 0, data:[0], valId:'sox-val',   badgeId:'sox-badge',   canvasId:'c-sox'   },
    oil:    { base: 0, chg: 0, data:[0], valId:'oil-val',   badgeId:'oil-badge',   canvasId:'c-oil'   },
    usd:    { base: 0, chg: 0, data:[0], valId:'usd-val',   badgeId:'usd-badge',   canvasId:'c-usd'   },
    dxy:    { base: 0, chg: 0, data:[0], valId:'dxy-val',   badgeId:'dxy-badge',   canvasId:'c-dxy'   },
  };

  /* Merge agent-provided data into defaults */
  const marketData = {};
  const src = window.MARKET_DATA || {};
  Object.entries(_defaults).forEach(([key, def]) => {
    const s = src[key] || {};
    const chg = s.chg ?? def.chg;
    marketData[key] = {
      base:     s.base ?? def.base,
      chg:      chg,
      data:     s.data && s.data.length > 1 ? s.data : def.data,
      color:    chg >= 0 ? UP_COLOR : DOWN_COLOR,
      valId:    def.valId,
      badgeId:  def.badgeId,
      canvasId: def.canvasId,
    };
  });

  function formatVal(key, v) {
    if (key === 'oil') return '$' + v.toFixed(2);
    if (['kospi','kosdaq','nasdaq','dji','nq','usd'].includes(key))
      return v.toLocaleString('ko-KR', {minimumFractionDigits:2,maximumFractionDigits:2});
    return v.toFixed(2);
  }

  const OIL_THRESHOLD = 3.0;
  function updateOilReason() {
    const li = document.getElementById('oil-reason-li');
    if (!li) return;
    const chg = marketData.oil.chg;
    if (Math.abs(chg) >= OIL_THRESHOLD) {
      const dir = chg > 0 ? '급등' : '급락';
      const sign = chg > 0 ? '+' : '';
      li.textContent = `WTI 국제유가 ${dir}(${sign}${chg.toFixed(2)}%)으로 에너지·화학 업종 변동성 확대 예상`;
      li.style.display = '';
    } else {
      li.style.display = 'none';
    }
  }

  function renderAll() {
    Object.entries(marketData).forEach(([key, d]) => {
      const valEl   = document.getElementById(d.valId);
      const badgeEl = document.getElementById(d.badgeId);
      if (valEl)   valEl.textContent = formatVal(key, d.base);
      if (badgeEl) {
        const sign = d.chg >= 0 ? '+' : '';
        badgeEl.textContent = `${sign}${d.chg.toFixed(2)}%`;
        badgeEl.className = 'mkt-chg ' + (d.chg >= 0 ? 'up' : 'down');
      }
      drawSparkline(d.canvasId, d.data, d.color);
    });
    updateOilReason();
  }

  /* Fear & Greed value from agent data */
  let fgVal = (window.MARKET_DATA && window.MARKET_DATA.fearGreed) ? window.MARKET_DATA.fearGreed.value : 50;

  /* ============================================================
     Sparkline hover tooltip (value + time)
  ============================================================ */
  const sparkTooltip = document.createElement('div');
  sparkTooltip.style.cssText = [
    'position:fixed',
    'background:var(--surface)',
    'border:1px solid var(--line-primary)',
    'border-radius:7px',
    'padding:5px 10px',
    'pointer-events:none',
    'z-index:9999',
    'white-space:nowrap',
    'display:none',
    'box-shadow:var(--shadow-20)',
    'line-height:1.4',
  ].join(';');
  document.body.appendChild(sparkTooltip);

  /* Generate a time label for each data point (5-min intervals, looking back) */
  function sparkTimeLabel(idx, total) {
    const minutesAgo = (total - 1 - idx) * 5;
    const t = new Date(Date.now() - minutesAgo * 60000);
    const hh = String(t.getHours()).padStart(2, '0');
    const mm = String(t.getMinutes()).padStart(2, '0');
    return `${hh}:${mm}`;
  }

  function attachSparkTooltip(canvasId, dataKey) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    canvas.addEventListener('mousemove', e => {
      const rect  = canvas.getBoundingClientRect();
      const pct   = (e.clientX - rect.left) / rect.width;
      const arr   = marketData[dataKey].data;
      const idx   = Math.max(0, Math.min(arr.length - 1, Math.floor(pct * arr.length)));
      const val   = formatVal(dataKey, arr[idx]);
      const color = marketData[dataKey].color;
      const time  = sparkTimeLabel(idx, arr.length);

      sparkTooltip.innerHTML =
        `<div style="font-size:10px;color:var(--text-tertiary);font-weight:500;margin-bottom:1px;">${time}</div>` +
        `<div style="font-size:13px;font-weight:700;font-variant-numeric:tabular-nums;color:${color};">${val}</div>`;

      sparkTooltip.style.display = 'block';
      sparkTooltip.style.left = (e.clientX + 14) + 'px';
      sparkTooltip.style.top  = (e.clientY - 52) + 'px';
    });
    canvas.addEventListener('mouseleave', () => {
      sparkTooltip.style.display = 'none';
    });
  }

  /* Boot */
  /* ============================================================
     Stock pick MA20 mini chart
  ============================================================ */
  function drawStockMiniChart(canvasId, prices, ma20vals, ma200vals) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const dpr  = window.devicePixelRatio || 1;
    const cssW = canvas.offsetWidth  || 88;
    const cssH = canvas.offsetHeight || 52;
    canvas.width  = cssW * dpr;
    canvas.height = cssH * dpr;
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);

    const allVals = [...prices, ...ma20vals, ...(ma200vals || [])];
    const minV = Math.min(...allVals);
    const maxV = Math.max(...allVals);
    const range = maxV - minV || 1;
    const pad = { t: 5, b: 5, l: 3, r: 3 };
    const pW = cssW - pad.l - pad.r;
    const pH = cssH - pad.t - pad.b;

    const xOf = (i, len) => pad.l + (i / (len - 1)) * pW;
    const yOf = (v)       => pad.t + (1 - (v - minV) / range) * pH;

    /* MA200 thick purple dashed line (drawn first, behind) */
    if (ma200vals && ma200vals.length) {
      ctx.beginPath();
      ctx.setLineDash([4, 3]);
      ctx.strokeStyle = '#7C3AED';
      ctx.lineWidth = 1.8;
      ma200vals.forEach((v, i) => {
        i === 0 ? ctx.moveTo(xOf(i, ma200vals.length), yOf(v))
                : ctx.lineTo(xOf(i, ma200vals.length), yOf(v));
      });
      ctx.stroke();
      ctx.setLineDash([]);
    }

    /* MA20 thin amber dashed line */
    ctx.beginPath();
    ctx.setLineDash([3, 2]);
    ctx.strokeStyle = '#D97706';
    ctx.lineWidth = 1.2;
    ma20vals.forEach((v, i) => {
      i === 0 ? ctx.moveTo(xOf(i, ma20vals.length), yOf(v))
              : ctx.lineTo(xOf(i, ma20vals.length), yOf(v));
    });
    ctx.stroke();
    ctx.setLineDash([]);

    /* Price fill */
    ctx.beginPath();
    prices.forEach((v, i) => {
      i === 0 ? ctx.moveTo(xOf(i, prices.length), yOf(v))
              : ctx.lineTo(xOf(i, prices.length), yOf(v));
    });
    ctx.lineTo(xOf(prices.length - 1, prices.length), cssH - pad.b);
    ctx.lineTo(pad.l, cssH - pad.b);
    ctx.closePath();
    const grad = ctx.createLinearGradient(0, pad.t, 0, cssH - pad.b);
    grad.addColorStop(0, 'rgba(224,49,49,0.22)');
    grad.addColorStop(1, 'rgba(224,49,49,0.02)');
    ctx.fillStyle = grad;
    ctx.fill();

    /* Price line */
    ctx.beginPath();
    ctx.strokeStyle = '#E03131';
    ctx.lineWidth = 1.6;
    prices.forEach((v, i) => {
      i === 0 ? ctx.moveTo(xOf(i, prices.length), yOf(v))
              : ctx.lineTo(xOf(i, prices.length), yOf(v));
    });
    ctx.stroke();

    /* Endpoint dot */
    const lx = xOf(prices.length - 1, prices.length);
    const ly = yOf(prices[prices.length - 1]);
    ctx.beginPath();
    ctx.arc(lx, ly, 2.5, 0, Math.PI * 2);
    ctx.fillStyle = '#E03131';
    ctx.fill();
  }

  /* Stock mini chart data — provided by agent via window.MARKET_DATA.stockCharts */
  const stockMiniData = {};
  if (window.MARKET_DATA && Array.isArray(window.MARKET_DATA.stockCharts)) {
    window.MARKET_DATA.stockCharts.forEach(d => {
      if (d.id) stockMiniData[d.id] = { prices: d.prices || [], ma20: d.ma20 || [], ma200: d.ma200 || [] };
    });
  }

  window.addEventListener('load', () => {
    renderAll();
    setFearGreed(fgVal);
    /* Update FG history from data */
    const fgData = (window.MARKET_DATA && window.MARKET_DATA.fearGreed) || {};
    ['prev','1w','1m','1y'].forEach((k, i) => {
      const el = document.getElementById('fg-hist-' + k);
      if (el && fgData[k] !== undefined) {
        el.textContent = fgData[k];
        el.style.color = fgData[k] >= 50 ? '#E03131' : '#2563EB';
      }
    });
    Object.entries(marketData).forEach(([key, d]) => attachSparkTooltip(d.canvasId, key));
    // rAF ensures layout is complete so canvas.offsetWidth is accurate on mobile
    requestAnimationFrame(() => {
      Object.entries(stockMiniData).forEach(([id, d]) => drawStockMiniChart(id, d.prices, d.ma20, d.ma200));
    });
  });
  window.addEventListener('resize', () => {
    renderAll();
    Object.entries(stockMiniData).forEach(([id, d]) => drawStockMiniChart(id, d.prices, d.ma20, d.ma200));
  });

  function openKelloggModal() {
    document.getElementById('kellogg-modal').classList.add('is-open');
  }
  function closeKelloggModal() {
    document.getElementById('kellogg-modal').classList.remove('is-open');
  }
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeKelloggModal(); });