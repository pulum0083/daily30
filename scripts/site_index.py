# 발행본 목록에서 만드는 사이트 색인 — 사이드바 목록·목록 JSON·아카이브·RSS·종목 홈 최근 브리핑·robots·사이트맵

import html
import json
import re
import sys
from datetime import datetime, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from html_common import BASE_DIR, BRIEFINGS_DIR, BRIEFING_LABELS, CONFIG_DIR, DATA_DIR, DATA_FILE, KST, SCHEDULED_TIMES, SITE_BASE, TYPE_MAP, WEB_DIR, _md, day_label, fmt_time, load_json, make_env
from briefing_meta import BRAND_KO, briefing_head


# ── 인접 브리핑 + 목록 ─────────────────────────────────────────────────────────
def existing_dates(internal_type: str) -> list:
    if not BRIEFINGS_DIR.exists():
        return []
    return sorted(d.name for d in BRIEFINGS_DIR.iterdir()
                  if d.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}$", d.name)
                  and (d / internal_type / "index.html").exists())


def find_adjacent(internal_type: str, target: str) -> tuple:
    dirs = existing_dates(internal_type)
    if target not in dirs:
        # 아직 안 써졌으면 가상으로 끼워 계산
        dirs = sorted(set(dirs) | {target})
    idx = dirs.index(target)
    prev_url = f"/briefings/{dirs[idx-1]}/{internal_type}/" if idx > 0 else None
    next_url = f"/briefings/{dirs[idx+1]}/{internal_type}/" if idx < len(dirs) - 1 else None
    return prev_url, next_url


def build_list_context(target_date: str, active_type: str) -> dict:
    bpath = DATA_DIR / "briefings.json"
    briefings = load_json(bpath).get("briefings", []) if bpath.exists() else []
    today = datetime.now(KST).strftime("%Y-%m-%d")

    def norm_type(t):
        return TYPE_MAP.get(t, t)

    def cell_for(d: str, btype: str, today_card: bool) -> dict:
        new_path = BRIEFINGS_DIR / d / btype / "index.html"
        ready = new_path.exists()
        match = next((b for b in briefings if b.get("date") == d and norm_type(b.get("type")) == btype), None)
        base = {"type": btype, "label": BRIEFING_LABELS[btype]}
        if d == target_date and btype == active_type:
            base["state"] = "current"
        elif ready:
            base["state"] = "ready"
            base["url"] = f"/briefings/{d}/{btype}/"
        elif today_card:
            base["state"] = "pending"
            base["scheduled_time"] = SCHEDULED_TIMES[btype]
            return base
        else:
            base["state"] = "empty"
            return base
        # ready/current 공통 표시
        if not today_card:
            # 지난 장 목록(2026-11-12 A안): 헤드라인·예측 채점·마감 등락
            base["headline"] = _archive_headline(d, btype)
            if btype == "close":
                base.update(close_map.get(d) or {})
            elif match and match.get("is_correct") in (True, False):
                base["hit"] = bool(match["is_correct"])
        if match:
            direction = match.get("predicted_direction") or match.get("direction", "")
            if btype == "close":
                chg = match.get("actual_change_pct")
                base["pill_cls"] = "neutral"
                base["pill_text"] = f"{chg:+.2f}%" if isinstance(chg, (int, float)) else ""
                base["title"] = f"KOSPI {chg:+.2f}%" if isinstance(chg, (int, float)) else "마감"
            else:
                up = "상승" in direction
                base["pill_cls"] = "up" if up else "dn"
                base["pill_text"] = ("▲" if up else "▼") if direction else ""
                base["title"] = direction or "—"
            base["time"] = fmt_time(match.get("generated_at", ""))
        else:
            base["title"] = "—"
            base["time"] = ""
        return base

    types = ["kospi", "close", "us"]
    close_map = {}
    today_card = {
        "date": today, "day_label": day_label(today, full=True),
        "slots": [cell_for(today, t, True) for t in types],
    }
    past_dates = sorted({b["date"] for b in briefings if b.get("date") and b["date"] != today}, reverse=True)[:20]
    close_map = _close_changes(past_dates)
    past_rows, prev_month = [], None
    for d in past_dates:
        if not any((BRIEFINGS_DIR / d / t / "index.html").exists() for t in types):
            continue
        if len(past_rows) >= 10:
            break
        try:
            dt = date.fromisoformat(d)
        except ValueError:
            continue
        month = f"{dt.year}년 {dt.month}월"
        past_rows.append({
            "date": d, "date_short": d[5:], "day_label": day_label(d),
            "date_long": f"{dt.month}월 {dt.day}일", "day_full": day_label(d, full=True),
            "chg": (close_map.get(d) or {}).get("chg"),
            "month_label": month, "show_month": month != prev_month,
            "cells": [cell_for(d, t, False) for t in types],
        })
        prev_month = month
    return {"today_card": today_card, "past_rows": past_rows}


