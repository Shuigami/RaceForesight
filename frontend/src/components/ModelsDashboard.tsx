"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchLiveModelArtifacts,
  fetchModelMetrics,
  fetchTrainStatus,
  runModelEvaluation,
  startModelTrain,
  type LiveModelArtifact,
  type ModelScore,
  type ModelsMetricsResponse,
  type TrainJobStatus,
  type TrainModelProgress,
  type TrainTarget,
} from "@/lib/api";
import { fmtTrainedAt } from "@/lib/resultsIntegrity";
import { METRIC_GLOSSARY, metricInfo } from "@/lib/metricGlossary";
import { ExplainPanel } from "./ExplainPanel";

const SECTION_ORDER = ["lap_time", "classification", "race_time"] as const;

const SECTION_LABELS: Record<(typeof SECTION_ORDER)[number], string> = {
  lap_time: "Lap time",
  classification: "Classification",
  race_time: "Race time",
};

const SECTION_BLURBS: Record<(typeof SECTION_ORDER)[number], string> = {
  lap_time: "Regressors used by tyre strategy (primary) and a Random Forest benchmark.",
  classification: "Finishing-order ranker scored leave-one-race-out vs OpenF1 results.",
  race_time: "Total race duration per driver (not Strategy tyre times).",
};

function metricEntries(model: ModelScore) {
  return Object.entries(model.metrics).filter(([, v]) => v !== null && v !== undefined);
}

function formatMetric(key: string, value: number | string | null) {
  if (value == null) return "—";
  if (typeof value === "string") return value;
  if (key.includes("rate") || key === "r2" || key.includes("spearman") || key.includes("kendall")) {
    return value.toFixed(3);
  }
  if (key.includes("mae") || key.includes("rmse")) {
    return value.toFixed(3);
  }
  if (Number.isInteger(value)) return String(value);
  return value.toFixed(3);
}

/** Prefer trailing …-vN, else lexicographic. */
function versionRank(version: string): number {
  const m = version.match(/v(\d+)\s*$/i);
  return m ? Number(m[1]) : 0;
}

function sortVersionsDesc(versions: string[]): string[] {
  return [...versions].sort((a, b) => {
    const dr = versionRank(b) - versionRank(a);
    if (dr !== 0) return dr;
    return b.localeCompare(a);
  });
}

function defaultSelection(models: ModelScore[]): { name: string; version: string } | null {
  if (models.length === 0) return null;
  const primary = models.find((m) => m.primary) ?? models[0];
  const sameName = models.filter((m) => m.name === primary.name);
  const versions = sortVersionsDesc(sameName.map((m) => m.version));
  return { name: primary.name, version: versions[0] };
}

function stageLabel(stage: string | null | undefined): string {
  switch (stage) {
    case "history":
      return "History";
    case "pace":
      return "Pace ingest";
    case "label":
      return "Label races";
    case "fit":
      return "Fitting";
    case "done":
      return "Done";
    case "starting":
      return "Starting";
    default:
      return stage || "Idle";
  }
}

