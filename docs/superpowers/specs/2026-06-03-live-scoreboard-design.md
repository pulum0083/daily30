# 라이브 예측 스코어보드 — 설계 문서

> 작성: 2026-06-03  
> 상태: 브레인스토밍 완료, 구현 대기  
> 목업 파일: `docs/prototypes/live-scoreboard-E.html`

---

## 1. 배경 및 목적

Double-Shot은 매일 아침 코스피·미국 시장 예측 브리핑을 발행한다. 현재는 아침(예측)과 저녁(마감 결과)만 존재해 장중에는 서비스를 열 이유가 없다.

**핵심 통찰:** Double-Shot이 가진 유일한 자산은 "오늘 아침에 내린 예측"이다. 장중 재방문을 만드는 열쇠는 그 예측이 지금 맞고 있는지 추적하는 것 — **중계 모델**(아침=프리뷰, 장중=라이브, 저녁=결과).

---

## 2. 확정된 기능 범위

### 이번 구현 포함
- **라이브 예측 스코어보드** (변형 E) — 코스피 브리핑에만 적용

### 이번 구현 제외
- 정오 점검 텔레그램 알림 (추후 검토)
- 미국 시장 버전
- 픽 종목 라이브 추적
- `/live` 별도 페이지

---

## 3. UI 설계 (변형 E)

### 3-1. 배치
- **위치:** 기존 코스피 브리핑 페이지 상단 (aside 영역 최상단)
- **노출 조건:** 장중(09:00~15:30 KST, 평일)에만 활성. 마감 후 최종 판정으로 고정.

### 3-2. 카드 구조 (위→아래)

```
┌─────────────────────────────────────────┐
│ 예측 vs 실제 · 코스피          ● LIVE   │  ← 헤더 (LIVE: 연한 녹색 배경 #dafbe1, 텍스트 #1a7f37)
├─────────────────────────────────────────┤
│ 예측대로 순항 중                         │  ← 헤드라인 (19px Bold, 강조어 색 = 판정 상태 색)
│ 아침 "상승 우위(신뢰도 76%)" 예측이...  │  ← 서브텍스트 (12.5px, muted)
│ [이탈] ─────────[박빙]─────────[적중]  │  ← 판정 게이지 (바늘이 실시간 이동)
├─────────────────────────────────────────┤
│ 2,718.40  +0.42%  ↑상승우위  ↻30초     │  ← 현재값 행 (지수+등락%+예측태그+갱신주기)
├─────────────────────────────────────────┤
│ ● 방금 업데이트 · 14:00 기준 · 매1시간 │  ← 뉴스 이슈 헤더
│ [파란 카드: 최신 이슈 제목            ] │  ← 최신 이슈 (파란 배경 카드, 제목+한 줄 요약)
│  [직전 이슈 타이틀]            ∨        │  ← 아코디언 토글 (닫힌 상태: 직전 이슈 타이틀 미리보기)
│  (열리면) 이전 이슈 접기       ∧        │  ← 아코디언 토글 (열린 상태)
│   13:00  이슈 제목                      │  ← 이전 이슈 목록 (시간 역순)
│   12:00  이슈 제목                      │
│   ...                                   │
├─────────────────────────────────────────┤
│ 마감까지 1:17:30                         │  ← 푸터 (카운트다운만, 갱신주기는 지수 행에)
└─────────────────────────────────────────┘
```

### 3-3. 판정 상태 3종

| 상태 | 헤드라인 강조어 | 강조어 색 | 게이지 바늘 위치 | 뉴스 이슈 톤 |
|------|---------------|----------|----------------|-------------|
| 적중 중 | "순항 중" | 빨강(상승) #E03131 | 우측 (76%) | 긍정적 |
| 박빙 | "팽팽한 접전" | 골드 #B7791F | 중앙 (50%) | 중립 |
| 이탈 중 | "빗나가는 중" | 파랑(하락) #2775ED | 좌측 (20%) | 부정적 |

> 빗나감을 숨기지 않는 **정직성**이 브랜드 차별점.

### 3-4. LIVE 배지 색
- 배경: `#dafbe1` (연한 민트 녹색)
- 텍스트: `#1a7f37`
- 점(dot): `#2da44e`, 애니메이션 pulse
- **의도:** 상승(빨강) · 하락(파랑)과 명확히 구분되는 중립 색

---

## 4. 데이터 및 갱신 주기

### 코스피 지수 (30초)
- **소스:** 기존 `api/kospi-live.mjs` (네이버 코스피 프록시, `Cache-Control: s-maxage=30`)
- **방식:** 클라이언트 JS `setInterval(30000)` → fetch → DOM 업데이트
- **갱신 항목:** 지수값, 등락률, 판정 상태(헤드라인+게이지 바늘)

