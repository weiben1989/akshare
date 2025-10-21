#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""缓存真实数据自检工具。

通过检查 ``data/cache/*.pkl``，确认系统将使用真实的宏观与市场数据。
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd

# 将项目根目录加入 sys.path，便于脚本直接运行
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.storage import DataCacheManager  # noqa: E402


@dataclass
class CheckRule:
    """单个数据表的校验规则。"""

    min_rows: int = 1
    require_date: bool = True
    note: Optional[str] = None


REQUIRED_DATASETS: Dict[str, Dict[str, CheckRule]] = {
    "macro_data": {
        "gdp": CheckRule(min_rows=8, note="用于需求增速判断"),
        "ppi": CheckRule(min_rows=12, note="用于价格趋势"),
        "pmi": CheckRule(min_rows=12, note="用于库存与需求判断"),
        "social_financing": CheckRule(min_rows=12, note="用于信用周期"),
    },
    "market_data": {
        "hs300": CheckRule(min_rows=240, note="沪深300指数收盘价"),
        "sh000001": CheckRule(min_rows=240, note="上证指数"),
    },
    "fund_data": {
        "north_flow": CheckRule(min_rows=60, note="北向资金"),
    },
}

DATE_CANDIDATES: Tuple[str, ...] = (
    "日期",
    "date",
    "Date",
    "DATETIME",
    "月份",
    "季度",
    "period",
    "TRADE_DATE",
    "交易日",
    "统计期",
)


def _find_date_series(df: pd.DataFrame) -> Optional[pd.Series]:
    for column in DATE_CANDIDATES:
        if column in df.columns:
            series = pd.to_datetime(df[column], errors="coerce")
            if series.notna().sum():
                return series
    return None


def _describe_dataframe(df: pd.DataFrame) -> Dict[str, str]:
    """返回便于展示的关键信息。"""

    info: Dict[str, str] = {"rows": str(len(df))}

    date_series = _find_date_series(df)
    if date_series is not None and date_series.notna().any():
        info["period"] = f"{date_series.min().date()} → {date_series.max().date()}"

    numeric = df.select_dtypes(include="number")
    if not numeric.empty:
        latest_row = numeric.tail(1).iloc[0].dropna()
        if not latest_row.empty:
            info["latest_fields"] = ", ".join(
                f"{col}={latest_row[col]:.2f}" for col in latest_row.index[:3]
            )
    return info


def _format_info(info: Dict[str, str]) -> str:
    parts = [f"{k}: {v}" for k, v in info.items()]
    return "; ".join(parts)


def _print_header() -> None:
    print("\n🔍 真实数据自检 (check_real_data.py)")
    print("=" * 60)


def _print_footer(passed: bool) -> None:
    print("=" * 60)
    if passed:
        print("✅ 已检测到关键缓存数据，系统会使用真实数据进行分析。")
    else:
        print(
            "⚠️  上述表格缺失或为空。请先运行 `python scripts/download_data.py` "
            "补齐数据；若曾使用旧版模拟数据，请删除 data/cache/*.pkl 后重试。"
        )
    print()


def _check_dataset(
    dataset: str,
    rules: Dict[str, CheckRule],
    cache_manager: DataCacheManager,
) -> bool:
    data = cache_manager.load_dataset(dataset)
    ok = True

    if not isinstance(data, dict):
        print(f"✗ {dataset}: 未找到缓存文件或格式不正确")
        return False

    print(f"\n📁 数据集: {dataset}")

    for key, rule in rules.items():
        df = data.get(key)
        if not isinstance(df, pd.DataFrame) or df.empty:
            print(f"  ✗ {key}: 未找到数据表，请重新下载 ({rule.note or '缺少数据'})")
            ok = False
            continue

        if len(df) < rule.min_rows:
            print(
                f"  ✗ {key}: 行数仅 {len(df)} 行，少于建议的 {rule.min_rows} 行"
                "，请重新下载"
            )
            ok = False
            continue

        if rule.require_date and _find_date_series(df) is None:
            print(
                f"  ✗ {key}: 未检测到日期列，疑似为旧版模拟数据，请清理缓存后重新下载"
            )
            ok = False
            continue

        info = _describe_dataframe(df)
        note = f" ({rule.note})" if rule.note else ""
        print(f"  ✓ {key}{note} -> {_format_info(info)}")

    return ok


def run_checks() -> bool:
    cache_manager = DataCacheManager()
    results: List[bool] = []

    for dataset, rules in REQUIRED_DATASETS.items():
        results.append(_check_dataset(dataset, rules, cache_manager))

    return all(results)


def main() -> None:
    _print_header()
    passed = run_checks()
    _print_footer(passed)


if __name__ == "__main__":
    main()