def find_latest_ready():
    """파일 수정 시간 기준 가장 최근 생성된 ready 브리핑 (internal_type, date) 반환. 없으면 None."""
    best = None  # (mtime, internal_type, date)
    for d_dir in BRIEFINGS_DIR.iterdir():
        d = d_dir.name
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', d):
            continue
        for it in DATA_FILE:
            html = d_dir / it / "index.html"
            if not html.exists():
                continue
            mtime = html.stat().st_mtime
            if best is None or mtime > best[0]:
                best = (mtime, it, d)
    return (best[1], best[2]) if best else None


def update_vercel_briefings_route(internal_type: str, target_date: str):
    """vercel.json의 /briefings/ 라우팅을 최신 브리핑으로 업데이트."""
    import re
    vercel_path = BASE_DIR / "vercel.json"
    content = vercel_path.read_text(encoding="utf-8")
    dest = f"/briefings/{target_date}/{internal_type}/index.html"
    pattern = r'("src": "\^/briefings/\?\$",\s*"dest": ")[^"]*(")'
    if not re.search(pattern, content):
        print(f"[generate_html] vercel.json /briefings/ 패턴 미일치, 건너뜀")
        return
    updated = re.sub(pattern, lambda m: m.group(1) + dest + m.group(2), content)
    if updated == content:
        print(f"[generate_html] vercel.json /briefings/ 이미 최신 ({dest})")
        return
    vercel_path.write_text(updated, encoding="utf-8")
    print(f"[generate_html] vercel.json /briefings/ → {dest}")


def _parse_close_price(html_path):
    """close 브리핑 HTML에서 KOSPI 종가 추출 (신규/레거시 포맷 모두 지원)."""
    try:
        html = html_path.read_text(encoding="utf-8")
        m = re.search(r'class="a-hero__idx-val">([0-9,]+(?:\.\d+)?)<', html)
        if not m:
            m = re.search(r'close-idx__name">KOSPI.*?close-idx__val">([0-9,]+(?:\.\d+)?)<', html, re.DOTALL)
        return m.group(1) if m else None
    except Exception:
        return None


def _close_changes(dates) -> dict:
    """{날짜: {"price": "5,375.36", "chg": 2.6}} — 마감 브리핑 발행본의 코스피 종가와 전 거래일 대비 등락.

    전 거래일 종가는 같은 목록 안의 직전 마감 발행본에서 찾는다. 없으면 chg를 빼고 가격만 둔다(§0).
    브리핑 하단 목록(정적·JSON)이 같은 계산을 쓴다(§30).
    """
    out, prev = {}, None
    for d in sorted(set(dates)):
        page = BRIEFINGS_DIR / d / "close" / "index.html"
        price = _parse_close_price(page) if page.exists() else None
        if not price:
            continue
        val = float(price.replace(",", ""))
        item = {"price": price}
        if prev:
            item["chg"] = round((val / prev - 1) * 100, 2)
        out[d] = item
        prev = val
    return out


