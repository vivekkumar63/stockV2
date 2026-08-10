from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

import pandas as pd


class StrategyType(str, Enum):
    TECHNICAL = "technical"
    FUNDAMENTAL = "fundamental"
    ML = "ml"
    CUSTOM = "custom"


class Timeframe(str, Enum):
    DAILY = "daily"
    INTRADAY_15M = "intraday_15m"
    INTRADAY_1H = "intraday_1h"


@dataclass
class Signal:
    signal_type: Literal["BUY", "SELL", "WATCH", "NONE"]
    confidence: float = 0.0
    risk_score: float = 0.5
    expected_upside_pct: float = 0.0
    stop_loss_pct: float = 7.0
    target_pct: float = 15.0
    holding_days: int = 15
    conditions_met: list[str] = field(default_factory=list)
    conditions_failed: list[str] = field(default_factory=list)


class BaseStrategy(ABC):
    name: str = ""
    description: str = ""
    strategy_type: StrategyType = StrategyType.TECHNICAL
    timeframe: Timeframe = Timeframe.DAILY
    min_holding_days: int = 5
    max_holding_days: int = 30
    weight: float = 0.20

    @abstractmethod
    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal: ...

    def get_parameters(self) -> dict:
        return {}

    def get_required_indicators(self) -> list[str]:
        return []
