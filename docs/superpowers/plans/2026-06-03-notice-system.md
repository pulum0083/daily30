# Notice System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** GNB 벨 아이콘 클릭 시 슬라이드 패널로 공지사항을 보여주고, 패널 하단 건의하기 버튼으로 텔레그램에 의견을 전송한다.

**Architecture:** `web/data/notices.json`을 JS가 fetch해 패널을 동적 삽입한다. 읽음 상태는 localStorage(`ds_read_notices`)에 공지 id 배열로 저장한다. 건의하기는 `POST /api/feedback`으로 텍스트를 전송하면 Vercel 함수가 텔레그램 봇으로 포워딩한다.

**Tech Stack:** Vanilla JS (IIFE), CSS variables, Vercel Edge Function (ESM), Telegram Bot API

---

## 파일 변경 목록

| 파일 | 구분 | 역할 |
|------|------|------|
| `web/data/notices.json` | 신규 | 공지 데이터 소스 |
| `api/feedback.mjs` | 신규 | 건의 텍스트 → 텔레그램 전송 |
| `scripts/templates/base.html` | 수정 | GNB에 벨 아이콘 버튼 추가 |
| `web/assets/style.css` | 수정 | 패널·오버레이·카드·모달 CSS |
| `web/assets/main.js` | 수정 | 공지 fetch·패널 토글·읽음 처리·모달 JS |

---

### Task 1: notices.json 생성

**Files:**
- Create: `web/data/notices.json`

- [ ] **Step 1: 파일 생성**

```json
{
  "notices": [
    {
      "id": "2026-06-03-launch",
      "type": "update",
      "date": "2026-06-03",
      "title": "공지사항 기능 추가",
      "body": "서비스 업데이트 내역과 운영 공지를 GNB 벨 아이콘에서 확인할 수 있습니다."
    }
  ]
}
```

- [ ] **Step 2: 커밋**

```bash
git add web/data/notices.json
git commit -m "feat: notices.json 초기 데이터 추가"
```

---

### Task 2: CSS 추가 (style.css)

**Files:**
- Modify: `web/assets/style.css` — GNB 섹션 아래에 블록 추가

- [ ] **Step 1: style.css GNB 섹션 끝(line 62 `.icon-sun,.icon-moon` 아래)에 아래 CSS 추가**

