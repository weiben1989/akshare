"""End-to-end pipeline coordinating data ingestion, factor calculation and reporting."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from core.allocation import decide_allocation, pick_industries, rotation_map
from core.config import load_config
from core.factors import compute_multi_horizon, trend_label
from core.scoring import score_liquidity, score_macro, score_momentum, score_riskon
from integrations.deepseek import DeepSeekClient
from providers.akshare_provider import AkshareDataProvider, DataValidationError
from reporting.renderer import generate_json, generate_markdown


@dataclass
class PipelineResult:
    markdown: str
    json_text: str
    report: Dict[str, object]


class DailyReviewPipeline:
    """Pipeline entry point."""

    def __init__(self, config_path: str | Path = "config.yaml") -> None:
        self.logger = logging.getLogger(__name__)
        self.config = load_config(config_path)
        self.provider = AkshareDataProvider(self.config, logger=self.logger)
        self.windows = [int(w) for w in self.config.get("windows", [5, 10, 30])]
        score_weights = self.config.get("score_weights", {}) or {}
        total_weight = sum(float(value) for value in score_weights.values()) or 1.0
        self.score_weights = {
            key: float(value) / total_weight for key, value in score_weights.items()
        }
        self.flags = self.config.get("flags", {}) or {}

    def run(
        self,
        *,
        target_date: Optional[str] = None,
        export_dir: str | Path = "out",
        enable_deepseek: Optional[bool] = None,
    ) -> PipelineResult:
        export_path = Path(export_dir)
        export_path.mkdir(parents=True, exist_ok=True)
        review_date = self._parse_date(target_date)
        self.logger.info("Starting daily review for %s", review_date)
        raw_data = self.provider.prepare_daily_data(review_date)

        market_amount_series = self.provider.load_series("market_amount", "total_amount")
        northbound_series = self.provider.load_series("northbound", "net_flow")
        margin_series = self.provider.load_series("margin", "total_balance")
        index_series = self.provider.load_series("indices", "close", key_filters={"symbol": "sh000300"})

        etf_trends: Dict[str, Dict[int, Dict[str, Optional[float]]]] = {}
        for bucket in self.provider.etf_buckets.keys():
            series = self.provider.load_series("etf_flows", "share_change", key_filters={"bucket": bucket})
            etf_trends[bucket] = compute_multi_horizon(series, self.windows)

        market_amount_trend = compute_multi_horizon(market_amount_series, self.windows)
        northbound_trend = compute_multi_horizon(northbound_series, self.windows)
        margin_trend = compute_multi_horizon(margin_series, self.windows)
        index_trend = compute_multi_horizon(index_series, self.windows)

        liquidity_score, liquidity_components = score_liquidity(
            market_amount=market_amount_trend,
            northbound=northbound_trend,
            margin=margin_trend,
            etf_trends=etf_trends,
        )

        breadth_history = self.provider.load_table("breadth")
        breadth_history["date"] = pd.to_datetime(breadth_history["date"])
        breadth_current = breadth_history[breadth_history["date"] == pd.Timestamp(review_date)]
        if breadth_current.empty:
            breadth_current = breadth_history.tail(1)
        if breadth_current.empty:
            raise DataValidationError("Breadth data missing for scoring")
        breadth_row = breadth_current.iloc[-1].to_dict()
        risk_score, risk_components = score_riskon(breadth_row, breadth_history)

        momentum_score, momentum_components = score_momentum(
            index_trend=index_trend, amount_trend=market_amount_trend
        )

        macro_table = self.provider.load_table("macro")
        macro_table["date"] = pd.to_datetime(macro_table["date"])
        macro_table = macro_table[macro_table["date"] <= pd.Timestamp(review_date)]
        macro_latest = (
            macro_table.sort_values("date").drop_duplicates("indicator", keep="last")
        )
        macro_values = {
            row["indicator"]: float(row["value"]) for _, row in macro_latest.iterrows()
        }
        macro_score, macro_components = score_macro(macro_values)

        scores = {
            "macro": {"score": macro_score, "components": macro_components},
            "liquidity": {"score": liquidity_score, "components": liquidity_components},
            "riskon": {"score": risk_score, "components": risk_components},
            "momentum": {"score": momentum_score, "components": momentum_components},
        }

        astro_info = self._handle_astro(review_date, scores)

        total_score = self._weighted_score(scores)
        allocation_rule = decide_allocation(
            total_score * 100 if total_score <= 1 else total_score,
            self.config.get("allocation_rules", []),
        )
        if total_score <= 1:  # convert to percentage scale if weights sum to 1
            total_score *= 100
        allocation_rule["position"] = max(20, min(90, allocation_rule.get("position", 50)))

        industry_snapshot = raw_data.get("industry_snapshot")
        rotation_df = rotation_map(industry_snapshot)
        rotation_selection = pick_industries(rotation_df)
        notes: List[str] = []
        if rotation_selection.get("note"):
            notes.append(rotation_selection["note"])
        breadth_note = breadth_row.get("note")
        if breadth_note and breadth_note != "数据完整":
            notes.append(str(breadth_note))

        rotation_entries = self._build_rotation_entries(rotation_df, rotation_selection)

        trend_sections = self._build_trend_sections(
            review_date,
            market_amount_series,
            market_amount_trend,
            northbound_series,
            northbound_trend,
            margin_series,
            margin_trend,
            etf_trends,
        )

        summary = {
            "total_score": total_score,
            "position": allocation_rule.get("position", 50),
            "style": allocation_rule.get("style", "均衡"),
        }

        takeaways = self._build_takeaways(summary, trend_sections, scores, rotation_selection)

        report_payload = self._build_json_payload(
            review_date,
            market_amount_trend,
            northbound_trend,
            etf_trends,
            margin_trend,
            index_trend,
            scores,
            total_score,
            allocation_rule,
            rotation_entries,
            rotation_selection,
            astro_info,
            takeaways,
        )

        deepseek_text = None
        if self._should_use_deepseek(enable_deepseek):
            deepseek_text = self._call_deepseek(report_payload)
            if deepseek_text:
                notes.append("附带 DeepSeek 增强解读")

        report_model = {
            "date": review_date.isoformat(),
            "summary": summary,
            "scores": scores,
            "score_weights": self.score_weights,
            "trend_sections": trend_sections,
            "rotation_entries": rotation_entries,
            "allocation": {
                "overweight": rotation_selection.get("overweight", []),
                "neutral": rotation_selection.get("neutral", []),
                "underweight": rotation_selection.get("underweight", []),
            },
            "astro": astro_info,
            "takeaways": takeaways,
            "notes": notes,
            "json": report_payload,
        }
        if deepseek_text:
            report_model["deepseek"] = deepseek_text

        markdown = generate_markdown(report_model)
        json_text = generate_json(report_model)

        report_file = export_path / f"report_{review_date.isoformat()}.md"
        json_file = export_path / f"review_{review_date.isoformat()}.json"
        report_file.write_text(markdown, encoding="utf-8")
        json_file.write_text(json_text, encoding="utf-8")
        self.logger.info("Outputs written to %s and %s", report_file, json_file)

        return PipelineResult(markdown=markdown, json_text=json_text, report=report_model)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _parse_date(self, date_text: Optional[str]) -> date:
        if not date_text:
            return date.today()
        if len(date_text) == 8 and date_text.isdigit():
            return datetime.strptime(date_text, "%Y%m%d").date()
        return datetime.strptime(date_text, "%Y-%m-%d").date()

    def _weighted_score(self, scores: Dict[str, Dict[str, object]]) -> float:
        total = 0.0
        for key, weight in self.score_weights.items():
            total += float(scores.get(key, {}).get("score", 0.0)) * weight
        return total

    def _build_trend_sections(
        self,
        review_date: date,
        market_amount_series: pd.Series,
        market_trend: Dict[int, Dict[str, Optional[float]]],
        northbound_series: pd.Series,
        northbound_trend: Dict[int, Dict[str, Optional[float]]],
        margin_series: pd.Series,
        margin_trend: Dict[int, Dict[str, Optional[float]]],
        etf_trends: Dict[str, Dict[int, Dict[str, Optional[float]]]],
    ) -> List[Dict[str, object]]:
        sections = []
        sections.append(
            {
                "title": "成交额",
                "label": trend_label(market_trend),
                "details": self._format_trend_details(market_amount_series, market_trend, "亿元"),
            }
        )
        sections.append(
            {
                "title": "北向资金",
                "label": trend_label(northbound_trend),
                "details": self._format_trend_details(northbound_series, northbound_trend, "亿元"),
            }
        )
        sections.append(
            {
                "title": "融资余额",
                "label": trend_label(margin_trend),
                "details": self._format_trend_details(margin_series, margin_trend, "亿元"),
            }
        )
        etf_details = []
        for bucket, trend in etf_trends.items():
            label = trend_label(trend)
            detail_text = ", ".join(self._format_trend_details(None, trend, "万份"))
            etf_details.append(f"{bucket}: {label} ({detail_text})")
        sections.append(
            {
                "title": "ETF 分组",
                "label": "；".join(f"{bucket}:{trend_label(trend)}" for bucket, trend in etf_trends.items()),
                "details": etf_details,
            }
        )
        return sections

    def _format_trend_details(
        self,
        series: Optional[pd.Series],
        trend: Dict[int, Dict[str, Optional[float]]],
        unit: str = "",
    ) -> List[str]:
        details: List[str] = []
        if series is not None and not series.empty:
            latest = series.dropna().iloc[-1]
            details.append(f"最新值 {latest:,.2f}{unit}")
        for window in self.windows:
            metrics = trend.get(window, {})
            ema = metrics.get("ema")
            slope = metrics.get("slope")
            z = metrics.get("z")
            if ema is None and slope is None and z is None:
                continue
            parts = []
            if ema is not None:
                parts.append(f"EMA {ema:,.2f}{unit}")
            if slope is not None:
                parts.append(f"斜率 {slope:.4f}")
            if z is not None:
                parts.append(f"z-score {z:.2f}")
            details.append(f"{window}日: " + ", ".join(parts))
        if not details:
            details.append("数据不足")
        return details

    def _build_rotation_entries(
        self,
        rotation_df: pd.DataFrame,
        rotation_selection: Dict[str, List[str]],
    ) -> List[Dict[str, object]]:
        entries: List[Dict[str, object]] = []
        if rotation_df is None or rotation_df.empty:
            return entries
        overweight = set(rotation_selection.get("overweight", []))
        underweight = set(rotation_selection.get("underweight", []))
        for _, row in rotation_df.iterrows():
            industry = row.get("industry")
            advice = "标配"
            if industry in overweight:
                advice = "超配"
            elif industry in underweight:
                advice = "低配"
            entries.append(
                {
                    "industry": industry,
                    "strength": float(row.get("strength", 0.0) or 0.0),
                    "crowding": float(row.get("crowding", 0.0) or 0.0),
                    "quadrant": row.get("quadrant", ""),
                    "advice": advice,
                }
            )
        return entries

    def _build_takeaways(
        self,
        summary: Dict[str, object],
        trend_sections: List[Dict[str, object]],
        scores: Dict[str, Dict[str, object]],
        rotation_selection: Dict[str, List[str]],
    ) -> Dict[str, object]:
        bullish: List[str] = []
        bearish: List[str] = []
        for section in trend_sections:
            label = section.get("label", "")
            title = section.get("title", "")
            if isinstance(label, str) and label.startswith("多周期共振上行"):
                bullish.append(f"{title}{label}")
            if isinstance(label, str) and "走弱" in label:
                bearish.append(f"{title}{label}")
        if scores.get("liquidity", {}).get("score", 0) > 60:
            bullish.append("流动性维度回升")
        if scores.get("macro", {}).get("score", 0) < 45:
            bearish.append("宏观指标偏弱")
        conclusion = (
            f"仓位 {summary.get('position', 0)}%，风格 {summary.get('style', '均衡')}，"
            f"超配 {', '.join(rotation_selection.get('overweight', []) or ['无'])}，"
            f"低配 {', '.join(rotation_selection.get('underweight', []) or ['无'])}。"
        )
        return {"bullish": bullish, "bearish": bearish, "conclusion": conclusion}

    def _build_json_payload(
        self,
        review_date: date,
        market_trend: Dict[int, Dict[str, Optional[float]]],
        northbound_trend: Dict[int, Dict[str, Optional[float]]],
        etf_trends: Dict[str, Dict[int, Dict[str, Optional[float]]]],
        margin_trend: Dict[int, Dict[str, Optional[float]]],
        index_trend: Dict[int, Dict[str, Optional[float]]],
        scores: Dict[str, Dict[str, object]],
        total_score: float,
        allocation_rule: Dict[str, object],
        rotation_entries: List[Dict[str, object]],
        rotation_selection: Dict[str, List[str]],
        astro_info: Dict[str, object],
        takeaways: Dict[str, object],
    ) -> Dict[str, object]:
        def encode_trend(trend: Dict[int, Dict[str, Optional[float]]]) -> Dict[str, Dict[str, Optional[float]]]:
            payload = {}
            for window, metrics in trend.items():
                payload[str(window)] = {key: (float(value) if value is not None else None) for key, value in metrics.items()}
            return payload

        rotation_json = [
            {
                "industry": entry.get("industry"),
                "strength": entry.get("strength"),
                "crowding": entry.get("crowding"),
                "quadrant": entry.get("quadrant"),
                "advice": entry.get("advice"),
            }
            for entry in rotation_entries
        ]
        allocation_payload = {
            "position": allocation_rule.get("position"),
            "style": allocation_rule.get("style"),
            "overweight": rotation_selection.get("overweight", []),
            "neutral": rotation_selection.get("neutral", []),
            "underweight": rotation_selection.get("underweight", []),
        }
        score_payload = {
            key: float(value.get("score", 0.0)) for key, value in scores.items()
        }
        score_payload["total"] = float(total_score)
        return {
            "date": review_date.isoformat(),
            "trends": {
                "market_amount": encode_trend(market_trend),
                "northbound": encode_trend(northbound_trend),
                "etf_flows": {bucket: encode_trend(trend) for bucket, trend in etf_trends.items()},
                "margin": encode_trend(margin_trend),
                "index": encode_trend(index_trend),
            },
            "scores": score_payload,
            "allocation": allocation_payload,
            "rotation_map": rotation_json,
            "astro": astro_info,
            "takeaways": takeaways,
        }

    def _handle_astro(self, review_date: date, scores: Dict[str, Dict[str, object]]) -> Dict[str, object]:
        if not self.flags.get("enable_astro", True):
            return {"is_window": False, "events": [], "adjust": {"riskon": 0, "momentum": 0}}
        astro_info = self.provider.get_astro_events(review_date)
        adjust = astro_info.get("adjust", {})
        if astro_info.get("is_window"):
            risk_adjust = float(adjust.get("riskon", 0) or 0)
            momentum_adjust = float(adjust.get("momentum", 0) or 0)
            scores["riskon"]["score"] = float(min(100, max(0, scores["riskon"].get("score", 0) + risk_adjust)))
            scores["momentum"]["score"] = float(min(100, max(0, scores["momentum"].get("score", 0) + momentum_adjust)))
        return astro_info

    def _should_use_deepseek(self, override: Optional[bool]) -> bool:
        if override is not None:
            return override
        return bool(self.flags.get("enable_deepseek"))

    def _call_deepseek(self, payload: Dict[str, object]) -> Optional[str]:
        client = DeepSeekClient()
        if not client.enabled:
            return None
        prompt_path = Path("integrations/deepseek_prompt.txt")
        if prompt_path.exists():
            template = prompt_path.read_text(encoding="utf-8")
        else:
            template = "你是专业分析师，请结合输入的 JSON 给出结论。"
        message = f"{template}\n\n输入 JSON:\n{json.dumps(payload, ensure_ascii=False)}"
        try:
            return client.analyze(message)
        except RuntimeError as exc:  # pragma: no cover - network failures handled upstream
            self.logger.warning("DeepSeek 分析失败: %s", exc)
            return None


__all__ = ["DailyReviewPipeline", "PipelineResult"]
