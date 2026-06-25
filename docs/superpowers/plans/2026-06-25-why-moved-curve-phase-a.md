# 왜 움직였나 — Phase A: 실데이터 장중 곡선 인프라 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 코스피 주도주 카드와 종목 상세 페이지에 실측 1분봉 장중 곡선을 붙이고, 홈의 미 벨웨더·외국인 보유율 행은 상세 페이지로 이전한다. (뉴스 핀은 Phase B)

**Architecture:** 신규 외부 의존성 0. `api/intraday.mjs`에 종목 코드 분기를 추가해 네이버 fchart 1분봉을 종목별로 제공하고, 프론트(허브 `index.html` + 상세 `stocks.js`)가 이를 받아 곡선을 그린다. 허브는 기존 stocks-live 폴링에 라이브 점을 누적한다. 벨웨더·외국인 데이터는 이미 스냅샷에 있으므로 상세 템플릿 컨텍스트에 추가만 한다.

**Tech Stack:** Vercel serverless(mjs), 네이버 fchart, Jinja2(`generate_html.py`), Vanilla JS(SVG), pytest.

**전제:** 현재 `web/stocks/index.html`에는 Phase 0 프로토타입 목업(`#why-moved` + mock `DATA`)이 들어있다. Task 2가 이 목업을 실데이터 배선으로 **교체**한다. 목업 데이터는 남기지 않는다.

**정합성 규칙(운영규칙 0번):** 곡선·등락은 모두 실측(fchart 1분봉, stocks-live). 추정·하드코딩 금지. 데이터 없으면 섹션 숨김.

---

## File Structure

| 파일 | 책임 | 작업 |
| --- | --- | --- |
| `api/intraday.mjs` | 지수·종목 1분봉 프록시 | 수정 — `?code=` 분기 추가 |
| `web/stocks/index.html` | 허브. 주도주 카드 | 수정 — 목업→실곡선 배선, 벨웨더 행 제거 |
| `scripts/generate_html.py` | 상세 페이지 렌더(`build_stock_page`) | 수정 — 벨웨더·외국인 컨텍스트 주입 |
| `scripts/templates/stocks/detail.html` | 상세 템플릿 | 수정 — 장중 곡선 카드 + 벨웨더/외국인 블록 |
| `web/assets/stocks.js` | 상세 페이지 클라이언트 JS | 수정 — 장중 곡선 렌더러 |
| `scripts/test_build_stocks_snapshot.py` | 스냅샷 테스트 | 수정 — 벨웨더 컨텍스트 헬퍼 테스트 |

---

## Task 1: `intraday.mjs` 종목 1분봉 분기

**Files:**
- Modify: `api/intraday.mjs:31-45` (handler)

- [ ] **Step 1: handler 상단에 code 분기 추가**

`export default async function handler(req, res) {` 본문 시작 직후, 기존 `const [kosdaq...]` 위에 삽입:

```js
  res.setHeader('Cache-Control', 's-maxage=30, stale-while-revalidate=60');
  res.setHeader('Access-Control-Allow-Origin', '*');

  const code = (req.query && req.query.code) ? String(req.query.code).replace(/[^0-9A-Za-z]/g, '') : '';
  if (code) {
    try {
      const minutes = await fetchMinutes(code);
      return res.status(200).json({ code, minutes });
    } catch (e) {
      return res.status(502).json({ code, minutes: [], error: String(e) });
    }
  }
```

기존 지수 응답부의 중복 `setHeader` 두 줄은 삭제(위로 이동했으므로).

- [ ] **Step 2: 로컬 dev 서버에서 검증**

Run: `curl -s 'http://localhost:3000/api/intraday?code=005930' | head -c 300`
Expected: `{"code":"005930","minutes":[숫자,숫자,...]}` 형태. `minutes` 배열 길이 ≥ 1.
(fchart는 네이버 도메인이라 사내 프록시 영향 없음 — 로컬에서 동작.)

- [ ] **Step 3: 지수 응답 회귀 확인**

Run: `curl -s 'http://localhost:3000/api/intraday' | head -c 120`
Expected: `{"kosdaq":[...],"kospi200":[...],"forex":[...]}` 여전히 정상.

- [ ] **Step 4: Commit**

```bash
git add api/intraday.mjs
git commit -m "feat: intraday API에 종목 1분봉 분기(?code=) 추가"
```

