"""
报告渲染模块 - Report Rendering (Markdown + JSON)

功能：
1. 生成Markdown格式日度复盘报告
2. 生成JSON格式结构化数据
3. 三段式报告：利好因素、利空因素、结论与建议

作者：Claude
日期：2025-10-21
"""

import json
import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class ReportRenderer:
    """报告渲染器"""

    def __init__(self, config: dict):
        """
        初始化渲染器

        Args:
            config: 配置字典
        """
        self.config = config

    def render_markdown(
        self,
        date: str,
        indices: Dict,
        breadth: Dict,
        scores: Dict,
        allocation: Dict,
        factor_summary: Optional[pd.DataFrame] = None,
        industry_rotation: Optional[pd.DataFrame] = None
    ) -> str:
        """
        生成Markdown格式报告

        Args:
            date: 日期 '2025-10-21'
            indices: 指数数据
            breadth: 市场宽度数据
            scores: 四维度评分结果
            allocation: 配置建议
            factor_summary: 因子汇总表
            industry_rotation: 行业轮动矩阵

        Returns:
            Markdown格式字符串
        """
        report = []

        # 标题
        report.append(f"# A股日度复盘报告")
        report.append(f"\n**日期**: {date}")
        report.append(f"\n**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("\n---\n")

        # 核心摘要
        report.append("## 📊 核心摘要\n")
        composite = scores['composite']
        report.append(f"- **市场综合得分**: {composite['total_score']} / 100")
        report.append(f"- **市场状态**: {composite['level']}")
        report.append(f"- **建议仓位**: {composite['position']}%")
        report.append(f"- **操作建议**: {allocation['position']['action']}")
        report.append("\n---\n")

        # 市场表现
        report.append("## 📈 市场表现\n")
        report.append("### 主要指数\n")
        report.append("| 指数 | 收盘价 | 涨跌幅 | 涨跌点 |")
        report.append("|------|--------|--------|--------|")

        for idx_name, idx_data in indices.items():
            close = idx_data.get('close', 0)
            change_pct = idx_data.get('change_pct', 0)
            change_pts = idx_data.get('change_pts', 0)
            arrow = "▲" if change_pct >= 0 else "▼"

            report.append(
                f"| {idx_name} | {close:.2f} | {arrow} {change_pct:+.2f}% | {change_pts:+.2f} |"
            )

        # 市场宽度
        report.append("\n### 市场宽度\n")
        up_count = breadth.get('up_count', 0)
        down_count = breadth.get('down_count', 0)
        flat_count = breadth.get('flat_count', 0)
        total = up_count + down_count + flat_count

        if total > 0:
            up_pct = up_count / total * 100
            down_pct = down_count / total * 100
            flat_pct = flat_count / total * 100

            report.append(f"- 📈 上涨: {up_count}家 ({up_pct:.1f}%)")
            report.append(f"- 📉 下跌: {down_count}家 ({down_pct:.1f}%)")
            report.append(f"- ━ 平盘: {flat_count}家 ({flat_pct:.1f}%)")

        limit_up = breadth.get('limit_up_count', 0)
        limit_down = breadth.get('limit_down_count', 0)
        report.append(f"- 🔺 涨停: {limit_up}家")
        report.append(f"- 🔻 跌停: {limit_down}家")

        report.append("\n---\n")

        # 四维度评分
        report.append("## 🎯 四维度评分\n")
        report.append("| 维度 | 得分 | 权重 | 贡献 | 状态 |")
        report.append("|------|------|------|------|------|")

        weights = {
            'macro': 0.25,
            'liquidity': 0.35,
            'riskon': 0.20,
            'momentum': 0.20
        }

        dim_names = {
            'macro': '宏观',
            'liquidity': '流动性',
            'riskon': '风险偏好',
            'momentum': '动量'
        }

        for dim_key, dim_name in dim_names.items():
            score_data = scores[dim_key]
            score = score_data['total_score']
            weight = weights[dim_key]
            contribution = score * weight
            label = score_data['label']

            report.append(
                f"| {dim_name} | {score:.1f} | {weight*100:.0f}% | {contribution:.1f} | {label} |"
            )

        report.append(f"\n**综合得分**: {composite['total_score']} / 100\n")

        # 详细分析展开
        report.append("### 详细分析\n")

        # 宏观维度
        report.append("#### 🌍 宏观维度\n")
        macro = scores['macro']
        report.append(f"- PMI得分: {macro['pmi_score']}")
        report.append(f"- PPI得分: {macro['ppi_score']}")
        report.append(f"- GDP得分: {macro['gdp_score']}")
        report.append(f"- **状态**: {macro['label']}\n")

        # 流动性维度
        report.append("#### 💧 流动性维度\n")
        liquidity = scores['liquidity']
        report.append(f"- M2得分: {liquidity['m2_score']}")
        report.append(f"- 融资得分: {liquidity['margin_score']}")
        report.append(f"- ETF流向得分: {liquidity['etf_score']}")
        report.append(f"- **状态**: {liquidity['label']}\n")

        # 风险偏好维度
        report.append("#### 🎲 风险偏好维度\n")
        riskon = scores['riskon']
        report.append(f"- 换手率得分: {riskon['turnover_score']}")
        report.append(f"- 涨跌停得分: {riskon['limit_score']}")
        report.append(f"- 市场宽度得分: {riskon['breadth_score']}")
        report.append(f"- **状态**: {riskon['label']}\n")

        # 动量维度
        report.append("#### 🚀 动量维度\n")
        momentum = scores['momentum']
        report.append(f"- 指数动量得分: {momentum['index_momentum_score']}")
        report.append(f"- 宽度动量得分: {momentum['breadth_momentum_score']}")
        report.append(f"- 轮动得分: {momentum['rotation_score']}")
        report.append(f"- **状态**: {momentum['label']}\n")

        report.append("---\n")

        # 利好因素
        bullish = self._extract_bullish_factors(scores, allocation)
        if bullish:
            report.append("## ✅ 利好因素\n")
            for i, factor in enumerate(bullish, 1):
                report.append(f"{i}. **{factor['title']}**: {factor['description']}")
            report.append("\n")

        # 利空因素
        bearish = self._extract_bearish_factors(scores, allocation)
        if bearish:
            report.append("## ⚠️ 利空因素\n")
            for i, factor in enumerate(bearish, 1):
                report.append(f"{i}. **{factor['title']}**: {factor['description']}")
            report.append("\n")

        report.append("---\n")

        # 投资建议
        report.append("## 💡 结论与建议\n")

        report.append("### 仓位配置\n")
        pos = allocation['position']
        report.append(f"- **权益仓位**: {pos['equity_position']}%")
        report.append(f"- **债券仓位**: {pos['bond_position']}%")
        report.append(f"- **现金仓位**: {pos['cash_position']}%")
        report.append(f"- **操作**: {pos['action']}")
        report.append(f"- **理由**: {pos['reason']}\n")

        report.append("### 风格偏好\n")
        style = allocation['style']
        report.append(f"- **风格**: {style['style'].upper()}")
        report.append(f"- **成长权重**: {style['preference']['growth_weight']}%")
        report.append(f"- **价值权重**: {style['preference']['value_weight']}%")
        report.append(f"- **理由**: {style['reason']}\n")

        report.append("### 市值配置\n")
        cap = allocation['cap_allocation']
        report.append(f"- **大盘股**: {cap['large_cap']}%")
        report.append(f"- **中盘股**: {cap['mid_cap']}%")
        report.append(f"- **小盘股**: {cap['small_cap']}%")
        report.append(f"- **理由**: {cap['reason']}\n")

        # 行业配置
        if allocation['industry_allocation']['overweight']:
            report.append("### 行业配置\n")

            report.append("#### 🟢 超配行业\n")
            for ind in allocation['industry_allocation']['overweight']:
                report.append(f"- **{ind['industry']}** ({ind['weight']}%): {ind['reason']}")

            if allocation['industry_allocation']['neutral']:
                report.append("\n#### 🟡 标配行业\n")
                for ind in allocation['industry_allocation']['neutral']:
                    report.append(f"- **{ind['industry']}** ({ind['weight']}%): {ind['reason']}")

            if allocation['industry_allocation']['underweight']:
                report.append("\n#### 🔴 低配/回避行业\n")
                for ind in allocation['industry_allocation']['underweight']:
                    report.append(f"- **{ind['industry']}**: {ind['reason']}")

        report.append("\n---\n")

        # 风险提示
        report.append("## ⚠️ 风险提示\n")
        report.append("1. 本报告基于量化模型生成，仅供参考，不构成投资建议")
        report.append("2. 市场存在不确定性，请根据自身风险承受能力决策")
        report.append("3. 历史数据不代表未来表现")
        report.append("4. 建议配合基本面分析和市场情绪综合判断\n")

        report.append("---\n")
        report.append(f"\n*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
        report.append(f"\n*数据来源: AKShare*")
        report.append(f"\n*Powered by A股日度复盘引擎*\n")

        return "\n".join(report)

    def _extract_bullish_factors(self, scores: Dict, allocation: Dict) -> List[Dict]:
        """提取利好因素"""
        factors = []

        # 检查各维度
        if scores['macro']['total_score'] >= 60:
            factors.append({
                'title': '宏观面偏暖',
                'description': f"宏观维度得分{scores['macro']['total_score']}，{scores['macro']['label']}"
            })

        if scores['liquidity']['total_score'] >= 60:
            factors.append({
                'title': '流动性充裕',
                'description': f"流动性维度得分{scores['liquidity']['total_score']}，{scores['liquidity']['label']}"
            })

        if scores['riskon']['total_score'] >= 60:
            factors.append({
                'title': '风险偏好回升',
                'description': f"风险偏好得分{scores['riskon']['total_score']}，{scores['riskon']['label']}"
            })

        if scores['momentum']['total_score'] >= 60:
            factors.append({
                'title': '动量向上',
                'description': f"动量维度得分{scores['momentum']['total_score']}，{scores['momentum']['label']}"
            })

        # 行业机会
        if allocation['industry_allocation']['overweight']:
            industries = [x['industry'] for x in allocation['industry_allocation']['overweight'][:3]]
            factors.append({
                'title': '行业轮动机会',
                'description': f"发现配置型机会：{', '.join(industries)}等行业强势+低拥挤"
            })

        return factors

    def _extract_bearish_factors(self, scores: Dict, allocation: Dict) -> List[Dict]:
        """提取利空因素"""
        factors = []

        # 检查各维度
        if scores['macro']['total_score'] < 50:
            factors.append({
                'title': '宏观面偏冷',
                'description': f"宏观维度得分{scores['macro']['total_score']}，{scores['macro']['label']}"
            })

        if scores['liquidity']['total_score'] < 50:
            factors.append({
                'title': '流动性收紧',
                'description': f"流动性维度得分{scores['liquidity']['total_score']}，{scores['liquidity']['label']}"
            })

        if scores['riskon']['total_score'] < 50:
            factors.append({
                'title': '风险偏好低迷',
                'description': f"风险偏好得分{scores['riskon']['total_score']}，{scores['riskon']['label']}"
            })

        if scores['momentum']['total_score'] < 50:
            factors.append({
                'title': '动量减弱',
                'description': f"动量维度得分{scores['momentum']['total_score']}，{scores['momentum']['label']}"
            })

        # 行业风险
        if allocation['industry_allocation']['underweight']:
            industries = [x['industry'] for x in allocation['industry_allocation']['underweight'][:3]]
            factors.append({
                'title': '部分行业拥挤',
                'description': f"{', '.join(industries)}等行业弱势+高拥挤，建议回避"
            })

        return factors

    def render_json(
        self,
        date: str,
        indices: Dict,
        breadth: Dict,
        scores: Dict,
        allocation: Dict,
        factor_summary: Optional[pd.DataFrame] = None,
        industry_rotation: Optional[pd.DataFrame] = None
    ) -> Dict:
        """
        生成JSON格式报告

        Returns:
            结构化的字典，可直接序列化为JSON
        """
        # 基础信息
        report = {
            'meta': {
                'date': date,
                'generated_at': datetime.now().isoformat(),
                'version': '1.0.0'
            },
            'market': {
                'indices': indices,
                'breadth': breadth
            },
            'scores': {
                'composite': scores['composite'],
                'dimensions': {
                    'macro': scores['macro'],
                    'liquidity': scores['liquidity'],
                    'riskon': scores['riskon'],
                    'momentum': scores['momentum']
                }
            },
            'allocation': allocation,
            'analysis': {
                'bullish_factors': self._extract_bullish_factors(scores, allocation),
                'bearish_factors': self._extract_bearish_factors(scores, allocation)
            }
        }

        # 添加因子汇总（如果有）
        if factor_summary is not None:
            report['factors'] = factor_summary.to_dict('records')

        # 添加行业轮动（如果有）
        if industry_rotation is not None:
            report['industry_rotation'] = industry_rotation.to_dict('records')

        return report

    def save_report(
        self,
        markdown_content: str,
        json_content: Dict,
        output_dir: Path,
        date: str
    ) -> Dict[str, Path]:
        """
        保存报告到文件

        Args:
            markdown_content: Markdown内容
            json_content: JSON内容
            output_dir: 输出目录
            date: 日期

        Returns:
            {'markdown': Path, 'json': Path}
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # 保存Markdown
        md_file = output_dir / f"report_{date}.md"
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(markdown_content)

        # 保存JSON
        json_file = output_dir / f"report_{date}.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(json_content, f, ensure_ascii=False, indent=2)

        logger.info(f"报告已保存: {md_file}, {json_file}")

        return {
            'markdown': md_file,
            'json': json_file
        }


if __name__ == '__main__':
    # 测试代码
    import yaml

    # 加载配置
    config_path = Path(__file__).parent.parent / 'config' / 'config.yaml'
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # 创建渲染器
    renderer = ReportRenderer(config)

    # 准备测试数据
    date = '2025-10-21'

    indices = {
        '上证指数': {'close': 3245.67, 'change_pct': -0.85, 'change_pts': -27.89},
        '深证成指': {'close': 10567.32, 'change_pct': 1.23, 'change_pts': 128.45},
        '创业板指': {'close': 2187.56, 'change_pct': 0.56, 'change_pts': 12.18},
        '沪深300': {'close': 3876.45, 'change_pct': -0.32, 'change_pts': -12.45}
    }

    breadth = {
        'up_count': 2134,
        'down_count': 2456,
        'flat_count': 108,
        'limit_up_count': 87,
        'limit_down_count': 45
    }

    scores = {
        'macro': {'total_score': 61.0, 'pmi_score': 70, 'ppi_score': 40, 'gdp_score': 70, 'label': '宏观偏暖'},
        'liquidity': {'total_score': 67.2, 'm2_score': 60, 'margin_score': 70, 'etf_score': 75, 'label': '流动性充裕'},
        'riskon': {'total_score': 54.5, 'turnover_score': 60, 'limit_score': 55, 'breadth_score': 50, 'high_low_score': 55, 'label': '风险偏好中性'},
        'momentum': {'total_score': 62.0, 'index_momentum_score': 65, 'breadth_momentum_score': 55, 'rotation_score': 65, 'label': '动量向上'},
        'composite': {'total_score': 62.1, 'position': 65, 'level': '中性偏多', 'breakdown': {'macro': 61.0, 'liquidity': 67.2, 'riskon': 54.5, 'momentum': 62.0}}
    }

    allocation = {
        'position': {
            'equity_position': 65,
            'bond_position': 21,
            'cash_position': 14,
            'action': '逐步建仓',
            'reason': '市场中性偏多，适度增配权益'
        },
        'style': {
            'style': 'balanced',
            'preference': {'growth_weight': 50, 'value_weight': 50},
            'reason': '市场风格均衡，成长价值兼顾'
        },
        'cap_allocation': {
            'large_cap': 40,
            'mid_cap': 35,
            'small_cap': 25,
            'reason': '市场偏强，均衡配置'
        },
        'industry_allocation': {
            'overweight': [
                {'industry': '煤炭', 'weight': 11, 'reason': '配置型机会：强势+低拥挤'},
                {'industry': '钢铁', 'weight': 10, 'reason': '配置型机会：强势+低拥挤'},
                {'industry': '有色', 'weight': 9, 'reason': '配置型机会：强势+低拥挤'}
            ],
            'neutral': [
                {'industry': '化工', 'weight': 3, 'reason': '标配：强势但拥挤，谨慎参与'}
            ],
            'underweight': [
                {'industry': '医药', 'weight': 0, 'reason': '回避：弱势+高拥挤'},
                {'industry': '消费', 'weight': 0, 'reason': '回避：弱势+高拥挤'}
            ]
        },
        'composite_score': 62.1,
        'dimension_scores': {'macro': 61.0, 'liquidity': 67.2, 'riskon': 54.5, 'momentum': 62.0}
    }

    # 生成Markdown报告
    print("=" * 80)
    print("生成Markdown报告")
    print("=" * 80)
    markdown = renderer.render_markdown(date, indices, breadth, scores, allocation)
    print(markdown)

    # 生成JSON报告
    print("\n" + "=" * 80)
    print("生成JSON报告")
    print("=" * 80)
    json_report = renderer.render_json(date, indices, breadth, scores, allocation)
    print(json.dumps(json_report, ensure_ascii=False, indent=2))

    # 保存报告
    print("\n" + "=" * 80)
    print("保存报告")
    print("=" * 80)
    output_dir = Path(__file__).parent.parent / 'output' / 'reports'
    files = renderer.save_report(markdown, json_report, output_dir, date)
    print(f"✅ Markdown: {files['markdown']}")
    print(f"✅ JSON: {files['json']}")

    print("\n✅ 报告渲染模块测试完成！")