### 뉴스 이슈 (1시간)
- **소스:** 신규 GitHub Actions job (장중 매 정시: 09, 10, 11, 12, 13, 14, 15시)
- **파이프라인:** cron-job.org → GitHub Actions → Gemini 2.5 Flash (Google Search grounding) → `web/data/kospi-news-live.json` 저장 → 클라이언트 fetch
- **프롬프트:** "지금 코스피 장중에 영향을 주는 핵심 이슈 1개. 제목(15자 이내) + 한 줄 요약(40자 이내) JSON."
- **구조:**
  ```json
  {
    "updated_at": "14:00",
    "latest": { "title": "외국인, 반도체 집중 순매수 전환", "summary": "삼성·SK하이닉스 중심 2,300억 순매수 전환." },
    "history": [
      { "time": "13:00", "title": "원·달러 환율, 1,380원대 안정세", "summary": "..." },
      ...
    ]
  }
  ```

### 판정 상태 계산 (클라이언트 JS)
- 아침 예측 방향(`data-dir="up"|"down"`)과 현재 등락률로 계산
- `changePct > 0.1` + 예측 up → 적중
- `|changePct| <= 0.1` → 박빙
- 예측과 반대 방향 → 이탈

---

## 5. 아키텍처

### 신규 파일
| 파일 | 역할 |
|------|------|
| `web/data/kospi-news-live.json` | 장중 뉴스 이슈 (cron 생성) |
| `scripts/fetch_news_live.py` | Gemini 장중 뉴스 요약 스크립트 |

### 수정 파일
| 파일 | 변경 내용 |
|------|---------|
| `scripts/templates/briefings/kospi.html` | 스코어보드 섹션 include 추가 |
| `scripts/templates/sections/_live_scoreboard.html` | 스코어보드 HTML 템플릿 |
| `web/assets/main.js` | `initLiveScoreboard()` 함수 추가 |
| `web/assets/style.css` | 스코어보드 CSS 추가 |
| `.github/workflows/daily_report.yml` | `kospi-news-live` job 추가 |

### 기존 재사용
- `api/kospi-live.mjs` — 그대로 사용 (30초 지수 갱신)

---

## 6. 장/장외 상태 처리

| 상황 | 처리 |
|------|------|
| 장전 (09:00 이전) | 스코어보드 미노출 (조건부 렌더링) |
| 장중 (09:00~15:30) | LIVE 배지 + 실시간 갱신 |
| 장 마감 후 (15:30~) | LIVE → "마감" 배지, 최종 판정으로 고정, 갱신 중단 |
| 휴장일 | 스코어보드 미노출 |

---

## 7. 디자인 시스템

- **목표:** GronkOut/ncai-design-system CSS 토큰 사용
- **토큰 매핑:**

| 기존 (현 서비스) | NCAI 토큰 |
|----------------|-----------|
| `--canvas` | `--color-canvas` |
| `--surface-soft` | `--color-surface-soft` |
| `--surface-inset` | `--color-surface-inset` |
| `--hairline` | `--color-hairline` |
| `--ink` | `--color-ink` |
| `--muted` | `--color-body-muted` |
| `--primary` | `--color-primary` |
| `--up` (#E03131) | `--color-semantic-error` (#f33942) |
| `--up-bg` | `--color-semantic-error-bg` |
| `--gold` | `--color-semantic-warning` |
| `--gold-bg` | `--color-semantic-warning-bg` |

- **하락(--dn) 주의:** NCAI는 하락 전용 색이 없음 → `--color-primary` (#006eff) 사용 (기존 #2775ED와 유사한 파랑 계열)
- **폰트:** `--font-text` (Pretendard Variable)

---

## 8. 구현 순서 (다음 세션)

1. `scripts/templates/sections/_live_scoreboard.html` 작성
2. `web/assets/style.css`에 스코어보드 CSS 추가 (NCAI 토큰 사용)
3. `web/assets/main.js`에 `initLiveScoreboard()` 추가
4. `scripts/templates/briefings/kospi.html`에 include 추가
5. `scripts/fetch_news_live.py` 작성 (Gemini 장중 뉴스)
6. `web/data/kospi-news-live.json` 초기값 생성
7. `.github/workflows/daily_report.yml`에 `kospi-news-live` job 추가
8. 장중 테스트 후 배포

---

## 9. 참고 목업

- `docs/prototypes/live-scoreboard-E.html` — 최종 확정 UI (현재 서비스 CSS 토큰 기준)
- `docs/prototypes/halftime-check.html` — 정오 점검 UI (이번 범위 제외, 참고용)
- `docs/prototypes/live-scoreboard.html` — A/B/C 변형 비교