---

## Task 2: 허브 주도주 카드 — 목업 제거, 실곡선 배선

**Files:**
- Modify: `web/stocks/index.html` (Phase 0 프로토타입 `#why-moved` 블록 + 스크립트)

- [ ] **Step 1: 목업 `DATA` 객체와 render의 mock 분기 제거, 실 fetch로 교체**

`<script>(function(){ var X0=14... var DATA={...}; ...})();</script>` 블록 전체를 아래로 교체. 곡선 좌표는 `/api/intraday?code=`의 `minutes`(종가 배열)를 viewBox(0~640 × 0~180)로 정규화해 그린다.

```html
    <script>
    (function(){
      var X0=14,X1=626,YT=22,YB=150;
      var buf={};            // code -> [values] (백필 + 라이브 누적)
      var curCode='005930';

      function pathFrom(vals){
        if(!vals || vals.length<2) return null;
        var lo=Math.min.apply(null,vals), hi=Math.max.apply(null,vals);
        var span=(hi-lo)||1, n=vals.length;
        return vals.map(function(v,i){
          var x=X0+(X1-X0)*(i/(n-1));
          var y=YB-(YB-YT)*((v-lo)/span);
          return x.toFixed(1)+','+y.toFixed(1);
        }).join(' ');
      }
      function draw(code){
        var vals=buf[code]||[], svg=document.getElementById('wm-svg');
        if(!svg) return;
        var nm=document.getElementById('wm-name');
        var meta=document.querySelector('#why-moved [data-code="'+code+'"]');
        if(nm && meta) nm.textContent=meta.getAttribute('data-name')||'';
        var pts=pathFrom(vals);
        if(!pts){ document.getElementById('why-moved').style.display='none'; return; }
        document.getElementById('why-moved').style.display='';
        var up = vals[vals.length-1] >= vals[0];
        var col = up ? '#E03131' : '#2775ED';
        var last=pts.split(' ').pop().split(',');
        svg.innerHTML =
          '<line x1="14" y1="150" x2="626" y2="150" stroke="#E5E7EB" stroke-width="1"/>'+
          '<polyline points="'+pts+'" fill="none" stroke="'+col+'" stroke-width="2" stroke-linejoin="round"/>'+
          '<circle cx="'+last[0]+'" cy="'+last[1]+'" r="3.5" fill="'+col+'"/>'+
          '<text x="14" y="170" font-size="10" fill="#9CA3AF">09:00</text>'+
          '<text x="595" y="170" font-size="10" fill="#9CA3AF">15:30</text>';
      }
      function backfill(code){
        fetch('/api/intraday?code='+code).then(function(r){return r.json();}).then(function(d){
          if(d && d.minutes && d.minutes.length){ buf[code]=d.minutes.slice(); draw(code); }
          else { if(code===curCode) document.getElementById('why-moved').style.display='none'; }
        }).catch(function(){ if(code===curCode) document.getElementById('why-moved').style.display='none'; });
      }
      // 라이브 누적: stocks-live 폴링이 종목 가격을 받을 때 호출 (Step 3에서 연결)
      window.whyMovedPush=function(code, price){
        if(typeof price!=='number' || !isFinite(price)) return;
        if(!buf[code]) buf[code]=[];
        var b=buf[code];
        if(!b.length || b[b.length-1]!==price){ b.push(price); if(b.length>120) b.shift(); }
        if(code===curCode) draw(code);
      };
      window.whyMovedRender=function(code){ curCode=code; if(buf[code]) draw(code); else backfill(code); };

      // 주도주 카드 안으로 합치기 + 벨웨더(.us-detail) 제거
      var card=document.getElementById('us-linked-widget');
      var tiles=card && card.querySelector('.usw-tiles');
      var wm=document.getElementById('why-moved');
      if(card && tiles && wm){
        card.querySelectorAll('.us-detail').forEach(function(d){d.remove();});
        wm.style.cssText='background:none;border:none;box-shadow:none;padding:0;margin:13px 0 0;';
        tiles.insertAdjacentElement('afterend', wm);
      }
      backfill(curCode);
    })();
    </script>
```

- [ ] **Step 2: `#why-moved` 마크업에서 목업 잔재 정리 + 종목 메타 추가**

