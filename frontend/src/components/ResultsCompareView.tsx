"use client";

import { useMemo } from "react";
import Link from "next/link";
import {
  formatPitWindows,
  formatRaceTime,
  type ActualDriverStrategy,
  type GlobalStrategy,
  type LockStatus,
  type PredictionCompareResponse,
} from "@/lib/api";
import { CompoundPills } from "./CompoundPills";

function compoundKey(compounds: string[]): string {
  return [...compounds].map((c) => c.toUpperCase()).sort().join("|");
}

function formatGap(seconds: number): string {
  if (seconds === 0) return "baseline";
  const sign = seconds > 0 ? "+" : "";
  return `${sign}${seconds.toFixed(1)}s`;
}

function compoundsInTop4(pred: GlobalStrategy[], compounds: string[]): boolean {
  const key = compoundKey(compounds);
  return pred.some((s) => compoundKey(s.compounds) === key);
}

function fmtWhen(iso: string | null | undefined) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function lockLabel(status: LockStatus): string {
  switch (status) {
    case "locked_before_start":
      return "Locked before lights out";
    case "overwritten_after_start":
      return "Overwritten after start";
    case "saved_after_start":
      return "Saved after start";
    case "awaiting_race_start":
      return "Awaiting race";
    default:
      return status;
  }
}

function lockClass(status: LockStatus): string {
  switch (status) {
    case "locked_before_start":
      return "border-emerald-500/40 bg-emerald-500/10 text-emerald-200";
    case "overwritten_after_start":
      return "border-amber-500/40 bg-amber-500/10 text-amber-100";
    case "saved_after_start":
      return "border-white/20 bg-white/5 text-fog";
    case "awaiting_race_start":
      return "border-sky-500/40 bg-sky-500/10 text-sky-100";
    default:
      return "border-white/15 text-muted";
  }
}

function deltaClass(delta: number | null) {
  if (delta == null) return "text-muted";
  if (delta === 0) return "text-fog";
  if (delta < 0) return "text-emerald-300";
  return "text-accent";
}

