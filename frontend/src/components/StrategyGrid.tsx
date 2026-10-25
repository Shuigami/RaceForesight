"use client";

import type { ActualDriverStrategy, GlobalStrategy } from "@/lib/api";
import { formatPitWindows, formatRaceTime } from "@/lib/api";
import { CompoundPills } from "./CompoundPills";

type Props = {
  strategies: GlobalStrategy[];
  actual?: ActualDriverStrategy[];
};

function formatGap(seconds: number): string {
  if (seconds === 0) return "baseline";
  const sign = seconds > 0 ? "+" : "";
  return `${sign}${seconds.toFixed(1)}s`;
}

function compoundKey(compounds: string[]): string {
  return [...compounds].map((c) => c.toUpperCase()).sort().join("|");
}

export function StrategyGrid({ strategies, actual = [] }: Props) {
  const fieldCounts = new Map<string, number>();
  for (const a of actual) {
    const key = compoundKey(a.compounds);
    fieldCounts.set(key, (fieldCounts.get(key) ?? 0) + 1);
  }
  const showActual = actual.length > 0;

  return (
    <div className="overflow-x-auto rounded-sm border border-white/10 bg-panel/80 backdrop-blur">
      <table className="w-full min-w-[640px] border-collapse text-left text-sm">
        <thead>
          <tr className="border-b border-white/10 text-[11px] uppercase tracking-[0.14em] text-muted">
            <th className="px-4 py-3 font-medium">Rank</th>
            <th className="px-4 py-3 font-medium">Plan</th>
            <th className="px-4 py-3 font-medium">Compounds</th>
            <th className="px-4 py-3 font-medium">Pit window</th>
            <th className="px-4 py-3 font-medium">Pred time</th>
            <th className="px-4 py-3 font-medium">Gap</th>
            {showActual && <th className="px-4 py-3 font-medium">Field</th>}
          </tr>
        </thead>
        <tbody>
          {strategies.map((s) => {
            const fieldN = fieldCounts.get(compoundKey(s.compounds)) ?? 0;
            return (
              <tr key={`${s.rank}-${s.strategy_label}`} className="border-b border-white/5">
                <td className="px-4 py-3 font-mono text-muted">{s.rank}</td>
                <td className="px-4 py-3 font-mono text-xs text-fog">{s.stops}-stop</td>
                <td className="px-4 py-3">
                  <CompoundPills compounds={s.compounds} />
                </td>
                <td className="px-4 py-3 font-mono text-fog">
                  {formatPitWindows(s.pit_windows, s.pit_laps)}
                </td>
                <td className="px-4 py-3 font-mono text-white">
                  {formatRaceTime(s.predicted_race_time_s)}
                </td>
                <td className="px-4 py-3 font-mono text-fog">{formatGap(s.gap_to_best_s)}</td>
                {showActual && (
                  <td className="px-4 py-3 font-mono text-xs text-muted">
                    {fieldN > 0 ? `${fieldN} cars` : "—"}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
