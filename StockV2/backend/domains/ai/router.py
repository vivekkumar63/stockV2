from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from domains.ai.explainer import SignalExplainer, SellExplainer
from domains.strategies.service import StrategyService

router = APIRouter(tags=["ai"])


@router.get("/signals/{signal_id}/explanation")
def get_signal_explanation(signal_id: int, db: Session = Depends(get_db)):
    signal = StrategyService(db).get_signal_by_id(signal_id)
    if not signal:
        raise HTTPException(status_code=404, detail=f"Signal {signal_id} not found")

    if signal["signal_type"] == "BUY":
        result = SignalExplainer(db).explain(signal_id)
    elif signal["signal_type"] == "SELL":
        result = SellExplainer(db).explain(signal_id)
    else:
        raise HTTPException(status_code=400, detail="Explanation only available for BUY or SELL signals")

    if result is None:
        raise HTTPException(status_code=503, detail="AI explanation unavailable — check ANTHROPIC_API_KEY")
    return result
