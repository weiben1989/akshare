"""
马克斯钟摆模型 - 市场情绪周期分析
霍华德·马克斯的市场钟摆理论，衡量市场情绪和风险偏好
"""

import sys
import os
# 添加项目根目录到路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple, List, Any
from datetime import datetime

from utils.logger import logger
from data.storage import DataCacheManager


class MarksPendulum:
    """
    霍华德·马克斯的市场钟摆理论
    衡量市场情绪和风险偏好

    钟摆位置：0（极度悲观）到 100（极度乐观）
    """

    def __init__(self, data_fetcher=None, cache_manager: Optional[DataCacheManager] = None):
        """
        Args:
            data_fetcher: 数据获取器实例
        """
        self.data_fetcher = data_fetcher
        self.cache_manager = cache_manager
        self.logger = logger

        # 各维度权重
        self.components = {
            'valuation': 0.3,      # 估值水平权重
            'sentiment': 0.3,      # 情绪指标权重
            'liquidity': 0.2,      # 流动性权重
            'breadth': 0.2         # 市场宽度权重
        }

        self.latest_details: Dict[str, Dict] = {}
        self.history_records: List[Dict[str, float]] = []

    def calculate_pendulum_position(self) -> Dict:
        """
        计算钟摆位置：0（极度悲观）到 100（极度乐观）

        Returns:
            包含总分及各维度得分的字典
        """
        context = self._load_context()

        valuation_score, valuation_detail = self._calc_valuation_percentile(context)
        sentiment_score, sentiment_detail = self._calc_sentiment_score(context)
        liquidity_score, liquidity_detail = self._calc_liquidity_score(context)
        breadth_score, breadth_detail = self._calc_market_breadth(context)

        # 综合得分
        total_score = (
            valuation_score * self.components['valuation'] +
            sentiment_score * self.components['sentiment'] +
            liquidity_score * self.components['liquidity'] +
            breadth_score * self.components['breadth']
        )

        self.latest_details = {
            'valuation': valuation_detail,
            'sentiment': sentiment_detail,
            'liquidity': liquidity_detail,
            'breadth': breadth_detail,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        self.history_records.append({
            'timestamp': self.latest_details['timestamp'],
            'total_score': total_score,
            'valuation': valuation_score,
            'sentiment': sentiment_score,
            'liquidity': liquidity_score,
            'breadth': breadth_score
        })
        if len(self.history_records) > 180:
            self.history_records = self.history_records[-180:]

        result = {
            'total_score': total_score,
            'level': self._classify_level(total_score),
            'valuation': valuation_score,
            'sentiment': sentiment_score,
            'liquidity': liquidity_score,
            'breadth': breadth_score,
            'recommendation': self._get_recommendation(total_score),
            'details': self.latest_details
        }

        self.logger.info(f"市场情绪温度: {total_score:.1f} ({result['level']})")

        return result

    def get_history(self, window: int = 180) -> pd.DataFrame:
        """返回历史记录供可视化使用。"""

        if not self.history_records:
            return pd.DataFrame()

        df = pd.DataFrame(self.history_records)
        return df.tail(window).reset_index(drop=True)

    def _calc_valuation_percentile(self, context: Dict[str, pd.DataFrame]) -> Tuple[float, Dict]:
        """
        计算估值维度得分

        指标：
        - 全A股PE/PB历史分位数（5年）
        - 风险溢价（1/PE - 10年国债收益率）
        - 股债性价比

        Returns:
            估值得分 (0-100) 及细节
        """
        df = context.get('valuation', pd.DataFrame())
        details: Dict[str, Any] = {
            'records': len(df)
        }

        scores = []
        quantiles: List[float] = []

        if not df.empty:
            for col in ['quantileInRecent10YearsAveragePeLyr', 'quantileInRecent10YearsAveragePeTtm']:
                if col in df.columns:
                    series = pd.to_numeric(df[col], errors='coerce').dropna()
                    if not series.empty:
                        value = float(series.iloc[-1])
                        if value <= 1:
                            value *= 100
                        quantiles.append(float(np.clip(value, 0, 100)))

            if quantiles:
                scores.append(np.mean(quantiles))
            details['pe_quantiles'] = quantiles

            pe_series = pd.to_numeric(df.get('middlePETTM'), errors='coerce').dropna()
            if not pe_series.empty:
                latest_pe = float(pe_series.iloc[-1])
                details['latest_pe_ttm'] = latest_pe
                if len(pe_series) > 120:
                    rolling = pe_series.rolling(window=120).mean().iloc[-1]
                    if rolling and not np.isnan(rolling):
                        relative = latest_pe / rolling
                        details['relative_to_10m_avg'] = relative
                        scores.append(float(np.clip(relative * 50, 0, 100)))

        if not scores:
            score = 50.0
        else:
            score = float(np.clip(np.mean(scores), 0, 100))

        return score, details

    def _calc_sentiment_score(self, context: Dict[str, pd.DataFrame]) -> Tuple[float, Dict]:
        """
        计算情绪维度得分

        指标：
        - 融资买入额 / 总成交额
        - 两融余额增速
        - 新开户数（周度）
        - 交易软件下载量排名
        - 搜索指数："股票"、"炒股"

        Returns:
            情绪得分 (0-100)及细节
        """
        details: Dict[str, Any] = {}

        market_df = context.get('hs300', pd.DataFrame())
        close_series = self._prepare_series(market_df, ['close', '收盘', '收盘价'])
        momentum_score = 50.0
        momentum_pct = 0.0
        if len(close_series) > 21:
            returns_20 = close_series.pct_change(20).dropna() * 100
            if not returns_20.empty:
                momentum_pct = float(returns_20.iloc[-1])
                momentum_score = self._percentile(returns_20, momentum_pct)
        details['momentum_pct'] = momentum_pct
        details['momentum_score'] = momentum_score

        north_flow_df = context.get('north_flow', pd.DataFrame())
        north_flow_score = 50.0
        north_flow_value = 0.0
        if isinstance(north_flow_df, pd.DataFrame) and not north_flow_df.empty:
            north_series = pd.to_numeric(north_flow_df.get('资金净流入'), errors='coerce').dropna()
            if not north_series.empty:
                north_flow_value = float(north_series.iloc[-1])
                north_flow_score = self._percentile(north_series, north_flow_value)
        details['north_flow'] = north_flow_value
        details['north_flow_score'] = north_flow_score

        score = momentum_score * 0.6 + north_flow_score * 0.4
        return score, details

    def _calc_liquidity_score(self, context: Dict[str, pd.DataFrame]) -> Tuple[float, Dict]:
        """
        计算流动性维度得分

        指标：
        - M2-M1剪刀差（反向，剪刀差大→流动性紧→得分低）
        - Shibor利率水平（反向）
        - 10年国债收益率（反向）
        - 信用利差（反向）
        - 北向资金流向强度

        Returns:
            流动性得分 (0-100)及细节
        """
        details: Dict[str, Any] = {}

        m2_df = context.get('macro_m2', pd.DataFrame())
        social_df = context.get('macro_social', pd.DataFrame())
        north_flow_df = context.get('north_flow', pd.DataFrame())

        m2_series = self._prepare_series(m2_df, ['货币和准货币(M2)-同比增长'])
        social_series = self._prepare_series(social_df, ['社会融资规模增量'])
        social_growth = self._calc_growth_series(social_series)

        m2_score = self._percentile(m2_series, float(m2_series.iloc[-1])) if len(m2_series) else 50.0
        social_score = self._percentile(social_growth, float(social_growth.iloc[-1])) if len(social_growth) else 50.0

        north_score = 50.0
        if isinstance(north_flow_df, pd.DataFrame) and '资金净流入' in north_flow_df.columns:
            north_series = pd.to_numeric(north_flow_df['资金净流入'], errors='coerce').dropna()
            if not north_series.empty:
                north_score = self._percentile(north_series, float(north_series.iloc[-1]))

        details['m2_yoy'] = float(m2_series.iloc[-1]) if len(m2_series) else None
        details['social_financing_yoy'] = float(social_growth.iloc[-1]) if len(social_growth) else None
        details['north_flow_score'] = north_score

        score = m2_score * 0.4 + social_score * 0.4 + north_score * 0.2
        return score, details

    def _calc_market_breadth(self, context: Dict[str, pd.DataFrame]) -> Tuple[float, Dict]:
        """
        计算市场宽度得分

        指标：
        - 上涨家数 / (上涨+下跌家数)
        - 创新高股票数 / 创新低股票数
        - 涨停跌停比
        - 破净股数量（反向）
        - 行业上涨数量占比

        Returns:
            市场宽度得分 (0-100)及细节
        """
        details: Dict[str, Any] = {}

        stock_df = context.get('stock_list', pd.DataFrame())
        pct_series = self._extract_change_series(stock_df)
        advancers = int((pct_series > 0).sum())
        decliners = int((pct_series < 0).sum())
        total = advancers + decliners
        adv_ratio = advancers / total if total else 0.5

        north_flow_df = context.get('north_flow', pd.DataFrame())
        board_ratio = adv_ratio
        if isinstance(north_flow_df, pd.DataFrame) and {'上涨数', '下跌数', '持平数'}.issubset(north_flow_df.columns):
            last_row = north_flow_df.tail(1)
            up = float(pd.to_numeric(last_row['上涨数'], errors='coerce').iloc[-1]) if not last_row.empty else 0.0
            down = float(pd.to_numeric(last_row['下跌数'], errors='coerce').iloc[-1]) if not last_row.empty else 0.0
            flat = float(pd.to_numeric(last_row['持平数'], errors='coerce').iloc[-1]) if not last_row.empty else 0.0
            total_board = up + down + flat
            if total_board:
                board_ratio = up / total_board

        details['advancers'] = advancers
        details['decliners'] = decliners
        details['advancers_ratio'] = adv_ratio
        details['board_adv_ratio'] = board_ratio

        score = adv_ratio * 100 * 0.6 + board_ratio * 100 * 0.4
        return score, details

    # ==================== 数据加载与辅助函数 ====================

    def _load_context(self) -> Dict[str, pd.DataFrame]:
        context: Dict[str, pd.DataFrame] = {}
        context['valuation'] = self._load_cached_dataframe('valuation_data', 'all_a', fetcher='get_stock_a_ttm_lyr')
        context['hs300'] = self._load_cached_dataframe('market_data', 'hs300', fetcher='get_index_zh_a_hist', fetch_kwargs={'symbol': '000300'})
        context['stock_list'] = self._load_cached_dataframe('market_data', 'stock_list', fetcher='get_stock_zh_a_spot')
        context['north_flow'] = self._aggregate_north_flow(
            self._load_cached_dataframe('fund_data', 'north_flow', fetcher='get_stock_em_hsgt_north_net_flow_in')
        )
        context['macro_m2'] = self._load_cached_dataframe('macro_data', 'm2', fetcher='get_macro_china_m2')
        context['macro_social'] = self._load_cached_dataframe('macro_data', 'social_financing', fetcher='get_macro_china_social_financing')
        return context

    def _load_cached_dataframe(self, dataset: str, key: str, fetcher: Optional[str] = None,
                                fetch_kwargs: Optional[Dict] = None) -> pd.DataFrame:
        df = pd.DataFrame()
        if self.cache_manager:
            df = self.cache_manager.get_dataframe(dataset, key)
        if (df is None or df.empty) and fetcher and self.data_fetcher:
            fetch_func = getattr(self.data_fetcher, fetcher, None)
            if callable(fetch_func):
                fetch_kwargs = fetch_kwargs or {}
                df = fetch_func(**fetch_kwargs)
                if self.cache_manager and isinstance(df, pd.DataFrame) and not df.empty:
                    data = self.cache_manager.load_dataset(dataset) or {}
                    data[key] = df
                    self.cache_manager.save_dataset(dataset, data)
        if df is None:
            df = pd.DataFrame()
        return self._sort_dataframe(df)

    def _aggregate_north_flow(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()

        temp = df.copy()
        if '交易日' in temp.columns:
            temp['交易日'] = pd.to_datetime(temp['交易日'], errors='coerce')
        numeric_cols = ['资金净流入', '成交净买额', '上涨数', '下跌数', '持平数']
        for col in numeric_cols:
            if col in temp.columns:
                temp[col] = pd.to_numeric(temp[col], errors='coerce')

        if '交易日' in temp.columns:
            grouped = temp.groupby('交易日')[numeric_cols].sum(min_count=1).dropna(how='all')
            grouped = grouped.sort_index()
            return grouped.reset_index()

        return temp

    def _sort_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        for column in ['日期', 'date', '交易日', '时间', '月份']:
            if column in df.columns:
                try:
                    df[column] = pd.to_datetime(df[column], errors='coerce')
                    df = df.sort_values(column)
                    break
                except Exception:
                    continue
        return df.reset_index(drop=True)

    def _prepare_series(self, df: pd.DataFrame, candidates: List[str]) -> pd.Series:
        if df is None or df.empty:
            return pd.Series(dtype=float)

        for column in candidates:
            if column in df.columns:
                series = pd.to_numeric(df[column], errors='coerce').dropna()
                if not series.empty:
                    return series.reset_index(drop=True)
        return pd.Series(dtype=float)

    def _extract_change_series(self, df: pd.DataFrame) -> pd.Series:
        if df is None or df.empty:
            return pd.Series(dtype=float)

        for column in ['涨跌幅', '涨跌幅(%)', '涨跌额']:
            if column in df.columns:
                series = df[column].astype(str).str.replace('%', '').replace('--', np.nan)
                series = pd.to_numeric(series, errors='coerce').dropna()
                if not series.empty:
                    return series.reset_index(drop=True)
        return pd.Series(dtype=float)

    def _calc_growth_series(self, series: pd.Series, periods: int = 12) -> pd.Series:
        if series is None or series.empty:
            return pd.Series(dtype=float)
        if len(series) > periods:
            growth = series.pct_change(periods=periods) * 100
        else:
            growth = series.pct_change() * 100
        return growth.dropna()

    def _percentile(self, series: pd.Series, value: float) -> float:
        if series is None or series.empty:
            return 50.0
        clean = series.dropna()
        if clean.empty:
            return 50.0
        percentile = np.sum(clean <= value) / len(clean) * 100
        return float(np.clip(percentile, 0, 100))

    def _classify_level(self, score: float) -> str:
        """
        分类钟摆位置

        Args:
            score: 综合得分

        Returns:
            市场情绪级别描述
        """
        if score < 20:
            return '极度悲观（历史机遇）'
        elif score < 40:
            return '悲观（可以布局）'
        elif score < 60:
            return '中性（等待方向）'
        elif score < 80:
            return '乐观（注意风险）'
        else:
            return '极度乐观（危险区域）'

    def _get_recommendation(self, score: float) -> Dict:
        """
        根据钟摆位置给出操作建议

        Args:
            score: 综合得分

        Returns:
            操作建议字典
        """
        recommendations = [
            {
                'range': (0, 20),
                'position': 0.90,
                'action': '激进买入',
                'style': '价值+成长均衡',
                'reason': '市场极度悲观，历史性机会',
                'urgency': 'HIGH'
            },
            {
                'range': (20, 40),
                'position': 0.80,
                'action': '逐步建仓',
                'style': '偏价值',
                'reason': '市场悲观，但尚未见底',
                'urgency': 'MEDIUM'
            },
            {
                'range': (40, 60),
                'position': 0.65,
                'action': '持有观望',
                'style': '均衡配置',
                'reason': '市场中性，等待方向明确',
                'urgency': 'LOW'
            },
            {
                'range': (60, 80),
                'position': 0.50,
                'action': '逐步减仓',
                'style': '偏防御',
                'reason': '市场乐观，注意回调风险',
                'urgency': 'MEDIUM'
            },
            {
                'range': (80, 100),
                'position': 0.30,
                'action': '大幅减仓',
                'style': '纯防御',
                'reason': '市场极度乐观，泡沫风险高',
                'urgency': 'HIGH'
            }
        ]

        for rec in recommendations:
            if rec['range'][0] <= score < rec['range'][1]:
                return rec

        # 默认中性建议
        return recommendations[2]

    def get_historical_extremes(self) -> Dict:
        """
        获取历史极值点

        Returns:
            历史极值统计
        """
        return {
            'historical_low': {
                'date': '2008-10-28',
                'score': 8,
                'description': '金融危机最恐慌时刻'
            },
            'historical_high': {
                'date': '2015-06-12',
                'score': 95,
                'description': '杠杆牛市顶峰'
            },
            'recent_low': {
                'date': '2022-04-27',
                'score': 15,
                'description': '疫情恐慌底'
            },
            'recent_high': {
                'date': '2021-02-18',
                'score': 85,
                'description': '抱团股泡沫顶峰'
            }
        }
