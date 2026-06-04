# 산문 텍스트 할루시네이션 검증 설계

**날짜:** 2026-06-04  
**배경:** validate_analysis.py는 픽 종목의 price/change badge를 실측으로 교정하지만,
reasons·scenario·watchpoints 산문 텍스트 안의 % 수치는 교정하지 않는다.
이로 인해 Claude가 실측과 다른 수치를 산문에 삽입해도 발행이 차단되지 않는다.

**트리거 사례:** 2026-06-04 미국 브리핑 — AVGO 실측 -0.49%인데 Claude가
reasons·scenario·watchpoints 세 곳에 "+15.8% 폭등"을 할루시네이션.

---

## 1. 변경 범위

`scripts/validate_analysis.py` 내부에 함수 1개 추가.  
파이프라인 순서·인터페이스 변경 없음. 추가 API 호출 없음.

### 호출 위치

```
enrich_picks_with_realdata()    ← 픽 실측 fetch (기존)
correct_pick_price()            ← badge 교정 (기존)
validate_prose_against_picks()  ← 산문 교차검증 (신규) ← 여기
```

`enrich_picks_with_realdata()` 직후, `call_claude --render` 전에 실행.
픽 실측이 이미 메모리에 적재되어 있으므로 추가 네트워크 비용 없음.

---

## 2. `validate_prose_against_picks()` 설계

### 2-1. 픽 실측 테이블 구성

```python
# enriched_picks: enrich 완료된 stock_picks 리스트
ticker_real: dict[str, float]  # {"AVGO": -0.49, "META": 4.24, ...}
name_real:   dict[str, float]  # {"AVGO (브로드컴)": -0.49, ...}
```

### 2-2. 불일치 판정

```python
def is_contradicted(stated_pct: float, real_pct: float) -> bool:
    diff = abs(stated_pct - real_pct)
    if diff <= 5.0:
        return False                   # 5%p 이내 차이 → 허용
    if abs(real_pct) < 0.5:
        return True                    # 실측 0에 가까우면 diff만으로 판정
    return abs(stated_pct / real_pct) >= 5.0  # 5배 이상 차이
```

임계치 근거:
- **절댓값 5%p:** 프리마켓·장중 데이터 timing 차이 허용
- **배수 5배:** 실측 -0.49% vs 텍스트 +15.8% = 약 32배 → 확실히 포착
- **실측 < 0.5%:** 배수 계산 불안정 구간에서 diff만 사용

### 2-3. 텍스트에서 % 수치 추출

```python
PCT_RE = re.compile(r'([+-]?\d+\.?\d*)\s*%')

def extract_pcts(text: str) -> list[float]:
    return [float(m.group(1)) for m in PCT_RE.finditer(strip_tags(text))]
```

### 2-4. 세 영역 처리

#### reasons 리스트
- 각 reason 문자열에서 픽 ticker/name이 언급되는지 확인
- 언급된 reason에서 % 추출 → is_contradicted() 판정
- 불일치 시: reasons 리스트에서 해당 item 제거
- corrections에 기록

#### 픽 scenario 텍스트
- scenario는 해당 픽 자체를 서술하므로 ticker 언급 없이도 "change claim" 패턴을 검사
- **change claim 패턴:** `전일 +X%` / `단 하루에 +X%` / `+X% 폭등·급등` / `-X% 급락·하락`
  (MA 대비 상회율·목표 수익률·손절선과 구분하기 위해 컨텍스트 키워드 병용)
- change claim 문장의 % 추출 → is_contradicted(stated, pick.real_change_pct) 판정
- 불일치 문장 제거, 나머지 문장으로 scenario 재조합
- 빈 scenario가 되면 경고 기록 (발행은 계속)

#### watchpoints
- 각 watchpoint의 text 필드에서 픽 ticker/name 언급 여부 확인
- % 추출 → is_contradicted() 판정
- 불일치 시: 해당 watchpoint item 전체 제거

### 2-5. REASONS_MIN 가드

제거 후 reasons 개수 < 2이면:
- exit 1
- 관리자 텔레그램 알림: `[검증 실패] reasons 부족 (prose 교정 후 {n}개 남음)`

---

## 3. 적용 대상 briefing type

| type | 적용 여부 | 이유 |
|---|---|---|
| `us` | ✅ | 픽 실측(yfinance) 완전 fetch됨 |
| `kospi` | ✅ | 픽 실측(네이버) 완전 fetch됨 |
| `kospi-close` | ❌ | stock_picks 없음 |

---

## 4. 1회성 감사 스크립트 `scripts/audit_hallucinations.py`

기존 발행 HTML을 소급 스캔해 불일치 항목을 출력한다.

### 동작

1. `web/briefings/**/us/index.html`, `**/kospi/index.html` 순회
2. BeautifulSoup으로 각 픽 카드 파싱:
   - change badge 값 (`.stock-pick-card__change`) → real_pct
   - scenario 텍스트 (`.stock-pick-card__scenario`) → stated pcts
3. is_contradicted() 기준으로 불일치 항목 출력
4. reasons/watchpoints 텍스트도 동일 기준으로 스캔

### 출력 형식

```
[WARN] 2026-06-04/us  AVGO  badge=-0.49%  scenario="+15.80%"  diff=16.29%p
[WARN] 2026-06-04/us  AVGO  reasons[1]="+15.8%"
```

### 결과 활용

출력 리스트를 수동 확인 후 필요한 HTML만 직접 패치.
(오늘 AVGO 케이스는 이미 수동 패치 완료)

---

## 5. 미검증 영역 (향후 과제)

- **spill 텍스트의 tag 필드** (예: `+1.8%`) — 현재 LLM 생성값, 실측 검증 없음
- **premarket_highs change_pct** — 프리마켓 데이터 소스 없어 검증 불가
- **reasons 산문의 미픽 종목** — 픽에 없는 종목(NVDA 등)을 reasons에서 언급 시 실측 없음

---

## 6. 테스트 기준

| 케이스 | 기대 동작 |
|---|---|
| scenario "+15.8%", 실측 -0.49% | 해당 문장 제거, corrections 기록 |
| scenario "+4.2%", 실측 +4.0% | 통과 (5%p 이내) |
| reasons에 "AVGO +15.8% 폭등" | 해당 item 제거 |
| watchpoints에 "AVGO +15.8%" | 해당 watchpoint 제거 |
| 제거 후 reasons 1개 | exit 1 + 알림 |
| reasons에 다른 종목(NVDA) % 언급 | 픽에 NVDA 없으면 통과 (픽 테이블에만 의존) |
