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

function formatPct(pct: number): string {
  const sign = pct >= 0 ? "+" : "";
  return `${sign}${pct.toFixed(2)}%`;
}

/** Tyre-wear chart: degradation % (0% fresh → higher = more wear). Backend is already monotonic. */
function tyreWearChartValues(points: PacePoint[]): number[] {
  return points.map((p) => Math.max(0, p.tyre_degradation_pct ?? 0));
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
  const [chartMode, setChartMode] = useState<ChartMode>("tyre_only");
  const [selectedLapIdx, setSelectedLapIdx] = useState(0);
  const [selectedAlt, setSelectedAlt] = useState<number | null>(null);

  useEffect(() => {
    setSelectedStint(0);
    setSelectedLapIdx(0);
    setSelectedAlt(null);
  }, [best.driver_number, best.strategy_label]);

  const activeCurve = curves[Math.min(selectedStint, curves.length - 1)] ?? curves[0];
  const points = useMemo(() => activeCurve?.points ?? [], [activeCurve]);

  const tyreWearValues = useMemo(() => tyreWearChartValues(points), [points]);

  const values = useMemo(() => {
    if (chartMode === "race_pace") return points.map((p) => p.predicted_lap_s);
    return tyreWearValues;
  }, [points, chartMode, tyreWearValues]);

  // Race pace: min-max scale. Tyre wear: zero-anchored so 0% (fresh) is the shortest bar.
  const { minVal, range } = useMemo(() => {
    if (values.length === 0) return { minVal: 0, range: 1 };
    if (chartMode === "race_pace") {
      const maxV = Math.max(...values);
      const minV = Math.min(...values);
      return { minVal: minV, range: Math.max(maxV - minV, 0.01) };
    }
    const maxV = Math.max(...values, 0.05);
    const minV = Math.min(0, ...values);
    return { minVal: minV, range: Math.max(maxV - minV, 0.05) };
  }, [values, chartMode]);

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
              Tyre wear %
            </button>
          </div>
        </div>

        <p className="text-sm text-fog">
          {chartMode === "race_pace" ? (
            <>
              <strong className="text-white">Race pace</strong> mixes fuel + tyre + lap number. Early bars
              can look tall because the car is heavy — not because the tyre is worn.
            </>
          ) : (
            <>
              <strong className="text-white">Tyre wear %</strong> is pace loss vs a fresh tyre (fuel fixed).
              Fresh = <strong className="text-white">0%</strong> / tyre effect{" "}
              <strong className="text-white">0.000s</strong> (shortest bar). Wear is forced{" "}
              <em>non-decreasing</em> with age — a tyre cannot get faster mid-stint.
            </>
          )}{" "}
          Click a bar for details.
        </p>

        <div className="relative flex h-36 items-end gap-1 border border-white/10 bg-ink-900/50 p-3">
          {chartMode === "tyre_only" && (
            <div className="pointer-events-none absolute inset-x-3 top-3 flex justify-between text-[10px] uppercase tracking-wider text-muted">
              <span>0% fresh</span>
              <span>more wear →</span>
            </div>
          )}
          {points.map((point, idx) => {
            const value = values[idx] ?? 0;
            const height = Math.max(6, ((value - minVal) / range) * 100);
            const active = selectedLapIdx === idx;
            const label =
              chartMode === "race_pace"
                ? `${point.predicted_lap_s.toFixed(3)}s`
                : formatPct(point.tyre_degradation_pct ?? 0);
            return (
              <button
                key={`${point.lap_number}-${idx}`}
                type="button"
                onClick={() => setSelectedLapIdx(idx)}
                className={`flex-1 rounded-t-sm transition ${
                  active ? "bg-white" : "bg-accent/80 hover:bg-accent"
                }`}
                style={{ height: `${height}%` }}
                title={`Lap ${point.lap_number}: ${label}`}
                aria-label={`Lap ${point.lap_number}`}
              />
            );
          })}
        </div>

        {selectedPoint && (
          <div className="grid gap-3 border border-white/10 bg-ink-850/70 p-4 sm:grid-cols-2 lg:grid-cols-5">
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
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-[0.14em] text-muted">Degradation</p>
              <p className="font-mono text-xl text-accent">
                {formatPct(selectedPoint.tyre_degradation_pct ?? 0)}
              </p>
              <p className="text-[11px] text-muted">vs fresh tyre pace</p>
            </div>
            <div>
              <p className="text-[11px] uppercase tracking-[0.14em] text-muted">Life used</p>
              <p className="font-mono text-xl text-white">
                {(selectedPoint.tyre_life_used_pct ?? 0).toFixed(1)}%
              </p>
              <p className="text-[11px] text-muted">through this stint window</p>
            </div>
            <div className="sm:col-span-2 lg:col-span-5 grid gap-3 border-t border-white/10 pt-3 sm:grid-cols-2">
              <div>
                <p className="text-[11px] uppercase tracking-[0.14em] text-muted">Predicted lap (race pace)</p>
                <p className="font-mono text-lg text-white">{selectedPoint.predicted_lap_s.toFixed(3)}s</p>
              </div>
              <div>
                <p className="text-[11px] uppercase tracking-[0.14em] text-muted">Tyre effect</p>
                <p className="font-mono text-lg text-white">
                  {formatDelta(selectedPoint.tyre_effect_s)}
                </p>
              </div>
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
