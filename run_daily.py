"""Command line entry point for the A 股日度复盘引擎."""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from core.pipeline import DailyReviewPipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the A 股日度复盘引擎")
    parser.add_argument("--date", help="目标交易日，格式 YYYY-MM-DD 或 YYYYMMDD", dest="date")
    parser.add_argument("--export", help="输出目录", default="out")
    parser.add_argument("--config", help="配置文件路径", default="config.yaml")
    parser.add_argument(
        "--enable-deepseek",
        help="强制启用 DeepSeek 分析",
        action="store_true",
    )
    parser.add_argument(
        "--disable-deepseek",
        help="强制关闭 DeepSeek 分析",
        action="store_true",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    pipeline = DailyReviewPipeline(config_path=args.config)
    deepseek_override = None
    if args.enable_deepseek and args.disable_deepseek:
        raise SystemExit("不能同时启用和关闭 DeepSeek 开关")
    if args.enable_deepseek:
        deepseek_override = True
    elif args.disable_deepseek:
        deepseek_override = False
    try:
        pipeline.run(
            target_date=args.date,
            export_dir=Path(args.export),
            enable_deepseek=deepseek_override,
        )
    except Exception as exc:  # noqa: BLE001
        logging.exception("日度复盘失败: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
