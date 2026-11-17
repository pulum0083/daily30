# 큰 파이썬 모듈의 최상위 정의를 이름 목록대로 새 모듈로 옮기고 import를 자동으로 만드는 도구
"""사용법: python3 split_module.py <원본.py> <계획.json> [--dry]

계획.json
  {"modules": [{"name": "html_common", "header": "# 한 줄 역할", "items": ["BASE_DIR", "load_json", ...]}, ...]}

- 옮긴 정의는 원래 순서를 지킨다. 바로 위에 붙은 주석 줄도 함께 옮긴다.
- 새 모듈은 원본의 import 중 실제로 쓰는 것만 가져오고, 다른 새 모듈·원본에 남은 이름을 참조하면 알려 준다.
  원본에 남은 이름을 참조하면 순환 import가 되므로 멈춘다(계획을 고쳐야 한다).
- 원본에는 옮긴 이름 전부를 다시 import하는 줄을 넣는다 — 외부(call_claude·테스트)가 원본.이름으로 계속 읽을 수 있다.
"""
import ast
import json
import sys
from pathlib import Path

src_path = Path(sys.argv[1])
plan = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
dry = "--dry" in sys.argv
lines = src_path.read_text(encoding="utf-8").split("\n")
tree = ast.parse("\n".join(lines))
src_mod = src_path.stem


def bound_names(node):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [node.name]
    if isinstance(node, ast.Assign):
        out = []
        for t in node.targets:
            for n in ast.walk(t):
                if isinstance(n, ast.Name):
                    out.append(n.id)
        return out
    if isinstance(node, (ast.AnnAssign, ast.AugAssign)) and isinstance(node.target, ast.Name):
        return [node.target.id]
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return [(a.asname or a.name).split(".")[0] for a in node.names]
    if isinstance(node, ast.Try):   # try: import ... except ImportError: import ...
        out = []
        for b in node.body + [h for hh in node.handlers for h in hh.body]:
            out += bound_names(b)
        return out
    return []


def is_import(node):
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return True
    return isinstance(node, ast.Try) and all(isinstance(b, (ast.Import, ast.ImportFrom)) for b in node.body)


def used_names(node):
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


# 최상위 문장마다 [시작줄, 끝줄] — 바로 위 주석 줄을 붙인다(빈 줄 하나 위의 주석까지는 붙이지 않는다)
stmts = []
prev_end = 0
for node in tree.body:
    start = node.lineno
    if getattr(node, "decorator_list", None):
        start = min(d.lineno for d in node.decorator_list)
    s = start
    while s - 1 > prev_end and lines[s - 2].lstrip().startswith("#"):
        s -= 1
    stmts.append({"node": node, "start": s, "end": node.end_lineno, "names": bound_names(node)})
    prev_end = node.end_lineno

defined = {}
for i, st in enumerate(stmts):
    for n in st["names"]:
        defined.setdefault(n, i)

owner = {}   # 이름 → 새 모듈
for m in plan["modules"]:
    for it in m["items"]:
        if it not in defined:
            sys.exit(f"원본에 없는 이름: {it}")
        if it in owner:
            sys.exit(f"두 모듈에 배정됨: {it}")
        owner[it] = m["name"]

stmt_owner = {}
for i, st in enumerate(stmts):
    if is_import(st["node"]):
        continue
    mods = {owner[n] for n in st["names"] if n in owner}
    if len(mods) > 1:
        sys.exit(f"한 문장이 여러 모듈로 나뉨: {st['names']}")
    if mods:
        missing = [n for n in st["names"] if n not in owner]
        if missing:
            sys.exit(f"같은 문장의 이름 일부만 배정됨: {st['names']}")
        stmt_owner[i] = mods.pop()

import_stmts = [st for st in stmts if is_import(st["node"])]
import_of = {}   # 이름 → import 문장
for st in import_stmts:
    for n in st["names"]:
        import_of[n] = st

