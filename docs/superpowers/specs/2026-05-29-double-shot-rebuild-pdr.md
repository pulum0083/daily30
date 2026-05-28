# Double-Shot 서비스 리빌딩 PDR

**작성일**: 2026-05-29  
**상태**: 프로토타입 확정 → 구현 플랜 작성 전

---

## 1. 배경 및 목적

기존 구조의 문제점:
- `generate_html.py` 1,000줄+, `style.css` 2,700줄+ — 한 곳 수정 시 다른 곳 깨짐
- `patch_*.py` 임시 픽스 누적 (Fear & Greed 등)
- GNB가 여러 파일에 흩어져 있어 수정 시 불일치 발생
- 새 브리핑 타입·섹션 추가/제거가 계속될 예정 → 현재 구조로는 유지 어려움

목표: **config-driven section assembly** — 브리핑 타입별 config가 섹션 목록 선언, `generate_html.py`는 조립만 담당.

---

## 2. 확정된 범위

| 포함 | 제외 |
|------|------|
| 웹 페이지 (HTML 생성) | 텔레그램 발송 (현행 유지) |
| 데이터 수집 스크립트 | GitHub Actions 워크플로 구조 |
| AI 분석 스크립트 | Vercel 라우팅 설정 |
| CSS·JS 에셋 | |

---

## 3. 기술 스택

- **Python + Jinja2** 정적 생성 (프레임워크 미도입)
- **GitHub Actions** + **Vercel** 배포 유지
- **디자인 시스템**: Pretendard Variable, 색상 토큰, 8px 그리드

---

## 4. 브리핑 3종

| 타입 | 실행 | URL |
|------|------|-----|
| 코스피 시초가 예측 | 07:30 KST | `/briefings/{date}/kospi/` |
| 코스피 마감 | 15:40 KST | `/briefings/{date}/close/` |
| 미국 시장 예측 | 21:20 KST | `/briefings/{date}/us/` |

---

## 5. URL 체계

브리핑 단위 독립 URL 채택 (텔레그램 링크가 정확한 브리핑으로 직행해야 하기 때문).

```
/briefings/                          → 최신 브리핑 + 목록
/briefings/{YYYY-MM-DD}/kospi/       → 코스피 예측 뷰어
/briefings/{YYYY-MM-DD}/close/       → 코스피 마감 뷰어
/briefings/{YYYY-MM-DD}/us/          → 미국 시장 예측 뷰어
```

레거시 호환 (Vercel 리다이렉트 유지):
```
/briefings/ko/{date}/   → /briefings/{date}/kospi/
/briefings/us/{date}/   → /briefings/{date}/us/
```

---

## 6. 페이지 구조

### 6-1. `/briefings` 진입 시

```
[GNB: Double-Shot | Chip-Board →]
[LATEST 2026-05-29 · 코스피 시초가 예측    URL 복사]
─────────────────────────────────────────────────
[최신 브리핑 전체 콘텐츠]
  └ 날짜 헤더: 2026-05-28        [‹] [›]
  └ 브리핑 본문 (예측·근거·종목픽·사이드바)
─────────────────────────────────────────────────
브리핑 목록
[TODAY 카드: 코스피 예측 | 코스피 마감 | 미국 시장]
[날짜 1행 리스트: 05-28 | 05-27 | 05-26 | ...]
```

### 6-2. 브리핑 뷰어 `/briefings/{date}/{type}/`

```
[GNB: Double-Shot | Chip-Board →]
─────────────────────────────────────────────────
[선택한 브리핑 전체 콘텐츠]
  └ 날짜 헤더: 2026-05-28        [‹] [›]
    └ ‹ = 같은 타입 이전 날짜, › = 이후 날짜
    └ 없으면 해당 화살표 비활성(opacity .25)
  └ 브리핑 본문
─────────────────────────────────────────────────
브리핑 목록
[TODAY 카드]
[날짜 1행 리스트 — 현재 선택된 날짜+타입 셀 하이라이트]
```

---

## 7. 브리핑 목록 (v1: 날짜 1행)

