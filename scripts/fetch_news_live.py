# 이슈 브리핑 수집 스크립트
# 평일 06:00~익일 01:00 KST 운영. 실행 시각에 따라 프롬프트를 자동 분기한다.
#
# 구간별 프롬프트:
#   PRE_MARKET  (06:00~08:59) : 장 전 준비 — 전날 미국 마감 + 오늘 코스피 전망
#   MARKET      (09:00~15:29) : 장중 실시간 — 코스피·수급·급등락 이슈
#   POST_MARKET (15:30~19:59) : 마감 후 + 미국 프리마켓 — 한국 마감 정리·미국 개장 전
#   US_MARKET   (20:00~01:00) : 미국 시장 — 미국 장중 이슈 중심

import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST = timezone(timedelta(hours=9))
REPO_ROOT = Path(__file__).parent.parent
OUT_PATH = REPO_ROOT / "web" / "data" / "kospi-news-live.json"
MAX_HISTORY = 6


# ── 시간대 판별 ──────────────────────────────────────────────────────────────

def get_slot(hour: int, minute: int) -> str:
    """KST 시·분을 받아 구간 문자열을 반환한다.

    운영 구간:
      MARKET      09:00~15:29  장중 실시간
      POST_MARKET 16:35~21:29  마감 후 + 미국 프리마켓
      US_MARKET   21:30~01:00  미국 시장
    운영 외 시간은 MARKET 폴백 (워크플로우가 해당 시간에 실행하지 않음)
    """
    total = hour * 60 + minute
    if 540 <= total < 930:    # 09:00~15:29
        return "MARKET"
    if 995 <= total < 1290:   # 16:35~21:29
        return "POST_MARKET"
    # 21:30~23:59 또는 00:00~01:00(익일)
    if total >= 1290 or total <= 60:
        return "US_MARKET"
    return "MARKET"           # 운영 외 시간 폴백


# ── 프롬프트 템플릿 ─────────────────────────────────────────────────────────

# 공통 출력 규칙 (모든 프롬프트에 삽입)
_OUTPUT_RULES = """
[타이틀 규칙]
- 각 15자 이내, 지금 일어나고 있는 일을 짧고 강하게
- "지속", "흐름", "동향" 같은 밋밋한 단어 금지
- 구체적 숫자·행위자 포함 (예: "나스닥 2% 급락", "외국인 20일째 매도", "원화 1545 돌파")
- 시장 감정 표현 허용 (질주, 급락, 흔들, 버팀, 폭발 등)

[요약 규칙]
- 각 40자 이내, 해요체(~있어요, ~이에요, ~해요)
- 투자자 시각 — "왜 지금 이게 중요한지"를 한 줄로
- 원인 → 결과 구조 (예: "OO 때문에 XX가 흔들리고 있어요")

{avoid_block}아래 JSON 형식만 출력하세요 (마크다운·추가 텍스트 없이):
{{
  "market": {{"title": "시장 이슈 제목", "summary": "한 줄 요약"}},
  "stock":  {{"title": "종목/자산 이슈 제목", "summary": "한 줄 요약"}}
}}
"""

# 장 전 준비 (06:00~08:59)
PROMPT_PRE_MARKET = """
지금 {today} {time} KST — 한국 장 시작 전입니다.
반드시 오늘 {today} 날짜의 최신 기사를 Google Search로 검색해 정리해 주세요. 어제 이전 날짜 기사는 사용하지 마세요.
오늘 코스피 개장에 영향을 줄 핵심 이슈 2개를 찾아 정리해 주세요.

[선택 범위]
1. 시장 전체: 어젯밤 미국 나스닥·S&P500·SOX 등락, 오늘 코스피 방향에 영향을 줄 글로벌 변수 (환율·선물·VIX 등)
2. 주요 종목/자산: 어젯밤 미국 반도체·빅테크 중 오늘 국내 연관주에 영향을 줄 종목, 또는 오늘 코스피 예상 강세/약세 섹터
""" + _OUTPUT_RULES

