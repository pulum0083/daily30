#!/usr/bin/env python3
# Gemini Google Search grounding으로 최신 시장 뉴스를 수집·요약하는 스크립트

"""
흐름:
  Gemini 2.5 Flash (google_search grounding) → 그 시점 Google 검색 기반 최신 뉴스 수집·요약
  → data/news_summary_{type}.json 저장

Usage:
    python3 scripts/fetch_news.py --type kospi
    python3 scripts/fetch_news.py --type us
    python3 scripts/fetch_news.py --type kospi-close
"""
from __future__ import annotations  # `X | None` 어노테이션을 구버전 파이썬(로컬 3.9)에서도 허용

import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytz

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

KST = pytz.timezone("Asia/Seoul")


# ─────────────────────────────────────────────────────────────────────────────
# Gemini API
# ─────────────────────────────────────────────────────────────────────────────

def get_gemini_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        config_file = BASE_DIR / "config.json"
        if config_file.exists():
            with open(config_file, encoding="utf-8") as f:
                cfg = json.load(f)
            key = cfg.get("gemini", {}).get("api_key", "")
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY not set. "
            "Set the environment variable or add gemini.api_key to config.json"
        )
    return key


# ─────────────────────────────────────────────────────────────────────────────
# 검색 시점 기준 (코스피 아침 브리핑)
# ─────────────────────────────────────────────────────────────────────────────

_WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]


def _kospi_session_window(today: date) -> tuple:
    """코스피 아침 브리핑의 '검색 대상 구간' 지시문과 직전 미국장 라벨을 만든다.

    프롬프트에 "어제 미국장"·"간밤"을 상수로 박아두면 **월요일과 휴일 다음날에 틀린다**
    (§24 실사고). 그때 직전 미국장은 지난 금요일 이전이고, 그 사이 주말에 벌어진 일은
    검색 지시에 아예 존재하지 않아 통째로 누락된다.
    직전 거래일을 실제로 계산해 창을 명시하고, 주말이 낀 날에는 주말 이벤트를 함께 찾게 한다.

    Returns: (session_window 블록, us_label)
    """
    try:
        from session_label import prev_us_session, prev_kospi_session, us_session_label
        prev_us = prev_us_session(today)
        prev_kospi = prev_kospi_session(today)
        us_label = us_session_label(today)
    except Exception as e:  # 달력 의존성 문제 등 — 기존 동작으로 폴백(수집 자체는 막지 않는다)
        print(f"[fetch_news] session_label 사용 불가, 기본 라벨 사용: {e}", file=sys.stderr)
        return "", "어제"

    def stamp(d):
        return f"{d}({_WEEKDAY_KO[d.weekday()]}요일)" if d else "확인 불가"

    gap_days = (today - prev_us).days if prev_us else 1
    lines = [
        "",
        "[시점 기준 — 반드시 지켜라]",
        f"- 오늘은 {stamp(today)}이고, 이 브리핑은 KST 07:25경에 만들어진다. 코스피 개장은 09:00이다.",
        f"- 직전 미국장은 {stamp(prev_us)}이다. 한국어로 \"{us_label}\"이라 부른다.",
        f"- 직전 코스피 거래일은 {stamp(prev_kospi)}이다.",
        f"- **검색 대상 구간: {stamp(prev_us)} 미국장 마감 이후부터 지금까지다.**"
        " 이 구간에 실제로 벌어진 일만 담는다. 그 이전 사건은 이미 지난 브리핑에서 다뤘으므로"
        " 새 이슈로 쓰지 않는다.",
    ]
    if us_label != "간밤":
        lines.append(
            f"- 직전 미국장이 어제가 아니다(공백 {gap_days}일). **이 날의 미국장을 '간밤'·'어젯밤'·'밤사이'라고"
            f" 쓰지 마라 — \"{us_label}\"로 쓴다.**"
        )
        lines.append(
            "- **이 구간에는 주말·휴일이 포함된다. 미국 증시가 닫혀 있었다고 뉴스가 없는 게 아니다.**"
            " 그 사이 열린 글로벌 테크·산업 컨퍼런스와 거기서 나온 발언(AI 서밋·개발자 콘퍼런스·산업 전시회 등),"
            " 정책·규제 발표, 지정학 이벤트, 기업 발표, 주요 인사 발언을 **반드시 함께 검색한다.**"
            " 휴장 다음 첫 거래일의 코스피는 이 공백 구간에 쌓인 재료를 한꺼번에 반영한다."
        )
    lines.append("")
    return "\n".join(lines), us_label


# ─────────────────────────────────────────────────────────────────────────────
# 브리핑 타입별 검색·요약 프롬프트
# ─────────────────────────────────────────────────────────────────────────────

