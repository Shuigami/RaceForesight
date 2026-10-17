"use client";

import { useCallback, useEffect, useState } from "react";
import {
  fetchModelMetrics,
  runModelEvaluation,
  type ModelScore,
  type ModelsMetricsResponse,
} from "@/lib/api";
import { METRIC_GLOSSARY, metricInfo } from "@/lib/metricGlossary";
import { ExplainPanel } from "./ExplainPanel";

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

export function ModelsDashboard() {
  const [data, setData] = useState<ModelsMetricsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

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

  return (
    <main className="relative mx-auto flex w-full max-w-6xl flex-col gap-8 px-5 pb-16 pt-10 md:px-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-3">
          <p className="text-[11px] uppercase tracking-[0.28em] text-accent">Model lab</p>
          <h1 className="font-display text-5xl tracking-[0.04em] text-white md:text-6xl">
            Accuracy & scores
          </h1>
          <p className="max-w-2xl text-fog">
            Compare lap-time regressors and the classification backtest. XGBoost powers live strategy;
            Random Forest is a benchmark on the same split.
          </p>
        </div>
        <button
          type="button"
          onClick={onEvaluate}
          disabled={evaluating}
          className="border border-accent bg-accent/15 px-4 py-2.5 text-[11px] uppercase tracking-[0.16em] text-white transition hover:bg-accent/25 disabled:opacity-50"
        >
          {evaluating ? "Evaluating…" : "Re-run evaluation"}
        </button>
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

      {data && (
        <>
          <div className="flex flex-wrap gap-4 text-xs text-muted">
            <span>Generated {new Date(data.generated_at).toLocaleString()}</span>
            <span>·</span>
            <span>{data.evaluation_races} ranking races backtested</span>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            {data.models.map((model) => (
              <article
                key={`${model.kind}-${model.version}`}
                className={`border bg-panel/80 p-5 backdrop-blur ${
                  model.primary ? "border-accent/50" : "border-white/10"
                }`}
              >
                <div className="mb-3 flex items-start justify-between gap-2">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.14em] text-muted">{model.kind}</p>
                    <h2 className="font-display text-2xl tracking-wide text-white">{model.name}</h2>
                  </div>
                  {model.primary && (
                    <span className="border border-accent/40 bg-accent/10 px-2 py-0.5 text-[10px] uppercase tracking-wider text-accent">
                      Primary
                    </span>
                  )}
                </div>
                <p className="mb-4 text-xs leading-relaxed text-fog">{model.description}</p>
                <p className="mb-3 font-mono text-[11px] text-muted">{model.version}</p>
                <dl className="space-y-2">
                  {metricEntries(model).map(([key, value]) => {
                    const info = metricInfo(key);
                    return (
                      <div
                        key={key}
                        className="border-t border-white/5 pt-2"
                        title={`${info.short}. ${info.detail}`}
                      >
                        <div className="flex items-baseline justify-between gap-3">
                          <dt className="text-[11px] uppercase tracking-[0.12em] text-muted">
                            {info.label}
                          </dt>
                          <dd className="font-mono text-sm text-white">{formatMetric(key, value)}</dd>
                        </div>
                        <p className="mt-1 text-[11px] leading-snug text-fog/90">{info.short}</p>
                      </div>
                    );
                  })}
                </dl>
              </article>
            ))}
          </div>

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
