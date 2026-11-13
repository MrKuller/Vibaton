from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

from app import ai, geo, status as st
from app.weather import Weather

NOW = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
CALM = Weather(temp_c=-12, wind_ms=3, wind_gust_ms=5, wind_from_deg=180,
               days=[{"date": "a", "t_max": -12, "t_min": -20}, {"date": "b", "t_max": -11, "t_min": -19}])


def zone(**kw):
    return NS(**{"ban": False, "ban_text": None, "offshore_from": [[0, 90]], **kw})


def obs(type_, minutes, wrong=0, confirm=0, hazard="none"):
    return NS(type=type_, observed_at=NOW - timedelta(minutes=minutes), ai_hazard=hazard,
              counts={"confirm": confirm, "changed": 0, "wrong": wrong})


def test_no_data_is_not_safe():
    assert st.compute(zone(), [], CALM, NOW).level == "nodata"


def test_one_danger_beats_many_calm():
    o = [obs("clear", 10)] * 10 + [obs("hole", 30)]
    s = st.compute(zone(), o, CALM, NOW)
    assert s.level == "danger" and s.conflict


def test_freshness_windows():
    assert st.compute(zone(), [obs("clear", 5 * 60)], CALM, NOW).level == "clear"
    assert st.compute(zone(), [obs("clear", 7 * 60)], CALM, NOW).level == "nodata"
    assert st.compute(zone(), [obs("hole", 7 * 60)], CALM, NOW).level == "risk"
    assert st.compute(zone(), [obs("hole", 25 * 60)], CALM, NOW).level == "nodata"


def test_strong_wind_shortens_freshness_and_offshore_raises():
    windy = Weather(temp_c=-10, wind_ms=12, wind_gust_ms=17, wind_from_deg=10, days=CALM.days)
    s = st.compute(zone(), [obs("clear", 4 * 60)], windy, NOW)
    assert s.fresh_window_h == 3 and s.offshore_wind and s.level == "risk"


def test_wrong_reports_are_ignored():
    assert st.compute(zone(), [obs("hole", 10, wrong=3, confirm=1)], CALM, NOW).level == "nodata"


def test_text_can_only_raise():
    assert st.compute(zone(), [obs("clear", 10, hazard="danger")], CALM, NOW).level == "risk"
    assert st.compute(zone(), [obs("hole", 10, hazard="none")], CALM, NOW).level == "danger"


def test_ban_is_always_danger():
    assert st.compute(zone(ban=True, ban_text="Запрет"), [obs("clear", 5)], CALM, NOW).level == "danger"


def test_rules_classifier_and_forbidden_words():
    assert ai.classify_rules("Тут промоина у мыса")["hazard"] == "danger"
    assert ai.classify_rules("трещина вдоль берега")["hazard"] == "risk"
    assert ai.classify_rules("лёд 30 см, всё спокойно")["hazard"] == "none"
    assert not ai.is_clean("Лёд выдержит, можно идти")


def test_geo():
    g = {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]]}
    assert geo.point_in_polygon(0.5, 0.5, g) and not geo.point_in_polygon(2, 2, g)
    assert geo.angle_in_ranges(350, [[330, 40]]) and not geo.angle_in_ranges(180, [[330, 40]])
