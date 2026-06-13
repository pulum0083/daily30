# 종목 패시브(ETF) 자금 노출도 — 설계

> stock-page-engine(2026-06-10)의 하위 기능. 모든 종목 페이지에 "더블샷만의 숫자"를
> 주입해, AI 픽이 없는 종목도 평범한 시세 페이지로 전락하지 않게 만든다.

## 1. 문제와 가치제안

ETF로 돈이 들어오면 운용사는 구성종목을 비중대로 기계적으로 매수한다. 특정 ETF에
고비중으로 담긴 종목은 펀더멘털과 무관하게 패시브 흐름에 끌려다닌다("tail wags dog").

- **etfnow** 는 ETF→가치(iNAV)를 한다. **이 기능은 종목→패시브 노출**이라 정면충돌이 없다.
- 세 경쟁사(etfnow·excelkospi·raoni) 누구도 "종목별 패시브 노출 집중도"를 다루지 않는다.

**포지셔닝(엄수): 노출도(구조적)만 주장한다. 인과("ETF가 오늘 이 종목을 올렸다")는
주장하지 않는다.** 인과 검증엔 설정/환매(creation/redemption) 실시간 데이터가 필요한데
리테일이 못 구한다. 카피는 "패시브 자금 노출 / 구조적 보유"로만 쓴다.

## 2. 지표

```
passive_value(S)  = Σ( ETF_AUM × 비중 )      종목 S에 연동된 패시브 자금(원)
concentration(S)  = passive_value / 시총       유동시총 대용(전체시총 — 보수적)
days_of_volume(S) = passive_value / ADV20      일평균 거래대금 며칠치
```

핵심 통찰(2026-06-13 실측으로 입증): `passive_value` 절대액으로 줄세우면 삼성전자·
SK하이닉스가 1·2위지만 집중도 2%·거래일수 3~4일로 민감도가 낮다. **두 비율 지표를
AND로 결합**해야 진짜 인질(반도체 소부장 중소형주)이 걸러진다.

## 3. 데이터 소스 (전부 네이버, 무인증 — 2026-06-13 검증 완료)

| 데이터 | 엔드포인트 | 비고 |
| --- | --- | --- |
| ETF 유니버스 | `finance.naver.com/api/sise/etfItemList.nhn` | 1,137개 · `quant`(거래량)로 상위 N 선별 |
| ETF AUM·구성 | `m.stock.naver.com/api/stock/{code}/etfAnalysis` | `marketValue`(AUM) + `etfTop10MajorConstituentAssets` |
| 종목 시총 | `m.stock.naver.com/api/stock/{code}/integration` | `marketValue` |
| 종목 ADV20 | `api.stock.naver.com/chart/domestic/item/{code}/day` | 20거래일 close×volume 평균 |

**구조적 한계: 네이버는 ETF당 TOP10 구성종목만 준다.** 롱테일 비중은 누락(과소집계).
큰 비중은 대부분 TOP10에 잡히므로 타겟(중소형 테마주)엔 영향이 작다. 면책 표기로 해결.

## 4. 임계치 (2026-06-13 스파이크 분포 기준)

상위 60종목 내 분포: concentration p75=4.83% p90=12.09% / days_of_volume p75=5.3 p90=8.8

| 뱃지 | 기준 | 비고 |
| --- | --- | --- |
| 패시브 민감 高 | 거래일수 ≥ 8 **AND** 집중도 ≥ 10% | 이오테크닉스·리노공업·원익IPS·DB하이텍·한미반도체 |
| 中 | 거래일수 ≥ 4 **AND** 집중도 ≥ 5% (高 제외) | 에코프로비엠·에코프로 |
| 미표시 | 그 외 | 대형주 포함 대부분 |

> 운영 시엔 절대값 하드코딩 대신 **매 실행 횡단면 백분위**로 컷을 재계산한다.
> 시장 상황이 바뀌어도 의미가 유지되게. 위 절대값은 day-1 앵커일 뿐이다.

## 5. 파이프라인

`scripts/build_etf_exposure.py` (마감 후 1회, kospi-close job에 부착).

