"""
朱格拉周期识别引擎 (产能周期, 7-11年)
中期经济周期，主要由固定资产投资和产能利用率驱动
"""

import sys
import os
# 添加项目根目录到路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import pandas as pd
import numpy as np
from typing import Dict, Optional, List
from datetime import datetime

from utils.logger import logger
from data.storage import DataCacheManager


class JuglarCycle:
    """
    朱格拉周期识别 - 7-11年的产能投资周期

    判断方法：
    - 产能利用率 + 固定资产投资方向
    - PPI + ROE双轮驱动
    - 信贷周期（领先指标）
    """

    def __init__(self, data_fetcher=None, cache_manager: Optional[DataCacheManager] = None):
        """
        Args:
            data_fetcher: 数据获取器实例
        """
        self.data_fetcher = data_fetcher
        self.cache_manager = cache_manager
        self.logger = logger

        self.indicators = {
            'capacity_utilization': pd.Series(dtype=float),
            'fixed_investment': pd.Series(dtype=float),
            'ppi': pd.Series(dtype=float),
            'roe': pd.Series(dtype=float),
            'credit_growth': pd.Series(dtype=float)
        }

    def fetch_data(self) -> Dict:
        """获取周期判断所需数据"""
        try:
            pmi_df = self._load_macro_dataframe('pmi', 'get_macro_china_pmi')
            ppi_df = self._load_macro_dataframe('ppi', 'get_macro_china_ppi')
            gdp_df = self._load_macro_dataframe('gdp', 'get_macro_china_gdp')
            m2_df = self._load_macro_dataframe('m2', 'get_macro_china_m2')
            social_df = self._load_macro_dataframe('social_financing', 'get_macro_china_social_financing')

            capacity_series = self._prepare_series(pmi_df, ['制造业-指数'])
            investment_base = self._prepare_series(social_df, ['其中-企业债券', '其中-人民币贷款', '社会融资规模增量'])
            investment_series = self._calc_growth_series(investment_base)
            ppi_series = self._prepare_series(ppi_df, ['当月同比增长'])
            roe_series = self._prepare_series(gdp_df, ['第二产业-同比增长', '国内生产总值-同比增长'])
            credit_series = self._prepare_series(m2_df, ['货币和准货币(M2)-同比增长'])

            self.indicators = {
                'capacity_utilization': capacity_series,
                'fixed_investment': investment_series,
                'ppi': ppi_series,
                'roe': roe_series,
                'credit_growth': credit_series
            }

            data = {
                'timestamp': self._infer_latest_period([pmi_df, social_df, gdp_df, m2_df]),
                'fixed_investment_growth': self._latest_non_null(investment_series),
                'ppi_yoy': self._latest_non_null(ppi_series),
                'industrial_roe': self._latest_non_null(roe_series),
                'credit_growth': self._latest_non_null(credit_series),
                'capacity_utilization': self._latest_non_null(capacity_series)
            }

            self.logger.info("朱格拉周期数据获取成功（使用真实宏观数据）")
            return data

        except Exception as e:
            self.logger.error(f"朱格拉周期数据获取失败: {str(e)}", exc_info=True)
            return {}

    def calculate_phase(self) -> Dict:
        """
        判断当前处于朱格拉周期的哪个阶段

        四阶段：
        1. 复苏期：产能利用率回升，投资开始增加
        2. 繁荣期：产能扩张，企业盈利改善
        3. 衰退期：产能过剩显现，盈利下滑
        4. 萧条期：产能出清，等待新一轮周期

        Returns:
            包含周期信息的字典
        """
        data = self.fetch_data()

        capacity_trend = self._calc_trend(self.indicators.get('capacity_utilization'))
        investment_trend = self._calc_trend(self.indicators.get('fixed_investment'))
        ppi_level = self._get_percentile(data.get('ppi_yoy', 0), self.indicators.get('ppi'))
        roe_trend = self._calc_trend(self.indicators.get('roe'))
        credit_trend = self._calc_trend(self.indicators.get('credit_growth'), short=3, long=12)

        # 综合判断
        phase = self._综合判断phase(
            capacity_trend,
            investment_trend,
            ppi_level,
            roe_trend,
            credit_trend
        )

        result = {
            'phase': phase,
            'phase_name': ['复苏', '繁荣', '衰退', '萧条'][phase - 1],
            'confidence': self._calc_confidence(capacity_trend, investment_trend, roe_trend, credit_trend),
            'time_in_phase': self._estimate_phase_duration(phase),
            'next_inflection': self._predict_inflection_point(phase),
            'indicators': {
                'capacity_trend': capacity_trend,
                'investment_trend': investment_trend,
                'ppi_level': ppi_level,
                'roe_trend': roe_trend,
                'credit_trend': credit_trend
            },
            'timestamp': data.get('timestamp')
        }

        self.logger.info(f"朱格拉周期识别完成: {result['phase_name']} (置信度: {result['confidence']:.1%})")

        return result

    def get_industry_preference(self, phase: int) -> Dict:
        """
        根据朱格拉周期阶段返回行业配置建议

        Args:
            phase: 周期阶段 (1-4)

        Returns:
            行业配置建议
        """
        industry_map = {
            1: {  # 复苏期
                'overweight': ['机械设备', '化工', '建筑材料', '有色金属', '钢铁'],
                'neutral': ['电力设备', '汽车', '电子'],
                'underweight': ['食品饮料', '医药生物', '银行'],
                'reason': '产能利用率回升，周期品需求改善'
            },
            2: {  # 繁荣期
                'overweight': ['电子', '计算机', '传媒', '新能源', '军工'],
                'neutral': ['机械设备', '化工', '汽车'],
                'underweight': ['公用事业', '银行', '房地产'],
                'reason': '经济扩张，成长股表现最佳'
            },
            3: {  # 衰退期
                'overweight': ['医药生物', '食品饮料', '农林牧渔', '公用事业'],
                'neutral': ['家用电器', '轻工制造'],
                'underweight': ['有色金属', '钢铁', '煤炭', '化工'],
                'reason': '经济下行，防御性板块相对占优'
            },
            4: {  # 萧条期
                'overweight': ['公用事业', '银行', '黄金（商品）'],
                'neutral': ['医药生物', '必需消费'],
                'underweight': ['周期性行业全部'],
                'reason': '产能出清阶段，现金为王'
            }
        }

        return industry_map.get(phase, industry_map[2])

    def get_asset_allocation_adjustment(self, phase: int) -> Dict:
        """
        朱格拉周期对大类资产配置的影响系数

        Args:
            phase: 周期阶段

        Returns:
            各类资产的配置调整系数
        """
        allocation_adj = {
            1: {  # 复苏期
                'stock': 1.1,
                'bond': 0.9,
                'commodity': 1.2,
                'cash': 0.8,
                'recommended_position': 0.75
            },
            2: {  # 繁荣期
                'stock': 1.2,
                'bond': 0.8,
                'commodity': 1.0,
                'cash': 0.7,
                'recommended_position': 0.85
            },
            3: {  # 衰退期
                'stock': 0.8,
                'bond': 1.2,
                'commodity': 0.8,
                'cash': 1.1,
                'recommended_position': 0.50
            },
            4: {  # 萧条期
                'stock': 0.6,
                'bond': 1.3,
                'commodity': 0.7,
                'cash': 1.3,
                'recommended_position': 0.30
            }
        }

        return allocation_adj.get(phase, allocation_adj[2])

    def get_indicator_history(self) -> Dict[str, pd.Series]:
        """返回用于可视化的指标历史。"""

        history = {}
        for key, series in self.indicators.items():
            if isinstance(series, pd.Series):
                history[key] = series.copy()
            else:
                history[key] = pd.Series(series)
        return history

    # ==================== 私有方法 ====================

    def _load_macro_dataframe(self, key: str, fetcher: str) -> pd.DataFrame:
        df = pd.DataFrame()
        if self.cache_manager:
            df = self.cache_manager.get_dataframe('macro_data', key)
        if (df is None or df.empty) and self.data_fetcher:
            fetch_func = getattr(self.data_fetcher, fetcher, None)
            if callable(fetch_func):
                df = fetch_func()
                if self.cache_manager and isinstance(df, pd.DataFrame) and not df.empty:
                    data = self.cache_manager.load_dataset('macro_data') or {}
                    data[key] = df
                    self.cache_manager.save_dataset('macro_data', data)
        if df is None:
            df = pd.DataFrame()
        return self._sort_dataframe(df)

    def _sort_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        candidates = ['日期', 'date', '月份', '季度', '时间', '统计期', 'period', 'TRADE_DATE', '交易日']
        for column in candidates:
            if column in df.columns:
                sort_key = df[column]
                try:
                    parsed = pd.to_datetime(sort_key, errors='coerce')
                    if parsed.notna().sum() >= max(1, len(parsed) // 2):
                        sort_key = parsed
                except Exception:
                    pass
                df = df.assign(_sort_key=sort_key).sort_values('_sort_key').drop(columns=['_sort_key'])
                break

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

    def _calc_growth_series(self, series: pd.Series, periods: int = 12) -> pd.Series:
        if series is None or series.empty:
            return pd.Series(dtype=float)

        if len(series) > periods:
            growth = series.pct_change(periods=periods) * 100
        else:
            growth = series.pct_change() * 100
        return growth.dropna()

    def _latest_non_null(self, series: pd.Series) -> float:
        if series is None or series.empty:
            return 0.0
        value = series.dropna()
        if value.empty:
            return 0.0
        return float(np.nan_to_num(value.iloc[-1], nan=0.0))

    def _infer_latest_period(self, dfs: list[pd.DataFrame]) -> str:
        for df in dfs:
            if df is None or df.empty:
                continue
            for column in ['日期', 'date', '月份', '季度', '时间', '统计期', 'period', 'TRADE_DATE', '交易日']:
                if column in df.columns:
                    value = df[column].dropna().iloc[-1]
                    return str(value)
        return datetime.now().strftime('%Y-%m-%d')

    def _calc_trend(self, series: Optional[pd.Series], short: int = 3, long: int = 9) -> float:
        if series is None or series.empty:
            return 0.0

        clean = series.dropna()
        if clean.empty:
            return 0.0

        short_window = min(short, len(clean))
        long_window = min(long, len(clean))

        short_ma = clean.tail(short_window).mean()
        long_ma = clean.tail(long_window).mean()

        if long_ma == 0 or np.isnan(short_ma) or np.isnan(long_ma):
            return 0.0

        slope = (short_ma - long_ma) / abs(long_ma)
        return float(np.clip(slope, -1.0, 1.0))

    def _get_percentile(self, value: float, series: Optional[pd.Series]) -> float:
        if series is None or series.empty:
            return 50.0

        clean = series.dropna()
        if clean.empty:
            return 50.0

        arr = clean.values
        percentile = np.sum(arr <= value) / len(arr) * 100
        return float(np.clip(percentile, 0, 100))

    def _综合判断phase(self, capacity_trend: float, investment_trend: float,
                      ppi_level: float, roe_trend: float, credit_trend: float) -> int:
        """
        综合判断当前周期阶段

        Returns:
            1-复苏, 2-繁荣, 3-衰退, 4-萧条
        """
        # 简化的判断逻辑
        score = 0

        # 产能利用率上升+投资增加 → 繁荣
        if capacity_trend > 0 and investment_trend > 0:
            score += 2
        # 产能利用率下降+投资减少 → 衰退/萧条
        elif capacity_trend < 0 and investment_trend < 0:
            score -= 2

        # PPI高位 → 繁荣
        if ppi_level > 60:
            score += 1
        elif ppi_level < 40:
            score -= 1

        # ROE改善 → 复苏/繁荣
        if roe_trend > 0:
            score += 1
        else:
            score -= 1

        # 信贷领先指标
        if credit_trend > 0:
            score += 1
        else:
            score -= 1

        # 根据得分判断阶段
        if score >= 3:
            return 2  # 繁荣期
        elif score >= 1:
            return 1  # 复苏期
        elif score >= -1:
            return 3  # 衰退期
        else:
            return 4  # 萧条期

    def _calc_confidence(self, capacity_trend: float, investment_trend: float,
                         roe_trend: float, credit_trend: float) -> float:
        """计算判断置信度"""

        signals = [abs(capacity_trend), abs(investment_trend), abs(roe_trend), abs(credit_trend)]
        valid = [s for s in signals if not np.isnan(s)]
        base = np.mean(valid) if valid else 0.3
        base = np.clip(base, 0.1, 1.0)

        alignment = 1.0 if capacity_trend * investment_trend >= 0 else 0.7
        credit_factor = 1.0 - min(abs(credit_trend), 1.0) * 0.2

        confidence = base * alignment * credit_factor + 0.2
        return float(np.clip(confidence, 0.2, 0.95))

    def _estimate_phase_duration(self, phase: int) -> int:
        """估计当前阶段已持续时间（月）"""

        series = self.indicators.get('capacity_utilization')
        if series is None or len(series) < 2:
            return 12

        diff = series.diff().dropna()
        if diff.empty:
            return min(len(series), 12)

        last_sign = np.sign(diff.iloc[-1])
        if last_sign == 0:
            return 6

        streak = 1
        for val in reversed(diff.iloc[:-1]):
            if np.sign(val) == last_sign:
                streak += 1
            else:
                break

        return int(max(3, min(streak, 36)))

    def _predict_inflection_point(self, phase: int) -> str:
        """预测下一个拐点时间"""

        avg_duration = {
            1: 24,
            2: 36,
            3: 18,
            4: 12
        }
        elapsed = self._estimate_phase_duration(phase)
        remaining = max(avg_duration.get(phase, 24) - elapsed, 3)
        return f"预计{remaining}个月后进入下一阶段"