```css
/* ──────────────────────────────────────────────
   공지 패널 & 건의 모달
────────────────────────────────────────────── */
.gnb__notif-btn{width:30px;height:30px;border-radius:var(--r-sm);background:rgba(255,255,255,.08);color:rgba(255,255,255,.6);display:flex;align-items:center;justify-content:center;position:relative;cursor:pointer;border:none;}
.gnb__notif-btn:hover{background:rgba(255,255,255,.16);color:#fff;}
.gnb__notif-btn svg{width:16px;height:16px;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;}
.gnb__notif-dot{position:absolute;top:4px;right:4px;width:7px;height:7px;border-radius:50%;background:#E03131;border:1.5px solid var(--gnb-bg);display:none;}
.gnb__notif-dot.is-visible{display:block;}

.notice-overlay{position:fixed;inset:0;background:rgba(0,0,0,.3);z-index:400;opacity:0;pointer-events:none;transition:opacity .2s;}
.notice-overlay.is-open{opacity:1;pointer-events:auto;}

.notice-panel{position:fixed;top:0;right:0;bottom:0;width:320px;background:var(--canvas);border-left:1px solid var(--hairline);z-index:401;display:flex;flex-direction:column;transform:translateX(100%);transition:transform .22s cubic-bezier(.4,0,.2,1);box-shadow:-4px 0 24px rgba(0,0,0,.12);}
.notice-panel.is-open{transform:translateX(0);}
.notice-panel__header{padding:16px 16px 13px;border-bottom:1px solid var(--hairline);display:flex;align-items:center;justify-content:space-between;flex-shrink:0;}
.notice-panel__title{font-size:15px;font-weight:700;color:var(--ink);}
.notice-panel__close{width:28px;height:28px;border-radius:var(--r-sm);background:var(--surface-soft);border:1px solid var(--hairline);display:flex;align-items:center;justify-content:center;cursor:pointer;color:var(--muted);font-size:13px;}
.notice-panel__body{flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:8px;}
.notice-panel__footer{padding:10px;border-top:1px solid var(--hairline);flex-shrink:0;}
.notice-panel__empty{text-align:center;padding:40px 16px;font-size:13px;color:var(--muted);}

.notice-card{border-radius:10px;border:1px solid var(--hairline);padding:12px 13px;background:var(--canvas);}
.notice-card.is-unread{border-color:#BFDBFE;background:#F0F7FF;position:relative;}
html.dark .notice-card.is-unread{border-color:rgba(59,139,255,.3);background:rgba(59,139,255,.08);}
.notice-card__dot{position:absolute;top:12px;right:12px;width:6px;height:6px;border-radius:50%;background:var(--primary);}
.notice-card__meta{display:flex;align-items:center;gap:6px;margin-bottom:6px;}
.notice-badge{font-size:10px;font-weight:700;padding:2px 6px;border-radius:4px;line-height:1.4;}
.notice-badge--update{background:var(--primary-bg);color:var(--primary);}
.notice-badge--ops{background:var(--gold-bg);color:var(--gold);}
.notice-badge--urgent{background:var(--up-bg);color:var(--up);}
.notice-card__date{font-size:11px;color:var(--muted);margin-left:auto;}
.notice-card__title{font-size:13px;font-weight:700;color:var(--ink);margin-bottom:4px;line-height:1.4;}
.notice-card__body{font-size:12px;color:var(--muted);line-height:1.6;}

.suggest-btn{width:100%;padding:9px;border-radius:8px;border:1.5px solid var(--hairline);background:var(--surface-soft);font-size:13px;font-weight:600;color:var(--muted);display:flex;align-items:center;justify-content:center;gap:7px;cursor:pointer;}
.suggest-btn:hover{border-color:#B0BEC5;background:var(--surface-inset);}
.suggest-btn svg{width:14px;height:14px;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;}

.feedback-modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:500;display:flex;align-items:center;justify-content:center;padding:20px;opacity:0;pointer-events:none;transition:opacity .15s;}
.feedback-modal-overlay.is-open{opacity:1;pointer-events:auto;}
.feedback-modal{background:var(--canvas);border-radius:14px;width:100%;max-width:380px;padding:22px;box-shadow:0 12px 40px rgba(0,0,0,.18);}
.feedback-modal__header{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:6px;}
.feedback-modal__title{font-size:16px;font-weight:700;color:var(--ink);}
.feedback-modal__close{width:26px;height:26px;border-radius:6px;background:var(--surface-soft);border:1px solid var(--hairline);display:flex;align-items:center;justify-content:center;cursor:pointer;color:var(--muted);font-size:13px;flex-shrink:0;}
.feedback-modal__sub{font-size:13px;color:var(--muted);margin-bottom:14px;line-height:1.5;}
.feedback-modal__textarea{width:100%;padding:10px 12px;border-radius:8px;border:1.5px solid var(--hairline);font-size:13px;color:var(--ink);background:var(--canvas);resize:none;height:110px;font-family:inherit;line-height:1.6;margin-bottom:14px;}
.feedback-modal__textarea:focus{outline:none;border-color:var(--primary);}
.feedback-modal__footer{display:flex;justify-content:flex-end;gap:8px;}
.feedback-modal__cancel{padding:8px 16px;border-radius:8px;border:1.5px solid var(--hairline);font-size:13px;font-weight:600;color:var(--muted);background:var(--surface-soft);cursor:pointer;}
.feedback-modal__submit{padding:8px 18px;border-radius:8px;font-size:13px;font-weight:700;color:#fff;background:var(--primary);border:none;cursor:pointer;}
.feedback-modal__submit:disabled{opacity:.5;cursor:default;}
.feedback-modal__success{text-align:center;padding:16px 0 4px;font-size:14px;color:var(--ink);}
.feedback-modal__success-sub{text-align:center;font-size:12px;color:var(--muted);margin-top:4px;}
```

- [ ] **Step 2: 브라우저에서 style.css 직접 로드해 CSS 파싱 오류 없는지 확인**