KOSPI_PROMPT = """\
오늘({today}) 한국 코스피 시장 예측에 필요한 최신 뉴스를 Google Search로 검색해 분석해줘.
{session_window}
검색할 내용:
- {us_label}(현지 시각) 미국 나스닥·S&P500 등락 원인과 수치
- 오늘 코스피 개장에 영향을 줄 외국인 수급·ETF 자금 흐름
- 오늘 예정된 주요 경제 지표 또는 이벤트 (FOMC, CPI 등)
- 반도체·기술주 관련 최신 이슈 (NVDA, TSMC 등)
- 원유·환율 최신 동향
- **주도주 기업 이벤트**: 코스피 대형주(삼성전자·SK하이닉스·현대차 등)의 상장·ADR·M&A·지분매각·신사업 진출·대형 수주·설비투자·실적 발표
- **[상시 룰·최우선] {us_label} 미국 빅테크 실적은 코스피 대장주와 직결되므로 반드시 주요하게 다룬다.** 빅테크(구글·MS·아마존·메타·엔비디아 등)의 **AI 설비투자(capex) 성장률**이 곧 메모리·HBM 수요의 선행지표다 — capex가 늘면 삼성전자·SK하이닉스 HBM 수요 기대가 커지고(코스피 상승 압력), **capex 성장률이 꺾이면 메모리 수요 둔화 우려로 대장주·코스피 하락으로 직결된다.** 따라서 빅테크 실적일엔 실적·클라우드 성장률·**capex 규모와 증감 방향**을 핵심 촉매로 최우선 검색·수집하고, 삼성전자·SK하이닉스 read-through를 반드시 함께 정리한다.
- **[상시 룰] {us_label} 미국 빅테크 '실적 발표' — 이미 발표됐으면 '예정'이 아니라 '결과'를 담는다.** 미국 대형주 실적은 통상 미 증시 마감 후(= 직전 미국장 마감 직후 KST 새벽)에 나오므로, 코스피 아침 브리핑 시점엔 **이미 발표가 끝나 실제 결과가 공개된 경우가 대부분**이다. 이럴 때 "실적 발표 예정"·"오늘 밤 발표" 같은 **프리뷰(발표 전) 프레이밍 기사에 속지 말고**, 반드시 **실제 발표된 결과 기사**를 찾아 수치와 함께 담는다 — 매출·전년비 증감률, 클라우드/데이터센터 매출 성장률, **설비투자(capex) 규모·연간 가이던스**, 그리고 **발표 후 시간외/프리마켓 주가 반응**까지. 이 결과(특히 AI capex·클라우드 성장)가 한국 반도체·HBM(삼성전자·SK하이닉스) 수요 기대에 주는 파급(read-through)을 함께 정리한다. 아직 발표 전(장 마감 후 콜만 예정 등)이면 그때만 '예정'으로 표기하고 결과 수치를 지어내지 않는다(운영 규칙 0). **[임시 2026-07-22, 실적 시즌 종료 시 이 종목 예시만 제거]** 현재 진행 중인 빅테크 실적 시즌(구글/알파벳 등)을 명시적으로 검색한다.
- **인과 촉매**: 특정 섹터/주도주 등락의 '원인'이 된 사건 — 특히 미국 빅테크 전략 뉴스(클라우드·자체 칩 설계·감산·투자)가 한국 반도체·2차전지에 미치는 파급(read-through)
- **AI 모델 개발사 이슈(비상장이지만 핵심 촉매)**: OpenAI·Anthropic의 신모델 출시, 대형 칩·HBM·클라우드 계약, 대규모 투자·펀딩 — 이런 AI 인프라 수요 신호가 SK하이닉스·삼성전자 HBM·반도체 투자심리에 미치는 파급

[국내 트랙 — 위 미국발 이슈와 **별개로 반드시 함께 검색한다**]
아래는 코스피 자체 재료다. **미국 뉴스만으로 브리핑을 채우지 마라.** 한국 투자자가 보는 화면이므로
국내에서 벌어진 일이 최소한 미국 이슈만큼은 담겨야 한다.
- **통화·정책**: 한국은행 금통위 결정·총재 발언, 국내 시장금리·국고채, 정부의 증시·산업 정책, 세제·규제 변경(금투세·배당·공매도 등)
- **거시 지표**: 수출입 실적(특히 **반도체 수출 증감률**)·무역수지, 산업활동·물가 등 오늘 발표되거나 직전에 발표된 국내 지표
- **기업 공시·이벤트**: 코스피·코스닥 상장사의 실적·잠정 공시, 유상증자, 자사주 매입·소각, 대형 수주, 합병·분할, 신규 상장(IPO)
- **수급**: 외국인뿐 아니라 **기관·개인** 매매 동향과 그 배경, 프로그램 매매·선물 수급
- **테마·섹터**: 오늘 국내에서 부각될 테마(정책 수혜·업황 반전 등)와 그것을 촉발한 사건
- **지정학·대외**: 한반도 정세, 통상·관세 등 한국 증시에 직접 영향을 주는 이슈

[key_indicators 작성 규칙]
- 반드시 실제 수치(%, 금액)를 포함한다
- 오늘 코스피에 직접 영향을 줄 이슈만 포함한다
- **5개 중 최소 2개는 국내 트랙 항목으로 채운다.** 국내 재료를 실제로 못 찾았으면 그 슬롯을 비우고
  배열을 짧게 낸다 — **미국 이슈로 대신 채우지 않는다.**
- 포함 금지: YTD 수익률, 연간 상승률, 애널리스트 중장기 전망
- **포함 금지: "확인되지 않았습니다"·"관련 뉴스가 없습니다" 같은 검색 실패 보고.**
  그건 이슈가 아니다. 못 찾았으면 그 항목을 배열에서 빼라(빈 배열도 허용).

[catalysts 작성 규칙]
- 오늘 코스피 주도주·섹터를 움직일 '사건' 중심 뉴스만 담는다 (지수 등락률 나열이 아님)
- **해외 사건뿐 아니라 국내 사건도 담는다** — 공시·수주·정책·지표 발표가 국내 종목·섹터를 움직인 경우
- **각 항목은 반드시 `{{"date": "YYYY-MM-DD", "text": "사건 → 영향"}}` 형태의 객체다** (문자열이 아니다).
  `date`는 그 사건이 실제 발생·발표된 날짜로, 검색으로 확인한 실제 날짜만 넣고 추측하지 않는다.
  `text`는 "무슨 사건 → 어느 종목·섹터에 왜 영향" 한 문장.
- **`date`는 위 [시점 기준]의 검색 대상 구간 안에 있어야 한다.** 그 구간보다 앞선 사건은 이미 지난 브리핑에서
  다뤘으므로 담지 않는다(오늘 후속 기사가 검색되더라도 마찬가지).
- 실제로 검색된 사건만 담고, 없으면 빈 배열 []
- **[필수] 모든 항목의 주어는 실제 기업·기관 실명이어야 한다.** 이름을 특정하지 못했다면 "A사"·"B사"·"모 기업"처럼
  익명화하거나 아래 예시의 대괄호 슬롯을 그대로 남기지 말고, **그 항목을 통째로 버린다.** 실명 없는 사건은
  검증이 불가능해 발행할 수 없다. 남는 게 없으면 빈 배열 []로 둔다 — 완전성보다 정합성이 우선이다.
- 문장 형태 예시(회사명·사건은 형식 참고용일 뿐이다 — 절대 그대로 베끼지 말고, 오늘 실제 검색으로 찾은 회사명·사건·수치로만 채운다): "[해외 기업]의 [발표·이벤트] → [한국 관련 섹터·종목]에 [영향 방향]"

출력 형식 (JSON만, 다른 텍스트 없이):
{{
  "key_indicators": [
    "(1) {us_label} 미국 증시 관련 구체적 이슈 (수치 포함)",
    "(2) 반도체·기술주 이슈",
    "(3) 국내 정책·지표·공시·수급 중 실제로 검색된 것 (수치 포함)",
    "(4) 위와 다른 국내 소재 (수치 포함)",
    "(5) 원유·환율 동향"
  ],
  "catalysts": [
    {{"date": "YYYY-MM-DD", "text": "주도주·섹터를 움직인 사건 → 영향 (실제 검색된 것만·검색 대상 구간 내 발생분만, 없으면 이 배열은 비운다)"}}
  ],
  "headlines": [
    "오늘 코스피 방향에 직접 영향을 줄 헤드라인 1",
    "헤드라인 2",
    "헤드라인 3"
  ],
  "market_sentiment": "bullish or bearish or neutral"
}}

위 예시의 괄호 번호·설명 문구는 **무엇을 담을지 알려주는 안내일 뿐**이다. 실제 출력에는 번호도
설명 문구도 남기지 말고, 검색으로 확인한 사실만 한 문장씩 적는다. 못 찾은 슬롯은 안내 문구를
그대로 두거나 지어내지 말고 **배열에서 빼서 짧게 낸다**.
"""

KOSPI_CLOSE_PROMPT = """\
오늘({today}) 한국 코스피 마감 시황 분석에 필요한 최신 뉴스를 Google Search로 검색해 분석해줘.

검색할 내용:
- 오늘 코스피 마감 지수와 주요 등락 원인
- 오늘 외국인·기관 수급 동향
- 오늘 장중 급등락 섹터 및 종목 원인
- 오늘 발표된 경제 지표·정책·규제 이슈

[key_indicators 작성 규칙]
- 오늘 장중 실제 발생한 이슈만 포함한다
- 반드시 수치(%, 금액)를 포함한다
- 포함 금지: 중장기 전망, 애널리스트 목표가, 연간 수익률

출력 형식 (JSON만, 다른 텍스트 없이):
{{
  "key_indicators": [
    "오늘 코스피 등락 관련 핵심 이슈 (수치 포함)",
    "섹터별 이슈 (반도체·바이오·2차전지 등)",
    "외국인·기관 수급 관련 뉴스",
    "정책·규제·실적 이슈"
  ],
  "headlines": [
    "오늘 코스피 마감 관련 헤드라인 1",
    "헤드라인 2",
    "헤드라인 3"
  ],
  "market_sentiment": "bullish or bearish or neutral"
}}
"""

