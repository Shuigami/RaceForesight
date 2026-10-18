"use client";

import type { PredictedFinish } from "@/lib/api";
import { formatRaceTime } from "@/lib/api";

export function ClassificationDetail({ row }: { row: PredictedFinish }) {
  return (
    <section className="space-y-4 rounded-sm border border-white/10 bg-panel/90 p-6 backdrop-blur">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[11px] uppercase tracking-[0.2em] text-muted">Driver classification</p>
          <h2 className="font-display text-4xl tracking-wide text-white">{row.full_name}</h2>
          <p className="mt-1 text-sm text-fog">
            {row.team_name}
            {row.strategy_label ? ` · ${row.strategy_label}` : ""}
          </p>
        </div>
        <div className="text-right">
          <p className="text-[11px] uppercase tracking-[0.16em] text-muted">Predicted position</p>
          <p className="font-display text-4xl text-accent">P{row.position}</p>
          {row.confidence != null && (
            <p className="mt-1 font-mono text-xs text-muted">
              {Math.round(row.confidence * 100)}% confidence
            </p>
          )}
        </div>
      </header>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="border border-white/10 bg-ink-850/60 px-4 py-3">
          <p className="text-[11px] uppercase tracking-[0.16em] text-muted">Est. race time</p>
          <p className="mt-1 font-mono text-2xl text-white">
            {row.estimated_race_time_s != null ? formatRaceTime(row.estimated_race_time_s) : "—"}
          </p>
          <p className="mt-2 text-xs text-muted">
            Estimated race duration from the active model — not Strategy tyre wall-clock.
          </p>
        </div>
        <div className="border border-white/10 bg-ink-850/60 px-4 py-3">
          <p className="text-[11px] uppercase tracking-[0.16em] text-muted">Gap to P1 (pace)</p>
          <p className="mt-1 font-mono text-2xl text-fog">
            {row.gap_to_leader_s != null && row.gap_to_leader_s > 0
              ? `+${row.gap_to_leader_s.toFixed(1)}s`
              : row.gap_to_leader_s === 0
                ? "leader"
                : "—"}
          </p>
          <p className="mt-2 text-xs text-muted">
            Relative to P1’s pace estimate, not a race gap prediction.
          </p>
        </div>
      </div>
    </section>
  );
}
