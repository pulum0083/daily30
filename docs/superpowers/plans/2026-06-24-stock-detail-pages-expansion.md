# 종목 상세 페이지 41종목 확장 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 종목 상세 페이지를 3개에서 41개로 확장하고, 일러스트레이션 섹션을 제거해 "실측만 보여준다"는 서비스 원칙과 일치시킨다.

**Architecture:** (1) 템플릿에서 하드코딩된 일러스트 섹션을 제거하고 실측 MA 게이지를 추가한다. (2) stocks.json을 stock_universe.json의 41종목 전체로 확장한다. (3) `generate_html.py --stocks`로 38개 신규 페이지를 일괄 생성한다. 데이터 소스는 네이버 일봉 API(기존 파이프라인 그대로).

**Tech Stack:** Jinja2, Python, 네이버 주식 API(기존), generate_html.py --stocks 플래그

---

## 파일 변경 목록

| 파일 | 역할 | 변경 |
|------|------|------|
| `scripts/templates/stocks/detail.html` | 종목 상세 템플릿 | 일러스트 섹션 제거, MA 게이지 추가, 섹터 링크 수정 |
| `scripts/config/stocks.json` | 생성할 종목 목록 | 3개 → 41개 |
| `web/stocks/{code}/index.html` (×38) | 생성물 | --stocks 실행으로 자동 생성 |
| `web/sitemap.xml` | sitemap | --stocks 실행 시 자동 갱신 |

---

## Task 1: 템플릿 정리 — 일러스트 제거 + 실측 MA 추가

**Files:**
- Modify: `scripts/templates/stocks/detail.html`

현재 템플릿의 일러스트레이션 섹션과 수정 대상:

| 위치 | 현재 | 조치 |
|------|------|------|
| line 28 | `<div class="proto-tag">...` | **제거** |
| line 55–61 | 신호 칩(sigrow) + "일러스트레이션" 노트 | **제거** |
| line 66–74 | "오늘 왜 움직였나" 노란 박스 전체 | **제거** |
| line 76–89 | 수급 동향 섹션 전체 | **제거** |
| line 91–98 | 기술적 지표 섹션 전체 | **제거** |
| line 102–107 | 증권사 목표주가 블록 | **제거** |
| line 122–133 | 실적 분기추세 블록 | **제거** |
| line 160–171 | "담은 ETF" 패널(우측 사이드바) | **제거** |
| line 175–183 | 다른 섹터 링크 | `#xxx` → `/stocks/sector/xxx/` **수정** |
| line 187 | footer disclaimer | `(수급·목표가·실적 제외 — 일러스트레이션)` 부분 **제거** |

MA 게이지 (실측, 추가):
- `rd.ma20_dist_pct`: 이미 `_fetch_kospi_realdata`가 계산해서 반환 (`ma20_dist_pct`)
- `rd.ma200_dist_pct`: 동일

- [ ] **Step 1: proto-tag 제거**

`detail.html` line 28 삭제:
```html
<!-- 제거 대상 -->
<div class="proto-tag">프로토타입 · 시세·sparkline·52주는 실측, 수급·목표가·분기실적은 일러스트레이션</div>
```

- [ ] **Step 2: 신호 칩 + "오늘 왜 움직였나" 제거**

lines 55–74 블록 제거. 이 두 블록 전체:
```html
<!-- 제거: 신호 칩 -->
        <div class="sigrow">
          <span class="sigchip hot">🔥 거래량 급증</span>
          <span class="sigchip dn">🔵 외국인 수급 동향</span>
          <span class="sigchip tech">📈 기술적 신호</span>
        </div>
        <p class="refnote" style="margin:4px 0 0;">신호 칩은 일러스트레이션입니다.</p>
```
그리고:
```html
<!-- 제거: 오늘 왜 움직였나 -->
      <div class="sc" style="border-color:#FDE68A;background:#FFFBEB;">...</div>
```

- [ ] **Step 3: 수급 동향 + 기술적 지표 섹션 제거**

```html
<!-- 제거: 수급 동향 -->
      <div class="sc"><div class="sc__h"><span class="sc__t">수급 동향</span>...
<!-- 제거: 기술적 지표 -->
      <div class="sc"><div class="sc__h"><span class="sc__t">기술적 지표</span>...
```

