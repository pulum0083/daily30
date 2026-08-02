# 코스피 브리핑 위로 카드 재구성 — 설계

작성일 2026-08-02 · 대상 화면 코스피 아침 브리핑(`web/briefings/{date}/kospi/index.html`)

## 배경·목적

사용자 지시(2026-08-02)로 코스피 브리핑 상단 구성을 조정한다.

1. "이렇게 보는 이유"(`key_drivers` 3줄 넘버링) 섹션을 화면에서 제거한다.
2. 그 아래 있던 "위로 한 줄"(`comfort_line`) 카드를 확장해, 텔레그램 발송 메시지 끝에 붙는 투자 구루 명언(`data/guru_quotes.json`, 272개)을 웹에도 같이 보여준다.

비주얼 컴패니언으로 3라운드(A/B/C 배치안 → C 재설계 3변형) 검토 후 **C2(따옴표 글리프, 명언이 주인공)**로 확정했다.

## 화면 변경

### 1) "이렇게 보는 이유" 제거

`scripts/templates/briefings/kospi.html`에서 `{% if key_drivers %}{% include "sections/reasons.html" %}{% endif %}` 줄을 제거한다.

- **데이터 파이프라인은 건드리지 않는다.** `call_claude.py`는 여전히 `key_drivers`를 생성하고, `validate_analysis.py`의 §22 `validate_key_drivers`·§24 `_index_figure_wrong`·§28 `validate_index_superlatives`·§29 `validate_event_tense` 등은 여전히 이 필드를 검증한다 — 화면에 안 보여도 이 필드는 다른 필드(todays_view 등)의 서사가 기대는 근거이자 검증 대상이므로 생성 자체를 끊지 않는다. 이번 변경은 **렌더링 레이어 한 줄**이다.
- `reasons.html` 템플릿 파일 자체는 삭제하지 않는다(다른 브리핑 타입이 쓰지 않는 걸 확인했지만, 좌표 상 조용히 죽은 코드로 남겨도 §0 위반이 아니다 — 필요하면 나중에 정리).

### 2) 위로 카드 확장 — C2 (따옴표 글리프)

`scripts/templates/sections/_comfort_line.html`을 아래 구조로 교체한다.

```
[더블샷 카드 배경: surface-soft, radius 12px]
  " (44px, 색 var(--hairline), 장식용 글리프)
  명언 본문 (16px, weight 600, line-height 1.62)
  — 저자 (13px, var(--muted))
  ─── hairline 구분선 ───
  [원형 아이콘뱃지] 위로 문구 (13px, var(--muted))
```

- 좌측 컬러 액센트 바 없음(ncai 규칙). 강조는 타이포 위계(명언 16px/600 vs 위로문구 13px/400)와 톤(surface-soft 카드)만으로.
- 명언·저자가 위, 위로 문구가 아래 — "명언이 주인공"이라는 배치 의도를 그대로 반영.
- 색상 신규 사용 없음(ncai semantic 팔레트 개입 여지 없음 — 순수 무채색 타이포).
- 위치는 기존과 동일: `prediction_strip`/`prediction` 다음, `divider` 앞. (기존엔 그 사이에 `reasons`가 있었으나 위 1번 변경으로 빠지므로, 카드는 예측 섹션 바로 다음으로 한 칸 당겨진다.)

## 명언 데이터 — 텔레그램과 동기화

**문제**: 지금 `pick_quote()`(`scripts/send_telegram.py`)는 텔레그램 발송 직전(`main()` 안)에 `random.choice()`로 뽑는다. 웹 페이지는 그보다 앞선 `call_claude.py --render` 단계에서 이미 완성된다. 이대로 웹에 명언을 넣으면 각자 따로 뽑아 **같은 날 텔레그램과 웹이 서로 다른 명언**을 보여준다.

**해결**: 뽑는 시점을 렌더 단계로 옮기고, 텔레그램이 그 결과를 읽어 쓰도록 뒤집는다.

