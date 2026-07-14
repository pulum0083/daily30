# US 브리핑 "오늘의 관점" 배경색 톤 신호

날짜: 2026-07-15

## 목적

코스피 오전 브리핑의 "오늘의 관점"(`tv-lead`) 카드는 예측 방향에 따라 배경색이 바뀐다(상승=붉은 계열, 하락/기본=파란 계열). US 브리핑은 최근 이슈 중심 구조로 재정의되며 `prediction` 필드(방향·확률)를 완전히 제거했지만(2026-07-14, 예측 정확도 채점 탈퇴), 시각적 톤 신호까지 없앨 필요는 없다는 것이 이번 요청의 배경이다.

US "오늘의 관점" 카드에도 동일한 배경색 동기화를 적용하되:
- **숫자·확률은 어디에도 노출하지 않는다.** 색상만으로 톤을 전달한다.
- **채점하지 않는다.** `check_accuracy.py`·`data/briefings.json` 등 정확도 추적 대상에 포함하지 않는다.
- **텔레그램에는 적용하지 않는다.** 텔레그램 메시지는 순수 텍스트로 유지한다(Telegram Bot API의 HTML 서브셋은 배경색 스타일을 지원하지 않는다).

## 신호 소스

새 계산 로직을 만들지 않는다. `scripts/leading_signal.py`의 `compute_prior_us(latest)`를 재사용한다 — 프리마켓 선물(S&P·나스닥·다우)·SOX·VIX 등 **실측 시장 데이터**로 방향을 결정론적으로 계산하는 함수로, 현재는 `call_claude.py`가 Claude 프롬프트에 참고용(advisory)으로만 주입하고 있다.

이 함수가 반환하는 `direction`은 `"상승"` / `"하락"` / `"중립"` 세 값 중 하나다:
- 실측 데이터 기반 결정론적 계산이므로 **운영 규칙 0(화면에 표시되는 모든 수치는 실측이어야 한다)**에 위배되지 않는다 — 다만 이번 기능에서는 수치 자체를 표시하지 않고 CSS 클래스 선택에만 쓴다.
- LLM이 생성하는 값이 아니다.

## 계산 시점

`scripts/generate_html.py`가 US 페이지를 렌더링할 때(`--type us` 컨텍스트 빌드 단계), 이미 인자로 받은 `latest`(= `data/latest_us.json`, `validate_analysis.py`의 픽 실측 교정까지 반영된 최신본) 딕셔너리를 그대로 `compute_prior_us(latest)`에 넘겨 재계산한다.

- `call_claude.py --no-html` 단계에서도 동일 함수가 호출되지만 그 결과는 프롬프트 주입용으로 휘발되고 저장되지 않는다. 렌더 단계에서 별도로 재계산하는 이유는 두 단계가 별도 프로세스 호출이라 상태를 공유하지 않기 때문이다.
- 입력 신호(프리마켓 선물·SOX·VIX)는 `validate_analysis.py`가 건드리는 대상(개별 종목 픽)과 겹치지 않으므로, `--no-html` 단계와 렌더 단계 사이에 이 계산 결과가 달라질 일은 없다(둘 다 동일한 매크로 데이터를 참조).

## 매핑 규칙

| `compute_prior_us().direction` | CSS 클래스 | 배경 |
|---|---|---|
| `"상승"` | `up` | 기존 `--up-bg`(붉은 계열) 재사용 |
| `"하락"` | `dn` | 신규 — 기존 `.tv-lead` 기본값과 별도로 명시적 규칙 추가(파란 계열, `--dn-bg` 재사용) |
| `"중립"` | `neutral` | 신규 — 회색 계열, 기존 `--surface-inset`·`--muted` 토큰 재사용(새 색상 변수 안 만듦) |

코스피의 기존 `dir_cls` 계산(`build_prediction()`, `analysis.prediction.direction` 기반)은 **변경하지 않는다** — 코스피는 계속 up/기본값(파란) 2단 체계를 그대로 쓴다. `.tv-lead.dn`·`.tv-lead.neutral` CSS 규칙을 새로 추가해도 코스피 쪽 `dir_cls`가 절대 `"dn"`/`"neutral"` 문자열을 만들지 않으므로 코스피 렌더링에는 영향이 없다.

## 적용 범위

`scripts/templates/sections/todays_view.html`의 `.tv-lead {{ dir_cls }}` 클래스 하나. 이 템플릿은 코스피·US 공용이라 **템플릿 자체는 수정하지 않는다** — CSS 규칙 추가 + `generate_html.py`의 US 컨텍스트 빌드 함수에서 `dir_cls` 값을 새로 계산해 넘기기만 하면 된다.

이슈 카드(`_issues.html`)·픽 카드 등 다른 섹션에는 이번 톤 신호를 적용하지 않는다(요청 범위 밖).

## 변경 파일

1. **`web/assets/style.css`**
   - `.tv-lead.dn { background: linear-gradient(180deg, var(--dn-bg), transparent 70%); border-color: var(--dn-bg); }` + `.tv-lead.dn .tv-kicker { color: var(--dn); }`
   - `.tv-lead.neutral { background: linear-gradient(180deg, var(--surface-inset), transparent 70%); border-color: var(--surface-inset); }` + `.tv-lead.neutral .tv-kicker { color: var(--muted); }`
   - 라이트/다크 테마 모두 기존 토큰(`--dn`, `--dn-bg`, `--surface-inset`, `--muted`)을 재사용하므로 테마별 별도 값 정의 불필요.

2. **`scripts/generate_html.py`**
   - US 컨텍스트 빌드 함수(현재 `ctx["todays_view"] = analysis.get("todays_view")`가 있는 지점, `us` 분기)에 다음을 추가:
     ```python
     from leading_signal import compute_prior_us
     prior = compute_prior_us(latest)
     _dir_map = {"상승": "up", "하락": "dn", "중립": "neutral"}
     ctx["dir_cls"] = _dir_map.get(prior["direction"], "neutral")
     ```
   - `latest`는 US 컨텍스트 빌드 함수가 이미 인자로 받고 있는 딕셔너리(= `--data-file` 로드 결과)를 그대로 사용한다.

## 테스트 계획

- `compute_prior_us()`가 이미 `scripts/test_*` 스타일 단위 테스트로 커버되어 있는지 확인하고, 없다면 direction→dir_cls 매핑 3가지(상승/하락/중립) 케이스만 가벼운 단위 테스트로 추가.
- 렌더 후 `web/briefings/{date}/us/index.html`에서 `class="open-section tv-lead {up|dn|neutral}"`이 실제로 찍히는지 grep으로 확인.
- 브라우저에서 세 가지 케이스(latest_us.json의 선물·SOX·VIX 값을 임시로 바꿔가며) 시각 확인 — 라이트/다크 테마 모두.
- 코스피 페이지 렌더링 결과가 이번 변경 전후로 동일한지(회귀 없음) 확인.

## 범위 밖

- 이슈 카드·픽 카드 등 다른 섹션 색상 동기화.
- 텔레그램 메시지 색상 표기(플랫폼 미지원, 요청에서도 제외 확정).
- `check_accuracy.py`·`data/briefings.json` 연동(요청에서 명시적으로 제외).
- 코스피 쪽 `dir_cls` 계산 로직 변경.
