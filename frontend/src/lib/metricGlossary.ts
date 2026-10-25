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
      "Average absolute difference between predicted and actual values (lap times or full race durations, depending on the model).",
    goodWhen: "Lower is better. Lap models: under ~1s. Race-time model: tens of seconds is typical.",
  },
  rmse_s: {
    label: "RMSE (s)",
    short: "Root Mean Squared Error in seconds",
    detail:
      "Like MAE, but large mistakes are penalised more (errors are squared before averaging). Sensitive to outliers.",
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
  eval_protocol: {
    label: "Eval protocol",
    short: "How ranking was scored",
    detail:
      "leave_one_race_out means each scored GP was held out of training (no leakage from that race’s results or laps).",
    goodWhen: "Prefer LOO over a simple temporal split for finishing-order claims.",
  },
  n_races: {
    label: "Train races",
    short: "Races used to fit the ranker",
    detail: "Number of historical Grands Prix in the pairwise ranking training set.",
    goodWhen: "More completed races with quali + results help.",
  },
  n_rows: {
    label: "Ranker rows",
    short: "Driver-race examples",
    detail: "Total driver entries across training races for the ranking model.",
    goodWhen: "Hundreds of rows give a more stable pairwise fit.",
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
  within_race_mae_s: {
    label: "Within-race MAE (s)",
    short: "Relative gap error inside a race",
    detail:
      "Mean absolute error after removing each race’s average duration — how well we rank/separate drivers when Safety Cars dominate absolute wall-clock time.",
    goodWhen: "Lower is better. Under ~20s is a strong relative signal.",
  },
  best_iteration: {
    label: "Best iteration",
    short: "Trees kept by early stopping",
    detail: "Boosting round chosen on the inner validation split before performance stopped improving.",
    goodWhen: "Informative only — not a quality score by itself.",
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