US_PROMPT = """\
오늘({today}) 미국 증시(S&P500/NASDAQ) 예측에 필요한 최신 뉴스를 Google Search로 검색해 분석해줘.

검색할 내용:
- **[최우선·무버 역추적] 오늘 가장 크게 움직인 종목부터 찾는다**: 특정 이름을 미리 정해 검색하지 말고, 오늘(현지) 프리마켓·시간외에서 **가장 크게 오른 종목과 가장 크게 내린 종목**(S&P500·나스닥100 대형주 중심)을 먼저 식별한 뒤, **각 급등·급락의 원인 뉴스를 역으로 검색**한다. 아래 나열된 이름은 참고일 뿐이며, 목록에 없는 종목이라도 오늘 크게 움직였다면 반드시 포함한다(미디어·컨슈머·항공우주·헬스케어 등 어느 섹터든 — 예: 실적 발표 대형주, 개별 악재로 저점을 이탈한 종목).
- **[필수] 하락 촉매를 상승 촉매와 같은 비중으로 찾는다**: 오늘 **저점을 깨거나 급락한 종목·섹터와 그 원인**을 반드시 포함한다. 실적 미스·가이던스 하향·구독자/사용자 등 KPI 미달·발사/출시 연기·서비스 장애·리콜·소송·규제 제재·사고·경영진 이탈 등 **실적 외 이벤트성 악재**도 포함한다. 시장이 위로만 가지 않으므로, catalysts에 상승만 있고 하락이 하나도 없으면 검색이 부족한 것이다(그날 실제로 하락 촉매가 없었던 경우만 예외).
- 현재 S&P500·나스닥 선물 방향과 수치
- 오늘 발표된 경제 지표 결과 (CPI, NFP, FOMC 등)
- 빅테크·반도체 주요 이슈 (NVDA, AAPL, MSFT, AMD, NFLX 등)
- 연준 발언·금리 동향
- 아시아·유럽 증시 흐름
- **유가·지정학 리스크**: 국제 유가(WTI·브렌트)의 급등락과 그 원인(중동 정세·주요 해상 물류 항로 긴장·산유국 정책·재고 지표 등)이 에너지주(XOM·CVX 등)·정유·항공·해운주에 어느 방향으로 영향을 주는지 검색한다. 오늘 새로 불거진 지정학 이슈가 있으면 반드시 포함한다.
- **주도주 기업 이벤트**: 매그니피센트7(NVDA·AAPL·MSFT·GOOGL·AMZN·META·TSLA)·넷플릭스(NFLX)·브로드컴(AVGO)·AMD·스페이스X(SPCX) 등 시총 상위 빅테크의 실적·가이던스·신제품·M&A·대형 계약·자사주·감원, 그리고 **발사·미션 일정(연기·성공/실패)·서비스 장애·리콜 등 운영 이벤트**까지
- **[최우선] 오늘/어제 발표된 주요 기업 실적(어닝) — 어닝시즌에는 이것이 지수·섹터를 가장 크게 움직이는 촉매다**: 빅테크뿐 아니라 **금융주(모건스탠리·골드만삭스·JP모건·뱅크오브아메리카·블랙록·씨티 등 대형 은행·자산운용)**, 반도체·장비(마이크론·TSMC·ASML·램리서치·어플라이드머티리얼즈·KLA), 헬스케어·소비재 등 **모든 섹터의 대형주 실적·가이던스·컨퍼런스콜 경영진 코멘트**를 반드시 검색한다. 오늘 실적을 발표하는 기업, 발표한 기업의 EPS·매출 서프라이즈/미스, 주가 반응(프리마켓·시간외 포함)을 함께 찾는다.
- **[중요] 프리마켓(개장 전) 반응 — 이 브리핑은 미국 프리마켓 시점에 나가므로, 개장 전에 이미 나타난 반응이 오늘 세션의 1급 선행 신호다**: 미국 개장 전(현지 새벽~오전)에 실적을 낸 기업(유럽 상장사·대형 은행처럼 개장 전 발표)의 실적이 프리마켓에서 어느 종목·섹터를 어느 방향으로 움직이고 있는지 검색한다. "무슨 실적 서프라이즈/미스 → 프리마켓에서 어느 섹터가 왜 강세/약세" 형태로 찾는다. **단 오늘·어제 새로 발표된 실적만 대상으로 한다 — 며칠 전 발표된 실적이 후속 기사로 계속 검색된다고 해서 프리마켓 촉매로 다시 담지 않는다.**
- **실적 read-through(연쇄 파급)**: 한 기업의 실적·발언이 **다른 종목·섹터를 움직인 경우**를 포착한다. (예: 한 IT 대기업 실적 콜의 AI 인프라 언급 → 메모리·데이터센터주 상승, 은행 실적의 대손충당·자본시장 코멘트 → 금융 섹터 전반, 반도체 장비사 가이던스 → 관련 장비주(LRCX·AMAT·KLAC)) 어느 기업의 무슨 실적/발언이 어느 종목·섹터를 왜 움직였는지 인과로 정리한다.
- **인과 촉매**: 특정 섹터/주도주 등락의 '원인'이 된 사건 — 신제품·전략 발표, 규제·소송, 공급망·감산, **발사·출시 연기·서비스 장애·리콜·사고·경영진 이탈 등 운영 악재**가 어느 종목·섹터를 왜 움직였는지 (하락 원인도 상승 원인과 동일하게 중요)
- **AI 모델 개발사 이슈(비상장이지만 핵심 시장 촉매)**: OpenAI·Anthropic의 신모델 출시, 대형 칩·클라우드 계약, 펀딩·밸류, IPO 진행(S-1·상장 일정) — 엔비디아·브로드컴·MS·아마존·구글 등 상장 AI 인프라주에 미치는 파급

[key_indicators 작성 규칙]
- 오늘 또는 어제 실제 발생한 이슈, 현재 선물 방향만 포함한다
- 반드시 수치(%, 금액, bp)를 포함한다
- 포함 금지: YTD 수익률, 연간 상승률, 애널리스트 중장기 전망

[catalysts 작성 규칙]
- 오늘 미국 증시 주도주·섹터를 움직일 '사건' 중심 뉴스만 담는다 (지수 등락률 나열이 아님)
- **catalysts의 각 항목은 반드시 `{{"date": "YYYY-MM-DD", "text": "사건 → 영향", "ticker": "대표 티커"}}` 형태의 객체다** (문자열이 아니다). `date`는 그 사건이 실제 발생·발표된 날짜(실적이면 실적 발표일, 지정학·정책·유가면 사건 발생일)로, 검색으로 확인한 실제 날짜만 넣고 추측하지 않는다. `text`는 "무슨 사건 → 어느 종목·섹터에 왜 영향" 한 문장. `ticker`는 그 사건의 주체 기업 미국 티커(예: 마이크론이면 "MU", 여러 곳이면 "JPM,GS"). 거시·지정학·유가 등 특정 기업이 없으면 빈 문자열 "".
- **`date`는 오늘({today}) 또는 어제만 허용한다.** 이틀 이상 전에 발생·발표된 사건은, 오늘 후속 기사·리캡·주가 잔여 반응이 검색되더라도 담지 않는다. 특히 어닝(실적)은 며칠 전 발표분이 계속 검색된다고 매일 재등장시키지 않는다 — 발표일이 이틀 이상 전이면 catalysts에 넣지 말 것. 유가·지정학·정책 등 사건형 촉매도 오늘·어제 새로 전개된 것만 담는다.
- **오늘·어제 새로 발표된 실적이 없으면 실적 catalyst를 억지로 만들지 않는다.** 어닝시즌이라도 오늘 실제로 나온 실적이 없는 날이 있다 — 그런 날은 빈자리를 며칠 전 실적으로 채우지 말고, 유가·지정학·매크로·개별 이벤트 등 오늘 실제로 움직인 촉매만 담거나 빈 배열로 둔다. 완전성보다 정합성이 우선이다.
- 실제로 검색된 사건만 담고, 없으면 빈 배열 []
- **오늘/어제 발표된 주요 기업 실적(어닝)은 catalysts에 최우선으로 담는다** — 실적 서프라이즈·가이던스·경영진 발언이 해당 종목뿐 아니라 다른 종목·섹터로 파급된 경우(read-through)를 인과로 정리한다.
- **개장 전 실적으로 프리마켓에서 이미 움직인 섹터도 catalysts에 담는다** — 이 브리핑은 프리마켓 시점에 나가므로, 개장 전 반응은 오늘 세션을 예고하는 핵심 촉매다.
- **[필수] 모든 항목의 주어는 실제 기업·기관 실명이어야 한다.** 검색으로 회사 이름을 특정하지 못했다면
  "A사"·"B사"·"C은행"·"모 기업"·"익명의 한 기업"처럼 익명화하거나 아래 예시의 대괄호 슬롯(`[기업]`)을
  그대로 남기지 말고, **그 항목을 통째로 버린다.** 실명 없는 사건은 검증이 불가능해 발행할 수 없다.
  실명으로 채울 수 있는 항목이 하나도 없으면 빈 배열 []로 둔다 — 완전성보다 정합성이 우선이다.
- 문장 형태 예시 4개(회사명·사건은 형식 참고용일 뿐이다 — 절대 그대로 베끼지 말고, 오늘 실제 검색으로 찾은 회사명·사건·수치로만 채운다):
  · "[기업]의 [제품·전략 발표] → [파급되는 섹터·종목]에 [영향 방향]"
  · "[대형 은행]의 [실적 지표] 서프라이즈 → [동종 대형 은행들]에 동반 [영향 방향]"
  · "[기업] 실적 콜의 [경영진 코멘트] → [연관 섹터]로 파급"
  · "[해외 반도체 장비사]의 [실적·수주] 서프라이즈 → 프리마켓에서 [관련 장비주]에 [영향 방향]"
  · "[기업]의 [실적·KPI 미스] → [해당 종목·섹터] 저점 이탈·급락"
  · "[기업]의 [발사·출시 연기 / 서비스 장애 / 리콜 / 소송] → [관련 종목·섹터] 약세"
- **상승 촉매와 하락 촉매를 모두 담는다.** 오늘 저점을 깨거나 급락한 종목·섹터의 원인을 최소 1개 이상 포함한다(그날 하락 촉매가 실제로 없었던 경우만 예외). 상승만 나열하지 않는다.

출력 형식 (JSON만, 다른 텍스트 없이):
{{
  "key_indicators": [
    "오늘 선물·프리마켓 관련 구체적 이슈 (수치 포함)",
    "발표된 경제 지표 결과 또는 연준 이슈",
    "빅테크·반도체 이슈 (수치 포함)",
    "금리·VIX·달러 관련 이슈",
    "아시아·유럽 증시 흐름"
  ],
  "catalysts": [
    {{"date": "YYYY-MM-DD", "text": "주도주·섹터를 움직인 사건 → 영향 (실제 검색된 것만·오늘/어제 발생분만, 없으면 이 배열은 비운다)", "ticker": "대표 티커 또는 빈 문자열"}}
  ],
  "headlines": [
    "미국 증시 방향에 영향을 줄 헤드라인 1",
    "헤드라인 2",
    "헤드라인 3"
  ],
  "market_sentiment": "bullish or bearish or neutral"
}}
"""