`#why-moved` 마크업을 아래로 교체(타임라인/뉴스/목업뱃지 제거, 제목 "오늘 장중", 종목 메타 data 노드 추가):

```html
    <div id="why-moved">
      <div class="wm-h">
        <span style="font-size:15px;font-weight:800;color:#0F172A;">📈 <span id="wm-name">삼성전자</span> 오늘 장중</span>
        <span style="font-size:11px;font-weight:700;color:#E03131;background:#FEF2F2;border-radius:999px;padding:2px 8px;margin-left:8px;">● 실측 1분봉</span>
      </div>
      <svg id="wm-svg" viewBox="0 0 640 180" role="img" aria-label="장중 1분봉 곡선"></svg>
      <span data-code="005930" data-name="삼성전자" style="display:none"></span>
      <span data-code="000660" data-name="SK하이닉스" style="display:none"></span>
      <span data-code="005380" data-name="현대차" style="display:none"></span>
    </div>
```

`#why-moved .wm-evt`, `.wm-num`, `.wm-badge`, `.wm-src` CSS 규칙은 Phase B에서 다시 쓰므로 삭제하지 말고 둔다.

- [ ] **Step 3: 타일 선택·라이브 폴링에 곡선 연결**

`usSel` 인라인 스크립트(주도주 위젯 끝 `<script>function usSel(code){...}`)는 이미 `if(window.whyMovedRender)whyMovedRender(code);`를 호출한다 — 확인만.
이어서 stocks-live 폴링 IIFE(주석 `미국 연동 대표주 — 실측 스냅샷 baseline + 라이브 폴링(stocks-live)`)에서 종목별 라이브 가격을 반영하는 지점을 찾아, 가격 적용 직후 한 줄 추가:

```js
        if(window.whyMovedPush) window.whyMovedPush(code, price);
```

(해당 폴링이 `code`와 `price`를 다루는 루프 내부. 변수명이 다르면 그 스코프의 코드·가격 변수로 맞춘다.)

- [ ] **Step 4: 프리뷰 검증**

`/stocks/` 로드 → 주도주 카드 안에 삼성전자 곡선이 실측 1분봉으로 그려지는지, 타일(SK하이닉스/현대차) 클릭 시 곡선이 스왑되는지, 벨웨더·외국인 행이 사라졌는지 확인. 콘솔 에러 0.
검증: preview_eval로 `document.querySelectorAll('#wm-svg polyline').length === 1` 및 `document.querySelectorAll('#us-linked-widget .us-detail').length === 0`.

- [ ] **Step 5: 데이터 없음/휴장일 방어 확인**

preview_eval로 `whyMovedRender('999999')` 호출 → `#why-moved`가 `display:none`으로 숨고 콘솔 에러 없음.

- [ ] **Step 6: Commit**

```bash
git add web/stocks/index.html
git commit -m "feat: 주도주 카드 장중 실곡선 배선 — 목업 제거, 벨웨더 행 상세로 이전"
```

---

## Task 3: 상세 페이지 — 벨웨더·외국인 보유율 컨텍스트 주입

**Files:**
- Modify: `scripts/generate_html.py:909-928` (`build_stock_page`)
- Test: `scripts/test_build_stocks_snapshot.py`

- [ ] **Step 1: 벨웨더 추출 헬퍼 테스트 작성**

`scripts/test_build_stocks_snapshot.py`에 추가:

```python
def test_sector_bellwether_for_stock():
    from scripts.generate_html import sector_bellwether
    snapshot = {"bellwethers": {"NVDA": {"name": "엔비디아", "change_pct": 1.9}}}
    sectors = {"semicon": {"bellwethers": [{"t": "NVDA"}]}}
    # 종목 섹터키 semicon → 그 섹터의 첫 벨웨더 NVDA 반환
    bw = sector_bellwether(snapshot, sectors, "semicon")
    assert bw["t"] == "NVDA"
    assert bw["change_pct"] == 1.9
    # 없는 섹터 → None
    assert sector_bellwether(snapshot, sectors, "nonexist") is None
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest scripts/test_build_stocks_snapshot.py::test_sector_bellwether_for_stock -v`
Expected: FAIL — `ImportError: cannot import name 'sector_bellwether'`.

- [ ] **Step 3: `sector_bellwether` 구현**

`scripts/generate_html.py`의 `build_stock_page` 위에 추가:

```python
def sector_bellwether(snapshot: dict, sectors: dict, sector_key: str):
    """종목 섹터의 첫 미국 벨웨더 dict(t·name·change_pct) 반환. 없으면 None."""
    sec = (sectors or {}).get(sector_key) or {}
    bells = sec.get("bellwethers") or []
    if not bells:
        return None
    t = bells[0].get("t")
    info = (snapshot.get("bellwethers") or {}).get(t)
    if not info:
        return None
    return {"t": t, "name": info.get("name"), "change_pct": info.get("change_pct")}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest scripts/test_build_stocks_snapshot.py::test_sector_bellwether_for_stock -v`
Expected: PASS.

- [ ] **Step 5: `build_stock_page` 컨텍스트에 벨웨더·외국인 주입**

`build_stock_page`에서 스냅샷 로드(없으면 빈 dict) 후 템플릿 컨텍스트에 추가. `rd`에는 이미 `foreign_rate`/`foreign_spark`가 있으면 사용. 렌더 컨텍스트 dict에 다음 키 추가:

```python
        "bellwether": sector_bellwether(_load_stock_snapshot(), _load_sectors(), stock.get("sector_key")),
        "foreign_rate": rd.get("foreign_rate"),
        "foreign_spark": rd.get("foreign_spark"),
```

`_load_stock_snapshot()`/`_load_sectors()`가 없으면 `web/data/stock-snapshot.json`·`stock_universe.json`을 읽는 작은 캐시 헬퍼를 같은 파일에 추가(파일 없으면 `{}` 반환).

- [ ] **Step 6: Commit**

```bash
git add scripts/generate_html.py scripts/test_build_stocks_snapshot.py
git commit -m "feat: 상세 페이지 컨텍스트에 미 벨웨더·외국인 보유율 주입"
```

---

## Task 4: 상세 템플릿 — 장중 곡선 카드 + 벨웨더/외국인 블록

**Files:**
- Modify: `scripts/templates/stocks/detail.html:58-78` (헤더 spark 직후)
- Modify: `web/assets/stocks.js` (장중 곡선 렌더러)

- [ ] **Step 1: 헤더 카드 아래에 "오늘 장중" + 벨웨더/외국인 블록 추가**

`detail.html`의 `<div class="spark-header" ...></div>` 닫힘 직후, `{% if chips_ticker %}` 위에 삽입:

```html
      <!-- 오늘 장중 (실측 1분봉) — 장중/장후 거래일에만 JS가 채움 -->
      <div class="sc" id="intra-card" data-code="{{ stock.code }}" style="display:none">
        <div class="sc__h"><span class="sc__t">오늘 장중</span><span class="sc__s">실측 1분봉</span></div>
        <div class="scb" style="padding:8px 12px;">
          <svg id="intra-svg" viewBox="0 0 640 180" style="width:100%;height:160px;display:block;overflow:visible;" role="img" aria-label="장중 1분봉 곡선"></svg>
        </div>
      </div>

      {% if bellwether or foreign_rate is not none %}
      <div class="sc"><div class="sc__h"><span class="sc__t">해외 연동 · 외국인 보유율</span><span class="sc__s">참고용</span></div><div class="scb">
        {% if bellwether %}
        <div class="ti-row"><span class="ti-lbl">미 벨웨더 {{ bellwether.name }}</span>
          <span class="ti-desc"><b class="num {{ 'up' if (bellwether.change_pct or 0) >= 0 else 'dn' }}">{{ '+' if (bellwether.change_pct or 0) >= 0 else '' }}{{ "%.1f"|format(bellwether.change_pct or 0) }}%</b> 밤사이</span>
        </div>
        {% endif %}
        {% if foreign_rate is not none %}
        <div class="ti-row" style="border-bottom:none"><span class="ti-lbl">외국인 보유율</span>
          <span class="ti-desc"><b class="num">{{ "%.2f"|format(foreign_rate) }}%</b></span>
        </div>
        {% endif %}
      </div></div>
      {% endif %}
```

- [ ] **Step 2: `stocks.js`에 장중 곡선 렌더러 추가**

`web/assets/stocks.js` 끝에 추가(DOMContentLoaded 내 또는 IIFE):