- [ ] **Step 4: MA 게이지 추가 (실측, 수급 동향 자리 대체)**

"수급 동향"이 있던 자리에 실측 MA 게이지 삽입 (`hero2` 카드 바로 아래):

```html
{% if rd.ma20_dist_pct is not none or rd.ma200_dist_pct is not none %}
<div class="sc"><div class="sc__h"><span class="sc__t">이동평균 대비</span><span class="sc__s">{{ generated_label }} 종가 기준</span></div><div class="scb">
  {% if rd.ma20_dist_pct is not none %}
  <div class="ma200-gauge" style="margin-bottom:10px;">
    <div class="ma200-gauge__row">
      <span class="ma200-gauge__label">20일선 대비</span>
      <div class="ma200-gauge__track">
        <div class="ma200-gauge__zero"></div>
        <div class="ma200-gauge__fill {{ 'up' if rd.ma20_dist_pct >= 0 else 'down' }}" style="width:{{ [([rd.ma20_dist_pct | abs, 60] | min) / 60 * 50, 0.5] | max }}%"></div>
      </div>
      <span class="ma200-gauge__pct {{ 'up' if rd.ma20_dist_pct >= 0 else 'down' }}">{{ '+' if rd.ma20_dist_pct >= 0 else '' }}{{ "%.1f"|format(rd.ma20_dist_pct) }}%</span>
    </div>
  </div>
  {% endif %}
  {% if rd.ma200_dist_pct is not none %}
  <div class="ma200-gauge">
    <div class="ma200-gauge__row">
      <span class="ma200-gauge__label">200일선 대비</span>
      <div class="ma200-gauge__track">
        <div class="ma200-gauge__zero"></div>
        <div class="ma200-gauge__fill {{ 'up' if rd.ma200_dist_pct >= 0 else 'down' }}" style="width:{{ [([rd.ma200_dist_pct | abs, 60] | min) / 60 * 50, 0.5] | max }}%"></div>
      </div>
      <span class="ma200-gauge__pct {{ 'up' if rd.ma200_dist_pct >= 0 else 'down' }}">{{ '+' if rd.ma200_dist_pct >= 0 else '' }}{{ "%.1f"|format(rd.ma200_dist_pct) }}%</span>
    </div>
    <div class="ma200-gauge__scale"><span>-60%</span><span>0</span><span>+60%</span></div>
  </div>
  {% endif %}
</div></div>
{% endif %}
```

> 참고: `ma200-gauge`, `ma200-gauge__fill`, `ma200-gauge__zero`, `ma200-gauge__pct` CSS 클래스는 `/assets/style.css`에 이미 정의돼 있음 (브리핑 페이지에서 사용 중).

- [ ] **Step 5: 참고 지표에서 증권사 목표주가 + 실적 분기추세 제거, 52주만 남기기**

```html
<!-- 현재 참고 지표 전체 -->
<div class="sc"><div class="sc__h"><span class="sc__t">참고 지표</span>...
```

→ 아래로 교체 (52주 범위만 남김):

```html
{% if rd.week52_low %}
<div class="sc"><div class="sc__h"><span class="sc__t">52주 범위</span><span class="sc__s">현재가 {{ rd.week52_pos_pct }}% 지점</span></div><div class="scb">
  <div class="w52-bar">
    <div class="w52-fill" style="width:{{ rd.week52_pos_pct }}%"></div>
    <div class="w52-now" style="left:{{ rd.week52_pos_pct }}%"></div>
  </div>
  <div class="w52-lbl"><span>최저 <span class="num">{{ "{:,}".format(rd.week52_low | int) }}</span></span><span>최고 <span class="num">{{ "{:,}".format(rd.week52_high | int) }}</span></span></div>
</div></div>
{% endif %}
```

- [ ] **Step 6: 담은 ETF 패널 제거 (우측 사이드바)**

우측 사이드바에서 lines 160–171 블록 제거:
```html
<!-- 제거 -->
      <div class="panel" style="border-color:#BAE6FD;">
        <div class="panel__h" style="background:#F0F9FF;border-color:#BAE6FD;">
          <span style="color:#0C4A6E;">📦 {{ stock.name }} 담은 ETF</span>
        </div>
        ...
      </div>
```

- [ ] **Step 7: 다른 섹터 링크 수정**