- 최신 30일만 유지 (30일 초과분 자동 삭제)
- 1행 = 1일, 3열: 코스피 예측 / 코스피 마감 / 미국 시장
- 생성된 브리핑: 방향 뱃지(▲/▼) + 생성 시각 표시, 클릭 가능
- 미생성: 흐리게(opacity .35), "미생성" 텍스트, 클릭 불가
- TODAY 카드: 상단 고정, 오늘 3개 슬롯 (미생성은 점 펄스 애니메이션 + "예정 시각")

---

## 8. 날짜 헤더 네비게이션

브리핑 콘텐츠 카드 우측 상단에 `[‹] [›]` 화살표 아이콘 버튼 배치.

- 이전/다음은 **같은 타입 기준** (코스피 예측 ↔ 코스피 예측끼리)
- 날짜 없으면 비활성 (pointer-events:none, opacity .25)
- `generate_html.py`가 렌더링 시 prev/next URL을 Jinja2 컨텍스트로 주입

---

## 9. GNB

모든 페이지 동일한 단일 GNB:

```
[로고마크] Double-Shot | Chip-Board →       날짜·시각   [다크모드 토글]
```

- `base.html` 한 곳에서만 관리
- 브리핑 콘텐츠가 임베드될 때는 GNB 숨김 (`body.is-embed .gnb { display:none }`)

---

## 10. 아키텍처 (Config-Driven Section Assembly)

```
scripts/
├── templates/
│   ├── base.html               ← GNB·푸터 포함
│   ├── sections/
│   │   ├── prediction.html     ← 예측 섹션
│   │   ├── reasons.html        ← 근거 섹션
│   │   ├── stock_picks.html    ← 종목픽 섹션
│   │   ├── close_index.html    ← 마감 지수 섹션
│   │   ├── market_width.html   ← 시장폭 섹션
│   │   ├── supply.html         ← 수급 섹션
│   │   └── ...
│   ├── briefings/
│   │   ├── kospi.html          ← sections 조립
│   │   ├── close.html
│   │   └── us.html
│   └── pages/
│       ├── briefings_index.html ← /briefings 페이지
│       └── briefings_list.html  ← 목록 컴포넌트
├── config/
│   ├── kospi.json              ← 섹션 목록·순서
│   ├── close.json
│   └── us.json
└── generate_html.py            ← 조립 전용 (로직 최소화)
```

---

## 11. 어조 원칙

- 대상: 15년차+ 전문 투자자
- 친근체("~해요/~거든요") → **선언형** ("S&P500 +0.58%. 기술주 중심 강세로 코스피 갭업 출발이 기대된다.")
- 데이터 밀도 높게, Bloomberg 스타일
- `call_claude.py` 프롬프트 수정 필요

---

## 12. 확정된 프로토타입 파일

| 파일 | 내용 |
|------|------|
| `docs/prototypes/briefing-kospi.html` | 코스피 예측 브리핑 |
| `docs/prototypes/briefing-close.html` | 코스피 마감 브리핑 |
| `docs/prototypes/briefing-us.html` | 미국 시장 예측 브리핑 |
| `docs/prototypes/briefing-list.html` | 목록 v1 (날짜 1행) |
| `docs/prototypes/page-briefings-index.html` | `/briefings` 진입 페이지 |
| `docs/prototypes/page-briefings-viewer.html` | 브리핑 뷰어 페이지 |

---

## 13. 다음 단계

1. **구현 플랜 작성** (`writing-plans` 스킬) — 이 PDR 기반
2. **구현 단계** (별도 세션):
   - Phase 1: base.html + CSS 토큰 + GNB
   - Phase 2: 섹션 템플릿 분리 (Jinja2)
   - Phase 3: config JSON + generate_html.py 리팩터
   - Phase 4: /briefings 목록 페이지 + 뷰어 페이지
   - Phase 5: 어조 변경 (call_claude.py 프롬프트)
3. **스크립트 정리**: patch_fg.py 등 임시 픽스 통합
