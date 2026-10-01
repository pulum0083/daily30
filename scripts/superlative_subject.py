# 최상급 표현('사상 최고치' 등)이 어느 대상의 주장인지 문장 안에서 가려내는 공용 판정기
"""최상급 표현의 주어 판정 — fetch_news(수집 단계)와 validate_analysis(발행 직전)가 함께 쓴다.

2026-10-01 실사고(§59): "미국 10년물 국채금리는 … 2002년 5월 이후 최고치를 기록했어요.
이 금리 부담이 다우를 -0.86% 끌어내렸어요." — 최고치의 주어는 국채금리인데, 지수명 앞뒤
25자 창이 문장 경계를 넘어 '다우'를 잡아 "다우 '최고' 주장"으로 판정했고, 스칼라 산문이라
코스피 아침 브리핑 전체가 차단됐다.

판정 규칙 — 최상급 표현 하나마다 주어를 하나만 정한다.
  ① 같은 문장 안에서만 본다(문장 경계를 넘지 않는다).
  ② 최상급 **앞**에서 가장 가까운 대상(지수 또는 경쟁 주어)이 주어다. 그 사이에
     대조 접속('지만'·'반면'·'달리')이 있거나 거리가 MAX_GAP을 넘으면 주어가 없다.
  ③ 앞에서 못 정했을 때만, 최상급 **바로 뒤**에 관형형('…를 경신한 나스닥')으로 이어지는
     대상을 주어로 본다. '…치솟으며 다우를'처럼 연결형이면 주어가 아니다.
주어를 정할 수 없으면 아무 지수의 주장도 아니다(fail-open) — 정상 브리핑 차단보다 낫다.
"""
from __future__ import annotations

import re

HIGH_RE = re.compile(r"(?:사상\s*최고|역대\s*최고|최고치|신고가|사상최고)")
LOW_RE = re.compile(r"(?:사상\s*최저|역대\s*최저|최저치|신저가|사상최저)")

# 지수가 아닌데 최상급의 주어가 될 수 있는 대상. 이 중 하나가 지수명보다 최상급에 가까우면
# 그 최상급은 지수의 주장이 아니다. 지수명의 부분 문자열이 되면 안 된다('금'처럼 짧은 말은
# '지금'·'자금'에 걸리므로 넣지 않는다).
COMPETING_SUBJECTS = (
    "국채금리", "국채 금리", "국채수익률", "국채 수익률", "국채", "금리", "수익률", "채권",
    "유가", "국제유가", "WTI", "브렌트", "원유", "천연가스",
    "금값", "금 가격", "국제 금", "금 선물", "은값", "구리",
    "달러", "환율", "원화", "엔화", "위안화", "유로화",
    "비트코인", "가상자산", "암호화폐",
    "코스피", "코스닥", "VIX", "변동성",
    "물가", "CPI", "PCE", "실업률", "고용",
    "주가", "시가총액", "시총",
)

MAX_GAP = 30  # 주어와 최상급 사이 최대 글자 수
_CONTRAST_RE = re.compile(r"(?:지만|반면|달리)")
# 최상급 뒤 관형형으로 대상을 꾸미는 형태: '최고치를 경신한 나스닥', '최고치인 다우'
_ADNOMINAL_TAIL_RE = re.compile(r"^[^,.!?\n]{0,12}?(?:한|인|운|쓴|던)\s*$")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+|\n+")


def _mentions(sentence: str, index_names) -> list:
    """문장 안의 대상 언급 [(start, end, index_name|None)] — 긴 이름부터 잡고 자리를 가린다.

    index_names는 [(이름, 키)] — 키가 None이면 검증 대상이 아닌 지수(선물 등)로, 경쟁 주어처럼
    자리만 차지한다. 경쟁 주어도 key=None으로 기록한다.
    """
    cands = [(n, k) for n, k in index_names] + [(n, None) for n in COMPETING_SUBJECTS]
    cands.sort(key=lambda x: -len(x[0]))
    taken = [False] * len(sentence)
    out = []
    for name, key in cands:
        for m in re.finditer(re.escape(name), sentence):
            if any(taken[m.start():m.end()]):
                continue
            for i in range(m.start(), m.end()):
                taken[i] = True
            out.append((m.start(), m.end(), name if key is not None else None))
    out.sort()
    return out


def _owner(sentence: str, sup: re.Match, mentions) -> str | None:
    """최상급 표현 sup의 주어 지수명(없으면 None)."""
    before = [mt for mt in mentions if mt[1] <= sup.start()]
    if before:
        s, e, name = before[-1]
        gap = sentence[e:sup.start()]
        if len(gap) <= MAX_GAP and not _CONTRAST_RE.search(gap):
            return name  # 경쟁 주어면 None
        return None
    after = [mt for mt in mentions if mt[0] >= sup.end()]
    if after:
        s, e, name = after[0]
        if _ADNOMINAL_TAIL_RE.search(sentence[sup.end():s]):
            return name
    return None


def attributed_superlatives(text: str, index_names) -> list:
    """text에서 지수가 주어인 최상급 주장 [(지수명, 'high'|'low')]을 돌려준다(중복 제거)."""
    found = []
    for sentence in _SENTENCE_SPLIT_RE.split(text or ""):
        if not (HIGH_RE.search(sentence) or LOW_RE.search(sentence)):
            continue
        mentions = _mentions(sentence, index_names)
        for kind, rx in (("high", HIGH_RE), ("low", LOW_RE)):
            for sup in rx.finditer(sentence):
                name = _owner(sentence, sup, mentions)
                if name and (name, kind) not in found:
                    found.append((name, kind))
    return found
