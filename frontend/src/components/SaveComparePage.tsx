"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  fetchPredictionCompare,
  type PredictionCompareResponse,
} from "@/lib/api";
import { ResultsCompareView } from "./ResultsCompareView";

export function SaveComparePage({
  meetingKey,
  saveId,
}: {
  meetingKey: number;
  saveId: string;
}) {
  const [compare, setCompare] = useState<PredictionCompareResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchPredictionCompare(meetingKey, saveId);
        if (!cancelled) setCompare(data);
      } catch (err) {
        if (!cancelled) {
          setCompare(null);
          setError(err instanceof Error ? err.message : "Compare failed");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [meetingKey, saveId]);

  const meetingLabel = compare
    ? `${compare.snapshot.meeting.year} · ${compare.snapshot.meeting.meeting_name}`
    : `Meeting ${meetingKey}`;

  return (
    <main className="relative mx-auto flex w-full max-w-6xl flex-col gap-8 px-5 pb-16 pt-10 md:px-8">
      <header className="space-y-4">
        <p className="text-[11px] uppercase tracking-[0.28em] text-accent">Locked predictions</p>
        <h1 className="font-display text-4xl leading-none tracking-[0.04em] text-white md:text-6xl">
          {meetingLabel}
        </h1>
      </header>

      {loading && (
        <div className="animate-pulse border border-white/10 bg-panel/60 px-4 py-8 text-center text-sm text-muted">
          Comparing…
        </div>
      )}

      {error && (
        <div className="space-y-3">
          <div className="border border-accent/40 bg-accent/10 px-4 py-3 text-sm text-white">
            {error}
          </div>
          <Link
            href={`/results/${meetingKey}`}
            className="text-[11px] uppercase tracking-[0.16em] text-muted hover:text-white"
          >
            ← Back to saves
          </Link>
        </div>
      )}

      {compare && !loading && (
        <ResultsCompareView compare={compare} backHref={`/results/${meetingKey}`} />
      )}
    </main>
  );
}