```html
<!-- 수정 전 -->
<a href="/stocks/#power">⚡ 전력기기</a>
<a href="/stocks/#defense">🛡️ 방산</a>
...

<!-- 수정 후 -->
<a href="/stocks/sector/power/">⚡ 전력기기</a>
<a href="/stocks/sector/defense/">🛡️ 방산</a>
<a href="/stocks/sector/ship/">🚢 조선</a>
<a href="/stocks/sector/battery/">🔋 2차전지</a>
<a href="/stocks/sector/auto/">🚗 자동차</a>
<a href="/stocks/sector/bio/">🧬 바이오</a>
<a href="/stocks/sector/finance/">🏦 금융</a>
```

- [ ] **Step 8: footer disclaimer 정리**

```html
<!-- 수정 전 -->
<p class="disc">※ 모든 수치는 직전 거래일 종가 기준 실측값입니다 (수급·목표가·실적 제외 — 일러스트레이션). 투자 판단의 참고용입니다.</p>

<!-- 수정 후 -->
<p class="disc">※ 모든 수치는 직전 거래일 종가 기준 실측값입니다. 투자 판단의 참고용입니다.</p>
```

- [ ] **Step 9: 로컬 확인**

```bash
# 기존 3개 중 하나로 빠르게 재생성 후 브라우저 확인
python3 scripts/generate_html.py --stocks
# web/stocks/005930/index.html 열어서 확인:
# - "프로토타입" 태그 없음
# - "일러스트레이션" 텍스트 없음
# - MA 게이지 표시됨
# - 52주 범위 표시됨
# - "다른 섹터" 링크가 /stocks/sector/xxx/ 형태
```

---

## Task 2: stocks.json 41종목으로 확장

**Files:**
- Modify: `scripts/config/stocks.json`

아래 완전한 JSON으로 교체한다. peer 목록은 각 종목의 같은 섹터 내 다른 종목들.

- [ ] **Step 1: stocks.json 전체 교체**

`scripts/config/stocks.json`을 아래 내용으로 교체:

