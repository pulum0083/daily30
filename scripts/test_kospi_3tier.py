# 코스피 아침 브리핑 3단 구조(30초 요약 카드·오늘의 이슈 점검) 컨텍스트·렌더 테스트 — 네트워크 없이 돈다(§63)
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_html as gh  # noqa: E402


def _rec(date, direction="상승 우위", ok=None, gap=None, basis="open"):
    r = {"type": "kospi", "date": date, "predicted_direction": direction, "is_correct": ok}
    if basis:
        r["basis"] = basis
    if gap is not None:
        r["actual_open_pct"] = gap
    return r


def _briefings(tmp_path, monkeypatch, rows):
    (tmp_path / "briefings.json").write_text(json.dumps({"briefings": rows}), encoding="utf-8")
    monkeypatch.setattr(gh, "DATA_DIR", tmp_path)


def _no_net(_d):
    raise AssertionError("채점 기록이 있으면 네트워크를 부르지 않는다")


# ── 어제 예측 칩 ──
def test_prev_chip_uses_scored_record(tmp_path, monkeypatch):
    _briefings(tmp_path, monkeypatch, [_rec("2026-10-22", "상승 우위", False, -1.14), _rec("2026-10-23", "하락 우위")])
    a = {}
    ctx = gh.build_prev_prediction(a, "2026-10-23", gap_fn=_no_net)
    assert ctx["prev_pred"] == {"label": "어제", "dir_word": "상승", "ok": False, "open_pct": -1.14}
    assert a["prev_prediction_result"]["date"] == "2026-10-22"     # 스냅샷에 함께 저장된다


def test_prev_chip_scores_unscored_record_from_open_gap(tmp_path, monkeypatch):
    """07:25엔 전날 예측이 아직 채점 전 — 시초가 갭을 직접 구해 같은 규칙으로 채점한다."""
    _briefings(tmp_path, monkeypatch, [_rec("2026-10-21", "상승 우위", True, 0.8), _rec("2026-10-22", "하락 우위")])
    ctx = gh.build_prev_prediction({}, "2026-10-23", gap_fn=lambda d: (5500.0, 5600.0, -1.79) if d == "2026-10-22" else None)
    assert ctx["prev_pred"]["ok"] is True and ctx["prev_pred"]["open_pct"] == -1.79


def test_prev_chip_omitted_when_gap_unavailable_no_older_fallback(tmp_path, monkeypatch):
    """§16 — 최근 항목을 채점할 수 없으면 더 오래된 결과로 대신하지 않고 칩을 뺀다."""
    _briefings(tmp_path, monkeypatch, [_rec("2026-10-21", "상승 우위", True, 0.8), _rec("2026-10-22", "하락 우위")])
    a = {}
    assert gh.build_prev_prediction(a, "2026-10-23", gap_fn=lambda d: None) == {}
    assert "prev_prediction_result" not in a


def test_prev_chip_skips_close_basis_record(tmp_path, monkeypatch):
    _briefings(tmp_path, monkeypatch, [_rec("2026-10-08", "상승 우위", True, 0.5, basis=None)])
    assert gh.build_prev_prediction({}, "2026-10-13", gap_fn=_no_net) == {}


def test_prev_chip_prefers_snapshot_and_labels_monday(tmp_path, monkeypatch):
    monkeypatch.setattr(gh, "DATA_DIR", tmp_path)   # briefings.json 없어도 스냅샷 값이면 된다
    a = {"prev_prediction_result": {"date": "2026-10-23", "direction": "하락 우위", "ok": True, "open_pct": -2.1}}
    ctx = gh.build_prev_prediction(a, "2026-10-26", gap_fn=_no_net)
    assert ctx["prev_pred"]["label"] == "지난 금요일"          # 월요일에 '어제'라고 쓰지 않는다(§24)
    assert gh._prev_label("2026-09-30", "2026-10-02") == "9/30(수)"