def write_briefings_list_json():
    """web/data/briefings-list.json 을 생성한다.

    브리핑 목록 today 카드를 JS가 동적으로 패치하는 데 사용한다.
    각 날짜별 kospi/close/us 슬롯 상태를 담는다.
    """
    bpath = DATA_DIR / "briefings.json"
    briefings = load_json(bpath).get("briefings", []) if bpath.exists() else []

    types = ["kospi", "close", "us"]

    # 최근 30일 분 날짜만 대상
    all_dates = sorted({b["date"] for b in briefings if b.get("date")}, reverse=True)[:30]
    today = datetime.now(KST).strftime("%Y-%m-%d")
    if today not in all_dates:
        all_dates = [today] + all_dates

    slots = {}
    for d in all_dates:
        day_slots = {}
        for btype in types:
            new_path = BRIEFINGS_DIR / d / btype / "index.html"
            ready = new_path.exists()
            match = next((b for b in briefings if b.get("date") == d and TYPE_MAP.get(b.get("type"), b.get("type")) == btype), None)

            if ready:
                entry = {"state": "ready", "url": f"/briefings/{d}/{btype}/"}
                # 브리핑 헤드라인 — 페이지 맨 위·아카이브와 같은 문장(view_title 우선, §84)
                headline = _archive_headline(d, btype)
                if headline:
                    entry["headline"] = re.sub(r"<[^>]+>", "", str(headline)).strip()
                if btype != "close" and match and match.get("is_correct") in (True, False):
                    entry["hit"] = bool(match["is_correct"])
                if btype == "close":
                    price = _parse_close_price(new_path)
                    entry["title"] = price or "마감"
                    entry["price"] = price or ""
                    entry["time"] = fmt_time(match.get("generated_at", "")) if match else ""
                elif match:
                    direction = match.get("predicted_direction") or match.get("direction", "")
                    up = "상승" in direction
                    entry["pill_cls"] = "up" if up else "dn"
                    entry["pill_text"] = ("▲" if up else "▼") if direction else ""
                    entry["title"] = direction or "—"
                    entry["time"] = fmt_time(match.get("generated_at", ""))
                else:
                    entry["title"] = "—"
                    entry["time"] = ""
            else:
                entry = {"state": "pending", "scheduled_time": SCHEDULED_TIMES.get(btype, "")}
            day_slots[btype] = entry
        slots[d] = day_slots

    # 마감 등락(전 거래일 마감 발행본 대비) — 지난 장 목록 머리에 쓴다
    for d, item in _close_changes(all_dates).items():
        if "chg" in item and slots.get(d, {}).get("close", {}).get("state") == "ready":
            slots[d]["close"]["chg"] = item["chg"]

    out_path = WEB_DIR / "data" / "briefings-list.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"slots": slots}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[generate_html] wrote web/data/briefings-list.json")


# ─────────────────────────────────────────────────────────────────────────────
# 브리핑 아카이브 (/briefings/)
# ─────────────────────────────────────────────────────────────────────────────
# 2026-09-02 신설. 그 전까지 /briefings/ 는 briefings-list.json을 fetch해서
# 최신 브리핑으로 location.replace() 하는 1.7KB 리다이렉트 스텁이었다(본문 26자).
# 발행본이 80편 넘게 쌓였는데 **과거 브리핑을 훑어볼 경로가 사실상 없었고**,
# sitemap에는 그 스텁이 등재돼 크롤러에게 빈 페이지를 광고하고 있었다.
#
# ⚠️ 목록의 원본은 data/*.json이 아니라 **디스크에 커밋된 발행본**이다.
#    로컬 analysis 파일이 stale일 때 아카이브가 오염되는 것을 구조적으로 막는다(§23·§28).
# ⚠️ main.js patchBriefingList()는 `.bottom-list`를 찾아 최근 10일로 다시 그린다.
#    아카이브는 `.arch-list`를 쓰므로 그 대상이 아니다 — 클래스를 바꾸지 말 것.
# 하루 안에서도 **최신 발행이 위**로 온다 — 날짜가 최신순이므로 그래야 일관된다.
# 발행 시각: 코스피 예측 07:25 → 마감 16:25 → 미국 21:15 이므로 역순으로 나열한다.
# 이 순서가 곧 featured(맨 위 1편) 선정 순서이기도 하다 — 목록의 첫 항목이 featured다.
# ⚠️ build_list_context의 types(사이드바 3열 목록)와는 별개다. 그쪽은 가로 배치라 발행
#    순서대로 두는 게 자연스러우므로 함께 뒤집지 말 것.
ARCHIVE_TYPES = ["us", "close", "kospi"]


def _archive_headline(date_str: str, btype: str) -> str:
    """발행본의 헤드라인. 스냅샷 → meta description 순으로 찾고, 없으면 빈 문자열."""
    snap = BRIEFINGS_DIR / date_str / btype / "analysis_snapshot.json"
    if snap.exists():
        try:
            d = load_json(snap)
        except Exception:
            d = {}
        tv = d.get("todays_view") or {}
        for cand in (tv.get("view_title"), d.get("reason_title"), d.get("market_title")):
            if isinstance(cand, str) and cand.strip():
                return cand.strip()
    page = BRIEFINGS_DIR / date_str / btype / "index.html"
    if page.exists():
        m = re.search(r'<meta name="description" content="([^"]*)"', page.read_text(errors="ignore"))
        if m and m.group(1).strip():
            return html.unescape(m.group(1).strip())
    return ""


