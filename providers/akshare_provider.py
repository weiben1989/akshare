"""Data acquisition and persistence utilities for the daily review engine."""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from sqlalchemy import Boolean, Column, Date, Float, Integer, MetaData, String, Table, create_engine
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine

import akshare as ak

from core.config import Config


class DataFetchError(RuntimeError):
    """Raised when AkShare data cannot be fetched after retries."""


class DataValidationError(RuntimeError):
    """Raised when downloaded data does not contain required fields."""


@dataclass
class TableRegistryEntry:
    table: Table
    parquet_keys: Sequence[str]


DEFAULT_INDEX_SYMBOLS: Tuple[str, ...] = (
    "sh000001",  # 上证指数
    "sz399001",  # 深成指
    "sz399006",  # 创业板指
    "sh000300",  # 沪深300
)

DEFAULT_ETF_BUCKETS: Dict[str, Sequence[str]] = {
    "broad": ("510300", "510500", "159915"),
    "growth": ("159949", "159915"),
    "value": ("510880", "510900"),
    "industry_resources": ("510170", "159980"),
    "industry_tech": ("159801", "159841"),
}


class AkshareDataProvider:
    """Central point for interacting with AkShare and persisting datasets."""

    def __init__(self, config: Config, logger: Optional[logging.Logger] = None) -> None:
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        paths = config.get("paths", {}) or {}
        self.sqlite_path = Path(paths.get("sqlite", "data/review.sqlite"))
        self.parquet_dir = Path(paths.get("parquet_dir", "data/parquet"))
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.parquet_dir.mkdir(parents=True, exist_ok=True)

        self.retry = int(os.getenv("AKSHARE_RETRY", 3))
        self.timeout = int(os.getenv("AKSHARE_TIMEOUT", 30))
        self.index_symbols: Tuple[str, ...] = tuple(
            config.get("index_symbols", DEFAULT_INDEX_SYMBOLS)
        )
        etf_buckets_cfg = config.get("etf_buckets", DEFAULT_ETF_BUCKETS)
        self.etf_buckets: Dict[str, Sequence[str]] = {
            bucket: tuple(codes) for bucket, codes in etf_buckets_cfg.items()
        }

        self.engine: Engine = create_engine(f"sqlite:///{self.sqlite_path}")
        self.metadata = MetaData()
        self.tables: Dict[str, TableRegistryEntry] = {}
        self._register_tables()
        self.metadata.create_all(self.engine)

    # ------------------------------------------------------------------
    # Schema initialisation
    # ------------------------------------------------------------------
    def _register_tables(self) -> None:
        self.tables["indices"] = TableRegistryEntry(
            table=Table(
                "indices",
                self.metadata,
                Column("date", Date, primary_key=True),
                Column("symbol", String, primary_key=True),
                Column("open", Float),
                Column("close", Float),
                Column("high", Float),
                Column("low", Float),
                Column("volume", Float),
                Column("amount", Float),
            ),
            parquet_keys=("date", "symbol"),
        )
        self.tables["market_amount"] = TableRegistryEntry(
            table=Table(
                "market_amount",
                self.metadata,
                Column("date", Date, primary_key=True),
                Column("sh_amount", Float),
                Column("sz_amount", Float),
                Column("total_amount", Float),
            ),
            parquet_keys=("date",),
        )
        self.tables["breadth"] = TableRegistryEntry(
            table=Table(
                "breadth",
                self.metadata,
                Column("date", Date, primary_key=True),
                Column("advancers", Integer),
                Column("decliners", Integer),
                Column("unchanged", Integer),
                Column("limit_up_count", Integer),
                Column("limit_down_count", Integer),
                Column("max_limit_up_streak", Integer),
                Column("limit_up_sustainability", Float),
                Column("note", String),
            ),
            parquet_keys=("date",),
        )
        self.tables["northbound"] = TableRegistryEntry(
            table=Table(
                "northbound",
                self.metadata,
                Column("date", Date, primary_key=True),
                Column("net_flow", Float),
                Column("shanghai", Float),
                Column("shenzhen", Float),
                Column("unit", String),
            ),
            parquet_keys=("date",),
        )
        self.tables["etf_flows"] = TableRegistryEntry(
            table=Table(
                "etf_flows",
                self.metadata,
                Column("date", Date, primary_key=True),
                Column("bucket", String, primary_key=True),
                Column("share_change", Float),
                Column("net_value", Float),
            ),
            parquet_keys=("date", "bucket"),
        )
        self.tables["margin"] = TableRegistryEntry(
            table=Table(
                "margin",
                self.metadata,
                Column("date", Date, primary_key=True),
                Column("sse_balance", Float),
                Column("szse_balance", Float),
                Column("total_balance", Float),
            ),
            parquet_keys=("date",),
        )
        self.tables["industry_snapshot"] = TableRegistryEntry(
            table=Table(
                "industry_snapshot",
                self.metadata,
                Column("date", Date, primary_key=True),
                Column("industry", String, primary_key=True),
                Column("avg_return", Float),
                Column("net_inflow", Float),
                Column("turnover", Float),
                Column("limit_up_count", Integer),
                Column("sample_size", Integer),
            ),
            parquet_keys=("date", "industry"),
        )
        self.tables["macro"] = TableRegistryEntry(
            table=Table(
                "macro",
                self.metadata,
                Column("date", Date, primary_key=True),
                Column("indicator", String, primary_key=True),
                Column("value", Float),
            ),
            parquet_keys=("date", "indicator"),
        )
        self.tables["calendar"] = TableRegistryEntry(
            table=Table(
                "calendar",
                self.metadata,
                Column("date", Date, primary_key=True),
                Column("is_trading_day", Boolean, default=True),
            ),
            parquet_keys=("date",),
        )
        self.tables["limit_up_chain"] = TableRegistryEntry(
            table=Table(
                "limit_up_chain",
                self.metadata,
                Column("date", Date, primary_key=True),
                Column("code", String, primary_key=True),
                Column("name", String),
                Column("board_count", Integer),
            ),
            parquet_keys=("date", "code"),
        )
        self.tables["astro_events"] = TableRegistryEntry(
            table=Table(
                "astro_events",
                self.metadata,
                Column("date", Date, primary_key=True),
                Column("event_type", String, primary_key=True),
                Column("window", Integer, default=1),
                Column("impact_riskon", Float, default=0.0),
                Column("impact_momentum", Float, default=0.0),
            ),
            parquet_keys=("date", "event_type"),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def prepare_daily_data(self, target_date: date) -> Dict[str, pd.DataFrame]:
        """Fetch and persist all datasets required for the review."""
        self.logger.info("Collecting market data for %s", target_date)
        results: Dict[str, pd.DataFrame] = {}
        index_history = self._collect_indices(target_date)
        results["indices"] = index_history

        market_amount_df = self._persist_market_amount(index_history, target_date)
        results["market_amount"] = market_amount_df

        breadth_df = self._collect_market_breadth(target_date)
        results["breadth"] = breadth_df

        northbound_df = self._collect_northbound(target_date)
        results["northbound"] = northbound_df

        etf_df = self._collect_etf_flows(target_date)
        results["etf_flows"] = etf_df

        margin_df = self._collect_margin_balance(target_date)
        results["margin"] = margin_df

        industry_df = self._collect_industry_snapshot(target_date)
        results["industry_snapshot"] = industry_df

        macro_df = self._collect_macro_data()
        results["macro"] = macro_df

        self._ensure_calendar(index_history)

        return results

    # ------------------------------------------------------------------
    # Data extraction helpers
    # ------------------------------------------------------------------
    def _collect_indices(self, target_date: date) -> pd.DataFrame:
        start_date = (target_date - timedelta(days=180)).strftime("%Y%m%d")
        end_date = (target_date + timedelta(days=1)).strftime("%Y%m%d")
        frames: List[pd.DataFrame] = []
        for symbol in self.index_symbols:
            df = self._fetch_with_retry(
                ak.stock_zh_index_daily_em,
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
            )
            self._validate_columns(df, {"date", "open", "close", "high", "low", "volume", "amount"},
                                   f"stock_zh_index_daily_em({symbol})")
            df["date"] = pd.to_datetime(df["date"]).dt.date
            df["symbol"] = symbol
            frames.append(df)
        history = pd.concat(frames, ignore_index=True)
        self._store_dataframe("indices", history)
        return history

    def _persist_market_amount(self, index_history: pd.DataFrame, target_date: date) -> pd.DataFrame:
        if index_history.empty:
            raise DataValidationError("Index history is empty; cannot derive market amount")
        pivot = index_history.pivot_table(
            index="date", columns="symbol", values="amount", aggfunc="last"
        )
        missing_symbols = {"sh000001", "sz399001"} - set(pivot.columns)
        if missing_symbols:
            raise DataValidationError(
                f"Missing index amount data for symbols: {', '.join(sorted(missing_symbols))}"
            )
        market_amount = pd.DataFrame({
            "date": pivot.index,
            "sh_amount": pivot.get("sh000001"),
            "sz_amount": pivot.get("sz399001"),
        })
        market_amount["total_amount"] = market_amount[["sh_amount", "sz_amount"]].sum(axis=1)
        market_amount.dropna(subset=["total_amount"], inplace=True)
        self._store_dataframe("market_amount", market_amount)
        return market_amount

    def _collect_market_breadth(self, target_date: date) -> pd.DataFrame:
        spot_df = self._fetch_with_retry(ak.stock_zh_a_spot_em)
        required_cols = {"代码", "名称", "涨跌幅", "成交额", "换手率"}
        self._validate_columns(spot_df, required_cols, "stock_zh_a_spot_em")
        spot_df["涨跌幅"] = pd.to_numeric(spot_df["涨跌幅"], errors="coerce")
        spot_df["成交额"] = pd.to_numeric(spot_df["成交额"], errors="coerce")
        spot_df["换手率"] = pd.to_numeric(spot_df["换手率"], errors="coerce")
        advancers = int((spot_df["涨跌幅"] > 0).sum())
        decliners = int((spot_df["涨跌幅"] < 0).sum())
        unchanged = int(spot_df["涨跌幅"].isna().sum() + (spot_df["涨跌幅"] == 0).sum())

        limit_up_df = self._fetch_optional(
            ak.stock_zt_pool_em, date=target_date.strftime("%Y%m%d")
        )
        limit_down_df = self._fetch_optional(
            ak.stock_zt_pool_dtgc_em, date=target_date.strftime("%Y%m%d")
        )
        limit_chain_df = self._fetch_optional(
            ak.stock_zt_pool_lx_em, date=target_date.strftime("%Y%m%d")
        )

        limit_up_count = int(0 if limit_up_df is None else len(limit_up_df))
        limit_down_count = int(0 if limit_down_df is None else len(limit_down_df))
        max_limit_up = 0
        if limit_chain_df is not None and not limit_chain_df.empty:
            if "连板数" not in limit_chain_df.columns:
                raise DataValidationError("stock_zt_pool_lx_em missing 连板数 column")
            limit_chain_df["连板数"] = pd.to_numeric(limit_chain_df["连板数"], errors="coerce")
            max_limit_up = int(limit_chain_df["连板数"].max())
            cleaned_chain = limit_chain_df[["股票代码", "股票简称", "连板数"]].copy()
            cleaned_chain.columns = ["code", "name", "board_count"]
            cleaned_chain["date"] = target_date
            cleaned_chain["board_count"] = cleaned_chain["board_count"].fillna(0).astype(int)
            self._store_dataframe("limit_up_chain", cleaned_chain)
        else:
            max_limit_up = 0

        sustain_rate = self._compute_limit_up_sustainability(target_date, spot_df)

        breadth_data = pd.DataFrame(
            [
                {
                    "date": target_date,
                    "advancers": advancers,
                    "decliners": decliners,
                    "unchanged": unchanged,
                    "limit_up_count": limit_up_count,
                    "limit_down_count": limit_down_count,
                    "max_limit_up_streak": max_limit_up,
                    "limit_up_sustainability": sustain_rate,
                    "note": self._compose_breadth_note(limit_up_df, limit_down_df),
                }
            ]
        )
        self._store_dataframe("breadth", breadth_data)
        return breadth_data

    def _collect_northbound(self, target_date: date) -> pd.DataFrame:
        df = self._fetch_with_retry(ak.stock_hsgt_north_net_flow_in)
        self._validate_columns(
            df, {"日期", "北上资金", "沪股通", "深股通"}, "stock_hsgt_north_net_flow_in"
        )
        df["日期"] = pd.to_datetime(df["日期"]).dt.date
        df = df[df["日期"] <= target_date]
        if df.empty:
            raise DataValidationError("Northbound capital data is empty")
        df.sort_values("日期", inplace=True)
        df["北上资金"] = pd.to_numeric(df["北上资金"], errors="coerce")
        df["沪股通"] = pd.to_numeric(df["沪股通"], errors="coerce")
        df["深股通"] = pd.to_numeric(df["深股通"], errors="coerce")
        record = df[["日期", "北上资金", "沪股通", "深股通"]].copy()
        record.rename(
            columns={
                "日期": "date",
                "北上资金": "net_flow",
                "沪股通": "shanghai",
                "深股通": "shenzhen",
            },
            inplace=True,
        )
        record["unit"] = "亿元"
        self._store_dataframe("northbound", record)
        return record

    def _collect_etf_flows(self, target_date: date) -> pd.DataFrame:
        df = self._fetch_with_retry(ak.fund_etf_share_em)
        required = {"基金代码", "基金简称", "交易日期", "份额变动(万份)", "成交金额"}
        self._validate_columns(df, required, "fund_etf_share_em")
        df["交易日期"] = pd.to_datetime(df["交易日期"]).dt.date
        df = df[df["交易日期"] <= target_date]
        cutoff = target_date - timedelta(days=120)
        df = df[df["交易日期"] >= cutoff]
        if df.empty:
            raise DataValidationError("ETF share data is empty within the lookback window")
        df["份额变动(万份)"] = pd.to_numeric(df["份额变动(万份)"], errors="coerce")
        df["成交金额"] = pd.to_numeric(df["成交金额"], errors="coerce")
        bucket_rows: List[Dict[str, object]] = []
        for bucket, codes in self.etf_buckets.items():
            bucket_df = df[df["基金代码"].isin(codes)]
            if bucket_df.empty:
                continue
            grouped = (
                bucket_df.groupby("交易日期")[["份额变动(万份)", "成交金额"]]
                .sum()
                .reset_index()
            )
            grouped.columns = ["date", "share_change", "net_value"]
            grouped["bucket"] = bucket
            bucket_rows.extend(grouped.to_dict(orient="records"))
        if not bucket_rows:
            raise DataValidationError("ETF bucket aggregation returned no data")
        result_df = pd.DataFrame(bucket_rows)
        self._store_dataframe("etf_flows", result_df)
        return result_df

    def _collect_margin_balance(self, target_date: date) -> pd.DataFrame:
        sse_df = self._fetch_with_retry(ak.stock_margin_sse)
        szse_df = self._fetch_with_retry(ak.stock_margin_szse)
        self._validate_columns(sse_df, {"日期", "融资余额"}, "stock_margin_sse")
        self._validate_columns(szse_df, {"日期", "融资余额"}, "stock_margin_szse")
        sse_df["日期"] = pd.to_datetime(sse_df["日期"]).dt.date
        szse_df["日期"] = pd.to_datetime(szse_df["日期"]).dt.date
        sse_df = sse_df[sse_df["日期"] <= target_date]
        szse_df = szse_df[szse_df["日期"] <= target_date]
        merged = pd.merge(
            sse_df[["日期", "融资余额"]],
            szse_df[["日期", "融资余额"]],
            on="日期",
            how="outer",
            suffixes=("_sse", "_szse"),
        ).sort_values("日期")
        merged.fillna(method="ffill", inplace=True)
        merged.rename(columns={"日期": "date"}, inplace=True)
        merged["total_balance"] = (
            pd.to_numeric(merged["融资余额_sse"], errors="coerce")
            + pd.to_numeric(merged["融资余额_szse"], errors="coerce")
        )
        merged.rename(
            columns={
                "融资余额_sse": "sse_balance",
                "融资余额_szse": "szse_balance",
            },
            inplace=True,
        )
        merged.dropna(subset=["total_balance"], inplace=True)
        self._store_dataframe("margin", merged)
        return merged

    def _collect_industry_snapshot(self, target_date: date) -> pd.DataFrame:
        spot_df = self._fetch_with_retry(ak.stock_zh_a_spot_em)
        candidate_columns = ["行业", "所属行业", "板块"]
        industry_col = next((col for col in candidate_columns if col in spot_df.columns), None)
        if not industry_col:
            raise DataValidationError("Industry column missing from stock_zh_a_spot_em dataset")
        spot_df[industry_col] = spot_df[industry_col].fillna("未分类")
        spot_df["涨跌幅"] = pd.to_numeric(spot_df["涨跌幅"], errors="coerce")
        flow_col = next(
            (col for col in ["主力净流入-净额", "主力净流入净额", "主力净流入"] if col in spot_df.columns),
            None,
        )
        turnover_col = "换手率" if "换手率" in spot_df.columns else None
        if flow_col:
            spot_df[flow_col] = pd.to_numeric(spot_df[flow_col], errors="coerce")
        if turnover_col:
            spot_df[turnover_col] = pd.to_numeric(spot_df[turnover_col], errors="coerce")
        grouped = spot_df.groupby(industry_col)
        summary = pd.DataFrame(
            {
                "avg_return": grouped["涨跌幅"].mean(),
                "net_inflow": grouped[flow_col].sum() if flow_col else np.nan,
                "turnover": grouped[turnover_col].mean() if turnover_col else np.nan,
                "sample_size": grouped.size(),
            }
        ).reset_index()
        summary.rename(columns={industry_col: "industry"}, inplace=True)

        limit_up_df = self._fetch_optional(
            ak.stock_zt_pool_em, date=target_date.strftime("%Y%m%d")
        )
        if limit_up_df is not None and not limit_up_df.empty:
            if "所属行业" in limit_up_df.columns:
                limit_up_counts = (
                    limit_up_df.groupby("所属行业").size().rename("limit_up_count").reset_index()
                )
                limit_up_counts.rename(columns={"所属行业": "industry"}, inplace=True)
                summary = summary.merge(limit_up_counts, on="industry", how="left")
            elif "行业" in limit_up_df.columns:
                limit_up_counts = (
                    limit_up_df.groupby("行业").size().rename("limit_up_count").reset_index()
                )
                limit_up_counts.rename(columns={"行业": "industry"}, inplace=True)
                summary = summary.merge(limit_up_counts, on="industry", how="left")
        summary["limit_up_count"] = summary.get("limit_up_count", pd.Series(dtype=float)).fillna(0)
        summary["date"] = target_date
        self._store_dataframe("industry_snapshot", summary)
        return summary

    def _collect_macro_data(self) -> pd.DataFrame:
        pmi_df = self._fetch_with_retry(ak.macro_china_pmi)
        ppi_df = self._fetch_with_retry(ak.macro_china_ppi)
        commodity_df = self._fetch_optional(ak.macro_china_commodity_index)

        pmi_required = {"月份", "新订单指数", "产成品库存指数"}
        self._validate_columns(pmi_df, pmi_required, "macro_china_pmi")
        self._validate_columns(ppi_df, {"月份", "工业生产者出厂价格指数"}, "macro_china_ppi")

        pmi_df["date"] = pd.to_datetime(pmi_df["月份"]).dt.date
        pmi_data = pmi_df[["date", "新订单指数", "产成品库存指数"]].tail(12)
        records = []
        for _, row in pmi_data.iterrows():
            records.append(
                {"date": row["date"], "indicator": "PMI_NEW_ORDERS", "value": float(row["新订单指数"])}
            )
            records.append(
                {"date": row["date"], "indicator": "PMI_FINISHED_GOODS", "value": float(row["产成品库存指数"])}
            )
        ppi_df["date"] = pd.to_datetime(ppi_df["月份"]).dt.date
        for _, row in ppi_df.tail(12).iterrows():
            records.append(
                {"date": row["date"], "indicator": "PPI_YOY", "value": float(row["工业生产者出厂价格指数"])}
            )
        if commodity_df is not None and not commodity_df.empty:
            if {"月份", "当月值"}.issubset(commodity_df.columns):
                commodity_df["date"] = pd.to_datetime(commodity_df["月份"]).dt.date
                for _, row in commodity_df.tail(12).iterrows():
                    try:
                        value = float(row["当月值"])
                    except (TypeError, ValueError):
                        continue
                    records.append(
                        {"date": row["date"], "indicator": "COMMODITY_INDEX", "value": value}
                    )
        macro_df = pd.DataFrame(records)
        if macro_df.empty:
            raise DataValidationError("Macro dataset is empty")
        self._store_dataframe("macro", macro_df)
        return macro_df

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    def _store_dataframe(self, table_name: str, df: pd.DataFrame) -> None:
        if df is None or df.empty:
            raise DataValidationError(f"No data to store for table {table_name}")
        registry = self.tables[table_name]
        table = registry.table
        records = self._normalise_records(df, table_name)
        with self.engine.begin() as conn:
            for record in records:
                stmt = sqlite_insert(table).values(**record)
                conflict_cols = [col.name for col in table.primary_key.columns]
                update_mapping = {
                    col.name: stmt.excluded[col.name]
                    for col in table.columns
                    if col.name not in conflict_cols
                }
                stmt = stmt.on_conflict_do_update(index_elements=conflict_cols, set_=update_mapping)
                conn.execute(stmt)
        self._write_parquet(table_name, pd.DataFrame(records), registry.parquet_keys)

    def _normalise_records(self, df: pd.DataFrame, table_name: str) -> List[Dict[str, object]]:
        records: List[Dict[str, object]] = []
        for _, row in df.iterrows():
            record = {}
            for column in df.columns:
                value = row[column]
                if isinstance(value, pd.Timestamp):
                    value = value.date()
                if isinstance(value, np.generic):
                    value = value.item()
                if column == "date" and isinstance(value, str):
                    value = datetime.strptime(value, "%Y-%m-%d").date()
                record[column] = value
            records.append(record)
        return records

    def _write_parquet(self, table_name: str, df: pd.DataFrame, unique_cols: Sequence[str]) -> None:
        target = self.parquet_dir / f"{table_name}.parquet"
        if target.exists():
            existing = pd.read_parquet(target)
            combined = pd.concat([existing, df], ignore_index=True)
            combined.drop_duplicates(subset=list(unique_cols), keep="last", inplace=True)
        else:
            combined = df
        combined.to_parquet(target, index=False)

    # ------------------------------------------------------------------
    # Utility methods
    # ------------------------------------------------------------------
    def load_table(self, table_name: str) -> pd.DataFrame:
        registry = self.tables.get(table_name)
        if registry is None:
            raise KeyError(f"Unknown table {table_name}")
        return pd.read_sql_table(table_name, con=self.engine)

    def load_series(
        self,
        table_name: str,
        value_column: str,
        *,
        key_filters: Optional[Dict[str, object]] = None,
    ) -> pd.Series:
        df = self.load_table(table_name)
        if key_filters:
            for key, value in key_filters.items():
                df = df[df[key] == value]
        if df.empty:
            return pd.Series(dtype=float)
        df.sort_values("date", inplace=True)
        series = pd.Series(df[value_column].values, index=pd.to_datetime(df["date"]))
        return series

    def get_previous_trading_date(self, current_date: date) -> Optional[date]:
        calendar_df = self.load_table("calendar")
        if calendar_df.empty:
            return None
        calendar_df = calendar_df[calendar_df["is_trading_day"] == 1]
        calendar_df.sort_values("date", inplace=True)
        calendar_df["date"] = pd.to_datetime(calendar_df["date"]).dt.date
        previous = [d for d in calendar_df["date"].tolist() if d < current_date]
        return previous[-1] if previous else None

    def get_astro_events(self, current_date: date) -> Dict[str, object]:
        table = self.load_table("astro_events")
        if table.empty:
            return {"is_window": False, "events": [], "adjust": {"riskon": 0.0, "momentum": 0.0}}
        table["date"] = pd.to_datetime(table["date"]).dt.date
        events: List[Dict[str, object]] = []
        risk_adjust = 0.0
        momentum_adjust = 0.0
        for _, row in table.iterrows():
            event_date: date = row["date"]
            window = int(row.get("window", 0) or 0)
            if abs((current_date - event_date).days) <= window:
                impact_risk = float(row.get("impact_riskon", 0.0) or 0.0)
                impact_mom = float(row.get("impact_momentum", 0.0) or 0.0)
                risk_adjust += impact_risk
                momentum_adjust += impact_mom
                events.append(
                    {
                        "date": event_date.isoformat(),
                        "type": row.get("event_type", ""),
                        "window": window,
                        "impact_riskon": impact_risk,
                        "impact_momentum": impact_mom,
                    }
                )
        return {
            "is_window": bool(events),
            "events": events,
            "adjust": {"riskon": risk_adjust, "momentum": momentum_adjust},
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _fetch_with_retry(self, func, *args, **kwargs) -> pd.DataFrame:
        delay = 1.0
        last_error: Optional[Exception] = None
        for attempt in range(1, self.retry + 1):
            try:
                df = func(*args, **kwargs)
                if df is None or (hasattr(df, "empty") and df.empty):
                    raise DataFetchError(f"{func.__name__} returned empty dataset")
                return df
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                self.logger.warning(
                    "Attempt %s/%s failed for %s: %s", attempt, self.retry, func.__name__, exc
                )
                if attempt >= self.retry:
                    break
                time.sleep(delay)
                delay = min(delay * 2, 30)
        raise DataFetchError(f"Failed to fetch data from {func.__name__}: {last_error}")

    def _fetch_optional(self, func, *args, **kwargs) -> Optional[pd.DataFrame]:
        try:
            return self._fetch_with_retry(func, *args, **kwargs)
        except DataFetchError as exc:
            self.logger.warning("Optional dataset %s unavailable: %s", func.__name__, exc)
            return None

    def _validate_columns(
        self, df: pd.DataFrame, required: Iterable[str], source: str
    ) -> None:
        missing = set(required) - set(df.columns)
        if missing:
            raise DataValidationError(
                f"{source} missing required columns: {', '.join(sorted(missing))}"
            )

    def _compute_limit_up_sustainability(
        self, target_date: date, spot_df: pd.DataFrame
    ) -> Optional[float]:
        prev_date = self.get_previous_trading_date(target_date)
        if not prev_date:
            return None
        try:
            previous_chain = self.load_table("limit_up_chain")
        except Exception:  # pragma: no cover - table may not exist yet
            return None
        if previous_chain.empty:
            return None
        previous_chain["date"] = pd.to_datetime(previous_chain["date"]).dt.date
        prev_df = previous_chain[previous_chain["date"] == prev_date]
        if prev_df.empty:
            return None
        codes = prev_df["code"].unique().tolist()
        spot_subset = spot_df[spot_df["代码"].isin(codes)]
        if spot_subset.empty:
            return None
        spot_subset["涨跌幅"] = pd.to_numeric(spot_subset["涨跌幅"], errors="coerce")
        positive = (spot_subset["涨跌幅"] > 0).sum()
        total = len(spot_subset)
        if total == 0:
            return None
        return float(positive / total)

    def _compose_breadth_note(
        self,
        limit_up_df: Optional[pd.DataFrame],
        limit_down_df: Optional[pd.DataFrame],
    ) -> str:
        if (limit_up_df is None or limit_up_df.empty) and (
            limit_down_df is None or limit_down_df.empty
        ):
            return "涨跌停数据缺失或非交易日"
        return "数据完整"

    def _ensure_calendar(self, index_history: pd.DataFrame) -> None:
        if index_history.empty:
            return
        calendar_df = index_history[["date"]].drop_duplicates().copy()
        calendar_df["is_trading_day"] = True
        self._store_dataframe("calendar", calendar_df)


__all__ = [
    "AkshareDataProvider",
    "DataFetchError",
    "DataValidationError",
]