PROMPT_MAP = {
    "kospi": KOSPI_PROMPT,
    "kospi-close": KOSPI_CLOSE_PROMPT,
    "us": US_PROMPT,
}


# ─────────────────────────────────────────────────────────────────────────────
# Gemini Google Search grounding으로 뉴스 수집·요약
# ─────────────────────────────────────────────────────────────────────────────

def _load_prev_catalysts(briefing_type: str, max_items: int = 6) -> list:
    """직전 실행이 저장한 data/news_summary_{type}.json의 catalysts·headlines를 읽는다.

    이 파일은 매 실행마다 덮어써지므로, 오늘 실행이 덮어쓰기 전 시점엔 어제(직전) 실행분이
    그대로 남아 있다 — 이 시점에 읽어 "이미 다룬 주제" 목록으로 프롬프트에 주입한다.
    2026-07-15~17 실사고: ASML·모건스탠리 실적 촉매가 프롬프트의 예시 문장과 겹치는 데다
    이 중복 방지 장치가 없어 사흘 연속 같은 이슈가 "오늘의 이슈"로 재포장됐다.
    파일 없음·파싱 실패 시 빈 리스트를 반환해 중복 방지 없이 정상 진행한다(수집 자체를 막지 않음)."""
    path = DATA_DIR / f"news_summary_{briefing_type}.json"
    if not path.exists():
        return []
    try:
        prev = json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    items = (prev.get("catalysts") or []) + (prev.get("headlines") or [])
    return items[:max_items]


# 문자열형 catalyst 맨 앞의 [YYYY-MM-DD] 발생일 접두사 (하위호환 파싱용)
_DATE_PREFIX_RE = re.compile(r"^\s*\[(\d{4})-(\d{2})-(\d{2})\]\s*")


def _parse_iso_date(s: str):
    """'YYYY-MM-DD' → date, 파싱 불가 시 None."""
    m = re.match(r"^\s*(\d{4})-(\d{2})-(\d{2})", s or "")
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


# 방향 주장 어휘 — 대상 키워드 근처에 이 표현이 있으면 그 방향을 주장한 것으로 본다.
_UP_WORDS = r"(?:급등|상승|강세|오르|올라|뛰|치솟|반등|돌파|회복|상승세)"
_DOWN_WORDS = r"(?:급락|하락|약세|내리|떨어|밀리|빠지|폭락|급감|하락세|후퇴)"

# 실측 대조 대상 — 키워드 → 실측 스냅샷 키
# 지수는 2026-07-29 실사고로 추가됐다(§28): "나스닥 사상 최고치 경신"(실측 -0.22%)·
# "S&P500 5,500선 돌파"(실측 ~7,4xx)가 방향·레벨 무검증으로 통과했다.
# 긴 이름을 먼저 둬야 "필라델피아 반도체"가 부분 매칭으로 갈리지 않는다.
_REALITY_SUBJECTS = {
    "유가": "oil",
    "국제유가": "oil",
    "WTI": "oil",
    "브렌트": "oil",
    "필라델피아 반도체지수": "sox",
    "필라델피아 반도체": "sox",
    "나스닥": "nasdaq",
    "S&P500": "sp500",
    "S&P 500": "sp500",
    "다우존스": "dow",
    "다우": "dow",
}

# 지수 실측 조회 심볼 (change_pct·현재 레벨을 함께 본다)
_INDEX_SYMBOLS = {"nasdaq": "^IXIC", "sp500": "^GSPC", "dow": "^DJI", "sox": "^SOX"}

# "사상 최고치 경신"처럼 **수치가 없는 정성 최상급 주장**. 등락률 게이트(§22·§24)는
# 인접 숫자가 있어야 발화하므로 이런 주장에 구조적으로 눈이 먼다 — 별도로 잡는다.
_HIGH_SUPERLATIVE_RE = re.compile(r"(?:사상\s*최고|역대\s*최고|최고치|신고가|사상최고)")
_LOW_SUPERLATIVE_RE = re.compile(r"(?:사상\s*최저|역대\s*최저|최저치|신저가|사상최저)")

# "5,500선"·"5500 포인트"·"5,500 돌파" 형태의 지수 레벨 표기 (3~5자리)
_INDEX_LEVEL_RE = re.compile(r"(\d{1,2}[,]?\d{3})\s*(?:선|포인트|p\b|돌파|회복|안착)")
# "배럴당 78달러" 형태 — 유가는 자릿수가 짧아 위 지수 패턴에 안 걸린다
_PRICE_LEVEL_RE = re.compile(r"(\d{2,3}(?:\.\d+)?)\s*달러")


def _claim_direction(text: str, subject: str) -> str | None:
    """text가 subject에 대해 주장하는 방향("up"/"down")을 뽑는다. 없으면 None.

    subject 등장 위치 기준 앞뒤 25자 안에서만 방향어를 찾는다 — 문장 전체를 훑으면
    "유가 하락으로 항공주 상승"처럼 서로 다른 대상의 방향어가 교차 매칭된다.
    """
    if not text or subject not in text:
        return None
    for m in re.finditer(re.escape(subject), text):
        win = text[max(0, m.start() - 25): m.end() + 25]
        up = re.search(_UP_WORDS, win)
        down = re.search(_DOWN_WORDS, win)
        if up and not down:
            return "up"
        if down and not up:
            return "down"
    return None


def _superlative_claim_wrong(text: str, subject: str, snap: dict) -> str | None:
    """subject에 대한 '사상 최고/최저' 류 주장이 실측과 어긋나면 사유 문자열, 아니면 None.

    2026-07-29 실사고(§28): "나스닥이 사상 최고치를 경신"이 그대로 발행됐는데 실측은
    **-0.22% 하락 마감**이었고 최근 고점 대비로도 한참 아래였다. 이 주장엔 숫자가 하나도
    없어서 등락률 게이트(§22·§24)가 구조적으로 발화할 수 없었다 — 그래서 별도 게이트다.

    판정: 최고 주장인데 (그날 하락했거나 | 최근 고점의 99% 미만) → 틀림. 최저는 대칭.
    52주 고·저를 못 구했으면 등락 방향만으로 판정한다(fail-open 우선).
    """
    if subject not in text:
        return None
    win_all = "".join(text[max(0, m.start() - 25): m.end() + 25]
                      for m in re.finditer(re.escape(subject), text))
    chg, level = snap.get("change_pct"), snap.get("level")
    if _HIGH_SUPERLATIVE_RE.search(win_all):
        if chg is not None and chg < 0:
            return f"'최고' 주장이나 실측 {chg:+.2f}% 하락"
        hi = snap.get("high_52w")
        if level is not None and hi and level < hi * 0.99:
            return f"'최고' 주장이나 실측 {level:,.0f} < 52주 고점 {hi:,.0f}"
    if _LOW_SUPERLATIVE_RE.search(win_all):
        if chg is not None and chg > 0:
            return f"'최저' 주장이나 실측 {chg:+.2f}% 상승"
        lo = snap.get("low_52w")
        if level is not None and lo and level > lo * 1.01:
            return f"'최저' 주장이나 실측 {level:,.0f} > 52주 저점 {lo:,.0f}"
    return None