# 장중 실시간 (09:00~15:29)
PROMPT_MARKET = """
지금 {today} {time} KST — 코스피 장중입니다.
반드시 오늘 {today} 장중 실시간 기사를 Google Search로 검색해 정리해 주세요. 어제 이전 날짜 기사는 사용하지 마세요.
지금 이 순간 투자자가 가장 주목해야 할 이슈 2개를 찾아 정리해 주세요.

[선택 범위]
1. 시장 전체: 코스피·코스닥 지수 흐름, 외국인·기관 수급, 환율, 글로벌 돌발 이슈
2. 주요 종목: 삼성전자·SK하이닉스·현대차·셀트리온·카카오·NAVER·KB금융·포스코 등 대형주, 또는 오늘 5% 이상 급등락 중인 종목
""" + _OUTPUT_RULES

# 마감 후 + 미국 프리마켓 (15:30~19:59)
PROMPT_POST_MARKET = """
지금 {today} {time} KST — 한국 장 마감 후, 미국 프리마켓 시간대입니다.
반드시 오늘 {today} 날짜의 최신 기사를 Google Search로 검색해 정리해 주세요. 어제 이전 날짜 기사는 사용하지 마세요.
오늘 코스피 마감 정리와 오늘 밤 미국 시장 전망에 필요한 핵심 이슈 2개를 찾아 정리해 주세요.

[선택 범위]
1. 시장 전체: 오늘 코스피·코스닥 마감 등락 원인 요약, 또는 현재 미국 선물·프리마켓 방향과 원인
2. 주요 종목/자산: 오늘 국내 급등락 종목 사유, 또는 오늘 밤 미국 주목 종목 (실적·이벤트 등)
""" + _OUTPUT_RULES

# 미국 시장 (20:00~01:00)
PROMPT_US_MARKET = """
지금 {today} {time} KST — 미국 주식시장이 열려 있습니다 (또는 막 열렸습니다).
반드시 오늘 {today} 날짜의 미국 시장 실시간 기사를 Google Search로 검색해 정리해 주세요. 어제 이전 날짜 기사는 사용하지 마세요.
지금 미국 시장에서 가장 중요한 이슈 2개를 찾아 정리해 주세요.

[선택 범위]
1. 시장 전체: S&P500·나스닥·다우 장중 등락 원인, 연준 발언·경제지표 발표, VIX·달러·국채금리 움직임
2. 주요 종목/자산: 지금 미국 시장에서 급등락 중인 빅테크·반도체 종목 (NVDA·AAPL·MSFT·AMD·TSMC 등), 또는 실적 발표 종목
""" + _OUTPUT_RULES

PROMPT_MAP = {
    "MARKET":      PROMPT_MARKET,
    "POST_MARKET": PROMPT_POST_MARKET,
    "US_MARKET":   PROMPT_US_MARKET,
}

# 방향 모순 키워드 (하락장에서 상승 표현, 상승장에서 하락 표현)
_UP_WORDS      = re.compile(r"반등|상승|급등|오름|강세|올라|뛰어|돌파|신고가")
_DOWN_WORDS    = re.compile(r"하락|급락|폭락|무너|붕괴|추락|약세|내려|곤두박")
# 극단적 폭락/급등 표현 — 시장 방향과 조금만 반대여도 모순으로 처리
_EXTREME_CRASH = re.compile(r"서킷브레이커|서킷 브레이커|붕괴")


