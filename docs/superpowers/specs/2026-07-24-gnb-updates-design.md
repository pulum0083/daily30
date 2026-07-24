# GNB 업데이트 로그 — 설계

## 배경

서비스에 새 기능·UI 변경이 계속 반영되는데, 사용자가 이를 알 방법이 없다.
GNB(전역 상단바)에 업데이트 로그 버튼을 두어, 클릭 시 최근 변경 목록을 볼 수 있게 한다.

## 범위

**대상 3곳** (GNB 마크업을 직접 보유한 소스 3곳):
- `web/landing.html` (랜딩페이지)
- `web/stocks/index.html` (종목 대시보드)
- `scripts/templates/base.html` (브리핑 공통 템플릿 — kospi/close/us 신규 발행분에 적용)

**범위 밖** (이번엔 손대지 않음, 필요 시 같은 2개 파일 링크만 추가하면 확장 가능):
- 종목 상세 페이지(`scripts/templates/stocks/detail.html`, `us_detail.html`) 80여개
- 섹터 페이지(`scripts/templates/pages/stock_sector.html`)
- 법적고지 페이지(`web/legal/*`)
- 이미 생성된 과거 브리핑 정적 HTML (다음 재생성 전까지 미반영 — 신규 발행분부터 적용)

## 데이터

`web/data/changelog.json` — 수동 관리, 최신순 배열:

```json
[
  { "date": "2026-07-24", "title": "자금 지도 타일 펼침 애니메이션", "body": "클릭 시 상위 ETF 목록이 부드럽게 펼쳐지도록 개선했어요." }
]
```

- 히스토리 아카이브가 아님 — 최근 항목만 유지(오래된 항목은 지워도 무방).
- 커밋할 때마다 사람이 직접 항목을 추가하는 수동 워크플로우(자동 생성 아님).

## 구성 요소

1. **`web/assets/gnb-updates.js`** (신규, IIFE)
   - GNB의 `.right`(검색 버튼 옆) 영역에 🔔 버튼을 동적으로 삽입.
   - 버튼 클릭 → 드롭다운 패널 토글, `changelog.json`을 fetch해 목록 렌더(날짜·제목·본문).
   - `localStorage['gnb-updates-seen']`에 "마지막으로 확인한 날짜" 저장.
   - 최신 항목 날짜 > 저장된 날짜 → 버튼에 빨간 점 뱃지 표시(개수 아님, 점만 — YAGNI).
   - 패널을 열면 뱃지 사라지고 localStorage 갱신. 바깥 클릭 시 패널 닫힘.
   - fetch 실패 시 버튼 자체를 숨김(§0 원칙과 동일한 안전장치 — 억지로 빈 상태를 보여주지 않음).

2. **`web/assets/gnb-updates.css`** (신규)
   - 버튼·뱃지·드롭다운 패널 스타일만 포함. 기존 `style.css`/`stocks-home.css`는 건드리지 않음.

3. **3개 진입점에 링크 추가**
   - `<link rel="stylesheet" href="/assets/gnb-updates.css">`
   - `<script src="/assets/gnb-updates.js" defer></script>`

## 동작 흐름

```
페이지 로드 → gnb-updates.js가 .gnb .right에 🔔 버튼 삽입
  → fetch /data/changelog.json
    → 실패 시 버튼 숨김, 종료
    → 성공 시 items[0].date와 localStorage 저장값 비교 → 다르면 뱃지 표시
  → 버튼 클릭 → 패널 열림/닫힘 토글
    → 열릴 때: 뱃지 제거, localStorage에 items[0].date 저장, 목록 렌더
  → 문서 바깥 클릭 → 패널 닫힘
```

## 테스트/검증

- 각 3개 페이지에서 버튼 노출·패널 열림/닫힘·뱃지 표시/제거를 브라우저로 직접 확인.
- `changelog.json` 없음/404 상황에서 버튼이 조용히 숨겨지는지 확인.
- 별도 자동 테스트는 두지 않음(정적 페이지 + 소량 DOM 로직이라 과함).