def _level_claim_wrong(text: str, subject: str, snap: dict, tol: float = 0.15) -> str | None:
    """subject 근처에 적힌 지수 레벨이 실측과 tol(기본 ±15%)를 넘게 어긋나면 사유, 아니면 None.

    2026-07-29 실사고(§28): "S&P 500 지수는 0.3% 상승한 5,500선을 돌파" — **등락률은 맞고
    레벨만 틀린** 형태라 방향 게이트를 그대로 통과했다(실측 ~7,4xx, -26%). 학습 시점의
    옛 지수 레벨을 그대로 뱉는 그라운딩 실패의 전형이라, 레벨을 따로 대조한다.
    """
    level = snap.get("level")
    if level is None or subject not in text:
        return None
    # 유가는 자릿수가 짧아(78달러) 지수 패턴에 안 걸리므로 달러 표기도 함께 본다
    pats = (_INDEX_LEVEL_RE, _PRICE_LEVEL_RE) if level < 1000 else (_INDEX_LEVEL_RE,)
    for m in re.finditer(re.escape(subject), text):
        win = text[m.start(): m.end() + 30]
        for pat in pats:
            for lm in pat.finditer(win):
                claimed = float(lm.group(1).replace(",", ""))
                if abs(claimed / level - 1) > tol:
                    return f"레벨 {claimed:,.1f} vs 실측 {level:,.1f}"
    return None


def _drop_reality_contradictions(items: list, real: dict) -> list:
    """실측 시장데이터와 어긋나는 주장을 담은 항목을 제거한다.

    검사 3종 — ① 방향 반대 ② 정성 최상급(사상 최고/최저) 모순 ③ 지수 레벨 이탈.

    2026-07-27 실사고: 미국 브리핑 재수집분이 "국제유가 80달러 돌파 → 에너지 관련주 상승세"·
    "중동 긴장 완화 속 국제유가 상승세 지속"을 냈는데, 실측은 **WTI -6.05%·브렌트 -6.67%**로
    정반대였다(CVX -2.9%, XOM -3.3%). 익명 플레이스홀더 게이트(§25)는 실명이 있어 통과시키고,
    어닝 게이트(§22)는 실적 서사가 아니라 통과시키며, validate_analysis는 call_claude
    **이후**라 이미 서사가 만들어진 뒤다. 그래서 수집 단계에서 잘라낸다.

    2026-07-29 실사고(§28)로 ②③이 추가됐다 — ①만으로는 "나스닥 사상 최고치 경신"(숫자 없음)과
    "S&P500 5,500선 돌파"(방향은 맞고 레벨만 틀림)를 둘 다 놓친다.

    real이 비었거나 값이 없으면 판단하지 않는다(fail-open) — 정상 항목 오제거를 막는다.
    """
    out = []
    for it in items or []:
        text = it if isinstance(it, str) else (it.get("text", "") if isinstance(it, dict) else "")
        reason = None
        for subject, key in _REALITY_SUBJECTS.items():
            snap = real.get(key)
            if not snap:
                continue
            # 하위호환: 예전 스냅샷은 등락률 float 하나였다(§27) — dict로 승격해서 받는다
            if isinstance(snap, (int, float)):
                snap = {"change_pct": float(snap), "level": None}
            chg = snap.get("change_pct")
            if chg is not None:
                claimed = _claim_direction(text, subject)
                if claimed and claimed != ("up" if chg > 0 else "down"):
                    reason = f"{subject} 방향 모순(실측 {chg:+.2f}%, 주장 {claimed})"
            reason = reason or _superlative_claim_wrong(text, subject, snap)
            reason = reason or _level_claim_wrong(text, subject, snap)
            if reason:
                print(f"[fetch_news] 실측 모순 제거({subject}: {reason}): {text[:60]}",
                      file=sys.stderr)
                break
        if not reason:
            out.append(it)
    return out


def _fetch_reality_snapshot() -> dict:
    """실측 대조에 쓸 시장 스냅샷. 조회 실패 항목은 None으로 두어 fail-open한다.

    각 키는 {"change_pct":…, "level":…, "high_52w":…, "low_52w":…} 형태다(없는 값은 None).
    """
    real: dict = {}
    try:
        import yfinance as yf
    except Exception as e:                                     # pragma: no cover
        print(f"[fetch_news] yfinance 없음 — 실측 대조 생략: {e}", file=sys.stderr)
        return real

    def _snap(symbol: str, with_52w: bool) -> dict | None:
        h = yf.Ticker(symbol).history(period="1y" if with_52w else "7d")["Close"].dropna()
        if len(h) < 2:
            return None
        last, prev = float(h.iloc[-1]), float(h.iloc[-2])
        s = {"change_pct": round((last / prev - 1) * 100, 2), "level": last,
             "high_52w": None, "low_52w": None}
        if with_52w:
            s["high_52w"], s["low_52w"] = float(h.max()), float(h.min())
        return s

    for key, symbol in [("oil", "CL=F"), *_INDEX_SYMBOLS.items()]:
        try:
            snap = _snap(symbol, with_52w=(key != "oil"))
            if snap:
                real[key] = snap
        except Exception as e:
            print(f"[fetch_news] {key}({symbol}) 실측 조회 실패(대조 생략): {e}", file=sys.stderr)
    return real


def _catalyst_cutoff(briefing_type: str, today: date) -> date:
    """브리핑 타입별 catalyst 허용 시작일(이 날짜 이상만 채택).

    기본은 어제(today-1)다. **코스피 아침 브리핑만 직전 미국장까지 창을 넓힌다** —
    월요일 07:25에 직전 미국장은 지난 금요일이라, 어제(일요일) 기준으로 자르면
    그 브리핑이 실제로 다뤄야 할 금요일 미국장 사건이 통째로 잘려나간다(§24 세션 갭).
    평일에는 직전 미국장 = 어제라 기존 동작과 같다.
    """
    default = today - timedelta(days=1)
    if briefing_type != "kospi":
        return default
    try:
        from session_label import prev_us_session
        prev_us = prev_us_session(today)
    except Exception as e:
        print(f"[fetch_news] session_label 사용 불가, 기본 cutoff 사용: {e}", file=sys.stderr)
        return default
    return min(default, prev_us) if prev_us else default


def _filter_stale_catalysts(catalysts: list, today: date, cutoff: date = None) -> list:
    """catalyst별 발생일을 읽어 오늘/어제(today-1)보다 오래된 사건은 버리고, 남긴 항목은
    순수 문자열(사건 → 영향)로 반환한다. 다운스트림(call_claude)은 문자열 리스트를 기대한다.

    항목 형태 2가지를 모두 받는다:
      · {"date": "YYYY-MM-DD", "text": "사건 → 영향"}  ← US 프롬프트가 요구하는 구조화 형태
      · "사건 → 영향"  또는  "[YYYY-MM-DD] 사건 → 영향"  ← 문자열/인라인 접두사(하위호환)

    2026-07-15~20 실사고: 7/15 발표된 ASML 2분기 실적이 사흘 넘게 '오늘 프리마켓 촉매'로
    재등장했다(_load_prev_catalysts 소프트 중복 방지만으론 못 막음). 이 함수가 하드 게이트다.
    날짜 미상 항목은 버리지 않는다 — 유가·지정학 등 날짜 태그 없이 오는 거시 촉매를 보호한다.
    완전성보다 정합성이 우선이되, '날짜 미상'과 '오래됨'은 구분한다.

    cutoff를 명시하면 그 날짜 이상만 채택한다(코스피 월요일의 주말 공백 — `_catalyst_cutoff`)."""
    if cutoff is None:
        cutoff = today - timedelta(days=1)
    kept, dropped = [], []
    for c in catalysts:
        if isinstance(c, dict):
            text = (c.get("text") or c.get("catalyst") or "").strip()
            if not text:
                continue
            ev = _parse_iso_date(c.get("date") or c.get("event_date") or "")
        elif isinstance(c, str):
            m = _DATE_PREFIX_RE.match(c)
            text = _DATE_PREFIX_RE.sub("", c).strip() if m else c.strip()
            ev = _parse_iso_date(f"{m.group(1)}-{m.group(2)}-{m.group(3)}") if m else None
        else:
            continue
        if ev is not None and ev < cutoff:
            dropped.append((text, ev.isoformat()))
        else:
            kept.append(text)  # 최신이거나 날짜 미상 → 유지
    for txt, ev in dropped:
        print(f"[fetch_news] stale catalyst 제외({ev}): {txt}", file=sys.stderr)
    return kept


# ─────────────────────────────────────────────────────────────────────────────
# 교차일 recap 게이트 — 자기보고 날짜에 의존하지 않는 하드 방어
#
# flash-lite는 "오늘/어제만" 규칙을 stale 항목을 빼서가 아니라 날짜를 오늘·어제로 위조해
# 지킨다(모건스탠리 실적을 실제 발표일이 아니라 07-19로 찍는 식). 그래서 _filter_stale_catalysts
# (자기보고 날짜 기반)만으론 며칠 된 사건이 매일 재등장하는 걸 못 막는다.
# 이 게이트는 날짜를 믿지 않고, '2일 이상 전 브리핑에 실제로 나왔던 catalyst'와 내용이 실질적으로
# 같으면(문자 3-gram 유사도 + 공유 고유엔티티) 하드 제외한다. 2026-07-15~20 ASML 실사고 대응.
# ─────────────────────────────────────────────────────────────────────────────

