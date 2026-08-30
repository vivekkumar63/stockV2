import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from settings import settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are an expert Indian stock market analyst with 20 years of NSE/BSE experience. "
    "You specialise in technical analysis, fundamental analysis, and quantitative strategies. "
    "You always explain reasoning in plain English, give specific price levels, and never give "
    "generic advice. You understand NSE regulations, FII/DII behaviour, and sector cycles in "
    "Indian markets. Always respond with valid JSON only — no markdown, no extra text."
)


class SignalExplainer:
    def __init__(self, db: Session):
        self.db = db
        self._client = None
        if settings.anthropic_api_key:
            import anthropic
            self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def explain(self, signal_id: int) -> Optional[dict]:
        cached = self._get_cached(signal_id, "buy_explanation")
        if cached:
            return cached
        signal = self._load_signal(signal_id)
        if not signal or signal["signal_type"] != "BUY":
            return None
        result = self._call_claude_buy(signal)
        if result:
            self._save_cache(signal_id, "buy_explanation", result, ttl_hours=6)
        return result

    def _get_cached(self, signal_id: int, analysis_type: str) -> Optional[dict]:
        row = self.db.execute(
            text("""
                SELECT content FROM ai_analyses
                WHERE subject_type = 'signal' AND subject_id = :sid
                  AND analysis_type = :at
                  AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
            """),
            {"sid": signal_id, "at": analysis_type},
        ).fetchone()
        return json.loads(row[0]) if row else None

    def _save_cache(self, signal_id: int, analysis_type: str, content: dict, ttl_hours: int):
        # No UNIQUE constraint on ai_analyses, so DELETE then INSERT to avoid duplicates
        self.db.execute(
            text("""
                DELETE FROM ai_analyses
                WHERE subject_type = 'signal' AND subject_id = :sid
                  AND analysis_type = :at
            """),
            {"sid": signal_id, "at": analysis_type},
        )
        expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
        self.db.execute(
            text("""
                INSERT INTO ai_analyses
                (subject_type, subject_id, analysis_type, content, model_used, created_at, expires_at)
                VALUES ('signal', :sid, :at, :content, 'claude-sonnet-4-6',
                        CURRENT_TIMESTAMP, :expires)
            """),
            {
                "sid": signal_id,
                "at": analysis_type,
                "content": json.dumps(content),
                "expires": expires_at,
            },
        )
        self.db.commit()

    def _load_signal(self, signal_id: int) -> Optional[dict]:
        row = self.db.execute(
            text("""
                SELECT ss.*, s.name AS strategy_name, st.name AS stock_name, st.sector
                FROM strategy_signals ss
                JOIN strategies s ON ss.strategy_id = s.id
                LEFT JOIN stocks st ON ss.symbol = st.symbol
                WHERE ss.id = :id
            """),
            {"id": signal_id},
        ).fetchone()
        return dict(row._mapping) if row else None

    def _call_claude_buy(self, signal: dict) -> Optional[dict]:
        if not self._client:
            logger.warning("[SignalExplainer] Anthropic API key not configured")
            return None
        reasoning = json.loads(signal.get("reasoning_json") or "{}")
        user_prompt = (
            f"Analyse BUY signal for {signal['symbol']}:\n"
            f"Strategy: {signal['strategy_name']}\n"
            f"Price at signal: ₹{signal['price_at_signal']}\n"
            f"Confidence: {(signal['confidence_score'] or 0):.0%}\n"
            f"Conditions met: {', '.join(reasoning.get('conditions_met', []))}\n"
            f"Suggested stop loss: ₹{signal['suggested_stop_loss']}\n"
            f"Suggested target: ₹{signal['suggested_target']}\n"
            f"Holding period: {signal['holding_period_days']} days\n"
            f"Stock: {signal.get('stock_name', signal['symbol'])} | Sector: {signal.get('sector', 'Unknown')}\n\n"
            "Return a JSON object with keys: summary (string), bull_case (list[str]), "
            "bear_case (list[str]), confidence_reasoning (string), suggested_entry (number), "
            "stop_loss (number), target_1 (number), target_2 (number), "
            "holding_period (string), risk_rating (LOW|MEDIUM|HIGH)."
        )
        try:
            response = self._client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system=[{"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user_prompt}],
            )
            text_content = response.content[0].text.strip()
            if "```" in text_content:
                text_content = text_content.split("```")[1].lstrip("json").strip().split("```")[0]
            return json.loads(text_content)
        except Exception as e:
            logger.error("[SignalExplainer] Claude API error: %s", e)
            return None


class SellExplainer:
    def __init__(self, db: Session):
        self.db = db
        self._base = SignalExplainer(db)
        self._client = self._base._client

    def explain(self, signal_id: int) -> Optional[dict]:
        cached = self._base._get_cached(signal_id, "sell_explanation")
        if cached:
            return cached
        signal = self._base._load_signal(signal_id)
        if not signal or signal["signal_type"] != "SELL":
            return None
        result = self._call_claude_sell(signal)
        if result:
            self._base._save_cache(signal_id, "sell_explanation", result, ttl_hours=6)
        return result

    def _call_claude_sell(self, signal: dict) -> Optional[dict]:
        if not self._client:
            return None
        reasoning = json.loads(signal.get("reasoning_json") or "{}")
        user_prompt = (
            f"Analyse SELL signal for {signal['symbol']}:\n"
            f"Strategy: {signal['strategy_name']}\n"
            f"Price at signal: ₹{signal['price_at_signal']}\n"
            f"Confidence: {(signal['confidence_score'] or 0):.0%}\n"
            f"Conditions met: {', '.join(reasoning.get('conditions_met', []))}\n"
            f"Stock: {signal.get('stock_name', signal['symbol'])} | Sector: {signal.get('sector', 'Unknown')}\n\n"
            "Return a JSON object with keys: summary (string), exit_reasons (list[str]), "
            "risk_if_held (list[str]), action (EXIT_NOW|TRAIL_STOP), confidence_reasoning (string)."
        )
        try:
            response = self._client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=512,
                system=[{"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user_prompt}],
            )
            text_content = response.content[0].text.strip()
            if "```" in text_content:
                text_content = text_content.split("```")[1].lstrip("json").strip().split("```")[0]
            return json.loads(text_content)
        except Exception as e:
            logger.error("[SellExplainer] Claude API error: %s", e)
            return None
