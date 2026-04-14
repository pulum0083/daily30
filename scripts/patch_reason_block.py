# -*- coding: utf-8 -*-
"""Patch web/index.html reason-block with sentence-style Korean bullets."""
from pathlib import Path

p = Path(__file__).resolve().parent.parent / "web" / "index.html"
raw = p.read_text(encoding="utf-8")
a = '                <div class="reason-block">\n                  <ul>\n'
b = '                  </ul>\n                </div>\n              </div>\n\n              <div class="divider">'
i = raw.index(a)
j = raw.index(b, i)

items = [
    (
        "\U0001f680 "
        "\ubbf8\uad6d \ub098\uc2a4\ub2e5\uc740 <b>+1.23%</b>, NQ \uc120\ubb3c\uc740 <b>+1.24%</b>\ub85c "
        "\ub9c8\uac10\ud558\uba70 \uae30\uc220\uc8fc\uac00 \uc804\ubc18\uc801\uc73c\ub85c \uac15\ud558\uac8c "
        "\uc62c\ub790\uc2b5\ub2c8\ub2e4. MSFT\ub294 <b>+3.64%</b>\ub85c 20\uc77c \uc774\ub3d9\ud3c9\uade0\uc120\uc744 "
        "\ub3cc\ud30c\ud588\uace0, GOOGL <b>+1.28%</b>\xb7META <b>+0.74%</b>\uac00 \ud568\uaed8 \uc0c1\uc2b9\ud574 "
        "\ucf54\uc2a4\ud53c IT\xb7\ud50c\ub7ab\ud3fc \uc139\ud130 \uac2d \uc0c1\uc2b9\uc744 \uae30\ub300\ud560 \ub9cc\ud55c "
        "\uadfc\uac70\uac00 \ub429\ub2c8\ub2e4."
    ),
    (
        "\U0001f4a1 \ud544\ub77c\ub378\ud53c\uc544 \ubc18\ub3c4\uccb4 \uc9c0\uc218 SOX\ub294 <b>+1.68%</b>(9,039)\ub85c "
        "\uc5f0\uc18d \uac15\uc138\ub97c \ubcf4\uc774\uace0 \uc788\uc2b5\ub2c8\ub2e4. NVDA\ub294 <b>+0.36%</b>\ub85c "
        "\ube44\uad50\uc801 \uc548\uc815\uc801\uc778 \ud750\ub984 \uc18d\uc5d0\uc11c HBM \uacf5\uae09\ub9dd \uc804\ubc18\uc774 "
        "\uc218\ud61c\ub97c \ubc1b\uc744 \uc218 \uc788\ub2e4\ub294 \ud574\uc11d\uc774 \uac00\ub2a5\ud558\uba70, "
        "SK\ud558\uc774\ub2c9\uc2a4\xb7\uc0bc\uc131\uc804\uc790 \uc2dc\ucd08\uac00\uc5d0\ub294 \uc0c1\uc2b9 "
        "\uc555\ub825\uc774 \uc791\uc6a9\ud560 \uc5ec\uc9c0\uac00 \uc788\uc2b5\ub2c8\ub2e4."
    ),
    (
        "\U0001f1fa\U0001f1f8 \ud55c\uad6d \uad00\ub828 ETF\uc778 EWY\ub294 <b>+1.80%</b>\ub85c \uc0c1\uc2b9\ud588\uace0, "
        "MA20 \ub300\ube44 <b>+8.96%</b> \uc704\uc5d0 \uba38\ubb3c\uace0 \uc788\uc2b5\ub2c8\ub2e4. "
        "\uc678\uad6d\uc778 \ucf54\uc2a4\ud53c \uc21c\ub9e4\uc218\ub97c \uc9d1\ub294 \uc120\ud589 \uc9c0\ud45c\ub85c "
        "\ubcfc \ub54c \uc911\uae30 \ucd94\uc138\uac00 \uc6b0\uc0c1\ud5a5\uc77c \uc218 \uc788\ub2e4\ub294 \ud574\uc11d\uacfc "
        "\uc218\uae09 \uac1c\uc120 \uae30\ub300\uc5d0 \ubb34\uac8c\ub97c \ub458 \uc218 \uc788\uc2b5\ub2c8\ub2e4."
    ),
    (
        "\U0001f630 \uacf5\ud3ec\uc9c0\uc218 VIX\ub294 <b>19.12 (-0.57%)</b>\uc774\uba70, 20\uc77c \ud3c9\uade0 "
        "<b>24.59</b>\ubcf4\ub2e4 \ud06c\uac8c \uc544\ub798\uc5d0 \uc788\uc2b5\ub2c8\ub2e4. "
        "\uae00\ub85c\ubc8c \ub9ac\uc2a4\ud06c\uc628 \ubd84\uc704\uae30\uac00 \uc774\uc5b4\uc9c0\ub294 \uac00\uc6b4\ub370 "
        "\uc2e0\ud765\uc2dc\uc7a5\uc73c\ub85c\uc758 \uc790\uae08 \uc720\uc785 \uc5ec\uac74\uc774 \uc0c1\ub300\uc801\uc73c\ub85c "
        "\ub098\uc740 \ud3b8\uc73c\ub85c \ud574\uc11d\ub429\ub2c8\ub2e4."
    ),
]

lis = "\n".join(f'                    <li>{t}</li>' for t in items)
block = a + lis + "\n" + b
p.write_text(raw[:i] + block + raw[j + len(b) :], encoding="utf-8")
print("patched", p)
