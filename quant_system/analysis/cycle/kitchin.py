"""
基钦周期识别引擎 (库存周期, 3-4年)
这是最高频、最实用的周期，直接指导短期配置
"""

import sys
import os
# 添加项目根目录到路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime

from utils.logger import logger
from data.storage import DataCacheManager


class KitchinCycle:
    """
    基钦周期识别 - 3-4年的库存周期

    四象限判断法：
              需求上升 | 需求下降
    库存上升  被动补库  | 主动去库
    库存下降  主动补库  | 被动去库
    """

    def __init__(self, data_fetcher=None, cache_manager: Optional[DataCacheManager] = None):
        """
        Args:
            data_fetcher: 数据获取器实例
        """
        self.data_fetcher = data_fetcher
        self.cache_manager = cache_manager
        self.data_window = 36  # 3年数据窗口（月）
        self.logger = logger

        # 历史数据缓存
        self.historical_data = {
            'inventory': [],           # 库存增速
            'demand': [],              # 需求增速
            'dates': [],               # 时间标签
            'phase': []                # 阶段编号
        }

    def fetch_data(self) -> Dict:
        """
        获取库存周期判断所需数据

        Returns:
            包含各项指标的字典
        """
        try:
            pmi_df = self._load_macro_dataframe('pmi', 'get_macro_china_pmi')
            ppi_df = self._load_macro_dataframe('ppi', 'get_macro_china_ppi')
            gdp_df = self._load_macro_dataframe('gdp', 'get_macro_china_gdp')
            social_df = self._load_macro_dataframe('social_financing', 'get_macro_china_social_financing')

            inventory_growth = self._calc_inventory_growth(social_df, pmi_df)
            demand_growth = self._calc_demand_growth(gdp_df, pmi_df)
            pmi_inventory = self._latest_value(pmi_df, ['制造业-指数', '制造业-产成品库存', '制造业-产成品库存指数'])
            pmi_new_orders = self._latest_value(pmi_df, ['制造业-同比增长', '制造业-新订单'])
            ppi_mom = self._latest_value(ppi_df, ['当月同比增长', '当月'])

            timestamp = self._infer_latest_period([pmi_df, social_df, gdp_df, ppi_df])
            self._record_numeric_history(timestamp, inventory_growth, demand_growth)

            data = {
                'timestamp': timestamp,
                'inventory_growth': inventory_growth,
                'demand_growth': demand_growth,
                'pmi_inventory': pmi_inventory,
                'pmi_new_orders': pmi_new_orders,
                'ppi_mom': ppi_mom
            }

            self.logger.info("基钦周期数据获取成功（使用真实宏观数据）")
            return data

        except Exception as e:
            self.logger.error(f"基钦周期数据获取失败: {str(e)}", exc_info=True)
            return {}

    def identify_phase(self, inventory_growth: float = None,
                       demand_growth: float = None,
                       timestamp: Optional[str] = None) -> Dict:
        """
        判断当前处于库存周期的哪个阶段

        四象限识别：
        1. 被动补库：需求↑ 库存↑ (经济复苏初期)
        2. 主动补库：需求↑ 库存↓ (经济繁荣期)
        3. 被动去库：需求↓ 库存↓ (经济衰退期)
        4. 主动去库：需求↓ 库存↑ (经济萧条期)

        Args:
            inventory_growth: 库存增速（如果不提供则自动获取）
            demand_growth: 需求增速（如果不提供则自动获取）

        Returns:
            包含周期信息的字典
        """
        # 如果未提供数据，则获取最新数据
        if inventory_growth is None or demand_growth is None:
            data = self.fetch_data()
            inventory_growth = data.get('inventory_growth', 0)
            demand_growth = data.get('demand_growth', 0)
            timestamp = data.get('timestamp')
        else:
            # 外部传入数据时也补齐历史缓存
            timestamp = timestamp or datetime.now().strftime('%Y-%m-%d')
            self._record_numeric_history(timestamp, inventory_growth, demand_growth)

        # 需求方向：正为上升，负为下降
        demand_direction = 1 if demand_growth > 0 else -1

        # 库存方向：正为上升，负为下降
        inventory_direction = 1 if inventory_growth > 0 else -1

        # 四象限映射
        phase_mapping = {
            (1, 1): ('被动补库', 1),    # 需求↑ 库存↑
            (1, -1): ('主动补库', 2),   # 需求↑ 库存↓
            (-1, -1): ('被动去库', 3),  # 需求↓ 库存↓
            (-1, 1): ('主动去库', 4)    # 需求↓ 库存↑
        }

        phase_name, phase_code = phase_mapping[(demand_direction, inventory_direction)]

        self._record_phase_history(timestamp, phase_code)

        # 计算周期进度（0-1，表示该阶段进行到什么程度）
        phase_progress = self._calc_phase_progress(phase_code)

        result = {
            'phase': phase_code,
            'phase_name': phase_name,
            'progress': phase_progress,
            'demand_growth': demand_growth,
            'inventory_growth': inventory_growth,
            'timestamp': timestamp,
            'estimated_duration': self._estimate_remaining_months(phase_code, phase_progress),
            'confidence': self._calc_confidence(demand_growth, inventory_growth)
        }

        self.logger.info(f"基钦周期识别完成: {phase_name} (进度: {phase_progress:.1%})")

        return result

    def get_sector_rotation(self, phase: int) -> Dict:
        """
        根据库存周期阶段返回行业配置建议

        Args:
            phase: 周期阶段 (1-4)

        Returns:
            行业配置建议字典
        """
        rotation_map = {
            1: {  # 被动补库
                'phase_desc': '经济复苏初期，需求改善快于供给调整',
                'best': ['煤炭', '钢铁', '有色金属', '石油石化', '化工'],
                'good': ['建筑材料', '建筑装饰', '交运'],
                'avoid': ['消费', '医药', '科技'],
                'logic': '上游资源品受益于需求回暖和库存去化',
                'recommended_position': 0.75  # 建议仓位
            },
            2: {  # 主动补库
                'phase_desc': '经济繁荣期，企业乐观加库存',
                'best': ['机械设备', '电气设备', '汽车', '家电', '电子'],
                'good': ['计算机', '传媒', '轻工制造'],
                'avoid': ['上游周期', '防御性板块'],
                'logic': '中下游制造业和可选消费最受益',
                'recommended_position': 0.85
            },
            3: {  # 被动去库
                'phase_desc': '经济衰退初期，需求走弱但库存仍高',
                'best': ['医药生物', '食品饮料', '农林牧渔', '公用事业'],
                'good': ['银行', '非银金融'],
                'avoid': ['周期股全部', '可选消费'],
                'logic': '必需消费和防御性板块相对占优',
                'recommended_position': 0.50
            },
            4: {  # 主动去库
                'phase_desc': '经济衰退深化，企业主动去库存',
                'best': ['银行', '公用事业', '黄金（商品）'],
                'good': ['医药', '必需消费'],
                'avoid': ['制造业', '周期股'],
                'logic': '现金为王，配置债券或等待底部',
                'recommended_position': 0.30
            }
        }

        return rotation_map.get(phase, rotation_map[1])

    def get_timing_signal(self, phase: int, progress: float) -> Dict:
        """
        基于库存周期的择时信号

        Args:
            phase: 周期阶段
            progress: 阶段进度

        Returns:
            择时信号字典
        """
        # 重点关注周期切换时点
        if phase == 4 and progress > 0.7:
            # 主动去库末期 → 即将转向被动补库
            return {
                'signal': 'STRONG_BUY',
                'reason': '库存周期即将见底，布局周期股',
                'target_position': 0.85,
                'focus_sectors': ['上游资源', '建材', '化工'],
                'urgency': 'HIGH'
            }
        elif phase == 2 and progress > 0.7:
            # 主动补库末期 → 即将转向被动去库
            return {
                'signal': 'REDUCE',
                'reason': '库存周期接近顶部，降低周期股仓位',
                'target_position': 0.60,
                'focus_sectors': ['医药', '消费', '公用事业'],
                'urgency': 'HIGH'
            }
        elif phase == 1:
            # 被动补库阶段
            return {
                'signal': 'BUY',
                'reason': '需求回升，配置上游周期',
                'target_position': 0.75,
                'focus_sectors': ['煤炭', '有色', '钢铁'],
                'urgency': 'MEDIUM'
            }
        elif phase == 3:
            # 被动去库阶段
            return {
                'signal': 'DEFENSIVE',
                'reason': '需求下行，转向防御',
                'target_position': 0.50,
                'focus_sectors': ['食品饮料', '医药', '公用事业'],
                'urgency': 'MEDIUM'
            }
        else:
            return {
                'signal': 'HOLD',
                'reason': '周期中段，维持现有配置',
                'target_position': 0.70,
                'focus_sectors': [],
                'urgency': 'LOW'
            }

    def get_history(self, window: int = 36) -> pd.DataFrame:
        """返回历史数据用于可视化。"""

        df = pd.DataFrame({
            'period': self.historical_data['dates'],
            'inventory_growth': self.historical_data['inventory'],
            'demand_growth': self.historical_data['demand'],
            'phase': self.historical_data['phase']
        })

        if df.empty:
            return df

        df = df.tail(window).copy()
        df['phase_name'] = df['phase'].map({
            1: '被动补库',
            2: '主动补库',
            3: '被动去库',
            4: '主动去库'
        })
        df['date'] = pd.to_datetime(df['period'], errors='coerce')
        return df.reset_index(drop=True)

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

    def _series_yoy(self, series: pd.Series) -> float:
        if series is None or series.empty:
            return np.nan

        if len(series) > 12:
            prev = series.iloc[-13]
            if prev:
                return float((series.iloc[-1] - prev) / abs(prev) * 100)

        if len(series) > 1:
            prev = series.iloc[-2]
            if prev:
                return float((series.iloc[-1] - prev) / abs(prev) * 100)

        return np.nan

    def _series_pct_change(self, series: pd.Series, periods: int = 1) -> float:
        if series is None or series.empty or len(series) <= periods:
            return np.nan

        base = series.iloc[-periods - 1]
        if base:
            return float((series.iloc[-1] - base) / abs(base))
        return np.nan

    def _calc_inventory_growth(self, social_df: pd.DataFrame, pmi_df: pd.DataFrame) -> float:
        social_series = self._prepare_series(social_df, ['社会融资规模增量', '当月值'])
        value = self._series_yoy(social_series)

        if np.isnan(value):
            pmi_series = self._prepare_series(pmi_df, ['制造业-指数'])
            value = self._series_pct_change(pmi_series, periods=1)
            if not np.isnan(value):
                value *= 100

        return float(np.nan_to_num(value, nan=0.0))

    def _calc_demand_growth(self, gdp_df: pd.DataFrame, pmi_df: pd.DataFrame) -> float:
        gdp_series = self._prepare_series(gdp_df, ['国内生产总值-同比增长', 'GDP同比增长'])
        if not gdp_series.empty:
            value = gdp_series.iloc[-1]
            return float(np.nan_to_num(value, nan=0.0))

        pmi_series = self._prepare_series(pmi_df, ['制造业-指数'])
        value = self._series_pct_change(pmi_series, periods=3)
        if not np.isnan(value):
            value *= 100
        return float(np.nan_to_num(value, nan=0.0))

    def _latest_value(self, df: pd.DataFrame, candidates: List[str]) -> float:
        series = self._prepare_series(df, candidates)
        if series.empty:
            return 0.0
        return float(np.nan_to_num(series.iloc[-1], nan=0.0))

    def _infer_latest_period(self, dfs: List[pd.DataFrame]) -> str:
        for df in dfs:
            if df is None or df.empty:
                continue
            for column in ['日期', 'date', '月份', '季度', '时间', '统计期', 'period', 'TRADE_DATE', '交易日']:
                if column in df.columns:
                    value = df[column].dropna().iloc[-1]
                    return str(value)
        return datetime.now().strftime('%Y-%m-%d')

    def _record_numeric_history(self, timestamp: Optional[str], inventory: float, demand: float) -> None:
        timestamp = timestamp or datetime.now().strftime('%Y-%m-%d')
        history = self.historical_data

        if history['dates'] and history['dates'][-1] == timestamp:
            history['inventory'][-1] = inventory
            history['demand'][-1] = demand
            if len(history['phase']) < len(history['dates']):
                history['phase'].append(None)
        else:
            history['dates'].append(timestamp)
            history['inventory'].append(inventory)
            history['demand'].append(demand)
            history['phase'].append(None)
            self._trim_history()

    def _record_phase_history(self, timestamp: Optional[str], phase: int) -> None:
        timestamp = timestamp or datetime.now().strftime('%Y-%m-%d')
        history = self.historical_data

        if history['dates'] and history['dates'][-1] == timestamp:
            history['phase'][-1] = phase
        else:
            history['dates'].append(timestamp)
            history['inventory'].append(np.nan)
            history['demand'].append(np.nan)
            history['phase'].append(phase)
            self._trim_history()

    def _trim_history(self) -> None:
        for key in self.historical_data:
            values = self.historical_data[key]
            if len(values) > self.data_window:
                self.historical_data[key] = values[-self.data_window:]

    def _calc_phase_progress(self, phase: int) -> float:
        phases = self.historical_data.get('phase', [])
        if not phases:
            return 0.5

        count = 0
        for p in reversed(phases):
            if p is None:
                continue
            if p == phase:
                count += 1
            else:
                break

        if count == 0:
            return 0.35

        avg_duration = {
            1: 9,
            2: 12,
            3: 9,
            4: 9
        }
        total_months = avg_duration.get(phase, 9)
        progress = min(count / max(total_months, 1), 1.0)
        return float(max(0.05, progress))

    def _estimate_remaining_months(self, phase: int, progress: float) -> int:
        """
        估计当前阶段还剩余的月数

        Args:
            phase: 当前阶段
            progress: 当前进度

        Returns:
            剩余月数
        """
        # 每个阶段平均持续时间（月）
        avg_duration = {
            1: 9,   # 被动补库
            2: 12,  # 主动补库
            3: 9,   # 被动去库
            4: 9    # 主动去库
        }

        total_months = avg_duration.get(phase, 9)
        elapsed_months = total_months * progress
        remaining = total_months - elapsed_months

        return int(max(0, remaining))

    def _calc_confidence(self, demand_growth: float, inventory_growth: float) -> float:
        """
        计算判断的置信度

        Args:
            demand_growth: 需求增速
            inventory_growth: 库存增速

        Returns:
            置信度 (0-1)
        """
        demand_series = np.array([x for x in self.historical_data['demand'] if x is not None and not np.isnan(x)])
        inventory_series = np.array([x for x in self.historical_data['inventory'] if x is not None and not np.isnan(x)])

        demand_strength = self._signal_strength(demand_growth, demand_series)
        inventory_strength = self._signal_strength(inventory_growth, inventory_series)

        alignment = 1.0 if demand_growth * inventory_growth >= 0 else 0.6
        confidence = (demand_strength + inventory_strength) / 2 * alignment

        return float(np.clip(confidence, 0.1, 0.99))

    def _signal_strength(self, value: float, history: np.ndarray) -> float:
        if history.size < 3:
            return min(abs(value) / 5.0, 1.0)

        std = np.nanstd(history)
        if not std or np.isnan(std):
            return min(abs(value) / 5.0, 1.0)

        strength = abs(value) / (std * 2)
        return float(np.clip(strength, 0, 1.2))

    def get_historical_performance(self, phase: int) -> Dict:
        """
        获取该阶段的历史表现统计

        Args:
            phase: 周期阶段

        Returns:
            历史表现统计
        """
        # 模拟历史表现数据
        performance_map = {
            1: {
                'avg_return': 0.15,
                'win_rate': 0.72,
                'max_return': 0.45,
                'max_drawdown': -0.12,
                'best_sectors': ['有色金属', '煤炭', '化工']
            },
            2: {
                'avg_return': 0.22,
                'win_rate': 0.78,
                'max_return': 0.60,
                'max_drawdown': -0.15,
                'best_sectors': ['电子', '计算机', '机械设备']
            },
            3: {
                'avg_return': -0.08,
                'win_rate': 0.35,
                'max_return': 0.10,
                'max_drawdown': -0.25,
                'best_sectors': ['医药生物', '食品饮料', '公用事业']
            },
            4: {
                'avg_return': -0.15,
                'win_rate': 0.25,
                'max_return': 0.05,
                'max_drawdown': -0.30,
                'best_sectors': ['银行', '公用事业', '国债']
            }
        }

        return performance_map.get(phase, performance_map[1])
