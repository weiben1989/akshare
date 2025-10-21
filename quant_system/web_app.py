"""使用Streamlit构建交互式Dashboard。"""

from __future__ import annotations

import math
import os
import sys
from datetime import datetime
from typing import Any, Dict, Optional

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

# 添加路径，便于在命令行直接运行该文件
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import QuantSystem
from scripts.download_data import DataDownloader
from data.storage import DataCacheManager

# 页面配置
st.set_page_config(
    page_title="A股量化分析系统",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 自定义CSS
st.markdown(
    """
<style>
    :root {
        color-scheme: light;
    }
    body {
        background-color: #f5f5f7;
        font-family: 'SF Pro Display', 'Helvetica Neue', sans-serif;
        color: #1d1d1f;
    }
    .stApp {
        background: radial-gradient(circle at top, rgba(255,255,255,0.92), rgba(245,245,247,0.95));
    }
    .apple-header {
        text-align: center;
        padding: 2.5rem 1rem 1.5rem 1rem;
        color: #1d1d1f;
    }
    .apple-header h1 {
        font-size: 2.6rem;
        font-weight: 600;
        margin-bottom: 0.5rem;
    }
    .apple-subtitle {
        color: #6e6e73;
        font-size: 1rem;
    }
    .header-tags {
        margin-top: 1rem;
    }
    .apple-card {
        background: rgba(255, 255, 255, 0.82);
        border-radius: 24px;
        padding: 1.8rem 1.6rem;
        box-shadow: 0 18px 32px rgba(31, 41, 55, 0.08);
        border: 1px solid rgba(255, 255, 255, 0.6);
        backdrop-filter: blur(20px);
        margin-bottom: 1.5rem;
    }
    .apple-metric-value {
        font-size: 1.35rem;
        font-weight: 600;
        color: #1d1d1f;
    }
    .apple-metric-label {
        font-size: 0.82rem;
        color: #6e6e73;
        letter-spacing: 0.02em;
        text-transform: uppercase;
    }
    .chip {
        display: inline-flex;
        align-items: center;
        padding: 0.35rem 0.85rem;
        border-radius: 999px;
        font-size: 0.85rem;
        font-weight: 500;
        margin-right: 0.5rem;
        margin-bottom: 0.5rem;
    }
    .chip.green {
        background: rgba(52, 199, 89, 0.18);
        color: #1d7f3b;
    }
    .chip.red {
        background: rgba(255, 59, 48, 0.18);
        color: #b0281a;
    }
    .chip.yellow {
        background: rgba(255, 204, 0, 0.22);
        color: #8f6b00;
    }
    .chip.neutral {
        background: rgba(142, 142, 147, 0.18);
        color: #1d1d1f;
    }
    .apple-table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 1rem;
        font-size: 0.9rem;
    }
    .apple-table th,
    .apple-table td {
        padding: 0.35rem 0.2rem;
        border-bottom: 1px solid rgba(60, 60, 67, 0.12);
        text-align: left;
    }
    .apple-table th {
        font-weight: 600;
        color: #3a3a3c;
    }
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_resource
def init_system() -> QuantSystem:
    """初始化系统（缓存资源）"""

    return QuantSystem()


@st.cache_data(ttl=3600)
def get_market_analysis_data() -> Dict[str, Any]:
    """获取市场分析（缓存1小时）"""

    system = init_system()
    return system.analyze_market_cycle()


@st.cache_data(ttl=3600)
def get_investment_advice_data() -> Dict[str, Any]:
    """获取投资建议（缓存1小时）"""

    system = init_system()
    return system.get_investment_advice()


@st.cache_data(ttl=3600)
def get_strategy_data() -> Dict[str, Dict[str, Any]]:
    """获取资产配置策略结果"""

    system = init_system()
    return system.get_allocation_strategies()


@st.cache_data(ttl=3600)
def get_cycle_history_data() -> Dict[str, pd.DataFrame]:
    """获取周期相关历史数据"""

    system = init_system()
    return system.get_cycle_history()


@st.cache_data(ttl=3600)
def get_juglar_indicator_data() -> Dict[str, pd.Series]:
    """获取朱格拉周期指标历史"""

    system = init_system()
    return system.get_juglar_indicators()


@st.cache_data(ttl=3600)
def get_daily_report() -> str:
    """获取缓存的每日报告"""

    system = init_system()
    return system.generate_daily_report()


@st.cache_data(ttl=300)
def get_cache_overview() -> Dict[str, Any]:
    """统计缓存目录中的数据资源情况。"""

    manager = DataCacheManager()
    overview: Dict[str, Any] = {
        "last_download": manager.load_dataset("last_download") or {},
        "datasets": {},
        "files": manager.list_available(),
    }

    for name in [
        "macro_data",
        "market_data",
        "industry_data",
        "valuation_data",
        "fund_data",
        "strategy_data",
    ]:
        summary = _summarize_dataset(manager.load_dataset(name))
        if summary:
            overview["datasets"][name] = summary

    return overview


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def format_number(value: Any, decimals: int = 1, show_sign: bool = True) -> str:
    number = _to_float(value)
    if number is None or math.isnan(number):
        return "--"

    fmt = f"{{:+.{decimals}f}}" if show_sign else f"{{:.{decimals}f}}"
    return fmt.format(number)


def format_percentage(
    value: Any,
    decimals: int = 1,
    *,
    is_ratio: bool = True,
    show_sign: bool = False,
) -> str:
    number = _to_float(value)
    if number is None or math.isnan(number):
        return "--"

    if is_ratio:
        number *= 100

    fmt = f"{{:+.{decimals}f}}%" if show_sign else f"{{:.{decimals}f}}%"
    return fmt.format(number)


def _summarize_dataset(data: Any) -> Optional[Dict[str, Any]]:
    if isinstance(data, dict):
        items = []
        total_rows = 0
        for key, value in data.items():
            rows = None
            if isinstance(value, pd.DataFrame):
                rows = int(len(value))
                total_rows += rows
            elif isinstance(value, (list, tuple, set)):
                rows = len(value)
                total_rows += rows
            items.append({"key": key, "rows": rows})

        return {"items": items, "total_rows": total_rows}

    if isinstance(data, pd.DataFrame):
        rows = int(len(data))
        return {"items": [{"key": "records", "rows": rows}], "total_rows": rows}

    return None


def get_phase_color(phase: Optional[int]) -> str:
    mapping = {
        1: "green",
        2: "green",
        3: "yellow",
        4: "red",
    }
    return mapping.get(phase, "neutral")


def get_temperature_color(score: Optional[float]) -> str:
    value = _to_float(score)
    if value is None:
        return "neutral"
    if value < 30:
        return "green"
    if value < 70:
        return "yellow"
    return "red"


def get_signal_color(signal: str) -> str:
    signal = (signal or "").upper()
    if "BUY" in signal:
        return "green"
    if signal in {"DEFENSIVE", "NEUTRAL"}:
        return "yellow"
    if any(word in signal for word in ["REDUCE", "SELL", "RISK"]):
        return "red"
    return "neutral"


# ---------------------------------------------------------------------------
# 渲染函数
# ---------------------------------------------------------------------------

def render_header(cycle_analysis: Dict[str, Any]) -> None:
    updated_at = cycle_analysis.get("date", datetime.now().strftime("%Y-%m-%d"))
    kitchin = cycle_analysis.get("kitchin", {})
    juglar = cycle_analysis.get("juglar", {})
    pendulum = cycle_analysis.get("pendulum", {})
    macro_period = kitchin.get("timestamp") or juglar.get("timestamp")
    if isinstance(macro_period, (pd.Timestamp, datetime)):
        macro_period = macro_period.strftime("%Y-%m-%d")
    macro_label = macro_period or "--"

    st.markdown(
        f"""
        <div class="apple-header">
            <h1>📈 市场节奏与资产配置</h1>
            <div class="apple-subtitle">基于真实宏观与行情数据的多周期分析面板</div>
            <div style="margin-top:0.6rem;color:#86868b;font-size:0.9rem;">数据刷新时间：{updated_at} · 最新宏观口径：{macro_label}</div>
            <div class="header-tags">
                <span class="chip {get_phase_color(kitchin.get('phase'))}">基钦周期：{kitchin.get('phase_name', '--')}</span>
                <span class="chip {get_phase_color(juglar.get('phase'))}">朱格拉周期：{juglar.get('phase_name', '--')}</span>
                <span class="chip {get_temperature_color(pendulum.get('total_score'))}">情绪温度：{pendulum.get('level', '--')}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_cycle_dashboard(cycle_analysis: Dict[str, Any]) -> None:
    st.markdown("### 🔄 周期与情绪速览")

    col1, col2, col3 = st.columns(3)

    kitchin = cycle_analysis["kitchin"]
    juglar = cycle_analysis["juglar"]
    pendulum = cycle_analysis["pendulum"]

    with col1:
        st.markdown(
            f"""
            <div class="apple-card">
                <div class="apple-metric-label">库存周期 · 基钦</div>
                <div class="apple-metric-value" style="margin-bottom:0.6rem;">{kitchin['phase_name']}</div>
                <div class="chip {get_phase_color(kitchin['phase'])}">阶段进度 {format_percentage(kitchin['progress'])}</div>
                <div style="margin-top:0.8rem; font-size:0.95rem; color:#3a3a3c;">
                    需求增速：{format_number(kitchin['demand_growth'])}%<br/>
                    库存增速：{format_number(kitchin['inventory_growth'])}%<br/>
                    判断置信度：{format_percentage(kitchin['confidence'])}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            f"""
            <div class="apple-card">
                <div class="apple-metric-label">产能周期 · 朱格拉</div>
                <div class="apple-metric-value" style="margin-bottom:0.6rem;">{juglar['phase_name']}</div>
                <div class="chip {get_phase_color(juglar['phase'])}">信号强度 {format_percentage(juglar['confidence'])}</div>
                <div style="margin-top:0.8rem; font-size:0.95rem; color:#3a3a3c;">
                    阶段已持续：约 {juglar['time_in_phase']} 个月<br/>
                    下个拐点：{juglar['next_inflection']}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            f"""
            <div class="apple-card">
                <div class="apple-metric-label">市场情绪 · 马克斯钟摆</div>
                <div class="apple-metric-value" style="margin-bottom:0.6rem;">{pendulum['total_score']:.1f} / 100</div>
                <div class="chip {get_temperature_color(pendulum['total_score'])}">{pendulum['level']}</div>
                <div style="margin-top:0.8rem; font-size:0.95rem; color:#3a3a3c;">
                    估值温度：{format_number(pendulum['valuation'], show_sign=False)}<br/>
                    情绪分项：{format_number(pendulum['sentiment'], show_sign=False)}<br/>
                    流动性：{format_number(pendulum['liquidity'], show_sign=False)}<br/>
                    市场宽度：{format_number(pendulum['breadth'], show_sign=False)}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_strategy_section(strategies: Dict[str, Dict[str, Any]]) -> None:
    if not strategies:
        return

    st.markdown("### 🧭 经典资产配置策略")
    cols = st.columns(len(strategies))

    display_names = {
        "swensen": "斯文森捐赠组合",
        "all_weather": "全天候资产配置",
    }

    for col, (key, payload) in zip(cols, strategies.items()):
        name = payload.get("name", display_names.get(key, key.title()))
        portfolio = payload.get("portfolio", {})
        weights = payload.get("weights", {})
        notes = payload.get("notes", [])

        weights_rows = "".join(
            f"<tr><td>{asset}</td><td>{format_percentage(weight)}</td></tr>" for asset, weight in weights.items()
        )
        notes_rows = "".join(f"<li>{note}</li>" for note in notes)

        col.markdown(
            f"""
            <div class="apple-card">
                <div class="apple-metric-label">{name}</div>
                <div style="margin-top:0.6rem; font-size:0.95rem; color:#3a3a3c;">
                    预期年化收益：{format_percentage(portfolio.get('annual_return'))}<br/>
                    组合波动率：{format_percentage(portfolio.get('annual_volatility'))}<br/>
                    最大回撤：{format_percentage(portfolio.get('max_drawdown'), show_sign=True)}
                </div>
                <table class="apple-table">
                    <thead><tr><th>资产</th><th>目标权重</th></tr></thead>
                    <tbody>{weights_rows}</tbody>
                </table>
                <div style="margin-top:1rem; font-size:0.85rem; color:#6e6e73;">
                    <ul style="padding-left:1.2rem; margin:0;">{notes_rows}</ul>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_investment_advice(advice: Dict[str, Any], strategies: Dict[str, Dict[str, Any]]) -> None:
    st.markdown("### 💡 当期配置建议")

    col1, col2 = st.columns([1.1, 1.5])

    with col1:
        st.markdown(
            f"""
            <div class="apple-card">
                <div class="apple-metric-label">综合仓位建议</div>
                <div class="apple-metric-value">{format_percentage(advice['recommended_position'])}</div>
                <div style="margin:1rem 0 0.5rem 0;">
                    <div class="chip {get_signal_color(advice['timing_signal'])}">择时信号：{advice['timing_signal']}</div>
                </div>
                <div style="color:#3a3a3c; font-size:0.95rem;">
                    情绪策略：{advice['sentiment_action']}<br/>
                    风险等级：{advice['risk_level']}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        sector_rec = advice['sector_advice']['combined_recommendation']
        overweight = sector_rec.get('overweight', [])[:5]
        neutral = sector_rec.get('neutral', [])[:4]
        underweight = sector_rec.get('underweight', [])[:4]
        sectors_df = pd.DataFrame(
            {
                '配置': ['超配'] * len(overweight) + ['标配'] * len(neutral) + ['低配'] * len(underweight),
                '行业': overweight + neutral + underweight,
            }
        )

        st.markdown("<div class='apple-card'><div class='apple-metric-label'>行业配置偏好</div>", unsafe_allow_html=True)
        if sectors_df.empty:
            st.caption("暂无行业配置建议，请刷新数据。")
        else:
            st.dataframe(sectors_df, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

    render_strategy_section(strategies)


def render_key_points(advice: Dict[str, Any]) -> None:
    st.markdown("### 📌 关键要点")
    points = advice.get('key_points', [])
    items = "".join(f"<li>{point}</li>" for point in points)
    if not items:
        items = "<li>暂无结论，请稍后重试。</li>"

    st.markdown(
        f"""
        <div class="apple-card" style="padding:1.4rem 1.6rem;">
            <ul style="margin:0; padding-left:1.2rem; color:#3a3a3c; font-size:0.95rem;">{items}</ul>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_cycle_trend_chart(
    cycle_history: Dict[str, pd.DataFrame],
    juglar_history: Dict[str, pd.Series],
) -> None:
    kitchin_df = cycle_history.get('kitchin', pd.DataFrame()).copy()
    pendulum_df = cycle_history.get('pendulum', pd.DataFrame()).copy()

    if not kitchin_df.empty:
        if 'date' in kitchin_df.columns:
            kitchin_df['date'] = pd.to_datetime(kitchin_df['date'], errors='coerce')
        else:
            kitchin_df['date'] = pd.to_datetime(kitchin_df.get('period'), errors='coerce')
        kitchin_df = kitchin_df.dropna(subset=['date']).sort_values('date')
        kitchin_df['inventory_growth'] = pd.to_numeric(kitchin_df['inventory_growth'], errors='coerce')
        kitchin_df['demand_growth'] = pd.to_numeric(kitchin_df['demand_growth'], errors='coerce')
    if not pendulum_df.empty:
        pendulum_df['timestamp'] = pd.to_datetime(pendulum_df['timestamp'], errors='coerce')
        pendulum_df = pendulum_df.dropna(subset=['timestamp']).sort_values('timestamp')
        pendulum_df['total_score'] = pd.to_numeric(pendulum_df['total_score'], errors='coerce')

    juglar_frames: Dict[str, pd.Series] = {}
    for key, series in juglar_history.items():
        if isinstance(series, pd.Series) and not series.empty:
            cleaned = pd.to_numeric(series, errors='coerce')
            cleaned.index = pd.to_datetime(series.index, errors='coerce')
            cleaned = cleaned.dropna()
            if not cleaned.empty:
                juglar_frames[key] = cleaned.sort_index()

    juglar_df = pd.DataFrame(juglar_frames) if juglar_frames else pd.DataFrame()
    if not juglar_df.empty:
        juglar_df = juglar_df.dropna(how='all').sort_index()

    if kitchin_df.empty and pendulum_df.empty and juglar_df.empty:
        st.info("暂无可视化数据，请先刷新或下载最新数据。")
        return

    fig = make_subplots(
        rows=3,
        cols=1,
        specs=[[{"secondary_y": True}], [{}], [{}]],
        subplot_titles=("库存周期：需求 vs 库存增速", "朱格拉关键指标", "市场情绪温度"),
        vertical_spacing=0.12,
    )

    if not kitchin_df.empty:
        fig.add_trace(
            go.Scatter(
                x=kitchin_df['date'],
                y=kitchin_df['inventory_growth'],
                name='库存增速',
                mode='lines',
                line=dict(color='#0a84ff', width=2),
            ),
            row=1,
            col=1,
            secondary_y=False,
        )
        fig.add_trace(
            go.Scatter(
                x=kitchin_df['date'],
                y=kitchin_df['demand_growth'],
                name='需求增速',
                mode='lines',
                line=dict(color='#34c759', width=2),
            ),
            row=1,
            col=1,
            secondary_y=False,
        )
        fig.add_trace(
            go.Scatter(
                x=kitchin_df['date'],
                y=kitchin_df['phase'],
                name='阶段',
                mode='lines',
                line=dict(color='#ff9f0a', width=1.4, dash='dot', shape='hv'),
            ),
            row=1,
            col=1,
            secondary_y=True,
        )
        fig.update_yaxes(title_text='增速 (%)', row=1, col=1, secondary_y=False)
        fig.update_yaxes(
            title_text='阶段',
            row=1,
            col=1,
            secondary_y=True,
            tickvals=[1, 2, 3, 4],
            ticktext=['被动补库', '主动补库', '被动去库', '主动去库'],
        )

    if not juglar_df.empty:
        labels = {
            'capacity_utilization': '产能利用率',
            'fixed_investment': '固定投资增速',
            'ppi': 'PPI同比',
            'roe': 'ROE趋势',
            'credit_growth': '信贷增速',
        }
        for column in juglar_df.columns[:3]:
            fig.add_trace(
                go.Scatter(
                    x=juglar_df.index,
                    y=juglar_df[column],
                    mode='lines',
                    name=labels.get(column, column),
                ),
                row=2,
                col=1,
            )
        fig.update_yaxes(title_text='指数 / 增速', row=2, col=1)

    if not pendulum_df.empty:
        fig.add_trace(
            go.Scatter(
                x=pendulum_df['timestamp'],
                y=pendulum_df['total_score'],
                mode='lines',
                name='情绪温度',
                line=dict(color='#ff375f', width=2),
                fill='tozeroy',
                fillcolor='rgba(255, 55, 95, 0.08)',
            ),
            row=3,
            col=1,
        )
        fig.add_hline(y=80, line_dash='dash', line_color='#ff3b30', row=3, col=1)
        fig.add_hline(y=20, line_dash='dash', line_color='#34c759', row=3, col=1)
        fig.update_yaxes(title_text='得分', row=3, col=1)

    fig.update_layout(
        height=900,
        showlegend=True,
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        margin=dict(l=40, r=40, t=80, b=40),
    )

    st.plotly_chart(fig, use_container_width=True)

    if kitchin_df.empty:
        st.caption("⚠️ 暂无库存周期历史数据，请刷新或重新下载。")
    if juglar_df.empty:
        st.caption("⚠️ 暂无朱格拉指标历史数据，请刷新或重新下载。")
    if pendulum_df.empty:
        st.caption("⚠️ 暂无情绪历史数据，请刷新或重新下载。")


def render_sentiment_chart(pendulum: Dict[str, Any]) -> None:
    categories = ['估值', '情绪', '流动性', '市场宽度']
    values = [
        _to_float(pendulum.get('valuation')) or 0,
        _to_float(pendulum.get('sentiment')) or 0,
        _to_float(pendulum.get('liquidity')) or 0,
        _to_float(pendulum.get('breadth')) or 0,
    ]

    fig = go.Figure(
        data=go.Scatterpolar(r=values, theta=categories, fill='toself', name='当前状态')
    )
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        showlegend=False,
        height=420,
    )
    st.plotly_chart(fig, use_container_width=True)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("估值", format_number(pendulum.get('valuation'), show_sign=False))
    col2.metric("情绪", format_number(pendulum.get('sentiment'), show_sign=False))
    col3.metric("流动性", format_number(pendulum.get('liquidity'), show_sign=False))
    col4.metric("市场宽度", format_number(pendulum.get('breadth'), show_sign=False))


def render_sector_rotation_chart(advice: Dict[str, Any]) -> None:
    sectors = advice['sector_advice']['combined_recommendation']
    overweight = sectors.get('overweight', [])[:5]
    underweight = sectors.get('underweight', [])[:4]

    if not overweight and not underweight:
        st.info("暂无行业轮动数据，请刷新分析。")
        return

    fig = go.Figure()
    if overweight:
        fig.add_trace(
            go.Bar(
                y=overweight,
                x=[1.0] * len(overweight),
                orientation='h',
                name='超配',
                marker_color='#34c759',
            )
        )
    if underweight:
        fig.add_trace(
            go.Bar(
                y=underweight,
                x=[-1.0] * len(underweight),
                orientation='h',
                name='低配',
                marker_color='#ff3b30',
            )
        )

    fig.update_layout(
        title="行业配置建议",
        xaxis_title="配置倾向",
        yaxis_title="行业",
        barmode='relative',
        height=420,
    )
    fig.update_xaxes(showticklabels=False)

    st.plotly_chart(fig, use_container_width=True)


def render_charts(
    cycle_history: Dict[str, pd.DataFrame],
    juglar_history: Dict[str, pd.Series],
    cycle_analysis: Dict[str, Any],
    advice: Dict[str, Any],
) -> None:
    st.markdown("### 📈 数据可视化")

    tab1, tab2, tab3 = st.tabs(["周期趋势", "情绪雷达", "行业轮动"])

    with tab1:
        render_cycle_trend_chart(cycle_history, juglar_history)

    with tab2:
        render_sentiment_chart(cycle_analysis['pendulum'])

    with tab3:
        render_sector_rotation_chart(advice)


# ---------------------------------------------------------------------------
# 业务逻辑
# ---------------------------------------------------------------------------

def trigger_data_download(years: int = 5) -> None:
    downloader = DataDownloader()
    downloader.download_all(years=years)
    st.cache_data.clear()


def main() -> None:
    with st.sidebar:
        st.image(
            "https://assets.apple.com/v/iphone/home/y/images/overview/hero_iphone_15__f8dvj96oq0mm_large.jpg",
            use_column_width=True,
        )

        st.markdown("---")
        st.markdown("### ⚙️ 设置")

        if st.button("⬇️ 下载最新数据", use_container_width=True):
            with st.spinner("正在下载最新数据..."):
                trigger_data_download(years=5)
            st.success("数据下载完成，缓存已更新")
            st.rerun()

        if st.button("🔄 刷新分析", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

        report = get_daily_report()
        st.download_button(
            label="📥 下载今日报告",
            data=report,
            file_name=f"report_{datetime.now().strftime('%Y%m%d')}.txt",
            mime="text/plain",
            use_container_width=True,
        )

        cache_overview = get_cache_overview()
        dataset_labels = {
            "macro_data": "宏观数据",
            "market_data": "市场行情",
            "industry_data": "行业分类",
            "valuation_data": "估值指标",
            "fund_data": "资金流向",
            "strategy_data": "策略缓存",
        }

        st.markdown("---")
        st.markdown("### 🗂️ 数据缓存状态")

        last_download = cache_overview.get("last_download")
        if last_download:
            st.caption(
                f"最后下载：{last_download.get('date', '--')} · 覆盖{last_download.get('years', '--')}年数据"
            )
        else:
            st.warning("尚未检测到历史缓存，建议先点击“下载最新数据”。")

        dataset_info = cache_overview.get("datasets", {})
        for key, label in dataset_labels.items():
            summary = dataset_info.get(key)
            if not summary:
                st.caption(f"{label}：暂无数据")
                continue

            total_rows = summary.get("total_rows") or 0
            st.markdown(f"**{label}** · {total_rows} 条记录")

            entries = []
            for item in summary.get("items", []):
                name = item.get("key") or "记录"
                rows = item.get("rows")
                if rows is None:
                    entries.append(str(name))
                else:
                    entries.append(f"{name}（{rows}）")

            if entries:
                st.caption("，".join(entries))

        file_sizes = cache_overview.get("files", {})
        if file_sizes:
            total_bytes = sum(file_sizes.values())
            st.caption(
                f"缓存文件 {len(file_sizes)} 个 · 共 {total_bytes / 1024:.1f} KB"
            )

        st.markdown("---")
        st.markdown("### 📚 快速链接")
        st.markdown("- [使用指南](README.md)")
        st.markdown("- [新手指南](新手使用指南.md)")
        st.markdown("- [GitHub](https://github.com/akfamily/akshare)")

        st.markdown("---")
        st.markdown(
            """
            **版本**: 1.0.0  
            **更新**: 2025-10-21  
            **作者**: AI量化团队
            """
        )

    try:
        cycle_analysis = get_market_analysis_data()
        advice = get_investment_advice_data()
        strategies = get_strategy_data()
        cycle_history = get_cycle_history_data()
        juglar_history = get_juglar_indicator_data()

        render_header(cycle_analysis)
        render_cycle_dashboard(cycle_analysis)
        st.markdown("---")

        render_investment_advice(advice, strategies)
        st.markdown("---")

        render_key_points(advice)
        st.markdown("---")

        render_charts(cycle_history, juglar_history, cycle_analysis, advice)

    except Exception as exc:  # pragma: no cover - UI 层兜底提示
        st.error(f"加载数据失败: {exc}")
        st.info("请确保已经运行 `python scripts/download_data.py` 下载数据缓存。")

    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; color: gray;'>© 2025 A股量化分析系统 | 仅供学习研究使用</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