def _archive_dek(date_str: str, btype: str) -> str:
    """발행본의 서브타이틀(한 문단 요약). 없으면 빈 문자열 — 지어내지 않는다(§0).

    kospi·us는 `todays_view.dek`, close는 `dek`(2026-10-25~)·`sc_summary`가 같은 역할을 한다.
    맨 위 최신 1편에만 쓰이므로(그 아래는 제목만) 여기서만 읽는다.
    """
    snap = BRIEFINGS_DIR / date_str / btype / "analysis_snapshot.json"
    if not snap.exists():
        return ""
    try:
        d = load_json(snap)
    except Exception:
        return ""
    tv = d.get("todays_view") or {}
    for cand in (tv.get("dek"), d.get("dek"), d.get("sc_summary")):
        if isinstance(cand, str) and cand.strip():
            return cand.strip()
    return ""


def build_archive_context() -> dict:
    """발행된 브리핑을 디스크에서 훑어 월별 아카이브 목록을 만든다."""
    if not BRIEFINGS_DIR.exists():
        return {"months": [], "total": 0}
    dates = sorted(
        (p.name for p in BRIEFINGS_DIR.iterdir()
         if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.name)),
        reverse=True,
    )
    months, total, prev_month, featured_done = [], 0, None, False
    for d in dates:
        entries = []
        for t in ARCHIVE_TYPES:
            if not (BRIEFINGS_DIR / d / t / "index.html").exists():
                continue
            entry = {
                "label": BRIEFING_LABELS[t],
                "url": f"/briefings/{d}/{t}/",
                "headline": _archive_headline(d, t),
            }
            # 목록 맨 위 최신 1편만 서브타이틀까지 보여준다(2026-09-04). 나머지는 제목만 —
            # 전부 요약을 달면 목록이 길어져 훑어보기 어려워진다.
            if not featured_done:
                entry["dek"] = _archive_dek(d, t)
                entry["featured"] = True
                featured_done = True
            entries.append(entry)
        if not entries:
            continue
        total += len(entries)
        dt = date.fromisoformat(d)
        label = f"{dt.year}년 {dt.month}월"
        if label != prev_month:
            months.append({"label": label, "days": []})
            prev_month = label
        months[-1]["days"].append({
            "date": d, "date_short": f"{dt.month}월 {dt.day}일",
            "day_label": day_label(d),
            # ⚠️ 키 이름을 items로 두면 Jinja가 dict.items 메서드를 먼저 잡아 렌더가 깨진다.
            "briefings": entries,
        })
    return {"months": months, "total": total}


def write_briefings_index():
    """web/briefings/index.html — 정적 아카이브 목록을 생성한다."""
    ctx = build_archive_context()
    if not ctx["total"]:
        print("[generate_html] 아카이브: 발행본 없음 — index.html 생략", file=sys.stderr)
        return
    env = make_env()
    out = BRIEFINGS_DIR / "index.html"
    out.write_text(
        env.get_template("pages/briefings_index.html").render(
            canonical_url=f"{SITE_BASE}/briefings/", **ctx),
        encoding="utf-8")
    # 로그용 상대경로 — BASE_DIR 밖이면 relative_to가 예외를 던진다(테스트의 tmp_path 등).
    # 로그 한 줄 때문에 아카이브 생성이 죽으면 안 되므로 실패 시 절대경로로 떨어진다.
    try:
        shown = out.relative_to(BASE_DIR)
    except ValueError:
        shown = out
    print(f"[generate_html] 아카이브 갱신: {shown} "
          f"({ctx['total']}편 / {len(ctx['months'])}개월)")
    write_stocks_recent_briefings()
    write_briefings_rss()


# 브리핑 RSS(2026-10-27) — 네이버 서치어드바이저에 제출해 새 브리핑이 빨리 수집되게 한다.
# 아카이브와 같은 자리·같은 원본(디스크에 커밋된 발행본)으로 만든다. 제목·설명은 페이지 <head>와 같은 briefing_head.
# 파일은 BRIEFINGS_DIR 안에 둔다 — 테스트가 BRIEFINGS_DIR을 임시 폴더로 바꾸면 피드도 함께 따라간다.
RSS_ITEMS = 30


