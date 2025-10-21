"""资产配置策略的通用工具。"""

from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Dict, Optional, Callable, Tuple

from data.storage import DataCacheManager
from data.fetcher.akshare_api import AKShareAPI


class BaseAllocationStrategy:
    """为资产配置策略提供公共的工具方法。"""

    def __init__(self, data_api: AKShareAPI, cache_manager: Optional[DataCacheManager] = None) -> None:
        self.data_api = data_api
        self.cache_manager = cache_manager

    # ------------------------------------------------------------------
    # 数据加载
    # ------------------------------------------------------------------
    def _get_strategy_dataframe(self, key: str, loader: Optional[Callable[[], pd.DataFrame]] = None) -> pd.DataFrame:
        df = pd.DataFrame()
        if self.cache_manager:
            df = self.cache_manager.get_dataframe('strategy_data', key)

        if (df is None or df.empty) and loader:
            df = loader()
            if self.cache_manager and isinstance(df, pd.DataFrame) and not df.empty:
                data = self.cache_manager.load_dataset('strategy_data') or {}
                data[key] = df
                self.cache_manager.save_dataset('strategy_data', data)

        if df is None:
            df = pd.DataFrame()

        return df

    def _prepare_price_series(self, df: pd.DataFrame, candidates: Tuple[str, ...]) -> pd.Series:
        if df is None or df.empty:
            return pd.Series(dtype=float)

        for column in ('日期', 'date', '交易日'):
            if column in df.columns:
                df[column] = pd.to_datetime(df[column], errors='coerce')
                df = df.sort_values(column)
                df = df.set_index(column)
                break

        for column in candidates:
            if column in df.columns:
                series = pd.to_numeric(df[column], errors='coerce')
                series = series.dropna()
                if not series.empty:
                    return series

        return pd.Series(dtype=float)

    def _prepare_yield_series(self, df: pd.DataFrame, column: str) -> pd.Series:
        if df is None or df.empty or column not in df.columns:
            return pd.Series(dtype=float)

        if '日期' in df.columns:
            df['日期'] = pd.to_datetime(df['日期'], errors='coerce')
            df = df.sort_values('日期').set_index('日期')

        series = pd.to_numeric(df[column], errors='coerce').dropna()
        return series

    # ------------------------------------------------------------------
    # 指标计算
    # ------------------------------------------------------------------
    def _compute_asset_metrics(self, price_series: pd.Series) -> Tuple[Dict[str, Optional[float]], pd.Series]:
        if price_series is None or price_series.empty:
            return {
                'annual_return': None,
                'annual_volatility': None,
                'max_drawdown': None,
                'data_points': 0,
                'latest': None
            }, pd.Series(dtype=float)

        returns = price_series.pct_change().dropna()
        if returns.empty:
            return {
                'annual_return': None,
                'annual_volatility': None,
                'max_drawdown': None,
                'data_points': len(price_series),
                'latest': float(price_series.iloc[-1])
            }, pd.Series(dtype=float)

        annual_return = (1 + returns.mean()) ** 252 - 1
        annual_volatility = returns.std() * np.sqrt(252)
        cumulative = (1 + returns).cumprod()
        max_drawdown = (cumulative / cumulative.cummax() - 1).min()

        metrics = {
            'annual_return': float(annual_return),
            'annual_volatility': float(annual_volatility),
            'max_drawdown': float(max_drawdown),
            'data_points': int(len(price_series)),
            'latest': float(price_series.iloc[-1])
        }

        return metrics, returns

    def _combine_portfolio_metrics(self, weights: Dict[str, float], returns_map: Dict[str, pd.Series]) -> Dict[str, Optional[float]]:
        aligned_returns = {
            asset: series for asset, series in returns_map.items() if not series.empty and weights.get(asset)
        }

        if not aligned_returns:
            return {
                'annual_return': None,
                'annual_volatility': None,
                'max_drawdown': None
            }

        returns_df = pd.DataFrame(aligned_returns).dropna()
        if returns_df.empty:
            return {
                'annual_return': None,
                'annual_volatility': None,
                'max_drawdown': None
            }

        weight_vector = np.array([weights[col] for col in returns_df.columns])
        mean_returns = returns_df.mean().values
        cov_matrix = returns_df.cov().values * 252

        portfolio_return = float(np.dot(mean_returns, weight_vector) * 252)
        portfolio_volatility = float(np.sqrt(np.dot(weight_vector, np.dot(cov_matrix, weight_vector))))

        daily_weighted = returns_df.mul(weight_vector, axis=1).sum(axis=1)
        cumulative = (1 + daily_weighted).cumprod()
        max_drawdown = float((cumulative / cumulative.cummax() - 1).min())

        return {
            'annual_return': portfolio_return,
            'annual_volatility': portfolio_volatility,
            'max_drawdown': max_drawdown
        }

    def _approximate_bond_index(self, yield_series: pd.Series, duration: float = 10.0) -> pd.Series:
        if yield_series is None or yield_series.empty:
            return pd.Series(dtype=float)

        yields = yield_series.sort_index() / 100.0
        delta = yields.diff().dropna()
        if delta.empty:
            return pd.Series(dtype=float)

        returns = -duration * delta
        price = (1 + returns).cumprod() * 100
        price.index = delta.index
        return price
