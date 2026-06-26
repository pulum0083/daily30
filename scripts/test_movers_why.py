# 왜움직였나 엔진 순수함수 단위 테스트 (네트워크 없음)
#!/usr/bin/env python3
import fetch_movers_why as m


def test_select_movers_threshold_and_dedup():
    rows = [
        {"code": "A", "name": "에이", "change_pct": 5.0, "surge": 1.1},
        {"code": "B", "name": "비",  "change_pct": -3.0, "surge": 1.0},
        {"code": "C", "name": "씨",  "change_pct": 0.5, "surge": 2.0},
        {"code": "D", "name": "디",  "change_pct": 0.3, "surge": 1.1},
    ]
    out = m.select_movers(rows, max_n=10)
    codes = [r["code"] for r in out]
    assert "D" not in codes
    assert set(codes) == {"A", "B", "C"}


def test_select_movers_caps_at_max_n():
    rows = [{"code": str(i), "name": str(i), "change_pct": 9.0 - i*0.1, "surge": 1.0}
            for i in range(20)]
    out = m.select_movers(rows, max_n=10)
    assert len(out) == 10
    assert out[0]["code"] == "0"


def test_parse_naver_realtime():
    data = {"datas": [{
        "itemCode": "005930", "stockName": "삼성전자",
        "closePrice": "358,500", "fluctuationsRatio": "5.29",
        "accumulatedTradingVolume": "12,345,678",
    }]}
    r = m.parse_naver_realtime(data, vol_avg20=6000000)
    assert r["code"] == "005930"
    assert r["name"] == "삼성전자"
    assert r["change_pct"] == 5.29
    assert r["volume"] == 12345678
    assert round(r["surge"], 2) == 2.06


def test_parse_naver_realtime_missing():
    assert m.parse_naver_realtime({"datas": []}, vol_avg20=1) is None


def test_classify_tier():
    assert m.classify_tier(None, 5.0) == "none"
    assert m.classify_tier({"sentiment": "pos", "headline": "엔비디아 공급 확대"}, 5.0) == "why"
    assert m.classify_tier({"sentiment": "neg", "headline": "실적 쇼크 급락"}, -4.0) == "why"
    assert m.classify_tier({"sentiment": "pos", "headline": "수주 호재"}, -4.0) == "related"
    assert m.classify_tier({"sentiment": "neu", "headline": "급등 기대감"}, -4.0) == "related"
    assert m.classify_tier({"sentiment": "neu", "headline": "거래량 증가"}, 0.5) == "related"


def test_infer_sentiment():
    assert m._infer_sentiment("SK하이닉스 급락에 코스피 휘청") == "neg"
    assert m._infer_sentiment("삼성전자 신고가 돌파 강세") == "pos"
    assert m._infer_sentiment("현대차 신차 공개 행사 개최") == "neu"
    assert m._infer_sentiment("반등 시도했으나 급락 마감") == "neg"  # 하락어 우선


def test_fallback_event():
    a = {"time": "10:30", "headline": "알테오젠 급락 마감", "url": "http://x", "source": "연합"}
    ev = m._fallback_event(a)
    assert ev["summary"] == "알테오젠 급락 마감"  # 요약 대신 헤드라인 그대로
    assert ev["sentiment"] == "neg"
    assert ev["url"] == "http://x" and ev["time"] == "10:30"