```bash
# 파일이 UTF-8로 올바르게 저장됐는지 확인
python3 -c "open('web/assets/style.css', encoding='utf-8').read(); print('OK')"
```
Expected: `OK`

- [ ] **Step 3: 커밋**

```bash
git add web/assets/style.css
git commit -m "feat: 공지 패널·모달 CSS 추가"
```

---

### Task 3: GNB 벨 아이콘 추가 (base.html)

**Files:**
- Modify: `scripts/templates/base.html` line 36 — `gnb__theme-toggle` 버튼 바로 뒤에 추가

- [ ] **Step 1: base.html 수정 — `</div><!-- gnb__meta -->` 직전 theme-toggle 다음 줄에 벨 버튼 삽입**

기존:
```html
      <button class="gnb__theme-toggle" onclick="toggleTheme()" aria-label="다크모드 전환">
        ...
      </button>
    </div>
  </div>
</nav>
```

수정 후:
```html
      <button class="gnb__theme-toggle" onclick="toggleTheme()" aria-label="다크모드 전환">
        <svg class="icon-sun" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
        <svg class="icon-moon" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/></svg>
      </button>
      <button class="gnb__notif-btn" id="gnb-notif-btn" onclick="openNoticePanel()" aria-label="공지사항">
        <svg viewBox="0 0 24 24"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
        <span class="gnb__notif-dot" id="gnb-notif-dot"></span>
      </button>
    </div>
  </div>
</nav>
```

- [ ] **Step 2: 커밋**

```bash
git add scripts/templates/base.html
git commit -m "feat: GNB에 공지사항 벨 아이콘 추가"
```

---

### Task 4: 공지 패널 JS (main.js)

**Files:**
- Modify: `web/assets/main.js` — `window.addEventListener('load', ...)` 블록 안에 `initNotices()` 호출 추가, IIFE 내부에 함수들 추가

- [ ] **Step 1: main.js IIFE 내부에 공지 관련 함수 블록 추가 (기존 `/* ── 초기화 ── */` 주석 바로 위에)**

```javascript
  /* ── 공지사항 패널 ── */
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
        '<span class="notice-card__date">' + n.date + '</span></div>' +
        '<div class="notice-card__title">' + n.title + '</div>' +
        '<div class="notice-card__body">' + n.body + '</div>' +
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
        '<span class="notice-panel__title">공지사항</span>' +
        '<button class="notice-panel__close" onclick="closeNoticePanel()">✕</button>' +
      '</div>' +
      '<div class="notice-panel__body" id="notice-panel-body"><p class="notice-panel__empty">불러오는 중...</p></div>' +
      '<div class="notice-panel__footer">' +
        '<button class="suggest-btn" onclick="openFeedbackModal()">' +
          '<svg viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>' +
          '건의하기' +
        '</button>' +
      '</div>';

    document.body.appendChild(overlay);
    document.body.appendChild(panel);
  }

  function openNoticePanel() {
    injectNoticePanel();
    var overlay = document.getElementById('notice-overlay');
    var panel = document.getElementById('notice-panel');
    if (overlay) overlay.classList.add('is-open');
    if (panel) panel.classList.add('is-open');
    // 패널 열리면 모두 읽음 처리
    fetch(NOTICES_URL, { signal: AbortSignal.timeout(5000) })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        var notices = (data && data.notices) || [];
        var body = document.getElementById('notice-panel-body');
        if (body) body.innerHTML = renderNotices(notices);
        // 읽음 저장
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

  function initNotices() {
    fetch(NOTICES_URL, { signal: AbortSignal.timeout(5000) })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        var notices = (data && data.notices) || [];
        var readIds = getReadIds();
        var hasUnread = notices.some(function(n) { return readIds.indexOf(n.id) === -1; });
        var dot = document.getElementById('gnb-notif-dot');
        if (dot && hasUnread) dot.classList.add('is-visible');
      })
      .catch(function() {});
  }
```

- [ ] **Step 2: `window.addEventListener('load', ...)` 블록에 `initNotices()` 호출 추가**

기존 마지막 줄 `patchBriefingNav();` 바로 아래:
```javascript
    patchBriefingNav();
    initNotices();
```

