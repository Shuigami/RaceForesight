"""OpenF1 API client with polite rate limiting and simple disk cache."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings


class OpenF1Client:
    """Primary data source for RaceForesight."""

    def __init__(
        self,
        base_url: str | None = None,
        cache_dir: Path | None = None,
        max_rps: float | None = None,
    ) -> None:
        self.base_url = (base_url or settings.openf1_base_url).rstrip("/")
        self.cache_dir = cache_dir or settings.cache_dir / "openf1"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._min_interval = 1.0 / (max_rps or settings.openf1_max_rps)
        self._last_request = 0.0
        self._client = httpx.Client(timeout=60.0)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> OpenF1Client:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _cache_path(self, endpoint: str, params: dict[str, Any]) -> Path:
        key = hashlib.sha1(
            f"{endpoint}:{json.dumps(params, sort_keys=True, default=str)}".encode()
        ).hexdigest()
        safe_endpoint = endpoint.strip("/").replace("/", "_") or "root"
        return self.cache_dir / f"{safe_endpoint}_{key}.json"

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request = time.monotonic()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
    def get(self, endpoint: str, params: dict[str, Any] | None = None, *, use_cache: bool = True) -> list[dict]:
        params = {k: v for k, v in (params or {}).items() if v is not None}
        cache_path = self._cache_path(endpoint, params)
        if use_cache and cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8"))

        self._throttle()
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        response = self._client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            data = [data]
        if use_cache:
            cache_path.write_text(json.dumps(data), encoding="utf-8")
        return data

    def get_df(self, endpoint: str, params: dict[str, Any] | None = None, *, use_cache: bool = True) -> pd.DataFrame:
        rows = self.get(endpoint, params, use_cache=use_cache)
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    def meetings(self, year: int | None = None, country_name: str | None = None) -> pd.DataFrame:
        return self.get_df("meetings", {"year": year, "country_name": country_name})

    def sessions(
        self,
        year: int | None = None,
        meeting_key: int | None = None,
        session_name: str | None = None,
        session_type: str | None = None,
    ) -> pd.DataFrame:
        return self.get_df(
            "sessions",
            {
                "year": year,
                "meeting_key": meeting_key,
                "session_name": session_name,
                "session_type": session_type,
            },
        )

    def drivers(self, session_key: int | None = None, meeting_key: int | None = None) -> pd.DataFrame:
        return self.get_df("drivers", {"session_key": session_key, "meeting_key": meeting_key})

    def laps(self, session_key: int, driver_number: int | None = None) -> pd.DataFrame:
        return self.get_df("laps", {"session_key": session_key, "driver_number": driver_number})

    def stints(self, session_key: int, driver_number: int | None = None) -> pd.DataFrame:
        return self.get_df("stints", {"session_key": session_key, "driver_number": driver_number})

    def pits(self, session_key: int, driver_number: int | None = None) -> pd.DataFrame:
        return self.get_df("pit", {"session_key": session_key, "driver_number": driver_number})

    def weather(self, session_key: int) -> pd.DataFrame:
        return self.get_df("weather", {"session_key": session_key})
