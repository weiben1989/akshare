"""资产配置策略集合。"""

from .swensen import SwensenPortfolioStrategy
from .all_weather import AllWeatherPortfolioStrategy

__all__ = [
    'SwensenPortfolioStrategy',
    'AllWeatherPortfolioStrategy',
]
