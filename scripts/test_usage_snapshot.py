#!/usr/bin/env python3
# usage_snapshot 순수 함수 테스트 — 캐시 판정·요약·일자 upsert
#
# 네트워크를 타는 probe/fetch_team_state는 테스트하지 않는다. 판정 로직만 잠근다.
#
# 실행: python3 scripts/test_usage_snapshot.py

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from usage_snapshot import classify_cache, summarize, upsert_row  # noqa: E402


class TestClassifyCache(unittest.TestCase):
    # ⚠️ 2026-08-17 프로덕션 실측으로 확인된 전제 —
    #    Vercel 엣지는 오리진이 설정한 s-maxage를 **소비하고 클라이언트에게는 내보내지 않는다**.
    #    대신 `public, max-age=0, must-revalidate`로 재작성한다. no-store만 그대로 전달된다.
    #    따라서 Cache-Control만 보면 정상 캐시를 회귀로 오인한다 — x-vercel-cache를 함께 봐야 한다.

    def test_no_store는_회귀(self):
        self.assertEqual(classify_cache("no-store", "MISS"), "no-store")

    def test_no_store_조합도_회귀로_잡는다(self):
        # data.mjs가 원래 쓰던 형태 — s-maxage가 없으므로 캐시되지 않는다.
        self.assertEqual(classify_cache("no-store, no-cache, must-revalidate", "MISS"), "no-store")

    def test_엣지_적중은_캐시_정상(self):
        for v in ("HIT", "STALE", "hit", "stale"):
            self.assertEqual(classify_cache("public, max-age=0, must-revalidate", v), "ok", v)

    def test_엣지_재작성_형태는_MISS여도_캐시_정상(self):
        # 실측: kospi-live가 s-maxage=10인데 캐시 채우기 직후라 MISS + age 0으로 나온다.
        # 이걸 회귀로 잡으면 매일 거짓 경보가 뜬다.
        self.assertEqual(classify_cache("public, max-age=0, must-revalidate", "MISS"), "ok")

    def test_오리진_직접_응답의_s_maxage도_정상(self):
        # 엣지를 우회해 오리진을 직접 부르면 원본 헤더가 그대로 보인다.
        self.assertEqual(classify_cache("s-maxage=20, stale-while-revalidate=40", None), "ok")

    def test_대소문자_무관(self):
        self.assertEqual(classify_cache("S-MAXAGE=10", None), "ok")
        self.assertEqual(classify_cache("No-Store", "MISS"), "no-store")

    def test_헤더가_없으면_판정하지_않는다(self):
        # 응답을 못 받은 것과 no-store인 것은 다르다. 섞으면 거짓 경보가 난다.
        self.assertEqual(classify_cache("", None), "unknown")
        self.assertEqual(classify_cache(None, None), "unknown")

    def test_엣지를_안_거친_평범한_max_age는_판정하지_않는다(self):
        # x-vercel-cache가 없으면 엣지가 재작성한 형태인지 알 수 없다.
        self.assertEqual(classify_cache("public, max-age=0, must-revalidate", None), "unknown")


class TestSummarize(unittest.TestCase):
    def test_회귀와_장애를_각각_모은다(self):
        probes = [
            {"path": "/api/a", "status": 200, "cache": "ok"},
            {"path": "/api/b", "status": 200, "cache": "no-store"},
            {"path": "/api/c", "status": 502, "cache": "unknown"},
        ]
        s = summarize(probes)
        self.assertEqual(s["cacheable"], 1)
        self.assertEqual(s["total"], 3)
        self.assertEqual(s["regressed"], ["/api/b"])
        self.assertEqual(s["failed"], ["/api/c"])

    def test_정상일_때는_경보가_비어_있다(self):
        probes = [{"path": "/api/a", "status": 200, "cache": "ok"}]
        s = summarize(probes)
        self.assertEqual(s["regressed"], [])
        self.assertEqual(s["failed"], [])

    def test_응답_실패는_status가_None이라_failed로_잡힌다(self):
        probes = [{"path": "/api/a", "status": None, "error": "timeout", "cache": "unknown"}]
        self.assertEqual(summarize(probes)["failed"], ["/api/a"])


class TestUpsertRow(unittest.TestCase):
    def test_같은_날짜는_교체된다(self):
        rows = [{"date": "2026-08-18", "summary": {"cacheable": 1}}]
        out = upsert_row(rows, {"date": "2026-08-18", "summary": {"cacheable": 8}})
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["summary"]["cacheable"], 8)

    def test_다른_날짜는_추가되고_날짜순으로_정렬된다(self):
        rows = [{"date": "2026-08-20"}, {"date": "2026-08-18"}]
        out = upsert_row(rows, {"date": "2026-08-19"})
        self.assertEqual([r["date"] for r in out], ["2026-08-18", "2026-08-19", "2026-08-20"])

    def test_재실행으로_cpu_hours를_나중에_덧붙일_수_있다(self):
        # 자동 수집이 먼저 돌고, 대시보드 판독치를 나중에 같은 날짜에 얹는 사용 패턴.
        rows = upsert_row([], {"date": "2026-08-18", "summary": {}})
        rows = upsert_row(rows, {"date": "2026-08-18", "summary": {}, "cpu_hours_dashboard": 1.4})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["cpu_hours_dashboard"], 1.4)

    def test_빈_로그에서_시작해도_동작한다(self):
        self.assertEqual(upsert_row([], {"date": "2026-08-18"}), [{"date": "2026-08-18"}])


if __name__ == "__main__":
    unittest.main(verbosity=2)
