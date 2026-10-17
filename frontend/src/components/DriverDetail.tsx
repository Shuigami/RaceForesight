"use client";

import { useEffect, useMemo, useState } from "react";
import type { PacePoint, StrategyDetail } from "@/lib/api";
import { formatRaceTime } from "@/lib/api";
import { CompoundPills } from "./CompoundPills";

type ChartMode = "race_pace" | "tyre_only";

function formatDelta(seconds: number): string {
  const sign = seconds >= 0 ? "+" : "";
  return `${sign}${seconds.toFixed(3)}s`;
}

export function DriverDetail({ detail }: { detail: StrategyDetail }) {
  const { best, alternatives, stint_curves, degradation_curve } = detail;
  const curves =
    stint_curves?.length > 0
      ? stint_curves
      : [
          {
            stint_index: 0,
            compound: degradation_curve[0]?.compound ?? best.stints[0]?.compound ?? "UNKNOWN",
            lap_start: best.stints[0]?.lap_start ?? 1,
            lap_end: best.stints[0]?.lap_end ?? 25,
            points: degradation_curve as PacePoint[],
          },
        ];

  const [selectedStint, setSelectedStint] = useState(0);
  const [chartMode, setChartMode] = useState<ChartMode>("race_pace");
  const [selectedLapIdx, setSelectedLapIdx] = useState(0);
  const [selectedAlt, setSelectedAlt] = useState<number | null>(null);

  useEffect(() => {
    setSelectedStint(0);
    setSelectedLapIdx(0);
    setSelectedAlt(null);
  }, [best.driver_number, best.strategy_label]);

  const activeCurve = curves[Math.min(selectedStint, curves.length - 1)] ?? curves[0];
  const points = activeCurve?.points ?? [];

  const values = useMemo(
    () => points.map((p) => (chartMode === "race_pace" ? p.predicted_lap_s : p.tyre_effect_s)),
    [points, chartMode],
  );
  const maxVal = Math.max(...values, chartMode === "tyre_only" ? 0.01 : 1);
  const minVal = Math.min(...values, chartMode === "tyre_only" ? 0 : maxVal);
  const range = Math.max(maxVal - minVal, 0.01);

  const selectedPoint = points[Math.min(selectedLapIdx, Math.max(points.length - 1, 0))] ?? null;
  const comparedAlt = selectedAlt != null ? alternatives[selectedAlt] : null;
  const timeDelta =
    comparedAlt != null ? comparedAlt.predicted_race_time_s - best.predicted_race_time_s : null;

  return (
    <section className="space-y-6 rounded-sm border border-white/10 bg-panel/90 p-6 backdrop-blur">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[11px] uppercase tracking-[0.2em] text-muted">Driver strategy</p>
          <h2 className="font-display text-4xl tracking-wide text-white">{best.full_name}</h2>
          <p className="mt-1 text-sm text-fog">
            {best.team_name} · {best.strategy_label}
          </p>
        </div>
        <div className="text-right">
          <p className="text-[11px] uppercase tracking-[0.16em] text-muted">Strategy race time</p>
          <p className="font-mono text-3xl text-accent">{formatRaceTime(best.predicted_race_time_s)}</p>
        </div>
      </header>

      <div>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-[11px] uppercase tracking-[0.16em] text-muted">Stints — click to inspect</h3>
          <p className="text-xs text-fog">Selected stint drives the chart below</p>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          {best.stints.map((stint, i) => {
            const active = selectedStint === i;
            return (
              <button
                key={`${stint.compound}-${i}`}
                type="button"
                onClick={() => {
                  setSelectedStint(i);
                  setSelectedLapIdx(0);
                }}
                className={`border p-4 text-left transition ${
                  active
                    ? "border-accent bg-accent/15"
                    : "border-white/10 bg-ink-850/60 hover:border-white/25"
                }`}
              >
                <p className="text-[11px] uppercase tracking-[0.14em] text-muted">Stint {i + 1}</p>
                <div className="mt-2">
                  <CompoundPills compounds={[stint.compound]} />
                </div>
                <p className="mt-3 font-mono text-sm text-fog">
                  Laps {stint.lap_start}–{stint.lap_end}
                </p>
                {active && (
                  <p className="mt-2 text-[11px] uppercase tracking-[0.12em] text-accent">Viewing</p>
                )}
              </button>
            );
          })}
        </div>
      </div>

      <div className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h3 className="text-[11px] uppercase tracking-[0.16em] text-muted">Lap model explorer</h3>
            <p className="mt-1 font-display text-2xl tracking-wide text-white">
              Stint {selectedStint + 1} · {activeCurve?.compound ?? "—"}
            </p>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setChartMode("race_pace")}
              className={`px-3 py-1.5 text-[11px] uppercase tracking-[0.14em] transition ${
                chartMode === "race_pace"
                  ? "border border-accent bg-accent/20 text-white"
                  : "border border-white/15 text-muted hover:text-white"
              }`}
            >
              Race pace
            </button>
            <button
              type="button"
              onClick={() => setChartMode("tyre_only")}
              className={`px-3 py-1.5 text-[11px] uppercase tracking-[0.14em] transition ${
                chartMode === "tyre_only"
                  ? "border border-accent bg-accent/20 text-white"
                  : "border border-white/15 text-muted hover:text-white"
              }`}
            >
              Tyre wear only
            </button>
          </div>
        </div>

        <p className="text-sm text-fog">
          {chartMode === "race_pace" ? (
            <>
              <strong className="text-white">Race pace</strong> = predicted lap time with fuel burn + tyre
              age + lap number together. Early laps often look slow because the car is heavy — that is not
              tyre degradation.
            </>
          ) : (
            <>
              <strong className="text-white">Tyre wear only</strong> keeps fuel/lap fixed and varies tyre age.
              Bars rising to the right mean the compound is losing performance.
            </>
          )}{" "}
          Click a bar for details.
        </p>

        <div className="flex h-36 items-end gap-1 border border-white/10 bg-ink-900/50 p-3">
          {points.map((point, idx) => {
            const value = chartMode === "race_pace" ? point.predicted_lap_s : point.tyre_effect_s;
            const height =
              chartMode === "tyre_only"
                ? Math.max(8, ((value - minVal) / range) * 100)
                : Math.max(8, ((value - minVal) / range) * 100);
            const active = selectedLapIdx === idx;
            return (
              <button
                key={`${point.lap_number}-${idx}`}
                type="button"
                onClick={() => setSelectedLapIdx(idx)}
                className={`flex-1 rounded-t-sm transition ${
                  active ? "bg-white" : "bg-accent/80 hover:bg-accent"
                }`}
                style={{ height: `${height}%` }}
                title={`Lap ${point.lap_number}: ${
                  chartMode === "race_pace" ? `${value.toFixed(3)}s` : formatDelta(value)
                }`}
                aria-label={`Lap ${point.lap_number}`}
              />
            );
          })}
        </div>

        {selectedPoint && (
          <div className="grid gap-3 border border-white/10 bg-ink-850/70 p-4 sm:grid-cols-4">
            <div>
              <p className="text-[11px] uppercase tracking-[0.14em] text-muted">Lap</p>
              <p className="font-mono text-xl text-white">{selectedPoint.lap_number}</p>
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-[0.14em] text-muted">Tyre age</p>
              <p className="font-mono text-xl text-white">{selectedPoint.tyre_age} laps</p>
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-[0.14em] text-muted">Fuel proxy</p>
              <p className="font-mono text-xl text-white">{selectedPoint.fuel_proxy}</p>
              <p className="text-[11px] text-muted">laps of fuel left (proxy)</p>
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-[0.14em] text-muted">
                {chartMode === "race_pace" ? "Predicted lap" : "Tyre effect"}
              </p>
              <p className="font-mono text-xl text-accent">
                {chartMode === "race_pace"
                  ? `${selectedPoint.predicted_lap_s.toFixed(3)}s`
                  : formatDelta(selectedPoint.tyre_effect_s)}
              </p>
              {chartMode === "race_pace" && (
                <p className="text-[11px] text-muted">
                  tyre-only {formatDelta(selectedPoint.tyre_effect_s)}
                </p>
              )}
            </div>
          </div>
        )}
      </div>

      <div>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-[11px] uppercase tracking-[0.16em] text-muted">
            Alternatives — click to compare
          </h3>
          {timeDelta != null && (
            <p className="font-mono text-xs text-fog">
              vs best: <span className="text-accent">{formatDelta(timeDelta)}</span>
            </p>
          )}
        </div>
        <ul className="space-y-2">
          {alternatives.map((alt, idx) => {
            const active = selectedAlt === idx;
            const delta = alt.predicted_race_time_s - best.predicted_race_time_s;
            return (
              <li key={alt.strategy_label}>
                <button
                  type="button"
                  onClick={() => setSelectedAlt(active ? null : idx)}
                  className={`flex w-full flex-wrap items-center justify-between gap-3 border px-4 py-3 text-left transition ${
                    active
                      ? "border-accent bg-accent/15"
                      : "border-white/5 bg-ink-900/40 hover:border-white/20"
                  }`}
                >
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="font-mono text-xs text-fog">{alt.stops}-stop</span>
                    <CompoundPills compounds={alt.compounds} />
                    <span className="font-mono text-xs text-muted">@{alt.pit_laps.join(", ")}</span>
                  </div>
                  <div className="text-right">
                    <span className="font-mono text-sm text-white">
                      {formatRaceTime(alt.predicted_race_time_s)}
                    </span>
                    <span className="ml-3 font-mono text-xs text-muted">{formatDelta(delta)}</span>
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
