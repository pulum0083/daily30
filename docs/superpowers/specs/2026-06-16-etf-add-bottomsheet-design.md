# ETF 추가 바텀시트 설계

## 배경

인컴 설계기에서 ETF를 선택할 때 모바일 사용자가 "선택 시 시뮬레이터에 추가된다"는 사실을 인지하기 어렵다. 현재는 사이드바 행 클릭 또는 전체 보기 페이지 행 클릭 시 즉시 추가되는데, 추가 피드백이 눈에 잘 안 들어온다. 사전 입력형 바텀시트를 도입해 ETF 정보 확인 + 수량 입력 후 추가하는 흐름으로 개선한다.

## 변경 범위

**파일**: `docs/superpowers/specs/mockups/income-designer.html` (목업 단계)

## 흐름

```
ETF 행 클릭
  → openAddSheet(code)
    → 바텀시트 렌더 + 슬라이드 업 애니메이션
    → 사용자가 수량 입력
    → "시뮬레이터에 추가" 클릭
      → addFromRanking(code, qty) 호출
      → 바텀시트 닫힘
      → (전체 보기에 있었으면 전체 보기 유지, 사이드바에 있었으면 메인 유지)
```

## 바텀시트 구성

| 영역 | 내용 |
|------|------|
| 핸들 | 상단 중앙 짧은 바 — "드래그로 닫기" 힌트 |
| ETF 정보 | 이름(줄바꿈 허용) + KR/US 뱃지 |
| 지표 칩 3개 | 연 분배율(indigo) · 1년 가격변화(gray) · 건전성 뱃지(색상 기존 동일) |
| 수량 입력 | 레이블 "몇 주 담을까요?" + `<input type="number">` 기본값 100 |
| 이미 담긴 경우 | 입력창 위에 "이미 담겨 있어요. 수량을 변경할까요?" 안내 문구 |
| 버튼 행 | 좌: "취소"(secondary) · 우: "시뮬레이터에 추가"(primary, indigo) |

## 열기 / 닫기

- **열기**: `openAddSheet(code)` — 시트 DOM 렌더 후 `translateY(100%)` → `translateY(0)` CSS transition(0.25s ease-out)
- **닫기**: `closeAddSheet()` — `translateY(0)` → `translateY(100%)` 후 display none, 오버레이 제거
- 딤 오버레이 클릭 시 닫힘
- "취소" 버튼 클릭 시 닫힘

## 트리거 변경

| 기존 | 변경 후 |
|------|---------|
| `irow` onclick → `addFromRanking(code)` | `openAddSheet(code)` |
| `trow` onclick → `addFromRankingPage(code)` | `openAddSheet(code)` (전체 보기 닫지 않음) |
| 갈아타기 "시뮬레이터에 추가" 버튼 | 변경 없음 — 명시적 버튼이므로 즉시 추가 유지 |
| 목표 달성 전략 "시뮬레이터에 추가" 버튼 | 변경 없음 — 동일 이유 |

## addFromRanking 시그니처 변경

```js
// 기존: addFromRanking(code)  — qty 고정 100
// 변경: addFromRanking(code, qty)  — 시트에서 입력한 값 전달
function addFromRanking(code, qty = 100) { ... }
```

기존 갈아타기·목표 전략 버튼에서 qty 없이 호출하면 기본값 100 유지 — 하위 호환.

## DOM 구조

```html
<!-- body 직속 또는 .wrap 형제 -->
<div id="add-sheet-overlay" onclick="closeAddSheet()" style="display:none;..."></div>
<div id="add-sheet" style="display:none;...">
  <div class="add-sheet-handle"></div>
  <div id="add-sheet-body"><!-- JS로 렌더 --></div>
</div>
```

## CSS

- 시트: `position:fixed; bottom:0; left:0; right:0; border-radius:16px 16px 0 0; z-index:300`
- 오버레이: `position:fixed; inset:0; background:rgba(0,0,0,.4); z-index:299`
- transition: `transform .25s ease-out`

## 엣지 케이스

- 이미 담긴 종목: 안내 문구 표시, 입력값 그대로 추가(기존 수량에 합산하지 않고 qty로 덮어씀 — 기존 `addFromRanking` 동작 그대로)
- 수량 0 이하 입력: "추가" 버튼 비활성화(disabled)
- 수량 입력창: `min=1`, `step=1`, 열릴 때 자동 포커스 + 전체 선택