def _get_market_reality():
    """삼성전자 현재가로 오늘 장중 방향을 추정한다. 실패 시 None 반환."""
    try:
        sys.path.insert(0, str(REPO_ROOT))
        import scripts.toss_client as tc
        # 현재가
        prices = tc.get_prices(["005930"])
        if not prices:
            return None
        current = float(prices[0].get("lastPrice") or 0)
        if not current:
            return None
        # 전일 종가 (오늘 캔들 제외)
        today_str = datetime.now(KST).strftime("%Y-%m-%d")
        candles = tc.get_candles("005930", interval="1d", count=5)
        prev_closes = [
            float(c["closePrice"]) for c in candles
            if c.get("closePrice") and c.get("timestamp", "")[:10] != today_str
        ]
        if not prev_closes:
            return None
        prev_close = prev_closes[-1]  # 가장 최근 전일 종가
        change_pct = (current - prev_close) / prev_close * 100
        return {"change_pct": round(change_pct, 2), "current": current, "prev_close": prev_close}
    except Exception as e:
        print(f"[fetch_news_live] market reality 조회 실패 (무시): {e}")
        return None


def _is_direction_conflict(latest: dict, change_pct: float) -> bool:
    """시장 등락률과 이슈 타이틀 방향이 모순인지 확인한다."""
    titles = " ".join([
        (latest.get("market") or {}).get("title", ""),
        (latest.get("stock") or {}).get("title", ""),
    ])
    # 극단적 폭락 표현(붕괴·서킷브레이커)은 시장이 조금이라도 양전이면 모순
    if change_pct > 0.5 and _EXTREME_CRASH.search(titles):
        return True
    # 일반 방향 키워드: 임계값 ±1.5%로 낮춤 (기존 ±3%)
    if change_pct <= -1.5 and _UP_WORDS.search(titles):
        return True
    if change_pct >= 1.5 and _DOWN_WORDS.search(titles):
        return True
    return False

AVOID_BLOCK_TMPL = """[직전 2회 이슈 — 아래 시장·종목 주제와 동일하거나 매우 유사한 내용은 선택하지 마세요]
{items}

시장 이슈와 종목 이슈 모두 위 목록과 겹치지 않는 새로운 주제를 선택하세요.

"""


# ── API 키 ────────────────────────────────────────────────────────────────────

def get_gemini_api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        cfg = REPO_ROOT / "config.json"
        if cfg.exists():
            with open(cfg, encoding="utf-8") as f:
                config = json.load(f)
            key = config.get("gemini", {}).get("api_key", "")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not found in env or config.json")
    return key


# ── Gemini 호출 ───────────────────────────────────────────────────────────────

def _call_gemini(prompt: str) -> dict:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=get_gemini_api_key())
    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.7,
            max_output_tokens=400,
        ),
    )
    raw = response.text
    if not raw:
        raise RuntimeError("Gemini가 빈 응답을 반환했습니다")
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        raw = m.group(0)
    parsed = json.loads(raw)
    if "market" not in parsed and "title" in parsed:
        parsed = {"market": parsed, "stock": None}
    return parsed


