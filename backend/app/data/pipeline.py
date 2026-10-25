"""Ingest and cache race datasets from OpenF1 (and optional secondary sources)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app.clients.openf1 import OpenF1Client
from app.config import settings
from app.domain.circuit_laps import resolve_race_laps
from app.domain.models import ActualDriverStrategy, MeetingSummary, StintPlan

# Meeting weekend can start Fri while race is Sun — keep "next" through race day.
_DEFAULT_MEETING_LOOKBACK = pd.Timedelta(days=4)


def _media_url(value: object) -> str | None:
    """OpenF1 sometimes leaves spaces in path segments (breaks <img>/Next)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    url = str(value).strip()
    if not url or url.lower() in ("nan", "none"):
        return None
    return url.replace(" ", "%20")


def pick_default_meeting_key(
    meetings: pd.DataFrame,
    *,
    now: datetime | None = None,
) -> int:
    """Pick Austin / United States GP when possible; never prefer Las Vegas via country alone."""
    if meetings.empty:
        return -1
    now = now or datetime.now(timezone.utc)

    circuit = meetings["circuit_short_name"].astype(str)
    name = meetings["meeting_name"].astype(str)
    austin = meetings[
        circuit.str.upper().eq("COTA")
        | circuit.str.contains("Austin", case=False, na=False)
        | name.str.contains("United States", case=False, na=False)
    ].copy()
    pool = austin if not austin.empty else meetings.copy()
    pool["date_start"] = pd.to_datetime(pool["date_start"], utc=True, errors="coerce")
    upcoming = pool[pool["date_start"] >= now - _DEFAULT_MEETING_LOOKBACK].sort_values("date_start")
    if not upcoming.empty:
        return int(upcoming.iloc[0]["meeting_key"])
    return int(pool.sort_values("date_start").iloc[-1]["meeting_key"])


def actual_strategies_from_stints(
    stints: pd.DataFrame,
    pits: pd.DataFrame | None = None,
) -> list[ActualDriverStrategy]:
    """Map OpenF1 race stints to per-driver ground-truth tyre plans."""
    if stints.empty or "driver_number" not in stints.columns:
        return []

    pits_by_driver: dict[int, list[int]] = {}
    if pits is not None and not pits.empty and "driver_number" in pits.columns and "lap_number" in pits.columns:
        for dnum, grp in pits.groupby("driver_number"):
            laps = sorted(int(x) for x in grp["lap_number"].dropna().tolist())
            pits_by_driver[int(dnum)] = laps

    out: list[ActualDriverStrategy] = []
    for dnum, grp in stints.groupby("driver_number"):
        rows = grp.copy()
        if "stint_number" in rows.columns:
            rows = rows.sort_values(["stint_number", "lap_start"], na_position="last")
        else:
            rows = rows.sort_values("lap_start", na_position="last")

        plans: list[StintPlan] = []
        for _, row in rows.iterrows():
            if pd.isna(row.get("lap_start")):
                continue
            lap_start = int(row["lap_start"])
            lap_end_raw = row.get("lap_end")
            lap_end = int(lap_end_raw) if pd.notna(lap_end_raw) else lap_start
            if lap_end < lap_start:
                continue
            tyre_raw = row.get("tyre_age_at_start")
            plans.append(
                StintPlan(
                    compound=str(row.get("compound") or "UNKNOWN").upper(),
                    lap_start=lap_start,
                    lap_end=lap_end,
                    tyre_age_at_start=int(tyre_raw) if pd.notna(tyre_raw) else 0,
                )
            )
        if not plans:
            continue

        compounds = [p.compound for p in plans]
        derived_pits = [p.lap_end for p in plans[:-1]]
        pit_laps = pits_by_driver.get(int(dnum)) or derived_pits
        # Keep pit count aligned with stint boundaries when OpenF1 pits are noisy
        if len(pit_laps) != len(plans) - 1:
            pit_laps = derived_pits
        stops = max(0, len(plans) - 1)
        label = f"{stops}-stop {'→'.join(compounds)}"
        out.append(
            ActualDriverStrategy(
                driver_number=int(dnum),
                stops=stops,
                compounds=compounds,
                pit_laps=pit_laps,
                stints=plans,
                strategy_label=label,
            )
        )
    out.sort(key=lambda a: a.driver_number)
    return out


