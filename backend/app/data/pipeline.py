"""Ingest and cache race datasets from OpenF1 (and optional secondary sources)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app.clients.openf1 import OpenF1Client
from app.config import settings
from app.domain.models import MeetingSummary


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
                    race_laps=settings.race_laps_cota,
                )
            )
        for m in out:
            circuit = m.circuit_short_name.upper()
            if circuit == "COTA" or (
                "United States" in m.country_name and "United States" in m.meeting_name
            ):
                m.race_laps = settings.race_laps_cota
            else:
                # Generic fallback; accurate lap counts can be enriched later
                m.race_laps = 56
        return out

    def resolve_default_meeting_key(self, meetings: pd.DataFrame | None = None) -> int:
        """Prefer next upcoming United States / COTA meeting; else latest US GP."""
        if meetings is None:
            frames = []
            for year in range(2023, settings.default_season + 1):
                df = self.client.meetings(year=year)
                if not df.empty:
                    frames.append(df)
            meetings = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

        if meetings.empty:
            return -1

        us = meetings[
            meetings["country_name"].astype(str).str.contains("United States", case=False, na=False)
            | meetings["circuit_short_name"].astype(str).str.upper().eq("COTA")
            | meetings["meeting_name"].astype(str).str.contains("United States", case=False, na=False)
        ].copy()
        pool = us if not us.empty else meetings
        pool = pool.copy()
        pool["date_start"] = pd.to_datetime(pool["date_start"], utc=True, errors="coerce")
        now = datetime.now(timezone.utc)
        upcoming = pool[pool["date_start"] >= now - pd.Timedelta(days=1)].sort_values("date_start")
        if not upcoming.empty:
            return int(upcoming.iloc[0]["meeting_key"])
        return int(pool.sort_values("date_start").iloc[-1]["meeting_key"])

    def get_meeting(self, meeting_key: int | None = None) -> MeetingSummary:
        meetings = self.list_meetings()
        if meeting_key is None or meeting_key <= 0:
            meeting_key = self.resolve_default_meeting_key()
        for m in meetings:
            if m.meeting_key == meeting_key:
                return m
        raise ValueError(f"Meeting {meeting_key} not found")

    def race_session_key(self, meeting_key: int) -> int | None:
        sessions = self.client.sessions(meeting_key=meeting_key)
        if sessions.empty:
            return None
        race = sessions[sessions["session_name"].astype(str).str.lower().eq("race")]
        if race.empty:
            race = sessions[sessions["session_type"].astype(str).str.lower().eq("race")]
        if race.empty:
            return None
        return int(race.iloc[0]["session_key"])

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

    def build_training_frame(self, years: list[int] | None = None, max_sessions: int | None = None) -> pd.DataFrame:
        sessions = self.list_race_sessions(years)
        if sessions.empty:
            return pd.DataFrame()
        sessions = sessions.sort_values("date_start")
        if max_sessions:
            sessions = sessions.tail(max_sessions)

        frames: list[pd.DataFrame] = []
        for _, sess in sessions.iterrows():
            session_key = int(sess["session_key"])
            meeting_key = int(sess["meeting_key"])
            data = self.ingest_session(session_key)
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
            laps = laps[~laps["is_pit_out_lap"].fillna(False).astype(bool)]

        # Attach compound / tyre age from stints
        compound_rows: list[dict] = []
        if not stints.empty:
            for _, stint in stints.iterrows():
                lap_start = int(stint.get("lap_start") or 1)
                lap_end = int(stint.get("lap_end") or lap_start)
                tyre_age0 = int(stint.get("tyre_age_at_start") or 0)
                for lap_no in range(lap_start, lap_end + 1):
                    compound_rows.append(
                        {
                            "driver_number": int(stint["driver_number"]),
                            "lap_number": lap_no,
                            "compound": str(stint.get("compound") or "UNKNOWN"),
                            "tyre_age": tyre_age0 + (lap_no - lap_start),
                            "stint_number": int(stint.get("stint_number") or 1),
                        }
                    )
        compound_df = pd.DataFrame(compound_rows)
        if not compound_df.empty:
            laps = laps.merge(compound_df, on=["driver_number", "lap_number"], how="left")
        else:
            laps["compound"] = "UNKNOWN"
            laps["tyre_age"] = 0
            laps["stint_number"] = 1

        if not drivers.empty:
            driver_cols = [c for c in ["driver_number", "name_acronym", "full_name", "team_name", "team_colour"] if c in drivers.columns]
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

        max_lap = int(laps["lap_number"].max()) if not laps.empty else 1
        laps["fuel_proxy"] = (max_lap - laps["lap_number"].astype(int) + 1).clip(lower=1)
        laps["laps_remaining"] = laps["fuel_proxy"]

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
            "lap_number",
            "lap_duration",
            "compound",
            "tyre_age",
            "stint_number",
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
