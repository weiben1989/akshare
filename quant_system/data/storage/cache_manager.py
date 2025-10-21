"""缓存管理工具
封装对 `data/cache/*.pkl` 的读写，统一路径处理和容错逻辑。
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import pandas as pd


class DataCacheManager:
    """简单的 pickle 缓存管理器。

    量化系统的历史数据下载脚本会将不同类别的数据保存到
    ``data/cache`` 目录下。之前的代码直接在模块内部读写文件，
    缺乏统一的封装。为了让分析模块更容易地复用缓存数据，
    我们提供这个管理器：

    * 自动定位缓存目录；
    * 统一的读写接口，并做好异常处理；
    * 兼容 pandas DataFrame / Series 等常见对象。
    """

    def __init__(self, cache_dir: Optional[Path | str] = None) -> None:
        base_dir = Path(__file__).resolve().parents[2]  # quant_system 根目录
        self.cache_dir = Path(cache_dir) if cache_dir else base_dir / "data" / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 读写接口
    # ------------------------------------------------------------------
    def load_dataset(self, name: str) -> Optional[Any]:
        """读取缓存数据。

        Args:
            name: 数据集名称（文件名不含后缀）

        Returns:
            pickle 中的原始对象，如果文件不存在则返回 ``None``。
        """

        file_path = self.cache_dir / f"{name}.pkl"
        if not file_path.exists():
            return None

        try:
            with file_path.open("rb") as f:
                return pickle.load(f)
        except Exception:
            # 如果 pickle 反序列化失败，删除损坏文件避免污染后续使用
            try:
                file_path.unlink(missing_ok=True)
            except OSError:
                pass
            return None

    def save_dataset(self, name: str, data: Any) -> None:
        """写入缓存数据。

        Args:
            name: 数据集名称（文件名不含后缀）
            data: 需要持久化的对象
        """

        file_path = self.cache_dir / f"{name}.pkl"
        with file_path.open("wb") as f:
            pickle.dump(data, f)

    # ------------------------------------------------------------------
    # 辅助工具
    # ------------------------------------------------------------------
    def get_dataframe(self, dataset: str, key: str) -> pd.DataFrame:
        """从指定数据集中提取 DataFrame。

        Args:
            dataset: 数据集名称，对应 ``*.pkl`` 文件
            key: 数据集中子 DataFrame 的键

        Returns:
            对应的 ``pandas.DataFrame``，若不存在则返回空表。
        """

        data = self.load_dataset(dataset)
        if isinstance(data, dict):
            value = data.get(key)
            if isinstance(value, pd.DataFrame):
                return value.copy()
        if isinstance(data, pd.DataFrame) and key == "":
            return data.copy()
        return pd.DataFrame()

    def list_available(self) -> Dict[str, int]:
        """列出缓存目录中可用的数据集及其大小（字节）。"""

        datasets: Dict[str, int] = {}
        for file in sorted(self.cache_dir.glob("*.pkl")):
            try:
                datasets[file.stem] = file.stat().st_size
            except OSError:
                continue
        return datasets

    def ensure_keys(self, dataset: str, keys: Iterable[str]) -> bool:
        """检查给定数据集是否同时包含指定键。

        Args:
            dataset: 数据集名称
            keys: 需要检查的键集合

        Returns:
            如果所有键都存在且对应对象不为空，返回 ``True``。
        """

        data = self.load_dataset(dataset)
        if not isinstance(data, dict):
            return False

        for key in keys:
            value = data.get(key)
            if value is None:
                return False
            if isinstance(value, pd.DataFrame) and value.empty:
                return False
        return True


__all__ = ["DataCacheManager"]

