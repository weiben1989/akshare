#!/usr/bin/env python3
"""
A股日度复盘引擎 - 主程序

功能：
1. 从AKShare获取最新数据
2. 计算多周期因子
3. 四维度评分
4. 生成资产配置建议
5. 渲染Markdown和JSON报告

作者：Claude
日期：2025-10-21

用法:
    python run_daily.py                    # 分析今天
    python run_daily.py --date 2025-10-20  # 分析指定日期
    python run_daily.py --help             # 查看帮助
"""

import argparse
import logging
import sys
import yaml
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# 添加当前目录到路径（支持直接导入）
sys.path.insert(0, str(Path(__file__).parent))

from providers.akshare_provider import AKShareProvider
from core.factors import FactorCalculator, create_factor_summary
from core.scoring import FourDimensionScorer
from core.allocation import AssetAllocator
from reporting.renderer import ReportRenderer

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('review_engine.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class DailyReviewEngine:
    """日度复盘引擎"""

    def __init__(self, config_path: Path):
        """
        初始化引擎

        Args:
            config_path: 配置文件路径
        """
        # 加载配置
        with open(config_path) as f:
            self.config = yaml.safe_load(f)

        logger.info("配置加载成功")

        # 初始化各组件
        self.provider = AKShareProvider(self.config)
        self.factor_calc = FactorCalculator(self.config)
        self.scorer = FourDimensionScorer(self.config)
        self.allocator = AssetAllocator(self.config)
        self.renderer = ReportRenderer(self.config)

        logger.info("所有组件初始化完成")

    def run(self, date: str = None, save_report: bool = True) -> dict:
        """
        运行日度复盘

        Args:
            date: 分析日期，格式'YYYY-MM-DD'，默认今天
            save_report: 是否保存报告到文件

        Returns:
            包含所有分析结果的字典
        """
        # 确定日期
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        logger.info(f"=" * 80)
        logger.info(f"开始分析日期: {date}")
        logger.info(f"=" * 80)

        try:
            # 步骤1: 获取数据
            logger.info("步骤1: 从AKShare获取数据...")
            self.provider.fetch_and_save_all(date)
            logger.info("✅ 数据获取完成")

            # 步骤2: 加载数据用于分析
            logger.info("步骤2: 加载数据...")
            data = self._load_data(date)
            logger.info("✅ 数据加载完成")

            # 步骤3: 计算因子
            logger.info("步骤3: 计算多周期因子...")
            factors = self._calculate_factors(data)
            logger.info("✅ 因子计算完成")

            # 步骤4: 四维度评分
            logger.info("步骤4: 计算四维度评分...")
            scores = self._calculate_scores(data, factors)
            logger.info(f"✅ 评分完成 - 综合得分: {scores['composite']['total_score']}")

            # 步骤5: 行业轮动分析
            logger.info("步骤5: 行业轮动分析...")
            rotation_matrix = self._analyze_industry_rotation(data)
            logger.info(f"✅ 行业分析完成 - 共{len(rotation_matrix)}个行业")

            # 步骤6: 资产配置建议
            logger.info("步骤6: 生成资产配置建议...")
            allocation = self.allocator.create_full_allocation(
                scores['composite']['total_score'],
                scores['composite']['breakdown'],
                rotation_matrix
            )
            logger.info(f"✅ 配置完成 - 建议仓位: {allocation['position']['equity_position']}%")

            # 步骤7: 生成报告
            logger.info("步骤7: 生成报告...")
            markdown = self.renderer.render_markdown(
                date,
                data['indices'],
                data['breadth'],
                scores,
                allocation,
                factors.get('summary'),
                rotation_matrix
            )
            json_report = self.renderer.render_json(
                date,
                data['indices'],
                data['breadth'],
                scores,
                allocation,
                factors.get('summary'),
                rotation_matrix
            )

            # 保存报告
            if save_report:
                output_dir = Path(__file__).parent / 'output' / 'reports'
                files = self.renderer.save_report(markdown, json_report, output_dir, date)
                logger.info(f"✅ 报告已保存:")
                logger.info(f"   Markdown: {files['markdown']}")
                logger.info(f"   JSON: {files['json']}")

            logger.info("=" * 80)
            logger.info("✅ 复盘完成！")
            logger.info("=" * 80)

            return {
                'date': date,
                'data': data,
                'factors': factors,
                'scores': scores,
                'rotation': rotation_matrix,
                'allocation': allocation,
                'reports': {
                    'markdown': markdown,
                    'json': json_report
                }
            }

        except Exception as e:
            logger.error(f"❌ 复盘失败: {e}", exc_info=True)
            raise

    def _load_data(self, date: str) -> dict:
        """从数据库加载数据"""
        conn = self.provider.get_connection()

        # 加载指数数据
        indices_df = pd.read_sql(
            "SELECT * FROM indices WHERE date = ? ORDER BY name",
            conn,
            params=(date,)
        )

        indices = {}
        for _, row in indices_df.iterrows():
            indices[row['name']] = {
                'close': row['close'],
                'change_pct': row.get('change_pct', 0),
                'change_pts': row.get('change_pts', 0)
            }

        # 加载市场宽度数据
        breadth_row = pd.read_sql(
            "SELECT * FROM breadth WHERE date = ?",
            conn,
            params=(date,)
        )

        if len(breadth_row) > 0:
            breadth = breadth_row.iloc[0].to_dict()
        else:
            breadth = {
                'up_count': 0,
                'down_count': 0,
                'flat_count': 0,
                'limit_up_count': 0,
                'limit_down_count': 0
            }

        # 加载宏观数据
        macro_row = pd.read_sql(
            "SELECT * FROM macro WHERE date <= ? ORDER BY date DESC LIMIT 1",
            conn,
            params=(date,)
        )

        if len(macro_row) > 0:
            macro = macro_row.iloc[0].to_dict()
        else:
            macro = {
                'pmi_new_orders': 50,
                'pmi_inventory': 50,
                'ppi_yoy': 0
            }

        # 加载融资融券数据
        margin_row = pd.read_sql(
            "SELECT * FROM margin WHERE date <= ? ORDER BY date DESC LIMIT 1",
            conn,
            params=(date,)
        )

        if len(margin_row) > 0:
            margin = margin_row.iloc[0].to_dict()
        else:
            margin = {
                'balance': 15000,
                'buy_amount': 500
            }

        # 加载ETF流向数据
        etf_df = pd.read_sql(
            "SELECT * FROM etf_flows WHERE date <= ? ORDER BY date DESC LIMIT 5",
            conn,
            params=(date,)
        )

        if len(etf_df) > 0:
            etf_flow_5d = etf_df['total_flow'].sum()
        else:
            etf_flow_5d = 0

        # 加载行业数据
        industry_df = pd.read_sql(
            "SELECT * FROM industry WHERE date = ?",
            conn,
            params=(date,)
        )

        conn.close()

        return {
            'indices': indices,
            'breadth': breadth,
            'macro': macro,
            'margin': margin,
            'etf_flow_5d': etf_flow_5d,
            'industry': industry_df
        }

    def _calculate_factors(self, data: dict) -> dict:
        """计算因子"""
        # 获取指数历史数据用于趋势计算
        # 这里简化处理，实际应从Parquet读取
        conn = self.provider.get_connection()

        # 读取最近60天的指数数据
        sixty_days_ago = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')

        # 读取上证指数历史
        sh_index = pd.read_sql(
            "SELECT date, close FROM indices WHERE name = '上证指数' AND date >= ? ORDER BY date",
            conn,
            params=(sixty_days_ago,),
            parse_dates=['date'],
            index_col='date'
        )

        conn.close()

        if len(sh_index) < 30:
            logger.warning("历史数据不足，使用当前数据")
            # 使用模拟数据
            dates = pd.date_range(end=datetime.now(), periods=60, freq='D')
            sh_close = data['indices'].get('上证指数', {}).get('close', 3000)
            sh_index = pd.DataFrame({
                'close': [sh_close] * 60
            }, index=dates)

        # 计算趋势
        trends = self.factor_calc.compute_multi_horizon(sh_index['close'])
        label = self.factor_calc.trend_label(trends)
        momentum = self.factor_calc.compute_momentum(sh_index['close'])

        return {
            'trends': trends,
            'label': label,
            'momentum': momentum,
            'summary': None  # 可以扩展为完整的DataFrame
        }

    def _calculate_scores(self, data: dict, factors: dict) -> dict:
        """计算四维度评分"""
        # 准备宏观数据
        macro_data = {
            'pmi_new_orders': data['macro'].get('pmi_new_orders', 50),
            'pmi_inventory': data['macro'].get('pmi_inventory', 50),
            'ppi_yoy': data['macro'].get('ppi_yoy', 0)
        }

        # 准备流动性数据
        # 计算融资余额增速（需要历史数据，这里简化）
        liquidity_data = {
            'm2_yoy': 9.87,  # 应从宏观数据获取
            'margin_balance': data['margin'].get('balance', 15000),
            'margin_growth': 2.3,  # 应计算实际增速
            'etf_flow_5d': data['etf_flow_5d']
        }

        # 准备风险偏好数据
        breadth = data['breadth']
        total_amount = breadth.get('up_count', 0) + breadth.get('down_count', 0)
        if total_amount > 0:
            turnover_rate = 3.0  # 应从实际数据计算
        else:
            turnover_rate = 2.5

        riskon_data = {
            'turnover_rate': turnover_rate,
            'limit_up_count': breadth.get('limit_up_count', 0),
            'limit_down_count': breadth.get('limit_down_count', 0),
            'up_count': breadth.get('up_count', 0),
            'down_count': breadth.get('down_count', 0)
        }

        # 准备动量数据
        momentum_data = {
            'index_5d_ret': factors['momentum'].get('5d_ret', 0),
            'index_10d_ret': factors['momentum'].get('10d_ret', 0),
            'index_20d_ret': factors['momentum'].get('20d_ret', 0),
            'breadth_5d_change': 0,  # 应计算实际变化
            'sector_rotation_score': 50  # 应从行业轮动计算
        }

        # 计算所有维度得分
        return self.scorer.score_all(
            macro_data,
            liquidity_data,
            riskon_data,
            momentum_data
        )

    def _analyze_industry_rotation(self, data: dict) -> pd.DataFrame:
        """分析行业轮动"""
        industry_df = data['industry']

        if len(industry_df) == 0:
            logger.warning("没有行业数据，返回空矩阵")
            return pd.DataFrame()

        # 计算行业强度
        industry_df = self.factor_calc.compute_industry_strength(
            industry_df,
            return_col='avg_return',
            flow_col='net_flow'
        )

        # 计算拥挤度
        industry_df = self.factor_calc.compute_industry_crowding(
            industry_df,
            turnover_col='avg_turnover',
            limit_up_col='limit_up_count'
        )

        # 创建四象限矩阵
        rotation_matrix = self.factor_calc.create_industry_rotation_matrix(industry_df)

        return rotation_matrix


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='A股日度复盘引擎')
    parser.add_argument(
        '--date',
        type=str,
        help='分析日期 (YYYY-MM-DD)，默认今天'
    )
    parser.add_argument(
        '--config',
        type=str,
        default='config/config.yaml',
        help='配置文件路径'
    )
    parser.add_argument(
        '--no-save',
        action='store_true',
        help='不保存报告到文件'
    )

    args = parser.parse_args()

    # 配置文件路径
    config_path = Path(__file__).parent / args.config

    if not config_path.exists():
        logger.error(f"配置文件不存在: {config_path}")
        sys.exit(1)

    # 创建引擎
    engine = DailyReviewEngine(config_path)

    # 运行复盘
    try:
        result = engine.run(
            date=args.date,
            save_report=not args.no_save
        )

        # 打印关键信息
        print("\n" + "=" * 80)
        print("复盘结果摘要")
        print("=" * 80)
        print(f"日期: {result['date']}")
        print(f"综合得分: {result['scores']['composite']['total_score']}")
        print(f"市场状态: {result['scores']['composite']['level']}")
        print(f"建议仓位: {result['allocation']['position']['equity_position']}%")
        print(f"操作建议: {result['allocation']['position']['action']}")
        print("=" * 80)

        # 打印报告预览
        if not args.no_save:
            print("\n报告已生成，查看完整内容:")
            output_dir = Path(__file__).parent / 'output' / 'reports'
            print(f"Markdown: {output_dir}/report_{result['date']}.md")
            print(f"JSON: {output_dir}/report_{result['date']}.json")

    except Exception as e:
        logger.error(f"运行失败: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
