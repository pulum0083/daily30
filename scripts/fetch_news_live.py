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
[출력 규칙]
- title: 검색된 기사의 원문 제목을 그대로 사용하세요. 절대 새로 만들지 마세요.
- summary: 해당 기사의 리드 문장(첫 줄 또는 핵심 문장)을 그대로 가져오세요. 절대 새로 쓰지 마세요.

{avoid_block}아래 JSON 형식만 출력하세요 (마크다운·추가 텍스트 없이):
{{
  "market": {{"title": "기사 원문 제목", "summary": "기사 리드 문장"}},
  "stock":  {{"title": "기사 원문 제목", "summary": "기사 리드 문장"}}
}}
"""

# 장 전 준비 (06:00~08:59)
PROMPT_PRE_MARKET = """
지금 {today} {time} KST — 한국 장 시작 전입니다.
반드시 오늘 {today} 날짜의 최신 기사를 Google Search로 검색해 주세요. 어제 이전 날짜 기사는 사용하지 마세요.
오늘 코스피 개장에 영향을 줄 핵심 기사 2개를 찾아 주세요.

[선택 범위]
1. 시장 전체: 어젯밤 미국 나스닥·S&P500·SOX 등락, 오늘 코스피 방향에 영향을 줄 글로벌 변수 (환율·선물·VIX 등)
2. 주요 종목/자산: 어젯밤 미국 반도체·빅테크 중 오늘 국내 연관주에 영향을 줄 종목, 또는 오늘 코스피 예상 강세/약세 섹터
""" + _OUTPUT_RULES

# 장중 실시간 (09:00~15:29)
PROMPT_MARKET = """
지금 {today} {time} KST — 코스피 장중입니다.
반드시 오늘 {today} 장중 실시간 기사를 Google Search로 검색해 주세요. 어제 이전 날짜 기사는 사용하지 마세요.
지금 이 순간 투자자가 가장 주목할 기사 2개를 찾아 주세요.

[선택 범위]
1. 시장 전체: 코스피·코스닥 지수 흐름, 외국인·기관 수급, 환율, 글로벌 돌발 이슈
2. 주요 종목: 삼성전자·SK하이닉스·현대차·셀트리온·카카오·NAVER·KB금융·포스코 등 대형주, 또는 오늘 5% 이상 급등락 중인 종목
""" + _OUTPUT_RULES

# 마감 후 + 미국 프리마켓 (15:30~19:59)
PROMPT_POST_MARKET = """
지금 {today} {time} KST — 한국 장 마감 후, 미국 프리마켓 시간대입니다.
반드시 오늘 {today} 날짜의 최신 기사를 Google Search로 검색해 주세요. 어제 이전 날짜 기사는 사용하지 마세요.
오늘 코스피 마감과 오늘 밤 미국 시장 전망 관련 핵심 기사 2개를 찾아 주세요.

[선택 범위]
1. 시장 전체: 오늘 코스피·코스닥 마감 등락 원인, 또는 현재 미국 선물·프리마켓 방향과 원인
2. 주요 종목/자산: 오늘 국내 급등락 종목 사유, 또는 오늘 밤 미국 주목 종목 (실적·이벤트 등)
""" + _OUTPUT_RULES

# 미국 시장 (20:00~01:00)
PROMPT_US_MARKET = """
지금 {today} {time} KST — 미국 주식시장이 열려 있습니다 (또는 막 열렸습니다).
반드시 오늘 {today} 날짜의 미국 시장 실시간 기사를 Google Search로 검색해 주세요. 어제 이전 날짜 기사는 사용하지 마세요.
지금 미국 시장에서 가장 중요한 기사 2개를 찾아 주세요.

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

AVOID_BLOCK_TMPL = """[직전 이슈 중복 금지]
오늘 이미 다룬 이슈 전체:
{items}

중요: 제목이 달라도 위 목록에 등장하는 종목명·지수명·키워드가 같으면 중복입니다.
예) 직전에 '삼성전자·SK하이닉스 4%↑'를 다뤘다면, '삼성전자·SK하이닉스 4~7%↑'도 중복입니다.
시장 이슈와 종목 이슈 모두 완전히 다른 종목·주제를 선택하세요.
오전에 다룬 주제가 반복되면 독자가 장중 흐름을 파악할 수 없습니다. 시간대별로 다른 이슈를 발굴하세요.

"""

AVOID_KEYWORDS_TMPL = """[중복 키워드 금지 — 재시도]
아래 키워드가 포함된 뉴스는 이미 오늘 보도했습니다. 절대 선택하지 마세요:
{keywords}

완전히 다른 종목·섹터·이슈를 찾아서 선택하세요.

"""


def _title_keywords(title: str) -> set:
    """타이틀에서 2자 이상 한글·영문 단어 추출 (조사·불용어 제외)"""
    _stopwords = {'이슈', '뉴스', '기자', '오늘', '어제', '지난', '이번', '관련', '대한', '따른',
                  '코스피', '코스닥', '주가', '주식', '시장', '장중', '장세', '상승', '하락',
                  '전환', '반등', '급등', '급락', '강세', '약세', '회복', '마감'}
    words = set(re.findall(r'[가-힣A-Za-z]{2,}', title))
    return words - _stopwords


def _overlap_ratio(new_title: str, existing_title: str) -> float:
    """두 타이틀의 핵심 키워드 겹침 비율 (교집합 / 작은쪽 집합)"""
    wa = _title_keywords(new_title)
    wb = _title_keywords(existing_title)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / min(len(wa), len(wb))


