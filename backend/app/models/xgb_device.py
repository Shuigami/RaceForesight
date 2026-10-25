"""Pick XGBoost train device (GPU if CUDA works, else CPU)."""

from __future__ import annotations

from functools import lru_cache
from typing import Any


@lru_cache(maxsize=1)
def xgb_device() -> str:
    try:
        import numpy as np
        import xgboost as xgb
        from xgboost import XGBRegressor

        if not xgb.build_info().get("USE_CUDA"):
            return "cpu"
        # Probe: CUDA wheel can be installed without a usable GPU
        m = XGBRegressor(n_estimators=1, max_depth=1, device="cuda")
        x = np.zeros((8, 2), dtype=np.float32)
        m.fit(x, np.zeros(8, dtype=np.float32))
        return "cuda"
    except Exception:
        return "cpu"


def force_xgb_cpu(model: Any) -> Any:
    """Serve on CPU — CUDA boosters + numpy features crash the uvicorn worker on Windows."""
    if model is None:
        return model
    try:
        model.set_params(device="cpu")
    except Exception:
        pass
    try:
        booster = model.get_booster()
        booster.set_param({"device": "cpu"})
    except Exception:
        pass
    return model