function ScoreCard({ title, lines }: { title: string; lines: string[] }) {
  return (
    <div className="border border-white/10 bg-panel/80 px-4 py-3">
      <p className="text-[11px] uppercase tracking-[0.16em] text-muted">{title}</p>
      <ul className="mt-2 space-y-1 text-sm text-white">
        {lines.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </div>
  );
}

export function ResultsCompareView({
  compare,
  backHref,
}: {
  compare: PredictionCompareResponse;
  backHref: string;
}) {
  const actualPos = useMemo(() => {
    const map = new Map<number, { position: number; duration_s: number | null }>();
    for (const row of compare.actual_finishes) {
      map.set(row.driver_number, { position: row.position, duration_s: row.duration_s });
    }
    return map;
  }, [compare]);

  const actualStrategy = useMemo(() => {
    const map = new Map<number, ActualDriverStrategy>();
    for (const row of compare.actual_strategies) {
      map.set(row.driver_number, row);
    }
    return map;
  }, [compare]);

  const metrics = compare.metrics;
  const snap = compare.snapshot;

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-center gap-3">
        <Link
          href={backHref}
          className="text-[11px] uppercase tracking-[0.16em] text-muted hover:text-white"
        >
          ← Saves
        </Link>
        {snap.name && (
          <span className="text-sm text-fog">{snap.name}</span>
        )}
      </div>

      <section className="flex flex-wrap items-center gap-3">
        <span
          className={`border px-3 py-1.5 text-[11px] uppercase tracking-[0.14em] ${lockClass(compare.lock_status)}`}
        >
          {lockLabel(compare.lock_status)}
        </span>
        <span
          className={`border px-3 py-1.5 text-[11px] uppercase tracking-[0.14em] ${
            compare.status === "scored"
              ? "border-accent/40 bg-accent/10 text-white"
              : "border-white/15 text-muted"
          }`}
        >
          {compare.status === "scored" ? "Scored" : "Actuals pending"}
        </span>
        <div className="text-xs text-muted">
          Saved {fmtWhen(snap.saved_at)}
          {" · "}
          Race start {fmtWhen(snap.race_start_at)}
        </div>
      </section>

      {compare.status === "scored" && metrics && (
        <section className="grid gap-3 sm:grid-cols-3">
          <ScoreCard
            title="Classification"
            lines={[
              `Spearman ${metrics.classification.spearman ?? "—"}`,
              `Top-3 hits ${metrics.classification.top3_hits ?? "—"}/3`,
              `MAE pos ${metrics.classification.mae_pos ?? "—"}`,
            ]}
          />
          <ScoreCard
            title="Race time"
            lines={[
              `MAE ${metrics.race_time.mae_s != null ? `${metrics.race_time.mae_s}s` : "—"}`,
              `RMSE ${metrics.race_time.rmse_s != null ? `${metrics.race_time.rmse_s}s` : "—"}`,
              `n ${metrics.race_time.n ?? 0}`,
            ]}
          />
          <ScoreCard
            title="Strategy (top 4)"
            lines={[
              `Field hit ${metrics.strategy.compound_matches ?? 0}/${metrics.strategy.n ?? 0}`,
              `Rate ${
                metrics.strategy.compound_match_rate != null
                  ? `${(Number(metrics.strategy.compound_match_rate) * 100).toFixed(0)}%`
                  : "—"
              }`,
            ]}
          />
        </section>
      )}

      {compare.status === "awaiting_race" && (
        <div className="border border-white/10 bg-panel/50 px-4 py-3 text-sm text-fog">
          Official results not in yet — predictions below stay locked until OpenF1 posts
          session_result.
        </div>
      )}

      <section className="space-y-3">
        <h2 className="font-display text-2xl tracking-wide text-white">Classification</h2>
        <div className="overflow-x-auto rounded-sm border border-white/10 bg-panel/80">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-white/10 text-[11px] uppercase tracking-[0.14em] text-muted">
              <tr>
                <th className="px-3 py-2">Driver</th>
                <th className="px-3 py-2">Pred</th>
                <th className="px-3 py-2">Actual</th>
                <th className="px-3 py-2">Δ</th>
              </tr>
            </thead>
            <tbody>
              {snap.classification.standings.map((row) => {
                const act = actualPos.get(row.driver_number);
                const delta = act ? row.position - act.position : null;
                return (
                  <tr key={row.driver_number} className="border-t border-white/5">
                    <td className="px-3 py-2">
                      <span className="font-semibold text-white">{row.name_acronym}</span>
                      <span className="ml-2 text-muted">{row.team_name}</span>
                    </td>
                    <td className="px-3 py-2 text-white">{row.position}</td>
                    <td className="px-3 py-2 text-fog">{act?.position ?? "—"}</td>
                    <td className={`px-3 py-2 ${deltaClass(delta)}`}>
                      {delta == null ? "—" : delta === 0 ? "0" : delta > 0 ? `+${delta}` : delta}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="font-display text-2xl tracking-wide text-white">Race time</h2>
        <div className="overflow-x-auto rounded-sm border border-white/10 bg-panel/80">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-white/10 text-[11px] uppercase tracking-[0.14em] text-muted">
              <tr>
                <th className="px-3 py-2">Driver</th>
                <th className="px-3 py-2">Pred</th>
                <th className="px-3 py-2">Actual</th>
                <th className="px-3 py-2">Δ</th>
              </tr>
            </thead>
            <tbody>
              {[...snap.race_time.standings]
                .sort(
                  (a, b) =>
                    (a.estimated_race_time_s ?? 1e12) - (b.estimated_race_time_s ?? 1e12),
                )
                .map((row) => {
                  const act = actualPos.get(row.driver_number);
                  const pred = row.estimated_race_time_s;
                  const actual = act?.duration_s ?? null;
                  const delta = pred != null && actual != null ? pred - actual : null;
                  return (
                    <tr key={row.driver_number} className="border-t border-white/5">
                      <td className="px-3 py-2 font-semibold text-white">{row.name_acronym}</td>
                      <td className="px-3 py-2 text-fog">
                        {pred != null ? formatRaceTime(pred) : "—"}
                      </td>
                      <td className="px-3 py-2 text-fog">
                        {actual != null ? formatRaceTime(actual) : "—"}
                      </td>
                      <td
                        className={`px-3 py-2 ${deltaClass(delta == null ? null : Math.sign(delta))}`}
                      >
                        {delta == null
                          ? "—"
                          : `${delta > 0 ? "+" : ""}${delta.toFixed(1)}s`}
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="font-display text-2xl tracking-wide text-white">Predicted strategies</h2>
        <div className="overflow-x-auto rounded-sm border border-white/10 bg-panel/80">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-white/10 text-[11px] uppercase tracking-[0.14em] text-muted">
              <tr>
                <th className="px-3 py-2">Rank</th>
                <th className="px-3 py-2">Compounds</th>
                <th className="px-3 py-2">Pit window</th>
                <th className="px-3 py-2">Pred time</th>
                <th className="px-3 py-2">Gap</th>
                <th className="px-3 py-2">Field</th>
              </tr>
            </thead>
            <tbody>
              {snap.strategy.strategies.map((row) => {
                const fieldN = [...actualStrategy.values()].filter(
                  (a) => compoundKey(a.compounds) === compoundKey(row.compounds),
                ).length;
                return (
                  <tr key={`${row.rank}-${row.strategy_label}`} className="border-t border-white/5">
                    <td className="px-3 py-2 font-mono text-muted">{row.rank}</td>
                    <td className="px-3 py-2">
                      <CompoundPills compounds={row.compounds} />
                      <span className="ml-2 text-[11px] text-muted">{row.stops}-stop</span>
                    </td>
                    <td className="px-3 py-2 font-mono text-fog">
                      {formatPitWindows(row.pit_windows, row.pit_laps)}
                    </td>
                    <td className="px-3 py-2 font-mono text-fog">
                      {formatRaceTime(row.predicted_race_time_s)}
                    </td>
                    <td className="px-3 py-2 font-mono text-fog">
                      {formatGap(row.gap_to_best_s)}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs text-muted">
                      {compare.status === "scored"
                        ? fieldN > 0
                          ? `${fieldN} cars`
                          : "—"
                        : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {compare.actual_strategies.length > 0 && (
        <section className="space-y-3">
          <h2 className="font-display text-2xl tracking-wide text-white">Actual field strategies</h2>
          <div className="overflow-x-auto rounded-sm border border-white/10 bg-panel/80">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-white/10 text-[11px] uppercase tracking-[0.14em] text-muted">
                <tr>
                  <th className="px-3 py-2">Compounds</th>
                  <th className="px-3 py-2">Cars</th>
                  <th className="px-3 py-2">In top 4</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(
                  compare.actual_strategies.reduce<
                    Record<string, { compounds: string[]; count: number }>
                  >((acc, act) => {
                    const key = compoundKey(act.compounds);
                    if (!acc[key]) acc[key] = { compounds: act.compounds, count: 0 };
                    acc[key].count += 1;
                    return acc;
                  }, {}),
                )
                  .sort((a, b) => b[1].count - a[1].count)
                  .map(([key, row]) => {
                    const hit = compoundsInTop4(snap.strategy.strategies, row.compounds);
                    return (
                      <tr key={key} className="border-t border-white/5">
                        <td className="px-3 py-2">
                          <CompoundPills compounds={row.compounds} />
                        </td>
                        <td className="px-3 py-2 font-mono text-fog">{row.count}</td>
                        <td className={`px-3 py-2 ${hit ? "text-emerald-300" : "text-accent"}`}>
                          {hit ? "Yes" : "No"}
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