def _find_duplicate(new_result: dict, existing_titles: list, threshold: float = 0.55) -> list:
    """새 결과의 market/stock 타이틀이 기존 타이틀과 중복이면 겹친 키워드 목록 반환, 없으면 []"""
    new_titles = [
        (new_result.get("market") or {}).get("title", ""),
        (new_result.get("stock") or {}).get("title", ""),
    ]
    blocked = set()
    for nt in new_titles:
        if not nt:
            continue
        for et in existing_titles:
            if _overlap_ratio(nt, et) >= threshold:
                blocked |= _title_keywords(nt) & _title_keywords(et)
    return sorted(blocked)


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
    return _clean_issue(parsed)


def _clean_issue(issue: dict) -> dict:
    """title·summary 에서 [ ] ( ) 괄호 태그 제거."""
    def clean(text: str) -> str:
        if not text:
            return text
        text = re.sub(r"\[.*?\]", "", text)   # [ET특징주], [서울=연합뉴스] 등
        text = re.sub(r"\(.*?\)", "", text)   # (특징주), (005930) 등
        return re.sub(r"\s{2,}", " ", text).strip()

    result = {}
    for key in ("market", "stock"):
        val = issue.get(key)
        if isinstance(val, dict):
            result[key] = {
                "title":   clean(val.get("title", "")),
                "summary": clean(val.get("summary", "")),
            }
        else:
            result[key] = val
    return result


def fetch_latest_issue(
    slot: str,
    today: str,
    time_str: str,
    recent_stock_titles=None,
    market_reality=None,
    extra_avoid_keywords=None,  # Python 사후 검증에서 발견한 중복 키워드
) -> dict:
    avoid_block = ""
    if extra_avoid_keywords:
        # 중복 키워드 명시 블록 (재시도 시 사용)
        keywords_str = ", ".join(extra_avoid_keywords)
        avoid_block = AVOID_KEYWORDS_TMPL.format(keywords=keywords_str)
    elif recent_stock_titles:
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

    # 오늘 전체 market·stock 이슈 타이틀 수집 — 중복 방지 프롬프트용
    all_today_titles: list = []
    if OUT_PATH.exists():
        try:
            existing = json.loads(OUT_PATH.read_text(encoding="utf-8"))
            if existing.get("date") == today:
                lt = existing.get("latest", {})
                if isinstance(lt, dict):
                    for key in ("market", "stock"):
                        t = (lt.get(key) or {}).get("title", "")
                        if t and t not in all_today_titles:
                            all_today_titles.append(t)
                for h in existing.get("history", []):  # 제한 없이 오늘 전체
                    for key in ("market", "stock"):
                        t = (h.get(key) or {}).get("title", "")
                        if t and t not in all_today_titles:
                            all_today_titles.append(t)
        except Exception:
            pass
    if all_today_titles:
        print(f"[fetch_news_live] 오늘 이슈 전체({len(all_today_titles)}개): {all_today_titles}")

    # MARKET 슬롯: 실측 방향 조회 (검증용)
    market_reality = _get_market_reality() if slot == "MARKET" else None
    if market_reality:
        print(f"[fetch_news_live] 실측 삼성전자 {market_reality['change_pct']:+.1f}%")

    latest = None
    blocked_keywords: list = []  # Python 사후 검증에서 발견한 중복 키워드
    for attempt in range(4):
        # 재시도 시 중복 키워드를 명시한 강화 프롬프트 사용
        avoid_titles = all_today_titles if not blocked_keywords else None
        extra_avoid_keywords = blocked_keywords if blocked_keywords else None
        try:
            latest = fetch_latest_issue(
                slot, today, time_str,
                avoid_titles or None,
                market_reality=market_reality,
                extra_avoid_keywords=extra_avoid_keywords,
            )
        except Exception as e:
            print(f"[fetch_news_live] ERROR (시도 {attempt+1}): {e}", file=sys.stderr)
            if attempt == 3:
                sys.exit(1)
            continue

        # 방향 모순 검증 (MARKET 슬롯 + 실측 데이터 있을 때만)
        if market_reality and _is_direction_conflict(latest, market_reality["change_pct"]):
            titles = f"{(latest.get('market') or {}).get('title','')} / {(latest.get('stock') or {}).get('title','')}"
            print(f"[fetch_news_live] ⚠️ 방향 모순 감지 (시도 {attempt+1}): {titles} — 재시도")
            continue

        # Python 사후 중복 검증: 오늘 기존 타이틀과 키워드 겹침 확인
        if all_today_titles:
            blocked_keywords = _find_duplicate(latest, all_today_titles)
            if blocked_keywords:
                titles = f"{(latest.get('market') or {}).get('title','')} / {(latest.get('stock') or {}).get('title','')}"
                print(f"[fetch_news_live] ⚠️ 중복 감지 (시도 {attempt+1}): {titles}")
                print(f"[fetch_news_live]   겹친 키워드: {blocked_keywords} — 재시도")
                if attempt < 3:
                    continue

        break

    # 기존 history 이어받기 (같은 날짜인 경우만)
    history: list = []
    if OUT_PATH.exists():
        try:
            existing = json.loads(OUT_PATH.read_text(encoding="utf-8"))
            if existing.get("date") == today:
                history = existing.get("history", [])
        except Exception:
            pass

    # 새로 수집한 latest를 history 맨 앞에 추가 — 첫 실행부터 섹션 표시되도록
    new_entry = {"time": time_str}
    new_entry.update(latest)
    history = [new_entry] + history
    history = history[:MAX_HISTORY]

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
