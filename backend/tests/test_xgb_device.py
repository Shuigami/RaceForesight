from app.models.xgb_device import xgb_device


def test_xgb_device_returns_cpu_or_cuda() -> None:
    assert xgb_device() in {"cpu", "cuda"}
