# 증권가 시황 후보 필터 테스트 — 아침 리포트(Daily·Morning·Snapshot) 제외(2026-11-10 실사고, 네트워크 없음)
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_research_reports as fr  # noqa: E402

LIST = [
    {"researchId": 1, "title": "Eugene Daily Snapshot - 코스피 5천 가까스로 사수", "brokerName": "유진투자증권", "writeDate": "2026-11-10"},
    {"researchId": 2, "title": "Daily Morning Brief(2026.11.10)", "brokerName": "다올투자증권", "writeDate": "2026-11-10"},
    {"researchId": 3, "title": "마켓레이더 - 공포에서 안도로, CPI·CRWV는 대기 (11월 10일)", "brokerName": "신한투자증권", "writeDate": "2026-11-10"},
    {"researchId": 4, "title": "국내주식 마감 시황 (26.11.09) - 이제 하다하다", "brokerName": "유안타증권", "writeDate": "2026-11-10"},
    {"researchId": 5, "title": "국내 증시 장전 체크포인트", "brokerName": "키움증권", "writeDate": "2026-11-10"},
    {"researchId": 6, "title": "코스피 마감 코멘트", "brokerName": "대신증권", "writeDate": "2026-11-10"},
]


def test_morning_reports_excluded(monkeypatch):
    monkeypatch.setattr(fr, "_get_json", lambda url: LIST)
    picks = fr._list_today("2026-11-10")
    assert [p["firm"] for p in picks] == ["신한투자증권", "대신증권"]
