# GNB 업데이트 로그 — 설계 (개정)

## 배경

서비스에 새 기능·UI 변경이 계속 반영되는데, 사용자가 이를 알 방법이 없다.
GNB(전역 상단바)에 업데이트 로그 버튼을 두어, 클릭 시 최근 변경 목록을 볼 수 있게 한다.

## ⚠️ 개정 사유

최초 설계는 `changelog.json` + `gnb-updates.js/css` 신규 파일을 제안했으나,
조사 결과 **동일 기능이 이미 구현돼 있음**을 확인했다:

- `web/assets/main.js:482-752` — `/data/notices.json` 기반 "공지·게시판" 패널.
  `type: "update"/"ops"/"urgent"` 뱃지, localStorage 읽음 추적(`ds_read_notices`),
  안읽음 점 표시(`checkAndShowDot`)까지 전부 구현돼 있음.
- `web/landing.html:208` — GNB에 🔔 버튼(`gnb-notif-btn`)이 이미 붙어 있고 정상 동작.
- `web/assets/style.css:76-124` — 버튼·패널 CSS 전부 존재.
- `web/data/notices.json` — 데이터도 이미 있음. 다만 마지막 항목이 2026-06-05로 한 달 넘게 정체.

즉, 랜딩페이지에는 이미 기능이 있고 **브리핑·종목 대시보드에만 버튼이 빠져 있는 것**이
진짜 문제다. 새 시스템을 만들면 중복 구현이 되므로, 기존 시스템을 두 곳에 더 연결하는
쪽으로 범위를 바꾼다.

## 범위

**변경 없음(이미 동작):**
- `web/landing.html` — 버튼·JS·CSS 전부 이미 있음.

**연결 추가 (신규 파일 없음, 기존 3개 파일만 수정):**

1. `scripts/templates/base.html` — `{% block gnb %}`에 🔔 버튼 마크업 추가.
   main.js는 이미 `<script src="{{ js_path | default('/assets/main.js...') }}">`로
   로드 중이라, 마크업만 추가하면 즉시 동작(신규 발행 브리핑부터 적용).

2. `web/stocks/index.html` — 같은 버튼 마크업 추가 +
   `<script src="/assets/main.js" defer></script>` 신규 로드.
   - main.js는 IIFE로 감싸여 있고 모든 DOM 조회가 `if (!el) return` 가드로
     방어돼 있어(확인 완료), 이 페이지에 없는 브리핑 전용 엘리먼트(스코어보드 등)를
     찾다가 조용히 no-op됨 — 부작용 없음.
   - 다크모드 초기화(`classList.replace('light','dark')`)도 이 페이지 `<html>`에
     `class="light"`가 애초에 없어 no-op — 의도치 않은 다크모드 전환 없음.

3. `web/assets/stocks-home.css` — `style.css:76-124`의 공지·게시판 패널 CSS를
   복사해 추가. 변수명 2개만 치환:
   - `var(--hairline)` → `var(--hair)`
   - `var(--gnb-bg)` → `var(--gnb)`
   - 나머지 변수(`--canvas`, `--ink`, `--muted`, `--primary`, `--primary-bg`,
     `--up`, `--up-bg`, `--gold`, `--gold-bg`)는 stocks-home.css에 이미 동일한
     이름으로 정의돼 있어 그대로 사용 가능(확인 완료).

**데이터:**

4. `web/data/notices.json` — 최신 항목 추가(수동, `type: "update"`):
   - 자금 지도 타일 펼침 애니메이션
   - 섹터별 대표 종목 탭 PC 스티키 고정
   - 마감 브리핑 사이드바 위젯 통일

**범위 밖:**
- 종목 상세 페이지·섹터 페이지·법적고지 페이지(main.js 미로드 상태 유지, 필요 시 추후 확장)
- 게시판(board) 글쓰기 API(`/api/board`)는 손대지 않음 — 기존 그대로, 로컬 프리뷰에서
  실패해도 "다시 시도" 버튼으로 graceful degrade(기존 landing.html과 동일 동작)

## 동작 흐름 (기존 시스템 그대로)

```
페이지 로드(load 이벤트) → checkAndShowDot()
  → /data/notices.json fetch → 안읽음 항목 있으면 점 표시
버튼 클릭 → openNoticePanel()
  → 패널 열림, notices.json 재조회해 렌더, 읽음 처리(localStorage 갱신), 점 제거
바깥 클릭/닫기 버튼 → closeNoticePanel()
```

## 테스트/검증

- 3개 페이지(랜딩·종목 대시보드·브리핑 신규 발행분)에서 버튼 노출·패널 열림/닫힘·
  뱃지 표시/제거를 브라우저로 직접 확인.
- 종목 대시보드에서 main.js 추가 로드 후 기존 stocks-home.js 기능(신호·자금 지도 등)이
  정상 동작하는지 회귀 확인.
- 별도 자동 테스트는 두지 않음(기존 시스템 재사용이라 로직 자체는 변경 없음).