def _briefing_pub_date(date_str: str, btype: str, analysis: dict) -> str:
    """RFC 822 발행 시각. 스냅샷 generated_at, 없으면 정해진 발행 시각(SCHEDULED_TIMES)."""
    from email.utils import format_datetime
    try:
        dt = datetime.fromisoformat(analysis.get("generated_at") or "")
        if dt.tzinfo is None:
            dt = KST.localize(dt)
    except (TypeError, ValueError):
        h, m = SCHEDULED_TIMES[btype].split(":")
        dt = KST.localize(datetime.fromisoformat(date_str).replace(hour=int(h), minute=int(m)))
    return format_datetime(dt.astimezone(KST))


def write_briefings_rss(n: int = RSS_ITEMS) -> bool:
    """web/briefings/rss.xml — 최신 발행본 n편. 발행본이 없으면 쓰지 않는다."""
    if not BRIEFINGS_DIR.exists():
        return False
    dates = sorted((p.name for p in BRIEFINGS_DIR.iterdir()
                    if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.name)), reverse=True)
    items = []
    for d in dates:
        for t in ARCHIVE_TYPES:
            if len(items) >= n:
                break
            if not (BRIEFINGS_DIR / d / t / "index.html").exists():
                continue
            snap = BRIEFINGS_DIR / d / t / "analysis_snapshot.json"
            try:
                analysis = load_json(snap) if snap.exists() else {}
            except Exception:
                analysis = {}
            head = briefing_head(analysis, t, d)
            url = f"{SITE_BASE}/briefings/{d}/{t}/"
            items.append(
                # 항목 제목엔 사이트 이름을 붙이지 않는다 — 채널 제목이 이미 더블샷이다
                f"    <item>\n      <title>{head['title'].removesuffix(f' | {BRAND_KO}')}</title>\n      <link>{url}</link>\n"
                f"      <guid isPermaLink=\"true\">{url}</guid>\n"
                f"      <pubDate>{_briefing_pub_date(d, t, analysis)}</pubDate>\n"
                f"      <description>{head['description']}</description>\n    </item>")
    if not items:
        return False
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n  <channel>\n'
           '    <title>더블샷(Double-Shot) AI 투자 브리핑</title>\n'
           f'    <link>{SITE_BASE}/briefings/</link>\n'
           f'    <atom:link href="{SITE_BASE}/briefings/rss.xml" rel="self" type="application/rss+xml"/>\n'
           '    <description>매일 아침 코스피 시초가 예측, 오후 코스피 마감 시황, 저녁 미국 증시 전망 브리핑</description>\n'
           '    <language>ko</language>\n'
           + "\n".join(items) + "\n  </channel>\n</rss>\n")
    (BRIEFINGS_DIR / "rss.xml").write_text(xml, encoding="utf-8")
    print(f"[generate_html] RSS 갱신: {len(items)}편")
    return True


# /stocks/ 맨 아래 '최근 브리핑' — 크롤러가 스크립트 없이 읽는 정적 목록(2026-10-27, §70).
# /stocks/index.html은 손으로 만든 정적 페이지라, 두 표시 사이만 다시 쓴다. 아카이브와 같은 자리에서
# 함께 갱신되므로 원본도 같다(디스크에 커밋된 발행본). 맨 위 1편만 요약을 붙인다 — 아카이브와 같은 규칙.
STOCKS_HOME_HTML = WEB_DIR / "stocks" / "index.html"
RECENT_START = "<!-- RECENT_BRIEFINGS:START -->"
RECENT_END = "<!-- RECENT_BRIEFINGS:END -->"
_WEEKDAYS = "월화수목금토일"


def build_recent_briefings(n: int = 6) -> list:
    """최신 발행본 n편 — 날짜 최신순, 하루 안에서는 미국 → 마감 → 코스피(ARCHIVE_TYPES)."""
    if not BRIEFINGS_DIR.exists():
        return []
    dates = sorted((p.name for p in BRIEFINGS_DIR.iterdir()
                    if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.name)), reverse=True)
    out = []
    for d in dates:
        for t in ARCHIVE_TYPES:
            if len(out) >= n:
                return out
            if not (BRIEFINGS_DIR / d / t / "index.html").exists():
                continue
            headline = re.sub(r"<[^>]+>", "", _archive_headline(d, t)).strip()
            if not headline:
                continue   # 제목 없는 편은 싣지 않는다 — 종류 이름만 남은 줄은 정보가 없다
            dt = date.fromisoformat(d)
            out.append({"url": f"/briefings/{d}/{t}/", "label": BRIEFING_LABELS[t], "iso": d,
                        "date": f"{dt.month}/{dt.day}({_WEEKDAYS[dt.weekday()]})",
                        "headline": headline, "dek": _archive_dek(d, t) if not out else ""})
    return out


