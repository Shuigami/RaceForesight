export type MetricInfo = {
  label: string;
  short: string;
  detail: string;
  goodWhen: string;
};

/** Human-readable definitions for model score keys. */
export const METRIC_GLOSSARY: Record<string, MetricInfo> = {
  mae_s: {
    label: "MAE (s)",
    short: "Mean Absolute Error in seconds",
    detail:
      "Average absolute difference between predicted and actual lap times. If MAE = 0.8s, predictions are off by 0.8 seconds on average.",
    goodWhen: "Lower is better. Under ~1s is solid for race-pace modelling.",
  },
  rmse_s: {
    label: "RMSE (s)",
    short: "Root Mean Squared Error in seconds",
    detail:
      "Like MAE, but large mistakes are penalised more (errors are squared before averaging). Sensitive to outlier laps.",
    goodWhen: "Lower is better. Usually a bit higher than MAE.",
  },
  r2: {
    label: "R²",
    short: "Coefficient of determination",
    detail:
      "Share of lap-time variance explained by the model (0 = no better than predicting the mean, 1 = perfect fit on the test set).",
    goodWhen: "Closer to 1 is better. High R² can still hide systematic bias.",
  },
  n_train: {
    label: "Train rows",
    short: "Number of training laps",
    detail: "How many historical competitive laps were used to fit the model.",
    goodWhen: "More data generally helps, if the seasons stay relevant.",
  },
  n_test: {
    label: "Test rows",
    short: "Number of held-out laps",
    detail: "Laps from later sessions used only for scoring — not seen during training.",
    goodWhen: "Enough rows for a stable estimate (thousands is good).",
  },
  target: {
    label: "Target",
    short: "What the model predicts",
    detail:
      "circuit_residual means the model predicts the gap to that circuit’s typical lap, then we add the circuit baseline back.",
    goodWhen: "Residuals make strategy comparisons fairer across tracks.",
  },
  races_evaluated: {
    label: "Races evaluated",
    short: "Backtest sample size",
    detail: "How many completed Grands Prix were used to score the classification model against official results.",
    goodWhen: "More races → more trustworthy ranking metrics.",
  },
  spearman: {
    label: "Spearman ρ",
    short: "Rank correlation",
    detail:
      "Measures whether the predicted order matches the real finishing order (not the exact times). 1 = identical ranking, 0 = no relationship, negative = inverted.",
    goodWhen: "Higher is better. ~0.3–0.5 is a useful but imperfect F1 order signal.",
  },
  kendall_tau: {
    label: "Kendall τ",
    short: "Pairwise rank agreement",
    detail:
      "Fraction of driver pairs ordered the same way in prediction and reality, adjusted for ties. Similar intuition to Spearman, often a bit lower.",
    goodWhen: "Higher is better.",
  },
  top3_hit_rate: {
    label: "Top-3 hit rate",
    short: "Podium overlap",
    detail:
      "Average share of the real podium that also appears in our predicted top 3 (e.g. 0.47 ≈ 1.4 of 3 podium drivers correct).",
    goodWhen: "Higher is better. 1.0 would mean we always nail the podium set.",
  },
  mae_position: {
    label: "MAE position",
    short: "Mean absolute position error",
    detail:
      "On average, how many places off is each driver’s predicted finishing position vs reality.",
    goodWhen: "Lower is better. ~4–5 places is typical without quali/traffic modelling.",
  },
};

export function metricInfo(key: string): MetricInfo {
  return (
    METRIC_GLOSSARY[key] ?? {
      label: key,
      short: key,
      detail: "Metric produced by the evaluation pipeline.",
      goodWhen: "",
    }
  );
}