```js
(function(){
  var card=document.getElementById('intra-card');
  if(!card) return;
  var code=card.getAttribute('data-code');
  fetch('/api/intraday?code='+code).then(function(r){return r.json();}).then(function(d){
    var vals=(d&&d.minutes)||[];
    if(vals.length<2) return;            // 데이터 없으면 숨김 유지(정합성)
    var X0=14,X1=626,YT=22,YB=150;
    var lo=Math.min.apply(null,vals),hi=Math.max.apply(null,vals),span=(hi-lo)||1,n=vals.length;
    var pts=vals.map(function(v,i){var x=X0+(X1-X0)*(i/(n-1));var y=YB-(YB-YT)*((v-lo)/span);return x.toFixed(1)+','+y.toFixed(1);}).join(' ');
    var up=vals[n-1]>=vals[0], col=up?'#E03131':'#2775ED', last=pts.split(' ').pop().split(',');
    document.getElementById('intra-svg').innerHTML=
      '<line x1="14" y1="150" x2="626" y2="150" stroke="#E5E7EB" stroke-width="1"/>'+
      '<polyline points="'+pts+'" fill="none" stroke="'+col+'" stroke-width="2" stroke-linejoin="round"/>'+
      '<circle cx="'+last[0]+'" cy="'+last[1]+'" r="3.5" fill="'+col+'"/>'+
      '<text x="14" y="170" font-size="10" fill="#9CA3AF">09:00</text><text x="595" y="170" font-size="10" fill="#9CA3AF">15:30</text>';
    card.style.display='';
  }).catch(function(){});
})();
```

- [ ] **Step 3: 한 종목 렌더 후 검증**

Run: `python3 scripts/generate_html.py --stock 005930` (또는 전체 종목 렌더 진입점) 으로 `web/stocks/005930/index.html` 재생성.
Run: `grep -c 'intra-card' web/stocks/005930/index.html`
Expected: `1`. 벨웨더/외국인 블록 존재: `grep -c '외국인 보유율' web/stocks/005930/index.html` → `1`.
(진입점 플래그가 다르면 `build_stock_page`를 호출하는 기존 렌더 명령을 사용.)

- [ ] **Step 4: 프리뷰 검증**

`/stocks/005930/` 로드 → 헤더 아래 "오늘 장중" 곡선 카드가 실측 1분봉으로 표시, 그 아래 "해외 연동·외국인 보유율" 블록 표시. 휴장일/데이터 없으면 곡선 카드 `display:none` 유지.

- [ ] **Step 5: Commit**

```bash
git add scripts/templates/stocks/detail.html web/assets/stocks.js
git commit -m "feat: 상세 페이지 오늘 장중 곡선 + 벨웨더·외국인 블록"
```

---

## Task 5: 프로토타입 파일 정리

**Files:**
- Delete: `web/preview-stock-intraday.html`, `web/preview-hub-mover-live.html`

- [ ] **Step 1: 프리뷰 목업 파일 제거(설계 레퍼런스 역할 종료)**

```bash
git rm web/preview-stock-intraday.html web/preview-hub-mover-live.html
git commit -m "chore: 왜움직였나 곡선 프로토타입 프리뷰 파일 제거"
```

(스펙 부록의 프로토타입 언급은 문서로 남으므로 정보 손실 없음.)

---

## 검증 기준 (Phase A 완료 정의)

1. `/api/intraday?code=005930`가 실측 1분봉 배열을 반환하고, 지수 응답은 회귀 없음.
2. 허브 주도주 카드에 선택 종목 장중 곡선이 실측으로 그려지고, 타일 클릭 시 스왑된다.
3. 홈의 미 벨웨더·외국인 보유율 행이 제거되고, 종목 상세에 동등 정보가 표시된다.
4. 상세 페이지에 "오늘 장중" 곡선이 실측 1분봉으로 표시된다.
5. 데이터 없음/휴장일/없는 코드에서 곡선이 깨지지 않고 숨김, 콘솔 에러 0.
6. 화면 어디에도 목업·하드코딩 수치 없음(운영규칙 0번).

## Phase B 예고 (별도 계획)

`scripts/fetch_movers_why.py`(RSS+Gemini+`_is_direction_conflict` 패턴 재사용) → `web/data/movers-why-{date}.json` → 곡선 위 뉴스 핀 + "왜/관련/뉴스없음" 타임라인 + 제목 "오늘 장중 · 왜 움직였나" 승격 + GHA(`kospi-news-live.yml` 패턴) 스케줄.
