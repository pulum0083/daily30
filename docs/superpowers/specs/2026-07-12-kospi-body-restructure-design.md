# 코스피 아침 브리핑 본문 재구조 — 설계 (프로토타입 정합)

작성: 2026-07-12
프로토타입: `docs/prototypes/2026-07-11-kospi-briefing-redesign.html`
결정: 사용자 — "로테이션은 오늘의 관점으로 올리고, 별도 넘버링(이렇게 보는 이유) 추가"

## 배경 — 현재 vs 프로토타입

**현재 실서비스:**
```
① 오늘의 관점 = 제목 + 복기(recap) + 관전(outlook)   ← 고정
② 예측 스트립
③ 근거 섹션   = 6개 포맷(scenario/qa/flow/signal/keynum/why_what_so) 중 매일 랜덤 1개
```
`call_claude.py:1332`가 `random.choices(FORMAT_POOL)`로 하루치 포맷 1개 선택.
`reasons` 배열은 현재 비어 있음(포맷 로테이션이 그 자리를 대체).

**프로토타입(목표):**
```
① 오늘의 관점 = 제목 + dek + [6포맷 로테이션]        ← 로테이션이 관점 안
② 예측
③ 이렇게 보는 이유 = 넘버링 리스트 1·2·3            ← 별도, 항상
```

## 목표 구조

```
① 지금 코스피 밴드          (변경 없음)
② 오늘의 관점 = 제목 + dek + [6포맷 로테이션]
③ 예측 스트립              (변경 없음)
④ 이렇게 보는 이유 = 넘버링 리스트(1·2·3)          신규
⑤ 외국계 시각             (완료)
⑥ 종목 픽                (변경 없음)
```

## 하위 결정 (권장안 — 검토 요청)

### D1. recap/outlook(현재 오늘의 관점 본문)의 운명 — **확정(2026-07-12 사용자): split 포맷으로 편입**
프로토타입에서 "기본(복기·프레임)"은 6개 로테이션 포맷 중 하나(`split`)다. 따라서 현재의
recap/outlook을 **`split` 포맷으로 편입**해 로테이션 풀에 넣는다. split이 뽑힌 날만 복기/관전이
보이고, 다른 날은 scenario·qa·flow 등이 관점 자리에 뜬다.
- FORMAT_POOL에 `split` 추가(현재 6개 → 7개). todays_view(recap/outlook)는 `split` 포맷 데이터로 이관.
- 대안(비추천): recap/outlook 항상 유지 + 그 아래 로테이션 별도 → 관점 영역이 과도하게 길어짐.

### D2. 오늘의 관점(로테이션) vs 이렇게 보는 이유(넘버링) 내용 중복 방지 — **권장: 역할 분리**
- **오늘의 관점(로테이션)** = 그날의 *이야기·프레이밍* (내러티브: 시나리오/Q&A/흐름/신호등/핵심숫자/복기).
- **이렇게 보는 이유(넘버링)** = 예측 *근거 3줄 압축* (핵심 드라이버: 금리·반도체·수급 식). 관점과 다른 각도, 불릿형.
- LLM 프롬프트에 명시: "reasons는 관점 섹션과 문장을 반복하지 말고, 예측 방향의 핵심 동인 3개만 압축."

### D3. reasons 데이터 부활 — **권장: 스키마에 `reasons` 배열 복원**
- `reasons`: `[{ "text": "<b>핵심</b> 설명…", "codes": ["000660"] }]` 3개. (text에 `<b>` 허용, 종목 언급 시 codes)
- validate_analysis에서 codes 실측 검증(todays_view.recap과 동일 로직 재사용).
- generate_html `build_reasons`는 현재 포맷 컨텍스트만 만듦 → `reasons` 렌더 컨텍스트 추가.

### D4. dek(관점 부제) — **권장: 신규 필드 `todays_view.dek` 추가**
프로토타입 `.lead__dek`("지난주 후반 반등을 이끈 건…"). 제목 아래 1~2문장 해요체.
- `todays_view.dek` 필드 추가. 없으면 생략(하위호환).

## 파일 변경 범위

- `scripts/call_claude.py`
  - FORMAT_POOL에 `split` 추가 + split 포맷 지시문.
  - 프롬프트·스키마: `reasons` 배열(3개) 복원 + 역할 분리 지시(D2), `todays_view.dek` 추가(D4).
- `scripts/validate_analysis.py`: `reasons[].codes` 실측 검증(recap 로직 재사용).
- `scripts/generate_html.py`:
  - `build_reasons`에 `reasons` 렌더 컨텍스트 추가.
  - `split` 포맷 컨텍스트 빌더(recap/outlook) — 기존 todays_view 렌더를 포맷 케이스로 이동.
- `scripts/templates/briefings/kospi.html`: 재배치 — 관점 안에 포맷 렌더, 예측 뒤 `reasons.html` 추가.
- `scripts/templates/sections/`:
  - `todays_view.html` → 관점 셸(제목+dek) + 포맷 include.
  - 신규 `reasons.html`(넘버링 리스트, 프로토 `.rlist/.ritem/.rnum/.rtext`).
  - `split.html`(recap/outlook) 신규 or todays_view 재사용.
- `web/assets/style.css`: `.lead__dek`→`.tv-dek`, `.rlist/.ritem/.rnum/.rtext` 이식(네임스페이스 `.rz-*` 검토).

## 리스크

- LLM 스키마 변경 → 프롬프트 캐시 무효화(1회), 출력 필드 늘어 토큰 소폭 증가.
- reasons ↔ 관점 로테이션 내용 중복은 프롬프트 품질에 의존 — 초기 며칠 실출력 점검 필요.
- split 편입으로 복기/관전이 매일 안 보임(1/7 확률로만). 사용자가 복기/관전을 매일 원하면 D1 대안 재고.

## 검증

- 로컬 파이프라인(venv312)으로 실데이터 1회 생성 → 7개 포맷 각각 렌더·reasons 넘버링·dek 확인.
- 포맷별 목업 하니스로 split/scenario/qa 등 관점 렌더 + reasons 병존 확인.
- 다크 모드.

## 범위 밖

- 미국·마감 브리핑은 현행 유지(reasons·dek·split 미적용). 코스피 아침 전용.
- 포맷 스위처 UI(프로토의 fmt-tabs)는 프로토타입 전용 — 실서비스는 자동 로테이션이므로 미구현.
