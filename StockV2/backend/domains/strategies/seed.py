import json
import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from domains.strategies.engine import ALL_STRATEGIES

logger = logging.getLogger(__name__)


def seed_strategies(db: Session) -> None:
    for strategy in ALL_STRATEGIES:
        db.execute(
            text("""
                INSERT INTO strategies (name, type, description, parameters_json, is_active, created_at)
                VALUES (:name, :type, :desc, :params, 1, CURRENT_TIMESTAMP)
                ON CONFLICT (name) DO NOTHING
            """),
            {
                "name": strategy.name,
                "type": strategy.strategy_type.value,
                "desc": strategy.description,
                "params": json.dumps(strategy.get_parameters()),
            },
        )
    db.commit()
    logger.info("[seed_strategies] %d strategies seeded", len(ALL_STRATEGIES))