function TrainBar({
  progress,
  artifact,
  busy,
  onTrain,
}: {
  progress: TrainModelProgress | undefined;
  artifact: LiveModelArtifact | undefined;
  busy: boolean;
  onTrain: () => void;
}) {
  const status = progress?.status ?? "pending";
  const total = progress?.total ?? 0;
  const current = progress?.current ?? 0;
  const pct =
    status === "done"
      ? 100
      : total > 0
        ? Math.min(100, Math.round((current / total) * 100))
        : status === "running" || status === "queued"
          ? 4
          : 0;
  const detail =
    status === "error"
      ? progress?.error || "Train failed"
      : status === "done"
        ? "Trained"
        : status === "pending"
          ? "Not in this job"
          : `${stageLabel(progress?.stage)}${total > 0 ? ` · ${current}/${total}` : ""}`;

  return (
    <div className="mt-5 border-t border-white/10 pt-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-[11px] uppercase tracking-[0.14em] text-muted">Train</p>
          <p className="mt-1 font-mono text-[11px] text-fog">
            Last trained {fmtTrainedAt(artifact?.trained_at)}
            {artifact?.version ? ` · ${artifact.version}` : ""}
          </p>
        </div>
        <button
          type="button"
          onClick={onTrain}
          disabled={busy}
          className="border border-white/20 px-3 py-1.5 text-[10px] uppercase tracking-[0.14em] text-white transition hover:border-accent/50 hover:bg-accent/10 disabled:opacity-40"
        >
          Train this
        </button>
      </div>
      <div className="h-2 overflow-hidden border border-white/10 bg-ink-900">
        <div
          className={`h-full transition-[width] duration-300 ${
            status === "error" ? "bg-accent/80" : status === "done" ? "bg-emerald-500/80" : "bg-accent/70"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="mt-1.5 font-mono text-[11px] text-fog">{detail}</p>
    </div>
  );
}

function ModelSection({
  kind,
  models,
  trainProgress,
  artifact,
  trainBusy,
  onTrain,
}: {
  kind: (typeof SECTION_ORDER)[number];
  models: ModelScore[];
  trainProgress: TrainModelProgress | undefined;
  artifact: LiveModelArtifact | undefined;
  trainBusy: boolean;
  onTrain: () => void;
}) {
  const modelNames = useMemo(() => {
    const names = [...new Set(models.map((m) => m.name))];
    // Primary family's name first, then alpha
    const primaryName = models.find((m) => m.primary)?.name;
    return names.sort((a, b) => {
      if (a === primaryName) return -1;
      if (b === primaryName) return 1;
      return a.localeCompare(b);
    });
  }, [models]);

  const initial = useMemo(() => defaultSelection(models), [models]);
  const [name, setName] = useState(initial?.name ?? "");
  const [version, setVersion] = useState(initial?.version ?? "");

  // Reset when artifact reloads (new evaluate / first load)
  useEffect(() => {
    const next = defaultSelection(models);
    setName(next?.name ?? "");
    setVersion(next?.version ?? "");
  }, [models]);

  const versionsForName = useMemo(() => {
    return sortVersionsDesc(models.filter((m) => m.name === name).map((m) => m.version));
  }, [models, name]);

  useEffect(() => {
    if (versionsForName.length === 0) return;
    if (!versionsForName.includes(version)) {
      setVersion(versionsForName[0]);
    }
  }, [versionsForName, version]);

  const selected =
    models.find((m) => m.name === name && m.version === version) ??
    models.find((m) => m.name === name) ??
    null;

  const onModelChange = (nextName: string) => {
    setName(nextName);
    const vers = sortVersionsDesc(models.filter((m) => m.name === nextName).map((m) => m.version));
    setVersion(vers[0] ?? "");
  };

  return (
    <article className="border border-white/10 bg-panel/80 p-5 backdrop-blur">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.14em] text-muted">{kind}</p>
          <h2 className="font-display text-2xl tracking-wide text-white">{SECTION_LABELS[kind]}</h2>
          <p className="mt-1 max-w-xl text-xs leading-relaxed text-fog">{SECTION_BLURBS[kind]}</p>
        </div>
        {selected?.primary && (
          <span className="border border-accent/40 bg-accent/10 px-2 py-0.5 text-[10px] uppercase tracking-wider text-accent">
            Primary
          </span>
        )}
      </div>

      <div className="mb-5 grid gap-3 sm:grid-cols-2">
        <label className="block space-y-1.5">
          <span className="text-[11px] uppercase tracking-[0.14em] text-muted">Model</span>
          <select
            className="w-full border border-white/15 bg-ink-850 px-3 py-2.5 text-sm text-white outline-none focus:border-accent"
            value={name}
            onChange={(e) => onModelChange(e.target.value)}
            disabled={modelNames.length === 0}
          >
            {modelNames.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <label className="block space-y-1.5">
          <span className="text-[11px] uppercase tracking-[0.14em] text-muted">Version</span>
          <select
            className="w-full border border-white/15 bg-ink-850 px-3 py-2.5 font-mono text-sm text-white outline-none focus:border-accent"
            value={version}
            onChange={(e) => setVersion(e.target.value)}
            disabled={versionsForName.length === 0}
          >
            {versionsForName.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </label>
      </div>

      {!selected ? (
        <p className="text-sm text-muted">No scores for this selection.</p>
      ) : (
        <>
          <p className="mb-4 text-xs leading-relaxed text-fog">{selected.description}</p>
          <dl className="space-y-2">
            {metricEntries(selected).map(([key, value]) => {
              const info = metricInfo(key);
              return (
                <div
                  key={key}
                  className="border-t border-white/5 pt-2"
                  title={`${info.short}. ${info.detail}`}
                >
                  <div className="flex items-baseline justify-between gap-3">
                    <dt className="text-[11px] uppercase tracking-[0.12em] text-muted">{info.label}</dt>
                    <dd className="font-mono text-sm text-white">{formatMetric(key, value)}</dd>
                  </div>
                  <p className="mt-1 text-[11px] leading-snug text-fog/90">{info.short}</p>
                </div>
              );
            })}
          </dl>
        </>
      )}

      <TrainBar
        progress={trainProgress}
        artifact={artifact}
        busy={trainBusy}
        onTrain={onTrain}
      />
    </article>
  );
}

export function ModelsDashboard() {
  const [data, setData] = useState<ModelsMetricsResponse | null>(null);
  const [artifacts, setArtifacts] = useState<Partial<Record<TrainTarget, LiveModelArtifact>>>({});
  const [loading, setLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);
  const [trainJob, setTrainJob] = useState<TrainJobStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const trainActive = trainJob?.status === "queued" || trainJob?.status === "running";

  const loadArtifacts = useCallback(async () => {
    try {
      const live = await fetchLiveModelArtifacts();
      setArtifacts(live.models ?? {});
    } catch {
      /* artifacts optional */
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchModelMetrics());
    } catch (err) {
      setData(null);
      setError(err instanceof Error ? err.message : "Failed to load metrics");
    } finally {
      setLoading(false);
    }
    await loadArtifacts();
  }, [loadArtifacts]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    void fetchTrainStatus()
      .then((job) => setTrainJob(job))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!trainActive) return;
    const id = window.setInterval(() => {
      void fetchTrainStatus()
        .then((job) => {
          setTrainJob(job);
          if (job && (job.status === "done" || job.status === "error")) {
            void load();
          }
        })
        .catch(() => undefined);
    }, 1500);
    return () => window.clearInterval(id);
  }, [trainActive, load]);

  const onEvaluate = async () => {
    setEvaluating(true);
    setError(null);
    try {
      setData(await runModelEvaluation());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Evaluation failed");
    } finally {
      setEvaluating(false);
    }
  };

  const onTrain = async (targets: TrainTarget[]) => {
    setError(null);
    try {
      setTrainJob(await startModelTrain(targets));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Train failed to start");
    }
  };

  const byKind = useMemo(() => {
    const map: Record<string, ModelScore[]> = {};
    for (const m of data?.models ?? []) {
      (map[m.kind] ??= []).push(m);
    }
    return map;
  }, [data]);

  return (
    <main className="relative mx-auto flex w-full max-w-6xl flex-col gap-8 px-5 pb-16 pt-10 md:px-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-3">
          <p className="text-[11px] uppercase tracking-[0.28em] text-accent">Model lab</p>
          <h1 className="font-display text-5xl tracking-[0.04em] text-white md:text-6xl">
            Accuracy & scores
          </h1>
          <p className="max-w-2xl text-fog">
            Pick a model and version in each section. Defaults to the primary (live) model at its
            latest version. Re-run evaluation merges new scores without wiping older versions.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void onTrain([...SECTION_ORDER])}
            disabled={trainActive || evaluating}
            className="border border-white/20 bg-white/5 px-4 py-2.5 text-[11px] uppercase tracking-[0.16em] text-white transition hover:border-accent/40 hover:bg-accent/10 disabled:opacity-50"
          >
            {trainActive ? "Training…" : "Train all"}
          </button>
          <button
            type="button"
            onClick={onEvaluate}
            disabled={evaluating || trainActive}
            className="border border-accent bg-accent/15 px-4 py-2.5 text-[11px] uppercase tracking-[0.16em] text-white transition hover:bg-accent/25 disabled:opacity-50"
          >
            {evaluating ? "Evaluating…" : "Re-run evaluation"}
          </button>
        </div>
      </header>

      <ExplainPanel title="How to read these scores">
        <p>
          <strong className="text-white">Lap-time models</strong> are scored on held-out historical laps
          (later sessions than the training window). MAE / RMSE tell you how wrong a single lap prediction
          is, in seconds.
        </p>
        <p>
          <strong className="text-white">Classification</strong> is scored against official race results
          (OpenF1 <code className="text-white">session_result</code>). Here we care about order — Spearman /
          Kendall — more than exact race times.
        </p>
        <p>
          Hover any metric row for a one-line reminder; full definitions are in the glossary below.
        </p>
      </ExplainPanel>

      {error && (
        <div className="border border-accent/40 bg-accent/10 px-4 py-3 text-sm text-white">
          <p>{error}</p>
          <p className="mt-2 text-xs text-fog">
            If no artifact exists yet, click &quot;Re-run evaluation&quot; or run{" "}
            <code className="text-white">python scripts/evaluate_models.py</code>.
          </p>
        </div>
      )}

      {loading && !data && (
        <div className="animate-pulse border border-white/10 bg-panel/60 px-4 py-8 text-center text-sm text-muted">
          Loading model metrics…
        </div>
      )}

      {trainJob && (
        <p className="font-mono text-xs text-muted">
          Train job {trainJob.job_id} · {trainJob.status}
          {trainJob.error ? ` · ${trainJob.error}` : ""}
        </p>
      )}

      {data && (
        <div className="flex flex-wrap gap-4 text-xs text-muted">
          <span>Generated {new Date(data.generated_at).toLocaleString()}</span>
          <span>·</span>
          <span>{data.evaluation_races} ranking races backtested</span>
          <span>·</span>
          <span>{data.models.length} score entries</span>
        </div>
      )}

      {!loading && (
        <div className="grid gap-4">
          {SECTION_ORDER.map((kind) => (
            <ModelSection
              key={kind}
              kind={kind}
              models={byKind[kind] ?? []}
              trainProgress={trainJob?.models?.[kind]}
              artifact={artifacts[kind]}
              trainBusy={trainActive || evaluating}
              onTrain={() => void onTrain([kind])}
            />
          ))}
        </div>
      )}

      {data && (
        <>
          <section className="border border-white/10 bg-panel/60 p-5 backdrop-blur">
            <h2 className="font-display text-2xl tracking-wide text-white">Metric glossary</h2>
            <p className="mt-1 mb-5 text-sm text-fog">
              Plain-language definitions for every score shown above.
            </p>
            <div className="grid gap-4 md:grid-cols-2">
              {Object.entries(METRIC_GLOSSARY).map(([key, info]) => (
                <div key={key} className="border border-white/5 bg-ink-900/40 p-4">
                  <div className="flex items-baseline justify-between gap-2">
                    <h3 className="font-display text-lg tracking-wide text-white">{info.label}</h3>
                    <span className="font-mono text-[10px] text-muted">{key}</span>
                  </div>
                  <p className="mt-1 text-xs uppercase tracking-[0.12em] text-accent">{info.short}</p>
                  <p className="mt-2 text-sm leading-relaxed text-fog">{info.detail}</p>
                  {info.goodWhen && (
                    <p className="mt-2 text-xs text-muted">
                      <span className="text-white">Rule of thumb:</span> {info.goodWhen}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </section>

          {data.notes.length > 0 && (
            <section className="border border-white/10 bg-ink-850/60 p-4">
              <h3 className="mb-2 text-[11px] uppercase tracking-[0.16em] text-muted">Notes</h3>
              <ul className="space-y-1 text-sm text-fog">
                {data.notes.map((note) => (
                  <li key={note}>· {note}</li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </main>
  );
}