WEEKLY_RECENT_MAX_AGE = 14   # 가장 최근 주간 리포트가 이보다 오래됐으면(작업이 멈춤) 최근 목록에 싣지 않는다(§20)


def build_recent_weekly(today: str = "") -> dict:
    """가장 최근 주간 장기 리포트 한 줄(2026-11-09) — 디스크에 커밋된 web/weekly/{금요일}/ 에서. 없거나 오래됐으면 {}."""
    import longterm_pages as lp
    today = today or datetime.now(KST).strftime("%Y-%m-%d")
    for p in sorted((WEB_DIR / "weekly").glob("????-??-??/data.json"), reverse=True):
        if not (p.parent / "index.html").exists():
            continue
        end = p.parent.name
        if end > today or (date.fromisoformat(today) - date.fromisoformat(end)).days > WEEKLY_RECENT_MAX_AGE:
            return {}
        try:
            c = lp.weekly_context(json.loads(p.read_text(encoding="utf-8")))
        except (ValueError, KeyError):
            return {}
        if not c:
            return {}
        w = c["wk"]
        return {"url": f"/weekly/{end}/", "label": "주간 장기 리포트", "end": end,
                "date": f"{_md(w['monday'])}~{_md(end)}", "headline": w["head"]}
    return {}


def render_recent_briefings(items: list, weekly: dict = None) -> str:
    """발행 순서(최신 위)대로 쓴다. 주간 리포트는 토요일 아침에 나가므로 그 주 금요일 브리핑들 바로 위에 끼운다.
    맨 위 1편(가장 최근 발행)만 파란 바·요약으로 강조한다(2026-11-09 사용자 지적 — 주간 리포트가 늘 맨 위에 붙어 있었다)."""
    order = list(items)
    if weekly:
        end = weekly.get("end", "")
        at = next((k for k, it in enumerate(order) if it.get("iso", "") <= end), len(order))
        order.insert(at, dict(weekly, wk=True))
    rows = []
    for i, it in enumerate(order):
        cls = "rb-item" + (" feat" if i == 0 else "") + (" wk" if it.get("wk") else "")
        if it.get("wk"):
            rows.append(f'      <li class="{cls}"><a href="{it["url"]}"><div class="rb-meta">📅 {it["date"]} · {it["label"]}</div>'
                        f'<div class="rb-h">{html.escape(it["headline"])}</div></a></li>')
            continue
        # 요약은 우리 분석 문장이라 <b> 강조만 살리고 나머지 태그는 지운다(아카이브는 그대로 |safe로 쓴다).
        dek = re.sub(r"<(?!/?b>)[^>]+>", "", it["dek"]) if (it["dek"] and i == 0) else ""
        rows.append(
            f'      <li class="{cls}"><a href="{it["url"]}">'
            f'<div class="rb-meta">{it["date"]} · {it["label"]}</div>'
            f'<div class="rb-h">{html.escape(it["headline"])}</div>'
            + (f'<div class="rb-d">{dek}</div>' if dek else "") + "</a></li>")
    return "\n".join(rows)


def write_stocks_recent_briefings(n: int = 6) -> bool:
    """/stocks/index.html의 표시 사이에 최근 브리핑 목록을 다시 쓴다. 표시가 없거나 발행본이 없으면 건드리지 않는다."""
    if not STOCKS_HOME_HTML.exists():
        return False
    page = STOCKS_HOME_HTML.read_text(encoding="utf-8")
    i, j = page.find(RECENT_START), page.find(RECENT_END)
    items = build_recent_briefings(n)
    if i < 0 or j < i or not items:
        print("[generate_html] /stocks/ 최근 브리핑: 표시 또는 발행본 없음 — 건너뜀", file=sys.stderr)
        return False
    new = page[:i + len(RECENT_START)] + "\n" + render_recent_briefings(items, build_recent_weekly()) + "\n      " + page[j:]
    if new != page:
        STOCKS_HOME_HTML.write_text(new, encoding="utf-8")
    print(f"[generate_html] /stocks/ 최근 브리핑 갱신: {len(items)}편")
    return True


