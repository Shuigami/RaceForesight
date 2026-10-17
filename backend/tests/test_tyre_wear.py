from app.simulation.strategy import _monotonic_tyre_loss_seconds


def test_inverted_model_becomes_non_decreasing_positive_wear():
    # Fresh=0, then model says "faster", then slightly less fast — must not heal
    raw = [0.0, -1.5, -0.9]
    out = _monotonic_tyre_loss_seconds(raw, "MEDIUM")
    assert out[0] == 0.0
    assert out[1] >= 1.5 - 1e-9
    assert out[2] >= out[1] - 1e-9


def test_wear_floor_grows_with_age_even_if_model_flat():
    raw = [0.0, 0.0, 0.0, 0.0]
    out = _monotonic_tyre_loss_seconds(raw, "SOFT")
    assert out[0] == 0.0
    assert out[3] > out[1] > 0.0