- [ ] **Step 3: 전역 노출 — IIFE 내부 함수를 window에 바인딩 (기존 `toggleTheme`, `togglePreOpen` 등과 동일한 패턴)**

main.js IIFE 맨 아래, `})();` 바로 위에:
```javascript
  window.openNoticePanel = openNoticePanel;
  window.closeNoticePanel = closeNoticePanel;
  window.openFeedbackModal = openFeedbackModal;
```

- [ ] **Step 4: 커밋**

```bash
git add web/assets/main.js
git commit -m "feat: 공지 패널 fetch·렌더·읽음 처리 JS 추가"
```

---

### Task 5: 건의하기 모달 JS (main.js)

**Files:**
- Modify: `web/assets/main.js` — Task 4의 공지 블록 바로 아래에 모달 함수 추가

- [ ] **Step 1: main.js에 피드백 모달 함수 추가 (공지 블록 바로 아래, `/* ── 초기화 ── */` 위)**

```javascript
  /* ── 건의하기 모달 ── */
  function injectFeedbackModal() {
    if (document.getElementById('feedback-modal-overlay')) return;
    var el = document.createElement('div');
    el.className = 'feedback-modal-overlay';
    el.id = 'feedback-modal-overlay';
    el.innerHTML =
      '<div class="feedback-modal">' +
        '<div class="feedback-modal__header">' +
          '<span class="feedback-modal__title">건의하기</span>' +
          '<button class="feedback-modal__close" onclick="closeFeedbackModal()">✕</button>' +
        '</div>' +
        '<p class="feedback-modal__sub">불편한 점, 원하는 기능, 오류 제보를 자유롭게 남겨주세요.</p>' +
        '<textarea class="feedback-modal__textarea" id="feedback-textarea" placeholder="자유롭게 작성해주세요..."></textarea>' +
        '<div class="feedback-modal__footer">' +
          '<button class="feedback-modal__cancel" onclick="closeFeedbackModal()">취소</button>' +
          '<button class="feedback-modal__submit" id="feedback-submit" onclick="submitFeedback()">보내기</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(el);
  }

  function openFeedbackModal() {
    injectFeedbackModal();
    var overlay = document.getElementById('feedback-modal-overlay');
    if (overlay) overlay.classList.add('is-open');
    var ta = document.getElementById('feedback-textarea');
    if (ta) { ta.value = ''; setTimeout(function() { ta.focus(); }, 50); }
    var btn = document.getElementById('feedback-submit');
    if (btn) { btn.disabled = false; btn.textContent = '보내기'; }
  }

  function closeFeedbackModal() {
    var overlay = document.getElementById('feedback-modal-overlay');
    if (overlay) overlay.classList.remove('is-open');
  }

  function submitFeedback() {
    var ta = document.getElementById('feedback-textarea');
    var btn = document.getElementById('feedback-submit');
    var message = ta ? ta.value.trim() : '';
    if (!message) { if (ta) ta.focus(); return; }
    if (btn) { btn.disabled = true; btn.textContent = '전송 중...'; }

    fetch('/api/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: message, page: location.pathname }),
    })
      .then(function(r) {
        if (!r.ok) throw new Error('server error');
        var modal = document.querySelector('.feedback-modal');
        if (modal) {
          modal.innerHTML =
            '<p class="feedback-modal__success">✅ 의견이 전달됐습니다.</p>' +
            '<p class="feedback-modal__success-sub">소중한 의견 감사합니다.</p>';
        }
        setTimeout(closeFeedbackModal, 1800);
      })
      .catch(function() {
        if (btn) { btn.disabled = false; btn.textContent = '다시 시도'; }
      });
  }
```

- [ ] **Step 2: window에 closeFeedbackModal 노출 — Task 4 Step 3 위치에 함께 추가**

```javascript
  window.closeFeedbackModal = closeFeedbackModal;
```

- [ ] **Step 3: 커밋**

```bash
git add web/assets/main.js
git commit -m "feat: 건의하기 모달 JS 추가"
```

---

### Task 6: api/feedback.mjs 생성

**Files:**
- Create: `api/feedback.mjs`

