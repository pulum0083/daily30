# 이어받기 프롬프트 — 시장의 큰 흐름(국면) 섹션

다른 컴퓨터에서 아래 블록을 통째로 복사해 Claude Code에 붙여넣으세요.

---

```
double-shot 저장소에서 "시장의 큰 흐름(국면)" 섹션 구현을 이어서 진행해줘.

## 먼저 할 것

git fetch origin
git checkout feat/market-regime-section
git pull

## 읽어야 할 문서 (순서대로)

1. docs/superpowers/specs/2026-08-07-market-regime-section-design.md  ← 설계 스펙
2. docs/superpowers/plans/2026-08-07-market-regime-section.md         ← 구현 계획 (14 태스크)

## 지금까지 진행 상황

Task 1~9 완료, Task 10~14 남음.

완료된 것:
- scripts/config/regime_baskets.json — 바스켓 7개 (글로벌 5 + 한국 2)
- scripts/market_regime_core.py — 순수 계산 모듈 (네트워크 없음), 함수 9개
- scripts/test_market_regime_core.py — 단위 테스트 35건
- scripts/build_market_regime.py — 수집부만 (load_config, fetch_daily_closes, fetch_all)
- web/data/regime-backtest-fixture.json — 티커 22개 실데이터 (2024-08 ~ 2026-08)
- scripts/test_market_regime_backtest.py — 375영업일 리플레이 회귀 4건

현재 상태 확인:
  python3 -m pytest scripts/test_market_regime_core.py scripts/test_market_regime_backtest.py -q
  → 39 passed 가 나와야 정상

## 남은 태스크

Task 10: JSON 빌더 완성 (build_market_regime.py에 build()/main() 추가 → web/data/market-regime.json)
Task 11: 프런트 마크업 + regimeRender() + 신선도 가드 + 프런트 테스트 6건
Task 12: CSS와 반응형 + 캐시버스터
Task 13: 워크플로 연결 (daily_report.yml 마감 잡)
Task 14: 전체 검증

각 태스크의 전체 코드와 명령은 계획 문서에 그대로 있음.

## 진행 방식

superpowers:subagent-driven-development 스킬로 진행해줘.
태스크마다: 구현 서브에이전트 → 스펙 준수 리뷰 → 코드 품질 리뷰 → 다음 태스크.
리뷰에서 나온 지적은 같은 구현 에이전트에게 되돌려 고치게 하고,
고친 내용은 네가 직접 재현해서 확인한 뒤 넘어가.

## 이 환경에서 반드시 알아야 할 함정 2가지

### 1. macOS 파이썬 바이트코드 캐시 (중요)

이 맥의 시스템 python3는 바이트코드를 저장소 안 __pycache__가 아니라
~/Library/Caches/com.apple.python/<절대경로>/ 에 캐싱한다.

증상: 소스를 고쳤는데 옛 동작이 나온다. inspect.getsource()는 새 소스를 보여주는데
실제 실행 결과가 다르다. scripts/__pycache__를 지워도 안 고쳐지고, python3 -B도 소용없다
(-B는 쓰기만 막고 읽기는 막지 않음).

진단: python3 -c "import sys;sys.path.insert(0,'scripts');import market_regime_core as M;print(M.__cached__)"

해결:
  rm -rf "$HOME/Library/Caches/com.apple.python$(pwd)/scripts"

파일을 바꿔치기하는 실험(뮤테이션 테스트, cp로 원복)을 할 때마다 이걸 지워야 한다.
안 지우면 몇 십 분을 헛다리 짚는다. 실제로 그랬다.

### 2. 임계값을 임의로 바꾸지 말 것

COOL_THRESHOLD(-15), HIGH_THRESHOLD(-3), HYST_WINDOW(5), HYST_MIN(3), MIN_RUN(10)은
375영업일 백테스트로 고른 값이다. 초기 설계(히스테리시스 없음)는 전환이 75회 나서
평균 5일마다 카드가 깜빡였고, 지금 설정으로 4회까지 줄였다.

백테스트가 실패하면 임계값을 조정하지 말고, 어느 기준이 어떻게 깨졌는지 실제 수치를
뽑아서 원인을 먼저 찾을 것.

## 설계에서 절대 바꾸면 안 되는 것

- LLM을 쓰지 않는다. 헤드라인은 계산값 두 개로 템플릿을 채운다.
- 한국 바스켓은 헤드라인 주어가 될 수 없다 (read-through 줄 전용).
  진폭이 커서 넣으면 5개 국면 전부 주어가 "한국 반도체"가 된다.
- 헤드라인 슬롯 C(lead 상태의 주어)는 신고점 집합이 아니라 글로벌 5개 전체에서
  누적 1위를 고른다. 신고점으로 좁히면 누적 +12%짜리가 +214%짜리를 제치고
  "주도"로 불린다 (백테스트에서 실제로 발생, bcdb97f2에서 수정).
- web/data/regime-backtest-fixture.json은 절대 재생성하지 말 것.
  회귀 테스트가 특정 날짜(2026-05-15, 07-24, 08-06)에 묶여 있다.
- 기준일 표기에 .ds-asof를 쓰지 말 것. 이 데이터는 하루 1회 스냅샷인데
  .ds-asof는 장중에 "오늘 실시간"으로 바뀌어 없는 갱신을 광고하게 된다.

## 백테스트가 지금 내놓는 국면 (참고 — 바뀌면 안 됨)

2025-02-07~2025-06-04  none  뚜렷한 주도주가 없어요
2025-06-05~2026-02-05  lead  메모리 반도체 주도가 이어지고 있어요
2026-02-06~2026-04-09  swap  주도주가 AI 인프라에서 가치 경기민감으로 넘어가는 중이에요
2026-04-10~2026-06-23  lead  메모리 반도체 주도가 이어지고 있어요
2026-06-24~2026-08-06  swap  주도주가 메모리 반도체에서 AI 인프라, 가치 경기민감으로 넘어가는 중이에요

전환 4회, 문구 실패 0건, 한국 바스켓 등장 0건.
```

---

## 참고 — 커밋 이력 (feat/market-regime-section)

```
bcdb97f2  fix   헤드라인 lead 주어를 글로벌 전체 누적 1위로 (스펙 슬롯 C 일치)
858692b7  docs  계획의 픽스처 기대 티커 수 오기 수정 (19 → 22)
606f90d3  feat  국면 수집부 + 백테스트 픽스처
259d7c0c  fix   뒤로걷기 회귀 가드 추가, raw 재사용
7c29092c  feat  국면 단위 문구 확정
8119244c  fix   빈 바스켓 이름이 문장을 깨뜨리는 것 방지
12b5332b  feat  조사 분기·헤드라인 템플릿
d1af70e2  feat  짧은 국면 흡수
d13c70bc  fix   qualifying_sets 범위 밖 i를 거부
d23dee80  feat  히스테리시스를 판정 입력에 적용
1f40521d  fix   길이불일치·NaN 거부, 이중반올림 제거
f83e1cd7  feat  러닝 정점 대비 거리·플래그
8a369076  fix   빈 창·NaN 종가를 결측으로 처리
cada6a02  feat  바스켓 누적수익률·결측 처리
66df24c6  feat  바스켓 설정 추가
863f01a4  docs  구현 계획
833453b5  docs  디자인 스펙
```

`feat` 커밋마다 뒤따르는 `fix` 커밋은 코드 리뷰에서 잡힌 실제 버그다. 리뷰 단계를
건너뛰면 이 버그들이 그대로 남는다는 뜻이니, 이어받을 때도 리뷰를 생략하지 말 것.
