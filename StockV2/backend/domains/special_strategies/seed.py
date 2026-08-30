import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from domains.special_strategies import ALL_SPECIAL_STRATEGIES

logger = logging.getLogger(__name__)


def seed_special_strategies(db: Session) -> None:
    for s in ALL_SPECIAL_STRATEGIES:
        db.execute(
            text("""
                INSERT INTO special_strategies (name, description)
                VALUES (:name, :desc)
                ON CONFLICT (name) DO NOTHING
            """),
            {"name": s.name, "desc": s.description},
        )
    db.commit()
    logger.info("[seed_special_strategies] %d special strategies seeded", len(ALL_SPECIAL_STRATEGIES))
