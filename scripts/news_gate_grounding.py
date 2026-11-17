# 뉴스 그라운딩 게이트 — 항목 모양 통일, 수집 실패 신호 판정, 익명 주어·슬롯 에코·검색 실패 자백 제외

from __future__ import annotations
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from news_common import DATA_DIR


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
    # "A사"·"B사의"·"A 사" — 단일 영문 대문자 + 사 (뒤에 조사·구두점·공백만 허용)
    # \s* — 2026-07-30 실사고: 공백 하나("C 은행")로 게이트가 통째로 우회됐다.
    r"(?<![A-Za-z0-9])[A-Z]\s*사(?=[\s,.·)]|의|는|가|도|을|를|와|과|에|만|$)|"
    # "C은행"·"C 은행"·"D증권"·"E그룹"·"F기업" — 접미어 자체가 명확해 뒤 제약 불필요
    r"(?<![A-Za-z0-9])[A-Z]\s*(?:은행|증권|그룹|기업|테크)|"
    # 프롬프트 예시의 대괄호 슬롯이 그대로 남은 형태 — "[기업]의 …"
    r"\[[가-힣][가-힣·\s]*\]|"
    # 기호 마스킹 — "○○사", "XX사", "△△ 반도체"
    r"[○◯●△▲□■X×]{2,}|"
    # 한국어 익명 지칭 — "모 기업", "익명의 한 기술기업"
    r"익명의?\s|(?<![가-힣])모\s+(?:기업|기술|대형|주요|반도체|은행|증권|글로벌)"
)


def _load_today_calendar(briefing_type: str) -> dict:
    """fetch_data가 앞서 저장한 오늘 경제 캘린더를 읽는다 (워크플로우상 항상 선행 실행)."""
    path = DATA_DIR / f"latest_{briefing_type.replace('-', '_')}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("economic_calendar") or {}
    except Exception:
        return {}


# 본문이 담기는 키의 관측된 이름들. **이 목록은 최종 판단 근거가 아니다** — 아래 값 기반
# 폴백이 진짜 방어선이다(키 이름은 모델이 언제든 바꾼다).
_TEXT_KEY_HINTS = ("text", "catalyst", "headline", "event", "summary",
                   "title", "content", "body", "indicator", "description")
# 본문일 리 없는 키(날짜·티커·메타). 값 기반 폴백에서 제외한다.
_NON_TEXT_KEYS = {"date", "event_date", "time", "ticker", "tickers", "symbol", "code",
                  "impact", "sentiment", "source", "url", "link", "id"}
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _item_text(it) -> str:
    """뉴스 항목에서 본문을 뽑는다 — **키 이름에 의존하지 않는다**.

    2026-08-04 실사고: Gemini가 catalysts 항목을 프롬프트가 요구한 `text`가 아니라
    `catalyst` 키로 반환했다. 내용 게이트들은 전부 `c["text"]`만 읽어 본문이 빈 문자열이 됐고,
    41일 전(2026-06-24) 마이크론 실적이 "실적 촉매 아님"으로 판정돼 무검증 통과했다.
    반면 `_filter_stale_catalysts`만 `catalyst` 폴백이 있어 그 항목을 본문으로 되살려
    최종 출력에 실었다 — **JSON 키 이름 하나로 모든 게이트가 우회된 것**이다.

    그래서 키 이름 목록(_TEXT_KEY_HINTS)은 빠른 경로일 뿐이고, 모르는 키가 와도
    값에서 본문을 찾아낸다. 키 목록을 늘리는 방식이면 다음 변형에 또 뚫린다.
    """
    if isinstance(it, str):
        return it.strip()
    if not isinstance(it, dict):
        return ""
    for k in _TEXT_KEY_HINTS:
        v = it.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    cands = [v.strip() for k, v in it.items()
             if isinstance(v, str) and str(k).lower() not in _NON_TEXT_KEYS
             and len(v.strip()) >= 8 and not _ISO_DATE_RE.match(v.strip())]
    return max(cands, key=len) if cands else ""


def _normalize_news_items(items) -> list:
    """뉴스 항목을 {date, text, ticker} 한 가지 모양으로 통일한다(게이트 이전에 1회).

    모든 게이트가 같은 본문을 보게 만드는 경계다. 본문을 못 찾은 항목은 검증 자체가
    불가능하므로 버린다 — 완전성보다 정합성이 우선이다(운영 규칙 0).
    """
    out = []
    for it in items or []:
        text = _item_text(it)
        if not text:
            print(f"[fetch_news] 본문 없는 항목 제거(검증 불가): {str(it)[:80]}", file=sys.stderr)
            continue
        date_s, ticker = "", ""
        if isinstance(it, dict):
            date_s = str(it.get("date") or it.get("event_date") or "").strip()
            tk = it.get("ticker") or it.get("tickers") or ""
            ticker = ",".join(str(x) for x in tk) if isinstance(tk, list) else str(tk).strip()
        out.append({"date": date_s, "text": text, "ticker": ticker})
    return out


# "오늘 발표될 주요 경제 지표는 예정되어 있지 않으나" — 캘린더에 고영향 일정이 버젓이
# 있는데도 없다고 답하면, 그날을 실제로 검색하지 않았다는 뜻이다 (2026-07-30 실사고).
_NO_EVENT_CLAIM_RE = re.compile(
    r"(경제\s*지표|주요\s*지표|고영향\s*지표|경제\s*일정|발표\s*일정)"
    r"[^.\n]{0,30}?(없|예정되어\s*있지\s*않|예정돼\s*있지\s*않|부재)"
)


