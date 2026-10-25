from app.domain.models import ModelScore
from app.evaluation.metrics import ModelEvaluator


def test_merge_scores_keeps_old_versions_and_updates_primary():
    existing = [
        ModelScore(
            name="Lap-time XGBoost",
            kind="lap_time",
            version="xgboost-lap-v2",
            primary=True,
            metrics={"mae_s": 1.6},
        ),
        ModelScore(
            name="Lap-time Random Forest",
            kind="lap_time",
            version="rf-lap-v2",
            primary=False,
            metrics={"mae_s": 1.7},
        ),
    ]
    fresh = [
        ModelScore(
            name="Lap-time XGBoost",
            kind="lap_time",
            version="xgboost-lap-v3",
            primary=True,
            metrics={"mae_s": 1.3},
        ),
    ]
    merged = ModelEvaluator.merge_scores(existing, fresh)
    versions = {(m.name, m.version, m.primary) for m in merged}
    assert ("Lap-time XGBoost", "xgboost-lap-v2", False) in versions
    assert ("Lap-time XGBoost", "xgboost-lap-v3", True) in versions
    assert ("Lap-time Random Forest", "rf-lap-v2", False) in versions
