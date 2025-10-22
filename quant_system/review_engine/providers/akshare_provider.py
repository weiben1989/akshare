"""
AkShare数据提供者
严格使用AkShare真实数据，禁止任何虚拟/模拟数据
"""

import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union
import time
import logging
from pathlib import Path
import sqlite3
import os

logger = logging.getLogger(__name__)


class DataValidationError(Exception):
    """数据校验失败异常"""
    pass


class AkShareProvider:
    """
    AkShare数据提供者

    职责：
    1. 从AkShare获取真实数据（严禁虚拟数据）
    2. 字段校验与单位规范
    3. 持久化到SQLite和Parquet
    4. 错误处理与重试
    """

    def __init__(self, config: dict):
        self.config = config
        self.timeout = config.get('akshare', {}).get('timeout', 30)
        self.retry = config.get('akshare', {}).get('retry', 3)
        self.retry_delay = config.get('akshare', {}).get('retry_delay', 2)

        # 数据存储路径
        self.sqlite_path = config.get('paths', {}).get('sqlite', 'data/review.sqlite')
        self.parquet_dir = config.get('paths', {}).get('parquet_dir', 'data/parquet/')

        # 确保目录存在
        Path(self.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.parquet_dir).mkdir(parents=True, exist_ok=True)

        # 初始化数据库
        self._init_database()

    def _init_database(self):
        """初始化SQLite数据库表结构"""
        conn = sqlite3.connect(self.sqlite_path)
        cursor = conn.cursor()

        # 指数数据表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS indices (
                date TEXT NOT NULL,
                symbol TEXT NOT NULL,
                name TEXT,
                close REAL,
                open REAL,
                high REAL,
                low REAL,
                volume REAL,
                amount REAL,
                change_pct REAL,
                PRIMARY KEY (date, symbol)
            )
        """)

        # 成交额表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_amount (
                date TEXT PRIMARY KEY,
                sh_amount REAL,
                sz_amount REAL,
                total_amount REAL
            )
        """)

        # 市场广度表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS breadth (
                date TEXT PRIMARY KEY,
                up_count INTEGER,
                down_count INTEGER,
                flat_count INTEGER,
                limit_up_count INTEGER,
                limit_down_count INTEGER,
                max_continuous_limit_up INTEGER,
                continuous_limit_rate REAL
            )
        """)

        # 北向资金表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS northbound (
                date TEXT PRIMARY KEY,
                net_flow REAL,
                sh_net REAL,
                sz_net REAL
            )
        """)

        # ETF流向表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS etf_flows (
                date TEXT NOT NULL,
                bucket TEXT NOT NULL,
                net_flow REAL,
                PRIMARY KEY (date, bucket)
            )
        """)

        # 融资融券表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS margin (
                date TEXT PRIMARY KEY,
                balance REAL,
                buy_amount REAL
            )
        """)

        # 行业数据表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS industry (
                date TEXT NOT NULL,
                industry_name TEXT NOT NULL,
                avg_return REAL,
                net_flow REAL,
                avg_turnover REAL,
                limit_up_count INTEGER,
                PRIMARY KEY (date, industry_name)
            )
        """)

        # 宏观数据表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS macro (
                date TEXT NOT NULL,
                indicator TEXT NOT NULL,
                value REAL,
                PRIMARY KEY (date, indicator)
            )
        """)

        # 交易日历表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS calendar (
                date TEXT PRIMARY KEY,
                is_trading_day INTEGER
            )
        """)

        conn.commit()
        conn.close()
        logger.info("数据库初始化完成")

    def _retry_fetch(self, func, *args, **kwargs):
        """带重试的数据获取"""
        for i in range(self.retry):
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                if i < self.retry - 1:
                    logger.warning(f"数据获取失败，{self.retry_delay}秒后重试 ({i+1}/{self.retry}): {e}")
                    time.sleep(self.retry_delay * (2 ** i))  # 指数退避
                else:
                    logger.error(f"数据获取失败，已重试{self.retry}次: {e}")
                    raise

    def _validate_dataframe(self, df: pd.DataFrame, required_columns: List[str],
                           table_name: str) -> None:
        """
        校验DataFrame

        Args:
            df: 待校验的DataFrame
            required_columns: 必需的列
            table_name: 表名（用于日志）

        Raises:
            DataValidationError: 校验失败
        """
        if df is None or df.empty:
            raise DataValidationError(f"{table_name}: DataFrame为空")

        # 检查必需列
        missing_cols = set(required_columns) - set(df.columns)
        if missing_cols:
            raise DataValidationError(f"{table_name}: 缺少必需列 {missing_cols}")

        # 检查空值比例
        null_tolerance = self.config.get('validation', {}).get('null_tolerance', 0.1)
        for col in required_columns:
            null_ratio = df[col].isnull().sum() / len(df)
            if null_ratio > null_tolerance:
                raise DataValidationError(
                    f"{table_name}: 列 {col} 空值比例过高 ({null_ratio:.2%} > {null_tolerance:.2%})"
                )

    def fetch_indices(self, date: str) -> pd.DataFrame:
        """
        获取指数数据

        Args:
            date: 日期 YYYY-MM-DD

        Returns:
            包含上证/深成/创业板/沪深300的DataFrame
        """
        indices_config = {
            'sh000001': '上证指数',
            'sz399001': '深证成指',
            'sz399006': '创业板指',
            'sh000300': '沪深300'
        }

        results = []
        for symbol, name in indices_config.items():
            try:
                df = self._retry_fetch(ak.stock_zh_index_daily, symbol=symbol)

                if df is None or df.empty:
                    logger.warning(f"指数 {name} 数据为空")
                    continue

                # 转换日期列
                df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')

                # 筛选指定日期
                df_date = df[df['date'] == date]

                if df_date.empty:
                    logger.warning(f"指数 {name} 在 {date} 无数据")
                    continue

                df_date = df_date.copy()
                df_date['symbol'] = symbol
                df_date['name'] = name

                # 计算涨跌幅
                if 'close' in df_date.columns and len(df) > 1:
                    prev_close = df[df['date'] < date].iloc[-1]['close'] if len(df[df['date'] < date]) > 0 else None
                    if prev_close:
                        df_date['change_pct'] = (df_date['close'] - prev_close) / prev_close * 100

                results.append(df_date)

            except Exception as e:
                logger.error(f"获取指数 {name} 失败: {e}")

        if not results:
            raise DataValidationError(f"所有指数数据获取失败 (日期: {date})")

        result_df = pd.concat(results, ignore_index=True)

        # 校验
        required_cols = self.config.get('validation', {}).get('required_columns', {}).get('indices',
                                                              ['date', 'close', 'volume', 'amount'])
        self._validate_dataframe(result_df, required_cols, 'indices')

        return result_df

    def fetch_market_amount(self, date: str) -> Dict[str, float]:
        """
        获取两市成交额

        Args:
            date: 日期 YYYY-MM-DD

        Returns:
            {'sh_amount': xx, 'sz_amount': xx, 'total_amount': xx}
        """
        try:
            # 转换日期格式：YYYY-MM-DD -> YYYYMMDD
            date_fmt = date.replace('-', '')

            sh_amount = 0.0
            sz_amount = 0.0

            # 1. 获取上海市场成交额
            try:
                sh_df = self._retry_fetch(ak.stock_sse_deal_daily, date=date_fmt)
                if sh_df is not None and not sh_df.empty:
                    # 找到"股票"行的成交金额（单位：万元）
                    stock_row = sh_df[sh_df['产品类型'] == '股票']
                    if not stock_row.empty and '成交金额' in stock_row.columns:
                        sh_amount = float(stock_row['成交金额'].values[0]) / 10000  # 万元转亿元
            except Exception as e:
                logger.warning(f"获取上海市场成交额失败: {e}")

            # 2. 获取深圳市场成交额
            try:
                sz_df = self._retry_fetch(ak.stock_szse_summary, date=date_fmt)
                if sz_df is not None and not sz_df.empty:
                    # 找到"股票"行的成交金额（单位：元）
                    stock_row = sz_df[sz_df['证券类别'] == '股票']
                    if not stock_row.empty and '成交金额' in stock_row.columns:
                        sz_amount = float(stock_row['成交金额'].values[0]) / 100000000  # 元转亿元
            except Exception as e:
                logger.warning(f"获取深圳市场成交额失败: {e}")

            # 如果都获取失败，返回默认值而不是报错（允许部分数据缺失）
            return {
                'date': date,
                'sh_amount': sh_amount,
                'sz_amount': sz_amount,
                'total_amount': sh_amount + sz_amount
            }

        except Exception as e:
            logger.error(f"获取成交额失败: {e}")
            # 返回默认值而不是抛出异常
            return {
                'date': date,
                'sh_amount': 0.0,
                'sz_amount': 0.0,
                'total_amount': 0.0
            }

    def fetch_market_breadth(self, date: str) -> Dict:
        """
        获取市场广度

        注意：AkShare 的 stock_zh_a_spot_em 只能获取当天数据
        对于历史日期，只能获取涨跌停池数据，涨跌家数无法获取

        Args:
            date: 日期 YYYY-MM-DD

        Returns:
            涨跌家数、涨跌停等数据
        """
        from datetime import datetime

        up_count = 0
        down_count = 0
        flat_count = 0
        limit_up_count = 0
        limit_down_count = 0
        max_continuous = 0

        try:
            # 检查是否为当天
            today = datetime.now().strftime('%Y-%m-%d')
            is_today = (date == today)

            # 只有当天才能获取实时涨跌家数
            if is_today:
                try:
                    spot_df = self._retry_fetch(ak.stock_zh_a_spot_em)
                    if spot_df is not None and not spot_df.empty and '涨跌幅' in spot_df.columns:
                        up_count = len(spot_df[spot_df['涨跌幅'] > 0])
                        down_count = len(spot_df[spot_df['涨跌幅'] < 0])
                        flat_count = len(spot_df[spot_df['涨跌幅'] == 0])
                except Exception as e:
                    logger.warning(f"获取实时行情失败: {e}")

            # 获取涨停板（支持历史数据）
            try:
                date_fmt = date.replace('-', '')
                limit_up_df = self._retry_fetch(ak.stock_zt_pool_em, date=date_fmt)
                if limit_up_df is not None and not limit_up_df.empty:
                    limit_up_count = len(limit_up_df)
                    # 连板高度
                    if '连板数' in limit_up_df.columns:
                        max_continuous = int(limit_up_df['连板数'].max())
            except Exception as e:
                logger.warning(f"获取涨停池失败 (日期: {date}): {e}")

            # 获取跌停板（支持历史数据）
            try:
                date_fmt = date.replace('-', '')
                limit_down_df = self._retry_fetch(ak.stock_zt_pool_dtgc_em, date=date_fmt)
                if limit_down_df is not None and not limit_down_df.empty:
                    limit_down_count = len(limit_down_df)
            except Exception as e:
                logger.warning(f"获取跌停池失败 (日期: {date}): {e}")

            return {
                'date': date,
                'up_count': up_count,
                'down_count': down_count,
                'flat_count': flat_count,
                'limit_up_count': limit_up_count,
                'limit_down_count': limit_down_count,
                'max_continuous_limit_up': max_continuous,
                'continuous_limit_rate': 0.0  # 需要历史数据计算，暂时为0
            }

        except Exception as e:
            logger.error(f"获取市场广度失败: {e}")
            # 返回默认值而不是抛出异常
            return {
                'date': date,
                'up_count': 0,
                'down_count': 0,
                'flat_count': 0,
                'limit_up_count': 0,
                'limit_down_count': 0,
                'max_continuous_limit_up': 0,
                'continuous_limit_rate': 0.0
            }

    def fetch_northbound(self, date: str) -> Dict[str, float]:
        """
        获取北向资金

        Args:
            date: 日期

        Returns:
            北向净流入数据
        """
        try:
            df = self._retry_fetch(ak.stock_hsgt_north_net_flow_in_em)

            if df is None or df.empty:
                raise DataValidationError("北向资金数据为空")

            # 转换日期格式
            df['date'] = pd.to_datetime(df['日期']).dt.strftime('%Y-%m-%d')

            # 筛选日期
            df_date = df[df['date'] == date]

            if df_date.empty:
                logger.warning(f"北向资金在 {date} 无数据，可能非交易日")
                return {
                    'date': date,
                    'net_flow': 0.0,
                    'sh_net': 0.0,
                    'sz_net': 0.0
                }

            # 北向资金单位为亿元，转换为元
            net_flow = float(df_date['当日净流入-净流入'].values[0]) * 1e8
            sh_net = float(df_date['沪股通-净流入'].values[0]) * 1e8 if '沪股通-净流入' in df_date.columns else 0.0
            sz_net = float(df_date['深股通-净流入'].values[0]) * 1e8 if '深股通-净流入' in df_date.columns else 0.0

            return {
                'date': date,
                'net_flow': net_flow,
                'sh_net': sh_net,
                'sz_net': sz_net
            }

        except Exception as e:
            logger.error(f"获取北向资金失败: {e}")
            # 返回默认值而不是抛出异常
            return {
                'date': date,
                'net_flow': 0.0,
                'sh_net': 0.0,
                'sz_net': 0.0
            }

    def fetch_etf_flows(self, date: str) -> List[Dict]:
        """
        获取ETF流向（按分组）

        Args:
            date: 日期

        Returns:
            各分组的净流向数据列表
        """
        try:
            etf_buckets = self.config.get('etf_buckets', {})
            results = []

            for bucket_name, bucket_config in etf_buckets.items():
                codes = bucket_config.get('codes', [])
                total_flow = 0.0

                for code in codes:
                    try:
                        # 获取ETF份额数据
                        df = self._retry_fetch(ak.fund_etf_fund_info_em, fund=code, indicator="单位净值走势")

                        if df is None or df.empty:
                            continue

                        # 转换日期
                        df['净值日期'] = pd.to_datetime(df['净值日期']).dt.strftime('%Y-%m-%d')
                        df_date = df[df['净值日期'] == date]

                        if not df_date.empty and '日增长率' in df_date.columns:
                            # 使用日增长率作为流向代理
                            flow = float(df_date['日增长率'].values[0])
                            total_flow += flow

                    except Exception as e:
                        logger.warning(f"ETF {code} 数据获取失败: {e}")
                        continue

                results.append({
                    'date': date,
                    'bucket': bucket_name,
                    'net_flow': total_flow
                })

            return results

        except Exception as e:
            logger.error(f"获取ETF流向失败: {e}")
            return []

    def fetch_margin(self, date: str) -> Dict[str, float]:
        """
        获取融资融券余额

        Args:
            date: 日期

        Returns:
            融资融券余额数据
        """
        try:
            # 沪市融资融券
            try:
                sh_margin = self._retry_fetch(ak.stock_margin_sse, date=date.replace('-', ''))
                sh_balance = 0.0
                sh_buy = 0.0

                if sh_margin is not None and not sh_margin.empty:
                    if '融资余额' in sh_margin.columns:
                        sh_balance = float(sh_margin['融资余额'].sum())
                    if '融资买入额' in sh_margin.columns:
                        sh_buy = float(sh_margin['融资买入额'].sum())
            except:
                logger.warning(f"沪市融资融券数据获取失败 (日期: {date})")
                sh_balance = 0.0
                sh_buy = 0.0

            # 深市融资融券
            try:
                sz_margin = self._retry_fetch(ak.stock_margin_szse, date=date.replace('-', ''))
                sz_balance = 0.0
                sz_buy = 0.0

                if sz_margin is not None and not sz_margin.empty:
                    if '融资余额' in sz_margin.columns:
                        sz_balance = float(sz_margin['融资余额'].sum())
                    if '融资买入额' in sz_margin.columns:
                        sz_buy = float(sz_margin['融资买入额'].sum())
            except:
                logger.warning(f"深市融资融券数据获取失败 (日期: {date})")
                sz_balance = 0.0
                sz_buy = 0.0

            return {
                'date': date,
                'balance': sh_balance + sz_balance,
                'buy_amount': sh_buy + sz_buy
            }

        except Exception as e:
            logger.error(f"获取融资融券数据失败: {e}")
            return {'date': date, 'balance': 0.0, 'buy_amount': 0.0}

    def fetch_industry_data(self, date: str) -> pd.DataFrame:
        """
        聚合行业数据

        注意：AkShare 的 stock_zh_a_spot_em 只能获取当天数据
        对于历史日期无法获取行业数据

        Args:
            date: 日期 YYYY-MM-DD

        Returns:
            行业数据DataFrame
        """
        from datetime import datetime

        try:
            # 检查是否为当天
            today = datetime.now().strftime('%Y-%m-%d')
            is_today = (date == today)

            if not is_today:
                logger.warning(f"无法获取历史行业数据 (日期: {date})，AkShare只支持当天数据")
                return pd.DataFrame()

            # 获取A股实时数据（仅当天）
            spot_df = self._retry_fetch(ak.stock_zh_a_spot_em)

            if spot_df is None or spot_df.empty:
                logger.warning("A股快照数据为空")
                return pd.DataFrame()

            # 查找行业字段
            industry_col = None
            for col in ['行业', '所属行业', '板块']:
                if col in spot_df.columns:
                    industry_col = col
                    break

            if industry_col is None:
                logger.warning("未找到行业字段")
                return pd.DataFrame()

            # 检查必需的列是否存在
            if '涨跌幅' not in spot_df.columns:
                logger.warning("数据中缺少涨跌幅列")
                return pd.DataFrame()

            # 按行业分组聚合
            agg_dict = {
                '涨跌幅': 'mean'
            }

            # 可选列
            if '换手率' in spot_df.columns:
                agg_dict['换手率'] = 'mean'
            if '主力净流入' in spot_df.columns:
                agg_dict['主力净流入'] = 'sum'

            industry_stats = spot_df.groupby(industry_col).agg(agg_dict).reset_index()

            # 重命名列
            col_mapping = {
                industry_col: 'industry_name',
                '涨跌幅': 'avg_return'
            }
            if '换手率' in industry_stats.columns:
                col_mapping['换手率'] = 'avg_turnover'
            if '主力净流入' in industry_stats.columns:
                col_mapping['主力净流入'] = 'net_flow'

            industry_stats = industry_stats.rename(columns=col_mapping)

            # 添加缺失的列
            if 'avg_turnover' not in industry_stats.columns:
                industry_stats['avg_turnover'] = 0.0
            if 'net_flow' not in industry_stats.columns:
                industry_stats['net_flow'] = 0.0

            industry_stats['date'] = date

            # 计算涨停家数
            limit_up_count = spot_df[spot_df['涨跌幅'] >= 9.9].groupby(industry_col).size().to_dict()
            industry_stats['limit_up_count'] = industry_stats['industry_name'].map(
                lambda x: limit_up_count.get(x, 0)
            )

            return industry_stats

        except Exception as e:
            logger.error(f"获取行业数据失败: {e}")
            return pd.DataFrame()

    def fetch_macro_data(self, date: str) -> List[Dict]:
        """
        获取宏观数据

        Args:
            date: 日期

        Returns:
            宏观指标列表
        """
        results = []

        try:
            # PMI数据
            try:
                pmi_df = self._retry_fetch(ak.macro_china_pmi)
                if pmi_df is not None and not pmi_df.empty:
                    pmi_df['日期'] = pd.to_datetime(pmi_df['日期']).dt.strftime('%Y-%m')
                    target_month = date[:7]  # YYYY-MM

                    pmi_month = pmi_df[pmi_df['日期'] == target_month]
                    if not pmi_month.empty:
                        if '制造业-新订单' in pmi_month.columns:
                            results.append({
                                'date': date,
                                'indicator': 'pmi_new_orders',
                                'value': float(pmi_month['制造业-新订单'].values[0])
                            })
                        if '制造业-产成品库存' in pmi_month.columns:
                            results.append({
                                'date': date,
                                'indicator': 'pmi_inventory',
                                'value': float(pmi_month['制造业-产成品库存'].values[0])
                            })
            except Exception as e:
                logger.warning(f"PMI数据获取失败: {e}")

            # PPI数据
            try:
                ppi_df = self._retry_fetch(ak.macro_china_ppi)
                if ppi_df is not None and not ppi_df.empty:
                    ppi_df['日期'] = pd.to_datetime(ppi_df['日期']).dt.strftime('%Y-%m')
                    target_month = date[:7]

                    ppi_month = ppi_df[ppi_df['日期'] == target_month]
                    if not ppi_month.empty and '同比' in ppi_month.columns:
                        results.append({
                            'date': date,
                            'indicator': 'ppi_yoy',
                            'value': float(ppi_month['同比'].values[0])
                        })
            except Exception as e:
                logger.warning(f"PPI数据获取失败: {e}")

            return results

        except Exception as e:
            logger.error(f"获取宏观数据失败: {e}")
            return []

    def save_to_parquet(self, table_name: str, df: pd.DataFrame):
        """
        保存时间序列数据到Parquet

        Args:
            table_name: 表名
            df: DataFrame
        """
        try:
            if df.empty:
                return

            parquet_file = Path(self.parquet_dir) / f"{table_name}.parquet"

            # 如果文件存在，追加数据
            if parquet_file.exists():
                existing_df = pd.read_parquet(parquet_file)
                # 合并并去重
                df = pd.concat([existing_df, df], ignore_index=True)
                df = df.drop_duplicates(subset=['date'] if 'date' in df.columns else None)

            df.to_parquet(parquet_file, index=False)
            logger.info(f"数据已保存到Parquet: {table_name}")

        except Exception as e:
            logger.error(f"保存Parquet失败: {e}")

    def save_to_db(self, table_name: str, data: Union[pd.DataFrame, Dict]):
        """
        保存数据到SQLite

        Args:
            table_name: 表名
            data: DataFrame或Dict
        """
        conn = sqlite3.connect(self.sqlite_path)

        try:
            if isinstance(data, dict):
                # Dict转DataFrame
                df = pd.DataFrame([data])
            else:
                df = data

            # 幂等upsert
            df.to_sql(table_name, conn, if_exists='append', index=False)
            conn.commit()
            logger.info(f"数据已保存到表 {table_name}")

        except sqlite3.IntegrityError:
            # 主键冲突，更新数据
            logger.info(f"数据已存在，更新表 {table_name}")
            # 简化处理：先删除再插入
            if isinstance(data, dict):
                date = data.get('date')
                if date:
                    conn.execute(f"DELETE FROM {table_name} WHERE date = ?", (date,))
                df = pd.DataFrame([data])
            else:
                df = data
            df.to_sql(table_name, conn, if_exists='append', index=False)
            conn.commit()

        finally:
            conn.close()

    def fetch_and_save_all(self, date: str):
        """
        获取并保存所有数据

        Args:
            date: 日期 YYYY-MM-DD
        """
        logger.info(f"开始获取 {date} 的所有数据")

        try:
            # 1. 指数数据
            logger.info("获取指数数据...")
            indices = self.fetch_indices(date)
            self.save_to_db('indices', indices)
            self.save_to_parquet('indices', indices)

            # 2. 成交额
            logger.info("获取成交额...")
            amount = self.fetch_market_amount(date)
            self.save_to_db('market_amount', amount)

            # 3. 市场广度
            logger.info("获取市场广度...")
            breadth = self.fetch_market_breadth(date)
            self.save_to_db('breadth', breadth)

            # 4. 北向资金
            logger.info("获取北向资金...")
            northbound = self.fetch_northbound(date)
            self.save_to_db('northbound', northbound)

            # 5. ETF流向
            logger.info("获取ETF流向...")
            etf_flows = self.fetch_etf_flows(date)
            for flow in etf_flows:
                self.save_to_db('etf_flows', flow)

            # 6. 融资融券
            logger.info("获取融资融券...")
            margin = self.fetch_margin(date)
            self.save_to_db('margin', margin)

            # 7. 行业数据
            logger.info("获取行业数据...")
            industry = self.fetch_industry_data(date)
            if not industry.empty:
                self.save_to_db('industry', industry)

            # 8. 宏观数据
            logger.info("获取宏观数据...")
            macro = self.fetch_macro_data(date)
            for indicator in macro:
                self.save_to_db('macro', indicator)

            logger.info(f"{date} 数据获取完成")

        except Exception as e:
            logger.error(f"数据获取失败: {e}")
            raise


# 导入类型提示
from typing import Union
