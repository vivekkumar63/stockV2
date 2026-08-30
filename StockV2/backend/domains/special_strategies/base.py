from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class SpecialSignal:
    signal_type: str  # "BUY" | "NONE"
    confidence: float = 0.0
    conditions_met: list[str] = field(default_factory=list)
    conditions_failed: list[str] = field(default_factory=list)


class SpecialBaseStrategy(ABC):
    name: str = ""
    description: str = ""

    @abstractmethod
    def buy_signal(self, df: pd.DataFrame) -> SpecialSignal: ...

    @abstractmethod
    def sell_signal(self, df: pd.DataFrame, entry_price: float | None = None) -> bool: ...
