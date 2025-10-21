"""
四维度评分模块 - Four-Dimensional Scoring System

评分体系：
1. 宏观维度 (Macro) - 25%: PMI、PPI、GDP增速
2. 流动性维度 (Liquidity) - 35%: M2、融资余额、ETF流入
3. 风险偏好维度 (Risk-on) - 20%: 换手率、涨跌停、新高新低
4. 动量维度 (Momentum) - 20%: 指数动量、市场宽度、行业轮动

作者：Claude
日期：2025-10-21
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class FourDimensionScorer:
    """四维度评分系统"""

    def __init__(self, config: dict):
        """
        初始化评分器

        Args:
            config: 配置字典，包含权重等参数
        """
        self.config = config
        self.weights = config.get('score_weights', {
            'macro': 0.25,
            'liquidity': 0.35,
            'riskon': 0.20,
            'momentum': 0.20
        })

    def score_macro(self, macro_data: Dict) -> Dict[str, float]:
        """
        宏观维度评分

        Args:
            macro_data: {
                'pmi_new_orders': 52.3,
                'pmi_inventory': 48.7,
                'ppi_yoy': -1.23,
                # 可选
                'gdp_yoy': 5.2
            }

        Returns:
            {
                'pmi_score': 60,
                'ppi_score': 40,
                'gdp_score': 70,
                'total_score': 55,
                'label': '宏观偏暖'
            }
        """
        scores = {}

        # 1. PMI评分（新订单指数）
        pmi = macro_data.get('pmi_new_orders', 50)
        if pmi >= 55:
            scores['pmi_score'] = 90
        elif pmi >= 52:
            scores['pmi_score'] = 70
        elif pmi >= 50:
            scores['pmi_score'] = 60
        elif pmi >= 48:
            scores['pmi_score'] = 40
        else:
            scores['pmi_score'] = 20

        # 2. PPI评分（价格水平）
        ppi = macro_data.get('ppi_yoy', 0)
        if ppi > 3:
            scores['ppi_score'] = 30  # 过热
        elif ppi > 1:
            scores['ppi_score'] = 70  # 温和通胀
        elif ppi > -1:
            scores['ppi_score'] = 60  # 稳定
        elif ppi > -3:
            scores['ppi_score'] = 40  # 通缩压力
        else:
            scores['ppi_score'] = 20  # 深度通缩

        # 3. GDP评分（如果有）
        gdp = macro_data.get('gdp_yoy')
        if gdp is not None:
            if gdp >= 6:
                scores['gdp_score'] = 90
            elif gdp >= 5:
                scores['gdp_score'] = 70
            elif gdp >= 4:
                scores['gdp_score'] = 50
            else:
                scores['gdp_score'] = 30
        else:
            scores['gdp_score'] = 50  # 缺省值

        # 计算总分
        total = (
            scores['pmi_score'] * 0.5 +
            scores['ppi_score'] * 0.3 +
            scores['gdp_score'] * 0.2
        )
        scores['total_score'] = round(total, 1)

        # 生成标签
        if total >= 70:
            scores['label'] = '宏观强势'
        elif total >= 60:
            scores['label'] = '宏观偏暖'
        elif total >= 50:
            scores['label'] = '宏观中性'
        elif total >= 40:
            scores['label'] = '宏观偏冷'
        else:
            scores['label'] = '宏观疲弱'

        return scores

    def score_liquidity(self, liquidity_data: Dict) -> Dict[str, float]:
        """
        流动性维度评分

        Args:
            liquidity_data: {
                'm2_yoy': 9.87,  # M2同比增速
                'margin_balance': 15234.56,  # 融资余额（亿元）
                'margin_growth': 2.3,  # 融资余额增速（%）
                'etf_flow_5d': 123.45,  # 5日ETF净流入（亿元）
                'etf_flow_10d': 245.67
            }

        Returns:
            {
                'm2_score': 70,
                'margin_score': 60,
                'etf_score': 75,
                'total_score': 68.5,
                'label': '流动性充裕'
            }
        """
        scores = {}

        # 1. M2评分
        m2 = liquidity_data.get('m2_yoy', 8)
        if m2 >= 12:
            scores['m2_score'] = 90
        elif m2 >= 10:
            scores['m2_score'] = 75
        elif m2 >= 8:
            scores['m2_score'] = 60
        elif m2 >= 6:
            scores['m2_score'] = 40
        else:
            scores['m2_score'] = 20

        # 2. 融资余额评分（看增速）
        margin_growth = liquidity_data.get('margin_growth', 0)
        if margin_growth >= 5:
            scores['margin_score'] = 90
        elif margin_growth >= 2:
            scores['margin_score'] = 70
        elif margin_growth >= 0:
            scores['margin_score'] = 50
        elif margin_growth >= -2:
            scores['margin_score'] = 30
        else:
            scores['margin_score'] = 10

        # 3. ETF流向评分（5日）
        etf_flow = liquidity_data.get('etf_flow_5d', 0)
        if etf_flow >= 200:
            scores['etf_score'] = 90
        elif etf_flow >= 100:
            scores['etf_score'] = 75
        elif etf_flow >= 0:
            scores['etf_score'] = 55
        elif etf_flow >= -100:
            scores['etf_score'] = 35
        else:
            scores['etf_score'] = 15

        # 计算总分
        total = (
            scores['m2_score'] * 0.4 +
            scores['margin_score'] * 0.35 +
            scores['etf_score'] * 0.25
        )
        scores['total_score'] = round(total, 1)

        # 生成标签
        if total >= 75:
            scores['label'] = '流动性泛滥'
        elif total >= 60:
            scores['label'] = '流动性充裕'
        elif total >= 50:
            scores['label'] = '流动性中性'
        elif total >= 35:
            scores['label'] = '流动性收紧'
        else:
            scores['label'] = '流动性枯竭'

        return scores

    def score_riskon(self, riskon_data: Dict) -> Dict[str, float]:
        """
        风险偏好维度评分

        Args:
            riskon_data: {
                'turnover_rate': 3.45,  # 两市平均换手率（%）
                'limit_up_count': 87,  # 涨停数量
                'limit_down_count': 45,  # 跌停数量
                'up_count': 2134,  # 上涨家数
                'down_count': 2456,  # 下跌家数
                'new_high_count': 123,  # 创新高数量（可选）
                'new_low_count': 89  # 创新低数量（可选）
            }

        Returns:
            {
                'turnover_score': 65,
                'limit_score': 70,
                'breadth_score': 45,
                'high_low_score': 55,
                'total_score': 60.5,
                'label': '风险偏好中性'
            }
        """
        scores = {}

        # 1. 换手率评分
        turnover = riskon_data.get('turnover_rate', 2.5)
        if turnover >= 5:
            scores['turnover_score'] = 90  # 极度活跃
        elif turnover >= 4:
            scores['turnover_score'] = 75
        elif turnover >= 3:
            scores['turnover_score'] = 60
        elif turnover >= 2:
            scores['turnover_score'] = 45
        else:
            scores['turnover_score'] = 30  # 低迷

        # 2. 涨跌停评分
        limit_up = riskon_data.get('limit_up_count', 0)
        limit_down = riskon_data.get('limit_down_count', 0)

        if limit_down == 0:
            limit_ratio = limit_up
        else:
            limit_ratio = limit_up / limit_down

        if limit_ratio >= 3:
            scores['limit_score'] = 90  # 强势
        elif limit_ratio >= 2:
            scores['limit_score'] = 75
        elif limit_ratio >= 1:
            scores['limit_score'] = 55
        elif limit_ratio >= 0.5:
            scores['limit_score'] = 35
        else:
            scores['limit_score'] = 15  # 弱势

        # 3. 市场宽度评分（涨跌比）
        up_count = riskon_data.get('up_count', 2000)
        down_count = riskon_data.get('down_count', 2000)
        total_count = up_count + down_count

        if total_count > 0:
            up_ratio = up_count / total_count
        else:
            up_ratio = 0.5

        if up_ratio >= 0.65:
            scores['breadth_score'] = 90
        elif up_ratio >= 0.55:
            scores['breadth_score'] = 70
        elif up_ratio >= 0.45:
            scores['breadth_score'] = 50
        elif up_ratio >= 0.35:
            scores['breadth_score'] = 30
        else:
            scores['breadth_score'] = 10

        # 4. 新高新低评分（如果有）
        new_high = riskon_data.get('new_high_count')
        new_low = riskon_data.get('new_low_count')

        if new_high is not None and new_low is not None:
            if new_low == 0:
                high_low_ratio = new_high
            else:
                high_low_ratio = new_high / new_low

            if high_low_ratio >= 3:
                scores['high_low_score'] = 90
            elif high_low_ratio >= 2:
                scores['high_low_score'] = 70
            elif high_low_ratio >= 1:
                scores['high_low_score'] = 50
            elif high_low_ratio >= 0.5:
                scores['high_low_score'] = 30
            else:
                scores['high_low_score'] = 10
        else:
            scores['high_low_score'] = 50  # 缺省值

        # 计算总分
        total = (
            scores['turnover_score'] * 0.3 +
            scores['limit_score'] * 0.3 +
            scores['breadth_score'] * 0.25 +
            scores['high_low_score'] * 0.15
        )
        scores['total_score'] = round(total, 1)

        # 生成标签
        if total >= 75:
            scores['label'] = '风险偏好极高'
        elif total >= 60:
            scores['label'] = '风险偏好偏高'
        elif total >= 50:
            scores['label'] = '风险偏好中性'
        elif total >= 35:
            scores['label'] = '风险偏好偏低'
        else:
            scores['label'] = '风险偏好极低'

        return scores

    def score_momentum(self, momentum_data: Dict) -> Dict[str, float]:
        """
        动量维度评分

        Args:
            momentum_data: {
                'index_5d_ret': 0.0123,  # 指数5日收益率
                'index_10d_ret': 0.0245,
                'index_20d_ret': 0.0389,
                'breadth_5d_change': 150,  # 5日上涨家数变化
                'sector_rotation_score': 65  # 行业轮动得分（0-100）
            }

        Returns:
            {
                'index_momentum_score': 70,
                'breadth_momentum_score': 65,
                'rotation_score': 60,
                'total_score': 66.5,
                'label': '动量向上'
            }
        """
        scores = {}

        # 1. 指数动量评分（20日收益率）
        ret_20d = momentum_data.get('index_20d_ret', 0)
        if ret_20d >= 0.10:
            scores['index_momentum_score'] = 95
        elif ret_20d >= 0.05:
            scores['index_momentum_score'] = 80
        elif ret_20d >= 0.02:
            scores['index_momentum_score'] = 65
        elif ret_20d >= 0:
            scores['index_momentum_score'] = 50
        elif ret_20d >= -0.02:
            scores['index_momentum_score'] = 35
        elif ret_20d >= -0.05:
            scores['index_momentum_score'] = 20
        else:
            scores['index_momentum_score'] = 10

        # 2. 市场宽度动量评分（5日上涨家数变化）
        breadth_change = momentum_data.get('breadth_5d_change', 0)
        if breadth_change >= 500:
            scores['breadth_momentum_score'] = 90
        elif breadth_change >= 200:
            scores['breadth_momentum_score'] = 75
        elif breadth_change >= 0:
            scores['breadth_momentum_score'] = 55
        elif breadth_change >= -200:
            scores['breadth_momentum_score'] = 35
        else:
            scores['breadth_momentum_score'] = 15

        # 3. 行业轮动评分（直接使用）
        rotation = momentum_data.get('sector_rotation_score', 50)
        scores['rotation_score'] = rotation

        # 计算总分
        total = (
            scores['index_momentum_score'] * 0.5 +
            scores['breadth_momentum_score'] * 0.3 +
            scores['rotation_score'] * 0.2
        )
        scores['total_score'] = round(total, 1)

        # 生成标签
        if total >= 75:
            scores['label'] = '动量强劲'
        elif total >= 60:
            scores['label'] = '动量向上'
        elif total >= 50:
            scores['label'] = '动量中性'
        elif total >= 35:
            scores['label'] = '动量减弱'
        else:
            scores['label'] = '动量疲弱'

        return scores

    def compute_composite_score(
        self,
        macro_score: float,
        liquidity_score: float,
        riskon_score: float,
        momentum_score: float
    ) -> Dict[str, any]:
        """
        计算综合得分

        Args:
            macro_score: 宏观维度得分（0-100）
            liquidity_score: 流动性维度得分（0-100）
            riskon_score: 风险偏好维度得分（0-100）
            momentum_score: 动量维度得分（0-100）

        Returns:
            {
                'total_score': 65.3,
                'position': 65,  # 建议仓位（%）
                'level': '中性偏多',
                'breakdown': {
                    'macro': 55,
                    'liquidity': 68,
                    'riskon': 60,
                    'momentum': 67
                }
            }
        """
        # 计算加权总分
        total = (
            macro_score * self.weights['macro'] +
            liquidity_score * self.weights['liquidity'] +
            riskon_score * self.weights['riskon'] +
            momentum_score * self.weights['momentum']
        )

        # 建议仓位（总分映射到仓位）
        if total >= 80:
            position = 90
            level = '极度乐观'
        elif total >= 70:
            position = 80
            level = '偏多'
        elif total >= 60:
            position = 65
            level = '中性偏多'
        elif total >= 50:
            position = 50
            level = '中性'
        elif total >= 40:
            position = 35
            level = '中性偏空'
        elif total >= 30:
            position = 20
            level = '偏空'
        else:
            position = 10
            level = '极度悲观'

        return {
            'total_score': round(total, 1),
            'position': position,
            'level': level,
            'breakdown': {
                'macro': round(macro_score, 1),
                'liquidity': round(liquidity_score, 1),
                'riskon': round(riskon_score, 1),
                'momentum': round(momentum_score, 1)
            }
        }

    def score_all(
        self,
        macro_data: Dict,
        liquidity_data: Dict,
        riskon_data: Dict,
        momentum_data: Dict
    ) -> Dict:
        """
        一次性计算所有维度得分

        Returns:
            {
                'macro': {...},
                'liquidity': {...},
                'riskon': {...},
                'momentum': {...},
                'composite': {...}
            }
        """
        # 计算各维度得分
        macro = self.score_macro(macro_data)
        liquidity = self.score_liquidity(liquidity_data)
        riskon = self.score_riskon(riskon_data)
        momentum = self.score_momentum(momentum_data)

        # 计算综合得分
        composite = self.compute_composite_score(
            macro['total_score'],
            liquidity['total_score'],
            riskon['total_score'],
            momentum['total_score']
        )

        return {
            'macro': macro,
            'liquidity': liquidity,
            'riskon': riskon,
            'momentum': momentum,
            'composite': composite
        }


if __name__ == '__main__':
    # 测试代码
    import yaml

    # 加载配置
    config_path = Path(__file__).parent.parent / 'config' / 'config.yaml'
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # 创建评分器
    scorer = FourDimensionScorer(config)

    # 准备测试数据
    macro_data = {
        'pmi_new_orders': 52.3,
        'pmi_inventory': 48.7,
        'ppi_yoy': -1.23,
        'gdp_yoy': 5.2
    }

    liquidity_data = {
        'm2_yoy': 9.87,
        'margin_balance': 15234.56,
        'margin_growth': 2.3,
        'etf_flow_5d': 123.45,
        'etf_flow_10d': 245.67
    }

    riskon_data = {
        'turnover_rate': 3.45,
        'limit_up_count': 87,
        'limit_down_count': 45,
        'up_count': 2134,
        'down_count': 2456,
        'new_high_count': 123,
        'new_low_count': 89
    }

    momentum_data = {
        'index_5d_ret': 0.0123,
        'index_10d_ret': 0.0245,
        'index_20d_ret': 0.0389,
        'breadth_5d_change': 150,
        'sector_rotation_score': 65
    }

    # 测试各维度评分
    print("=" * 60)
    print("四维度评分测试")
    print("=" * 60)

    macro_result = scorer.score_macro(macro_data)
    print(f"\n宏观维度: {macro_result['total_score']} - {macro_result['label']}")
    print(f"  PMI: {macro_result['pmi_score']}, PPI: {macro_result['ppi_score']}, GDP: {macro_result['gdp_score']}")

    liquidity_result = scorer.score_liquidity(liquidity_data)
    print(f"\n流动性维度: {liquidity_result['total_score']} - {liquidity_result['label']}")
    print(f"  M2: {liquidity_result['m2_score']}, 融资: {liquidity_result['margin_score']}, ETF: {liquidity_result['etf_score']}")

    riskon_result = scorer.score_riskon(riskon_data)
    print(f"\n风险偏好维度: {riskon_result['total_score']} - {riskon_result['label']}")
    print(f"  换手: {riskon_result['turnover_score']}, 涨跌停: {riskon_result['limit_score']}, 宽度: {riskon_result['breadth_score']}")

    momentum_result = scorer.score_momentum(momentum_data)
    print(f"\n动量维度: {momentum_result['total_score']} - {momentum_result['label']}")
    print(f"  指数: {momentum_result['index_momentum_score']}, 宽度: {momentum_result['breadth_momentum_score']}, 轮动: {momentum_result['rotation_score']}")

    # 测试综合评分
    composite = scorer.compute_composite_score(
        macro_result['total_score'],
        liquidity_result['total_score'],
        riskon_result['total_score'],
        momentum_result['total_score']
    )

    print("\n" + "=" * 60)
    print("综合评分结果")
    print("=" * 60)
    print(f"\n总分: {composite['total_score']} / 100")
    print(f"建议仓位: {composite['position']}%")
    print(f"市场状态: {composite['level']}")
    print(f"\n各维度得分:")
    print(f"  宏观: {composite['breakdown']['macro']}")
    print(f"  流动性: {composite['breakdown']['liquidity']}")
    print(f"  风险偏好: {composite['breakdown']['riskon']}")
    print(f"  动量: {composite['breakdown']['momentum']}")

    print("\n✅ 四维度评分模块测试完成！")
