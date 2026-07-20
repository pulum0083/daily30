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
# 브리핑 타입별 검색·요약 프롬프트
# ─────────────────────────────────────────────────────────────────────────────

KOSPI_PROMPT = """\
오늘({today}) 한국 코스피 시장 예측에 필요한 최신 뉴스를 Google Search로 검색해 분석해줘.

검색할 내용:
- 어제(현지 시각) 미국 나스닥·S&P500 등락 원인과 수치
- 오늘 코스피 개장에 영향을 줄 외국인 수급·ETF 자금 흐름
- 오늘 예정된 주요 경제 지표 또는 이벤트 (FOMC, CPI 등)
- 반도체·기술주 관련 최신 이슈 (NVDA, TSMC 등)
- 원유·환율 최신 동향
- **주도주 기업 이벤트**: 코스피 대형주(삼성전자·SK하이닉스·현대차 등)의 상장·ADR·M&A·지분매각·신사업 진출·대형 수주·설비투자·실적 발표
- **[임시 2026-07-12 추가, 테마 소멸 시 제거]** SK하이닉스 ADR 미국 상장 이후 한국 증시(특히 SK하이닉스 본주) 반응·수급 대응 — 이번 주 핵심 테마이므로 명시 검색
- **인과 촉매**: 특정 섹터/주도주 등락의 '원인'이 된 사건 — 특히 미국 빅테크 전략 뉴스(클라우드·자체 칩 설계·감산·투자)가 한국 반도체·2차전지에 미치는 파급(read-through)
- **AI 모델 개발사 이슈(비상장이지만 핵심 촉매)**: OpenAI·Anthropic의 신모델 출시, 대형 칩·HBM·클라우드 계약, 대규모 투자·펀딩 — 이런 AI 인프라 수요 신호가 SK하이닉스·삼성전자 HBM·반도체 투자심리에 미치는 파급

[key_indicators 작성 규칙]
- 반드시 실제 수치(%, 금액)를 포함한다
- 오늘 코스피에 직접 영향을 줄 이슈만 포함한다
- 포함 금지: YTD 수익률, 연간 상승률, 애널리스트 중장기 전망

[catalysts 작성 규칙]
- 오늘 코스피 주도주·섹터를 움직일 '사건' 중심 뉴스만 담는다 (지수 등락률 나열이 아님)
- 각 항목은 "무슨 사건 → 어느 종목·섹터에 왜 영향" 형태의 한 문장. 실제로 검색된 사건만 담고, 없으면 빈 배열 []
- 문장 형태 예시(회사명·사건은 형식 참고용일 뿐이다 — 절대 그대로 베끼지 말고, 오늘 실제 검색으로 찾은 회사명·사건·수치로만 채운다): "[해외 기업]의 [발표·이벤트] → [한국 관련 섹터·종목]에 [영향 방향]"

출력 형식 (JSON만, 다른 텍스트 없이):
{{
  "key_indicators": [
    "어제 미국 증시 관련 구체적 이슈 (수치 포함)",
    "외국인 수급·ETF 관련 이슈",
    "오늘 예정된 경제 지표 또는 이벤트",
    "반도체·기술주 이슈",
    "원유·환율 동향"
  ],
  "catalysts": [
    "주도주·섹터를 움직인 사건 → 영향 (실제 검색된 것만, 없으면 이 배열은 비운다)"
  ],
  "headlines": [
    "오늘 코스피 방향에 직접 영향을 줄 헤드라인 1",
    "헤드라인 2",
    "헤드라인 3"
  ],
  "market_sentiment": "bullish or bearish or neutral"
}}
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
- **catalysts의 각 항목은 반드시 `{{"date": "YYYY-MM-DD", "text": "사건 → 영향"}}` 형태의 객체다** (문자열이 아니다). `date`는 그 사건이 실제 발생·발표된 날짜(실적이면 실적 발표일, 지정학·정책·유가면 사건 발생일)로, 검색으로 확인한 실제 날짜만 넣고 추측하지 않는다. `text`는 "무슨 사건 → 어느 종목·섹터에 왜 영향" 한 문장.
- **`date`는 오늘({today}) 또는 어제만 허용한다.** 이틀 이상 전에 발생·발표된 사건은, 오늘 후속 기사·리캡·주가 잔여 반응이 검색되더라도 담지 않는다. 특히 어닝(실적)은 며칠 전 발표분이 계속 검색된다고 매일 재등장시키지 않는다 — 발표일이 이틀 이상 전이면 catalysts에 넣지 말 것. 유가·지정학·정책 등 사건형 촉매도 오늘·어제 새로 전개된 것만 담는다.
- 실제로 검색된 사건만 담고, 없으면 빈 배열 []
- **오늘/어제 발표된 주요 기업 실적(어닝)은 catalysts에 최우선으로 담는다** — 실적 서프라이즈·가이던스·경영진 발언이 해당 종목뿐 아니라 다른 종목·섹터로 파급된 경우(read-through)를 인과로 정리한다.
- **개장 전 실적으로 프리마켓에서 이미 움직인 섹터도 catalysts에 담는다** — 이 브리핑은 프리마켓 시점에 나가므로, 개장 전 반응은 오늘 세션을 예고하는 핵심 촉매다.
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
    {{"date": "YYYY-MM-DD", "text": "주도주·섹터를 움직인 사건 → 영향 (실제 검색된 것만·오늘/어제 발생분만, 없으면 이 배열은 비운다)"}}
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


def _filter_stale_catalysts(catalysts: list, today: date) -> list:
    """catalyst별 발생일을 읽어 오늘/어제(today-1)보다 오래된 사건은 버리고, 남긴 항목은
    순수 문자열(사건 → 영향)로 반환한다. 다운스트림(call_claude)은 문자열 리스트를 기대한다.

    항목 형태 2가지를 모두 받는다:
      · {"date": "YYYY-MM-DD", "text": "사건 → 영향"}  ← US 프롬프트가 요구하는 구조화 형태
      · "사건 → 영향"  또는  "[YYYY-MM-DD] 사건 → 영향"  ← 문자열/인라인 접두사(하위호환)

    2026-07-15~20 실사고: 7/15 발표된 ASML 2분기 실적이 사흘 넘게 '오늘 프리마켓 촉매'로
    재등장했다(_load_prev_catalysts 소프트 중복 방지만으론 못 막음). 이 함수가 하드 게이트다.
    날짜 미상 항목은 버리지 않는다 — 유가·지정학 등 날짜 태그 없이 오는 거시 촉매를 보호한다.
    완전성보다 정합성이 우선이되, '날짜 미상'과 '오래됨'은 구분한다."""
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


def fetch_and_summarize(briefing_type: str) -> dict:
    """Gemini Google Search grounding으로 최신 뉴스를 검색·요약해 dict로 반환한다."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise RuntimeError("google-genai not installed. Run: pip install google-genai")

    client = genai.Client(api_key=get_gemini_api_key())
    today = datetime.now(KST).strftime("%Y-%m-%d")
    prompt = PROMPT_MAP[briefing_type].format(today=today)

    prev_items = _load_prev_catalysts(briefing_type)
    if prev_items:
        listed = "\n".join(f"- {x}" for x in prev_items)
        prompt += (
            "\n\n[중복 방지] 아래는 직전 브리핑에서 이미 다룬 이슈다. 오늘 검색 결과가 이 목록과"
            " 같은 사건이면(단순 재보도·반복 요약) 우선순위를 낮추고 실제로 새로 발생한 다른 이슈를"
            " 우선 검색해 담는다. 같은 사건이라도 오늘 새로운 후속 전개(추가 발표·주가 반응 변화 등)가"
            f" 있다면 그 새 전개 중심으로 다시 담아도 된다:\n{listed}"
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
    if isinstance(data.get("catalysts"), list):
        data["catalysts"] = _filter_stale_catalysts(data["catalysts"], datetime.now(KST).date())
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


if __name__ == "__main__":
    main()
