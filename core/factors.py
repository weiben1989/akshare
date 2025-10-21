"""Factor and trend utilities for the daily review engine."""
from __future__ import annotations

from typing import Dict, Iterable, Mapping, MutableMapping, Optional, Sequence

import numpy as np
import pandas as pd


def compute_multi_horizon(series: pd.Series, windows: Sequence[int]) -> Dict[int, Dict[str, Optional[float]]]:
    """Compute EMA, linear regression slope and z-score for multiple horizons."""
    if series is None or series.empty:
        return {int(window): {"ema": None, "slope": None, "z": None, "latest": None} for window in windows}
    series = series.dropna()
    series = series.sort_index()
    results: Dict[int, Dict[str, Optional[float]]] = {}
    for window in windows:
        span = max(int(window), 1)
        lookback = max(span, 10)
        window_series = series.iloc[-lookback:]
        if window_series.empty:
            results[int(window)] = {"ema": None, "slope": None, "z": None, "latest": None}
            continue
        ema = float(window_series.ewm(span=span, adjust=False).mean().iloc[-1])
        slope = _regression_slope(window_series)
        z_score = _rolling_z(window_series)
        latest_value = float(window_series.iloc[-1]) if not window_series.empty else None
        results[int(window)] = {
            "ema": ema,
            "slope": slope,
            "z": z_score,
            "latest": latest_value,
        }
    return results


def trend_label(trends: Mapping[int, Mapping[str, Optional[float]]], *, threshold: float = 0.0003) -> str:
    """Generate qualitative labels from multi-horizon trend metrics."""
    if not trends:
        return "数据不足"
    sorted_windows = sorted(trends.keys())
    slope_view = {window: trends[window].get("slope") for window in sorted_windows}
    if all(value is None for value in slope_view.values()):
        return "数据不足"
    classification = {window: _classify_slope(value, threshold) for window, value in slope_view.items()}
    short = classification.get(sorted_windows[0], 0)
    medium = classification.get(sorted_windows[len(sorted_windows) // 2], 0)
    long = classification.get(sorted_windows[-1], 0)

    if all(value == 1 for value in classification.values() if value is not None):
        return "多周期共振上行"
    if short == 1 and medium == 1 and long >= 0:
        return "短中上行、长未修复"
    if short == 1 and medium <= 0 and long < 0:
        return "短修复、长偏弱"
    if all(value == -1 for value in classification.values() if value is not None):
        return "多周期共振走弱"
    return "分化震荡"


def _regression_slope(window_series: pd.Series) -> Optional[float]:
    cleaned = window_series.dropna()
    if cleaned.size < 2:
        return None
    values = cleaned.values.astype(float)
    baseline = values[0]
    if baseline == 0:
        baseline = np.mean(values) or 1.0
    norm_values = values / baseline
    x = np.arange(norm_values.size, dtype=float)
    slope = float(np.polyfit(x, norm_values, 1)[0])
    return slope


def _rolling_z(window_series: pd.Series) -> Optional[float]:
    if window_series.empty:
        return None
    values = window_series.dropna().values.astype(float)
    if values.size < 2:
        return None
    mean_val = float(np.mean(values))
    std_val = float(np.std(values))
    if std_val == 0:
        return None
    latest = float(values[-1])
    return (latest - mean_val) / std_val


def _classify_slope(value: Optional[float], threshold: float) -> int:
    if value is None:
        return 0
    if value > threshold:
        return 1
    if value < -threshold:
        return -1
    return 0


__all__ = ["compute_multi_horizon", "trend_label"]
