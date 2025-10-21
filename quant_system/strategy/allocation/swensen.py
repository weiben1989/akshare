"""斯文森资产配置策略实现。"""

from __future__ import annotations

import pandas as pd
from typing import Dict, Optional

from .base import BaseAllocationStrategy
from data.fetcher.akshare_api import AKShareAPI
from data.storage import DataCacheManager


class SwensenPortfolioStrategy(BaseAllocationStrategy):
    """耶鲁大学捐赠基金（Swensen）资产配置模型。"""

    def __init__(self, data_api: AKShareAPI, cache_manager: Optional[DataCacheManager] = None) -> None:
        super().__init__(data_api, cache_manager)
        self.weights = {
            'A股权益': 0.30,
            '美国股票': 0.20,
            '新兴市场': 0.05,
            '全球REITs': 0.20,
            '长期国债': 0.15,
            '抗通胀债券': 0.10
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
            'name': '斯文森捐赠组合',
            'weights': self.weights,
            'assets': asset_metrics,
            'portfolio': portfolio_metrics,
            'rebalance': '每年',
            'notes': [
                '权益资产通过沪深300与标普500等指数代理',
                '债券部分采用国债指数与美债收益率估算，实际操作可替换为债券ETF',
                '建议至少使用3年以上历史数据评估长期收益' 
            ]
        }

    # ------------------------------------------------------------------
    # 数据加载
    # ------------------------------------------------------------------
    def _load_asset_series(self) -> Dict[str, pd.Series]:
        return {
            'A股权益': self._load_domestic_index('000300', 'hs300'),
            '美国股票': self._load_global_index('标普500', 'sp500'),
            '新兴市场': self._load_global_index('巴西BOVESPA', 'bovespa'),
            '全球REITs': self._load_global_index('富时新加坡海峡时报', 'sti'),
            '长期国债': self._load_domestic_index('000012', 'cn_bond'),
            '抗通胀债券': self._load_tips_proxy()
        }

    def _load_domestic_index(self, symbol: str, cache_key: str) -> pd.Series:
        df = self._get_strategy_dataframe(cache_key, loader=lambda: self.data_api.get_index_zh_a_hist(symbol=symbol))
        return self._prepare_price_series(df, ('收盘', 'close', '收盘价'))

    def _load_global_index(self, symbol: str, cache_key: str) -> pd.Series:
        df = self._get_strategy_dataframe(cache_key, loader=lambda: self.data_api.get_index_global_hist(symbol=symbol))
        return self._prepare_price_series(df, ('最新价', '收盘', 'close'))

    def _load_tips_proxy(self) -> pd.Series:
        df = self._get_strategy_dataframe('us_yield', loader=lambda: self.data_api.get_us_treasury_yield())
        yield_series = self._prepare_yield_series(df, '美国国债收益率10年')
        if yield_series.empty:
            return pd.Series(dtype=float)
        return self._approximate_bond_index(yield_series, duration=8.0)
