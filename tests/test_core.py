"""Sanity tests for the forecasting core: model correctness, metrics, tuning.

Run: ``python -m pytest tests/ -q``  (or ``python tests/test_core.py``).
"""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from demand_forecast.models.intermittent import Croston, SBA, TSB, _croston_smooth
from demand_forecast.models.timeseries import SES, MovingAverage
from demand_forecast.backtest import rolling_backtest, _naive_scale
from demand_forecast.classification import _adi_cv2, _sb_class
from demand_forecast.config import Config


def test_croston_constant_interval():
    # Demand of 10 every 3rd week -> rate should approach 10/3.
    y = np.zeros(30)
    y[::3] = 10.0
    z, p = _croston_smooth(y, alpha=0.2)
    rate = z / p
    assert 2.5 < rate < 4.0, rate


def test_sba_below_croston():
    y = np.zeros(40); y[::4] = np.array([5, 7, 6, 8, 5, 9, 4, 6, 7, 5], float)
    cr = Croston(alpha=0.2).fit(y).forecast(4).mean[0]
    sba = SBA(alpha=0.2).fit(y).forecast(4).mean[0]
    assert sba < cr  # bias correction shrinks the estimate


def test_tsb_probability_bounds():
    y = np.zeros(50); y[::5] = 3.0
    res = TSB(alpha=0.1, beta=0.1).fit(y).forecast(4)
    assert 0.0 <= res.p_occurrence <= 1.0
    assert res.mean[0] >= 0.0


def test_zero_series_is_safe():
    y = np.zeros(20)
    for m in (Croston(alpha=0.1), SBA(alpha=0.1), TSB(alpha=0.1, beta=0.1),
              SES(), MovingAverage(window=4)):
        res = m.fit(y).forecast(4)
        assert np.all(res.mean == 0.0)
        assert 0.0 <= res.p_occurrence <= 1.0


def test_naive_scale_positive():
    assert _naive_scale(np.array([1.0, 1.0, 1.0])) == 1.0  # zero-var -> 1.0 guard
    assert _naive_scale(np.array([0.0, 5.0, 0.0, 5.0])) > 0


def test_backtest_runs():
    rng = np.random.default_rng(0)
    y = rng.poisson(2, size=60).astype(float)
    score = rolling_backtest(lambda: SBA(alpha=0.1), y, h=4, folds=6, min_train=20)
    assert score.n_folds > 0
    assert np.isfinite(score.rmsse)


def test_classification_labels():
    cfg = Config()
    # Regular weekly demand -> smooth / low ADI.
    y = np.full(52, 5.0)
    adi, cv2, n = _adi_cv2(y)
    assert adi < cfg.adi_cut
    assert _sb_class(adi, cv2, cfg) == "smooth"
    # Sparse -> intermittent quadrant.
    y2 = np.zeros(52); y2[::10] = 4.0
    adi2, cv2_2, _ = _adi_cv2(y2)
    assert adi2 >= cfg.adi_cut


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed")
