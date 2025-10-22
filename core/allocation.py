"""Portfolio allocation helpers for the daily review engine."""
from __future__ import annotations

from typing import Dict, Iterable, List, Mapping
import pandas as pd


QUADRANT_LABELS = {
    ("high", "low"): "首选",
    ("high", "high"): "追高风险",
    ("low", "low"): "潜伏",
    ("low", "high"): "回避",
}


def rotation_map(industry_df: pd.DataFrame) -> pd.DataFrame:
    """Create the industry rotation matrix with strength and crowding measures."""
    if industry_df is None or industry_df.empty:
        return pd.DataFrame(
            columns=[
                "industry",
                "strength",
                "crowding",
                "strength_rank",
                "crowding_rank",
                "quadrant",
            ]
        )
    df = industry_df.copy()
    df = df.dropna(subset=["industry"]).reset_index(drop=True)
    df["avg_return"] = pd.to_numeric(df.get("avg_return"), errors="coerce")
    df["net_inflow"] = pd.to_numeric(df.get("net_inflow"), errors="coerce")
    df["turnover"] = pd.to_numeric(df.get("turnover"), errors="coerce")
    df["limit_up_count"] = pd.to_numeric(df.get("limit_up_count"), errors="coerce")

    df["return_rank"] = df["avg_return"].rank(pct=True, method="min")
    df["flow_rank"] = df["net_inflow"].rank(pct=True, method="min")
    df["turnover_rank"] = df["turnover"].rank(pct=True, method="min")
    df["limit_rank"] = df["limit_up_count"].rank(pct=True, method="min")

    df["strength"] = 0.6 * df["return_rank"] + 0.4 * df["flow_rank"]
    df["crowding"] = 0.6 * df["turnover_rank"].fillna(0.5) + 0.4 * df["limit_rank"].fillna(0.5)
    df["strength_rank"] = df["strength"].rank(pct=True, method="first")
    df["crowding_rank"] = df["crowding"].rank(pct=True, method="first")

    def classify(strength_value: float, crowding_value: float) -> str:
        strength_bucket = "high" if strength_value >= 0.6 else "low"
        crowding_bucket = "high" if crowding_value >= 0.7 else "low"
        return QUADRANT_LABELS[(strength_bucket, crowding_bucket)]

    df["quadrant"] = [classify(strength, crowding) for strength, crowding in zip(df["strength"], df["crowding"])]
    df.sort_values("strength", ascending=False, inplace=True)
    return df


def decide_allocation(total_score: float, rules: Iterable[Mapping[str, object]]) -> Dict[str, object]:
    """Map total score to position and style based on configuration rules."""
    for rule in rules:
        lower = float(rule.get("min", 0))
        upper = float(rule.get("max", 100))
        if lower <= total_score < upper:
            return {
                "position": int(rule.get("position", 50)),
                "style": rule.get("style", "均衡"),
                "label": rule.get("label", ""),
            }
    return {"position": 50, "style": "均衡", "label": "默认"}


def pick_industries(rotation_df: pd.DataFrame) -> Dict[str, List[str]]:
    """Select overweight/neutral/underweight industries from rotation matrix."""
    if rotation_df is None or rotation_df.empty:
        return {"overweight": [], "neutral": [], "underweight": [], "note": "数据不足导致兜底"}
    preferred = rotation_df[(rotation_df["quadrant"] == "首选") & (rotation_df["crowding"] < 0.7)]
    preferred = preferred.sort_values("strength", ascending=False)
    overweight = preferred["industry"].head(3).tolist()

    avoid = rotation_df[rotation_df["quadrant"] == "回避"].sort_values("crowding", ascending=False)
    underweight = avoid["industry"].head(3).tolist()

    neutral = [industry for industry in rotation_df["industry"] if industry not in overweight + underweight]
    return {"overweight": overweight, "neutral": neutral, "underweight": underweight}


__all__ = ["rotation_map", "decide_allocation", "pick_industries"]