def fetch_latest_issue(
    slot: str,
    today: str,
    time_str: str,
    recent_stock_titles=None,
    market_reality=None,   # _get_market_reality() 결과
) -> dict:
    avoid_block = ""
    if recent_stock_titles:
        items = "\n".join(f"- {t}" for t in recent_stock_titles)
        avoid_block = AVOID_BLOCK_TMPL.format(items=items)

    prompt_tmpl = PROMPT_MAP[slot]
    prompt = prompt_tmpl.format(today=today, time=time_str, avoid_block=avoid_block)

    # MARKET 슬롯: 실측 방향을 프롬프트에 주입 (모든 시도에 적용)
    if slot == "MARKET" and market_reality:
        chg = market_reality["change_pct"]
        direction = "하락" if chg < 0 else "상승"
        header = (
            f"\n\n[실측 데이터 — 반드시 반영]\n"
            f"삼성전자 현재 등락률: {chg:+.1f}% ({direction})\n"
        )
        if chg <= -1.5:
            prompt += header + "이 방향과 모순되는 '반등', '급등', '상승' 등의 표현은 사용하지 마세요."
        elif chg >= 1.5:
            prompt += header + "이 방향과 모순되는 '급락', '폭락', '하락', '붕괴' 등의 표현은 사용하지 마세요."
        else:
            # 소폭 등락 구간: 방향 안내 + 극단적 표현 모두 금지
            prompt += header + "시장이 소폭 움직이는 중이에요. '붕괴', '폭락', '서킷브레이커', '급등', '급락' 등 극단적 표현은 사용하지 마세요."

    return _call_gemini(prompt)


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main() -> None:
    now = datetime.now(KST)
    today = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")
    slot = get_slot(now.hour, now.minute)

    print(f"[fetch_news_live] {today} {time_str} KST — 슬롯={slot} — Gemini 이슈 수집 시작")

    # 직전 2회 market·stock 이슈 타이틀 수집 — 중복 방지용
    # 가장 최신 이슈(latest)와 그 이전 이슈(history[0])의 market·stock 타이틀을 모두 수집한다.
    recent_stock_titles: list = []
    if OUT_PATH.exists():
        try:
            existing = json.loads(OUT_PATH.read_text(encoding="utf-8"))
            if existing.get("date") == today:
                # 직전 이슈 (latest)
                lt = existing.get("latest", {})
                if isinstance(lt, dict):
                    for key in ("market", "stock"):
                        t = (lt.get(key) or {}).get("title", "")
                        if t and t not in recent_stock_titles:
                            recent_stock_titles.append(t)
                # 그 이전 이슈 (history[0])
                for h in existing.get("history", [])[:1]:
                    for key in ("market", "stock"):
                        t = (h.get(key) or {}).get("title", "")
                        if t and t not in recent_stock_titles:
                            recent_stock_titles.append(t)
        except Exception:
            pass
    if recent_stock_titles:
        print(f"[fetch_news_live] 중복 방지 이슈 목록: {recent_stock_titles}")

    # MARKET 슬롯: 실측 방향 조회 (검증용)
    market_reality = _get_market_reality() if slot == "MARKET" else None
    if market_reality:
        print(f"[fetch_news_live] 실측 삼성전자 {market_reality['change_pct']:+.1f}%")

    latest = None
    for attempt in range(3):
        try:
            latest = fetch_latest_issue(
                slot, today, time_str,
                recent_stock_titles or None,
                market_reality=market_reality,  # 첫 시도부터 항상 주입
            )
        except Exception as e:
            print(f"[fetch_news_live] ERROR (시도 {attempt+1}): {e}", file=sys.stderr)
            if attempt == 2:
                sys.exit(1)
            continue

        # 방향 모순 검증 (MARKET 슬롯 + 실측 데이터 있을 때만)
        if market_reality and _is_direction_conflict(latest, market_reality["change_pct"]):
            titles = f"{(latest.get('market') or {}).get('title','')} / {(latest.get('stock') or {}).get('title','')}"
            print(f"[fetch_news_live] ⚠️ 방향 모순 감지 (시도 {attempt+1}): {titles} — 재시도")
            continue
        break

    # 기존 latest를 history 맨 앞에 추가 (같은 날짜인 경우에만 이어받음)
    history: list = []
    if OUT_PATH.exists():
        try:
            existing = json.loads(OUT_PATH.read_text(encoding="utf-8"))
            if existing.get("date") == today:
                prev = existing.get("latest")
                if prev:
                    entry = {"time": existing.get("updated_at", "")}
                    if "market" in prev:
                        entry.update(prev)
                    elif prev.get("title") and prev.get("title") != "오늘의 이슈 준비 중":
                        entry["market"] = prev
                    if entry.get("market"):
                        history = [entry]
                history += existing.get("history", [])
                history = history[:MAX_HISTORY]
        except Exception:
            pass

    data = {
        "date": today,
        "updated_at": time_str,
        "slot": slot,           # 디버깅·프론트 활용용
        "latest": latest,
        "history": history,
    }
    OUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[fetch_news_live] Saved → {OUT_PATH}")

    # 날짜별 아카이브 저장 — 과거 브리핑 스코어보드에서 그날 이슈 표시용
    archive_path = OUT_PATH.parent / f"kospi-news-{today}.json"
    archive_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[fetch_news_live] Archive → {archive_path.name}")


if __name__ == "__main__":
    main()
