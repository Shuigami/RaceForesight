from xgboost import XGBRegressor
import numpy as np

from app.models.xgb_device import force_xgb_cpu, xgb_device


def test_xgb_device_returns_cpu_or_cuda() -> None:
    assert xgb_device() in {"cpu", "cuda"}


def test_force_xgb_cpu_sets_device() -> None:
    m = XGBRegressor(n_estimators=1, max_depth=1, device="cpu")
    x = np.zeros((8, 2), dtype=np.float32)
    m.fit(x, np.zeros(8, dtype=np.float32))
    force_xgb_cpu(m)
    assert m.get_params().get("device") == "cpu"
    assert force_xgb_cpu(None) is None