class RaceDataPipeline:
    def __init__(self, client: OpenF1Client | None = None, cache_dir: Path | None = None) -> None:
        self.client = client or OpenF1Client()
        self.owns_client = client is None
        self.cache_dir = cache_dir or settings.cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def close(self) -> None:
        if self.owns_client:
            self.client.close()

    def list_meetings(self, years: list[int] | None = None) -> list[MeetingSummary]:
        years = years or list(range(2023, settings.default_season + 1))
        frames: list[pd.DataFrame] = []
        for year in years:
            df = self.client.meetings(year=year)
            if not df.empty:
                frames.append(df)
        if not frames:
            return []

        meetings = pd.concat(frames, ignore_index=True)
        meetings = meetings.drop_duplicates(subset=["meeting_key"]).sort_values("date_start")
        default_key = self.resolve_default_meeting_key(meetings)
        out: list[MeetingSummary] = []
        for _, row in meetings.iterrows():
            out.append(
                MeetingSummary(
                    meeting_key=int(row["meeting_key"]),
                    meeting_name=str(row.get("meeting_name") or row.get("meeting_official_name") or "Unknown"),
                    circuit_short_name=str(row.get("circuit_short_name") or ""),
                    country_name=str(row.get("country_name") or ""),
                    year=int(row["year"]),
                    date_start=str(row["date_start"]) if pd.notna(row.get("date_start")) else None,
                    is_default=int(row["meeting_key"]) == default_key,
                    race_laps=resolve_race_laps(
                        str(row.get("circuit_short_name") or ""),
                        str(row.get("meeting_name") or row.get("meeting_official_name") or ""),
                    ),
                    circuit_image=_media_url(row.get("circuit_image")),
                    country_flag=_media_url(row.get("country_flag")),
                )
            )
        return out

    def resolve_default_meeting_key(self, meetings: pd.DataFrame | None = None) -> int:
        """Prefer next/current Austin (COTA / United States GP); else latest such meeting.

        Las Vegas / Miami are also "United States" in OpenF1 — do not treat them as the
        default target. Keep a multi-day weekend window so race Sunday still counts.
        """
        if meetings is None:
            frames = []
            for year in range(2023, settings.default_season + 1):
                df = self.client.meetings(year=year)
                if not df.empty:
                    frames.append(df)
            meetings = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

        if meetings.empty:
            return -1

        return pick_default_meeting_key(meetings, now=datetime.now(timezone.utc))

    def get_meeting(self, meeting_key: int | None = None) -> MeetingSummary:
        meetings = self.list_meetings()
        if meeting_key is None or meeting_key <= 0:
            meeting_key = self.resolve_default_meeting_key()
        for m in meetings:
            if m.meeting_key == meeting_key:
                return m
        raise ValueError(f"Meeting {meeting_key} not found")

    def _race_session_row(self, meeting_key: int):
        sessions = self.client.sessions(meeting_key=meeting_key)
        if sessions.empty:
            return None
        race = sessions[sessions["session_name"].astype(str).str.lower().eq("race")]
        if race.empty:
            race = sessions[sessions["session_type"].astype(str).str.lower().eq("race")]
        if race.empty:
            return None
        return race.iloc[0]

    def race_session_key(self, meeting_key: int) -> int | None:
        row = self._race_session_row(meeting_key)
        if row is None:
            return None
        return int(row["session_key"])

    def race_start_at(self, meeting_key: int) -> str | None:
        """Race session date_start (ISO), else meeting date_start."""
        row = self._race_session_row(meeting_key)
        if row is not None and row.get("date_start") is not None:
            return str(row["date_start"])
        try:
            meeting = self.get_meeting(meeting_key)
        except ValueError:
            return None
        return meeting.date_start

    def list_race_sessions(self, years: list[int] | None = None) -> pd.DataFrame:
        years = years or list(range(2023, settings.default_season + 1))
        frames: list[pd.DataFrame] = []
        for year in years:
            sessions = self.client.sessions(year=year, session_name="Race")
            if sessions.empty:
                sessions = self.client.sessions(year=year)
                if not sessions.empty:
                    sessions = sessions[
                        sessions["session_name"].astype(str).str.lower().eq("race")
                        | sessions["session_type"].astype(str).str.lower().eq("race")
                    ]
            if not sessions.empty:
                frames.append(sessions)
        if not frames:
            return pd.DataFrame()
        out = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["session_key"])
        return out

    def ingest_session(self, session_key: int, force: bool = False) -> dict[str, pd.DataFrame]:
        parquet_dir = self.cache_dir / "sessions" / str(session_key)
        parquet_dir.mkdir(parents=True, exist_ok=True)
        names = ["laps", "stints", "pits", "drivers", "weather"]
        result: dict[str, pd.DataFrame] = {}

        if not force and all((parquet_dir / f"{n}.parquet").exists() for n in names):
            for n in names:
                result[n] = pd.read_parquet(parquet_dir / f"{n}.parquet")
            return result

        fetchers = {
            "laps": lambda: self.client.laps(session_key),
            "stints": lambda: self.client.stints(session_key),
            "pits": lambda: self.client.pits(session_key),
            "drivers": lambda: self.client.drivers(session_key=session_key),
            "weather": lambda: self.client.weather(session_key),
        }
        for name, fetch in fetchers.items():
            try:
                result[name] = fetch()
            except Exception as exc:
                print(f"Warning: failed to fetch {name} for session {session_key}: {exc}")
                result[name] = pd.DataFrame()

        for n, df in result.items():
            df.to_parquet(parquet_dir / f"{n}.parquet", index=False)
        return result

    def build_training_frame(
        self,
        years: list[int] | None = None,
        max_sessions: int | None = None,
        *,
        completed_only: bool = True,
    ) -> pd.DataFrame:
        sessions = self.list_race_sessions(years)
        if sessions.empty:
            return pd.DataFrame()
        sessions = sessions.sort_values("date_start")
        if completed_only and "date_start" in sessions.columns:
            now = datetime.now(timezone.utc)
            starts = pd.to_datetime(sessions["date_start"], utc=True, errors="coerce")
            # Keep races that have already started (plus a small buffer for ongoing sessions)
            sessions = sessions.loc[starts <= now + pd.Timedelta(hours=3)].copy()
        if max_sessions:
            sessions = sessions.tail(max_sessions)

        frames: list[pd.DataFrame] = []
        for _, sess in sessions.iterrows():
            session_key = int(sess["session_key"])
            meeting_key = int(sess["meeting_key"])
            data = self.ingest_session(session_key)
            if data["laps"].empty:
                continue
            lap_df = self._join_lap_features(
                data,
                session_key=session_key,
                meeting_key=meeting_key,
                circuit_short_name=str(sess.get("circuit_short_name") or ""),
                year=int(sess.get("year") or 0),
            )
            if not lap_df.empty:
                frames.append(lap_df)
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def _join_lap_features(
        self,
        data: dict[str, pd.DataFrame],
        *,
        session_key: int,
        meeting_key: int,
        circuit_short_name: str,
        year: int,
    ) -> pd.DataFrame:
        laps = data["laps"].copy()
        stints = data["stints"].copy()
        drivers = data["drivers"].copy()
        weather = data["weather"].copy()
        if laps.empty:
            return pd.DataFrame()

        laps = laps[laps["lap_duration"].notna()].copy()
        laps = laps[laps["lap_duration"] > 0]
        if "is_pit_out_lap" in laps.columns:
            laps["is_outlap"] = laps["is_pit_out_lap"].fillna(False).astype(bool).astype(int)
        else:
            laps["is_outlap"] = 0

        # Attach compound / tyre age from stints
        compound_rows: list[dict] = []
        if not stints.empty:
            for _, stint in stints.iterrows():
                if pd.isna(stint.get("driver_number")):
                    continue
                lap_start_raw = stint.get("lap_start")
                lap_end_raw = stint.get("lap_end")
                if pd.isna(lap_start_raw):
                    continue
                lap_start = int(lap_start_raw)
                lap_end = int(lap_end_raw) if pd.notna(lap_end_raw) else lap_start
                if lap_end < lap_start:
                    continue
                tyre_age_raw = stint.get("tyre_age_at_start")
                tyre_age0 = int(tyre_age_raw) if pd.notna(tyre_age_raw) else 0
                stint_raw = stint.get("stint_number")
                stint_number = int(stint_raw) if pd.notna(stint_raw) else 1
                stint_len = lap_end - lap_start + 1
                for lap_no in range(lap_start, lap_end + 1):
                    compound_rows.append(
                        {
                            "driver_number": int(stint["driver_number"]),
                            "lap_number": lap_no,
                            "compound": str(stint.get("compound") or "UNKNOWN"),
                            "tyre_age": tyre_age0 + (lap_no - lap_start),
                            "stint_number": stint_number,
                            "stint_length": stint_len,
                            "stint_lap": lap_no - lap_start + 1,
                        }
                    )
        compound_df = pd.DataFrame(compound_rows)
        if not compound_df.empty:
            laps = laps.merge(compound_df, on=["driver_number", "lap_number"], how="left")
        else:
            laps["compound"] = "UNKNOWN"
            laps["tyre_age"] = 0
            laps["stint_number"] = 1
            laps["stint_length"] = 1
            laps["stint_lap"] = 1

        if not drivers.empty:
            driver_cols = [
                c
                for c in [
                    "driver_number",
                    "name_acronym",
                    "full_name",
                    "team_name",
                    "team_colour",
                    "headshot_url",
                ]
                if c in drivers.columns
            ]
            drivers_u = drivers[driver_cols].drop_duplicates(subset=["driver_number"])
            laps = laps.merge(drivers_u, on="driver_number", how="left")

        # Aggregate weather to session means
        track_temp = float(weather["track_temperature"].mean()) if not weather.empty and "track_temperature" in weather else 35.0
        rainfall = float(weather["rainfall"].mean()) if not weather.empty and "rainfall" in weather else 0.0
        laps["track_temp"] = track_temp
        laps["rainfall"] = rainfall
        laps["session_key"] = session_key
        laps["meeting_key"] = meeting_key
        laps["circuit_short_name"] = circuit_short_name
        laps["year"] = year
        laps["compound"] = laps["compound"].fillna("UNKNOWN").astype(str).str.upper()
        laps["tyre_age"] = laps["tyre_age"].fillna(0).astype(int)
        laps["stint_length"] = laps.get("stint_length", pd.Series(1, index=laps.index)).fillna(1).astype(int)
        laps["stint_lap"] = laps.get("stint_lap", pd.Series(1, index=laps.index)).fillna(1).astype(int)
        if "is_outlap" not in laps.columns:
            laps["is_outlap"] = 0

        max_lap = int(laps["lap_number"].max()) if not laps.empty else 1
        laps["fuel_proxy"] = (max_lap - laps["lap_number"].astype(int) + 1).clip(lower=1)
        laps["laps_remaining"] = laps["fuel_proxy"]

        # Relative pace vs field on same lap (traffic / pack density proxy)
        lap_field = laps.groupby("lap_number")["lap_duration"].transform("median")
        laps["field_delta"] = laps["lap_duration"] - lap_field

        # Session neutralization intensity: share of unusually slow green-flag candidates
        session_med = float(laps["lap_duration"].median()) if not laps.empty else 1.0
        slow_share = float((laps["lap_duration"] > session_med * 1.08).mean()) if session_med > 0 else 0.0
        laps["neutralization_intensity"] = slow_share

        keep = [
            "session_key",
            "meeting_key",
            "year",
            "circuit_short_name",
            "driver_number",
            "name_acronym",
            "full_name",
            "team_name",
            "team_colour",
            "headshot_url",
            "lap_number",
            "lap_duration",
            "compound",
            "tyre_age",
            "stint_number",
            "stint_length",
            "stint_lap",
            "is_outlap",
            "field_delta",
            "neutralization_intensity",
            "track_temp",
            "rainfall",
            "fuel_proxy",
            "laps_remaining",
        ]
        keep = [c for c in keep if c in laps.columns]
        return laps[keep].dropna(subset=["lap_duration"])

    def estimate_pit_loss(self, meeting_key: int | None = None, circuit_short_name: str = "COTA") -> float:
        """Average pit lane time + fixed in/out loss."""
        sessions = self.list_race_sessions()
        if sessions.empty:
            return 22.0 + settings.pit_loss_extra_seconds
        if circuit_short_name:
            mask = sessions["circuit_short_name"].astype(str).str.upper().eq(circuit_short_name.upper())
            subset = sessions[mask] if mask.any() else sessions
        else:
            subset = sessions
        durations: list[float] = []
        for _, sess in subset.tail(8).iterrows():
            pits = self.ingest_session(int(sess["session_key"]))["pits"]
            if pits.empty or "pit_duration" not in pits.columns:
                continue
            vals = pits["pit_duration"].dropna()
            vals = vals[(vals > 15) & (vals < 45)]
            durations.extend(vals.tolist())
        avg_pit = float(sum(durations) / len(durations)) if durations else 22.0
        return avg_pit + settings.pit_loss_extra_seconds

    def actual_strategies_for_meeting(self, meeting_key: int) -> list[ActualDriverStrategy]:
        """Ground-truth tyre plans for a completed race; empty if not raced / no stints."""
        session_key = self.race_session_key(meeting_key)
        if not session_key:
            return []
        data = self.ingest_session(session_key)
        if data["stints"].empty or data["laps"].empty:
            return []
        return actual_strategies_from_stints(data["stints"], data.get("pits"))

    def drivers_for_meeting(self, meeting_key: int) -> pd.DataFrame:
        session_key = self.race_session_key(meeting_key)
        if session_key:
            drivers = self.ingest_session(session_key)["drivers"]
            if not drivers.empty:
                return drivers.drop_duplicates(subset=["driver_number"])

        # Upcoming race: use latest race session drivers of same season
        meeting = self.get_meeting(meeting_key)
        sessions = self.client.sessions(year=meeting.year, session_name="Race")
        if sessions.empty:
            sessions = self.list_race_sessions([meeting.year, meeting.year - 1])
        if sessions.empty:
            return pd.DataFrame()
        latest = sessions.sort_values("date_start").iloc[-1]
        return self.ingest_session(int(latest["session_key"]))["drivers"].drop_duplicates(subset=["driver_number"])

    def qualifying_session_key(self, meeting_key: int) -> int | None:
        sessions = self.client.sessions(meeting_key=meeting_key)
        if sessions.empty:
            return None
        quali = sessions[sessions["session_name"].astype(str).str.lower().eq("qualifying")]
        if quali.empty:
            quali = sessions[sessions["session_type"].astype(str).str.lower().eq("qualifying")]
        if quali.empty:
            return None
        return int(quali.iloc[0]["session_key"])

    def qualifying_grid(self, meeting_key: int) -> dict[int, int]:
        """Grid positions from qualifying session_result (1 = pole)."""
        qkey = self.qualifying_session_key(meeting_key)
        if not qkey:
            return {}
        try:
            result = self.client.session_result(qkey)
        except Exception:
            return {}
        if result.empty or "position" not in result.columns or "driver_number" not in result.columns:
            return {}
        out: dict[int, int] = {}
        for _, row in result.dropna(subset=["position", "driver_number"]).iterrows():
            try:
                pos = int(float(row["position"]))
            except (TypeError, ValueError):
                continue
            out[int(row["driver_number"])] = pos
        return out

    def race_results_history(
        self,
        years: list[int] | None = None,
        *,
        exclude_session_key: int | None = None,
        max_sessions: int | None = 80,
    ) -> pd.DataFrame:
        """Completed race finishing positions for form features."""
        sessions = self.list_race_sessions(years)
        if sessions.empty:
            return pd.DataFrame()
        sessions = sessions.sort_values("date_start")
        now = datetime.now(timezone.utc)
        if "date_start" in sessions.columns:
            starts = pd.to_datetime(sessions["date_start"], utc=True, errors="coerce")
            sessions = sessions.loc[starts <= now + pd.Timedelta(hours=3)].copy()
        if exclude_session_key is not None:
            sessions = sessions[sessions["session_key"].astype(int) != int(exclude_session_key)]
        if max_sessions:
            sessions = sessions.tail(max_sessions)

        rows: list[dict] = []
        for _, sess in sessions.iterrows():
            session_key = int(sess["session_key"])
            try:
                result = self.client.session_result(session_key)
            except Exception:
                continue
            if result.empty or "position" not in result.columns:
                continue
            weather = self.ingest_session(session_key).get("weather", pd.DataFrame())
            rainfall = (
                float(weather["rainfall"].mean())
                if not weather.empty and "rainfall" in weather.columns
                else 0.0
            )
            for _, row in result.dropna(subset=["position", "driver_number"]).iterrows():
                try:
                    pos = int(float(row["position"]))
                    dnum = int(row["driver_number"])
                except (TypeError, ValueError):
                    continue
                rows.append(
                    {
                        "session_key": session_key,
                        "meeting_key": int(sess["meeting_key"]),
                        "year": int(sess.get("year") or 0),
                        "date_start": sess.get("date_start"),
                        "circuit_short_name": str(sess.get("circuit_short_name") or ""),
                        "driver_number": dnum,
                        "position": pos,
                        "rainfall": rainfall,
                    }
                )
        return pd.DataFrame(rows)
