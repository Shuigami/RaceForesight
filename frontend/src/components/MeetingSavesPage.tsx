"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  deletePredictionSave,
  fetchMeetingSaves,
  fetchRaces,
  renamePredictionSave,
  withMeetingArt,
  type LockStatus,
  type MeetingSummary,
  type PredictionSaveListItem,
} from "@/lib/api";
import { MeetingHero } from "./MeetingHero";

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
      return "Locked";
    case "overwritten_after_start":
      return "Overwritten";
    case "saved_after_start":
      return "After start";
    case "awaiting_race_start":
      return "Awaiting";
    default:
      return status;
  }
}

function lockTone(status: LockStatus): string {
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

function SaveRow({
  meetingKey,
  item,
  index,
  onChanged,
}: {
  meetingKey: number;
  item: PredictionSaveListItem;
  index: number;
  onChanged: () => void;
}) {
  const router = useRouter();
  const [name, setName] = useState(item.name);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setName(item.name);
  }, [item.name]);

  const commitRename = async () => {
    const next = name.trim();
    if (!next || next === item.name) {
      setName(item.name);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await renamePredictionSave(meetingKey, item.id, next);
      onChanged();
    } catch (err) {
      setName(item.name);
      setError(err instanceof Error ? err.message : "Rename failed");
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async () => {
    if (!window.confirm(`Delete save “${item.name}”?`)) return;
    setBusy(true);
    setError(null);
    try {
      await deletePredictionSave(meetingKey, item.id);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <li
      className="rf-row-hover group flex flex-col gap-3 border-t border-white/5 px-4 py-4 first:border-t-0 sm:flex-row sm:items-center sm:gap-5"
    >
      <div className="flex shrink-0 items-baseline gap-2 font-display text-2xl text-accent/80">
        <span className="rf-pos">{String(index + 1).padStart(2, "0")}</span>
      </div>
      <div className="min-w-0 flex-1 space-y-2">
        <input
          className="w-full border border-transparent bg-transparent px-1 py-1 font-display text-xl tracking-wide text-white outline-none focus:border-white/20"
          value={name}
          disabled={busy}
          onChange={(e) => setName(e.target.value)}
          onBlur={() => void commitRename()}
          onKeyDown={(e) => {
            if (e.key === "Enter") e.currentTarget.blur();
            if (e.key === "Escape") {
              setName(item.name);
              e.currentTarget.blur();
            }
          }}
          aria-label="Save name"
        />
        <div className="flex flex-wrap items-center gap-2 px-1">
          <span className={`border px-2 py-0.5 text-[10px] uppercase tracking-[0.14em] ${lockTone(item.lock_status)}`}>
            {lockLabel(item.lock_status)}
          </span>
          <span
            className={`border px-2 py-0.5 text-[10px] uppercase tracking-[0.14em] ${
              item.status === "scored"
                ? "border-accent/40 bg-accent/10 text-white"
                : "border-white/15 text-muted"
            }`}
          >
            {item.status === "scored" ? "Scored" : "Pending"}
          </span>
          <span className="font-mono text-[11px] text-muted">{fmtWhen(item.saved_at)}</span>
        </div>
        {item.model_versions && (
          <p className="px-1 text-[11px] leading-relaxed text-fog">
            {(
              [
                ["Class.", item.model_versions.classification],
                ["Race time", item.model_versions.race_time],
                ["Strategy", item.model_versions.strategy],
              ] as const
            ).map(([label, ref]) => (
              <span key={label} className="mr-3 inline-block">
                <span className="text-muted">{label}</span>{" "}
                <span className="text-white/90">{ref.name}</span>{" "}
                <span className="font-mono text-muted">{ref.version}</span>
              </span>
            ))}
          </p>
        )}
        {error && <p className="px-1 text-xs text-accent">{error}</p>}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => router.push(`/results/${meetingKey}/${item.id}`)}
          className="border border-accent bg-accent/20 px-4 py-2 text-[11px] uppercase tracking-[0.14em] text-white hover:bg-accent/30 disabled:opacity-50"
        >
          Compare
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void onDelete()}
          className="border border-white/15 px-3 py-2 text-[11px] uppercase tracking-[0.14em] text-muted hover:border-accent hover:text-accent disabled:opacity-50"
        >
          Delete
        </button>
      </div>
    </li>
  );
}

export function MeetingSavesPage({ meetingKey }: { meetingKey: number }) {
  const router = useRouter();
  const [saves, setSaves] = useState<PredictionSaveListItem[]>([]);
  const [races, setRaces] = useState<MeetingSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [items, raceList] = await Promise.all([
        fetchMeetingSaves(meetingKey),
        fetchRaces().catch(() => [] as MeetingSummary[]),
      ]);
      setRaces(raceList);
      setSaves(items);
      if (items.length === 0) {
        router.replace("/results");
      }
    } catch (err) {
      setSaves([]);
      setError(err instanceof Error ? err.message : "Failed to load saves");
    } finally {
      setLoading(false);
    }
  }, [meetingKey, router]);

  useEffect(() => {
    void load();
  }, [load]);

  const displaySaves = saves.map((s) => withMeetingArt(s, races));
  const first = displaySaves[0];

  return (
    <main className="relative mx-auto flex w-full max-w-6xl flex-col gap-8 px-5 pb-16 pt-10 md:px-8">
      <div className="space-y-4">
        <Link
          href="/results"
          className="text-[11px] uppercase tracking-[0.16em] text-muted hover:text-white"
        >
          ← Results
        </Link>
        {first ? (
          <MeetingHero
            meeting={first}
            kicker="Saved forecasts"
            title={first.meeting_name}
            meta={`${first.year ?? "—"}  ·  ${first.circuit_short_name || "—"}  ·  ${saves.length} SAVE${saves.length === 1 ? "" : "S"}`}
          />
        ) : (
          <h1 className="font-display text-4xl tracking-wide text-white md:text-6xl">
            Meeting {meetingKey}
          </h1>
        )}
        <p className="max-w-xl text-sm text-fog">
          Rename inline, delete, or open a save to compare against the race.
        </p>
      </div>

      {loading && (
        <div className="animate-pulse border border-white/10 bg-panel/60 px-4 py-8 text-center text-sm text-muted">
          Loading saves…
        </div>
      )}

      {error && (
        <div className="border border-accent/40 bg-accent/10 px-4 py-3 text-sm text-white">{error}</div>
      )}

      {!loading && displaySaves.length > 0 && (
        <ul className="overflow-x-clip border border-white/10 bg-panel/90">
          {displaySaves.map((item, index) => (
            <SaveRow
              key={item.id}
              meetingKey={meetingKey}
              item={item}
              index={index}
              onChanged={() => void load()}
            />
          ))}
        </ul>
      )}
    </main>
  );
}
