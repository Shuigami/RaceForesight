import type { IntegrityStatus } from "@/lib/api";

export function integrityLabel(status: IntegrityStatus): string {
  switch (status) {
    case "pre_race":
      return "Pre-race · clean";
    case "post_race":
      return "Post-race save";
    case "train_overlap":
      return "Train overlap";
    case "awaiting_race":
      return "Awaiting race";
    default:
      return "Integrity unknown";
  }
}

export function integrityTone(status: IntegrityStatus): string {
  switch (status) {
    case "pre_race":
      return "border-emerald-500/40 bg-emerald-500/10 text-emerald-200";
    case "post_race":
      return "border-white/20 bg-white/5 text-fog";
    case "train_overlap":
      return "border-amber-500/40 bg-amber-500/10 text-amber-100";
    case "awaiting_race":
      return "border-sky-500/40 bg-sky-500/10 text-sky-100";
    default:
      return "border-white/15 text-muted";
  }
}

export function fmtTrainedAt(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString([], {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}
