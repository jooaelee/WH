#!/usr/bin/env python3
"""Out-of-sample accuracy check: hold out the last N weeks, forecast them
blind using only earlier data, then compare against what actually shipped.

This is distinct from (and more honest than) the rmsse/mase/smape columns in
forecast_4weeks.csv: those come from rolling-origin backtests used partly to
*select* the model, which can look rosier than genuine forward-looking
performance. This script trains on data up to an earlier as-of date, forecasts
the next ``--holdout-weeks`` weeks, and scores against the real outcome.

Usage
-----
    python scripts/validate_holdout.py --config config.yaml --data-dir .
    python scripts/validate_holdout.py --config config.yaml --data-dir . --holdout-weeks 8
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from demand_forecast.config import load_config
from demand_forecast import data_loader
from demand_forecast.pipeline import run, GRAINS, _series_id


def _naive_scale(train: np.ndarray) -> float:
    """Mean absolute 1-step naive change over the training window (>0)."""
    if len(train) < 2:
        return 1.0
    m = np.abs(np.diff(train)).mean()
    return float(m) if m > 0 else 1.0


def main(argv=None):
    p = argparse.ArgumentParser(description="Out-of-sample holdout accuracy check")
    p.add_argument("--config", default=None, help="Path to config.yaml")
    p.add_argument("--data-dir", default=".", help="Base dir for relative data paths")
    p.add_argument("--holdout-weeks", type=int, default=4,
                   help="Weeks to hold out and forecast blind (default: 4)")
    p.add_argument("--output-dir", default="outputs/holdout_validation")
    args = p.parse_args(argv)

    cfg_full = load_config(args.config).resolved(args.data_dir)
    wh_full = data_loader.load(cfg_full)
    cutoff = wh_full.week_index[-1] - pd.Timedelta(weeks=args.holdout_weeks)
    print(f"학습 컷오프: {cutoff.date()}  (실제 데이터 최신일 {wh_full.week_index[-1].date()} "
          f"기준 {args.holdout_weeks}주 보류)")

    with tempfile.TemporaryDirectory() as tmp:
        result = run(load_config(args.config, as_of=str(cutoff.date()), output_dir=tmp,
                                 registry_path=str(Path(tmp) / "registry.json"),
                                 report_html=str(Path(tmp) / "report.html")),
                    base_dir=args.data_dir)

    cfg_train = load_config(args.config, as_of=str(cutoff.date())).resolved(args.data_dir)
    wh_train = data_loader.load(cfg_train)

    fc, lp = result.forecasts, result.large_prob
    wk_cols = sorted([c for c in fc.columns if c.startswith("w") and c.split("_")[0][1:].isdigit()],
                     key=lambda c: int(c.split("_")[0][1:]))
    future_weeks = pd.to_datetime([c.split("_", 1)[1] for c in wk_cols])
    full_idx = {wk: i for i, wk in enumerate(wh_full.week_index)}

    acc_rows, cal_rows = [], []
    for grain, keys in GRAINS.items():
        series_train = dict(data_loader.weekly_series(wh_train.outbound, keys, wh_train.week_index))
        series_full = dict(data_loader.weekly_series(wh_full.outbound, keys, wh_full.week_index))
        sid_to_key = {_series_id(grain, k): k for k in series_train}

        for _, row in fc[fc.grain == grain].iterrows():
            k = sid_to_key.get(row["series_id"])
            full_s = series_full.get(k) if k is not None else None
            if full_s is None:
                continue
            actual = np.array([full_s[full_idx[w]] if w in full_idx else np.nan for w in future_weeks])
            if np.any(np.isnan(actual)):
                continue
            forecast = np.array([row[c] for c in wk_cols], dtype=float)
            scale = _naive_scale(series_train[k])
            rmsse = float(np.sqrt(np.mean((forecast - actual) ** 2)) / scale)
            denom = np.abs(forecast) + np.abs(actual)
            with np.errstate(invalid="ignore", divide="ignore"):
                ratio = 2 * np.abs(forecast - actual) / denom
            smape = float(np.mean(np.where(denom > 0, ratio, 0.0)))
            acc_rows.append({"grain": grain, "series_id": row["series_id"], "label": row["label"],
                             "forecast_total": forecast.sum(), "actual_total": actual.sum(),
                             "rmsse": rmsse, "smape": smape})

        for _, row in lp[lp.grain == grain].iterrows():
            k = sid_to_key.get(row["series_id"])
            full_s = series_full.get(k) if k is not None else None
            if full_s is None:
                continue
            actual = np.array([full_s[full_idx[w]] if w in full_idx else np.nan for w in future_weeks])
            if np.any(np.isnan(actual)):
                continue
            thr = row["large_threshold"]
            actually_large = bool(np.any(actual >= thr)) if thr and thr > 0 else bool(np.any(actual > 0))
            cal_rows.append({"grain": grain, "series_id": row["series_id"],
                             "p_large_4w": row["p_large_4w"], "actually_large": actually_large})

    acc = pd.DataFrame(acc_rows)
    cal = pd.DataFrame(cal_rows)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    acc.to_csv(out_dir / "accuracy.csv", index=False)
    cal.to_csv(out_dir / "large_calibration.csv", index=False)

    finite = acc["rmsse"].replace([np.inf, -np.inf], np.nan).dropna()
    beats_naive = (finite < 1.0).mean() if len(finite) else float("nan")
    print(f"\n[OK] 평가 대상 {len(acc)}개 시계열 | 나이브 대비 우수(RMSSE<1) {beats_naive*100:.1f}% "
          f"| RMSSE 중앙값 {finite.median():.3f} | sMAPE 중앙값 {acc['smape'].median():.3f}")
    print(acc.groupby("grain").agg(n=("rmsse", "size"),
                                   beats_naive=("rmsse", lambda s: (s < 1).mean()),
                                   median_rmsse=("rmsse", "median")).round(3))

    if len(cal):
        cal["bucket"] = pd.cut(cal["p_large_4w"], bins=[0, 0.2, 0.4, 0.6, 0.8, 1.0], include_lowest=True)
        print("\n대량 출고 확률 캘리브레이션 (예측확률 구간별 실제 발생률):")
        print(cal.groupby("bucket", observed=True).agg(
            n=("actually_large", "size"), realized_rate=("actually_large", "mean")).round(3))
    print(f"\n결과 저장: {out_dir}/accuracy.csv, {out_dir}/large_calibration.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