# 고유 식별력이 없는 범용 대문자 토큰 — 엔티티로 치지 않는다(AI·CPI 등은 매일 등장)
_GENERIC_UPPER = {
    "AI", "CPI", "PPI", "WTI", "VIX", "EPS", "GDP", "FOMC", "ETF", "IPO", "US",
    "USD", "SP", "NASDAQ", "DOW", "Q", "KPI", "M", "ADR", "HBM", "DRAM", "SOX",
    "GPU", "CPU", "CEO", "CFO", "M&A", "S", "P", "PCE", "NFP", "BOJ", "ECB",
}


def _norm_for_match(s: str) -> str:
    """한글·영숫자만 남기고 소문자로 붙인다(조사·구두점·공백 제거)."""
    return re.sub(r"[^0-9a-z가-힣]", "", (s or "").lower())


def _char_ngrams(s: str, n: int = 3) -> set:
    s = _norm_for_match(s)
    if len(s) < n:
        return {s} if s else set()
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _distinctive_entities(text: str) -> set:
    """티커·영문 사명 등 고유 식별 토큰(2자 이상 라틴). 범용어(_GENERIC_UPPER)는 제외."""
    return {t for t in re.findall(r"[A-Za-z]{2,}", (text or "").upper())
            if t not in _GENERIC_UPPER}


def _is_cross_day_recap(text: str, stale_texts: list) -> bool:
    """text가 2일 이상 전 catalyst(stale_texts) 중 하나의 재탕이면 True.

    판정: 어떤 stale와 (유사도 ≥ 0.40) 이거나 (공유 고유엔티티 존재 AND 유사도 ≥ 0.15).
    실측(2026-07 ASML 변형)으로 튜닝 — 같은 사건 재탕은 잡고, 같은 엔티티라도 다른 뉴스는 유지."""
    g = _char_ngrams(text)
    ents = _distinctive_entities(text)
    for s in stale_texts:
        sim = _jaccard(g, _char_ngrams(s))
        if sim >= 0.40 or (ents & _distinctive_entities(s) and sim >= 0.15):
            return True
    return False


def _drop_cross_day_recaps(catalysts: list, stale_texts: list) -> list:
    """catalysts에서 stale_texts(2일+ 전)와 실질 중복인 항목을 하드 제외한다."""
    if not stale_texts:
        return catalysts
    kept = []
    for c in catalysts:
        if _is_cross_day_recap(c, stale_texts):
            print(f"[fetch_news] 교차일 recap 제외: {c}", file=sys.stderr)
        else:
            kept.append(c)
    return kept


# ─────────────────────────────────────────────────────────────────────────────
# 독립 어닝 캘린더 검증 — flash-lite의 자기보고 날짜 대신 yfinance 실제 발표일로 판정
#
# 2026-07-20 실사고: 오늘(월) 신선한 실적이 없는데도 프롬프트가 "실적 최우선"을 요구하니
# flash-lite가 몇 주 된 실적(마이크론 6/24·테슬라 인도량 7/2·JP모건 7/14)을 '오늘 촉매'로
# 재소환했다. 교차일 게이트는 히스토리 창(5일) 밖 사건은 못 잡는다. 근본 차단을 위해,
# 실적형 catalyst의 티커를 yfinance로 조회해 실제 최근 발표일이 max_age_days를 넘으면 제외한다.
# ─────────────────────────────────────────────────────────────────────────────

_EARNINGS_KEYWORDS = ("실적", "어닝", "earnings", "eps", "매출", "순이익",
                      "가이던스", "guidance", "분기", "컨퍼런스콜", "실적 발표")


def _is_earnings_catalyst(text: str) -> bool:
    t = (text or "").lower()
    return any(k in t for k in _EARNINGS_KEYWORDS)


def _parse_tickers(ticker_field) -> list:
    """catalyst의 ticker 필드(문자열/리스트)에서 유효 티커(1~5자 라틴)만 추출."""
    if isinstance(ticker_field, list):
        raw = " ".join(str(x) for x in ticker_field)
    else:
        raw = str(ticker_field or "")
    return [t for t in re.findall(r"[A-Za-z]{1,5}", raw.upper())
            if t not in _GENERIC_UPPER]


_earnings_age_cache: dict = {}


def _days_since_last_earnings(ticker: str, today: date):
    """yfinance로 ticker의 '가장 최근 과거 실적 발표일'을 조회해 today와의 일수 차를 반환.
    조회 실패·데이터 없음이면 None(검증 불가 → 상위 로직이 '유지'로 판단)."""
    if ticker in _earnings_age_cache:
        return _earnings_age_cache[ticker]
    age = None
    try:
        import yfinance as yf
        df = yf.Ticker(ticker).get_earnings_dates(limit=12)
        if df is not None and not df.empty:
            past = [d.date() for d in df.index if getattr(d, "tzinfo", None) and d.date() <= today]
            if past:
                age = (today - max(past)).days
    except Exception as e:
        print(f"[fetch_news] 어닝일 조회 실패({ticker}): {e}", file=sys.stderr)
    _earnings_age_cache[ticker] = age
    return age


# 뉴스 텍스트에 한글/영문 사명으로만 언급된 회사를 티커로 resolve — Gemini 문자열 catalyst엔
# ticker 필드가 없어 어닝 캘린더 검증이 건너뛰어지던 구멍을 막는다(2026-07-22 '엔비디아 실적 발표'
# 실사고: NVIDIA는 7월 하순에 실적이 없는데 Gemini가 오늘 촉매로 소환, ticker 필드가 없어 통과).
# yfinance 어닝 조회가 신뢰 가능한 미국 대형주만 등록(국내주는 .KS 어닝이 불안정 → 미등록=fail-open).
_NAME_TO_TICKER = {
    "엔비디아": "NVDA", "nvidia": "NVDA",
    "애플": "AAPL",
    "마이크로소프트": "MSFT",
    "아마존": "AMZN",
    "메타": "META",
    "알파벳": "GOOGL", "구글": "GOOGL",
    "테슬라": "TSLA",
    "마이크론": "MU", "micron": "MU",
    "브로드컴": "AVGO",
    "인텔": "INTC",
    "퀄컴": "QCOM",
    "넷플릭스": "NFLX",
    "오라클": "ORCL",
    "세일즈포스": "CRM",
    "어도비": "ADBE",
    "asml": "ASML",
    "tsmc": "TSM", "대만반도체": "TSM",
    "제이피모건": "JPM", "jp모건": "JPM", "jpmorgan": "JPM",
    "골드만삭스": "GS",
    "모건스탠리": "MS",
    "뱅크오브아메리카": "BAC",
    "씨티그룹": "C",
    "웰스파고": "WFC",
    "블랙록": "BLK",
}
_NAME_TO_TICKER_NORM = {_norm_for_match(k): v for k, v in _NAME_TO_TICKER.items()}


def _resolve_company_tickers(text: str) -> list:
    """뉴스 텍스트에 언급된 (매핑된) 회사명을 티커 리스트로 변환. 등장 회사만, 중복 제거."""
    t = _norm_for_match(text)
    out = []
    for name_norm, ticker in _NAME_TO_TICKER_NORM.items():
        if name_norm and name_norm in t and ticker not in out:
            out.append(ticker)
    return out


