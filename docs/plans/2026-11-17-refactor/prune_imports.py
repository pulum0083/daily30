# pyflakes가 '안 쓴다'고 한 import 이름만 지운다 — 다시 내보내는 줄(# noqa: F401)은 건드리지 않는다
import re
import subprocess
import sys
from collections import defaultdict

files = sys.argv[1:]
out = subprocess.run([sys.executable, "-m", "pyflakes", *files], capture_output=True, text=True).stdout
unused = defaultdict(lambda: defaultdict(set))
for line in out.splitlines():
    m = re.match(r"(.+?):(\d+):\d+:? '([^']+)' imported but unused", line)
    if m:
        name = m.group(3)
        bound = name.split(" as ")[-1].split(".")[-1] if " as " in name else name.split(".")[-1]
        unused[m.group(1)][int(m.group(2))].add(bound)
for f, by_line in unused.items():
    lines = open(f, encoding="utf-8").read().split("\n")
    for ln, names in by_line.items():
        text = lines[ln - 1]
        if "noqa" in text or "(" in text and not text.rstrip().endswith(")"):
            continue
        m = re.match(r"(\s*)from (\S+) import (.+)$", text)
        if m:
            parts = [p.strip() for p in m.group(3).split(",")]
            keep = [p for p in parts if p.split(" as ")[-1].strip() not in names]
            lines[ln - 1] = f"{m.group(1)}from {m.group(2)} import {', '.join(keep)}" if keep else None
            continue
        m = re.match(r"(\s*)import (\S+)$", text)
        if m and (m.group(2) in names or m.group(2).split(".")[-1] in names):
            lines[ln - 1] = None
    open(f, "w", encoding="utf-8").write("\n".join(l for l in lines if l is not None))
    print("정리:", f, sum(len(v) for v in by_line.values()))