```
1. etfItemList → 거래량 상위 N개 ETF (운영 N=150)
2. 각 ETF → etfAnalysis → AUM + TOP10(코드,비중)
3. 역인덱스: 종목코드 → passive_value, 기여 ETF 리스트
   ※ ETF 코드는 역인덱스에서 제외 (레버리지/TR ETF의 구성종목으로 섞여 들어옴)
4. passive_value 상위 K종목만 시총·ADV20 보강 (낮은 노출은 민감주 불가)
5. 백분위 컷으로 뱃지 분류
6. 산출: data/etf_exposure.json → 종목 페이지 생성 시 스냅샷 커밋(오염방지 패턴)
```

호출량 ≈ 150(ETF) + 2×K(종목) ≈ 270건/일.

## 6. 산출 스키마

```json
{
  "generated_at": "...+09:00",
  "coverage": { "etf_count": 150, "note": "주요 ETF TOP10 기준, 소수 비중 누락 가능" },
  "thresholds": { "high": {...}, "mid": {...} },
  "stocks": {
    "247540": {
      "passive_value_krw": 889500000000,
      "mcap_krw": 16631200000000,
      "concentration_pct": 5.3,
      "days_of_volume": 6.1,
      "badge": "mid",
      "top_etfs": [ {"code","name","weight_pct","contrib_krw"} ]
    }
  }
}
```

## 7. UI — 두 surface (히어로 + 서포트)

**히어로 — "패시브 민감주" destination (검색 유입 입구)**
- 독립 랭킹 페이지. 기본 정렬 = **거래일수**(가장 직관적: "ETF가 N일치 보유"). 토글: 거래일수 / 집중도 / 민감도(복합 0~100).
- 상단 "섹터 쏠림" 배너 = 개별 나열을 시장 읽기로 전환("지금 패시브 돈은 반도체 소부장").
- 행 클릭 → 종목 페이지. 명명된 개념 "패시브 민감주"로 롱테일 검색어 선점. (etfnow 전략의 열린 검색 루프 기여 자산)

**서포트 — 종목 페이지 위젯**
- 한 줄 번역 + 비율 2개(시총 대비 %, 거래일수) + 끌고 가는 ETF top 5(`비중 × AUM` 순) + 중립 띠.

**프로토타입 내 위치 (flow-clickable.html 기준)**
- destination 프리뷰 블록: 홈 종목 상승/하락 톱 **다음, `etf-divider` 직전**. 종목↔ETF의 개념적 경첩 자리. "패시브 민감주 톱5 + 전체 →"(거래량 톱 블록과 같은 패턴).
- 전체 페이지: `#ranking`과 같은 구조의 전용 스크린.
- 위젯: `#detail` 사이드바 "이 종목을 담은 ETF"(PHASE 2 더미) 패널 대체.
- (선택) 홈 HOT 카드 "ETF 등락 TOP" → "패시브 민감주"로 교체(더 차별적).

**카피 규칙: 인과 금지. 노출도/구조적 보유로만.**

## 8. 규칙 준수

- **SERVICE_RULES 0번(실측만)**: passive_value는 실측 AUM × 실측 비중의 계산값.
  LLM 생성·보간이 아니다. 위반 아님.
- 유동주식 데이터 부재 → 전체 시총을 분모로(과소평가 = 거짓경보 없음, 보수적).

## 9. 범위 절단

- **v1**: 파이프라인(역링크·passive_value·days_of_volume·백분위 뱃지) + **"패시브 민감주" destination(기본 정렬 거래일수)** 히어로 + 종목 위젯 서포트. ETF 상위 150.
- **v2**: 지수 정기변경 편입/편출 캘린더(KRX 별도, 가장 트레이더블).
- **안 함**: TOP10 초과 전체 구성종목, iNAV(etfnow 영역).

## 10. 오픈 이슈

1. 유효 ETF 85/120 (채권·해외·파생형은 TOP10 구조가 달라 제외됨 — 정상).
2. ADV/시총 보강을 상위 K로 제한 → K 경계 근처 종목 누락 가능. K=80 권장.
3. 백분위 모집단 정의: "passive_value 상위 K" 내 분포 vs 전체. 현재 전자. 일관 유지.