- [ ] **Step 1: 파일 생성**

```javascript
// 건의 텍스트를 텔레그램 관리자 봇으로 전달하는 Vercel 엔드포인트
export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const { message, page } = req.body || {};
  if (!message || !message.trim()) {
    return res.status(400).json({ error: 'message required' });
  }

  const token  = process.env.TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TELEGRAM_CHAT_ID;
  if (!token || !chatId) {
    return res.status(500).json({ error: 'Telegram env vars missing' });
  }

  const kst = new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Seoul' }));
  const ts  = `${kst.getFullYear()}-${String(kst.getMonth()+1).padStart(2,'0')}-${String(kst.getDate()).padStart(2,'0')} ${String(kst.getHours()).padStart(2,'0')}:${String(kst.getMinutes()).padStart(2,'0')} KST`;
  const text = `💬 [건의]\n\n${message.trim()}\n\n📄 ${page || '(페이지 미상)'}\n🕐 ${ts}`;

  const tgRes = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: chatId, text }),
  });

  if (!tgRes.ok) {
    const body = await tgRes.text();
    console.error('[feedback] Telegram error:', body);
    return res.status(500).json({ error: 'Telegram send failed' });
  }

  return res.status(200).json({ ok: true });
}
```

- [ ] **Step 2: 로컬에서 Vercel dev 서버로 엔드포인트 테스트**

```bash
# 별도 터미널에서 vercel dev 실행 후:
curl -X POST http://localhost:3000/api/feedback \
  -H "Content-Type: application/json" \
  -d '{"message":"테스트 건의입니다","page":"/briefings/2026-06-03/kospi/"}'
```
Expected: `{"ok":true}` + 텔레그램에 메시지 수신 확인

- [ ] **Step 3: 커밋**

```bash
git add api/feedback.mjs
git commit -m "feat: 건의 텔레그램 전송 API 추가"
```

---

### Task 7: 생성된 HTML에 반영 + 검증

**Files:**
- Run: `python3 scripts/generate_html.py --write-list-only` (notices.json 추가로 briefings-list 재생성 불필요, HTML 재생성만 필요한 경우)

- [ ] **Step 1: 최신 브리핑 HTML 재생성 (base.html 변경 반영)**

```bash
# 오늘 날짜 코스피 브리핑이 있는 경우 (없으면 가장 최신 날짜로)
python3 scripts/generate_html.py --type kospi --date 2026-06-02 \
  --data-file data/analysis_kospi.json
```
Expected: `web/briefings/2026-06-02/kospi/index.html` 재생성

- [ ] **Step 2: 재생성된 HTML에서 벨 아이콘 존재 확인**

```bash
grep -c "gnb__notif-btn" web/briefings/2026-06-02/kospi/index.html
```
Expected: `1`

- [ ] **Step 3: 브라우저에서 로컬 파일 열어 동작 확인**

```bash
# 로컬 HTTP 서버 실행
python3 -m http.server 8080 --directory web
# http://localhost:8080/briefings/2026-06-02/kospi/ 접속
```

확인 항목:
- GNB 우측에 벨 아이콘 표시
- 벨 클릭 → 패널 슬라이드인 + dim 오버레이
- 공지 카드 렌더링 (미확인 파란 점)
- 패널 닫은 후 재오픈 → 파란 점 사라짐
- 건의하기 클릭 → 모달 오픈
- 텍스트 입력 후 보내기 → "의견이 전달됐습니다" 표시

- [ ] **Step 4: 나머지 날짜 브리핑 HTML 일괄 재생성**

```bash
# 2026-06-02의 close, us도 재생성
python3 scripts/generate_html.py --type kospi-close --date 2026-06-02 \
  --data-file data/analysis_kospi-close.json
python3 scripts/generate_html.py --type us --date 2026-06-02 \
  --data-file data/analysis_us.json
```

- [ ] **Step 5: briefings/index.html 재생성**

```bash
python3 scripts/generate_html.py --write-list-only
```

- [ ] **Step 6: 최종 커밋**

```bash
git add web/briefings/
git commit -m "chore: base.html 변경 반영 — 전 브리핑 HTML 재생성"
```