new_mods = [m["name"] for m in plan["modules"]]
problems = []
files = {}
deps = {m: set() for m in new_mods}
for m in plan["modules"]:
    idx = [i for i, o in stmt_owner.items() if o == m["name"]]
    idx.sort()
    used = set()
    for i in idx:
        used |= used_names(stmts[i]["node"])
    mine = {n for i in idx for n in stmts[i]["names"]}
    need_imports = []
    for st in import_stmts:
        if any(n in used for n in st["names"]) and st not in need_imports:
            need_imports.append(st)
    from_new = {}
    for n in sorted(used - mine):
        if n in owner and owner[n] != m["name"]:
            from_new.setdefault(owner[n], []).append(n)
            deps[m["name"]].add(owner[n])
        elif n in defined and n not in owner and not is_import(stmts[defined[n]]["node"]):
            problems.append(f"{m['name']}: 원본에 남는 '{n}'을 참조 — 순환 import")
    body = [m["header"], ""]
    if any(isinstance(st["node"], ast.ImportFrom) and st["node"].module == "__future__" for st in import_stmts):
        body.append("from __future__ import annotations")   # 3.9에서 'dict | None' 힌트를 쓰려면 모든 새 모듈에 필요
        need_imports = [st for st in need_imports if not (isinstance(st["node"], ast.ImportFrom) and st["node"].module == "__future__")]

    def is_sibling(st):
        n = st["node"]
        if isinstance(n, ast.Try):
            return True
        if isinstance(n, ast.Import):
            return all((src_path.parent / f"{a.name.split('.')[0]}.py").exists() for a in n.names)
        return (isinstance(n, ast.ImportFrom) and n.level == 0 and n.module
                and (src_path.parent / f"{n.module.split('.')[0]}.py").exists())

    ext = [st for st in need_imports if not is_sibling(st)]
    sib = [st for st in need_imports if is_sibling(st)]
    for st in ext:   # 붙은 주석은 빼고 import 줄만
        body += lines[st["node"].lineno - 1: st["end"]]
    if sib or from_new:
        if not any(l.strip() == "import sys" for l in body):
            body.append("import sys")
        if not any(l.strip() == "from pathlib import Path" for l in body):
            body.append("from pathlib import Path")
        body.append("")
        body.append("sys.path.insert(0, str(Path(__file__).resolve().parent))")
        for st in sib:
            body += lines[st["node"].lineno - 1: st["end"]]
    for mod in new_mods:
        if mod in from_new:
            body.append(f"from {mod} import " + ", ".join(from_new[mod]))
    prev = None
    for i in idx:
        if prev is not None and i == prev + 1:
            body += lines[stmts[prev]["end"]: stmts[i]["start"] - 1]   # 원래 붙어 있던 문장은 원래 간격 그대로
        else:
            body += ["", ""]
        body += lines[stmts[i]["start"] - 1: stmts[i]["end"]]
        prev = i
    files[m["name"]] = "\n".join(body).rstrip() + "\n"
    if "--why" in sys.argv:
        print(m["name"], "←", from_new)

# 새 모듈끼리 순환 검사
def cyc(m, seen):
    for d in deps[m]:
        if d in seen:
            problems.append("새 모듈 순환: " + " → ".join(seen + [d]))
            continue
        cyc(d, seen + [d])


for m in new_mods:
    cyc(m, [m])

if problems:
    print("\n".join(sorted(set(problems))))
    sys.exit(1)

# 원본 다시 쓰기
drop = set()
for i in stmt_owner:
    drop |= set(range(stmts[i]["start"], stmts[i]["end"] + 1))
# 옮긴 코드 앞의 떠 있는 주석 문단(구역 제목 등)도 지운다 — 다음 코드 줄이 옮겨 갔으면 그 문단은 옮긴 코드의 설명이다
in_stmt = set()
for st in stmts:
    in_stmt |= set(range(st["start"], st["end"] + 1))
paras, cur = [], []
for ln, text in enumerate(lines, start=1):
    if ln not in in_stmt and text.lstrip().startswith("#"):
        cur.append(ln)
    else:
        if cur:
            paras.append(cur)
        cur = []
for para in reversed(paras):
    j = para[-1] + 1
    while j <= len(lines) and not lines[j - 1].strip():
        j += 1
    if j <= len(lines) and j in drop:
        drop |= set(para)
# 다시 내보내는 줄은 맨 위 import 묶음 바로 뒤에 둔다(파일 중간의 늦은 import 뒤가 아니라)
first_body = min((st["start"] for st in stmts if not is_import(st["node"])
                  and not (isinstance(st["node"], ast.Expr))), default=len(lines))
last_import_end = max(st["end"] for st in import_stmts if st["end"] < first_body)
top_level_src = "\n".join(lines[:first_body])
out = []
for ln, text in enumerate(lines, start=1):
    if ln in drop:
        continue
    out.append(text)
    if ln == last_import_end:
        # 의존 순서대로 다시 내보낸다
        order, seen = [], set()

        def visit(mod):
            if mod in seen:
                return
            seen.add(mod)
            for d in sorted(deps[mod]):
                visit(d)
            order.append(mod)

        for mod in new_mods:
            visit(mod)
        out.append("")
        if "sys.path.insert(0, str(Path(__file__).resolve().parent))" not in top_level_src:
            out.append("sys.path.insert(0, str(Path(__file__).resolve().parent))")
        out.append(f"# 역할별 모듈로 나눈 정의 — 원래 이름({src_mod}.X)으로도 그대로 읽힌다.")
        for mod in order:
            names = [n for n in owner if owner[n] == mod]
            out.append(f"from {mod} import (  # noqa: F401")
            for k in range(0, len(names), 6):
                out.append("    " + ", ".join(names[k:k + 6]) + ",")
            out.append(")")
text = "\n".join(out)
while "\n\n\n\n" in text:
    text = text.replace("\n\n\n\n", "\n\n\n")

used_after = used_names(ast.parse(text))
print("원본에 남는 줄:", len(text.split("\n")))
for mod, body in files.items():
    print(f"{mod}.py: {len(body.splitlines())}줄, 의존 {sorted(deps[mod])}")
if not dry:
    if "--source-only" not in sys.argv:
        for mod in files:
            if (src_path.parent / f"{mod}.py").exists():
                sys.exit(f"이미 있는 파일: {mod}.py")
        for mod, body in files.items():
            (src_path.parent / f"{mod}.py").write_text(body, encoding="utf-8")
    src_path.write_text(text, encoding="utf-8")