# ── 요약 카드 렌더 ──
def _hero_ctx(**kw):
    ctx = gh.build_prediction({"prediction": {"direction": "하락 우위", "up_pct": 7, "down_pct": 93,
                                              "confidence": 82, "basis": "open"}}, "KOSPI", "x", "07:29")
    ctx.update(gh.build_hero({"prediction": {"direction": "하락 우위"}}, "2026-10-23"))
    ctx["todays_view"] = {"view_title": "헤드라인", "dek": "보조 <b>-3.52%</b> 문장"}
    ctx.update(kw)
    return ctx


def test_hero_renders_prediction_headline_dek_and_definition():
    html = gh.make_env().get_template("sections/briefing_hero.html").render(**_hero_ctx())
    assert "10월 23일(금) 시초가 방향 예측" in html and "07:29 생성" in html
    assert "93%" in html and "신뢰도 82%" in html and "헤드라인" in html and "<b>-3.52%</b>" in html
    assert "장중 흐름과 종가는 예측하지 않아요" in html
    assert "bx-chip" not in html                      # 어제 예측 결과가 없으면 칩을 뺀다


def test_hero_neutral_shows_up_probability():
    ctx = _hero_ctx(**gh.build_hero({"prediction": {"direction": "중립", "up_pct": 52}}, "2026-10-23"))
    html = gh.make_env().get_template("sections/briefing_hero.html").render(**ctx)
    assert "52%" in html and "위로 열릴 확률" in html


def test_hero_prev_chip_render():
    ctx = _hero_ctx(prev_pred={"label": "어제", "dir_word": "상승", "ok": False, "open_pct": -1.14})
    html = gh.make_env().get_template("sections/briefing_hero.html").render(**ctx)
    assert "어제 예측" in html and "상승 → 빗나감" in html and "시초가 -1.14%" in html
    assert "적중률" not in html                       # 적중률 칩은 넣지 않는다(사용자 결정)


# ── 오늘의 이슈 점검 ──
US_CARDS = [
    {"title": "메모리·반도체 장비주 동반 급락 — 프리마켓 최대 변수",
     "sides": [{"side": "down", "label": "x", "marks": [{"ticker": "MU", "name": "MU", "pct": -6.26}], "proxy": None}],
     "check_line": "메모리는 <b>내렸어요</b>"},
    {"title": "S&P·다우 선물 동반 약세",
     "sides": [{"side": "down", "label": "지수 전반", "marks": [{"ticker": "^GSPC", "name": "S&P500", "pct": -1.21}], "proxy": "S&P500"}],
     "check_line": "지수 전반은 <b>내렸어요</b>"},
]


def _issue_html(**ctx):
    return gh.make_env().get_template("sections/issue_check.html").render(**ctx)


def test_issue_cards_trim_title_and_link_related_only_when_page_exists(monkeypatch):
    monkeypatch.setattr(gh, "_pick_detail_url", lambda code, t: "/stocks/005930/" if code == "005930" else "")
    cards = gh.build_issue_check(US_CARDS)["ic_us_cards"]
    assert cards[0]["title"] == "메모리·반도체 장비주 동반 급락"
    assert cards[0]["related"] == [{"name": "삼성전자", "url": "/stocks/005930/"}]   # 상세 페이지 없는 종목은 뺀다(§36)
    assert cards[1]["related"] == [] and cards[1]["proxy"] == "S&P500"
    html = _issue_html(ic_us_cards=cards, us_issue_label="간밤", us_issue_session="2026-10-22")
    assert "관련 종목" in html and "AI 판단" not in html and "코스피 ▼" not in html
    assert "S&P500 실측으로 봤어요" in html and "/briefings/2026-10-22/us/" in html
    assert "MU <b>−6.26%</b>" in html


def test_issue_section_omitted_when_everything_empty():
    assert "ic-section" not in _issue_html(ic_us_cards=[], domestic_issues=[], ib_korea_views=[], todays_view={})


