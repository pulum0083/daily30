#!/usr/bin/env python3
# rebuild-config-driven 브랜치 원본을 scripts/v2·web/v2 카나리 사본으로 동기화하는 스크립트
"""v2 카나리 하니스 동기화기.

작업 흐름:
  1. ../double-shot-v2src (rebuild-config-driven worktree)에서 v2 디자인·로직을 수정·커밋한다.
  2. 메인 리포에서 `python3 scripts/sync_v2.py` 를 실행한다.
  3. scripts/v2·web/v2 가 브랜치 최신 상태 + /v2/ 경로 패치로 재생성된다.
  4. 평소처럼 git add/commit/push 하면 라이브 /v2/ 에 반영된다.

수요일 컷오버 때 rebuild-config-driven 을 머지하면 브랜치에서 한 모든 수정이
그대로 라이브가 된다 → scripts/v2 수정 증발 위험 없음.

⚠️ scripts/v2·web/v2 를 직접 손으로 고치지 말 것. 이 스크립트가 매번 덮어쓴다.
원본은 항상 rebuild-config-driven 브랜치(=worktree)다.

패치 앵커가 하나라도 안 맞으면(브랜치 구조 변경 등) 즉시 에러로 중단된다.
"""

import shutil
import sys
from pathlib import Path

MAIN_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = MAIN_DIR.parent / "double-shot-v2src"  # rebuild-config-driven worktree

# 브랜치에서 사본을 직접 손대지 말라는 안내(생성 사본 최상단 주석엔 안 넣음 — 파일 동일성 유지 위해)

# ── 패치 정의: (설명, old, new). old 가 정확히 1회 나와야 한다(아니면 에러). ──
GEN_HTML_PATCHES = [
    ("BASE_DIR 루트 보정",
     'BASE_DIR = Path(__file__).resolve().parent.parent\n',
     'BASE_DIR = Path(__file__).resolve().parent.parent.parent  # scripts/v2/ → 리포 루트\n'),
    ("DATA_DIR 격리",
     'DATA_DIR = BASE_DIR / "data"\n',
     'DATA_DIR = BASE_DIR / "data" / "v2"           # v2 격리: 입출력 데이터\n'),
    ("BRIEFINGS_DIR 격리",
     'BRIEFINGS_DIR = WEB_DIR / "briefings"\n',
     'BRIEFINGS_DIR = WEB_DIR / "v2" / "briefings"  # v2 격리: 출력 루트\n'),
    ("네비 prev_url",
     'prev_url = f"/briefings/{dirs[idx-1]}/{internal_type}/" if idx > 0 else None',
     'prev_url = f"/v2/briefings/{dirs[idx-1]}/{internal_type}/" if idx > 0 else None'),
    ("네비 next_url",
     'next_url = f"/briefings/{dirs[idx+1]}/{internal_type}/" if idx < len(dirs) - 1 else None',
     'next_url = f"/v2/briefings/{dirs[idx+1]}/{internal_type}/" if idx < len(dirs) - 1 else None'),
    ("목록 셀 url",
     'base["url"] = f"/briefings/{d}/{btype}/"',
     'base["url"] = f"/v2/briefings/{d}/{btype}/"'),
    # 에셋 경로(2회 등장): replace_all 처리
    ("에셋 css/js (전체)",
     '"css_path": "/assets/style.css", "js_path": "/assets/main.js"',
     '"css_path": "/v2/assets/style.css", "js_path": "/v2/assets/main.js"',
     "all"),
]

CALL_CLAUDE_PATCHES = [
    ("BASE_DIR 루트 보정",
     'BASE_DIR = Path(__file__).parent.parent\n',
     'BASE_DIR = Path(__file__).resolve().parent.parent.parent  # scripts/v2/ → 리포 루트\n'),
    ("DATA_DIR 격리",
     'DATA_DIR = BASE_DIR / "data"\n',
     'DATA_DIR = BASE_DIR / "data" / "v2"   # v2 격리: 입출력 데이터\n'),
    ("generate_html 경로 (전체)",
     'BASE_DIR / "scripts" / "generate_html.py"',
     'BASE_DIR / "scripts" / "v2" / "generate_html.py"',
     "all"),
]

BASE_HTML_PATCHES = [
    ("favicon",
     'href="/favicon.svg"',
     'href="/v2/favicon.svg"'),
    ("gnb 로고",
     '<a class="gnb__logo" href="/briefings">',
     '<a class="gnb__logo" href="/v2/briefings">'),
]

