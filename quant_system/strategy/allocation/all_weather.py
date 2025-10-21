"""全天候资产配置策略实现。"""

from __future__ import annotations

import pandas as pd
from typing import Dict, Optional

from .base import BaseAllocationStrategy
from data.fetcher.akshare_api import AKShareAPI
from data.storage import DataCacheManager


class AllWeatherPortfolioStrategy(BaseAllocationStrategy):
    """基于瑞·达里奥全天候理念的资产配置模型。"""

    def __init__(self, data_api: AKShareAPI, cache_manager: Optional[DataCacheManager] = None) -> None:
        super().__init__(data_api, cache_manager)
        self.weights = {
            '股票资产': 0.30,
            '长期国债': 0.40,
            '中期国债': 0.15,
            '商品指数': 0.075,
            '防御资产': 0.075
        }

    def generate_portfolio(self) -> Dict:
        assets = self._load_asset_series()
        asset_metrics: Dict[str, Dict] = {}
        returns_map: Dict[str, pd.Series] = {}

        for asset, series in assets.items():
            metrics, returns = self._compute_asset_metrics(series)
            metrics['weight'] = self.weights.get(asset)
            asset_metrics[asset] = metrics
            returns_map[asset] = returns

        portfolio_metrics = self._combine_portfolio_metrics(self.weights, returns_map)

        return {
            'name': '全天候资产配置',
            'weights': self.weights,
            'assets': asset_metrics,
            'portfolio': portfolio_metrics,
            'rebalance': '半年',
            'notes': [
                '长期与中期国债收益率通过收益率曲线估算，建议实际使用相应ETF替代',
                '商品板块采用CRB指数代理，可替换为包含能源与金属的商品基金',
                '防御资产使用美元指数近似，实盘可使用黄金或现金等价物' 
            ]
        }

    # ------------------------------------------------------------------
    # 数据加载
    # ------------------------------------------------------------------
    def _load_asset_series(self) -> Dict[str, pd.Series]:
        return {
            '股票资产': self._load_domestic_index('000300', 'hs300'),
            '长期国债': self._load_domestic_index('000012', 'cn_bond'),
            '中期国债': self._load_us_yield_proxy('美国国债收益率5年', 'us_yield_5y', duration=5.0),
            '商品指数': self._load_global_index('路透CRB商品指数', 'crb'),
            '防御资产': self._load_global_index('美元指数', 'dxy')
        }

    def _load_domestic_index(self, symbol: str, cache_key: str) -> pd.Series:
        df = self._get_strategy_dataframe(cache_key, loader=lambda: self.data_api.get_index_zh_a_hist(symbol=symbol))
        return self._prepare_price_series(df, ('收盘', 'close', '收盘价'))

    def _load_global_index(self, symbol: str, cache_key: str) -> pd.Series:
        df = self._get_strategy_dataframe(cache_key, loader=lambda: self.data_api.get_index_global_hist(symbol=symbol))
        return self._prepare_price_series(df, ('最新价', '收盘', 'close'))

    def _load_us_yield_proxy(self, column: str, cache_key: str, duration: float) -> pd.Series:
        df = self._get_strategy_dataframe(cache_key, loader=lambda: self.data_api.get_us_treasury_yield())
        yield_series = self._prepare_yield_series(df, column)
        if yield_series.empty:
            return pd.Series(dtype=float)
        return self._approximate_bond_index(yield_series, duration=duration)
