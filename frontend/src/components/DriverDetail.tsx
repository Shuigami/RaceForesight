"use client";

import type { StrategyDetail } from "@/lib/api";
import { formatRaceTime } from "@/lib/api";
import { CompoundPills } from "./CompoundPills";

export function DriverDetail({ detail }: { detail: StrategyDetail }) {
  const { best, alternatives, degradation_curve } = detail;
  const maxLap = Math.max(...degradation_curve.map((p) => p.predicted_lap_s), 1);
  const minLap = Math.min(...degradation_curve.map((p) => p.predicted_lap_s), maxLap);

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
          <p className="text-[11px] uppercase tracking-[0.16em] text-muted">Predicted race time</p>
          <p className="font-mono text-3xl text-accent">{formatRaceTime(best.predicted_race_time_s)}</p>
        </div>
      </header>

      <div className="grid gap-4 md:grid-cols-3">
        {best.stints.map((stint, i) => (
          <div key={`${stint.compound}-${i}`} className="border border-white/10 bg-ink-850/60 p-4">
            <p className="text-[11px] uppercase tracking-[0.14em] text-muted">Stint {i + 1}</p>
            <div className="mt-2">
              <CompoundPills compounds={[stint.compound]} />
            </div>
            <p className="mt-3 font-mono text-sm text-fog">
              Laps {stint.lap_start}–{stint.lap_end}
            </p>
          </div>
        ))}
      </div>

      <div>
        <h3 className="mb-3 text-[11px] uppercase tracking-[0.16em] text-muted">
          Tyre degradation · {degradation_curve[0]?.compound ?? "—"}
        </h3>
        <div className="flex h-28 items-end gap-1 border border-white/10 bg-ink-900/50 p-3">
          {degradation_curve.map((point) => {
            const range = Math.max(maxLap - minLap, 0.01);
            const height = ((point.predicted_lap_s - minLap) / range) * 100;
            return (
              <div
                key={point.tyre_age}
                className="flex-1 rounded-t-sm bg-accent/80 transition-all"
                style={{ height: `${Math.max(12, height)}%` }}
                title={`Age ${point.tyre_age}: ${point.predicted_lap_s.toFixed(3)}s`}
              />
            );
          })}
        </div>
      </div>

      <div>
        <h3 className="mb-3 text-[11px] uppercase tracking-[0.16em] text-muted">Alternatives</h3>
        <ul className="space-y-2">
          {alternatives.map((alt) => (
            <li
              key={alt.strategy_label}
              className="flex flex-wrap items-center justify-between gap-3 border border-white/5 bg-ink-900/40 px-4 py-3"
            >
              <div className="flex items-center gap-3">
                <span className="font-mono text-xs text-fog">{alt.stops}-stop</span>
                <CompoundPills compounds={alt.compounds} />
                <span className="font-mono text-xs text-muted">@{alt.pit_laps.join(", ")}</span>
              </div>
              <span className="font-mono text-sm">{formatRaceTime(alt.predicted_race_time_s)}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
