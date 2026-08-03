# 밤사이 브리지 디스클레이머의 제외 섹터 문구가 실제 섹터 구성과 어긋나지 않는지 검증.
#!/usr/bin/env python3
"""실행: python3 -m pytest scripts/test_bridge_disclaimer_sync.py -v

`/stocks/`의 디스클레이머는 "조선은 대응 미국 지표가 없어 제외했습니다"라고 정적 HTML에
박혀 있는데, 어느 섹터가 빠지는지는 `BRIDGE_US_TICKERS`(파이썬)가 정한다. 둘이 갈라지면
화면은 조선만 빠진다고 말하는데 실제로는 다른 섹터가 빠져 있는 상태가 된다 — §20이 말하는
"라벨이 자기가 설명하던 데이터보다 오래 사는" 형태다.

조선에 미국 벨웨더가 생기거나 다른 섹터가 빠지는 일은 드물지만, 드물기 때문에 오히려
아무도 디스클레이머를 고치러 돌아오지 않는다. 문서로 부탁하는 대신 테스트로 잡는다.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_data as m  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent
UNIVERSE_PATH = BASE_DIR / "scripts" / "config" / "stock_universe.json"
STOCKS_INDEX = BASE_DIR / "web" / "stocks" / "index.html"


def _excluded_sector_labels() -> list:
    """유니버스에는 있는데 브리지 미국 레그에는 없는 섹터의 한글 라벨."""
    sectors = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))["sectors"]
    return [cfg.get("label", key) for key, cfg in sectors.items()
            if key not in m.BRIDGE_US_TICKERS]


def _disclaimer_text() -> str:
    html = STOCKS_INDEX.read_text(encoding="utf-8")
    match = re.search(r'<p class="ob-note">(.*?)</p>', html, re.S)
    assert match, "web/stocks/index.html에서 .ob-note 디스클레이머를 찾지 못했다."
    return match.group(1)


def test_disclaimer_names_every_excluded_sector():
    """제외된 섹터는 전부 디스클레이머에 이름이 있어야 한다 — 조용히 빠지면 안 된다."""
    note = _disclaimer_text()
    missing = [label for label in _excluded_sector_labels() if label not in note]
    assert not missing, (
        f"브리지에서 제외된 섹터 {missing}가 디스클레이머에 없다. "
        f"web/stocks/index.html의 .ob-note 문구를 함께 고칠 것."
    )


def test_disclaimer_does_not_name_included_sectors():
    """반대 방향 — 실제로는 표시되는 섹터를 '제외했다'고 말하면 안 된다."""
    note = _disclaimer_text()
    sectors = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))["sectors"]
    included = [sectors[key].get("label", key) for key in m.BRIDGE_US_TICKERS
                if key in sectors]
    wrongly_named = [label for label in included if label in note]
    assert not wrongly_named, (
        f"디스클레이머가 {wrongly_named}를 제외했다고 말하지만 실제로는 표시된다. "
        f"BRIDGE_US_TICKERS에 추가됐다면 문구에서 빼야 한다."
    )