def _drop_stale_earnings(catalysts: list, today: date, max_age_days: int = 2,
                         age_fn=None) -> list:
    """실적형 catalyst 중, 티커의 실제 최근 발표일이 max_age_days를 초과한 것을 제외.

    - 실적형이 아니면(거시·지정학·제품 등) 검증하지 않고 유지.
    - 티커가 없거나 조회 실패면 검증 불가 → 유지(과잉 제외 방지, 교차일 게이트가 백스톱).
    - 여러 티커 중 하나라도 최근(≤max_age_days) 발표면 신선한 실적으로 보고 유지.
    catalysts 항목은 {date,text,ticker} dict 또는 문자열. 반환 shape는 입력과 동일."""
    age_fn = age_fn or _days_since_last_earnings
    kept = []
    for c in catalysts:
        text = c.get("text", "") if isinstance(c, dict) else str(c)
        ticker_field = c.get("ticker", "") if isinstance(c, dict) else ""
        if not _is_earnings_catalyst(text):
            kept.append(c)
            continue
        # ticker 필드 + 텍스트에서 resolve한 사명(엔비디아→NVDA 등)을 합쳐 검증
        tickers = list(dict.fromkeys(_parse_tickers(ticker_field) + _resolve_company_tickers(text)))
        if not tickers:
            kept.append(c)  # 검증 불가 → 유지
            continue
        ages = [a for a in (age_fn(t, today) for t in tickers) if a is not None]
        if not ages:
            kept.append(c)  # 전부 조회 실패 → 유지
            continue
        if min(ages) > max_age_days:
            print(f"[fetch_news] stale 실적 제외(최근 발표 {min(ages)}일 전 > {max_age_days}): {text}",
                  file=sys.stderr)
        else:
            kept.append(c)
    return kept


def _history_path(briefing_type: str) -> Path:
    return DATA_DIR / f"catalyst_history_{briefing_type}.json"


def _load_stale_catalysts(briefing_type: str, today: date, min_age_days: int = 2) -> list:
    """catalyst_history_{type}.json에서 (today - min_age_days) 이전 날짜의 catalyst를 모아 반환.

    '오늘/어제'는 정상(신선)이므로 제외하고, 이틀 이상 전에 등장했던 것만 recap 판정 대상으로 쓴다."""
    path = _history_path(briefing_type)
    if not path.exists():
        return []
    try:
        hist = json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    cutoff = today - timedelta(days=min_age_days)
    stale = []
    for entry in hist:
        d = _parse_iso_date(entry.get("date", ""))
        if d is not None and d <= cutoff:
            stale.extend(entry.get("catalysts", []))
    return stale


def _append_catalyst_history(briefing_type: str, today: date, catalysts: list,
                             keep_days: int = 5) -> None:
    """오늘 발행한 catalyst(문자열 리스트)를 히스토리에 기록하고 최근 keep_days개 날짜만 유지."""
    path = _history_path(briefing_type)
    hist = []
    if path.exists():
        try:
            hist = json.load(open(path, encoding="utf-8"))
        except Exception:
            hist = []
    today_str = today.isoformat()
    hist = [e for e in hist if e.get("date") != today_str]  # 같은 날 재실행 시 갱신
    hist.append({"date": today_str, "catalysts": list(catalysts)})
    hist.sort(key=lambda e: e.get("date", ""))
    hist = hist[-keep_days:]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=2)


# 검색 실패 보고 문장 (이슈가 아니라 "못 찾았다"는 메타 서술)
_SEARCH_FAILURE_RE = re.compile(
    r"(확인되지\s*않|검색되지\s*않|찾을\s*수\s*없|찾지\s*못|나오지\s*않|"
    r"아직\s*(?:발표|공개)되지\s*않|"
    r"관련\s*(?:최신\s*)?뉴스는?\s*없|특별한\s*(?:이슈|뉴스)는?\s*없|정보가\s*없|"
    r"(?:신규\s*)?이슈\s*(?:는\s*)?없|"
    r"[(（][^)）]*(?:없음|않음|미확인)[)）])"
)


# 익명 플레이스홀더 주어 (실존 기업이 아니라 "A사"·"[기업]" 같은 빈 슬롯)
_PLACEHOLDER_ENTITY_RE = re.compile(
    # "A사"·"B사의" — 단일 영문 대문자 + 사 (뒤에 조사·구두점·공백만 허용)
    r"(?<![A-Za-z0-9])[A-Z]사(?=[\s,.·)]|의|는|가|도|을|를|와|과|에|만|$)|"
    # "C은행"·"D증권"·"E그룹"·"F기업" — 접미어 자체가 명확해 뒤 제약 불필요
    r"(?<![A-Za-z0-9])[A-Z](?:은행|증권|그룹|기업|테크)|"
    # 프롬프트 예시의 대괄호 슬롯이 그대로 남은 형태 — "[기업]의 …"
    r"\[[가-힣][가-힣·\s]*\]|"
    # 기호 마스킹 — "○○사", "XX사", "△△ 반도체"
    r"[○◯●△▲□■X×]{2,}|"
    # 한국어 익명 지칭 — "모 기업", "익명의 한 기술기업"
    r"익명의?\s|(?<![가-힣])모\s+(?:기업|기술|대형|주요|반도체|은행|증권|글로벌)"
)


def _drop_placeholder_entities(items: list) -> list:
    """"B사"·"C은행"·"[기업]" 처럼 익명 플레이스홀더가 주어인 항목을 제거한다.

    2026-07-27 미국 브리핑 실사고: Gemini가 google_search로 실제 소재를 못 찾자,
    US_PROMPT의 예시 슬롯("[기업]의 [제품·전략 발표] → …") 구조만 남기고 주어를
    "A사"·"B사"·"C은행"·"D사"로 익명화해 형식상 그럴듯한 뉴스를 만들어냈다.
    수치 게이트(validate_analysis)는 "주어가 가짜"를 검출하지 못하고,
    _drop_search_failure_notes는 자백형 실패만 잡으며, _drop_stale_earnings는
    "B사"가 어떤 티커로도 resolve되지 않아 fail-open으로 통과시킨다.

    실명 없는 사건 서술은 검증 자체가 불가능하므로 항목째 버린다 —
    완전성보다 정합성이 우선이다(운영 규칙 0).
    """
    out = []
    for it in items or []:
        text = it if isinstance(it, str) else (it.get("text", "") if isinstance(it, dict) else "")
        if _PLACEHOLDER_ENTITY_RE.search(text or ""):
            print(f"[fetch_news] 익명 플레이스홀더 제거: {text[:60]}", file=sys.stderr)
            continue
        out.append(it)
    return out


# 출력 형식 예시의 슬롯 설명을 모델이 그대로 되돌려준 흔적.
# 예: "국내 트랙 이슈 1 — 한국 증권거래소는 …" (2026-07-29 실사고 §28)
_SLOT_ECHO_RE = re.compile(
    r"^\s*(?:국내\s*트랙\s*이슈\s*\d*|헤드라인\s*\d+|이슈\s*\d+|"
    r"[가-힣·\s]*이슈\s*\d+)\s*[—\-–:]\s*"
)


def _drop_prompt_slot_echoes(items: list) -> list:
    """출력 형식 예시의 슬롯 라벨("국내 트랙 이슈 1 — ")을 그대로 되뱉은 항목을 제거한다.

    2026-07-29 실사고(§28): Gemini가 google_search 그라운딩에 실패한 채 프롬프트의 출력
    형식 예시를 '채워 넣기'만 했고, 슬롯 라벨까지 그대로 남긴 key_indicators가 나왔다.
    라벨 echo는 "검색이 아니라 템플릿을 메웠다"는 강한 신호라, 내용이 그럴듯해 보여도 버린다
    (실제로 그 두 항목이 ADR·금통위 미검증 서사의 출처였다).

    §25의 교훈("슬롯형 예시는 LLM이 빈칸으로 메운다")과 같은 계열이므로,
    프롬프트 쪽 슬롯 라벨 제거(1차 방어)와 이 게이트(최종 방어선)를 함께 둔다.
    """
    out = []
    for it in items or []:
        text = it if isinstance(it, str) else (it.get("text", "") if isinstance(it, dict) else "")
        if _SLOT_ECHO_RE.match(text or ""):
            print(f"[fetch_news] 프롬프트 슬롯 echo 제거: {text[:60]}", file=sys.stderr)
            continue
        out.append(it)
    return out


def _drop_search_failure_notes(items: list) -> list:
    """"현재까지 확인되지 않았습니다" 류의 검색 실패 보고를 제거한다.

    Gemini가 소재를 못 찾으면 그 사실을 그대로 문장으로 만들어 key_indicators·catalysts에
    넣어버린다(2026-07-27 실제 출력: "…최신 뉴스는 현재까지 확인되지 않았습니다").
    이건 이슈가 아니라 메타 서술이라 브리핑에 그대로 실리면 지면만 낭비한다.
    프롬프트로도 금지하지만 새기 때문에 결정론 게이트를 최종 방어선으로 둔다(§22 교훈).
    """
    out = []
    for it in items or []:
        text = it if isinstance(it, str) else (it.get("text", "") if isinstance(it, dict) else "")
        if _SEARCH_FAILURE_RE.search(text or ""):
            print(f"[fetch_news] 검색 실패 보고 제거: {text[:60]}", file=sys.stderr)
            continue
        out.append(it)
    return out