1. `call_claude.py`의 `render_outputs()` 안, **`briefing_type == "kospi"`일 때만**, `generate_html.py` 서브프로세스를 호출하기 전에 `data/guru_quotes.json`에서 랜덤 1개를 뽑아 `data/quote_today.json`에 저장한다: `{"date": "2026-08-02", "quote": "...", "author": "..."}`. (`render_outputs()`는 먼저 `save_telegram_message()`로 텔레그램 txt를 쓰고 그다음 `generate_html.py`를 호출하는 순서 — quote_today.json은 HTML 렌더가 읽으므로 그 호출 전에 존재해야 한다. us·kospi-close 타입은 건드리지 않는다.)
2. `generate_html.py`가 이 파일을 읽어 위 C2 카드에 렌더한다. **날짜가 오늘이 아니면(=이 코스피 브리핑 실행분에서 만든 게 아니면) 렌더하지 않고 위로 문구만 표시** — stale 명언을 화면에 남기지 않는다(§0 정신 일관 적용, 다만 명언 자체는 큐레이션된 정적 문구라 이 게이트는 "오늘 것만 쓴다"는 신선도 확인이지 §0의 실측 검증과는 성격이 다르다).
3. `pick_quote()`(`send_telegram.py`)를 수정: `data/quote_today.json`이 존재하고 `date`가 오늘이면 그 값을 그대로 쓴다. 없거나 날짜가 다르면 **기존 `random.choice()` 폴백** 그대로 유지 — 코스피 브리핑이 아닌 타입(us·kospi-close)이나 렌더 단계가 실패한 경우에도 텔레그램 발송 자체는 지금처럼 끊김 없이 동작한다.

이 설계는 코스피 브리핑에만 적용된다. `us`·`kospi-close`는 이 카드가 없으므로 `quote_today.json`을 만들지 않고, 그날 텔레그램은 기존 랜덤 폴백을 그대로 쓴다 — 코스피 발송 이후 같은 날 저녁 미국 브리핑 텔레그램에서 오전과 다른 명언이 나올 수 있으나(웹에 명언 카드가 없으니 대조될 화면이 없다), 이는 현재 동작과 동일하므로 회귀가 아니다.

## 에러 처리

| 상황 | 동작 |
| --- | --- |
| `guru_quotes.json` 로드 실패(렌더 단계) | `quote_today.json` 생성 생략 → 웹은 위로 문구만(명언 블록 숨김), 텔레그램은 기존 랜덤 폴백 |
| `quote_today.json`이 오늘 날짜가 아님 | 웹은 명언 블록 숨김, 텔레그램은 랜덤 폴백 |
| 정상 | 웹·텔레그램 동일 명언 표시 |

`comfort_line` 필드 자체(Claude 생성)가 비어 있는 경우는 현재 로직과 동일하게 카드 자체를 렌더하지 않는다(변경 없음).

## 테스트 계획

- `scripts/test_quote_today.py`(신규): quote_today.json 정상 저장·로드, 날짜 불일치 시 폴백, 파일 없을 때 폴백 — 순수함수 단위.
- `send_telegram.pick_quote()`에 대한 기존 테스트가 있으면 함께 갱신(신규 분기 커버).
- 시각 확인: 로컬에서 `generate_html.py --type kospi --date <오늘> --force`로 재생성 후 "이렇게 보는 이유" 섹션이 사라지고 C2 카드가 정확한 위치에 렌더되는지 브라우저로 확인.

## 미결 사항 (구현 계획에서 확정)

- `_overnight_bridge.html`(별도 스펙, 같은 템플릿 파일을 건드림)과의 include 순서 충돌 방지를 위해, 두 스펙을 구현할 때 최종 `kospi.html` 섹션 순서를 한 번에 정리한다. 현재 의도한 순서: `_now_band` → `todays_view`/형식별 블록 → `_us_issues` → `_overnight_bridge`(신규) → `prediction_strip`/`prediction` → **(reasons 제거)** → `_comfort_line`(C2 확장) → `divider` → `domestic_issues` → ...
