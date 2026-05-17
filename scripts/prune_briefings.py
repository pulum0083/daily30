# 15일 초과 브리핑 파일 자동 삭제 스크립트
import os
import re
import shutil
from datetime import date, timedelta

BRIEFINGS_DIR = os.path.join(os.path.dirname(__file__), '..', 'web', 'briefings')
KEEP_DAYS = 15
DATE_RE = re.compile(r'^(\d{4}-\d{2}-\d{2})')

def prune():
    cutoff = date.today() - timedelta(days=KEEP_DAYS)
    removed = []

    briefings = os.path.realpath(BRIEFINGS_DIR)

    for entry in os.scandir(briefings):
        m = DATE_RE.match(entry.name)
        if not m:
            continue
        try:
            entry_date = date.fromisoformat(m.group(1))
        except ValueError:
            continue

        if entry_date < cutoff:
            if entry.is_dir():
                shutil.rmtree(entry.path)
            else:
                os.remove(entry.path)
            removed.append(entry.name)

    # ko-close 하위 디렉토리도 동일 규칙 적용
    ko_close = os.path.join(briefings, 'ko-close')
    if os.path.isdir(ko_close):
        for entry in os.scandir(ko_close):
            m = DATE_RE.match(entry.name)
            if not m:
                continue
            try:
                entry_date = date.fromisoformat(m.group(1))
            except ValueError:
                continue
            if entry_date < cutoff:
                if entry.is_dir():
                    shutil.rmtree(entry.path)
                else:
                    os.remove(entry.path)
                removed.append(f'ko-close/{entry.name}')

    if removed:
        print(f"[prune] {cutoff} 이전 {len(removed)}개 삭제:")
        for r in sorted(removed):
            print(f"  - {r}")
    else:
        print(f"[prune] {cutoff} 이전 파일 없음 — 정리 불필요")

if __name__ == '__main__':
    prune()