def fetch_and_summarize(briefing_type: str) -> dict:
    """Gemini Google Search grounding으로 최신 뉴스를 검색·요약해 dict로 반환한다."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise RuntimeError("google-genai not installed. Run: pip install google-genai")

    client = genai.Client(api_key=get_gemini_api_key())
    today_date = datetime.now(KST).date()
    today = today_date.strftime("%Y-%m-%d")
    # 코스피 아침 브리핑만 세션 창을 계산해 주입 (다른 타입은 키를 무시한다)
    session_window, us_label = _kospi_session_window(today_date)
    prompt = PROMPT_MAP[briefing_type].format(
        today=today, session_window=session_window, us_label=us_label
    )

    prev_items = _load_prev_catalysts(briefing_type)
    if prev_items:
        listed = "\n".join(f"- {x}" for x in prev_items)
        prompt += (
            "\n\n[중복 방지] 아래는 직전 브리핑에서 이미 다룬 이슈다. 오늘 검색 결과가 이 목록과"
            " 같은 사건이면(단순 재보도·반복 요약) 우선순위를 낮추고 실제로 새로 발생한 다른 이슈를"
            " 우선 검색해 담는다. 같은 사건이라도 오늘 새로운 후속 전개(추가 발표·주가 반응 변화 등)가"
            f" 있다면 그 새 전개 중심으로 다시 담아도 된다:\n{listed}"
        )

    # 2026-07-28 저녁 미국 브리핑 1회성 힌트 (사용자 요청) — 코카콜라(KO) 52주 신고가
    # 실측 확인(토스증권 API, 07-28 장중 고가 86.79 > 직전 52주 내 최고치 85.68).
    # 오늘 날짜에만 적용되고 다음 날부터는 자동으로 빠진다 — 상시 규칙으로 코드에 박지 않는다.
    if briefing_type == "us" and today == "2026-07-28":
        prompt += (
            "\n\n[오늘의 참고 소재] 코카콜라(KO)가 오늘 52주 신고가를 경신했다(실측 확인됨)."
            " 관련 뉴스(실적·배당·투자의견 등 상승 배경)가 검색되면 catalysts에 포함한다."
            " 검색되지 않으면 억지로 만들지 않는다."
        )

    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.3,
            max_output_tokens=1400,
        ),
    )
    if not response.text:
        finish = getattr(response.candidates[0], 'finish_reason', 'UNKNOWN') if response.candidates else 'NO_CANDIDATES'
        raise RuntimeError(f"Gemini returned empty response (finish_reason={finish})")
    raw = response.text.strip()

    # JSON 블록 추출 (마크다운 펜스·전후 텍스트 제거)
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    # { ... } 블록만 추출
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        raw = m.group(0)

    data = json.loads(raw)
    today_kst = datetime.now(KST).date()
    # 스키마 위반은 그라운딩 실패의 선행 신호다 — 프롬프트는 catalysts를 {date,text} 객체로
    # 요구하는데 문자열 배열로 오면, 검색이 아니라 형식만 흉내낸 출력일 가능성이 크다(§25·§28).
    # 날짜 미상 catalyst 자체는 허용(거시 촉매 보호)이라 버리지 않고 경고만 남긴다.
    _cats = data.get("catalysts")
    if isinstance(_cats, list) and _cats and not any(isinstance(c, dict) for c in _cats):
        print("[fetch_news] ⚠️ catalysts가 객체가 아닌 문자열 배열 — 그라운딩 실패 의심"
              f"({len(_cats)}건). 아래 실측·슬롯 게이트 결과를 함께 확인할 것.", file=sys.stderr)
    if isinstance(data.get("catalysts"), list):
        # 1차: 실적형 catalyst를 yfinance 실제 발표일로 검증(자기보고 날짜 무시), stale 제외
        cats = _drop_stale_earnings(data["catalysts"], today_kst)
        # 2차: 자기보고 날짜 기반 stale 제외 + 순수 문자열로 환원
        # 코스피 아침은 직전 미국장까지 창을 넓힌다(월요일 주말 공백 — _catalyst_cutoff)
        cats = _filter_stale_catalysts(
            cats, today_kst, cutoff=_catalyst_cutoff(briefing_type, today_kst)
        )
        # 3차: 2일+ 전 catalyst와 실질 중복인 재탕을 하드 제외(날짜 창 밖 재탕 백스톱)
        stale = _load_stale_catalysts(briefing_type, today_kst)
        data["catalysts"] = _drop_cross_day_recaps(cats, stale)
    # headlines·key_indicators도 stale 실적 서사를 제외 — Gemini가 텍스트에 심은 '엔비디아 실적 발표'
    # 류 날조가 catalysts만 걸러도 다른 필드로 Claude에 새어나가던 것을 차단(실측 지수는 fetch_data가
    # 별도 소스라 해당 항목이 통째 빠져도 §0 안전).
    for _fld in ("headlines", "key_indicators"):
        if isinstance(data.get(_fld), list):
            data[_fld] = _drop_stale_earnings(data[_fld], today_kst)
    # "…확인되지 않았습니다" 류 검색 실패 보고를 전 필드에서 제거 (이슈가 아니라 메타 서술)
    # + "B사"·"C은행"·"[기업]" 류 익명 플레이스홀더 주어를 담은 날조 항목도 함께 제거
    # + 실측 시장데이터와 방향이 반대인 주장도 제거 (유가 등)
    reality = _fetch_reality_snapshot()
    for _fld in ("catalysts", "headlines", "key_indicators"):
        if isinstance(data.get(_fld), list):
            data[_fld] = _drop_search_failure_notes(data[_fld])
            data[_fld] = _drop_placeholder_entities(data[_fld])
            data[_fld] = _drop_prompt_slot_echoes(data[_fld])
            data[_fld] = _drop_reality_contradictions(data[_fld], reality)
    return data


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def _is_retryable_error(e: Exception) -> bool:
    msg = str(e).upper()
    return (
        "429" in msg or "RESOURCE_EXHAUSTED" in msg or "QUOTA" in msg
        or "503" in msg or "UNAVAILABLE" in msg or "SERVICE_UNAVAILABLE" in msg
    )


EMPTY_NEWS = {
    "key_indicators": [],
    "catalysts": [],
    "headlines": [],
    "market_sentiment": "neutral",
}


def main():
    parser = argparse.ArgumentParser(description="Gemini Google Search grounding으로 시장 뉴스 수집·요약")
    parser.add_argument("--type", choices=["kospi", "kospi-close", "us"], required=True)
    args = parser.parse_args()

    print(f"[fetch_news] Fetching news via Gemini Google Search grounding (type={args.type})")

    summary = None
    last_err = None
    for attempt in range(1, 4):
        try:
            summary = fetch_and_summarize(args.type)
            print(
                f"[fetch_news] OK (attempt {attempt}): "
                f"{len(summary.get('key_indicators', []))} indicators, "
                f"{len(summary.get('headlines', []))} headlines"
            )
            break
        except Exception as e:
            last_err = e
            if _is_retryable_error(e) and attempt < 3:
                import time
                wait = 45 * attempt
                print(f"[fetch_news] 일시 오류({attempt}/3) — {wait}s 후 재시도: {e}", file=sys.stderr)
                time.sleep(wait)
            else:
                break

    if summary is None:
        print(f"[fetch_news] ERROR: {last_err}", file=sys.stderr)
        # stale 파일이 남아 있으면 downstream이 구 데이터를 쓰지 않도록 삭제
        stale = DATA_DIR / f"news_summary_{args.type}.json"
        if stale.exists():
            stale.unlink()
            print(f"[fetch_news] stale 뉴스 파일 삭제: {stale}", file=sys.stderr)
        # Gemini 일시 장애 시 빈 뉴스로 파이프라인 계속 진행
        print("[fetch_news] WARN: 빈 뉴스로 계속 진행 (Gemini 일시 장애)", file=sys.stderr)
        summary = EMPTY_NEWS

    summary["generated_at"] = datetime.now(KST).isoformat()
    out_path = DATA_DIR / f"news_summary_{args.type}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"[fetch_news] Saved → {out_path}")

    # 오늘 발행한 catalyst를 히스토리에 기록(다음 실행의 교차일 recap 판정 기준)
    if summary.get("catalysts"):
        _append_catalyst_history(args.type, datetime.now(KST).date(), summary["catalysts"])


if __name__ == "__main__":
    main()