# scripts/v2/templates 에서 제거할 레거시(미사용) 템플릿
LEGACY_TEMPLATES = ["briefing.html", "briefing_closing.html", "index.html"]


def apply_patches(text: str, patches: list, fname: str) -> str:
    for p in patches:
        desc, old, new = p[0], p[1], p[2]
        mode = p[3] if len(p) > 3 else "one"
        count = text.count(old)
        if mode == "all":
            if count == 0:
                sys.exit(f"[sync_v2] ERROR {fname}: 패치 앵커 '{desc}' 0회 — 브랜치 구조 변경됨. 패치 정의 갱신 필요.")
            text = text.replace(old, new)
        else:
            if count != 1:
                sys.exit(f"[sync_v2] ERROR {fname}: 패치 앵커 '{desc}' {count}회 (1회 기대) — 패치 정의 갱신 필요.")
            text = text.replace(old, new)
    return text


def patch_file(src: Path, dst: Path, patches: list):
    text = src.read_text(encoding="utf-8")
    text = apply_patches(text, patches, dst.name)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text, encoding="utf-8")
    print(f"[sync_v2] patched {dst.relative_to(MAIN_DIR)}")


def copy_tree(src: Path, dst: Path):
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    print(f"[sync_v2] copied  {dst.relative_to(MAIN_DIR)}/")


def main():
    if not SRC_DIR.exists():
        sys.exit(f"[sync_v2] ERROR: worktree 없음 {SRC_DIR}\n"
                 f"  git worktree add \"{SRC_DIR}\" rebuild-config-driven 로 생성하세요.")

    # 브랜치 미커밋 경고(증발 방지 — 컷오버는 커밋된 것만 머지)
    import subprocess
    dirty = subprocess.run(["git", "-C", str(SRC_DIR), "status", "--porcelain"],
                           capture_output=True, text=True).stdout.strip()
    if dirty:
        print("[sync_v2] ⚠️  worktree에 미커밋 변경이 있습니다. sync는 현재 작업트리 파일을 그대로 반영하지만,")
        print("[sync_v2] ⚠️  수요일 컷오버는 '커밋된' 브랜치만 머지합니다. 잊지 말고 worktree에서 커밋하세요:")
        print(f"[sync_v2] ⚠️    git -C \"{SRC_DIR}\" add -A && git -C \"{SRC_DIR}\" commit -m ...")

    scripts_v2 = MAIN_DIR / "scripts" / "v2"
    web_v2 = MAIN_DIR / "web" / "v2"

    # 1. generate_html.py (패치)
    patch_file(SRC_DIR / "scripts" / "generate_html.py",
               scripts_v2 / "generate_html.py", GEN_HTML_PATCHES)
    # 2. call_claude.py (패치)
    patch_file(SRC_DIR / "scripts" / "call_claude.py",
               scripts_v2 / "call_claude.py", CALL_CLAUDE_PATCHES)
    # 3. config (무변경 복사)
    copy_tree(SRC_DIR / "scripts" / "config", scripts_v2 / "config")
    # 4. templates (복사 후 base.html 패치 + 레거시 제거)
    copy_tree(SRC_DIR / "scripts" / "templates", scripts_v2 / "templates")
    base_html = scripts_v2 / "templates" / "base.html"
    base_html.write_text(
        apply_patches(base_html.read_text(encoding="utf-8"), BASE_HTML_PATCHES, "base.html"),
        encoding="utf-8")
    print(f"[sync_v2] patched scripts/v2/templates/base.html")
    for name in LEGACY_TEMPLATES:
        f = scripts_v2 / "templates" / name
        if f.exists():
            f.unlink()
            print(f"[sync_v2] removed scripts/v2/templates/{name} (레거시)")
    # 5. web/assets (무변경 복사)
    copy_tree(SRC_DIR / "web" / "assets", web_v2 / "assets")
    # 6. web/favicon.svg (무변경 복사)
    (web_v2).mkdir(parents=True, exist_ok=True)
    shutil.copy2(SRC_DIR / "web" / "favicon.svg", web_v2 / "favicon.svg")
    print(f"[sync_v2] copied  web/v2/favicon.svg")

    # 7. 산출물 구문 검사
    import ast
    for f in [scripts_v2 / "generate_html.py", scripts_v2 / "call_claude.py"]:
        ast.parse(f.read_text(encoding="utf-8"))
    print("[sync_v2] syntax OK")
    print("[sync_v2] ✅ 완료. 이제 git add scripts/v2 web/v2 && commit && push 하세요.")


if __name__ == "__main__":
    main()
