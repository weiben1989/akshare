"""专注于真实数据缓存的 Streamlit 仪表盘。"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd
import streamlit as st

# 允许脚本直接运行
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.storage import DataCacheManager
from main import QuantSystem
from scripts.download_data import DataDownloader
from scripts.check_real_data import CheckRule, DATE_CANDIDATES, REQUIRED_DATASETS

# ---------------------------------------------------------------------------
# 常量配置
# ---------------------------------------------------------------------------
DEFAULT_PORT = os.environ.get("QS_REAL_DASHBOARD_PORT", "8701")


@dataclass
class TableStatus:
    """缓存表格的状态描述。"""

    dataset: str
    name: str
    ok: bool
    note: Optional[str] = None
    reason: Optional[str] = None
    rows: Optional[int] = None
    period: Optional[str] = None
    latest_fields: Optional[str] = None


def _find_date_series(df: pd.DataFrame) -> Optional[pd.Series]:
    for column in DATE_CANDIDATES:
        if column in df.columns:
            series = pd.to_datetime(df[column], errors="coerce")
            if series.notna().sum():
                return series
    return None


def _summarise_dataframe(df: pd.DataFrame) -> Dict[str, Any]:
    info: Dict[str, Any] = {"rows": len(df)}

    date_series = _find_date_series(df)
    if date_series is not None and date_series.notna().any():
        info["period"] = f"{date_series.min().date()} → {date_series.max().date()}"

    numeric = df.select_dtypes(include="number")
    if not numeric.empty:
        latest_row = numeric.tail(1).iloc[0].dropna()
        if not latest_row.empty:
            info["latest_fields"] = ", ".join(
                f"{col}={latest_row[col]:.2f}" for col in latest_row.index[:3]
            )

    return info


def _validate_cache_dataset(
    dataset: str,
    rules: Dict[str, CheckRule],
    cache_manager: DataCacheManager,
) -> List[TableStatus]:
    data = cache_manager.load_dataset(dataset)
    statuses: List[TableStatus] = []

    if not isinstance(data, dict):
        statuses.append(
            TableStatus(
                dataset=dataset,
                name="__dataset__",
                ok=False,
                reason="未找到缓存文件或格式不正确",
            )
        )
        return statuses

    for key, rule in rules.items():
        df = data.get(key)
        if not isinstance(df, pd.DataFrame) or df.empty:
            statuses.append(
                TableStatus(
                    dataset=dataset,
                    name=key,
                    ok=False,
                    note=rule.note,
                    reason="数据缺失，请重新下载",
                )
            )
            continue

        if len(df) < rule.min_rows:
            statuses.append(
                TableStatus(
                    dataset=dataset,
                    name=key,
                    ok=False,
                    note=rule.note,
                    reason=f"行数仅 {len(df)} 行，少于建议的 {rule.min_rows} 行",
                )
            )
            continue

        if rule.require_date and _find_date_series(df) is None:
            statuses.append(
                TableStatus(
                    dataset=dataset,
                    name=key,
                    ok=False,
                    note=rule.note,
                    reason="未检测到日期列，疑似旧版模拟数据",
                )
            )
            continue

        summary = _summarise_dataframe(df)
        statuses.append(
            TableStatus(
                dataset=dataset,
                name=key,
                ok=True,
                note=rule.note,
                rows=summary.get("rows"),
                period=summary.get("period"),
                latest_fields=summary.get("latest_fields"),
            )
        )

    return statuses


def validate_real_cache() -> Dict[str, Any]:
    cache_manager = DataCacheManager()
    all_statuses: List[TableStatus] = []

    for dataset, rules in REQUIRED_DATASETS.items():
        all_statuses.extend(_validate_cache_dataset(dataset, rules, cache_manager))

    missing = [status for status in all_statuses if not status.ok]
    return {
        "ok": not missing,
        "statuses": all_statuses,
    }


def _prepare_chart(df: pd.DataFrame, limit: Optional[int] = 120) -> Optional[pd.DataFrame]:
    date_series = _find_date_series(df)
    if date_series is None:
        return None

    numeric = df.select_dtypes(include="number")
    if numeric.empty:
        return None

    chart = numeric.copy()
    chart.index = pd.to_datetime(date_series)
    chart = chart.sort_index()
    chart = chart.loc[chart.index.notna()]
    if limit:
        chart = chart.tail(limit)

    # 仅展示前3个字段，避免图表过于拥挤
    if chart.shape[1] > 3:
        chart = chart.iloc[:, :3]

    return chart


@st.cache_data(ttl=120)
def get_cache_status() -> Dict[str, Any]:
    return validate_real_cache()


@st.cache_data(ttl=900)
def load_cached_dataset(name: str) -> Dict[str, pd.DataFrame]:
    manager = DataCacheManager()
    dataset = manager.load_dataset(name)
    result: Dict[str, pd.DataFrame] = {}
    if isinstance(dataset, dict):
        for key, value in dataset.items():
            if isinstance(value, pd.DataFrame) and not value.empty:
                result[key] = value.copy()
    return result


@st.cache_resource
def get_system() -> QuantSystem:
    return QuantSystem()


def _render_status(statuses: Iterable[TableStatus]) -> None:
    grouped: Dict[str, List[TableStatus]] = {}
    for status in statuses:
        grouped.setdefault(status.dataset, []).append(status)

    for dataset, items in grouped.items():
        st.subheader(f"缓存数据集 · {dataset}")
        for item in items:
            if item.name == "__dataset__":
                st.error("未找到缓存文件，请先下载真实数据。")
                continue

            cols = st.columns([1.5, 1, 1.2, 2])
            with cols[0]:
                title = item.name
                if item.note:
                    title += f" · {item.note}"
                if item.ok:
                    st.markdown(f"✅ **{title}**")
                else:
                    st.markdown(f"❌ **{title}**")

            with cols[1]:
                if item.rows is not None:
                    st.metric("样本数", item.rows)
                else:
                    st.write("—")

            with cols[2]:
                if item.period:
                    st.caption(f"覆盖: {item.period}")
                else:
                    st.caption("覆盖: 未识别")

            with cols[3]:
                if item.ok and item.latest_fields:
                    st.caption(f"最新数值: {item.latest_fields}")
                elif item.ok:
                    st.caption("已检测到真实数据")
                else:
                    st.caption(item.reason or "数据异常")

        st.divider()


def _render_cycle_cards(cycle_data: Dict[str, Any]) -> None:
    st.subheader("市场周期定位（真实数据）")
    cards = st.columns(3)

    kitchin = cycle_data.get("kitchin", {})
    juglar = cycle_data.get("juglar", {})
    pendulum = cycle_data.get("pendulum", {})

    with cards[0]:
        st.markdown("### 基钦周期")
        st.metric("阶段", kitchin.get("phase_name", "—"))
        st.caption(f"库存增速: {kitchin.get('inventory_growth', '—')}")

    with cards[1]:
        st.markdown("### 朱格拉周期")
        st.metric("阶段", juglar.get("phase_name", "—"))
        st.caption(juglar.get("next_inflection", "等待更多真实数据"))

    with cards[2]:
        st.markdown("### 情绪温度")
        st.metric("得分", f"{pendulum.get('total_score', '—')}")
        st.caption(pendulum.get("recommendation", {}).get("reason", ""))


def _render_macro_section(macro_data: Dict[str, pd.DataFrame]) -> None:
    st.subheader("宏观指标走势")
    macro_tabs = st.tabs(["PMI", "PPI", "GDP", "社融"])

    datasets = {
        "PMI": macro_data.get("pmi"),
        "PPI": macro_data.get("ppi"),
        "GDP": macro_data.get("gdp"),
        "社融": macro_data.get("social_financing"),
    }

    for tab, (name, df) in zip(macro_tabs, datasets.items()):
        with tab:
            if isinstance(df, pd.DataFrame) and not df.empty:
                chart = _prepare_chart(df)
                if chart is not None:
                    st.line_chart(chart)
                st.dataframe(df.tail(20), use_container_width=True)
            else:
                st.info(f"暂未检测到{name}的真实数据，请先下载。")


def _render_market_section(market_data: Dict[str, pd.DataFrame]) -> None:
    st.subheader("主要指数行情")
    market_tabs = st.tabs(["沪深300", "上证指数", "行情快照"])

    series_map = {
        "沪深300": market_data.get("hs300"),
        "上证指数": market_data.get("sh000001"),
    }

    for tab, (name, df) in zip(market_tabs[:2], series_map.items()):
        with tab:
            if isinstance(df, pd.DataFrame) and not df.empty:
                chart = _prepare_chart(df)
                if chart is not None:
                    st.line_chart(chart)
                st.dataframe(df.tail(60), use_container_width=True)
            else:
                st.warning(f"尚未缓存{name}的真实行情。")

    with market_tabs[2]:
        spot_df = market_data.get("stock_list")
        if isinstance(spot_df, pd.DataFrame) and not spot_df.empty:
            st.dataframe(spot_df.head(200), use_container_width=True)
        else:
            st.info("暂无A股行情快照，请确认已下载真实数据。")


def _render_strategy_section(strategies: Dict[str, Dict[str, Any]]) -> None:
    st.subheader("经典资产配置（基于真实数据回测参数）")
    cols = st.columns(2)

    for col, (name, data) in zip(cols, strategies.items()):
        with col:
            st.markdown(f"#### {data.get('name', name.title())}")
            st.write(data.get("description", ""))
            metrics = data.get("metrics", {})
            if metrics:
                m_cols = st.columns(3)
                m_cols[0].metric("预期收益", f"{metrics.get('expected_return', 0):.2%}")
                m_cols[1].metric("波动率", f"{metrics.get('volatility', 0):.2%}")
                m_cols[2].metric("最大回撤", f"{metrics.get('max_drawdown', 0):.2%}")
            allocations = data.get("allocations", {})
            if allocations:
                allocation_df = pd.DataFrame(
                    [{"资产": k, "目标权重": v} for k, v in allocations.items()]
                )
                st.dataframe(allocation_df, hide_index=True, use_container_width=True)


def main() -> None:
    st.set_page_config(
        page_title="A股量化系统 · 真实数据仪表盘",
        page_icon="🟢",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.title("A股量化系统 · 真实数据仪表盘")
    st.caption(
        "运行命令：`streamlit run real_data_dashboard.py --server.port "
        f"{DEFAULT_PORT}`"
    )

    st.sidebar.header("真实数据工具箱")
    st.sidebar.success("当前页面仅展示已通过校验的真实数据")
    st.sidebar.caption(
        "若想在独立分支中体验，可执行 `git switch -c real-data-dashboard` "
        "再运行上述命令。"
    )

    if st.sidebar.button("⬇️ 重新下载真实数据", use_container_width=True):
        with st.spinner("正在从 AKShare 抓取真实数据，请稍候..."):
            downloader = DataDownloader()
            downloader.download_all(years=3)
        st.sidebar.success("下载完成，缓存已更新")
        st.cache_data.clear()
        st.cache_resource.clear()
        st.experimental_rerun()

    cache_status = get_cache_status()
    if not cache_status["ok"]:
        st.error(
            "当前缓存未通过真实数据校验。请点击左侧按钮重新下载，"
            "或运行 `python scripts/download_data.py`。"
        )
        _render_status(cache_status["statuses"])
        st.stop()

    st.success("✅ 已检测到真实数据缓存，以下内容均基于真实指标生成")
    _render_status(cache_status["statuses"])

    system = get_system()
    cycle_data = system.analyze_market_cycle()
    _render_cycle_cards(cycle_data)

    strategies = system.get_allocation_strategies()
    _render_strategy_section(strategies)

    macro_data = load_cached_dataset("macro_data")
    market_data = load_cached_dataset("market_data")

    _render_macro_section(macro_data)
    _render_market_section(market_data)


if __name__ == "__main__":
    main()