def _grounding_failure_signals(data: dict, calendar: dict | None = None,
                               grounding_chunks: int | None = None) -> list:
    """수집이 검색 대신 **학습 시점 지식**으로 답했다는 신호를 모은다.

    2026-07-30 실사고에서 세 신호가 모두 데이터에 남아 있었는데도, 개별 항목을
    정규식으로 하나씩 반박하는 기존 게이트들은 전부 통과시켰다. 개별 문장을 쫓는
    대신 **수집 결과 전체의 신뢰도**를 판정하기 위한 함수다(SERVICE_RULES §29).

    ⚠️ 반드시 **정규화·게이트 이전의 원본 응답**으로 호출한다. 2026-08-04까지는 이 함수가
    `_filter_stale_catalysts`가 문자열로 환원한 **뒤에** 호출돼, catalysts가 비어있지만
    않으면 `catalysts_schema_violation`이 **항상** 발화했다 — 정보량 0인 신호였고, 정작
    그날의 진짜 스키마 위반(dict인데 본문 키가 text가 아님)은 아무도 감지하지 못했다.
    """
    signals = []

    cats = data.get("catalysts") or []
    if cats:
        # 프롬프트는 {date,text,ticker} 객체를 요구한다. 전부 문자열이거나, dict인데 본문이
        # text에 없으면 검색이 아니라 형식만 흉내 낸 출력이다(2026-08-04 실사고의 직접 원인).
        all_strings = not any(isinstance(c, dict) for c in cats)
        textless_dict = any(isinstance(c, dict) and not str(c.get("text") or "").strip()
                            for c in cats)
        if all_strings or textless_dict:
            signals.append("catalysts_schema_violation")

    # 출처가 하나도 붙지 않은 응답 — 어떤 문서로도 뒷받침되지 않는 주장이라는 뜻이다.
    # None이면 조회 불가 → 판단하지 않는다(fail-open).
    if grounding_chunks is not None and grounding_chunks <= 0:
        signals.append("no_grounding_sources")

    fields = ("catalysts", "headlines", "key_indicators")
    blob = " ".join(
        _item_text(it) for f in fields for it in (data.get(f) or []) if isinstance(data.get(f), list)
    )

    today_events = [e for e in ((calendar or {}).get("today") or []) if isinstance(e, dict)]
    if today_events and _NO_EVENT_CLAIM_RE.search(blob):
        signals.append("denies_scheduled_events")

    if _PLACEHOLDER_ENTITY_RE.search(blob):
        signals.append("placeholder_entities")

    return signals


def _count_grounding_chunks(response) -> int | None:
    """응답에 붙은 검색 출처(grounding chunk) 개수. 판정 불가면 None(fail-open).

    google_search 툴을 쓰면 Gemini는 실제로 참조한 문서를 grounding_chunks로 돌려준다.
    이 값이 0이면 **어떤 문서로도 뒷받침되지 않는 답**이라는 뜻이다 — 검색 쿼리를 날렸는지
    (web_search_queries)와는 별개다. 2026-08-04 실사고 응답이 정확히 그 상태였다.
    """
    try:
        cand = (response.candidates or [None])[0]
        gm = getattr(cand, "grounding_metadata", None)
        if gm is None:
            # 툴을 아예 호출하지 않았다는 뜻 — 출처 0과 같게 본다.
            return 0
        return len(getattr(gm, "grounding_chunks", None) or [])
    except Exception as e:
        print(f"[fetch_news] grounding_metadata 확인 실패(판정 생략): {e}", file=sys.stderr)
        return None


def _is_grounding_failure(data: dict, calendar: dict | None = None,
                          grounding_chunks: int | None = None) -> bool:
    """출처 0건이면 즉시, 그 외에는 신호 2개 이상이면 수집 실패로 본다.

    **출처(grounding chunk) 0건은 단독으로 폐기 사유다** (2026-08-04 결정). 어떤 문서로도
    뒷받침되지 않는 답은 검증할 대상이 아니라 버릴 대상이다 — 게이트로 반박 가능한 주장만
    걸러지고 나머지는 그대로 실린다는 게 §22~§31에서 여덟 번 확인됐다.

    나머지 신호는 1개만으론 정상 수집에서도 우연히 나올 수 있어 2개 이상을 요구한다.
    어느 쪽이든 뉴스 요약을 통째로 버리고 **뉴스 없이 발행**한다 — 이슈 섹션이 비는 것보다
    방향이 틀린 브리핑이 훨씬 위험하다(§27).
    """
    signals = _grounding_failure_signals(data, calendar, grounding_chunks)
    return "no_grounding_sources" in signals or len(signals) >= 2


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
        text = _item_text(it)
        if _PLACEHOLDER_ENTITY_RE.search(text):
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
        text = _item_text(it)
        if _SLOT_ECHO_RE.match(text):
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
        text = _item_text(it)
        if _SEARCH_FAILURE_RE.search(text):
            print(f"[fetch_news] 검색 실패 보고 제거: {text[:60]}", file=sys.stderr)
            continue
        out.append(it)
    return out
