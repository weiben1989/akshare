import pandas as pd

from core.allocation import pick_industries, rotation_map
from core.factors import compute_multi_horizon, trend_label
from core.scoring import score_liquidity, score_macro, score_momentum, score_riskon
from reporting.renderer import generate_markdown


def build_series(start: float, step: float, periods: int = 60) -> pd.Series:
    index = pd.date_range("2024-01-01", periods=periods, freq="D")
    values = [start + step * i for i in range(periods)]
    return pd.Series(values, index=index)


def test_compute_multi_horizon_basic():
    series = build_series(1000, 5)
    result = compute_multi_horizon(series, [5, 10, 30])
    assert set(result.keys()) == {5, 10, 30}
    for metrics in result.values():
        assert set(metrics.keys()) == {"ema", "slope", "z", "latest"}
        assert metrics["ema"] is not None


def test_trend_label_positive():
    series = build_series(100, 2)
    trend = compute_multi_horizon(series, [5, 10, 30])
    label = trend_label(trend)
    assert "上行" in label


def test_score_liquidity_and_momentum_ranges():
    series_up = build_series(1000, 10)
    trend = compute_multi_horizon(series_up, [5, 10, 30])
    liquidity_score, _ = score_liquidity(
        market_amount=trend,
        northbound=trend,
        margin=trend,
        etf_trends={"broad": trend},
    )
    momentum_score, _ = score_momentum(index_trend=trend, amount_trend=trend)
    assert 0 <= liquidity_score <= 100
    assert 0 <= momentum_score <= 100


def test_score_macro_and_riskon():
    history = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=40, freq="D"),
            "limit_up_count": [10 + (i % 5) for i in range(40)],
            "limit_down_count": [2 + (i % 3) for i in range(40)],
            "max_limit_up_streak": [1 + (i % 4) for i in range(40)],
            "limit_up_sustainability": [0.4 + (i % 4) * 0.05 for i in range(40)],
        }
    )
    current = history.iloc[-1].to_dict()
    risk_score, components = score_riskon(current, history)
    macro_score, _ = score_macro(
        {
            "PMI_NEW_ORDERS": 52,
            "PMI_FINISHED_GOODS": 47,
            "PPI_YOY": -1.2,
            "COMMODITY_INDEX": 105,
        }
    )
    assert 0 <= risk_score <= 100
    assert 0 <= macro_score <= 100
    assert set(components.keys()) >= {"limit_up", "limit_ratio", "sustainability"}


def test_rotation_and_markdown_structure():
    industry_df = pd.DataFrame(
        {
            "industry": ["科技", "资源", "消费"],
            "avg_return": [3.5, -1.0, 0.5],
            "net_inflow": [2.0, 1.0, -0.5],
            "turnover": [5.0, 3.0, 2.0],
            "limit_up_count": [2, 0, 1],
            "sample_size": [50, 30, 40],
        }
    )
    rotation_df = rotation_map(industry_df)
    picks = pick_industries(rotation_df)
    report_model = {
        "date": "2024-06-01",
        "summary": {"total_score": 62.5, "position": 60, "style": "均衡"},
        "scores": {
            "macro": {"score": 55.0, "components": {}},
            "liquidity": {"score": 60.0, "components": {}},
            "riskon": {"score": 58.0, "components": {}},
            "momentum": {"score": 59.0, "components": {}},
        },
        "score_weights": {"macro": 0.25, "liquidity": 0.35, "riskon": 0.2, "momentum": 0.2},
        "trend_sections": [
            {"title": "成交额", "label": "多周期共振上行", "details": ["示例"]},
        ],
        "rotation_entries": rotation_df.assign(advice="标配").to_dict(orient="records"),
        "allocation": picks,
        "astro": {"is_window": False, "events": [], "adjust": {"riskon": 0, "momentum": 0}},
        "takeaways": {"bullish": ["量能回升"], "bearish": [], "conclusion": "仓位 60%"},
        "notes": [],
        "json": {
            "date": "2024-06-01",
            "trends": {},
            "scores": {},
            "allocation": {},
            "rotation_map": [],
            "astro": {},
            "takeaways": {},
        },
    }
    markdown = generate_markdown(report_model)
    assert "利好" in markdown
    assert "利空" in markdown
    assert "结论" in markdown
