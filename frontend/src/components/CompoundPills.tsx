import { compoundColor } from "@/lib/api";

export function CompoundPills({ compounds }: { compounds: string[] }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {compounds.map((c, i) => (
        <span
          key={`${c}-${i}`}
          className="inline-flex items-center gap-1 rounded px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-ink-900"
          style={{ backgroundColor: compoundColor(c), color: c === "HARD" ? "#111" : "#0a0a0a" }}
        >
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{ backgroundColor: c === "HARD" ? "#333" : "#fff", opacity: 0.7 }}
          />
          {c.slice(0, 1)}
        </span>
      ))}
    </div>
  );
}
