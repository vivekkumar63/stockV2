"""
Portfolio risk guard — enforces limits before allowing a new position entry.

Checks (in order):
  1. Open position count   — max MAX_POSITIONS open at once
  2. Opportunity score     — signal must score >= MIN_OPPORTUNITY_SCORE (if provided)
  3. False signal rate     — strategy must have < MAX_FALSE_SIGNAL_RATE (if data exists)
  4. Sector concentration  — sector must be < MAX_SECTOR_PCT of total positions

All checks are advisory by default; the caller decides whether to block or warn.
Each check result includes "passed", "name", and a human-readable "reason".
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

MAX_POSITIONS         = 10     # maximum open positions
MIN_OPPORTUNITY_SCORE = 35     # minimum score to allow entry (grade C or better)
MAX_FALSE_SIGNAL_RATE = 0.70   # block if strategy has >70% false signals recently
MAX_SECTOR_PCT        = 0.40   # max 40% of positions in one sector


@dataclass
class RiskCheck:
    name: str
    passed: bool
    reason: str
    blocking: bool = True   # False = advisory warning, not a hard block


@dataclass
class RiskCheckResult:
    allowed: bool
    symbol: str
    checks: list[RiskCheck] = field(default_factory=list)
    summary: str = ""

    def warnings(self) -> list[RiskCheck]:
        return [c for c in self.checks if not c.passed and not c.blocking]

    def blockers(self) -> list[RiskCheck]:
        return [c for c in self.checks if not c.passed and c.blocking]


class RiskGuard:
    """
    Enforces portfolio-level risk rules before entering a new position.

    Usage:
        result = RiskGuard().check_entry(db, symbol="RELIANCE",
                                         strategy_id=2,
                                         opportunity_score=72)
        if result.allowed:
            enter_position(...)
    """

    def check_entry(
        self,
        db: Session,
        symbol: str,
        strategy_id: Optional[int] = None,
        opportunity_score: Optional[int] = None,
    ) -> RiskCheckResult:
        checks: list[RiskCheck] = []
        sym = symbol.upper()

        # ── 1. Open position count ────────────────────────────────────────────
        open_count = self._count_open_positions(db)
        checks.append(RiskCheck(
            name="max_positions",
            passed=open_count < MAX_POSITIONS,
            reason=(
                f"{open_count}/{MAX_POSITIONS} positions open — at limit"
                if open_count >= MAX_POSITIONS
                else f"{open_count}/{MAX_POSITIONS} positions open"
            ),
            blocking=True,
        ))

        # ── 2. Opportunity score ──────────────────────────────────────────────
        if opportunity_score is not None:
            checks.append(RiskCheck(
                name="opportunity_score",
                passed=opportunity_score >= MIN_OPPORTUNITY_SCORE,
                reason=(
                    f"Score {opportunity_score} < minimum {MIN_OPPORTUNITY_SCORE}"
                    if opportunity_score < MIN_OPPORTUNITY_SCORE
                    else f"Score {opportunity_score} meets minimum {MIN_OPPORTUNITY_SCORE}"
                ),
                blocking=True,
            ))

        # ── 3. False signal rate ──────────────────────────────────────────────
        if strategy_id is not None:
            false_rate = self._get_false_signal_rate(db, strategy_id)
            if false_rate is not None:
                checks.append(RiskCheck(
                    name="false_signal_rate",
                    passed=false_rate < MAX_FALSE_SIGNAL_RATE,
                    reason=(
                        f"Strategy false signal rate {false_rate:.0%} >= {MAX_FALSE_SIGNAL_RATE:.0%} limit"
                        if false_rate >= MAX_FALSE_SIGNAL_RATE
                        else f"Strategy false signal rate {false_rate:.0%} within limit"
                    ),
                    blocking=True,
                ))

        # ── 4. Sector concentration ───────────────────────────────────────────
        sector = self._get_sector(db, sym)
        if sector:
            sector_count, total = self._sector_counts(db, sector)
            sector_pct = sector_count / total if total > 0 else 0.0
            checks.append(RiskCheck(
                name="sector_concentration",
                passed=sector_pct < MAX_SECTOR_PCT,
                reason=(
                    f"{sector} at {sector_pct:.0%} of portfolio (limit {MAX_SECTOR_PCT:.0%})"
                    if sector_pct >= MAX_SECTOR_PCT
                    else f"{sector} at {sector_pct:.0%} — within {MAX_SECTOR_PCT:.0%} limit"
                ),
                blocking=False,   # advisory; don't hard-block on sector
            ))

        blocking_failures = [c for c in checks if not c.passed and c.blocking]
        allowed = len(blocking_failures) == 0

        summary = (
            "Entry allowed"
            if allowed
            else f"Entry blocked: {'; '.join(c.reason for c in blocking_failures)}"
        )

        return RiskCheckResult(
            allowed=allowed,
            symbol=sym,
            checks=checks,
            summary=summary,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _count_open_positions(self, db: Session) -> int:
        row = db.execute(
            text("SELECT COUNT(*) FROM portfolio_holdings WHERE is_active = 1")
        ).fetchone()
        return int(row[0]) if row else 0

    def _get_false_signal_rate(self, db: Session, strategy_id: int) -> Optional[float]:
        from domains.intelligence.false_signal_detector import FalseSignalDetector
        return FalseSignalDetector().get_rate_for_strategy(db, strategy_id)

    def _get_sector(self, db: Session, symbol: str) -> Optional[str]:
        row = db.execute(
            text("SELECT sector FROM stocks WHERE symbol = :s LIMIT 1"),
            {"s": symbol},
        ).fetchone()
        return str(row[0]) if row and row[0] else None

    def _sector_counts(self, db: Session, sector: str) -> tuple[int, int]:
        """Returns (sector_count, total_open_positions)."""
        rows = db.execute(
            text("""
                SELECT s.sector, COUNT(*) AS cnt
                FROM portfolio_holdings ph
                LEFT JOIN stocks s ON s.symbol = ph.symbol
                WHERE ph.is_active = 1
                GROUP BY s.sector
            """)
        ).fetchall()
        total = sum(int(r[1]) for r in rows)
        sector_count = sum(int(r[1]) for r in rows if r[0] == sector)
        return sector_count, total