```json
[
  {"code": "005930", "name": "삼성전자", "sector": "반도체", "sector_key": "semicon", "market": "KOSPI",
   "peers": [{"code": "000660", "name": "SK하이닉스"}, {"code": "042700", "name": "한미반도체"}, {"code": "058470", "name": "리노공업"}, {"code": "000990", "name": "DB하이텍"}]},
  {"code": "000660", "name": "SK하이닉스", "sector": "반도체", "sector_key": "semicon", "market": "KOSPI",
   "peers": [{"code": "005930", "name": "삼성전자"}, {"code": "042700", "name": "한미반도체"}, {"code": "058470", "name": "리노공업"}, {"code": "000990", "name": "DB하이텍"}]},
  {"code": "005380", "name": "현대차", "sector": "자동차", "sector_key": "auto", "market": "KOSPI",
   "peers": [{"code": "000270", "name": "기아"}, {"code": "012330", "name": "현대모비스"}, {"code": "204320", "name": "HL만도"}, {"code": "011210", "name": "현대위아"}]},
  {"code": "042700", "name": "한미반도체", "sector": "반도체", "sector_key": "semicon", "market": "KOSPI",
   "peers": [{"code": "005930", "name": "삼성전자"}, {"code": "000660", "name": "SK하이닉스"}, {"code": "058470", "name": "리노공업"}, {"code": "039030", "name": "이오테크닉스"}]},
  {"code": "058470", "name": "리노공업", "sector": "반도체", "sector_key": "semicon", "market": "KOSDAQ",
   "peers": [{"code": "005930", "name": "삼성전자"}, {"code": "000660", "name": "SK하이닉스"}, {"code": "042700", "name": "한미반도체"}, {"code": "039030", "name": "이오테크닉스"}]},
  {"code": "000990", "name": "DB하이텍", "sector": "반도체", "sector_key": "semicon", "market": "KOSPI",
   "peers": [{"code": "005930", "name": "삼성전자"}, {"code": "042700", "name": "한미반도체"}, {"code": "058470", "name": "리노공업"}, {"code": "039030", "name": "이오테크닉스"}]},
  {"code": "039030", "name": "이오테크닉스", "sector": "반도체", "sector_key": "semicon", "market": "KOSDAQ",
   "peers": [{"code": "000660", "name": "SK하이닉스"}, {"code": "042700", "name": "한미반도체"}, {"code": "058470", "name": "리노공업"}, {"code": "000990", "name": "DB하이텍"}]},
  {"code": "267260", "name": "HD현대일렉트릭", "sector": "전력기기", "sector_key": "power", "market": "KOSPI",
   "peers": [{"code": "010120", "name": "LS일렉트릭"}, {"code": "298040", "name": "효성중공업"}, {"code": "034020", "name": "두산에너빌리티"}, {"code": "033100", "name": "제룡전기"}]},
  {"code": "010120", "name": "LS일렉트릭", "sector": "전력기기", "sector_key": "power", "market": "KOSPI",
   "peers": [{"code": "267260", "name": "HD현대일렉트릭"}, {"code": "298040", "name": "효성중공업"}, {"code": "034020", "name": "두산에너빌리티"}, {"code": "033100", "name": "제룡전기"}]},
  {"code": "298040", "name": "효성중공업", "sector": "전력기기", "sector_key": "power", "market": "KOSPI",
   "peers": [{"code": "267260", "name": "HD현대일렉트릭"}, {"code": "010120", "name": "LS일렉트릭"}, {"code": "034020", "name": "두산에너빌리티"}, {"code": "033100", "name": "제룡전기"}]},
  {"code": "034020", "name": "두산에너빌리티", "sector": "전력기기", "sector_key": "power", "market": "KOSPI",
   "peers": [{"code": "267260", "name": "HD현대일렉트릭"}, {"code": "010120", "name": "LS일렉트릭"}, {"code": "298040", "name": "효성중공업"}, {"code": "033100", "name": "제룡전기"}]},
  {"code": "033100", "name": "제룡전기", "sector": "전력기기", "sector_key": "power", "market": "KOSDAQ",
   "peers": [{"code": "267260", "name": "HD현대일렉트릭"}, {"code": "010120", "name": "LS일렉트릭"}, {"code": "298040", "name": "효성중공업"}, {"code": "034020", "name": "두산에너빌리티"}]},
  {"code": "012450", "name": "한화에어로스페이스", "sector": "방산", "sector_key": "defense", "market": "KOSPI",
   "peers": [{"code": "079550", "name": "LIG넥스원"}, {"code": "064350", "name": "현대로템"}, {"code": "047810", "name": "한국항공우주"}, {"code": "272210", "name": "한화시스템"}]},
  {"code": "079550", "name": "LIG넥스원", "sector": "방산", "sector_key": "defense", "market": "KOSPI",
   "peers": [{"code": "012450", "name": "한화에어로스페이스"}, {"code": "064350", "name": "현대로템"}, {"code": "047810", "name": "한국항공우주"}, {"code": "272210", "name": "한화시스템"}]},
  {"code": "064350", "name": "현대로템", "sector": "방산", "sector_key": "defense", "market": "KOSPI",
   "peers": [{"code": "012450", "name": "한화에어로스페이스"}, {"code": "079550", "name": "LIG넥스원"}, {"code": "047810", "name": "한국항공우주"}, {"code": "272210", "name": "한화시스템"}]},
  {"code": "047810", "name": "한국항공우주", "sector": "방산", "sector_key": "defense", "market": "KOSPI",
   "peers": [{"code": "012450", "name": "한화에어로스페이스"}, {"code": "079550", "name": "LIG넥스원"}, {"code": "064350", "name": "현대로템"}, {"code": "272210", "name": "한화시스템"}]},
  {"code": "272210", "name": "한화시스템", "sector": "방산", "sector_key": "defense", "market": "KOSPI",
   "peers": [{"code": "012450", "name": "한화에어로스페이스"}, {"code": "079550", "name": "LIG넥스원"}, {"code": "064350", "name": "현대로템"}, {"code": "047810", "name": "한국항공우주"}]},
  {"code": "329180", "name": "HD현대중공업", "sector": "조선", "sector_key": "ship", "market": "KOSPI",
   "peers": [{"code": "042660", "name": "한화오션"}, {"code": "010140", "name": "삼성중공업"}, {"code": "009540", "name": "HD한국조선해양"}, {"code": "010620", "name": "HD현대미포"}]},
  {"code": "042660", "name": "한화오션", "sector": "조선", "sector_key": "ship", "market": "KOSPI",
   "peers": [{"code": "329180", "name": "HD현대중공업"}, {"code": "010140", "name": "삼성중공업"}, {"code": "009540", "name": "HD한국조선해양"}, {"code": "010620", "name": "HD현대미포"}]},
  {"code": "010140", "name": "삼성중공업", "sector": "조선", "sector_key": "ship", "market": "KOSPI",
   "peers": [{"code": "329180", "name": "HD현대중공업"}, {"code": "042660", "name": "한화오션"}, {"code": "009540", "name": "HD한국조선해양"}, {"code": "010620", "name": "HD현대미포"}]},
  {"code": "009540", "name": "HD한국조선해양", "sector": "조선", "sector_key": "ship", "market": "KOSPI",
   "peers": [{"code": "329180", "name": "HD현대중공업"}, {"code": "042660", "name": "한화오션"}, {"code": "010140", "name": "삼성중공업"}, {"code": "010620", "name": "HD현대미포"}]},
  {"code": "010620", "name": "HD현대미포", "sector": "조선", "sector_key": "ship", "market": "KOSPI",
   "peers": [{"code": "329180", "name": "HD현대중공업"}, {"code": "042660", "name": "한화오션"}, {"code": "010140", "name": "삼성중공업"}, {"code": "009540", "name": "HD한국조선해양"}]},
  {"code": "373220", "name": "LG에너지솔루션", "sector": "2차전지", "sector_key": "battery", "market": "KOSPI",
   "peers": [{"code": "247540", "name": "에코프로비엠"}, {"code": "006400", "name": "삼성SDI"}, {"code": "003670", "name": "포스코퓨처엠"}, {"code": "066970", "name": "엘앤에프"}]},
  {"code": "247540", "name": "에코프로비엠", "sector": "2차전지", "sector_key": "battery", "market": "KOSDAQ",
   "peers": [{"code": "373220", "name": "LG에너지솔루션"}, {"code": "006400", "name": "삼성SDI"}, {"code": "003670", "name": "포스코퓨처엠"}, {"code": "066970", "name": "엘앤에프"}]},
  {"code": "006400", "name": "삼성SDI", "sector": "2차전지", "sector_key": "battery", "market": "KOSPI",
   "peers": [{"code": "373220", "name": "LG에너지솔루션"}, {"code": "247540", "name": "에코프로비엠"}, {"code": "003670", "name": "포스코퓨처엠"}, {"code": "066970", "name": "엘앤에프"}]},
  {"code": "003670", "name": "포스코퓨처엠", "sector": "2차전지", "sector_key": "battery", "market": "KOSPI",
   "peers": [{"code": "373220", "name": "LG에너지솔루션"}, {"code": "247540", "name": "에코프로비엠"}, {"code": "006400", "name": "삼성SDI"}, {"code": "066970", "name": "엘앤에프"}]},
  {"code": "066970", "name": "엘앤에프", "sector": "2차전지", "sector_key": "battery", "market": "KOSDAQ",
   "peers": [{"code": "373220", "name": "LG에너지솔루션"}, {"code": "247540", "name": "에코프로비엠"}, {"code": "006400", "name": "삼성SDI"}, {"code": "003670", "name": "포스코퓨처엠"}]},
  {"code": "000270", "name": "기아", "sector": "자동차", "sector_key": "auto", "market": "KOSPI",
   "peers": [{"code": "005380", "name": "현대차"}, {"code": "012330", "name": "현대모비스"}, {"code": "204320", "name": "HL만도"}, {"code": "011210", "name": "현대위아"}]},
  {"code": "012330", "name": "현대모비스", "sector": "자동차", "sector_key": "auto", "market": "KOSPI",
   "peers": [{"code": "005380", "name": "현대차"}, {"code": "000270", "name": "기아"}, {"code": "204320", "name": "HL만도"}, {"code": "011210", "name": "현대위아"}]},
  {"code": "204320", "name": "HL만도", "sector": "자동차", "sector_key": "auto", "market": "KOSPI",
   "peers": [{"code": "005380", "name": "현대차"}, {"code": "000270", "name": "기아"}, {"code": "012330", "name": "현대모비스"}, {"code": "011210", "name": "현대위아"}]},
  {"code": "011210", "name": "현대위아", "sector": "자동차", "sector_key": "auto", "market": "KOSPI",
   "peers": [{"code": "005380", "name": "현대차"}, {"code": "000270", "name": "기아"}, {"code": "012330", "name": "현대모비스"}, {"code": "204320", "name": "HL만도"}]},
  {"code": "207940", "name": "삼성바이오로직스", "sector": "바이오", "sector_key": "bio", "market": "KOSPI",
   "peers": [{"code": "068270", "name": "셀트리온"}, {"code": "000100", "name": "유한양행"}, {"code": "326030", "name": "SK바이오팜"}, {"code": "196170", "name": "알테오젠"}]},
  {"code": "068270", "name": "셀트리온", "sector": "바이오", "sector_key": "bio", "market": "KOSPI",
   "peers": [{"code": "207940", "name": "삼성바이오로직스"}, {"code": "000100", "name": "유한양행"}, {"code": "326030", "name": "SK바이오팜"}, {"code": "196170", "name": "알테오젠"}]},
  {"code": "000100", "name": "유한양행", "sector": "바이오", "sector_key": "bio", "market": "KOSPI",
   "peers": [{"code": "207940", "name": "삼성바이오로직스"}, {"code": "068270", "name": "셀트리온"}, {"code": "326030", "name": "SK바이오팜"}, {"code": "196170", "name": "알테오젠"}]},
  {"code": "326030", "name": "SK바이오팜", "sector": "바이오", "sector_key": "bio", "market": "KOSPI",
   "peers": [{"code": "207940", "name": "삼성바이오로직스"}, {"code": "068270", "name": "셀트리온"}, {"code": "000100", "name": "유한양행"}, {"code": "196170", "name": "알테오젠"}]},
  {"code": "196170", "name": "알테오젠", "sector": "바이오", "sector_key": "bio", "market": "KOSDAQ",
   "peers": [{"code": "207940", "name": "삼성바이오로직스"}, {"code": "068270", "name": "셀트리온"}, {"code": "000100", "name": "유한양행"}, {"code": "326030", "name": "SK바이오팜"}]},
  {"code": "105560", "name": "KB금융", "sector": "금융", "sector_key": "finance", "market": "KOSPI",
   "peers": [{"code": "055550", "name": "신한지주"}, {"code": "138040", "name": "메리츠금융지주"}, {"code": "086790", "name": "하나금융지주"}, {"code": "316140", "name": "우리금융지주"}]},
  {"code": "055550", "name": "신한지주", "sector": "금융", "sector_key": "finance", "market": "KOSPI",
   "peers": [{"code": "105560", "name": "KB금융"}, {"code": "138040", "name": "메리츠금융지주"}, {"code": "086790", "name": "하나금융지주"}, {"code": "316140", "name": "우리금융지주"}]},
  {"code": "138040", "name": "메리츠금융지주", "sector": "금융", "sector_key": "finance", "market": "KOSPI",
   "peers": [{"code": "105560", "name": "KB금융"}, {"code": "055550", "name": "신한지주"}, {"code": "086790", "name": "하나금융지주"}, {"code": "316140", "name": "우리금융지주"}]},
  {"code": "086790", "name": "하나금융지주", "sector": "금융", "sector_key": "finance", "market": "KOSPI",
   "peers": [{"code": "105560", "name": "KB금융"}, {"code": "055550", "name": "신한지주"}, {"code": "138040", "name": "메리츠금융지주"}, {"code": "316140", "name": "우리금융지주"}]},
  {"code": "316140", "name": "우리금융지주", "sector": "금융", "sector_key": "finance", "market": "KOSPI",
   "peers": [{"code": "105560", "name": "KB금융"}, {"code": "055550", "name": "신한지주"}, {"code": "138040", "name": "메리츠금융지주"}, {"code": "086790", "name": "하나금융지주"}]}
]
```