def test_issue_cards_each_omitted_independently():
    tv = {"outlook": [{"tag": "watch", "text": "메모리 <b>+6.49%</b>, EWY <b>+3.94%</b> 반응을 보세요."}]}
    html = _issue_html(ic_us_cards=[], domestic_issues=[], ib_korea_views=[], todays_view=tv)
    assert "오늘 볼 것 · AI 해석" in html and "개장 뒤 확인할 한 가지" in html
    assert "국내 · 뉴스" not in html and "외국계 · 뉴스" not in html and "미국 · 실측" not in html
    # §35 — li의 직접 자식은 span 하나(문장 속 <b>가 flex item으로 쪼개지지 않게)
    assert "<li><span>메모리 <b>+6.49%</b>, EWY <b>+3.94%</b> 반응을 보세요.</span></li>" in html


def test_domestic_and_ib_cards_render_links():
    html = _issue_html(
        domestic_issues=[{"title": "한은 동결", "source": "연합", "url": "https://a.example/1"}],
        domestic_card_title=gh._domestic_card_title("2026-10-23 15:30"),
        ib_korea_views=[{"house": "JP모건", "sentiment": "bull", "summary": "비중 확대", "source": "한경", "url": "https://b.example/2"}])
    assert "10월 23일 장 마감 이후 국내 소식" in html and 'href="https://a.example/1"' in html
    assert "외국계 · 뉴스" in html and "JP모건" in html and "강세" in html and 'href="https://b.example/2"' in html


def test_issue_label_follows_session_on_monday():
    html = _issue_html(ic_us_cards=gh.build_issue_check(US_CARDS[1:])["ic_us_cards"], us_issue_label="지난 금요일")
    assert "지난 금요일 미국 · 실측" in html and "간밤" not in html


# ── 성적표 라벨 ──
def _scored(n):
    return [_rec(f"2026-10-{d:02d}", "상승 우위", d % 3 != 0, 0.5 if d % 2 else -0.5) for d in range(1, n + 1)]


def test_scorecard_hides_recent15_until_15_records(tmp_path, monkeypatch):
    _briefings(tmp_path, monkeypatch, _scored(9))
    ctx = gh.build_scorecard("kospi")
    assert ctx["sc_show_recent15"] is False and ctx["sc_cum_count"] == 9
    html = gh.make_env().get_template("sections/_scorecard.html").render(**ctx)
    assert "최근 15건" not in html and "누적 9건" in html


def test_scorecard_shows_recent15_from_15_records(tmp_path, monkeypatch):
    _briefings(tmp_path, monkeypatch, _scored(16))
    ctx = gh.build_scorecard("kospi")
    html = gh.make_env().get_template("sections/_scorecard.html").render(**ctx)
    assert ctx["sc_show_recent15"] is True and "최근 15건" in html


# ── 템플릿 구조 ──
def test_kospi_template_three_tiers_and_close_keeps_shared_sections():
    k = (gh.TEMPLATES_DIR / "briefings" / "kospi.html").read_text(encoding="utf-8")
    i_hero, i_issue, i_ma5 = (k.index(f"sections/{n}.html") for n in ("briefing_hero", "issue_check", "monthly_ma5"))
    assert i_hero < i_issue < i_ma5
    for gone in ("todays_view", "prediction_strip", "why_what_so", "_comfort_line", "us_issue_results", "domestic_issues"):
        assert f"sections/{gone}.html" not in k
    c = (gh.TEMPLATES_DIR / "briefings" / "close.html").read_text(encoding="utf-8")
    for shared in ("scenario_split", "qa", "signal_board", "_comfort_line"):
        assert f"sections/{shared}.html" in c and (gh.TEMPLATES_DIR / "sections" / f"{shared}.html").exists()


def test_close_shared_sections_still_render_title_and_dek():
    """마감은 format_in_view를 넘기지 않으므로 공유 섹션이 제목과 close_dek를 그대로 그린다."""
    env = gh.make_env()
    for name in ("scenario_split", "qa", "signal_board"):
        html = env.get_template(f"sections/{name}.html").render(reason_title="마감 제목", close_dek="마감 서브 문장")
        assert "마감 제목" in html and 'class="close-dek"' in html and "마감 서브 문장" in html, name
