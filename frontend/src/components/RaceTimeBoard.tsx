"use client";

import type { DriverStrategy } from "@/lib/api";
import { formatRaceTime } from "@/lib/api";

type Props = {
  drivers: DriverStrategy[];
  selected: number | null;
  onSelect: (driverNumber: number) => void;
};

function formatGap(seconds: number): string {
  if (seconds <= 0) return "—";
  return `+${seconds.toFixed(3)}`;
}

export function RaceTimeBoard({ drivers, selected, onSelect }: Props) {
  const ordered = [...drivers].sort(
    (a, b) => a.predicted_race_time_s - b.predicted_race_time_s,
  );
  const leader = ordered[0]?.predicted_race_time_s ?? 0;

  return (
    <div className="overflow-x-auto rounded-sm border border-white/10 bg-panel/80 backdrop-blur">
      <table className="w-full min-w-[720px] border-collapse text-left text-sm">
        <thead>
          <tr className="border-b border-white/10 text-[11px] uppercase tracking-[0.14em] text-muted">
            <th className="px-4 py-3 font-medium">Pos</th>
            <th className="px-4 py-3 font-medium">Driver</th>
            <th className="px-4 py-3 font-medium">Team</th>
            <th className="px-4 py-3 font-medium">Race time</th>
            <th className="px-4 py-3 font-medium">Gap</th>
            <th className="px-4 py-3 font-medium">Avg lap</th>
            <th className="px-4 py-3 font-medium">Plan</th>
          </tr>
        </thead>
        <tbody>
          {ordered.map((d, idx) => {
            const active = selected === d.driver_number;
            const gap = d.predicted_race_time_s - leader;
            return (
              <tr
                key={d.driver_number}
                onClick={() => onSelect(d.driver_number)}
                className={`cursor-pointer border-b border-white/5 transition-colors ${
                  active ? "bg-accent/15" : "hover:bg-white/5"
                }`}
              >
                <td className="px-4 py-3 font-display text-xl text-accent">{idx + 1}</td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-3">
                    <span
                      className="h-8 w-1 rounded-full"
                      style={{ backgroundColor: d.team_colour ? `#${d.team_colour}` : "#e10600" }}
                    />
                    <div>
                      <div className="font-display text-lg leading-none tracking-wide">
                        {d.name_acronym}
                      </div>
                      <div className="text-xs text-muted">{d.full_name}</div>
                    </div>
                  </div>
                </td>
                <td className="px-4 py-3 text-muted">{d.team_name}</td>
                <td className="px-4 py-3 font-mono text-accent">
                  {formatRaceTime(d.predicted_race_time_s)}
                </td>
                <td className="px-4 py-3 font-mono text-fog">{formatGap(gap)}</td>
                <td className="px-4 py-3 font-mono text-fog">
                  {d.predicted_avg_lap_s != null ? `${d.predicted_avg_lap_s.toFixed(3)}s` : "—"}
                </td>
                <td className="px-4 py-3 text-xs text-muted">{d.strategy_label}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
