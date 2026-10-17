from app.domain.circuit_laps import resolve_race_laps


def test_singapore_is_62():
    assert resolve_race_laps("Singapore") == 62
    assert resolve_race_laps("Marina Bay", "Singapore Grand Prix") == 62


def test_cota_is_56():
    assert resolve_race_laps("COTA", "United States Grand Prix") == 56


def test_monaco_is_78():
    assert resolve_race_laps("Monaco") == 78