# 브리핑 검색 색인 기간(2026-11-13 결정) — 애드센스 '가치가 별로 없는 콘텐츠' 거절(§80) 뒤, 매일 같은 틀의
# 짧은 자동 생성 페이지가 사이트의 90%를 차지했다. 발행일에서 30일이 지난 브리핑은 noindex로 돌리고
# sitemap에서도 뺀다. 페이지는 지우지 않는다(§33) — 아카이브·링크로는 계속 열린다.
BRIEFING_INDEX_DAYS = 30
ROBOTS_INDEX = '<meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1">'
ROBOTS_NOINDEX = '<meta name="robots" content="noindex, follow">'
_ROBOTS_RE = re.compile(r'<meta name="robots" content="[^"]*">')


def briefing_indexed(d: str, today: str) -> bool:
    """발행일 d가 오늘에서 30일 이내면 색인한다."""
    try:
        return (date.fromisoformat(today) - date.fromisoformat(d)).days <= BRIEFING_INDEX_DAYS
    except ValueError:
        return True


def apply_briefing_robots(today: str = None) -> int:
    """발행된 브리핑의 robots 메타를 색인 기간에 맞춘다. <head>의 그 한 줄만 바꾼다(본문은 그대로, §33·§71).
    sitemap과 같은 자리(write_sitemap_xml)에서 돌아 두 판정이 어긋나지 않는다. 바꾼 페이지 수를 돌려준다."""
    today = today or datetime.now(KST).strftime("%Y-%m-%d")
    changed = 0
    for page in sorted(BRIEFINGS_DIR.glob("????-??-??/*/index.html")):
        want = ROBOTS_INDEX if briefing_indexed(page.parent.parent.name, today) else ROBOTS_NOINDEX
        html = page.read_text(encoding="utf-8")
        m = _ROBOTS_RE.search(html)
        if m:
            if m.group(0) == want:
                continue
            new = html[:m.start()] + want + html[m.end():]
        elif "<head>" in html:
            new = html.replace("<head>", "<head>\n" + want, 1)   # 7월 초 발행본엔 robots 메타가 없다
        else:
            continue
        page.write_text(new, encoding="utf-8")
        changed += 1
    if changed:
        print(f"[generate_html] 브리핑 robots 갱신 {changed}편 (색인 기간 {BRIEFING_INDEX_DAYS}일)")
    return changed


