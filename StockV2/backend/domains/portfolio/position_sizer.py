from dataclasses import dataclass
from typing import Optional

from settings import settings


@dataclass
class PositionSize:
    quantity: int
    position_value: float
    risk_amount: float
    stop_loss_price: float
    target_price: float
    reject_reason: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return self.reject_reason is None and self.quantity > 0


class PositionSizer:
    def compute(
        self,
        entry_price: float,
        stop_loss_price: float,
        target_price: float,
        open_positions: int,
        invested_capital: float,
        _cfg=None,
    ) -> PositionSize:
        cfg = _cfg or settings
        risk_per_share = entry_price - stop_loss_price

        if risk_per_share <= 0:
            return PositionSize(0, 0.0, 0.0, stop_loss_price, target_price,
                                "Invalid stop loss: stop_loss_price must be below entry_price")

        risk_amount = cfg.total_capital * cfg.risk_per_trade_pct / 100
        quantity = int(risk_amount / risk_per_share)

        if quantity <= 0:
            return PositionSize(0, 0.0, risk_amount, stop_loss_price, target_price,
                                "Quantity is 0 after risk sizing")

        max_pos_value = cfg.total_capital * cfg.max_single_stock_pct / 100
        if quantity * entry_price > max_pos_value:
            quantity = int(max_pos_value / entry_price)

        if quantity <= 0:
            return PositionSize(0, 0.0, risk_amount, stop_loss_price, target_price,
                                "Quantity is 0 after max-position cap")

        position_value = round(quantity * entry_price, 2)

        if open_positions >= cfg.max_open_positions:
            return PositionSize(0, 0.0, risk_amount, stop_loss_price, target_price,
                                f"Max open positions reached ({cfg.max_open_positions})")

        available = cfg.paper_capital - invested_capital
        if position_value > available:
            return PositionSize(0, 0.0, risk_amount, stop_loss_price, target_price,
                                f"Insufficient capital: need ₹{position_value:.0f}, available ₹{available:.0f}")

        return PositionSize(
            quantity=quantity,
            position_value=position_value,
            risk_amount=risk_amount,
            stop_loss_price=stop_loss_price,
            target_price=target_price,
        )