> **주의**: `stock_universe.json`에서 종목 코드를 확인했으나, 시장 구분(KOSPI/KOSDAQ)은 위 JSON을 기준으로 사용. 리노공업(058470), 이오테크닉스(039030), 에코프로비엠(247540), 엘앤에프(066970), 알테오젠(196170), 제룡전기(033100)는 KOSDAQ.

- [ ] **Step 2: JSON 유효성 확인**

```bash
python3 -c "import json; d=json.load(open('scripts/config/stocks.json')); print(len(d), '종목')"
# Expected: 41 종목
```

---

## Task 3: 페이지 생성 + 검증

**Files:**
- Generate: `web/stocks/{code}/index.html` (×38 신규)
- Regenerate: `web/sitemap.xml`

- [ ] **Step 1: 종목 상세 페이지 일괄 생성**

```bash
python3 scripts/generate_html.py --stocks
# 각 종목마다 "stocks/{code}/index.html" 출력
# 네이버 API 호출 38회 추가 — 약 2~3분 소요
# 에러 발생 시: "XXXX 실측 실패" 메시지 → 해당 종목 code 확인
```

- [ ] **Step 2: 생성 결과 확인**

```bash
find web/stocks -name "index.html" | grep -v "income-designer\|sector\|index.html$" | wc -l
# Expected: 41 (기존 3 + 신규 38)
```

