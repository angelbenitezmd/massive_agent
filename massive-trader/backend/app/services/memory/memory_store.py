"""
Memory Store - SQLite Persistence for Trade Outcomes.

Stores:
- Trade decisions and their outcomes
- Agent predictions and accuracy
- Market conditions at decision time
"""

import logging
import sqlite3
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class TradeMemory:
    """Record of a trade decision and outcome."""
    id: str
    ticker: str
    timestamp: datetime

    # Decision context
    action_taken: str  # BUY, SELL, HOLD
    entry_price: float

    # Agent contributions
    agent_predictions: Dict[str, Dict]  # agent_name -> {direction, confidence, reasoning}
    debate_summary: Optional[str] = None
    consensus_confidence: float = 50

    # Market context at decision time
    market_regime: str = "neutral"
    vix_level: float = 20
    sector_performance: Dict[str, float] = field(default_factory=dict)
    news_sentiment: str = "neutral"
    technical_regime: str = "neutral"

    # Outcome (filled later)
    exit_price: Optional[float] = None
    exit_timestamp: Optional[datetime] = None
    pnl: Optional[float] = None
    pnl_percent: Optional[float] = None
    holding_period_hours: Optional[float] = None

    # Performance attribution
    winning_agents: Optional[List[str]] = None
    losing_agents: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "ticker": self.ticker,
            "timestamp": self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else self.timestamp,
            "action_taken": self.action_taken,
            "entry_price": self.entry_price,
            "agent_predictions": self.agent_predictions,
            "debate_summary": self.debate_summary,
            "consensus_confidence": self.consensus_confidence,
            "market_regime": self.market_regime,
            "vix_level": self.vix_level,
            "sector_performance": self.sector_performance,
            "news_sentiment": self.news_sentiment,
            "technical_regime": self.technical_regime,
            "exit_price": self.exit_price,
            "exit_timestamp": self.exit_timestamp.isoformat() if isinstance(self.exit_timestamp, datetime) else self.exit_timestamp,
            "pnl": self.pnl,
            "pnl_percent": self.pnl_percent,
            "holding_period_hours": self.holding_period_hours,
            "winning_agents": self.winning_agents,
            "losing_agents": self.losing_agents,
        }


