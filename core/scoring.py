"""Scoring utilities for the daily review engine."""
from __future__ import annotations

from typing import Dict, Mapping, Optional, Tuple

import numpy as np
import pandas as pd


def score_liquidity(
    *,
    market_amount: Mapping[int, Mapping[str, Optional[float]]],
    northbound: Mapping[int, Mapping[str, Optional[float]]],
    margin: Mapping[int, Mapping[str, Optional[float]]],
    etf_trends: Mapping[str, Mapping[int, Mapping[str, Optional[float]]]],
) -> Tuple[float, Dict[str, float]]:
    """Compute the liquidity score from multi-horizon trends."""
    components: Dict[str, Optional[float]] = {}
    components["market_amount"] = _trend_strength(market_amount)
    components["northbound"] = _trend_strength(northbound)
    components["margin"] = _trend_strength(margin)
    etf_scores = [_trend_strength(value) for value in etf_trends.values()]
    etf_scores = [score for score in etf_scores if score is not None]
    if etf_scores:
        components["etf"] = float(np.mean(etf_scores))
    values = [value for value in components.values() if value is not None]
    score = float(np.mean(values)) if values else 0.0
    return _clip_score(score), {key: _clip_score(value) if value is not None else 0.0 for key, value in components.items()}


def score_riskon(
    current: Mapping[str, float],
    history: pd.DataFrame,
) -> Tuple[float, Dict[str, float]]:
    """Assess risk-on appetite based on breadth metrics."""
    metrics: Dict[str, Optional[float]] = {}
    if history is None or history.empty:
        return 0.0, {"limit_up": 0.0, "limit_ratio": 0.0, "sustainability": 0.0}
    history_sorted = history.sort_values("date")
    history_sorted["date"] = pd.to_datetime(history_sorted["date"])

    def _hist_z(column: str, value: float, invert: bool = False) -> Optional[float]:
        series = pd.to_numeric(history_sorted[column], errors="coerce").dropna()
        if series.empty:
            return None
        mean_val = series.rolling(window=30, min_periods=10).mean().iloc[-1]
        std_val = series.rolling(window=30, min_periods=10).std().iloc[-1]
        if pd.isna(mean_val) or pd.isna(std_val) or std_val == 0:
            return None
        raw = (value - mean_val) / std_val
        return -raw if invert else raw

    limit_up = current.get("limit_up_count", 0.0)
    limit_down = current.get("limit_down_count", 0.0)
    max_chain = current.get("max_limit_up_streak", 0.0)
    sustain = current.get("limit_up_sustainability", 0.0)

    metrics["limit_up"] = _tanh_scale(_hist_z("limit_up_count", limit_up))
    metrics["limit_down"] = _tanh_scale(_hist_z("limit_down_count", limit_down, invert=True))
    ratio_series = (
        (pd.to_numeric(history_sorted["limit_up_count"], errors="coerce") + 1)
        /
        (pd.to_numeric(history_sorted["limit_down_count"], errors="coerce") + 1)
    )
    ratio_series = ratio_series.replace([np.inf, -np.inf], np.nan).dropna()
    ratio_z = None
    if not ratio_series.empty:
        mean_ratio = ratio_series.rolling(window=30, min_periods=10).mean().iloc[-1]
        std_ratio = ratio_series.rolling(window=30, min_periods=10).std().iloc[-1]
        if pd.notna(mean_ratio) and pd.notna(std_ratio) and std_ratio != 0:
            ratio_z = ( (limit_up + 1) / (limit_down + 1) - mean_ratio) / std_ratio
    metrics["limit_ratio"] = _tanh_scale(ratio_z)
    metrics["chain"] = _tanh_scale(_hist_z("max_limit_up_streak", max_chain))
    metrics["sustainability"] = _tanh_scale(_hist_z("limit_up_sustainability", sustain))

    values = [value for value in metrics.values() if value is not None]
    score = float(np.mean(values)) if values else 0.0
    return _clip_score(score), {key: _clip_score(value) if value is not None else 0.0 for key, value in metrics.items()}


def score_momentum(
    *,
    index_trend: Mapping[int, Mapping[str, Optional[float]]],
    amount_trend: Mapping[int, Mapping[str, Optional[float]]],
) -> Tuple[float, Dict[str, float]]:
    """Score short-to-long momentum combining price and volume trends."""
    index_strength = _trend_strength(index_trend)
    amount_strength = _trend_strength(amount_trend)
    components = {"index": index_strength, "amount": amount_strength}
    values = [value for value in components.values() if value is not None]
    score = float(np.mean(values)) if values else 0.0
    return _clip_score(score), {key: _clip_score(value) if value is not None else 0.0 for key, value in components.items()}


def score_macro(latest_values: Mapping[str, float]) -> Tuple[float, Dict[str, float]]:
    """Compute the macro score based on PMI, PPI and commodity proxies."""
    new_orders = latest_values.get("PMI_NEW_ORDERS")
    inventory = latest_values.get("PMI_FINISHED_GOODS")
    ppi = latest_values.get("PPI_YOY")
    commodity = latest_values.get("COMMODITY_INDEX")

    quadrant_score = 50.0
    if new_orders is not None and inventory is not None:
        if new_orders >= 50 and inventory < 50:
            quadrant_score = 70.0
        elif new_orders >= 50 and inventory >= 50:
            quadrant_score = 60.0
        elif new_orders < 50 and inventory >= 50:
            quadrant_score = 40.0
        else:
            quadrant_score = 45.0
    adjustments = []
    if ppi is not None:
        adjustments.append(_tanh_scale((ppi - 0) / 5.0, scale=1.5) - 50)
    if commodity is not None:
        adjustments.append(_tanh_scale((commodity - 100) / 20.0, scale=1.5) - 50)
    if adjustments:
        quadrant_score += float(np.mean(adjustments))
    return _clip_score(quadrant_score), {
        "pmi": _clip_score(quadrant_score),
        "ppi": _clip_score(adjustments[0] + 50 if adjustments else 50),
        "commodity": _clip_score(adjustments[1] + 50 if len(adjustments) > 1 else 50),
    }


def _trend_strength(trend: Mapping[int, Mapping[str, Optional[float]]]) -> Optional[float]:
    if not trend:
        return None
    slopes = []
    biases = []
    zscores = []
    for metrics in trend.values():
        slope = metrics.get("slope")
        z = metrics.get("z")
        latest = metrics.get("latest")
        ema = metrics.get("ema")
        if slope is not None:
            slopes.append(slope * 100)
        if z is not None:
            zscores.append(z)
        if latest is not None and ema not in (None, 0):
            biases.append((latest - ema) / abs(ema))
    components = []
    if slopes:
        components.append(_tanh_scale(np.mean(slopes), scale=1.5))
    if zscores:
        components.append(_tanh_scale(np.mean(zscores), scale=1.5))
    if biases:
        components.append(_tanh_scale(np.mean(biases), scale=1.0))
    if not components:
        return None
    return float(np.mean(components))


def _tanh_scale(value: Optional[float], scale: float = 1.0) -> Optional[float]:
    if value is None or np.isnan(value):
        return None
    return 50.0 + 50.0 * np.tanh(value / scale)


def _clip_score(value: Optional[float]) -> float:
    if value is None or np.isnan(value):
        return 0.0
    return float(min(100.0, max(0.0, value)))


__all__ = [
    "score_liquidity",
    "score_riskon",
    "score_momentum",
    "score_macro",
]
