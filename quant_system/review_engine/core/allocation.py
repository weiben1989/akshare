"""
资产配置模块 - Asset Allocation & Position Recommendation

功能：
1. 仓位映射：综合得分 → 建议仓位
2. 风格偏好：成长/价值/平衡
3. 行业配置：基于轮动矩阵的超配/标配/低配
4. 板块推荐：大盘/中盘/小盘

作者：Claude
日期：2025-10-21
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class AssetAllocator:
    """资产配置引擎"""

    def __init__(self, config: dict):
        """
        初始化配置器

        Args:
            config: 配置字典
        """
        self.config = config

    def map_score_to_position(
        self,
        composite_score: float,
        risk_level: str = 'moderate'
    ) -> Dict[str, any]:
        """
        将综合得分映射到仓位建议

        Args:
            composite_score: 综合得分（0-100）
            risk_level: 风险偏好 'conservative' | 'moderate' | 'aggressive'

        Returns:
            {
                'equity_position': 65,  # 权益仓位（%）
                'bond_position': 20,
                'cash_position': 15,
                'action': '逐步建仓',
                'reason': '市场中性偏多，适度增配权益'
            }
        """
        # 基础仓位映射
        if composite_score >= 80:
            base_equity = 90
            action = '积极加仓'
            reason = '市场极度乐观，重配权益资产'
        elif composite_score >= 70:
            base_equity = 80
            action = '持续加仓'
            reason = '市场偏多，增配权益'
        elif composite_score >= 60:
            base_equity = 65
            action = '逐步建仓'
            reason = '市场中性偏多，适度增配权益'
        elif composite_score >= 50:
            base_equity = 50
            action = '维持仓位'
            reason = '市场中性，保持均衡配置'
        elif composite_score >= 40:
            base_equity = 35
            action = '逐步减仓'
            reason = '市场中性偏空，降低权益仓位'
        elif composite_score >= 30:
            base_equity = 20
            action = '持续减仓'
            reason = '市场偏空，大幅降低权益仓位'
        else:
            base_equity = 10
            action = '清仓观望'
            reason = '市场极度悲观，转入防御'

        # 根据风险偏好调整
        if risk_level == 'conservative':
            equity = base_equity * 0.7
        elif risk_level == 'aggressive':
            equity = min(base_equity * 1.2, 95)
        else:  # moderate
            equity = base_equity

        equity = round(equity)

        # 债券和现金配置
        remaining = 100 - equity

        if composite_score >= 60:
            # 偏多时，债券少，现金更少
            bond = round(remaining * 0.6)
            cash = remaining - bond
        elif composite_score >= 40:
            # 中性时，债券现金均衡
            bond = round(remaining * 0.5)
            cash = remaining - bond
        else:
            # 偏空时，现金多
            bond = round(remaining * 0.4)
            cash = remaining - bond

        return {
            'equity_position': equity,
            'bond_position': bond,
            'cash_position': cash,
            'action': action,
            'reason': reason
        }

    def determine_style(
        self,
        macro_score: float,
        liquidity_score: float,
        riskon_score: float
    ) -> Dict[str, any]:
        """
        确定投资风格偏好

        Args:
            macro_score: 宏观得分
            liquidity_score: 流动性得分
            riskon_score: 风险偏好得分

        Returns:
            {
                'style': 'growth' | 'value' | 'balanced',
                'preference': {
                    'growth_weight': 60,
                    'value_weight': 40
                },
                'reason': '流动性充裕+风险偏好高，偏好成长'
            }
        """
        # 成长风格得分（流动性和风险偏好主导）
        growth_score = liquidity_score * 0.5 + riskon_score * 0.5

        # 价值风格得分（宏观主导）
        value_score = macro_score * 0.6 + (100 - riskon_score) * 0.4

        # 判断风格
        if growth_score > value_score + 10:
            style = 'growth'
            growth_weight = 70
            value_weight = 30
            reason = '流动性充裕+风险偏好高，偏好成长'
        elif value_score > growth_score + 10:
            style = 'value'
            growth_weight = 30
            value_weight = 70
            reason = '宏观偏暖+风险偏好低，偏好价值'
        else:
            style = 'balanced'
            growth_weight = 50
            value_weight = 50
            reason = '市场风格均衡，成长价值兼顾'

        return {
            'style': style,
            'preference': {
                'growth_weight': growth_weight,
                'value_weight': value_weight
            },
            'reason': reason
        }

    def allocate_by_cap(
        self,
        composite_score: float,
        momentum_score: float
    ) -> Dict[str, int]:
        """
        按市值风格分配（大/中/小盘）

        Args:
            composite_score: 综合得分
            momentum_score: 动量得分

        Returns:
            {
                'large_cap': 50,  # 大盘股配置比例
                'mid_cap': 30,
                'small_cap': 20
            }
        """
        # 高分+高动量：偏小盘
        # 低分+低动量：偏大盘
        # 中性：均衡

        if composite_score >= 70 and momentum_score >= 70:
            # 市场强势，小盘占优
            return {
                'large_cap': 30,
                'mid_cap': 40,
                'small_cap': 30,
                'reason': '市场强势，中小盘占优'
            }
        elif composite_score >= 60 and momentum_score >= 60:
            # 偏强，均衡偏小
            return {
                'large_cap': 40,
                'mid_cap': 35,
                'small_cap': 25,
                'reason': '市场偏强，均衡配置'
            }
        elif composite_score >= 40:
            # 中性，偏大盘
            return {
                'large_cap': 50,
                'mid_cap': 30,
                'small_cap': 20,
                'reason': '市场中性，偏大盘防御'
            }
        else:
            # 弱势，大盘为主
            return {
                'large_cap': 60,
                'mid_cap': 25,
                'small_cap': 15,
                'reason': '市场弱势，大盘防御'
            }

    def allocate_industries(
        self,
        rotation_matrix: pd.DataFrame,
        equity_position: int
    ) -> Dict[str, List[Dict]]:
        """
        基于轮动矩阵进行行业配置

        Args:
            rotation_matrix: 包含quadrant和action列的DataFrame
            equity_position: 权益仓位（%）

        Returns:
            {
                'overweight': [
                    {'industry': '煤炭', 'weight': 12, 'reason': '配置型机会'},
                    ...
                ],
                'neutral': [...],
                'underweight': [...]
            }
        """
        if rotation_matrix is None or len(rotation_matrix) == 0:
            return {
                'overweight': [],
                'neutral': [],
                'underweight': []
            }

        # 分类行业
        配置型机会 = rotation_matrix[rotation_matrix['quadrant'] == '配置型机会']
        警惕过热 = rotation_matrix[rotation_matrix['quadrant'] == '警惕过热']
        等待拐点 = rotation_matrix[rotation_matrix['quadrant'] == '等待拐点']
        避免追高 = rotation_matrix[rotation_matrix['quadrant'] == '避免追高']

        # 超配：配置型机会
        overweight = []
        if len(配置型机会) > 0:
            # 取前5个
            top_industries = 配置型机会.head(5)
            for _, row in top_industries.iterrows():
                industry_name = row.get('industry', row.name)
                strength = row.get('strength_score', 0)

                # 权重：根据强度分配，总共不超过权益仓位的60%
                weight = round((strength / 100) * equity_position * 0.6 / len(top_industries))

                overweight.append({
                    'industry': industry_name,
                    'weight': weight,
                    'reason': '配置型机会：强势+低拥挤'
                })

        # 标配：警惕过热（少量配置）
        neutral = []
        if len(警惕过热) > 0:
            top_industries = 警惕过热.head(3)
            for _, row in top_industries.iterrows():
                industry_name = row.get('industry', row.name)
                weight = round(equity_position * 0.05)  # 每个5%

                neutral.append({
                    'industry': industry_name,
                    'weight': weight,
                    'reason': '标配：强势但拥挤，谨慎参与'
                })

        # 低配/回避：避免追高
        underweight = []
        if len(避免追高) > 0:
            bottom_industries = 避免追高.head(5)
            for _, row in bottom_industries.iterrows():
                industry_name = row.get('industry', row.name)

                underweight.append({
                    'industry': industry_name,
                    'weight': 0,
                    'reason': '回避：弱势+高拥挤'
                })

        return {
            'overweight': overweight,
            'neutral': neutral,
            'underweight': underweight
        }

    def generate_trading_plan(
        self,
        current_position: Dict[str, float],
        target_position: Dict[str, float]
    ) -> List[Dict]:
        """
        生成交易计划

        Args:
            current_position: 当前持仓 {'equity': 50, 'bond': 30, 'cash': 20}
            target_position: 目标仓位 {'equity': 65, 'bond': 20, 'cash': 15}

        Returns:
            [
                {'asset': 'equity', 'action': '买入', 'amount': 15, 'priority': 'HIGH'},
                {'asset': 'bond', 'action': '卖出', 'amount': 10, 'priority': 'MEDIUM'},
                ...
            ]
        """
        plan = []

        for asset in ['equity', 'bond', 'cash']:
            current = current_position.get(asset, 0)
            target = target_position.get(asset, 0)
            diff = target - current

            if abs(diff) >= 5:  # 差异>=5%才调整
                action = '买入' if diff > 0 else '卖出'
                amount = abs(diff)

                # 优先级
                if abs(diff) >= 15:
                    priority = 'HIGH'
                elif abs(diff) >= 10:
                    priority = 'MEDIUM'
                else:
                    priority = 'LOW'

                plan.append({
                    'asset': asset,
                    'action': action,
                    'amount': round(amount, 1),
                    'priority': priority
                })

        # 按优先级排序
        priority_order = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}
        plan = sorted(plan, key=lambda x: priority_order[x['priority']])

        return plan

    def create_full_allocation(
        self,
        composite_score: float,
        dimension_scores: Dict[str, float],
        rotation_matrix: Optional[pd.DataFrame] = None,
        risk_level: str = 'moderate'
    ) -> Dict:
        """
        生成完整的配置建议

        Args:
            composite_score: 综合得分
            dimension_scores: {
                'macro': 61,
                'liquidity': 67,
                'riskon': 55,
                'momentum': 62
            }
            rotation_matrix: 行业轮动矩阵（可选）
            risk_level: 风险偏好

        Returns:
            完整的配置方案
        """
        # 1. 仓位配置
        position = self.map_score_to_position(composite_score, risk_level)

        # 2. 风格偏好
        style = self.determine_style(
            dimension_scores['macro'],
            dimension_scores['liquidity'],
            dimension_scores['riskon']
        )

        # 3. 市值风格
        cap_allocation = self.allocate_by_cap(
            composite_score,
            dimension_scores['momentum']
        )

        # 4. 行业配置
        if rotation_matrix is not None:
            industry_allocation = self.allocate_industries(
                rotation_matrix,
                position['equity_position']
            )
        else:
            industry_allocation = {
                'overweight': [],
                'neutral': [],
                'underweight': []
            }

        return {
            'position': position,
            'style': style,
            'cap_allocation': cap_allocation,
            'industry_allocation': industry_allocation,
            'composite_score': composite_score,
            'dimension_scores': dimension_scores
        }


if __name__ == '__main__':
    # 测试代码
    import yaml

    # 加载配置
    config_path = Path(__file__).parent.parent / 'config' / 'config.yaml'
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # 创建配置器
    allocator = AssetAllocator(config)

    # 测试数据
    composite_score = 62.1
    dimension_scores = {
        'macro': 61.0,
        'liquidity': 67.2,
        'riskon': 54.5,
        'momentum': 62.0
    }

    # 创建模拟的行业轮动矩阵
    rotation_data = {
        'industry': ['煤炭', '钢铁', '有色', '电力', '建材', '化工', '医药', '消费', '科技', '金融'],
        'strength_score': [85, 78, 72, 45, 38, 55, 42, 35, 68, 60],
        'crowding_score': [35, 42, 38, 28, 55, 48, 62, 70, 52, 45],
        'quadrant': ['配置型机会', '配置型机会', '配置型机会', '等待拐点', '等待拐点',
                     '警惕过热', '避免追高', '避免追高', '警惕过热', '警惕过热']
    }
    rotation_matrix = pd.DataFrame(rotation_data)

    # 测试完整配置
    print("=" * 70)
    print("资产配置测试")
    print("=" * 70)

    allocation = allocator.create_full_allocation(
        composite_score,
        dimension_scores,
        rotation_matrix,
        risk_level='moderate'
    )

    print(f"\n综合得分: {allocation['composite_score']}")
    print("\n各维度得分:")
    for dim, score in allocation['dimension_scores'].items():
        print(f"  {dim}: {score}")

    print("\n" + "=" * 70)
    print("仓位配置")
    print("=" * 70)
    pos = allocation['position']
    print(f"权益仓位: {pos['equity_position']}%")
    print(f"债券仓位: {pos['bond_position']}%")
    print(f"现金仓位: {pos['cash_position']}%")
    print(f"操作建议: {pos['action']}")
    print(f"理由: {pos['reason']}")

    print("\n" + "=" * 70)
    print("风格偏好")
    print("=" * 70)
    sty = allocation['style']
    print(f"风格: {sty['style']}")
    print(f"成长权重: {sty['preference']['growth_weight']}%")
    print(f"价值权重: {sty['preference']['value_weight']}%")
    print(f"理由: {sty['reason']}")

    print("\n" + "=" * 70)
    print("市值风格配置")
    print("=" * 70)
    cap = allocation['cap_allocation']
    print(f"大盘: {cap['large_cap']}%")
    print(f"中盘: {cap['mid_cap']}%")
    print(f"小盘: {cap['small_cap']}%")
    print(f"理由: {cap['reason']}")

    print("\n" + "=" * 70)
    print("行业配置")
    print("=" * 70)

    print("\n🟢 超配行业:")
    for ind in allocation['industry_allocation']['overweight']:
        print(f"  {ind['industry']}: {ind['weight']}% - {ind['reason']}")

    print("\n🟡 标配行业:")
    for ind in allocation['industry_allocation']['neutral']:
        print(f"  {ind['industry']}: {ind['weight']}% - {ind['reason']}")

    print("\n🔴 低配/回避行业:")
    for ind in allocation['industry_allocation']['underweight']:
        print(f"  {ind['industry']}: {ind['weight']}% - {ind['reason']}")

    # 测试交易计划
    print("\n" + "=" * 70)
    print("交易计划生成")
    print("=" * 70)

    current_pos = {'equity': 50, 'bond': 30, 'cash': 20}
    target_pos = {
        'equity': pos['equity_position'],
        'bond': pos['bond_position'],
        'cash': pos['cash_position']
    }

    plan = allocator.generate_trading_plan(current_pos, target_pos)

    print("\n从当前仓位调整到目标仓位:")
    print(f"当前: 权益{current_pos['equity']}% 债券{current_pos['bond']}% 现金{current_pos['cash']}%")
    print(f"目标: 权益{target_pos['equity']}% 债券{target_pos['bond']}% 现金{target_pos['cash']}%")

    print("\n调整计划:")
    for action in plan:
        print(f"  [{action['priority']}] {action['asset']}: {action['action']} {action['amount']}%")

    print("\n✅ 资产配置模块测试完成！")
