"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  deletePredictionSave,
  fetchMeetingSaves,
  renamePredictionSave,
  type LockStatus,
  type PredictionSaveListItem,
} from "@/lib/api";

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

function SaveRow({
  meetingKey,
  item,
  onChanged,
}: {
  meetingKey: number;
  item: PredictionSaveListItem;
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
    <li className="flex flex-col gap-2 border-t border-white/5 px-4 py-3 first:border-t-0 sm:flex-row sm:items-center sm:gap-4">
      <div className="min-w-0 flex-1 space-y-1">
        <input
          className="w-full border border-transparent bg-transparent px-1 py-1 text-sm text-white outline-none focus:border-white/20"
          value={name}
          disabled={busy}
          onChange={(e) => setName(e.target.value)}
          onBlur={() => void commitRename()}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.currentTarget.blur();
            }
            if (e.key === "Escape") {
              setName(item.name);
              e.currentTarget.blur();
            }
          }}
          aria-label="Save name"
        />
        <p className="px-1 text-xs text-muted">
          {fmtWhen(item.saved_at)}
          {" · "}
          {lockLabel(item.lock_status)}
          {" · "}
          {item.status === "scored" ? "scored" : "pending"}
        </p>
        {error && <p className="px-1 text-xs text-accent">{error}</p>}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => router.push(`/results/${meetingKey}/${item.id}`)}
          className="border border-white/15 px-3 py-1.5 text-[11px] uppercase tracking-[0.14em] text-fog hover:border-accent hover:text-white disabled:opacity-50"
        >
          Open
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void onDelete()}
          className="border border-white/15 px-3 py-1.5 text-[11px] uppercase tracking-[0.14em] text-muted hover:border-accent hover:text-accent disabled:opacity-50"
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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const items = await fetchMeetingSaves(meetingKey);
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

  const title = saves[0]
    ? `${saves[0].year ? `${saves[0].year} · ` : ""}${saves[0].meeting_name}`
    : `Meeting ${meetingKey}`;

  return (
    <main className="relative mx-auto flex w-full max-w-6xl flex-col gap-8 px-5 pb-16 pt-10 md:px-8">
      <header className="space-y-4">
        <Link
          href="/results"
          className="text-[11px] uppercase tracking-[0.16em] text-muted hover:text-white"
        >
          ← Results
        </Link>
        <p className="text-[11px] uppercase tracking-[0.28em] text-accent">Saved forecasts</p>
        <h1 className="font-display text-4xl leading-none tracking-[0.04em] text-white md:text-6xl">
          {title}
        </h1>
        <p className="max-w-xl text-sm text-fog">
          Rename inline, delete, or open a save to compare against the race.
        </p>
      </header>

      {loading && (
        <div className="animate-pulse border border-white/10 bg-panel/60 px-4 py-8 text-center text-sm text-muted">
          Loading saves…
        </div>
      )}

      {error && (
        <div className="border border-accent/40 bg-accent/10 px-4 py-3 text-sm text-white">{error}</div>
      )}

      {!loading && saves.length > 0 && (
        <ul className="border border-white/10 bg-panel/80">
          {saves.map((item) => (
            <SaveRow
              key={item.id}
              meetingKey={meetingKey}
              item={item}
              onChanged={() => void load()}
            />
          ))}
        </ul>
      )}
    </main>
  );
}
