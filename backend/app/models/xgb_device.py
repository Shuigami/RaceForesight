"""Pick XGBoost train device (GPU if CUDA works, else CPU)."""

from __future__ import annotations

from functools import lru_cache


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
