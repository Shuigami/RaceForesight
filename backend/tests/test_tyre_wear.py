from app.simulation.strategy import _monotonic_tyre_loss_seconds


def test_inverted_spike_does_not_plateau_whole_stint():
    # Model says older = faster early on — must NOT freeze a huge constant wear
    raw = [0.0, -1.5, -0.9, -1.2, -0.8]
    out = _monotonic_tyre_loss_seconds(raw, "MEDIUM")
    assert out[0] == 0.0
    # Grows with age via physical floor (0.04 s/lap for medium)
    assert out[1] == 0.04
    assert out[4] == 0.16
    assert out[4] > out[2] > out[1]


def test_positive_model_slowdown_is_kept_and_non_decreasing():
    raw = [0.0, 0.2, 0.5, 0.35, 0.6]
    out = _monotonic_tyre_loss_seconds(raw, "HARD")
    assert out[0] == 0.0
    assert out[2] >= 0.5
    assert out[3] >= out[2]  # cannot heal when model dips
    assert out[4] >= out[3]


def test_flat_model_still_wears_soft_faster_than_hard():
    raw = [0.0] * 11
    soft = _monotonic_tyre_loss_seconds(raw, "SOFT")
    hard = _monotonic_tyre_loss_seconds(raw, "HARD")
    assert soft[10] > hard[10] > 0.0