class MemoryStore:
    """
    Persistent memory for agent learning.

    Uses SQLite for simplicity, can be upgraded to PostgreSQL.
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # Default to data directory
            data_dir = Path(__file__).parent.parent.parent.parent / "data"
            data_dir.mkdir(exist_ok=True)
            db_path = str(data_dir / "trading_memory.db")

        self.db_path = db_path
        self._init_db()
        logger.info(f"MemoryStore initialized at {db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Initialize database schema."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Trade memories table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trade_memories (
                id TEXT PRIMARY KEY,
                ticker TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                action_taken TEXT NOT NULL,
                entry_price REAL NOT NULL,
                agent_predictions TEXT,
                debate_summary TEXT,
                consensus_confidence REAL,
                market_regime TEXT,
                vix_level REAL,
                sector_performance TEXT,
                news_sentiment TEXT,
                technical_regime TEXT,
                exit_price REAL,
                exit_timestamp TEXT,
                pnl REAL,
                pnl_percent REAL,
                holding_period_hours REAL,
                winning_agents TEXT,
                losing_agents TEXT
            )
        """)

        # Agent performance table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_performance (
                agent_name TEXT NOT NULL,
                period TEXT NOT NULL,
                total_predictions INTEGER DEFAULT 0,
                correct_predictions INTEGER DEFAULT 0,
                accuracy REAL DEFAULT 0.5,
                avg_confidence REAL DEFAULT 0.5,
                calibration_score REAL DEFAULT 0.5,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (agent_name, period)
            )
        """)

        # Market regime performance table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_regime_performance (
                regime TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                accuracy REAL DEFAULT 0.5,
                sample_count INTEGER DEFAULT 0,
                PRIMARY KEY (regime, agent_name)
            )
        """)

        # Confidence bucket performance (for calibration)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS confidence_buckets (
                agent_name TEXT NOT NULL,
                bucket INTEGER NOT NULL,
                total_predictions INTEGER DEFAULT 0,
                correct_predictions INTEGER DEFAULT 0,
                PRIMARY KEY (agent_name, bucket)
            )
        """)

        # Completed trades table (performance tracking)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS completed_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                side TEXT NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL NOT NULL,
                entry_time TEXT NOT NULL,
                exit_time TEXT NOT NULL,
                quantity REAL NOT NULL,
                pnl REAL NOT NULL,
                pnl_pct REAL NOT NULL,
                hold_time_minutes REAL,
                score_at_entry REAL,
                atr_at_entry REAL,
                rvol_at_entry REAL,
                regime_at_entry TEXT,
                source TEXT,
                exit_reason TEXT
            )
        """)

        # Create indices
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_ticker
            ON trade_memories(ticker)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_timestamp
            ON trade_memories(timestamp)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_regime
            ON trade_memories(market_regime)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_completed_ticker
            ON completed_trades(ticker)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_completed_exit_time
            ON completed_trades(exit_time)
        """)

        conn.commit()
        conn.close()

    async def store_decision(self, memory: TradeMemory) -> str:
        """Store a new trade decision."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT OR REPLACE INTO trade_memories (
                    id, ticker, timestamp, action_taken, entry_price,
                    agent_predictions, debate_summary, consensus_confidence,
                    market_regime, vix_level, sector_performance,
                    news_sentiment, technical_regime
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                memory.id,
                memory.ticker,
                memory.timestamp.isoformat() if isinstance(memory.timestamp, datetime) else memory.timestamp,
                memory.action_taken,
                memory.entry_price,
                json.dumps(memory.agent_predictions),
                memory.debate_summary,
                memory.consensus_confidence,
                memory.market_regime,
                memory.vix_level,
                json.dumps(memory.sector_performance),
                memory.news_sentiment,
                memory.technical_regime,
            ))

            conn.commit()
            logger.info(f"Stored trade decision: {memory.id}")
            return memory.id

        except Exception as e:
            logger.error(f"Error storing decision: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

    async def update_outcome(
        self,
        memory_id: str,
        exit_price: float,
        exit_timestamp: datetime,
        pnl: float,
        pnl_percent: float,
    ) -> None:
        """Update a trade memory with the outcome."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Get the original memory
            cursor.execute(
                "SELECT * FROM trade_memories WHERE id = ?",
                (memory_id,)
            )
            row = cursor.fetchone()

            if not row:
                logger.warning(f"Memory {memory_id} not found")
                return

            # Parse agent predictions
            agent_predictions = json.loads(row["agent_predictions"]) if row["agent_predictions"] else {}
            entry_price = row["entry_price"]
            action_taken = row["action_taken"]

            # Calculate holding period
            entry_ts = datetime.fromisoformat(row["timestamp"])
            holding_hours = (exit_timestamp - entry_ts).total_seconds() / 3600

            # Determine winning/losing agents
            winning_agents = []
            losing_agents = []

            for agent_name, prediction in agent_predictions.items():
                predicted_direction = prediction.get("direction", "HOLD")

                # Agent was right if they predicted the profitable direction
                if action_taken in ["BUY", "STRONG_BUY"]:
                    # We bought - agents who said BUY were right if we made money
                    if predicted_direction in ["BUY", "STRONG_BUY"] and pnl > 0:
                        winning_agents.append(agent_name)
                    elif predicted_direction in ["SELL", "STRONG_SELL"] and pnl < 0:
                        winning_agents.append(agent_name)  # They warned us correctly
                    elif predicted_direction in ["SELL", "STRONG_SELL", "HOLD"] and pnl > 0:
                        losing_agents.append(agent_name)  # They said not to, but we made money
                    elif predicted_direction in ["BUY", "STRONG_BUY"] and pnl < 0:
                        losing_agents.append(agent_name)  # They said buy but we lost
                elif action_taken in ["SELL", "STRONG_SELL"]:
                    # Similar logic for sells
                    if predicted_direction in ["SELL", "STRONG_SELL"] and pnl > 0:
                        winning_agents.append(agent_name)
                    elif predicted_direction in ["SELL", "STRONG_SELL"] and pnl < 0:
                        losing_agents.append(agent_name)

            # Update the record
            cursor.execute("""
                UPDATE trade_memories SET
                    exit_price = ?,
                    exit_timestamp = ?,
                    pnl = ?,
                    pnl_percent = ?,
                    holding_period_hours = ?,
                    winning_agents = ?,
                    losing_agents = ?
                WHERE id = ?
            """, (
                exit_price,
                exit_timestamp.isoformat(),
                pnl,
                pnl_percent,
                holding_hours,
                json.dumps(winning_agents),
                json.dumps(losing_agents),
                memory_id,
            ))

            conn.commit()
            logger.info(f"Updated outcome for {memory_id}: PnL={pnl_percent:.2f}%")

            # Update agent performance
            await self._update_agent_performance(
                winning_agents, losing_agents, agent_predictions, row["market_regime"]
            )

        except Exception as e:
            logger.error(f"Error updating outcome: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()

    async def _update_agent_performance(
        self,
        winning_agents: List[str],
        losing_agents: List[str],
        agent_predictions: Dict[str, Dict],
        market_regime: str,
    ) -> None:
        """Update agent performance metrics."""
        conn = self._get_connection()
        cursor = conn.cursor()
        now = datetime.utcnow().isoformat()

        try:
            all_agents = set(winning_agents + losing_agents)

            for agent_name in all_agents:
                is_correct = agent_name in winning_agents
                confidence = agent_predictions.get(agent_name, {}).get("confidence", 50)
                bucket = int(confidence // 10) * 10  # 0, 10, 20, ... 90

                # Update overall performance
                for period in ["day", "week", "month", "all"]:
                    cursor.execute("""
                        INSERT INTO agent_performance
                            (agent_name, period, total_predictions, correct_predictions,
                             accuracy, avg_confidence, updated_at)
                        VALUES (?, ?, 1, ?, ?, ?, ?)
                        ON CONFLICT(agent_name, period) DO UPDATE SET
                            total_predictions = total_predictions + 1,
                            correct_predictions = correct_predictions + ?,
                            accuracy = CAST(correct_predictions + ? AS REAL) / (total_predictions + 1),
                            avg_confidence = (avg_confidence * total_predictions + ?) / (total_predictions + 1),
                            updated_at = ?
                    """, (
                        agent_name, period, 1 if is_correct else 0,
                        1.0 if is_correct else 0.0, confidence / 100, now,
                        1 if is_correct else 0, 1 if is_correct else 0,
                        confidence / 100, now
                    ))

                # Update market regime performance
                cursor.execute("""
                    INSERT INTO market_regime_performance
                        (regime, agent_name, accuracy, sample_count)
                    VALUES (?, ?, ?, 1)
                    ON CONFLICT(regime, agent_name) DO UPDATE SET
                        accuracy = (accuracy * sample_count + ?) / (sample_count + 1),
                        sample_count = sample_count + 1
                """, (
                    market_regime, agent_name, 1.0 if is_correct else 0.0,
                    1.0 if is_correct else 0.0
                ))

                # Update confidence bucket
                cursor.execute("""
                    INSERT INTO confidence_buckets
                        (agent_name, bucket, total_predictions, correct_predictions)
                    VALUES (?, ?, 1, ?)
                    ON CONFLICT(agent_name, bucket) DO UPDATE SET
                        total_predictions = total_predictions + 1,
                        correct_predictions = correct_predictions + ?
                """, (
                    agent_name, bucket, 1 if is_correct else 0,
                    1 if is_correct else 0
                ))

            conn.commit()

        except Exception as e:
            logger.error(f"Error updating agent performance: {e}")
            conn.rollback()
        finally:
            conn.close()

    async def get_similar_situations(
        self,
        ticker: str,
        market_regime: str,
        technical_regime: str,
        limit: int = 10,
    ) -> List[TradeMemory]:
        """Retrieve similar past situations for context."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Find completed trades with similar context
            cursor.execute("""
                SELECT * FROM trade_memories
                WHERE exit_price IS NOT NULL
                AND (ticker = ? OR market_regime = ? OR technical_regime = ?)
                ORDER BY
                    CASE WHEN ticker = ? THEN 0 ELSE 1 END,
                    CASE WHEN market_regime = ? AND technical_regime = ? THEN 0 ELSE 1 END,
                    timestamp DESC
                LIMIT ?
            """, (ticker, market_regime, technical_regime,
                  ticker, market_regime, technical_regime, limit))

            rows = cursor.fetchall()
            return [self._row_to_memory(row) for row in rows]

        finally:
            conn.close()

    async def get_agent_accuracy(
        self,
        agent_name: str,
        period: str = "month",
        market_regime: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get agent's historical accuracy."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            if market_regime:
                cursor.execute("""
                    SELECT accuracy, sample_count
                    FROM market_regime_performance
                    WHERE agent_name = ? AND regime = ?
                """, (agent_name, market_regime))
            else:
                cursor.execute("""
                    SELECT accuracy, avg_confidence, calibration_score, total_predictions
                    FROM agent_performance
                    WHERE agent_name = ? AND period = ?
                """, (agent_name, period))

            row = cursor.fetchone()

            if row:
                if market_regime:
                    return {
                        "accuracy": row["accuracy"],
                        "sample_count": row["sample_count"],
                    }
                else:
                    return {
                        "accuracy": row["accuracy"],
                        "avg_confidence": row["avg_confidence"],
                        "calibration_score": row["calibration_score"],
                        "sample_count": row["total_predictions"],
                    }

            return {"accuracy": 0.5, "sample_count": 0}

        finally:
            conn.close()

    async def get_predictions_by_confidence(
        self,
        agent_name: str,
        period: str = "month",
    ) -> Dict[int, Dict[str, int]]:
        """Get predictions grouped by confidence bucket."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT bucket, total_predictions, correct_predictions
                FROM confidence_buckets
                WHERE agent_name = ?
            """, (agent_name,))

            rows = cursor.fetchall()
            result = {}
            for row in rows:
                result[row["bucket"]] = {
                    "total": row["total_predictions"],
                    "correct": row["correct_predictions"],
                }
            return result

        finally:
            conn.close()

    def _row_to_memory(self, row: sqlite3.Row) -> TradeMemory:
        """Convert database row to TradeMemory."""
        return TradeMemory(
            id=row["id"],
            ticker=row["ticker"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            action_taken=row["action_taken"],
            entry_price=row["entry_price"],
            agent_predictions=json.loads(row["agent_predictions"]) if row["agent_predictions"] else {},
            debate_summary=row["debate_summary"],
            consensus_confidence=row["consensus_confidence"] or 50,
            market_regime=row["market_regime"] or "neutral",
            vix_level=row["vix_level"] or 20,
            sector_performance=json.loads(row["sector_performance"]) if row["sector_performance"] else {},
            news_sentiment=row["news_sentiment"] or "neutral",
            technical_regime=row["technical_regime"] or "neutral",
            exit_price=row["exit_price"],
            exit_timestamp=datetime.fromisoformat(row["exit_timestamp"]) if row["exit_timestamp"] else None,
            pnl=row["pnl"],
            pnl_percent=row["pnl_percent"],
            holding_period_hours=row["holding_period_hours"],
            winning_agents=json.loads(row["winning_agents"]) if row["winning_agents"] else None,
            losing_agents=json.loads(row["losing_agents"]) if row["losing_agents"] else None,
        )

    async def get_stats(self) -> Dict[str, Any]:
        """Get overall memory store statistics."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT COUNT(*) as count FROM trade_memories")
            total_trades = cursor.fetchone()["count"]

            cursor.execute(
                "SELECT COUNT(*) as count FROM trade_memories WHERE exit_price IS NOT NULL"
            )
            completed_trades = cursor.fetchone()["count"]

            cursor.execute(
                "SELECT COUNT(*) as count FROM trade_memories WHERE pnl > 0"
            )
            winning_trades = cursor.fetchone()["count"]

            cursor.execute(
                "SELECT AVG(pnl_percent) as avg FROM trade_memories WHERE pnl_percent IS NOT NULL"
            )
            avg_pnl = cursor.fetchone()["avg"] or 0

            return {
                "total_trades": total_trades,
                "completed_trades": completed_trades,
                "pending_trades": total_trades - completed_trades,
                "winning_trades": winning_trades,
                "win_rate": winning_trades / completed_trades if completed_trades > 0 else 0,
                "avg_pnl_percent": avg_pnl,
            }

        finally:
            conn.close()

    def record_completed_trade(
        self,
        ticker: str,
        side: str,
        entry_price: float,
        exit_price: float,
        entry_time: str,
        exit_time: str,
        quantity: float,
        pnl: float,
        pnl_pct: float,
        hold_time_minutes: float = 0,
        score_at_entry: Optional[float] = None,
        atr_at_entry: Optional[float] = None,
        rvol_at_entry: Optional[float] = None,
        regime_at_entry: Optional[str] = None,
        source: Optional[str] = None,
        exit_reason: Optional[str] = None,
    ):
        """Record a completed trade for performance tracking."""
        conn = self._get_connection()
        try:
            conn.execute("""
                INSERT INTO completed_trades (
                    ticker, side, entry_price, exit_price, entry_time, exit_time,
                    quantity, pnl, pnl_pct, hold_time_minutes,
                    score_at_entry, atr_at_entry, rvol_at_entry, regime_at_entry,
                    source, exit_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ticker, side, entry_price, exit_price, entry_time, exit_time,
                quantity, pnl, pnl_pct, hold_time_minutes,
                score_at_entry, atr_at_entry, rvol_at_entry, regime_at_entry,
                source, exit_reason,
            ))
            conn.commit()
            logger.info(f"Recorded completed trade: {ticker} {side} pnl={pnl:+.2f} ({pnl_pct:+.2f}%)")
        except Exception as e:
            logger.error(f"Error recording completed trade: {e}")
        finally:
            conn.close()

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics from completed trades."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) as n FROM completed_trades")
            total = cursor.fetchone()["n"]
            if total == 0:
                return {"total_trades": 0, "message": "No completed trades yet"}

            cursor.execute("SELECT COUNT(*) as n FROM completed_trades WHERE pnl > 0")
            wins = cursor.fetchone()["n"]

            cursor.execute("SELECT AVG(pnl_pct) as v FROM completed_trades WHERE pnl > 0")
            avg_win = cursor.fetchone()["v"] or 0

            cursor.execute("SELECT AVG(pnl_pct) as v FROM completed_trades WHERE pnl <= 0")
            avg_loss = cursor.fetchone()["v"] or 0

            cursor.execute("SELECT SUM(pnl) as v FROM completed_trades WHERE pnl > 0")
            gross_profit = cursor.fetchone()["v"] or 0

            cursor.execute("SELECT SUM(ABS(pnl)) as v FROM completed_trades WHERE pnl <= 0")
            gross_loss = cursor.fetchone()["v"] or 0

            cursor.execute("SELECT SUM(pnl) as v FROM completed_trades")
            net_pnl = cursor.fetchone()["v"] or 0

            cursor.execute("SELECT AVG(hold_time_minutes) as v FROM completed_trades")
            avg_hold = cursor.fetchone()["v"] or 0

            # Stats by score range
            score_stats = {}
            for lo, hi, label in [(80, 85, "80-84"), (85, 90, "85-89"), (90, 101, "90+")]:
                cursor.execute(
                    "SELECT COUNT(*) as n, SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as w, AVG(pnl_pct) as avg "
                    "FROM completed_trades WHERE score_at_entry >= ? AND score_at_entry < ?",
                    (lo, hi)
                )
                row = cursor.fetchone()
                if row["n"] > 0:
                    score_stats[label] = {
                        "trades": row["n"],
                        "win_rate": round(row["w"] / row["n"] * 100, 1),
                        "avg_pnl_pct": round(row["avg"], 2),
                    }

            # Stats by regime
            regime_stats = {}
            cursor.execute(
                "SELECT regime_at_entry, COUNT(*) as n, "
                "SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as w, AVG(pnl_pct) as avg "
                "FROM completed_trades WHERE regime_at_entry IS NOT NULL "
                "GROUP BY regime_at_entry"
            )
            for row in cursor.fetchall():
                regime_stats[row["regime_at_entry"]] = {
                    "trades": row["n"],
                    "win_rate": round(row["w"] / row["n"] * 100, 1),
                    "avg_pnl_pct": round(row["avg"], 2),
                }

            profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0

            return {
                "total_trades": total,
                "wins": wins,
                "losses": total - wins,
                "win_rate": round(wins / total * 100, 1),
                "avg_win_pct": round(avg_win, 2),
                "avg_loss_pct": round(avg_loss, 2),
                "profit_factor": round(profit_factor, 2),
                "net_pnl": round(net_pnl, 2),
                "gross_profit": round(gross_profit, 2),
                "gross_loss": round(gross_loss, 2),
                "avg_hold_minutes": round(avg_hold, 1),
                "by_score_range": score_stats,
                "by_regime": regime_stats,
            }
        finally:
            conn.close()
