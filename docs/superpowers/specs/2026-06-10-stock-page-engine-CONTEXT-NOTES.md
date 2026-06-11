# 종목 페이지 엔진 — 이어가기 노트 (Context Notes)

> 다른 세션·다른 컴퓨터에서 이 작업을 이어받을 때 **이 파일부터 읽으세요.**
> 마지막 갱신: 2026-06-11

## 한 줄 요약

ETFNow식 검색 유입 전략을 더블샷에 이식하는 **종목 페이지 엔진** 기획 중. 현재 **브레인스토밍/목업 단계 완료 직전**, 아직 코드 구현 전. 다음은 랭킹 전체 페이지 목업(선택) → 기획 확정 → 구현 계획(writing-plans).

## 어디서 이어받나

```bash
git fetch origin
git checkout feature/stock-page-engine
git pull
```

그다음 읽을 순서.
1. **설계 스펙** — `docs/superpowers/specs/2026-06-10-stock-page-engine-design.md` (전체 설계·데이터·산식·화면)
2. **목업** — `docs/superpowers/specs/mockups/` 의 HTML을 브라우저로 열기. 특히 `flow-clickable.html`(클릭 동선 통합 프로토타입)부터.

> 비주얼 브레인스토밍을 이어가려면 superpowers brainstorming의 companion 서버를 다시 띄우면 됨. 기존 `.superpowers/`는 gitignore라 안 따라옴(중요 목업은 mockups/에 복사됨).

## 확정된 결정 (요약 — 상세는 스펙)

- **포지셔닝**: 종목 서비스가 메인, 브리핑은 보조. **홈(`/`) = `/stocks` 허브.** 기존 랜딩은 나중에 정리.
- **구현 위치**: 이 저장소 안. 새 폴더만 분리(`web/stocks/`, `scripts/templates/stocks/`). 외부 레포 분리 안 함.
- **범위**: Phase 1 = 종목 페이지(기존 데이터). Phase 2 = ETF 역인덱스·조합. Phase 3 = 종목별 적중률 표시(Phase 1부터 기록만).
- **유니버스**: `data/stock_universe.json` 레지스트리 누적 + 일별 토스 candles 갱신.
- **2티어 AI 상승확률**: 티어1 Claude 예측(픽) `AI 78` / 티어2 기술신호 점수(전 종목) `신호 64`. 산식은 스펙 참조. 극단값 안 만듦(YMYL).
- **레이아웃**: 더블샷 2단 재사용. 종목 페이지만 사이드바 360 + 메인 2분할. **홈은 C 하이브리드** — 거래량 톱 풀폭(대표) → 상승·하락 2단 → ETF 2단. (세로 풀폭 스택에서 변경, 2026-06-11.)
- **ETF 블록**: 홈에 ETF 거래량 톱 + ETF 상승 톱 추가. ETF도 6자리 코드라 토스 candles로 시세·기술신호 산출 가능. 단 Claude 픽(`AI 78`)은 개별 종목 전용 → **ETF는 `신호`만**(헤더에 "AI 픽 미적용·신호만"). "거래량 상위 ETF" 검색어 흡수 + ETFNow 영역 잠식. Phase 1.5(역인덱스보다 단순).
- **화면**: 홈 허브 / 종목 상세 / 섹터 페이지 / 검색 오버레이 / 랭킹 전체(`/stocks/volume·gainers·losers`).

## 완료된 것

- [x] 설계 스펙 작성·커밋 (Phase 1 + 프로토타입 확정 + 하이브리드 랭킹 산식)
- [x] 목업 6종: home, stock-detail, sector, search-overlay, hybrid-ranking, flow-clickable
- [x] IA·GNB 탭·라우트·진입경로 정의
- [x] AI 뱃지 hover 툴팁(2티어 의미 설명)

## 다음 단계 (남은 일)

1. (선택) **랭킹 전체 페이지 목업** — `/stocks/volume` 등. 전 종목 + 섹터 필터 + 페이지네이션. 만들면 화면 세트 완성.
2. **기획 최종 확정** — 사용자 스펙 리뷰.
3. **writing-plans** — 구현 계획(checklist + 단계별). 사용자가 "모든 기획 정리 후 진행" 요청함. 아직 코드 구현 시작 안 함.
4. 구현 착수 시 검증 기준은 스펙 "검증 기준" 5가지 참조.

## 주의 / 함정

- **데이터 정합성(SERVICE_RULES §0)**: 모든 수치는 실측. 국내 종목은 6자리 코드만(`.KS`/`.KQ` 금지). LLM 생성 숫자 금지.
- 픽은 `name`만 있고 코드 없을 수 있음 → name↔ticker 역매핑, 실패 시 페이지 미생성.
- `/chips`는 별도 배포(chipboard.vercel.app) 프록시 — 이 레포 아님. 종목 엔진은 반대로 레포 내부 구현(데이터가 여기 있음).
- 텔레그램 ad-hoc 발송 금지(스케줄 외).

## 브랜치 / 커밋

- 브랜치: `feature/stock-page-engine` (origin에 푸시됨)
- 주요 커밋: 설계 스펙 → 프로토타입 확정 → 2티어 산식 → 홈/섹터/검색/플로우 목업
- PR 미생성 (구현 시작 시 생성 예정)
