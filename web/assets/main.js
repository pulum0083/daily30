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
  (function() {
    const saved = localStorage.getItem('theme');
    if (saved === 'light') {
      document.documentElement.classList.remove('dark');
      document.documentElement.classList.add('light');
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
    if (bdgEl) { bdgEl.className = `fg-badge ${m.badge}`; }
  }

  /* ============================================================
     Market data + live simulation
  ============================================================ */
  const marketData = {
    kospi:  { base: 2584.36, chg:  1.24, data:[2540,2548,2556,2560,2555,2562,2570,2575,2578,2584], color:UP_COLOR,   valId:'kospi-val',  badgeId:'kospi-badge',  canvasId:'c-kospi'  },
    kosdaq: { base:  742.18, chg:  0.88, data:[728,730,733,736,734,737,739,741,741,742],            color:UP_COLOR,   valId:'kosdaq-val', badgeId:'kosdaq-badge', canvasId:'c-kosdaq' },
    nasdaq: { base:17925.12, chg:  2.27, data:[17420,17510,17580,17630,17590,17680,17750,17820,17880,17925], color:UP_COLOR, valId:'nasdaq-val', badgeId:'nasdaq-badge', canvasId:'c-nasdaq'},
    nq:     { base:19842.50, chg:  0.41, data:[19680,19710,19740,19760,19750,19780,19800,19820,19835,19843], color:UP_COLOR, valId:'nq-val',    badgeId:'nq-badge',    canvasId:'c-nq'    },
    dji:    { base:40527.48, chg:  1.56, data:[39800,39900,40050,40120,40080,40200,40310,40420,40480,40527], color:UP_COLOR, valId:'dji-val',   badgeId:'dji-badge',   canvasId:'c-dji'   },
    sox:    { base: 4821.36, chg:  2.41, data:[4680,4710,4740,4760,4745,4770,4790,4805,4815,4821],  color:UP_COLOR,   valId:'sox-val',   badgeId:'sox-badge',   canvasId:'c-sox'   },
    oil:    { base:   61.24, chg: -4.21, data:[65.2,64.8,64.3,63.9,63.5,63.1,62.7,62.2,61.7,61.24],color:DOWN_COLOR, valId:'oil-val',   badgeId:'oil-badge',   canvasId:'c-oil'   },
    usd:    { base: 1368.50, chg: -0.21, data:[1374,1373,1372,1371,1371,1370,1370,1369,1369,1368.5],color:DOWN_COLOR, valId:'usd-val',   badgeId:'usd-badge',   canvasId:'c-usd'   },
    dxy:    { base:  102.84, chg: -0.38, data:[103.4,103.3,103.2,103.1,103.1,103.0,103.0,102.9,102.9,102.84],color:DOWN_COLOR,valId:'dxy-val',badgeId:'dxy-badge',canvasId:'c-dxy'},
  };

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

  /* Live simulation — jitter every 5 s */
  let fgVal = 28;
  function simulateLive() {
    Object.entries(marketData).forEach(([, d]) => {
      d.base += (Math.random() - 0.5) * 0.002 * d.base;
      d.chg  += (Math.random() - 0.5) * 0.04;
      d.data.push(d.base);
      d.data.shift();
    });
    fgVal = Math.min(100, Math.max(0, fgVal + (Math.random() - 0.5) * 1.5));
    renderAll();
    setFearGreed(Math.round(fgVal));
  }

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

  const stockMiniData = {
    'mc-skhy': {
      /* MA200 탈환 + MA20 돌파: 주가가 MA200·MA20 모두 위로 돌파 */
      prices:  [179000,179500,180200,180800,181300,181800,182300,182900,184000,185200],
      ma20:    [182800,182900,183000,183050,183100,183100,183100,183100,183100,183100],
      ma200:   [174000,175000,176000,177000,178000,179000,180000,180000,180000,180000]
    },
    'mc-ssec': {
      /* MA20 반등, MA200 하회: 주가가 MA20에서 반등하나 MA200 아래에 있음 */
      prices:  [74400,74000,73600,73200,72950,72820,72800,72900,73150,73400],
      ma20:    [73400,73250,73100,73000,72900,72850,72800,72800,72800,72800],
      ma200:   [78000,77800,77600,77400,77200,77000,77000,77000,77000,77000]
    },
    'mc-posco': {
      /* MA200 탈환 + MA20 돌파: 주가가 MA200·MA20 모두 위로 돌파 */
      prices:  [415000,416500,418000,419200,420100,420600,421800,423500,426000,428000],
      ma20:    [419800,420000,420200,420350,420500,420500,420500,420500,420500,420500],
      ma200:   [409000,410000,411000,412000,413000,414000,414000,414000,414000,414000]
    },
    'mc-kakao': {
      /* MA20 반등, MA200 근접: 주가가 MA20에서 반등하며 MA200에 접근 중 */
      prices:  [43400,43000,42600,42200,41950,41810,41800,41870,42010,42150],
      ma20:    [42400,42250,42100,41980,41880,41820,41800,41800,41800,41800],
      ma200:   [43800,43700,43600,43400,43200,43100,43000,43000,43000,43000]
    },
    /* ── 미국 증시 종목 ── */
    'mc-nvda': {
      /* MA200 탈환 + MA20 돌파: 블랙웰 수요로 MA200($864) 상향 돌파 */
      prices:  [858,860,863,866,870,874,878,882,887,892],
      ma20:    [876,876,875,875,875,874,874,874,874,874],
      ma200:   [848,852,856,860,862,863,864,864,864,864]
    },
    'mc-meta': {
      /* MA200 탈환 + MA20 돌파: AI 광고 수요로 MA200($510) 상향 돌파 */
      prices:  [504,506,509,511,514,516,518,520,522,524],
      ma20:    [516,516,516,516,516,515,515,515,515,515],
      ma200:   [497,500,503,506,508,509,510,510,510,510]
    },
    'mc-msft': {
      /* MA20 반등, MA200 하회: MA20($410) 지지 확인 후 반등 */
      prices:  [420,418,416,413,411,410,410,411,412,413],
      ma20:    [411,410,410,410,410,410,410,410,410,410],
      ma200:   [432,430,429,428,427,427,426,426,426,426]
    },
    'mc-amzn': {
      /* MA20 반등, MA200 하회: MA20($182) 지지 확인 후 반등 */
      prices:  [188,187,185,183,182,182,182,183,184,185],
      ma20:    [182,182,182,182,182,182,182,182,182,182],
      ma200:   [191,190,190,189,189,188,188,188,188,188]
    }
  };

  window.addEventListener('load', () => {
    renderAll();
    setFearGreed(28);
    setInterval(simulateLive, 5000);
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