- [ ] **Step 3: 생성된 페이지 실측 여부 확인**

```bash
# 일러스트레이션 텍스트가 남아 있으면 안 됨
grep -r "일러스트레이션\|프로토타입" web/stocks/*/index.html | grep -v "sector\|income"
# Expected: 출력 없음 (모두 제거됐어야 함)
```

- [ ] **Step 4: MA 게이지 포함 여부 확인**

```bash
grep -l "ma200-gauge" web/stocks/*/index.html | wc -l
# Expected: 41 (전 종목에 게이지 포함)
```

- [ ] **Step 5: sitemap URL 수 확인**

```bash
grep -c "<loc>" web/sitemap.xml
# Expected: 이전(41)보다 38 증가 = 79 내외
```

- [ ] **Step 6: 브라우저 검증 (2개 샘플)**

프리뷰 서버에서:
- `/stocks/012450/` (한화에어로스페이스, 방산): MA 게이지 + 52주 범위 + 피어 4종목
- `/stocks/196170/` (알테오젠, 바이오): KOSDAQ 종목, 피어 4종목

체크 항목:
- "프로토타입", "일러스트레이션" 텍스트 없음
- MA20/MA200 게이지 렌더링됨 (수치 있음)
- 섹터 칩 클릭 시 `/stocks/sector/{key}/`로 이동
- "다른 섹터" 링크가 `/stocks/sector/xxx/` 형태

