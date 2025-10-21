"""Render markdown and JSON outputs for the daily review."""
from __future__ import annotations

import json
from typing import List, Mapping


def generate_markdown(report: Mapping[str, object]) -> str:
    date = report.get("date", "")
    summary = report.get("summary", {})
    scores = report.get("scores", {})
    score_weights = report.get("score_weights", {})
    trend_sections = report.get("trend_sections", [])
    rotation_entries = report.get("rotation_entries", [])
    allocation = report.get("allocation", {})
    astro = report.get("astro", {})
    takeaways = report.get("takeaways", {})
    notes = report.get("notes", [])

    lines: List[str] = []
    lines.append(f"# 今日市场复盘（{date}）")
    lines.append("")
    lines.append(
        f"**总分：{summary.get('total_score', 0):.1f}**｜**建议仓位：{summary.get('position', 0)}%**｜**风格：{summary.get('style', '均衡')}**"
    )
    lines.append("")

    lines.append("## 量能与资金多周期观察")
    for section in trend_sections:
        label = section.get("label", "")
        details = section.get("details", [])
        title = section.get("title", "")
        lines.append(f"**{title}：{label}**")
        for detail in details:
            lines.append(f"- {detail}")
        lines.append("")

    lines.append("## 四维评分")
    lines.append("| 维度 | 权重 | 得分 |")
    lines.append("| --- | --- | --- |")
    for key in ("macro", "liquidity", "riskon", "momentum"):
        score = scores.get(key, {}).get("score", 0.0)
        weight = score_weights.get(key, 0)
        lines.append(f"| {key.title()} | {weight:.0%} | {score:.1f} |")
    lines.append(f"| **总分** | 100% | **{summary.get('total_score', 0):.1f}** |")
    lines.append("")

    lines.append("## 行业轮动矩阵")
    if rotation_entries:
        lines.append("| 行业 | 强度分位 | 拥挤分位 | 象限 | 建议 |")
        lines.append("| --- | --- | --- | --- | --- |")
        for entry in rotation_entries:
            lines.append(
                "| {industry} | {strength:.2f} | {crowding:.2f} | {quadrant} | {advice} |".format(
                    industry=entry.get("industry", ""),
                    strength=entry.get("strength", 0.0),
                    crowding=entry.get("crowding", 0.0),
                    quadrant=entry.get("quadrant", ""),
                    advice=entry.get("advice", "标配"),
                )
            )
    else:
        lines.append("数据不足导致兜底，保持原有行业权重")
    lines.append("")

    lines.append("## 金融占星提示")
    if astro.get("is_window"):
        lines.append(
            f"处于事件窗：{', '.join(e.get('type', '') for e in astro.get('events', []))}，"
            f"对风险因子调节 {astro.get('adjust', {}).get('riskon', 0)}，动量调节 {astro.get('adjust', {}).get('momentum', 0)}"
        )
    else:
        lines.append("当前无显著天象事件窗")
    lines.append("")

    lines.append("## 三段式收束")
    bullish_items = takeaways.get("bullish", [])
    bearish_items = takeaways.get("bearish", [])
    conclusion_text = takeaways.get("conclusion", "无")
    bullish_text = "；".join(bullish_items) if bullish_items else "无"
    bearish_text = "；".join(bearish_items) if bearish_items else "无"
    lines.append("**利好：**" + bullish_text)
    lines.append("**利空：**" + bearish_text)
    lines.append("**结论：**" + conclusion_text)
    lines.append("")

    if notes:
        lines.append("## 附注")
        for note in notes:
            lines.append(f"- {note}")
        lines.append("")

    deepseek_text = report.get("deepseek")
    if deepseek_text:
        lines.append("## AI 增强解读")
        lines.append(deepseek_text)
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def generate_json(report: Mapping[str, object]) -> str:
    payload = report.get("json", {})
    return json.dumps(payload, ensure_ascii=False, indent=2)


__all__ = ["generate_markdown", "generate_json"]
