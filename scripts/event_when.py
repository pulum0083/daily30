# 미국 경제 이벤트 시각을 브리핑 날짜(KST) 기준 '오늘/내일 새벽'으로 바꾸는 단일 소스 — 프롬프트 지시와 발행 직전 교정이 함께 쓴다
"""2026-10-28 실사고: 07:25 코스피 아침 브리핑이 FOMC 결과(10/28 14:00 ET = 10/29 03:00 KST)를
"오늘 새벽 FOMC 결과 발표가 예정돼 있어요"라고 썼다. 07:25에 '오늘 새벽'은 이미 지났고,
실제로는 '내일 새벽'이다. 미국 날짜(ET) 기준으로 '오늘'을 쓴 것이다.

캘린더(fetch_data._bucket_calendar_events)는 이미 KST 시각(date_kst)을 갖고 있으므로
그 시각을 브리핑 날짜와 비교해 한국어 상대 표기를 결정론으로 만든다.
"""
import re
from datetime import date, datetime

# 미국 이벤트 제목 조각 → 한국어 본문에서 그 이벤트를 가리키는 말
_ALIASES = [
    ("FOMC", ("FOMC", "연준")),
    ("Federal Funds", ("FOMC", "연준")),
    ("Non-Farm", ("고용", "비농업")),
    ("Unemployment", ("실업률",)),
    ("CPI", ("CPI", "소비자물가")),
    ("PPI", ("PPI", "생산자물가")),
    ("PCE", ("PCE",)),
    ("GDP", ("GDP",)),
    ("Retail Sales", ("소매판매",)),
    ("ISM", ("ISM",)),
]
_ACRONYM = re.compile(r"\b([A-Z]{3,5})\b")
_DAY_WORDS = ("오늘", "내일", "모레")
_EARLY_WORDS = ("새벽", "아침", "오전")
_DAY_TIME = re.compile(r"(오늘|금일|내일|모레)(\s*)(새벽|아침|오전|오후|저녁|밤)")
# 문장 경계 — 마침표 뒤 공백·줄바꿈. "4.00%" 같은 소수점에서 끊지 않는다
_SENT_SPLIT = re.compile(r"((?<=[.!?])\s+|\n+)")
_WD = "월화수목금토일"


def _parse_kst(s):
    try:
        return datetime.strptime(str(s)[:16], "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return None


def part_of_day(hour: int) -> str:
    if hour < 6:
        return "새벽"
    if hour < 9:
        return "아침"
    if hour < 12:
        return "오전"
    if hour < 18:
        return "오후"
    if hour < 21:
        return "저녁"
    return "밤"


def day_word(dt: datetime, today: date):
    """브리핑 날짜 기준 '오늘'·'내일'·'모레'. 그 밖이면 None."""
    diff = (dt.date() - today).days
    return _DAY_WORDS[diff] if 0 <= diff < len(_DAY_WORDS) else None


def when_label(date_kst: str, today: date):
    """'2026-10-29 03:00 KST' → '내일 새벽 3시'. 사흘 넘게 떨어지면 '10/31(토) 새벽 3시'."""
    dt = _parse_kst(date_kst)
    if not dt:
        return None
    clock = f"{dt.hour if dt.hour <= 12 else dt.hour - 12}시" + (f" {dt.minute}분" if dt.minute else "")
    if dt.hour == 0:
        clock = "0시" + (f" {dt.minute}분" if dt.minute else "")
    head = day_word(dt, today) or f"{dt.month}/{dt.day}({_WD[dt.weekday()]})"
    return f"{head} {part_of_day(dt.hour)} {clock}"


def keywords(title: str) -> set:
    kws = set(_ACRONYM.findall(title or ""))
    for frag, words in _ALIASES:
        if frag in (title or ""):
            kws.update(words)
    return kws


def us_events(calendar) -> list:
    """캘린더(today+upcoming)에서 미국 이벤트만 [{title, dt, kws}]로."""
    out = []
    for bucket in ("today", "upcoming"):
        for e in ((calendar or {}).get(bucket) or []):
            if not isinstance(e, dict) or e.get("country") != "USD":
                continue
            dt = _parse_kst(e.get("date_kst"))
            kws = keywords(e.get("title", ""))
            if dt and kws:
                out.append({"title": e.get("title", ""), "dt": dt, "date_kst": e.get("date_kst"), "kws": kws})
    return out


def fix_day_words(text: str, events: list, today: date) -> str:
    """문장 안 '오늘/내일 새벽·아침·오전'이 같은 문장의 미국 이벤트 실제 KST 날짜와 다르면 고친다.

    한 문장에 이벤트가 여럿이면 그 표현에 가장 가까운 이벤트를 기준으로 삼는다.
    시간대 말과 이벤트 시각이 오전/오후로 엇갈리면(예: '오늘 새벽'인데 가장 가까운 이벤트가 밤 9시) 판단하지 않는다.
    '오늘 밤'이 다음 날 새벽 이벤트를 가리키는 건 우리말로 자연스러우니 그대로 둔다.
    """
    if not text or not events:
        return text

    def fix_sentence(sent):
        hits = []   # (위치, 이벤트)
        for ev in events:
            for k in ev["kws"]:
                for km in re.finditer(re.escape(k), sent):
                    hits.append((km.start(), ev))
        if not hits:
            return sent

        def repl(dm):
            pos = dm.start()
            ev = min(hits, key=lambda h: abs(h[0] - pos))[1]
            hour, tw = ev["dt"].hour, dm.group(3)
            word = "오늘" if dm.group(1) == "금일" else dm.group(1)
            right = day_word(ev["dt"], today)
            if tw in ("밤", "저녁") and hour < 6 and right and _DAY_WORDS.index(right) == _DAY_WORDS.index(word) + 1:
                return dm.group(0)   # '오늘 밤'(= 내일 새벽 3시) — 자연스러운 말투
            if (hour < 12) != (tw in _EARLY_WORDS):
                return dm.group(0)   # 시간대가 엇갈리면 다른 이벤트 얘기일 수 있다
            if not right or right == word:
                return dm.group(0)
            return right + dm.group(2) + part_of_day(hour)
        return _DAY_TIME.sub(repl, sent)

    parts = _SENT_SPLIT.split(text)   # 짝수 칸이 문장, 홀수 칸이 경계
    return "".join(fix_sentence(p) if i % 2 == 0 else p for i, p in enumerate(parts))