---

## Task 4: 커밋

- [ ] **Step 1: 변경 파일 스테이징**

```bash
git add scripts/templates/stocks/detail.html
git add scripts/config/stocks.json
git add web/stocks/
git add web/sitemap.xml
```

- [ ] **Step 2: 커밋**

```bash
git commit -m "$(cat <<'EOF'
feat(종목): 상세 페이지 41종목으로 확장 + 일러스트 제거

- stocks.json 3개 → 41개 (8섹터 전체 유니버스)
- detail.html: 수급·기술지표·목표가·실적·담은ETF 일러스트 섹션 제거
- detail.html: MA20·MA200 실측 게이지 추가 (rd.ma20_dist_pct)
- detail.html: 다른 섹터 링크 /stocks/#xxx → /stocks/sector/xxx/ 수정
- sitemap.xml 갱신 (38 URL 추가)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

**Spec 커버리지 체크:**
- [x] 일러스트 섹션 제거 → Task 1 Steps 1–6
- [x] MA 게이지(실측) 추가 → Task 1 Step 4
- [x] 다른 섹터 링크 수정 → Task 1 Step 7
- [x] stocks.json 41종목 확장 → Task 2
- [x] --stocks 생성 → Task 3
- [x] 생성 검증 → Task 3 Steps 3–6
- [x] 커밋 → Task 4

**플레이스홀더 없음 확인:**
- 모든 코드 블록에 실제 코드 포함
- 모든 명령에 예상 출력 포함
- "TBD" 없음

**타입 일관성:**
- `rd.ma20_dist_pct`, `rd.ma200_dist_pct` — validate_analysis._closes_to_realdata가 반환, generate_html.stock_realdata()가 _fetch_kospi_realdata 호출로 전달됨
- `rd.week52_low`, `rd.week52_high`, `rd.week52_pos_pct` — stock_realdata()에서 _fetch_stock_closes로 계산
- `stock.sector_key` — stocks.json의 sector_key 필드
