"""
因子计算模块 - Multi-Horizon Factor Calculation

功能：
1. 多周期趋势计算（EMA、斜率、Z-score）
2. 趋势标签生成（共振上行/下行等）
3. 百分位排名计算
4. 动量和反转因子

作者：Claude
日期：2025-10-21
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from scipy import stats
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class FactorCalculator:
    """多周期因子计算器"""

    def __init__(self, config: dict):
        """
        初始化因子计算器

        Args:
            config: 配置字典，包含windows等参数
        """
        self.config = config
        self.windows = config.get('windows', [5, 10, 30])

    def compute_multi_horizon(
        self,
        series: pd.Series,
        windows: Optional[List[int]] = None
    ) -> Dict[str, Dict[str, float]]:
        """
        计算多周期趋势指标

        Args:
            series: 时序数据（需要有date索引）
            windows: 窗口期列表，默认使用配置中的windows

        Returns:
            {
                '5d': {'ema': 3245.67, 'slope': 0.0123, 'zscore': 1.5},
                '10d': {'ema': 3240.12, 'slope': 0.0089, 'zscore': 0.8},
                '30d': {'ema': 3230.45, 'slope': -0.0012, 'zscore': -0.3}
            }
        """
        if windows is None:
            windows = self.windows

        results = {}

        for window in windows:
            key = f'{window}d'

            # 1. EMA（指数移动平均）
            ema = series.ewm(span=window, adjust=False).mean().iloc[-1]

            # 2. 线性回归斜率
            if len(series) >= window:
                recent = series.iloc[-window:]
                x = np.arange(len(recent))
                slope, _, _, _, _ = stats.linregress(x, recent.values)
            else:
                slope = 0.0

            # 3. 滚动Z-score（相对于过去window期）
            if len(series) >= window:
                rolling_mean = series.rolling(window).mean().iloc[-1]
                rolling_std = series.rolling(window).std().iloc[-1]
                current_value = series.iloc[-1]

                if rolling_std > 0:
                    zscore = (current_value - rolling_mean) / rolling_std
                else:
                    zscore = 0.0
            else:
                zscore = 0.0

            results[key] = {
                'ema': round(ema, 2),
                'slope': round(slope, 6),
                'zscore': round(zscore, 2)
            }

        return results

    def trend_label(self, trends: Dict[str, Dict[str, float]]) -> str:
        """
        生成趋势标签

        Args:
            trends: compute_multi_horizon的输出

        Returns:
            趋势描述，如"多周期共振上行"、"短期反弹、中长期下行"等
        """
        # 提取各周期斜率
        slopes = {k: v['slope'] for k, v in trends.items()}

        # 定义阈值
        STRONG_UP = 0.005
        WEAK_UP = 0.001
        WEAK_DOWN = -0.001
        STRONG_DOWN = -0.005

        # 判断各周期趋势
        labels = {}
        for window, slope in slopes.items():
            if slope > STRONG_UP:
                labels[window] = '强上行'
            elif slope > WEAK_UP:
                labels[window] = '弱上行'
            elif slope > WEAK_DOWN:
                labels[window] = '震荡'
            elif slope > STRONG_DOWN:
                labels[window] = '弱下行'
            else:
                labels[window] = '强下行'

        # 检查共振
        all_up = all('上行' in v for v in labels.values())
        all_down = all('下行' in v for v in labels.values())

        if all_up:
            # 全部上行，检查强度
            if all('强上行' in v for v in labels.values()):
                return '多周期强势共振上行'
            else:
                return '多周期共振上行'
        elif all_down:
            # 全部下行
            if all('强下行' in v for v in labels.values()):
                return '多周期强势共振下行'
            else:
                return '多周期共振下行'
        else:
            # 不一致，分析短期vs长期
            short_label = labels.get('5d', '震荡')
            long_label = labels.get('30d', '震荡')

            if '上行' in short_label and '下行' in long_label:
                return '短期反弹，中长期下行'
            elif '下行' in short_label and '上行' in long_label:
                return '短期回调，中长期上行'
            elif '上行' in short_label:
                return f'短期{short_label}，长期{long_label}'
            elif '下行' in short_label:
                return f'短期{short_label}，长期{long_label}'
            else:
                return '多周期震荡分化'

    def compute_percentile_rank(
        self,
        value: float,
        history: pd.Series,
        window: int = 252
    ) -> float:
        """
        计算百分位排名

        Args:
            value: 当前值
            history: 历史序列
            window: 回看窗口（默认252个交易日≈1年）

        Returns:
            百分位数（0-100）
        """
        if len(history) < 2:
            return 50.0

        recent_history = history.iloc[-window:] if len(history) > window else history

        # 计算当前值在历史中的排名
        percentile = stats.percentileofscore(recent_history.values, value, kind='rank')

        return round(percentile, 1)

    def compute_momentum(
        self,
        series: pd.Series,
        periods: List[int] = [5, 10, 20]
    ) -> Dict[str, float]:
        """
        计算动量指标

        Args:
            series: 价格序列
            periods: 动量周期列表

        Returns:
            {'5d_ret': 0.0123, '10d_ret': 0.0245, '20d_ret': 0.0389}
        """
        results = {}

        for period in periods:
            if len(series) >= period + 1:
                ret = (series.iloc[-1] / series.iloc[-(period+1)]) - 1
                results[f'{period}d_ret'] = round(ret, 4)
            else:
                results[f'{period}d_ret'] = 0.0

        return results

    def compute_volatility(
        self,
        returns: pd.Series,
        window: int = 20
    ) -> float:
        """
        计算滚动波动率

        Args:
            returns: 收益率序列
            window: 滚动窗口

        Returns:
            年化波动率
        """
        if len(returns) < window:
            return 0.0

        rolling_std = returns.rolling(window).std().iloc[-1]

        # 年化（假设252个交易日）
        annualized_vol = rolling_std * np.sqrt(252)

        return round(annualized_vol, 4)

    def compute_industry_strength(
        self,
        industry_df: pd.DataFrame,
        return_col: str = 'avg_return',
        flow_col: str = 'net_flow'
    ) -> pd.DataFrame:
        """
        计算行业强度得分

        Args:
            industry_df: 行业数据DataFrame，需包含return_col和flow_col
            return_col: 收益率列名
            flow_col: 资金流向列名

        Returns:
            添加了strength_score列的DataFrame
        """
        df = industry_df.copy()

        # 计算收益率百分位（0-100）
        df['return_pct'] = df[return_col].rank(pct=True) * 100

        # 计算资金流百分位
        df['flow_pct'] = df[flow_col].rank(pct=True) * 100

        # 强度得分 = 收益率百分位 × 0.6 + 资金流百分位 × 0.4
        df['strength_score'] = (
            df['return_pct'] * 0.6 +
            df['flow_pct'] * 0.4
        )

        # 排序
        df = df.sort_values('strength_score', ascending=False)

        return df

    def compute_industry_crowding(
        self,
        industry_df: pd.DataFrame,
        turnover_col: str = 'avg_turnover',
        limit_up_col: str = 'limit_up_count'
    ) -> pd.DataFrame:
        """
        计算行业拥挤度得分

        Args:
            industry_df: 行业数据DataFrame
            turnover_col: 换手率列名
            limit_up_col: 涨停数量列名

        Returns:
            添加了crowding_score列的DataFrame
        """
        df = industry_df.copy()

        # 计算换手率百分位
        df['turnover_pct'] = df[turnover_col].rank(pct=True) * 100

        # 计算涨停数百分位
        df['limit_up_pct'] = df[limit_up_col].rank(pct=True) * 100

        # 拥挤度得分 = 换手率百分位 × 0.6 + 涨停数百分位 × 0.4
        df['crowding_score'] = (
            df['turnover_pct'] * 0.6 +
            df['limit_up_pct'] * 0.4
        )

        return df

    def create_industry_rotation_matrix(
        self,
        industry_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        创建行业轮动矩阵（四象限）

        需要先计算strength_score和crowding_score

        Args:
            industry_df: 包含strength_score和crowding_score的DataFrame

        Returns:
            添加了quadrant列的DataFrame

        四象限定义：
        - 强势+低拥挤(strength>50, crowding<50): "配置型机会"
        - 强势+高拥挤(strength>50, crowding>50): "警惕过热"
        - 弱势+低拥挤(strength<50, crowding<50): "等待拐点"
        - 弱势+高拥挤(strength<50, crowding>50): "避免追高"
        """
        df = industry_df.copy()

        def classify_quadrant(row):
            strength = row['strength_score']
            crowding = row['crowding_score']

            if strength >= 50 and crowding < 50:
                return '配置型机会'
            elif strength >= 50 and crowding >= 50:
                return '警惕过热'
            elif strength < 50 and crowding < 50:
                return '等待拐点'
            else:  # strength < 50 and crowding >= 50
                return '避免追高'

        df['quadrant'] = df.apply(classify_quadrant, axis=1)

        # 添加推荐操作
        quadrant_actions = {
            '配置型机会': '逐步建仓',
            '警惕过热': '高抛减仓',
            '等待拐点': '观望',
            '避免追高': '清仓离场'
        }
        df['action'] = df['quadrant'].map(quadrant_actions)

        return df

    def compute_reversal_signal(
        self,
        series: pd.Series,
        lookback: int = 20,
        threshold: float = 2.0
    ) -> Dict[str, any]:
        """
        计算反转信号

        Args:
            series: 价格序列
            lookback: 回看期
            threshold: Z-score阈值

        Returns:
            {
                'signal': 'oversold' | 'overbought' | 'neutral',
                'zscore': float,
                'percentile': float
            }
        """
        if len(series) < lookback:
            return {
                'signal': 'neutral',
                'zscore': 0.0,
                'percentile': 50.0
            }

        # 计算Z-score
        mean = series.iloc[-lookback:].mean()
        std = series.iloc[-lookback:].std()
        current = series.iloc[-1]

        if std > 0:
            zscore = (current - mean) / std
        else:
            zscore = 0.0

        # 计算百分位
        percentile = self.compute_percentile_rank(current, series, lookback)

        # 判断信号
        if zscore < -threshold:
            signal = 'oversold'  # 超卖
        elif zscore > threshold:
            signal = 'overbought'  # 超买
        else:
            signal = 'neutral'

        return {
            'signal': signal,
            'zscore': round(zscore, 2),
            'percentile': percentile
        }

    def batch_compute_trends(
        self,
        data_dict: Dict[str, pd.Series]
    ) -> Dict[str, Dict]:
        """
        批量计算多个序列的趋势

        Args:
            data_dict: {
                'index_sh': pd.Series(...),
                'index_sz': pd.Series(...),
                ...
            }

        Returns:
            {
                'index_sh': {
                    'trends': {...},
                    'label': '多周期共振上行',
                    'momentum': {...}
                },
                ...
            }
        """
        results = {}

        for name, series in data_dict.items():
            try:
                # 计算趋势
                trends = self.compute_multi_horizon(series)

                # 生成标签
                label = self.trend_label(trends)

                # 计算动量
                momentum = self.compute_momentum(series)

                # 计算反转信号
                reversal = self.compute_reversal_signal(series)

                results[name] = {
                    'trends': trends,
                    'label': label,
                    'momentum': momentum,
                    'reversal': reversal,
                    'current_value': round(series.iloc[-1], 2)
                }

            except Exception as e:
                logger.error(f"计算{name}趋势时出错: {e}")
                results[name] = None

        return results


