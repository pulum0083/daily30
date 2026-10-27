# 브리핑 공유 카드(og:image, 1200×630 PNG)를 그리는 모듈 — 카카오톡·텔레그램 링크 미리보기용
"""브리핑 한 편의 공유 카드.

카드에 들어가는 글자는 전부 발행된 analysis에 이미 있는 값이다(헤드라인·예측 방향·확률).
새 숫자를 만들지 않는다(§0). 마감 브리핑은 카드에 수치를 넣지 않고 헤드라인만 쓴다 —
지수 종가는 analysis가 아니라 시장 데이터 파일에 있어서, 재생성 때 다른 날 값이 섞일 수 있다.
"""
import io
import re
from datetime import date
from pathlib import Path

FONT_DIR = Path(__file__).resolve().parent / "fonts"
W, H = 1200, 630
BG, INK, MUTED = (22, 24, 26), (243, 245, 247), (150, 154, 160)
UP, DN, NEUTRAL = (255, 92, 92), (90, 150, 255), (200, 204, 210)
TYPE_LABEL = {"kospi": "코스피 시초가 예측", "close": "코스피 마감 시황", "us": "미국 증시 전망"}
WEEKDAYS = "월화수목금토일"


def _font(weight: str, size: int):
    from PIL import ImageFont
    return ImageFont.truetype(str(FONT_DIR / f"Pretendard-{weight}.ttf"), size)


def _plain(s) -> str:
    return re.sub(r"<[^>]+>", "", s).strip() if isinstance(s, str) else ""


def _wrap(draw, text: str, font, width: int, max_lines: int) -> list:
    """띄어쓰기 단위로 줄을 접는다. 넘치면 마지막 줄 끝을 '…'로 줄인다."""
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= width:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        cur = word
        while draw.textlength(cur, font=font) > width:   # 한 어절이 한 줄보다 길면 글자 단위로 자른다
            i = len(cur)
            while i > 1 and draw.textlength(cur[:i], font=font) > width:
                i -= 1
            lines.append(cur[:i])
            cur = cur[i:]
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        last = lines[max_lines - 1]
        while last and draw.textlength(last + "…", font=font) > width:
            last = last[:-1]
        lines = lines[:max_lines - 1] + [last.rstrip() + "…"]
    return lines


def _readout(analysis: dict, btype: str):
    """(문구, 색) — 코스피·미국 예측 방향과 큰 쪽 확률. 없으면 None."""
    if btype not in ("kospi", "us"):
        return None
    p = analysis.get("prediction") or {}
    up = p.get("up_pct")
    if not isinstance(up, (int, float)):
        return None
    down = p.get("down_pct", 100 - up)
    if btype == "kospi":
        direction = p.get("direction") or ""
        if "상승" in direction:
            return f"{direction} {up}%", UP
        if "하락" in direction:
            return f"{direction} {down}%", DN
        return None
    if up == down:
        return None
    return (f"상승 우위 {up}%", UP) if up > down else (f"하락 우위 {down}%", DN)


def make_card(analysis: dict, btype: str, date_str: str):
    """PNG bytes. 헤드라인이 없거나 그릴 수 없으면 None — 페이지는 이미지 없이 나간다."""
    analysis = analysis or {}
    tv = analysis.get("todays_view") or {}
    headline = next((t for t in map(_plain, (tv.get("view_title"), analysis.get("reason_title"),
                                             analysis.get("market_title"))) if t), "")
    if not headline:
        return None
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (W, H), BG)
        draw = ImageDraw.Draw(img)
        x = 72
        d = date.fromisoformat(date_str)
        label = TYPE_LABEL[btype]
        if btype == "kospi" and (analysis.get("prediction") or {}).get("basis") != "open":
            label = "코스피 방향 예측"
        draw.text((x, 64), f"{label} · {d.month}월 {d.day}일({WEEKDAYS[d.weekday()]})",
                  font=_font("Medium", 34), fill=MUTED)
        y = 132
        ro = _readout(analysis, btype)
        if ro:
            draw.text((x, y), ro[0], font=_font("Bold", 76), fill=ro[1])
            y += 118
        else:
            y += 20
        size = 64 if ro else 72
        font = _font("Bold", size)
        max_lines = 3 if ro else 4
        for line in _wrap(draw, headline, font, W - 2 * x, max_lines):
            draw.text((x, y), line, font=font, fill=INK)
            y += int(size * 1.32)
        draw.text((x, H - 80), "Double-Shot", font=_font("Bold", 32), fill=INK)
        draw.text((x + draw.textlength("Double-Shot  ", font=_font("Bold", 32)), H - 78),
                  "doubleshot.space", font=_font("Medium", 30), fill=MUTED)
        buf = io.BytesIO()
        img.save(buf, "PNG", optimize=True)
        return buf.getvalue()
    except Exception as e:   # Pillow·폰트가 없거나 그리다 실패해도 브리핑 발행은 막지 않는다
        import sys
        print(f"[og_card] 카드 생성 실패 — 이미지 없이 발행: {e}", file=sys.stderr)
        return None