def write_sitemap_xml():
    """web/sitemap.xml 을 생성한다. generate_html 실행마다 자동 갱신."""
    BASE = "https://doubleshot.space"
    today = datetime.now(KST).strftime("%Y-%m-%d")
    apply_briefing_robots(today)

    # ⚠️ `/` 는 vercel.json에서 `/stocks/`로 301 리다이렉트된다 — sitemap에 넣으면
    #    "리디렉션이 있는 페이지"로 색인에서 제외되고 신호만 흐려진다. 도착지를 직접 등재한다.
    # /about/·/legal/* 는 손으로 만든 정적 페이지라 자동 수집 대상이 아니었다.
    # 심사·신뢰도 판단 때 가장 먼저 찾는 페이지들이므로 명시적으로 넣는다(2026-09-02 추가).
    urls = [
        {"loc": f"{BASE}/stocks/",                       "changefreq": "daily",   "priority": "1.0"},
        {"loc": f"{BASE}/briefings/",                    "changefreq": "daily",   "priority": "0.9"},
        {"loc": f"{BASE}/stocks/income-designer/",       "changefreq": "monthly", "priority": "0.8"},
        {"loc": f"{BASE}/stocks/nasdaq-check/",          "changefreq": "daily",   "priority": "0.7"},
        {"loc": f"{BASE}/stocks/sp500-200/",             "changefreq": "daily",   "priority": "0.7"},
        {"loc": f"{BASE}/stocks/midterm-2018/",          "changefreq": "daily",   "priority": "0.6"},
        {"loc": f"{BASE}/stocks/trump-terms/",           "changefreq": "daily",   "priority": "0.6"},
        {"loc": f"{BASE}/weekly/",                       "changefreq": "weekly",  "priority": "0.7"},
        {"loc": f"{BASE}/accuracy/",                     "changefreq": "daily",   "priority": "0.7"},
        {"loc": f"{BASE}/methodology/",                  "changefreq": "monthly", "priority": "0.6"},
        {"loc": f"{BASE}/guides/",                       "changefreq": "weekly",  "priority": "0.6"},   # 해설 글(2026-11-16, §87)
        {"loc": f"{BASE}/guides/accuracy-baseline/",     "changefreq": "monthly", "priority": "0.6"},
        {"loc": f"{BASE}/guides/aftermarket-close/",     "changefreq": "monthly", "priority": "0.6"},
        {"loc": f"{BASE}/guides/nasdaq-5y-average/",     "changefreq": "monthly", "priority": "0.6"},
        {"loc": f"{BASE}/guides/kospi-open-us-signals/", "changefreq": "monthly", "priority": "0.6"},
        {"loc": f"{BASE}/guides/monthly-ma5-test/", "changefreq": "monthly", "priority": "0.6"},
        {"loc": f"{BASE}/guides/sp-futures-close/", "changefreq": "monthly", "priority": "0.6"},
        {"loc": f"{BASE}/guides/income-etf-yield/", "changefreq": "monthly", "priority": "0.6"},
        {"loc": f"{BASE}/guides/open-vs-close/", "changefreq": "monthly", "priority": "0.6"},
        {"loc": f"{BASE}/guides/sp500-breadth/", "changefreq": "monthly", "priority": "0.6"},
        {"loc": f"{BASE}/guides/investor-flow-timing/", "changefreq": "monthly", "priority": "0.6"},
        {"loc": f"{BASE}/guides/ewy-double-count/", "changefreq": "monthly", "priority": "0.6"},
        {"loc": f"{BASE}/about/",                        "changefreq": "monthly", "priority": "0.6"},
        {"loc": f"{BASE}/legal/disclaimer/",             "changefreq": "yearly",  "priority": "0.3"},
        {"loc": f"{BASE}/legal/privacy/",                "changefreq": "yearly",  "priority": "0.3"},
        {"loc": f"{BASE}/legal/terms/",                  "changefreq": "yearly",  "priority": "0.3"},
    ]

    # 주간 장기 리포트(2026-11-09) — 토요일에 한 번 쓰고 고치지 않는다. 디스크에 있는 주만 등재한다
    for wp in sorted((WEB_DIR / "weekly").glob("????-??-??/index.html"), reverse=True):
        urls.append({"loc": f"{BASE}/weekly/{wp.parent.name}/", "lastmod": wp.parent.name, "changefreq": "yearly", "priority": "0.6"})

    # ready 상태인 브리핑 페이지만 포함
    bpath = DATA_DIR / "briefings.json"
    briefings = load_json(bpath).get("briefings", []) if bpath.exists() else []
    ready_dates = sorted({b["date"] for b in briefings if b.get("date")}, reverse=True)

    type_order = ["kospi", "close", "us"]
    for d in ready_dates:
        if not briefing_indexed(d, today):     # 30일 지난 브리핑은 noindex — sitemap에도 넣지 않는다
            continue
        for btype in type_order:
            page = BRIEFINGS_DIR / d / btype / "index.html"
            if page.exists():
                lastmod = d if d <= today else today
                urls.append({
                    "loc": f"{BASE}/briefings/{d}/{btype}/",
                    "lastmod": lastmod,
                    "changefreq": "monthly",
                    "priority": "0.7",
                })

    # 생성된 섹터 페이지만 포함 (2026-07-21 추가 — 생성은 되는데 sitemap에 빠져 색인 경로가 없었다)
    universe_path = CONFIG_DIR / "stock_universe.json"
    if universe_path.exists():
        for key in load_json(universe_path).get("sectors", {}):
            if (WEB_DIR / "stocks" / "sector" / key / "index.html").exists():
                urls.append({
                    "loc": f"{BASE}/stocks/sector/{key}/",
                    "changefreq": "daily",
                    "priority": "0.7",
                })

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        lines.append("  <url>")
        lines.append(f"    <loc>{u['loc']}</loc>")
        if "lastmod" in u:
            lines.append(f"    <lastmod>{u['lastmod']}</lastmod>")
        lines.append(f"    <changefreq>{u['changefreq']}</changefreq>")
        lines.append(f"    <priority>{u['priority']}</priority>")
        lines.append("  </url>")
    lines.append("</urlset>")

    out_path = WEB_DIR / "sitemap.xml"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[generate_html] wrote web/sitemap.xml ({len(urls)} urls)")
