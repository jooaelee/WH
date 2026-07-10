"""Turn a tuned model into the deliverables: 4-week forecasts, large-shipment
probabilities, and routine (small-volume) expectations for a single series.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import numpy as np

from .config import Config
from .models import build_model
from .models.intermittent import TSB


@dataclass
class SeriesForecast:
    weekly: np.ndarray          # expected demand per future week (length h)
    total: float                # cumulative expected demand over the horizon
    p_occurrence: float         # per-week probability of any shipment
    # Large / small decomposition ------------------------------------------
    large_threshold: float      # weekly qty at/above which a week is "대량"
    p_large_week: float         # smoothed per-week probability of a large week
    p_large_horizon: float      # probability of >=1 large shipment within h weeks
    expected_large_size: float  # expected qty of a large shipment
    routine_weekly: float       # expected routine (small) weekly qty
    routine_total: float        # routine expectation over the horizon
    last_large_week: Optional[object] = None


def _bernoulli_rate(binary: np.ndarray, alpha: float = 0.2) -> float:
    """Smoothed probability that next week is a '1', via the TSB probability
    recursion (robust for sparse events)."""
    if binary.sum() == 0:
        return 0.0
    res = TSB(alpha=alpha, beta=alpha).fit(binary.astype(float)).forecast(1)
    return float(np.clip(res.p_occurrence, 0.0, 1.0))


def forecast_series(y: np.ndarray, model_name: str, params: dict,
                    cfg: Config, week_index=None) -> SeriesForecast:
    """Fit the chosen model on the full history and produce all outputs."""
    y = np.asarray(y, float)
    h = cfg.horizon_weeks
    model = build_model(model_name, params).fit(y)
    res = model.forecast(h)
    weekly = np.clip(res.mean, 0.0, None)

    nz = y[y > 0]
    if nz.size:
        large_thr = float(np.quantile(nz, cfg.large_quantile))
    else:
        large_thr = 0.0
    # A large week: qty at/above the per-series large threshold.
    large_mask = y >= max(large_thr, 1e-9)
    p_large_week = _bernoulli_rate(large_mask.astype(float))
    p_large_h = 1.0 - (1.0 - p_large_week) ** h
    large_sizes = y[y >= max(large_thr, 1e-9)]
    exp_large = float(large_sizes.mean()) if large_sizes.size else 0.0

    # Routine (small) demand: cap spikes at the large threshold, then take the
    # chosen model's expected weekly level so it reflects baseline volume.
    capped = np.minimum(y, large_thr) if large_thr > 0 else y
    routine_model = build_model(model_name, params).fit(capped)
    routine_weekly = float(np.clip(routine_model.forecast(1).mean[0], 0.0, None))

    last_large = None
    if week_index is not None:
        idx = np.flatnonzero(large_mask)
        if idx.size:
            last_large = week_index[idx[-1]]

    return SeriesForecast(
        weekly=weekly,
        total=float(weekly.sum()),
        p_occurrence=float(np.clip(res.p_occurrence, 0.0, 1.0)),
        large_threshold=large_thr,
        p_large_week=p_large_week,
        p_large_horizon=float(p_large_h),
        expected_large_size=exp_large,
        routine_weekly=routine_weekly,
        routine_total=routine_weekly * h,
        last_large_week=last_large,
    )