def create_factor_summary(
    factor_results: Dict[str, Dict]
) -> pd.DataFrame:
    """
    将因子计算结果转换为DataFrame格式

    Args:
        factor_results: batch_compute_trends的输出

    Returns:
        DataFrame with columns: name, current, 5d_slope, 10d_slope, 30d_slope,
                                label, 5d_ret, reversal_signal
    """
    rows = []

    for name, data in factor_results.items():
        if data is None:
            continue

        row = {
            'name': name,
            'current': data['current_value'],
            '5d_slope': data['trends']['5d']['slope'],
            '10d_slope': data['trends']['10d']['slope'],
            '30d_slope': data['trends']['30d']['slope'],
            'label': data['label'],
            '5d_ret': data['momentum']['5d_ret'],
            '10d_ret': data['momentum']['10d_ret'],
            '20d_ret': data['momentum']['20d_ret'],
            'reversal_signal': data['reversal']['signal'],
            'reversal_zscore': data['reversal']['zscore']
        }

        rows.append(row)

    return pd.DataFrame(rows)


if __name__ == '__main__':
    # 测试代码
    import yaml

    # 加载配置
    config_path = Path(__file__).parent.parent / 'config' / 'config.yaml'
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # 创建计算器
    calc = FactorCalculator(config)

    # 生成测试数据
    dates = pd.date_range('2024-01-01', '2024-10-21', freq='D')
    prices = 3000 + np.cumsum(np.random.randn(len(dates)) * 10)
    series = pd.Series(prices, index=dates)

    # 测试多周期趋势
    trends = calc.compute_multi_horizon(series)
    print("多周期趋势:")
    for window, metrics in trends.items():
        print(f"  {window}: EMA={metrics['ema']}, Slope={metrics['slope']}, Z-score={metrics['zscore']}")

    # 测试趋势标签
    label = calc.trend_label(trends)
    print(f"\n趋势标签: {label}")

    # 测试动量
    momentum = calc.compute_momentum(series)
    print(f"\n动量指标: {momentum}")

    # 测试反转信号
    reversal = calc.compute_reversal_signal(series)
    print(f"\n反转信号: {reversal}")

    print("\n✅ 因子计算模块测试完成！")
