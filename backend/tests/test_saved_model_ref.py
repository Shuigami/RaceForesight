from app.domain.models import PredictionModelVersions, PredictionSnapshot


def test_coerce_legacy_version_strings():
    mv = PredictionModelVersions.model_validate(
        {
            "classification": "ranking-pairwise-v1",
            "race_time": "race-time-xgb-v1",
            "strategy": "xgboost-lap-v2",
        }
    )
    assert mv.classification.name == "Classification (pairwise ranker)"
    assert mv.classification.version == "ranking-pairwise-v1"
    assert mv.race_time.version == "race-time-xgb-v1"
    assert mv.strategy.name == "Lap-time XGBoost"


def test_snapshot_accepts_legacy_model_versions():
    snap = PredictionSnapshot.model_validate(
        {
            "id": "abc",
            "name": "test",
            "meeting": {
                "meeting_key": 1,
                "meeting_name": "Test",
                "circuit_short_name": "T",
                "country_name": "T",
                "year": 2026,
                "race_laps": 50,
            },
            "first_saved_at": "2026-01-01T00:00:00Z",
            "saved_at": "2026-01-01T00:00:00Z",
            "model_versions": {
                "classification": "ranking-pairwise-v2",
                "race_time": "race-time-xgb-v2",
                "strategy": "xgboost-lap-v3",
            },
            "classification": {"standings": [], "note": ""},
            "race_time": {"standings": [], "note": ""},
            "strategy": {"strategies": []},
        }
    )
    assert snap.model_versions.strategy.version == "xgboost-lap-v3"
    assert "Lap-time" in snap.model_versions.strategy.name
