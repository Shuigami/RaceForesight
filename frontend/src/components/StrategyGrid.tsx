"use client";

import type { ActualDriverStrategy, DriverStrategy } from "@/lib/api";
import { formatRaceTime } from "@/lib/api";
import { CompoundPills } from "./CompoundPills";

type Props = {
  drivers: DriverStrategy[];
  actual?: ActualDriverStrategy[];
  selected: number | null;
  onSelect: (driverNumber: number) => void;
};

export function StrategyGrid({ drivers, actual = [], selected, onSelect }: Props) {
  const actualByDriver = new Map(actual.map((a) => [a.driver_number, a]));
  const showActual = actual.length > 0;

  return (
    <div className="overflow-x-auto rounded-sm border border-white/10 bg-panel/80 backdrop-blur">
      <table className="w-full min-w-[720px] border-collapse text-left text-sm">
        <thead>
          <tr className="border-b border-white/10 text-[11px] uppercase tracking-[0.14em] text-muted">
            <th className="px-4 py-3 font-medium">#</th>
            <th className="px-4 py-3 font-medium">Driver</th>
            <th className="px-4 py-3 font-medium">Team</th>
            <th className="px-4 py-3 font-medium">Predicted</th>
            <th className="px-4 py-3 font-medium">Compounds</th>
            <th className="px-4 py-3 font-medium">Pit laps</th>
            {showActual && (
              <>
                <th className="px-4 py-3 font-medium">Ran</th>
                <th className="px-4 py-3 font-medium">Actual compounds</th>
                <th className="px-4 py-3 font-medium">Actual pits</th>
              </>
            )}
            <th className="px-4 py-3 font-medium text-right">Strategy race time</th>
          </tr>
        </thead>
        <tbody>
          {drivers.map((d, idx) => {
            const active = selected === d.driver_number;
            const ran = actualByDriver.get(d.driver_number);
            return (
              <tr
                key={d.driver_number}
                onClick={() => onSelect(d.driver_number)}
                className={`cursor-pointer border-b border-white/5 transition-colors ${
                  active ? "bg-accent/15" : "hover:bg-white/5"
                }`}
              >
                <td className="px-4 py-3 font-mono text-muted">{idx + 1}</td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-3">
                    <span
                      className="h-8 w-1 rounded-full"
                      style={{ backgroundColor: d.team_colour ? `#${d.team_colour}` : "#e10600" }}
                    />
                    <div>
                      <div className="font-display text-lg leading-none tracking-wide">{d.name_acronym}</div>
                      <div className="text-xs text-muted">{d.full_name}</div>
                    </div>
                  </div>
                </td>
                <td className="px-4 py-3 text-muted">{d.team_name}</td>
                <td className="px-4 py-3">
                  <span className="font-mono text-xs text-fog">{d.stops}-stop</span>
                </td>
                <td className="px-4 py-3">
                  <CompoundPills compounds={d.compounds} />
                </td>
                <td className="px-4 py-3 font-mono text-fog">{d.pit_laps.join(", ")}</td>
                {showActual && (
                  <>
                    <td className="px-4 py-3">
                      {ran ? (
                        <span className="font-mono text-xs text-fog">{ran.stops}-stop</span>
                      ) : (
                        <span className="text-xs text-muted">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {ran ? <CompoundPills compounds={ran.compounds} /> : <span className="text-xs text-muted">—</span>}
                    </td>
                    <td className="px-4 py-3 font-mono text-fog">
                      {ran ? ran.pit_laps.join(", ") || "—" : "—"}
                    </td>
                  </>
                )}
                <td className="px-4 py-3 text-right font-mono tabular-nums text-white">
                  {formatRaceTime(d.predicted_race_time_s)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
