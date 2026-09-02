from domains.strategies.base import BaseStrategy, Signal, StrategyType

_TYPE_WEIGHTS: dict[StrategyType, float] = {
    StrategyType.ML: 0.35,
    StrategyType.FUNDAMENTAL: 0.05,
    StrategyType.TECHNICAL: 0.20,
    StrategyType.CUSTOM: 0.15,
}


class SignalAggregator:
    def aggregate(self, signals: list[tuple[BaseStrategy, Signal]]) -> dict:
        buy_pairs = [(s, sig) for s, sig in signals if sig.signal_type == "BUY"]
        sell_count = sum(1 for _, sig in signals if sig.signal_type == "SELL")

        if not buy_pairs:
            return {"signal_type": "NONE", "consensus_score": 0.0, "buy_count": 0, "sell_count": sell_count}

        total_weight = 0.0
        weighted_confidence = 0.0
        for strategy, signal in buy_pairs:
            w = _TYPE_WEIGHTS.get(strategy.strategy_type, 0.20)
            weighted_confidence += w * signal.confidence
            total_weight += w

        consensus_score = weighted_confidence / total_weight if total_weight > 0 else 0.0
        buy_count = len(buy_pairs)

        min_buy = min(3, len(signals))
        if consensus_score > 0.65 and buy_count >= min_buy:
            signal_type = "BUY"
        elif consensus_score > 0.45 and buy_count >= 2:
            signal_type = "WATCH"
        else:
            signal_type = "NONE"

        return {
            "signal_type": signal_type,
            "consensus_score": round(consensus_score, 4),
            "buy_count": buy_count,
            "sell_count": sell_count,
        }
