#!/usr/bin/env python3
# 기존 발행 브리핑 HTML에서 픽 badge % vs 산문 텍스트 % 불일치를 스캔한다.
"""
사용법: python3 scripts/audit_hallucinations.py
출력: [WARN] 날짜/타입  종목  badge=X%  location="텍스트 발췌"
"""
import re
import sys
from pathlib import Path

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("pip install beautifulsoup4 후 실행하세요", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web" / "briefings"

# validate_analysis의 함수 재사용
sys.path.insert(0, str(ROOT / "scripts"))
from validate_analysis import is_contradicted, _extract_change_claims, strip_tags

PCT_RE = re.compile(r'([+-]?\d+\.?\d*)\s*%')


def parse_pct(text: str):
    """'+4.24%' → 4.24, '-0.49%' → -0.49, None if fail."""
    m = re.search(r'([+-]?\d+\.?\d*)\s*%', strip_tags(text or ""))
    return float(m.group(1)) if m else None


def audit_html(path: Path) -> list:
    """HTML 파일에서 불일치 항목을 찾아 리스트로 반환."""
    issues = []
    briefing_id = "/".join(path.parts[-4:-1])  # 예: 2026-06-04/us
    html = path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")

    # 픽 카드 순회
    for card in soup.select(".stock-pick-card"):
        name_el = card.select_one(".stock-pick-card__name")
        chg_el = card.select_one(".stock-pick-card__change")
        scen_el = card.select_one(".stock-pick-card__scenario")
        if not (name_el and chg_el):
            continue

        name = name_el.get_text(strip=True)
        badge_pct = parse_pct(chg_el.get_text(strip=True))
        if badge_pct is None:
            continue

        # scenario 검사
        if scen_el:
            scen_text = scen_el.get_text()
            claims = _extract_change_claims(scen_text)
            for c in claims:
                if is_contradicted(c, badge_pct):
                    issues.append(
                        f"[WARN] {briefing_id}  {name}  "
                        f"badge={badge_pct:+.2f}%  scenario={c:+.2f}%  "
                        f"diff={abs(c-badge_pct):.2f}%p"
                    )

    # reasons 검사
    for li in soup.select(".reason-block li"):
        text = li.get_text()
        for card in soup.select(".stock-pick-card"):
            name_el = card.select_one(".stock-pick-card__name")
            chg_el = card.select_one(".stock-pick-card__change")
            if not (name_el and chg_el):
                continue
            badge_pct = parse_pct(chg_el.get_text(strip=True))
            if badge_pct is None:
                continue
            name = name_el.get_text(strip=True)
            parts = [p.strip() for p in re.split(r'[\s()/·]', name) if len(p.strip()) >= 2]
            if any(p in text for p in parts):
                claims = _extract_change_claims(text)
                for c in claims:
                    if is_contradicted(c, badge_pct):
                        issues.append(
                            f"[WARN] {briefing_id}  {name}  "
                            f"badge={badge_pct:+.2f}%  reasons='{text[:80].strip()}'"
                        )
                        break

    return issues


def main():
    found = []
    for html_path in sorted(WEB_DIR.glob("**/index.html")):
        parts = html_path.parts
        if len(parts) < 2:
            continue
        btype = parts[-2]
        if btype not in ("kospi", "us"):
            continue
        issues = audit_html(html_path)
        found.extend(issues)

    if not found:
        print("✅ 할루시네이션 의심 항목 없음")
    else:
        for issue in found:
            print(issue)
        print(f"\n총 {len(found)}건 발견 — 수동 확인 후 필요시 HTML 패치")


if __name__ == "__main__":
    main()
