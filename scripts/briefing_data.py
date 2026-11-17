"""브리핑의 선택적 데이터 로딩 — 저장된 스냅샷 우선, 새 파일은 발행 날짜 확인.

파일이 없거나 깨졌거나 객체가 아니면 해당 섹션을 생략한다. 호출자가 경로를
넘기므로 파일 저장 위치와 HTML 생성·텔레그램 전송에 의존하지 않는다.
"""
import json
from pathlib import Path


def read_dated_payload(path: Path, target_date: str = ""):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        print(f"[briefing_data] {path.name} 읽기 실패: {exc} — 섹션 생략")
        return None
    if not isinstance(data, dict):
        print(f"[briefing_data] {path.name} 객체가 아닌 데이터 — 섹션 생략")
        return None
    if target_date and data.get("date") != target_date:
        print(f"[briefing_data] {path.name} 날짜 불일치({data.get('date')} ≠ {target_date}) — 섹션 생략")
        return None
    return data


def read_snapshot_payload(analysis: dict, key: str, data_dir: Path, target_date: str = ""):
    """발행본 재생성은 기존 스냅샷을 보존하고, 새로 읽은 유효 데이터만 저장한다."""
    data = analysis.get(key)
    if isinstance(data, dict):
        return data
    data = read_dated_payload(data_dir / f"{key}.json", target_date)
    if data is not None:
        analysis[key] = data
    return data
