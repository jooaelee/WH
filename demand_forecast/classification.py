"""SKU characteristic analysis, labelling, and forecast-target selection.

For every weekly demand series we compute the Syntetos-Boylan descriptors and
assign one of two operating labels:

* **교체형 (intermittent / replacement)** — sporadic orders; forecast with the
  Croston family.
* **지속형 (continuous)** — regular, recently-active demand; forecast with a
  time-series model.

We also mark the *forecast targets*: the volume drivers (top X% by total volume)
that have enough history to model. Everything is returned as a tidy DataFrame.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Config


def _adi_cv2(y: np.ndarray):
    """Average demand interval and squared CV of non-zero demand (weekly)."""
    nz = np.flatnonzero(y > 0)
    n_active = nz.size
    if n_active == 0:
        return np.inf, 0.0, 0
    # ADI over the observed span (first demand -> last demand).
    span = (nz[-1] - nz[0]) + 1
    adi = span / n_active
    sizes = y[nz]
    mean = sizes.mean()
    cv2 = float((sizes.std() / mean) ** 2) if mean > 0 and n_active > 1 else 0.0
    return float(adi), cv2, int(n_active)


def _sb_class(adi: float, cv2: float, cfg: Config) -> str:
    """Fine-grained Syntetos-Boylan quadrant (for diagnostics)."""
    if adi >= cfg.adi_cut and cv2 < cfg.cv2_cut:
        return "intermittent"
    if adi >= cfg.adi_cut and cv2 >= cfg.cv2_cut:
        return "lumpy"
    if adi < cfg.adi_cut and cv2 >= cfg.cv2_cut:
        return "erratic"
    return "smooth"


def classify_series(series: dict, week_index, cfg: Config) -> pd.DataFrame:
    """Describe & label each series in ``series`` (mapping key -> weekly vector)."""
    n_weeks = len(week_index)
    recent = min(cfg.recent_window_weeks, n_weeks)
    rows = []
    for key, y in series.items():
        y = np.asarray(y, float)
        adi, cv2, n_active = _adi_cv2(y)
        sb = _sb_class(adi, cv2, cfg)
        recent_active = float((y[-recent:] > 0).mean()) if recent else 0.0
        total = float(y.sum())
        # Operating label: 지속형 only if regular AND still active recently.
        is_continuous = (
            adi < cfg.adi_cut
            and recent_active >= cfg.continuous_recent_activity
            and n_active >= cfg.min_active_weeks
        )
        label = "지속형" if is_continuous else "교체형"
        rows.append({
            "key": key,
            "total_qty": total,
            "n_active_weeks": n_active,
            "recent_active_ratio": round(recent_active, 3),
            "adi": round(adi, 3) if np.isfinite(adi) else np.inf,
            "cv2": round(cv2, 3),
            "sb_class": sb,
            "label": label,
            "last_ship_week": _last_ship(y, week_index),
        })
    return pd.DataFrame(rows)


def _last_ship(y, week_index):
    nz = np.flatnonzero(y > 0)
    return week_index[nz[-1]] if nz.size else pd.NaT


def select_targets(desc: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Flag which series to actually forecast.

    A target must (a) clear the volume cut (top ``1 - target_volume_quantile``)
    and (b) have enough history to model. Returns ``desc`` with a boolean
    ``is_target`` column added.
    """
    desc = desc.copy()
    if desc.empty:
        desc["is_target"] = []
        return desc
    thr = desc["total_qty"].quantile(cfg.target_volume_quantile)
    enough_history = desc["n_active_weeks"] >= cfg.min_active_weeks
    desc["volume_threshold"] = thr
    desc["is_target"] = (desc["total_qty"] >= thr) & enough_history
    return desc.sort_values("total_qty", ascending=False).reset_index(drop=True)
