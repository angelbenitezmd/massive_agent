from __future__ import annotations

"""Simplified FastAPI application with real Benzinga integration."""
import logging
import asyncio
import random
import json
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import os
import sqlite3

# Use simple config
from app.core.config_simple import get_settings
from app.services.benzinga_simple import BenzingaClient
from app.services.alpaca_trader import alpaca_trader
from app.services.dashboard_service import DashboardService
from app.services.position_manager import PositionManager, init_position_manager, get_position_manager
from app.services.ai_agents import NewsIntelligenceAgent
from app.services.trade_policy import assess_entry_timing, build_trade_levels, build_trade_plan, calculate_atr, calculate_relative_volume
from app.services.token_tracker import token_tracker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global Benzinga client
benzinga_client = None

# Simple TTL cache for data (reduces API calls while staying fresh)
_sentiment_cache = {}
_momentum_cache = {}
_scan_cache = {}
SENTIMENT_CACHE_TTL = 30   # Default cache; RTH uses shorter TTL below for faster reaction to headlines
SENTIMENT_CACHE_TTL_RTH_SECONDS = 14  # Regular session: refresh keyword sentiment often so age/freshness stays honest
MOMENTUM_CACHE_TTL = 15    # Cache momentum for 15 seconds (price-sensitive)
SCAN_CACHE_TTL = 20        # Cache scan results for 20 seconds
TRENDING_CACHE_TTL = 300   # Cache trending results for 5 minutes

# Excluded ETFs/indices from trending discovery (not individual stocks)
_EXCLUDED_TICKERS = {
    "SPY", "QQQ", "DIA", "IWM", "VTI", "VOO", "IVV", "RSP",
    "XLF", "XLK", "XLE", "XLV", "XLI", "XLU", "XLP", "XLY", "XLB", "XLRE", "XLC",
    "SMH", "SOXX", "GLD", "SLV", "USO", "TLT", "HYG", "AGG", "BND",
    "TQQQ", "SQQQ", "SPXL", "SPXU", "UVXY", "VXX", "VIXY",
}

# Per-ticker trade cooldown — only trade each ticker ONCE per day
_ticker_cooldowns = {}  # {ticker: datetime} - when ticker was last traded
TICKER_COOLDOWN_MINUTES = 480  # 8 hours = effectively once per trading day
_recent_trade_decisions: dict[str, dict] = {}  # ticker -> {status, reason, timestamp}

# Pre-market ready list (built at 9:15 AM ET, consumed at bell rush)
_premarket_ready_list: list = []
_premarket_built_today: str = ""  # date string, e.g. "2026-03-24"
_bell_rush_results: list = []  # Populated during bell rush, cleared next day
_bell_rush_date: str = ""  # date string for when bell rush ran
_last_market_state: str = ""

# Dynamic watchlist: tickers auto-added when they score 70+ in keyword scan
_dynamic_watchlist = {}  # {ticker: datetime_added} - auto-expires after 24h
DYNAMIC_WATCHLIST_EXPIRY_HOURS = 24

# --- Sparse-data shrinkage config (per scoring category) ---
# base_trust: conceptual reliability when this is the only source
# min/max_shrinkage: range of pull-toward-50 (0=no shrinkage, 1=full collapse to 50)
SHRINKAGE_CONFIG = {
    "news":      {"base_trust": 0.85, "min_shrinkage": 0.05, "max_shrinkage": 0.30},
    "earnings":  {"base_trust": 0.70, "min_shrinkage": 0.10, "max_shrinkage": 0.35},
    "ratings":   {"base_trust": 0.60, "min_shrinkage": 0.10, "max_shrinkage": 0.40},
    "consensus": {"base_trust": 0.45, "min_shrinkage": 0.20, "max_shrinkage": 0.45},
}
MULTI_SOURCE_SHRINKAGE = {1: 0.7, 2: 0.3, 3: 0.10, 4: 0.0}


def _add_to_dynamic_watchlist(ticker: str, score: float):
    """Add a ticker to the dynamic watchlist if it scored 70+ in keyword scan."""
    if ticker in _EXCLUDED_TICKERS:
        return
    if ticker not in _dynamic_watchlist:
        logger.info(f"[DYNAMIC-WL] Adding {ticker} (kw_score={score:.1f}) to dynamic watchlist")
    _dynamic_watchlist[ticker] = datetime.utcnow()


def _get_dynamic_tickers() -> set:
    """Return active dynamic watchlist tickers, pruning expired ones."""
    now = datetime.utcnow()
    expired = [t for t, added in _dynamic_watchlist.items()
               if (now - added).total_seconds() > DYNAMIC_WATCHLIST_EXPIRY_HOURS * 3600]
    for t in expired:
        logger.info(f"[DYNAMIC-WL] Expired {t} from dynamic watchlist")
        del _dynamic_watchlist[t]
    return set(_dynamic_watchlist.keys())

def _newest_article_age_hours(articles: list, now: datetime) -> float | None:
    """Return age in hours of the newest article, or None if no dates found."""
    from dateutil import parser as _dateutil_parser
    newest = None
    for art in articles:
        raw = art.get("published") or art.get("created")
        if not raw:
            continue
        try:
            dt = _dateutil_parser.parse(str(raw))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=None)
                cmp_now = now.replace(tzinfo=None) if now.tzinfo else now
            else:
                from zoneinfo import ZoneInfo as _ZI_art
                cmp_now = now.astimezone(_ZI_art("UTC")) if now.tzinfo else now.replace(tzinfo=_ZI_art("UTC"))
                dt = dt.astimezone(_ZI_art("UTC"))
            if newest is None or dt > newest[0]:
                newest = (dt, cmp_now)
        except (ValueError, TypeError):
            continue
    if newest is None:
        return None
    return max(0.0, (newest[1] - newest[0]).total_seconds() / 3600)


def _compute_category_quality(
    category: str,
    *,
    news_items: list | None = None,
    earnings_items: list | None = None,
    ratings_items: list | None = None,
    net_signals: float = 0,
    now: datetime | None = None,
) -> float:
    """Return quality score 0–1 for a scoring category based on available data."""
    if now is None:
        now = datetime.utcnow()

    if category == "news":
        count = len(news_items) if news_items else 0
        count_q = min(1.0, 0.3 if count <= 1 else (0.7 if count < 6 else 1.0))
        age = _newest_article_age_hours(news_items or [], now)
        if age is None:
            freshness_q = 0.2
        elif age <= 2:
            freshness_q = 1.0
        else:
            freshness_q = max(0.0, 1.0 - (age - 2) / 58)  # decays over 60h
        abs_net = abs(net_signals)
        strength_q = min(1.0, 0.2 + abs_net * 0.267) if abs_net < 3 else 1.0
        return 0.40 * count_q + 0.35 * freshness_q + 0.25 * strength_q

    if category == "earnings":
        if not earnings_items:
            return 0.3
        # Recency: days since latest earnings
        from dateutil import parser as _dateutil_parser
        days_old = 150.0
        surprise_mag = 0.0
        for e in earnings_items:
            date_str = e.get("date") or e.get("report_date")
            if date_str:
                try:
                    dt = _dateutil_parser.parse(str(date_str))
                    naive_now = now.replace(tzinfo=None) if now.tzinfo else now
                    naive_dt = dt.replace(tzinfo=None) if dt.tzinfo else dt
                    d = (naive_now - naive_dt).days
                    if d < days_old:
                        days_old = d
                except (ValueError, TypeError):
                    pass
            # Surprise magnitude
            try:
                est = float(e.get("estimated_eps", 0))
                act = float(e.get("actual_eps", 0))
                if est != 0:
                    mag = abs((act - est) / abs(est)) * 100
                    surprise_mag = max(surprise_mag, mag)
            except (ValueError, TypeError):
                pass
        recency_q = max(0.3, 1.0 - days_old / 150)
        surprise_q = min(1.0, surprise_mag / 20) if surprise_mag > 0 else 0.3
        return 0.50 * recency_q + 0.50 * surprise_q

    if category == "ratings":
        if not ratings_items:
            return 0.2
        count = len(ratings_items)
        count_q = min(1.0, 0.4 + count * 0.15) if count < 5 else 1.0
        from dateutil import parser as _dateutil_parser
        days_old = 90.0
        for r in ratings_items:
            date_str = r.get("date") or r.get("action_date")
            if date_str:
                try:
                    dt = _dateutil_parser.parse(str(date_str))
                    naive_now = now.replace(tzinfo=None) if now.tzinfo else now
                    naive_dt = dt.replace(tzinfo=None) if dt.tzinfo else dt
                    d = (naive_now - naive_dt).days
                    if d < days_old:
                        days_old = d
                except (ValueError, TypeError):
                    pass
        recency_q = max(0.2, 1.0 - days_old / 90)
        return 0.50 * count_q + 0.50 * recency_q

    # consensus: fixed 0.5
    return 0.5


# === SCORING SNAPSHOT RECORDER (for backtesting) ===
_scoring_db_path = str(Path(__file__).parent.parent / "data" / "trading_memory.db")


def _init_scoring_snapshots_table():
    """Create scoring_snapshots table if it doesn't exist. Called at startup."""
    try:
        conn = sqlite3.connect(_scoring_db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scoring_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                mode TEXT NOT NULL,
                news_items TEXT,
                earnings_items TEXT,
                ratings_items TEXT,
                consensus TEXT,
                score REAL,
                shrinkage TEXT,
                components TEXT
            )
        """)
        cursor.execute("DELETE FROM scoring_snapshots WHERE timestamp < datetime('now', '-30 days')")
        conn.commit()
        conn.close()
        logger.info("✅ scoring_snapshots table ready")
    except Exception as e:
        logger.warning(f"Failed to init scoring_snapshots table: {e}")


def _record_scoring_snapshot_sync(
    ticker: str, mode: str, news_items: list, earnings_items: list,
    ratings_items: list, consensus_data, score: float,
    shrinkage_info: dict, components_data: dict,
):
    """Write a scoring snapshot row (runs in thread via asyncio.to_thread)."""
    try:
        conn = sqlite3.connect(_scoring_db_path)
        conn.execute(
            """INSERT INTO scoring_snapshots
               (ticker, timestamp, mode, news_items, earnings_items, ratings_items, consensus, score, shrinkage, components)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ticker,
                datetime.utcnow().isoformat(),
                mode,
                json.dumps(news_items[:10]) if news_items else None,
                json.dumps(earnings_items[:5]) if earnings_items else None,
                json.dumps(ratings_items[:5]) if ratings_items else None,
                json.dumps(consensus_data) if isinstance(consensus_data, dict) else None,
                score,
                json.dumps(shrinkage_info),
                json.dumps(components_data),
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug(f"Scoring snapshot write failed for {ticker}: {e}")


# === TRADE GATE LOGGING ===
def _log_trade_gate(ticker: str, score: float, allowed: bool, reason: str, source: str = "auto"):
    """Log trade gate decision for transparency."""
    status = "ALLOWED" if allowed else "BLOCKED"
    from zoneinfo import ZoneInfo
    et_now = datetime.now(ZoneInfo("America/New_York")).strftime("%H:%M:%S ET")
    logger.info(f"[TRADE-GATE] {status} {ticker} from={source} score={score:.1f} | {reason} | {et_now}")
    # Also log blocked high-score tickers to activity log for frontend visibility
    if not allowed and score >= 70:
        log_activity(
            log_type="TRADE_BLOCKED",
            ticker=ticker,
            action="BLOCKED",
            details={
                "score": score,
                "reason": reason,
                "source": source,
            },
        )


# Risk management: Daily loss limit and market trend filter
DAILY_LOSS_LIMIT_PCT = -0.01  # Stop trading if day P&L drops below -1% of equity
SPY_TREND_THRESHOLD = -0.005  # Skip buys if SPY is down more than -0.5% on the day
_daily_loss_limit_hit = False  # Flag to stop trading for the day

# Position sizing defaults
DEFAULT_RISK_PER_TRADE = 0.0035  # 0.35% of portfolio at risk per trade
# Dynamic max position based on signal score — keep concentration low while edge is still proving itself.
MAX_POSITION_PCT_BASE = 0.05       # 5% max for standard signals (score 70-79)
MAX_POSITION_PCT_GOOD = 0.06       # 6% max for good signals (score 80-84)
MAX_POSITION_PCT_STRONG = 0.08     # 8% max for strong signals (score 85-89)
MAX_POSITION_PCT_EXCELLENT = 0.10  # 10% max for excellent signals (score 90+)
MIN_SHARES = 1
MAX_SHARES = 500  # Safety cap
MIN_POSITION_VALUE = 150  # Small starter positions are preferable to oversized losers
TARGET_POSITION_PCT_HIGH_CONF = 0.05  # Target 5% for high confidence (>0.8)
TARGET_POSITION_PCT_MED_CONF = 0.035  # Target 3.5% for medium confidence (0.6-0.8)
TARGET_POSITION_PCT_LOW_CONF = 0.02   # Target 2% for low confidence (<0.6)

# Live auto-trade gate: aligned with recalibrated LLM scoring (full 0-100 range).
AUTO_TRADE_MIN_COMBINED_SCORE = 70.0
AUTO_TRADE_MIN_COMBINED_SCORE_EARLY = 64.0  # true early window should not need full follow-through yet
AUTO_TRADE_MIN_AI_SCORE = 62.0
AUTO_TRADE_MIN_MOMENTUM_SCORE = 52.0
AUTO_TRADE_MAX_ABS_MOVE_PCT = 5.0
AUTO_TRADE_MIN_PRICE = 25.0  # No penny stocks
AUTO_TRADE_MAX_FINANCIAL_POSITIONS = 1
AUTO_TRADE_MAX_OPEN_POSITIONS = 4
AUTO_TRADE_MAX_NEW_TRADES_PER_DAY = 3
AUTO_TRADE_TRENDING_MIN_COMBINED_SCORE = 75.0
AUTO_TRADE_MAX_CONSECUTIVE_LOSSES = 3
_FINANCIAL_TICKERS = {
    "JPM", "BAC", "WFC", "C", "GS", "MS", "SCHW", "PNC", "USB", "BK", "BLK",
}


def _auto_trade_sector_bucket(ticker: str) -> Optional[str]:
    """Group tickers into coarse sector buckets for concentration control."""
    if ticker in _FINANCIAL_TICKERS:
        return "financials"
    return None


def _count_today_auto_trade_buys() -> int:
    """Count how many BUY auto-trades have already executed today."""
    today = datetime.utcnow().date().isoformat()
    return sum(
        1
        for entry in _activity_log
        if entry.get("type") == "AUTO_TRADE"
        and entry.get("action") == "BUY"
        and str(entry.get("timestamp", "")).startswith(today)
    )


def _get_trade_feedback(signal: dict) -> dict:
    """Penalize repeat bad setups using recent outcomes and postmortems."""
    ticker = str(signal.get("ticker", "")).upper()
    source = str(signal.get("source") or "watchlist")
    regime = signal.get("regime_at_entry")
    feedback = {
        "score_penalty": 0.0,
        "size_multiplier": 1.0,
        "veto": False,
        "reasons": [],
    }

    if not ticker:
        return feedback

    try:
        from app.services.memory.memory_store import MemoryStore

        store = MemoryStore()
        try:
            postmortems = store.get_similar_loss_postmortems(
                ticker=ticker,
                regime_at_entry=regime,
                source=source,
                limit=5,
            )
        except Exception as exc:
            logger.debug(f"Loss postmortem lookup unavailable for {ticker}: {exc}")
            postmortems = []

        try:
            recent_trades = store.get_recent_completed_trades(
                ticker=ticker,
                regime_at_entry=regime,
                source=source,
                limit=6,
            )
        except Exception as exc:
            logger.debug(f"Completed trade lookup unavailable for {ticker}: {exc}")
            recent_trades = []
    except Exception as exc:
        logger.debug(f"Trade feedback unavailable for {ticker}: {exc}")
        return feedback

    if postmortems:
        feedback["score_penalty"] = max(
            float(getattr(item, "score_penalty", 0) or 0)
            for item in postmortems[:3]
        )
        feedback["size_multiplier"] = min(
            float(getattr(item, "size_multiplier", 1.0) or 1.0)
            for item in postmortems[:3]
        )
        if any(bool(getattr(item, "veto_future_similar", False)) for item in postmortems[:2]):
            feedback["veto"] = True
            feedback["reasons"].append("loss_review_veto")
        feedback["reasons"].append(f"recent_loss_reviews={min(len(postmortems), 3)}")

    if recent_trades:
        pnl_values = [float(item.get("pnl_pct", 0) or 0) for item in recent_trades]
        avg_pnl = sum(pnl_values) / len(pnl_values)
        win_rate = sum(1 for pnl in pnl_values if pnl > 0) / len(pnl_values)
        consecutive_losses = 0

        for pnl in pnl_values:
            if pnl <= 0:
                consecutive_losses += 1
            else:
                break

        if len(pnl_values) >= 3 and win_rate < 0.4:
            feedback["score_penalty"] = max(feedback["score_penalty"], 6.0)
            feedback["size_multiplier"] = min(feedback["size_multiplier"], 0.6)
            feedback["reasons"].append("weak_recent_win_rate")

        if len(pnl_values) >= 3 and avg_pnl < -0.5:
            feedback["score_penalty"] = max(feedback["score_penalty"], 8.0)
            feedback["size_multiplier"] = min(feedback["size_multiplier"], 0.5)
            feedback["reasons"].append("negative_recent_expectancy")

        if consecutive_losses >= AUTO_TRADE_MAX_CONSECUTIVE_LOSSES:
            feedback["veto"] = True
            feedback["reasons"].append("recent_consecutive_losses")

    feedback["score_penalty"] = round(float(feedback["score_penalty"]), 1)
    feedback["size_multiplier"] = round(
        max(0.25, min(1.0, float(feedback["size_multiplier"] or 1.0))),
        2,
    )
    feedback["reasons"] = feedback["reasons"][:4]
    return feedback


def _apply_trade_feedback_to_signal(signal: dict) -> None:
    """Recalculate quantity after historical penalties are applied."""
    feedback = signal.get("trade_feedback") or {}
    base_multiplier = float(signal.get("position_size_multiplier", 1.0) or 1.0)
    feedback_multiplier = float(feedback.get("size_multiplier", 1.0) or 1.0)
    size_multiplier = max(0.25, min(1.0, base_multiplier * feedback_multiplier))
    combined_score = float(signal.get("combined_score", 0) or 0)
    effective_score = float(signal.get("effective_score", combined_score) or combined_score)
    entry_price = float(signal.get("entry_price") or signal.get("price", 0) or 0)
    stop_loss = float(signal.get("stop_loss", 0) or 0)

    if entry_price <= 0:
        signal["position_size_multiplier"] = round(size_multiplier, 2)
        return

    stop_loss_price = stop_loss if stop_loss > 0 else round(entry_price * 0.985, 2)
    signal["quantity"] = calculate_position_size(
        price=entry_price,
        stop_loss_price=stop_loss_price,
        confidence=min(max(effective_score / 100.0, 0.35), 0.9),
        signal_score=round(effective_score),
        performance_multiplier=size_multiplier,
    )
    signal["position_size_multiplier"] = round(size_multiplier, 2)
    signal["effective_score"] = round(effective_score, 1)


def _auto_trade_signal_rank(signal: dict) -> tuple:
    """Sort key (higher is better): prefer early timing, fresher news, lower late risk, then score."""
    age = signal.get("newest_article_age_hours")
    try:
        age_f = float(age) if age is not None else 24.0
    except (TypeError, ValueError):
        age_f = 24.0
    early = signal.get("entry_timing_state") == "early"
    ultra_fresh = age_f <= 0.33  # ~20 min
    timing_score = float(signal.get("entry_timing_score") or 0)
    late_risk = float(signal.get("late_entry_risk") or 50)
    combined = float(signal.get("combined_score") or 0)
    return (1 if early else 0, 1 if ultra_fresh else 0, timing_score, -late_risk, combined)


def _passes_live_auto_trade_gate(signal: dict, owned_symbols: set[str]) -> tuple[bool, str]:
    """Require stronger agreement before live auto-trading."""
    ticker = str(signal.get("ticker", "")).upper()
    source = str(signal.get("source") or "watchlist")
    action = str(signal.get("action", "WAIT"))
    combined_score = float(signal.get("combined_score", 0) or 0)
    ai_score = float(signal.get("ai_score", 0) or 0)
    momentum_score = float(signal.get("momentum_score", 0) or 0)
    price_change_pct = abs(float(signal.get("price_change_pct", 0) or 0))

    entry_price = float(signal.get("entry_price", 0) or signal.get("price", 0) or 0)

    if action != "BUY":
        return False, f"action={action}"
    if entry_price > 0 and entry_price < AUTO_TRADE_MIN_PRICE:
        return False, f"price=${entry_price:.2f}<min=${AUTO_TRADE_MIN_PRICE:.0f}"
    if not signal.get("llm_enhanced", False):
        return False, "llm_confirmation_required"
    if len(owned_symbols) >= AUTO_TRADE_MAX_OPEN_POSITIONS:
        return False, f"max_open_positions={AUTO_TRADE_MAX_OPEN_POSITIONS}"
    if _count_today_auto_trade_buys() >= AUTO_TRADE_MAX_NEW_TRADES_PER_DAY:
        return False, f"daily_trade_cap={AUTO_TRADE_MAX_NEW_TRADES_PER_DAY}"
    if ai_score < AUTO_TRADE_MIN_AI_SCORE:
        return False, f"ai_score={ai_score:.1f}<min={AUTO_TRADE_MIN_AI_SCORE:.1f}"
    price_raw = float(signal.get("price_change_pct", 0) or 0)
    early_tape = -1.2 <= price_raw <= 1.5 and ai_score >= AUTO_TRADE_MIN_AI_SCORE
    early_entry = bool(
        signal.get("entry_timing_state") == "early"
        and signal.get("fresh_catalyst")
        and early_tape
    )
    mom_floor = 44.0 if early_entry else (46.0 if early_tape else float(AUTO_TRADE_MIN_MOMENTUM_SCORE))
    if momentum_score < mom_floor:
        return False, f"momentum_score={momentum_score:.1f}<min={mom_floor:.1f}"
    buy_gate = signal.get("buy_gate") or {}
    if buy_gate and not buy_gate.get("passed", False):
        gate_reasons = ",".join((buy_gate.get("reasons") or [])[:3]) or "buy_gate_failed"
        return False, gate_reasons
    if signal.get("momentum_warning"):
        return False, "momentum_warning"
    if signal.get("technical_veto"):
        return False, signal.get("technical_veto_reason") or "technical_veto"
    if price_change_pct > AUTO_TRADE_MAX_ABS_MOVE_PCT:
        return False, f"price_move={price_change_pct:.1f}%>max={AUTO_TRADE_MAX_ABS_MOVE_PCT:.1f}%"
    risk_reward_ratio = float(signal.get("risk_reward_ratio", 0) or 0)
    if risk_reward_ratio and risk_reward_ratio < 1.5:
        return False, f"risk_reward={risk_reward_ratio:.2f}<min=1.5"

    feedback = _get_trade_feedback(signal)
    signal["trade_feedback"] = feedback
    effective_score = combined_score - float(feedback.get("score_penalty", 0) or 0)
    signal["effective_score"] = round(effective_score, 1)

    if feedback.get("veto"):
        return False, ",".join(feedback.get("reasons", [])[:2]) or "loss_memory_veto"
    min_eff = float(AUTO_TRADE_MIN_COMBINED_SCORE)
    if early_entry:
        min_eff = min(min_eff, float(AUTO_TRADE_MIN_COMBINED_SCORE_EARLY))
    if effective_score < min_eff:
        return False, f"effective_score={effective_score:.1f}<min={min_eff:.1f}"
    if source == "trending" and effective_score < AUTO_TRADE_TRENDING_MIN_COMBINED_SCORE:
        return False, f"trending_score={effective_score:.1f}<min={AUTO_TRADE_TRENDING_MIN_COMBINED_SCORE:.1f}"

    bucket = _auto_trade_sector_bucket(ticker)
    if bucket == "financials":
        owned_in_bucket = sum(1 for symbol in owned_symbols if _auto_trade_sector_bucket(symbol) == bucket)
        if owned_in_bucket >= AUTO_TRADE_MAX_FINANCIAL_POSITIONS:
            return False, "financial_sector_limit"

    _apply_trade_feedback_to_signal(signal)
    return True, "passed"


def check_trade_allowed(
    ticker: str,
    score: float,
    llm_enhanced: bool,
    source: str = "watchlist",
    owned_symbols: Optional[set[str]] = None,
    signal: Optional[dict] = None,
) -> dict:
    """Compatibility helper used by tests and manual trade checks."""
    candidate = dict(signal or {})
    candidate.setdefault("ticker", ticker.upper())
    candidate.setdefault("action", "BUY")
    candidate.setdefault("combined_score", float(score))
    candidate.setdefault("ai_score", float(score))
    candidate.setdefault("momentum_score", max(60.0, float(score) - 10.0))
    candidate.setdefault("price_change_pct", 0.5)
    candidate.setdefault("llm_enhanced", llm_enhanced)
    candidate.setdefault("source", source)
    candidate.setdefault("entry_price", 100.0)
    candidate.setdefault("stop_loss", 98.0)
    allowed, reason = _passes_live_auto_trade_gate(candidate, owned_symbols or set())
    return {"allowed": allowed, "reason": reason, "signal": candidate}


def _entry_risk_levels(
    price: float,
    quote: dict,
    technical_ctx: Optional[dict] = None,
    bars: Optional[list] = None,
) -> tuple[float, float]:
    """Build risk levels from volatility plus nearby structure instead of fixed tiny stops."""
    support = None
    resistance = None
    technical_score = None

    if technical_ctx:
        support = technical_ctx.get("support")
        resistance = technical_ctx.get("resistance")
        technical_score = technical_ctx.get("technical_score")

    high = float(quote.get("high") or 0)
    low = float(quote.get("low") or 0)
    if support is None and 0 < low < price:
        support = low
    if resistance is None and high > price:
        resistance = high

    levels = build_trade_levels(
        price=price,
        bars=bars or [],
        support=support,
        resistance=resistance,
        technical_score=technical_score,
        relative_volume=(technical_ctx or {}).get("relative_volume"),
    )
    return levels["stop_loss"], levels["take_profit"]


def _technical_context_from_bars(ticker: str, price: float, bars: list) -> dict:
    """Local TA overlay with volatility, volume, and structure metrics."""
    from app.services.technical_indicators import analyze_technical, TechnicalRegime

    if not bars or len(bars) < 15 or price <= 0:
        return {
            "technical_veto": False,
            "technical_veto_reason": None,
            "technical_score": None,
            "technical_regime": None,
            "technical_rsi": None,
            "technical_bias_points": 0.0,
            "support": None,
            "resistance": None,
            "atr": 0.0,
            "relative_volume": None,
            "resistance_room_pct": None,
            "support_room_pct": None,
            "ma_alignment": None,
            "macd_crossover": None,
            "momentum_state": None,
        }
    try:
        tech = analyze_technical(ticker, price, bars)
    except Exception as e:
        logger.debug(f"analyze_technical failed for {ticker}: {e}")
        return {
            "technical_veto": False,
            "technical_veto_reason": None,
            "technical_score": None,
            "technical_regime": None,
            "technical_rsi": None,
            "technical_bias_points": 0.0,
            "support": None,
            "resistance": None,
            "atr": 0.0,
            "relative_volume": None,
            "resistance_room_pct": None,
            "support_room_pct": None,
            "ma_alignment": None,
            "macd_crossover": None,
            "momentum_state": None,
        }

    atr = calculate_atr(bars)
    relative_volume = calculate_relative_volume(bars)
    support_room_pct = ((price - tech.support) / price * 100) if tech.support and tech.support < price else None
    resistance_room_pct = ((tech.resistance - price) / price * 100) if tech.resistance and tech.resistance > price else None

    veto = False
    veto_reason = None
    if tech.regime in (TechnicalRegime.STRONG_BEARISH, TechnicalRegime.BEARISH):
        veto = True
        veto_reason = f"bearish_tape_{tech.regime.value}"
    elif tech.rsi is not None and tech.rsi >= 78 and (resistance_room_pct or 0) < 3.0:
        veto = True
        veto_reason = f"rsi_extreme_overbought_{tech.rsi:.0f}"

    bias = 0.0
    if not veto:
        if tech.regime in (TechnicalRegime.STRONG_BULLISH, TechnicalRegime.BULLISH):
            bias = min(5.0, max(0.0, (tech.score - 58) * 0.12))
        elif tech.regime == TechnicalRegime.NEUTRAL and tech.score < 44:
            bias = -5.0

    return {
        "technical_veto": veto,
        "technical_veto_reason": veto_reason,
        "technical_score": tech.score,
        "technical_regime": tech.regime.value,
        "technical_rsi": tech.rsi,
        "technical_bias_points": round(bias, 1),
        "support": tech.support,
        "resistance": tech.resistance,
        "atr": round(atr, 4) if atr else 0.0,
        "relative_volume": relative_volume,
        "resistance_room_pct": round(resistance_room_pct, 2) if resistance_room_pct is not None else None,
        "support_room_pct": round(support_room_pct, 2) if support_room_pct is not None else None,
        "ma_alignment": tech.ma_alignment,
        "macd_crossover": tech.macd_crossover,
        "momentum_state": tech.momentum,
    }


def calculate_position_size(
    price: float,
    stop_loss_price: float,
    confidence: float = 0.7,
    risk_pct: float = DEFAULT_RISK_PER_TRADE,
    signal_score: int = 70,
    performance_multiplier: float = 1.0,
) -> int:
    """
    Calculate position size using a conservative hybrid approach:
    1. Risk-based sizing (how much we can lose)
    2. Target position sizing (based on confidence/signal strength)
    3. Take the smaller of the two so weak setups cannot size up aggressively

    Formula considers:
        - Account equity and buying power
        - Stop loss distance (risk per share)
        - Signal confidence (scales position aggressively)
        - Signal score (bonus for high-conviction trades)
        - Minimum position value (avoid tiny meaningless trades)

    Args:
        price: Entry price per share
        stop_loss_price: Stop loss price
        confidence: Signal confidence (0-1), scales position size
        risk_pct: Percentage of portfolio to risk per trade
        signal_score: Combined signal score (0-100)
        performance_multiplier: Historical penalty multiplier from loss reviews

    Returns:
        Number of shares to buy (integer)
    """
    try:
        # Get account info
        account = alpaca_trader.get_account_status()
        if not account:
            logger.warning("Could not get account status, using default 15 shares")
            return 15

        equity = float(account.get("equity", 100000))
        # Use daytrading_buying_power if available (prevents "insufficient day trading buying power" errors)
        buying_power = float(account.get("daytrading_buying_power", 0)) or float(account.get("buying_power", equity))

        if price <= 0:
            return MIN_SHARES

        # === METHOD 1: Risk-based sizing ===
        risk_per_share = abs(price - stop_loss_price)
        if risk_per_share < 0.01:
            risk_per_share = price * 0.02  # Default 2% stop

        # Confidence scaling — capped so sizing does not explode on borderline scores
        if confidence >= 0.85:
            confidence_multiplier = 0.90 + (confidence - 0.85) * 0.35
        elif confidence >= 0.6:
            confidence_multiplier = 0.60 + (confidence - 0.6) * 0.8
        else:
            confidence_multiplier = 0.40 + confidence * 0.30

        # Keep score bonuses modest; good scores earn slightly more size, not massively more.
        if signal_score >= 90:
            score_bonus = 1.15 + (signal_score - 90) * 0.01
        elif signal_score >= 85:
            score_bonus = 1.08 + (signal_score - 85) * 0.014
        elif signal_score >= 80:
            score_bonus = 1.03 + (signal_score - 80) * 0.01
        else:
            score_bonus = 1.0 + max(0, (signal_score - 70) * 0.004)

        feedback_multiplier = max(0.25, min(1.0, performance_multiplier))
        risk_amount = equity * risk_pct * confidence_multiplier * score_bonus * feedback_multiplier
        shares_from_risk = int(risk_amount / risk_per_share)

        # === METHOD 2: Target position sizing ===
        # Determine target position % based on confidence
        if confidence >= 0.8:
            target_pct = TARGET_POSITION_PCT_HIGH_CONF
        elif confidence >= 0.6:
            target_pct = TARGET_POSITION_PCT_MED_CONF
        else:
            target_pct = TARGET_POSITION_PCT_LOW_CONF

        # Apply score bonus to target
        target_position_value = equity * target_pct * score_bonus * feedback_multiplier
        shares_from_target = int(target_position_value / price)

        # === METHOD 3: Minimum position value ===
        # A small floor keeps position tracking/logging useful without forcing huge trades.
        min_shares_for_value = int(MIN_POSITION_VALUE / price)

        # === COMBINE: Take the SMALLER of risk-based and target-based ===
        # If either method wants smaller size, obey the smaller number.
        positive_candidates = [v for v in (shares_from_risk, shares_from_target) if v > 0]
        shares_base = min(positive_candidates) if positive_candidates else 0
        if shares_base < min_shares_for_value and min_shares_for_value > 0:
            shares_base = min_shares_for_value

        # === Apply constraints ===
        # Dynamic max position size based on signal score (higher score = more conviction)
        if signal_score >= 90:
            max_position_pct = MAX_POSITION_PCT_EXCELLENT  # 35% for exceptional signals
        elif signal_score >= 85:
            max_position_pct = MAX_POSITION_PCT_STRONG     # 25% for strong signals
        elif signal_score >= 80:
            max_position_pct = MAX_POSITION_PCT_GOOD       # 22% for good signals
        else:
            max_position_pct = MAX_POSITION_PCT_BASE       # 12% for standard signals

        max_position_value = equity * max_position_pct
        shares_from_max_position = int(max_position_value / price)

        # Buying power constraint — never let one trade dominate deployable capital.
        shares_from_buying_power = int(buying_power * 0.25 / price)

        # Final calculation: minimum of (base, constraints), but at least MIN_SHARES
        shares = min(shares_base, shares_from_max_position, shares_from_buying_power, MAX_SHARES)
        shares = max(shares, MIN_SHARES)

        # Calculate final position value for logging
        position_value = shares * price
        position_pct = (position_value / equity) * 100

        logger.info(
            f"Position sizing: equity=${equity:,.0f}, price=${price:.2f}, "
            f"conf={confidence:.2f}, score={signal_score}, max_pct={max_position_pct*100:.0f}%, "
            f"risk_shares={shares_from_risk}, target_shares={shares_from_target}, "
            f"min_value_shares={min_shares_for_value} -> {shares} shares "
            f"(${position_value:,.0f}, {position_pct:.1f}% of portfolio)"
        )

        return shares

    except Exception as e:
        logger.error(f"Position sizing error: {e}, defaulting to 15 shares")
        return 15

async def _free_capital_for_excellent_signal(ticker: str, price: float, equity: float) -> bool:
    """Check whether we already have enough buying power for a high-score trade.

    We intentionally do not liquidate other names anymore. Rotating out of the
    existing book to chase a fresh signal increased churn and often locked in
    avoidable losses.
    """
    if not alpaca_trader or not alpaca_trader.client:
        return False

    target_value = equity * MAX_POSITION_PCT_EXCELLENT
    account = alpaca_trader.get_account_status()
    if not account:
        return False

    buying_power = float(account.get("daytrading_buying_power", 0)) or float(account.get("buying_power", 0))
    needed_shares = int(target_value / price) if price > 0 else 0
    needed_value = needed_shares * price

    if buying_power >= needed_value:
        logger.info(f"[EXCELLENT] Already have enough buying power (${buying_power:,.0f} >= ${needed_value:,.0f})")
        return True

    shortfall = needed_value - buying_power
    logger.info(
        f"[EXCELLENT] Need ${needed_value:,.0f} for {ticker}, have ${buying_power:,.0f}, "
        f"shortfall=${shortfall:,.0f}; not rotating out of open positions to fund it"
    )
    return False


# Auto-trade state (persisted to file for restarts)
AUTO_TRADE_STATE_FILE = Path(__file__).parent.parent / "data" / "auto_trade_state.json"
_auto_trade_enabled = False
_auto_trade_interval = 60  # seconds between trade scans

def load_auto_trade_state():
    """Load auto-trade state from disk."""
    global _auto_trade_enabled, _auto_trade_interval
    try:
        if AUTO_TRADE_STATE_FILE.exists():
            with open(AUTO_TRADE_STATE_FILE, "r") as f:
                state = json.load(f)
                _auto_trade_enabled = state.get("enabled", False)
                _auto_trade_interval = state.get("interval", 60)
                logger.info(f"Loaded auto-trade state: enabled={_auto_trade_enabled}, interval={_auto_trade_interval}s")
    except Exception as e:
        logger.error(f"Failed to load auto-trade state: {e}")

def save_auto_trade_state():
    """Save auto-trade state to disk."""
    try:
        AUTO_TRADE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(AUTO_TRADE_STATE_FILE, "w") as f:
            json.dump({
                "enabled": _auto_trade_enabled,
                "interval": _auto_trade_interval,
                "updated_at": datetime.utcnow().isoformat()
            }, f)
    except Exception as e:
        logger.error(f"Failed to save auto-trade state: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown."""
    # Startup
    global benzinga_client
    settings = get_settings()

    logger.info("="*60)
    logger.info("AI Trading System Starting (With Benzinga Integration)")
    logger.info(f"Trading Environment: {settings.ALPACA_ENV.upper()}")

    if settings.ALPACA_ENV == "live":
        logger.warning("⚠️ LIVE TRADING MODE - REAL MONEY AT RISK ⚠️")
    else:
        logger.info("✅ Paper trading mode (safe)")

    # Initialize scoring snapshots table for backtesting
    _init_scoring_snapshots_table()

    # Initialize Benzinga client
    if settings.BENZINGA_API_KEY:
        benzinga_client = BenzingaClient(
            base_url=settings.BENZINGA_BASE_URL,
            api_key=settings.BENZINGA_API_KEY
        )
        logger.info("✅ Benzinga client initialized")
    else:
        logger.warning("⚠️ Benzinga API key not configured")

    # Initialize and start smart position manager (LLM-powered exits)
    pm = init_position_manager(check_interval=30, min_analysis_interval=120)
    asyncio.create_task(pm.start())
    logger.info("✅ Smart Position Manager started (LLM-powered exits)")
    logger.info("✅ Legacy simple auto-exit loop disabled in favor of Position Manager")

    # Load auto-trade state and start background loops
    load_auto_trade_state()
    asyncio.create_task(auto_trade_loop())
    logger.info(f"✅ Auto-trade loop started (enabled={_auto_trade_enabled})")

    asyncio.create_task(news_push_loop())
    logger.info("✅ News-push watcher started (15s poll, immediate trade on breaking news)")

    logger.info("="*60)

    yield

    # Shutdown
    logger.info("Shutting down AI Trading System")


# Create FastAPI app
app = FastAPI(
    title="AI Trading Intelligence System",
    description="Real-time market data from Benzinga + AI signals + Alpaca trading",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "AI Trading System API",
        "version": "1.0.0",
        "benzinga_connected": benzinga_client is not None,
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "environment": settings.ALPACA_ENV,
        "paper_trading": settings.is_paper_trading,
        "benzinga_connected": benzinga_client is not None
    }


@app.get("/status")
async def system_status():
    """Get system status and configuration."""
    return {
        "trading_env": settings.ALPACA_ENV,
        "is_paper": settings.is_paper_trading,
        "risk_settings": {
            "max_position_risk": settings.TRADING_DEFAULT_MAX_POSITION_RISK,
            "daily_max_drawdown": settings.TRADING_DAILY_MAX_DRAWDOWN,
            "min_signal_score": settings.TRADING_MIN_SIGNAL_SCORE
        },
        "watchlist": settings.watchlist,
        "hybrid_interval": settings.TRADING_HYBRID_INTERVAL_SECONDS,
        "api_keys_configured": {
            "benzinga": bool(settings.BENZINGA_API_KEY),
            "alpaca": bool(settings.ALPACA_API_KEY_ID and settings.ALPACA_API_SECRET_KEY),
            "anthropic": bool(settings.ANTHROPIC_API_KEY)
        }
    }


# ============= BENZINGA API ENDPOINTS =============

@app.get("/api/news")
async def get_news(
    ticker: Optional[str] = Query(None, description="Stock ticker(s), comma-separated"),
    channels: Optional[str] = Query(None, description="News channels to filter"),
    days_back: int = Query(1, description="Number of days to look back"),
    hours_back: int = Query(None, description="Hours to look back (overrides days_back)"),
    limit: int = Query(10, description="Maximum results")
):
    """Get real-time news from Benzinga."""
    if not benzinga_client:
        raise HTTPException(status_code=503, detail="Benzinga client not configured")

    # For global news (no ticker), fetch unfiltered recent news.
    # Multi-ticker comma-separated queries return empty on the Benzinga/Massive API,
    # so we omit tickers entirely for the live feed.
    request_tickers = ticker
    if not ticker:
        hours_back = hours_back or 1  # Default 1 hour for global
        limit = min(limit, 15)  # Cap at 15 for global news

    # Calculate date range — Benzinga only accepts date-only format (YYYY-MM-DD)
    if hours_back:
        published_gte = (datetime.utcnow() - timedelta(hours=hours_back)).strftime("%Y-%m-%d")
    else:
        published_gte = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    try:
        result = await benzinga_client.get_news(
            tickers=request_tickers,
            channels=channels,
            published_gte=published_gte,
            limit=limit
        )
        return result
    except Exception as e:
        logger.error(f"Error fetching news: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/earnings")
async def get_earnings(
    ticker: Optional[str] = Query(None, description="Stock ticker"),
    days_back: int = Query(90, description="Days to look back for past earnings"),
    days_ahead: int = Query(30, description="Days to look ahead for upcoming earnings"),
    importance_min: int = Query(0, description="Minimum importance (0-5)"),
    limit: int = Query(20, description="Maximum results")
):
    """Get earnings calendar from Benzinga (both past and upcoming)."""
    if not benzinga_client:
        raise HTTPException(status_code=503, detail="Benzinga client not configured")

    # Date range - look back for recent earnings AND ahead for upcoming
    date_gte = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    date_lte = (datetime.utcnow() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    try:
        result = await benzinga_client.get_earnings(
            ticker=ticker,
            date_gte=date_gte,
            date_lte=date_lte,
            importance_gte=importance_min,
            limit=limit
        )
        return result
    except Exception as e:
        logger.error(f"Error fetching earnings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ratings")
async def get_ratings(
    ticker: Optional[str] = Query(None, description="Stock ticker"),
    days_back: int = Query(7, description="Days to look back"),
    action: Optional[str] = Query(None, description="Rating action (upgrades, downgrades, etc.)"),
    limit: int = Query(20, description="Maximum results")
):
    """Get analyst ratings from Benzinga."""
    if not benzinga_client:
        raise HTTPException(status_code=503, detail="Benzinga client not configured")

    date_gte = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    result = await benzinga_client.get_ratings(
        ticker=ticker,
        date_gte=date_gte,
        rating_action=action,
        limit=limit
    )

    if "error" in result:
        # Return empty results instead of error for subscription issues
        if "403" in result.get("error", "") or "NOT_AUTHORIZED" in result.get("message", ""):
            return {
                "results": [],
                "message": "Ratings data requires a Benzinga Ratings subscription"
            }
        raise HTTPException(status_code=500, detail=result.get("message", "API error"))

    return result


@app.get("/api/consensus/{ticker}")
async def get_consensus(ticker: str):
    """Get consensus ratings for a specific ticker."""
    if not benzinga_client:
        raise HTTPException(status_code=503, detail="Benzinga client not configured")

    # Convert ticker to uppercase for consistency
    ticker = ticker.upper()
    result = await benzinga_client.get_consensus(ticker)

    if "error" in result:
        # Return empty results instead of error for subscription issues
        if "403" in result.get("error", "") or "NOT_AUTHORIZED" in result.get("message", ""):
            return {
                "results": [],
                "message": "Consensus data requires a Benzinga Consensus subscription"
            }
        raise HTTPException(status_code=500, detail=result.get("message", "API error"))

    return result


@app.get("/api/token-usage")
async def get_token_usage():
    """Return today's LLM token usage summary."""
    try:
        return token_tracker.get_today_summary()
    except Exception as e:
        logger.error(f"Error fetching token usage: {e}")
        return {
            "date": datetime.utcnow().date().isoformat(),
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cost_estimate": 0.0,
            "call_count": 0,
            "by_model": {},
            "by_agent": {},
            "by_hour": [],
        }


@app.get("/api/dashboard/{ticker}")
async def get_dashboard(ticker: str):
    """Aggregate market, agent, and risk data for a ticker."""
    service = DashboardService()
    try:
        return await service.get_dashboard_state(ticker)
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Failed to build dashboard for {ticker}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to build dashboard payload") from exc


# ============= FAST SIGNAL ENDPOINT (NO API CALLS) =============

@app.get("/api/signal/fast/{ticker}")
async def get_fast_signal(ticker: str):
    """
    ULTRA-FAST signal endpoint - uses ONLY cached data and local Python analysis.
    NO external API calls. Target: <100ms response time.

    This is used for:
    - AI Agents panel (instant display)
    - Trade decision panel (instant recommendations)
    - Auto-trade logic (must be fast for real-time trading)
    """
    ticker = ticker.upper()

    try:
        # Get quote (fast - Alpaca is quick)
        quote_data = await get_quote(ticker)
        current_price = quote_data.get("price", 100)

        # Get bars for technical analysis (fast - Alpaca is quick)
        bars = await get_bars(ticker, timeframe="15Min", limit=80)

        # Pure Python technical analysis (instant)
        from app.services.technical_indicators import analyze_technical
        technical = analyze_technical(ticker, current_price, bars)

        # Check sentiment cache (NO API call if not cached)
        cached_sentiment = _sentiment_cache.get(ticker)
        sentiment_score = 50  # Neutral default
        sentiment_label = "neutral"

        if cached_sentiment:
            cached_data, cache_time = cached_sentiment
            # Use cache if less than 5 minutes old
            if (datetime.utcnow() - cache_time).total_seconds() < 300:
                sentiment_score = cached_data.get("score", 50)
                sentiment_label = cached_data.get("sentiment", "neutral")

        fast_plan = build_trade_plan(
            price=current_price,
            catalyst_score=sentiment_score,
            ai_score=sentiment_score,
            momentum_score=technical.score,
            price_change_pct=float(quote_data.get("change_percent", 0) or 0),
            llm_enhanced=bool(cached_sentiment and cached_sentiment[0].get("llm_enhanced")),
            technical_score=technical.score,
            technical_regime=technical.regime.value,
            technical_rsi=technical.rsi,
            support=technical.support,
            resistance=technical.resistance,
            relative_volume=calculate_relative_volume(bars),
            bars=bars,
            buy_threshold=70,
            news_age_hours=None,
        )

        combined_score = fast_plan["setup_score"]
        action = fast_plan["action"]
        confidence = min(max(combined_score / 100, 0.35), 0.9)

        # Build agent signals for the UI
        news_agent = {
            "score": sentiment_score,
            "sentiment": 1 if sentiment_score > 60 else -1 if sentiment_score < 40 else 0,
            "confidence": 0.7 if cached_sentiment else 0.3,
            "urgency": 0.5,
            "notes": f"Sentiment: {sentiment_label}" + (" (cached)" if cached_sentiment else " (no data)")
        }

        earnings_agent = {
            "score": 50,
            "sentiment": 0,
            "confidence": 0.3,
            "urgency": 0.2,
            "notes": "Earnings data from cache"
        }

        technical_agent = {
            "score": technical.score,
            "sentiment": 1 if technical.score > 55 else -1 if technical.score < 45 else 0,
            "confidence": technical.confidence / 100,
            "urgency": 0.7 if abs(technical.score - 50) > 20 else 0.3,
            "notes": f"{technical.trend} trend, RSI: {technical.rsi:.1f}"
        }

        return {
            "ticker": ticker,
            "timestamp": datetime.utcnow().isoformat(),
            "fast_mode": True,
            "agents": {
                "news": news_agent,
                "earnings": earnings_agent,
                "technical": technical_agent
            },
            "decision": {
                "action": action,
                "ticker": ticker,
                "confidence": confidence,
                "score": round(combined_score),
                "entry_price": current_price,
                "entry_timing_state": fast_plan.get("timing_state"),
                "entry_timing_score": fast_plan.get("timing_score"),
                "entry_window": fast_plan.get("entry_window", fast_plan.get("timing_state")),
                "fresh_catalyst": fast_plan.get("fresh_catalyst"),
                "late_entry_risk": fast_plan.get("late_entry_risk"),
                "stop_loss": fast_plan["stop_loss"],
                "take_profit": fast_plan["take_profit"],
                "quantity": calculate_position_size(
                    price=current_price,
                    stop_loss_price=fast_plan["stop_loss"],
                    confidence=confidence,
                    signal_score=round(combined_score),
                    performance_multiplier=fast_plan["size_multiplier"],
                ),
                "rationale": ", ".join(fast_plan.get("supporting_reasons", [])[:3]) or f"Technical: {technical.score}, Sentiment: {sentiment_score}",
            },
            "technicals": {
                "rsi": technical.rsi,
                "macd": {
                    "value": technical.macd_value,
                    "signal": technical.macd_signal,
                    "histogram": technical.macd_histogram,
                },
                "trend": technical.trend,
                "regime": technical.regime.value,
                "support": technical.support,
                "resistance": technical.resistance,
                "signals": technical.signals
            },
            "market": {
                "price": current_price,
                "change": quote_data.get("change", 0),
                "change_percent": quote_data.get("change_percent", 0)
            }
        }

    except Exception as e:
        logger.error(f"Fast signal error for {ticker}: {e}")
        # Return neutral signal on error - never block the UI
        return {
            "ticker": ticker,
            "timestamp": datetime.utcnow().isoformat(),
            "fast_mode": True,
            "error": str(e),
            "agents": {
                "news": {"score": 50, "sentiment": 0, "confidence": 0, "urgency": 0, "notes": "Error"},
                "earnings": {"score": 50, "sentiment": 0, "confidence": 0, "urgency": 0, "notes": "Error"},
                "technical": {"score": 50, "sentiment": 0, "confidence": 0, "urgency": 0, "notes": "Error"}
            },
            "decision": {
                "action": "HOLD",
                "ticker": ticker,
                "confidence": 0,
                "score": 50,
                "rationale": "Error - defaulting to HOLD"
            }
        }


# ============= REAL-TIME PRICE ENDPOINT =============

# Alpaca data client for real quotes
_alpaca_data_client = None

def get_alpaca_data_client():
    """Get or create Alpaca data client for quotes."""
    global _alpaca_data_client
    if _alpaca_data_client is None:
        from alpaca.data.historical import StockHistoricalDataClient
        api_key = settings.ALPACA_API_KEY_ID
        secret_key = settings.ALPACA_API_SECRET_KEY
        if api_key and secret_key:
            _alpaca_data_client = StockHistoricalDataClient(api_key, secret_key)
    return _alpaca_data_client

@app.get("/api/quote/{ticker}")
async def get_quote(ticker: str):
    """Get real-time quote for a ticker from Alpaca."""
    ticker = ticker.upper()

    # Try to get real quote from Alpaca
    try:
        client = get_alpaca_data_client()
        if client:
            from alpaca.data.requests import StockLatestQuoteRequest, StockLatestTradeRequest, StockBarsRequest
            from alpaca.data.timeframe import TimeFrame

            current_price = 0
            prev_close = 0
            volume = 0
            source = "alpaca"

            # First try to get latest trade (more accurate for after hours)
            try:
                trade_request = StockLatestTradeRequest(symbol_or_symbols=[ticker])
                trades = client.get_stock_latest_trade(trade_request)
                if ticker in trades:
                    trade = trades[ticker]
                    current_price = float(trade.price) if trade.price else 0
                    volume = int(trade.size) if trade.size else 0
                    source = "alpaca_trade"
            except Exception as e:
                logger.debug(f"Failed to get latest trade for {ticker}: {e}")

            # Fallback to quote if no trade
            if current_price == 0:
                try:
                    request = StockLatestQuoteRequest(symbol_or_symbols=[ticker])
                    quotes = client.get_stock_latest_quote(request)
                    if ticker in quotes:
                        quote = quotes[ticker]
                        bid = float(quote.bid_price) if quote.bid_price else 0
                        ask = float(quote.ask_price) if quote.ask_price else 0
                        if bid > 0 and ask > 0:
                            current_price = (bid + ask) / 2
                        elif bid > 0:
                            current_price = bid
                        elif ask > 0:
                            current_price = ask
                        source = "alpaca_quote"
                except Exception as e:
                    logger.debug(f"Failed to get quote for {ticker}: {e}")

            # Get daily bars for prev close, high, low, open, volume
            day_high = 0
            day_low = 0
            day_open = 0
            day_volume = 0
            if current_price > 0:
                try:
                    bars_request = StockBarsRequest(
                        symbol_or_symbols=[ticker],
                        timeframe=TimeFrame.Day,
                        limit=5
                    )
                    bars_result = client.get_stock_bars(bars_request)
                    bar_list = list(bars_result[ticker])

                    if len(bar_list) >= 2:
                        prev_close = float(bar_list[-2].close)
                        today_bar = bar_list[-1]
                    elif len(bar_list) == 1:
                        prev_close = float(bar_list[0].open)
                        today_bar = bar_list[0]
                    else:
                        today_bar = None

                    if today_bar:
                        day_high = float(today_bar.high) if today_bar.high else 0
                        day_low = float(today_bar.low) if today_bar.low else 0
                        day_open = float(today_bar.open) if today_bar.open else 0
                        day_volume = int(today_bar.volume) if today_bar.volume else 0
                except Exception as e:
                    logger.debug(f"Failed to get bars for change calc {ticker}: {e}")

            if current_price > 0:
                change = current_price - prev_close if prev_close > 0 else 0
                change_percent = (change / prev_close * 100) if prev_close > 0 else 0

                return {
                    "ticker": ticker,
                    "price": round(current_price, 2),
                    "change": round(change, 2),
                    "change_percent": round(change_percent, 2),
                    "volume": day_volume or volume,
                    "high": round(day_high, 2) if day_high > 0 else None,
                    "low": round(day_low, 2) if day_low > 0 else None,
                    "open": round(day_open, 2) if day_open > 0 else None,
                    "prev_close": round(prev_close, 2) if prev_close > 0 else None,
                    "timestamp": datetime.utcnow().isoformat(),
                    "source": source
                }
    except Exception as e:
        logger.warning(f"Failed to get Alpaca quote for {ticker}: {e}")

    # Fallback to simulated quotes (updated Dec 2024 prices)
    simulated_quotes = {
        "AAPL": {"price": 237.33, "change": 2.30, "change_pct": 0.98},
        "MSFT": {"price": 423.46, "change": 6.51, "change_pct": 1.56},
        "GOOGL": {"price": 171.04, "change": -1.20, "change_pct": -0.70},
        "TSLA": {"price": 352.56, "change": 8.90, "change_pct": 2.59},
        "NVDA": {"price": 179.92, "change": 2.94, "change_pct": 1.66},
        "META": {"price": 569.19, "change": -4.30, "change_pct": -0.75},
        "AMZN": {"price": 207.89, "change": 1.80, "change_pct": 0.87},
        "AMD": {"price": 138.35, "change": 1.20, "change_pct": 0.88},
    }

    if ticker in simulated_quotes:
        quote = simulated_quotes[ticker]
        return {
            "ticker": ticker,
            "price": quote["price"],
            "change": quote["change"],
            "change_percent": quote["change_pct"],
            "timestamp": datetime.utcnow().isoformat(),
            "source": "simulated"
        }
    else:
        base_price = random.uniform(50, 300)
        change = random.uniform(-5, 5)
        return {
            "ticker": ticker,
            "price": round(base_price, 2),
            "change": round(change, 2),
            "change_percent": round((change / base_price) * 100, 2),
            "timestamp": datetime.utcnow().isoformat(),
            "source": "simulated"
        }

# ============= BARS/CHART DATA ENDPOINT =============

@app.get("/api/bars/{ticker}")
async def get_bars(
    ticker: str,
    timeframe: str = Query("1Min", description="Bar timeframe"),
    limit: int = Query(100, description="Number of bars")
):
    """Get real historical price bars from Alpaca."""
    ticker = ticker.upper()

    # Try to get real bars from Alpaca
    try:
        client = get_alpaca_data_client()
        if client:
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

            # Map timeframe string to Alpaca TimeFrame
            timeframe_map = {
                "1Min": TimeFrame.Minute,
                "5Min": TimeFrame(5, TimeFrameUnit.Minute),
                "15Min": TimeFrame(15, TimeFrameUnit.Minute),
                "30Min": TimeFrame(30, TimeFrameUnit.Minute),
                "1H": TimeFrame.Hour,
                "1Hour": TimeFrame.Hour,
                "1D": TimeFrame.Day,
                "1Day": TimeFrame.Day,
            }

            tf = timeframe_map.get(timeframe, TimeFrame.Minute)

            # Calculate start time based on timeframe
            # Note: Don't set end time - Alpaca free tier doesn't allow recent SIP queries
            now = datetime.utcnow()

            if timeframe in ["1D", "1Day"]:
                start = now - timedelta(days=limit + 5)
            elif timeframe in ["1H", "1Hour"]:
                start = now - timedelta(hours=limit + 10)
            else:
                # For minute bars, go back 1 day to include today's trading
                start = now - timedelta(days=1)

            request = StockBarsRequest(
                symbol_or_symbols=[ticker],
                timeframe=tf,
                start=start,
                # Note: No end time - let Alpaca return up to current available data
            )

            bars_data = client.get_stock_bars(request)

            # Access bars from the BarSet object
            if hasattr(bars_data, 'data') and ticker in bars_data.data:
                bars_list = bars_data.data[ticker]
            elif ticker in bars_data:
                bars_list = list(bars_data[ticker])
            else:
                bars_list = None

            if bars_list:
                result = []
                # Import pytz for timezone conversion
                import pytz
                eastern = pytz.timezone('America/New_York')

                for i, bar in enumerate(bars_list[-limit:]):  # Get last N bars
                    bar_time = bar.timestamp
                    # Convert to Eastern time for display
                    bar_time_et = bar_time.astimezone(eastern)
                    # Format time based on timeframe
                    if timeframe in ["1D", "1Day"]:
                        t_str = bar_time_et.strftime("%m/%d")
                    elif timeframe in ["1H", "1Hour", "4Hour"]:
                        t_str = bar_time_et.strftime("%m/%d %-I%p").replace("AM", "am").replace("PM", "pm")
                    else:
                        # Minute bars - show 12-hour format with AM/PM
                        t_str = bar_time_et.strftime("%-I:%M%p").replace("AM", "am").replace("PM", "pm")

                    result.append({
                        "time": i,
                        "timestamp": bar_time.isoformat(),
                        "t": t_str,
                        "open": float(bar.open),
                        "high": float(bar.high),
                        "low": float(bar.low),
                        "close": float(bar.close),
                        "volume": int(bar.volume),
                        "vwap": float(bar.vwap) if bar.vwap else None,
                        "trade_count": int(bar.trade_count) if bar.trade_count else None
                    })

                if result:
                    logger.info(f"Fetched {len(result)} real bars for {ticker}")
                    return result

    except Exception as e:
        logger.warning(f"Failed to get Alpaca bars for {ticker}: {e}")

    # Fallback to simulated bars if Alpaca fails
    logger.info(f"Using simulated bars for {ticker}")
    quote_data = await get_quote(ticker)
    base_price = quote_data.get("price", 100)

    interval_minutes = {
        "1Min": 1, "5Min": 5, "15Min": 15, "30Min": 30,
        "1H": 60, "1Hour": 60, "1D": 1440, "1Day": 1440
    }.get(timeframe, 1)

    bars = []
    current_price = base_price * 0.98
    now = datetime.utcnow()

    # Import pytz for timezone conversion
    import pytz
    eastern = pytz.timezone('America/New_York')

    for i in range(limit):
        bar_time = now - timedelta(minutes=interval_minutes * (limit - 1 - i))
        change_pct = random.uniform(-0.003, 0.0035)
        current_price = current_price * (1 + change_pct)

        high = current_price * (1 + random.uniform(0, 0.002))
        low = current_price * (1 - random.uniform(0, 0.002))
        open_price = current_price * (1 + random.uniform(-0.001, 0.001))

        # Convert to Eastern time for display
        bar_time_et = bar_time.replace(tzinfo=pytz.UTC).astimezone(eastern)
        if timeframe in ["1D", "1Day"]:
            t_str = bar_time_et.strftime("%m/%d")
        elif timeframe in ["1H", "1Hour", "4Hour"]:
            t_str = bar_time_et.strftime("%m/%d %-I%p").replace("AM", "am").replace("PM", "pm")
        else:
            # Minute bars - show 12-hour format with AM/PM
            t_str = bar_time_et.strftime("%-I:%M%p").replace("AM", "am").replace("PM", "pm")

        bars.append({
            "time": i,
            "timestamp": bar_time.isoformat(),
            "t": t_str,
            "open": round(open_price, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(current_price, 2),
            "volume": random.randint(10000, 500000)
        })

    return bars


# ============= MARKET SENTIMENT ENDPOINT =============

@app.get("/api/sentiment/{ticker}")
async def get_sentiment(ticker: str, use_llm: bool = False):
    """Get aggregated sentiment for a ticker based on news and earnings."""
    # Convert ticker to uppercase for consistency
    ticker = ticker.upper()

    # Check cache first (separate cache for LLM vs keyword mode)
    cache_key = f"{ticker}_llm" if use_llm else ticker
    now = datetime.utcnow()
    try:
        from zoneinfo import ZoneInfo as _ZI_sent
        _et_sent = datetime.now(_ZI_sent("America/New_York"))
        _in_rth_sent = _et_sent.weekday() < 5 and 9 <= _et_sent.hour < 16
    except Exception:
        _in_rth_sent = False
    _sent_ttl = float(SENTIMENT_CACHE_TTL_RTH_SECONDS) if _in_rth_sent and not use_llm else float(SENTIMENT_CACHE_TTL)

    if cache_key in _sentiment_cache:
        cached_data, cache_time = _sentiment_cache[cache_key]
        if (now - cache_time).total_seconds() < _sent_ttl:
            logger.debug(f"Sentiment cache HIT for {ticker}")
            return cached_data

    if not benzinga_client:
        return {
            "ticker": ticker,
            "sentiment": "neutral",
            "score": 50,
            "message": "Benzinga API not configured"
        }

    # Fetch all Benzinga data sources (cheap API calls)
    news_task = benzinga_client.get_news(tickers=ticker, limit=20)
    earnings_task = benzinga_client.get_earnings(ticker=ticker, limit=5)
    ratings_task = benzinga_client.get_ratings(ticker=ticker, limit=5)
    consensus_task = benzinga_client.get_consensus(ticker)

    news, earnings, ratings, consensus = await asyncio.gather(
        news_task, earnings_task, ratings_task, consensus_task,
        return_exceptions=True
    )

    # Extract data lists safely
    news_items = news.get("results", [])[:10] if isinstance(news, dict) else []
    earnings_items = earnings.get("results", [])[:3] if isinstance(earnings, dict) else []
    ratings_items = ratings.get("results", [])[:5] if isinstance(ratings, dict) else []

    components = []  # List of (category, score, weight) tuples
    llm_used = False
    shrinkage_info = {"mode": "keywords", "final_shrinkage": 0.0}

    # === LLM MODE: Feed everything to Claude, get one holistic score ===
    # Only allow LLM calls during market hours (Mon-Fri 9:30AM-4PM ET) to save credits
    if use_llm:
        from zoneinfo import ZoneInfo as _ZI_llm
        _now_llm = datetime.now(_ZI_llm("America/New_York"))
        _in_market_hours = (
            _now_llm.weekday() < 5
            and _now_llm.hour >= 9
            and _now_llm.hour < 16
        )
        if not _in_market_hours:
            logger.debug(f"LLM skip for {ticker}: outside market hours")
            use_llm = False

    if use_llm and not news_items:
        logger.debug(f"LLM skip for {ticker}: no news articles")
        use_llm = False

    if use_llm and news_items:
        try:
            # Extract latest news timestamp for cache invalidation
            latest_ts = None
            for item in news_items:
                published = item.get("published", item.get("created", ""))
                if published:
                    try:
                        ts = datetime.fromisoformat(str(published).replace("Z", "+00:00"))
                        if latest_ts is None or ts > latest_ts:
                            latest_ts = ts
                    except (ValueError, TypeError):
                        pass

            llm_result = await NewsIntelligenceAgent.analyze_with_cache(
                news_items=news_items,
                ticker=ticker,
                latest_news_ts=latest_ts,
                earnings_data=earnings_items if earnings_items else None,
                ratings_data=ratings_items if ratings_items else None,
                consensus_data=consensus if isinstance(consensus, dict) else None,
            )
            sentiment_score = float(llm_result.get("score", 50))
            llm_used = True
            shrinkage_info = {"mode": "llm", "final_shrinkage": 0.0}
            logger.info(f"LLM score for {ticker}: {sentiment_score} (confidence: {llm_result.get('confidence', 'N/A')})")
        except Exception as e:
            logger.warning(f"LLM analysis failed for {ticker}, falling back to keywords: {e}")
            use_llm = False  # Fall through to keyword mode

    # === KEYWORD MODE: Component-based scoring (fast, free) ===
    if not use_llm:
        news_weight = 0.25
        earnings_weight = 0.30
        ratings_weight = 0.25
        consensus_weight = 0.20

        # News: keyword matching
        net_signals = 0
        news_score = 50
        if news_items:
            positive_signals = 0
            negative_signals = 0
            theme_counts = {}

            for item in news_items:
                title = item.get("title", "").lower()
                theme_words = [w for w in ["upgrade", "downgrade", "beat", "miss", "earnings", "rating"] if w in title]
                theme_key = "_".join(sorted(theme_words)) if theme_words else title[:48]
                n_seen = theme_counts.get(theme_key, 0)
                if n_seen >= 3:
                    continue
                theme_counts[theme_key] = n_seen + 1

                if any(word in title for word in ["upgrade", "beat", "beats", "surge", "rally", "soar",
                                                  "jump", "bullish", "outperform", "record", "breakthrough"]):
                    positive_signals += 1
                elif any(word in title for word in ["downgrade", "miss", "misses", "plunge", "crash",
                                                    "bearish", "underperform", "bankruptcy", "investigation"]):
                    negative_signals += 1
                elif any(word in title for word in ["gain", "rise", "strong", "growth"]):
                    positive_signals += 0.5
                elif any(word in title for word in ["fall", "drop", "loss", "weak", "concern", "decline"]):
                    negative_signals += 0.5

            net_signals = positive_signals - negative_signals
            if net_signals > 0:
                news_score = 50 + min(35, 12 * (net_signals ** 0.7))
            elif net_signals < 0:
                news_score = 50 - min(35, 12 * (abs(net_signals) ** 0.7))
            components.append(("news", news_score, news_weight))

        # Earnings: EPS beat/miss math
        earnings_score = 50
        if earnings_items:
            earnings_signals = []
            for i, earning in enumerate(earnings_items):
                if earning.get("estimated_eps") and earning.get("actual_eps"):
                    try:
                        estimated = float(earning["estimated_eps"])
                        actual = float(earning["actual_eps"])
                        if estimated != 0:
                            surprise_pct = (actual - estimated) / abs(estimated)
                            recency_weight = 1.0 / (2 ** i)
                            earnings_signals.append((surprise_pct, recency_weight))
                    except (ValueError, TypeError):
                        pass
            if earnings_signals:
                total_weight = sum(w for _, w in earnings_signals)
                weighted_surprise = sum(s * w for s, w in earnings_signals) / total_weight
                adjustment = max(-25, min(25, weighted_surprise * 150))
                earnings_score = 50 + adjustment
                components.append(("earnings", earnings_score, earnings_weight))

        # Ratings: count upgrades vs downgrades
        ratings_score = 50
        if ratings_items:
            upgrades = sum(1 for r in ratings_items if "upgrade" in r.get("rating_action", "").lower())
            downgrades = sum(1 for r in ratings_items if "downgrade" in r.get("rating_action", "").lower())
            if upgrades or downgrades:
                net = upgrades - downgrades
                if net > 0:
                    ratings_score = 50 + min(30, 10 * net)
                elif net < 0:
                    ratings_score = 50 - min(30, 10 * abs(net))
                components.append(("ratings", ratings_score, ratings_weight))

        # Consensus: overall analyst label
        consensus_score = 50
        if isinstance(consensus, dict) and consensus.get("results"):
            cons = consensus["results"][0] if isinstance(consensus["results"], list) else consensus["results"]
            rating = cons.get("consensus_rating", "").lower()
            if "strong buy" in rating:
                consensus_score = 80
            elif "buy" in rating:
                consensus_score = 68
            elif "hold" in rating or "neutral" in rating:
                consensus_score = 50
            elif "sell" in rating:
                consensus_score = 32
            elif "strong sell" in rating:
                consensus_score = 20
            components.append(("consensus", consensus_score, consensus_weight))

        # Weighted average of all components with nuanced shrinkage
        shrinkage_info = {"mode": "keywords", "final_shrinkage": 0.0}
        if components:
            total_weight = sum(w for _, _, w in components)
            sentiment_score = sum(s * w for _, s, w in components) / total_weight
            pre_shrinkage = round(sentiment_score, 2)

            # Compute per-category quality and blended shrinkage
            categories_used = [cat for cat, _, _ in components]
            quality_map = {}
            shrinkage_per_cat = {}
            for cat, _, w in components:
                q = _compute_category_quality(
                    cat,
                    news_items=news_items,
                    earnings_items=earnings_items,
                    ratings_items=ratings_items,
                    net_signals=net_signals,
                )
                quality_map[cat] = round(q, 3)
                cfg = SHRINKAGE_CONFIG[cat]
                shrinkage_per_cat[cat] = cfg["max_shrinkage"] - q * (cfg["max_shrinkage"] - cfg["min_shrinkage"])

            # Weighted average of per-category shrinkages
            blended_shrinkage = sum(
                shrinkage_per_cat[cat] * w for cat, _, w in components
            ) / total_weight

            # Multi-source factor: more sources → less shrinkage
            n_sources = min(len(components), 4)
            multi_factor = MULTI_SOURCE_SHRINKAGE.get(n_sources, 0.0)
            final_shrinkage = blended_shrinkage * multi_factor

            sentiment_score = 50 + (sentiment_score - 50) * (1 - final_shrinkage)

            shrinkage_info = {
                "mode": "keywords",
                "categories_used": categories_used,
                "quality": quality_map,
                "blended_shrinkage": round(blended_shrinkage, 4),
                "multi_source_factor": multi_factor,
                "final_shrinkage": round(final_shrinkage, 4),
                "pre_shrinkage_score": pre_shrinkage,
                "post_shrinkage_score": round(sentiment_score, 2),
            }

            # Fresh bullish headlines with limited tape move should score before the crowd piles in.
            _age_kw = _newest_article_age_hours(news_items, datetime.utcnow())
            if (
                _age_kw is not None
                and _age_kw <= 1.5
                and net_signals >= 1
                and sentiment_score > 52
            ):
                freshness_lift = min(8.0, 2.5 + 1.4 * min(float(net_signals), 4.0))
                if _age_kw <= 0.33:
                    freshness_lift += 3.0
                sentiment_score = min(95.0, sentiment_score + freshness_lift)
        else:
            sentiment_score = 50

    # === FINAL SCORE PROCESSING (both modes) ===
    sentiment_score = round(max(5, min(95, sentiment_score)), 1)

    if sentiment_score >= 70:
        sentiment = "bullish"
    elif sentiment_score >= 60:
        sentiment = "slightly_bullish"
    elif sentiment_score <= 30:
        sentiment = "bearish"
    elif sentiment_score <= 40:
        sentiment = "slightly_bearish"
    else:
        sentiment = "neutral"

    # Build result
    component_scores = {"mode": "llm" if llm_used else "keywords"}
    if llm_used:
        component_scores["llm_score"] = sentiment_score
    else:
        if news_items:
            component_scores["news"] = round(news_score, 1)
        if earnings_items:
            component_scores["earnings"] = round(earnings_score, 1)
        if ratings_items:
            component_scores["ratings"] = round(ratings_score, 1)
        if isinstance(consensus, dict) and consensus.get("results"):
            component_scores["consensus"] = round(consensus_score, 1)

    _art_age = _newest_article_age_hours(news_items, datetime.utcnow()) if news_items else None
    result = {
        "ticker": ticker,
        "sentiment": sentiment,
        "score": sentiment_score,
        "llm_enhanced": llm_used,
        "components": component_scores,
        "shrinkage": shrinkage_info,
        "newest_article_age_hours": round(_art_age, 4) if _art_age is not None else None,
        "sources": {
            "news_analyzed": len(news_items),
            "earnings_analyzed": len(earnings_items),
            "ratings_analyzed": len(ratings_items),
            "has_consensus": bool(isinstance(consensus, dict) and consensus.get("results"))
        },
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

    # Cache the result
    _sentiment_cache[cache_key] = (result, datetime.utcnow())

    # Record scoring snapshot for backtesting (non-blocking, market hours only)
    from zoneinfo import ZoneInfo as _ZI_snap
    _snap_now = datetime.now(_ZI_snap("America/New_York"))
    if _snap_now.weekday() < 5 and 9 <= _snap_now.hour < 16:
        asyncio.ensure_future(asyncio.to_thread(
            _record_scoring_snapshot_sync,
            ticker=ticker,
            mode="llm" if llm_used else "keywords",
            news_items=news_items,
            earnings_items=earnings_items,
            ratings_items=ratings_items,
            consensus_data=consensus if isinstance(consensus, dict) else {},
            score=sentiment_score,
            shrinkage_info=shrinkage_info,
            components_data=component_scores,
        ))

    return result


# ============= UNIFIED PRODUCTION TRADING SYSTEM =============

async def _analyze_ticker_for_signal(ticker: str) -> dict:
    """Analyze a single ticker and return signal data."""
    try:
        local_settings = get_settings()
        buy_threshold = float(local_settings.TRADING_MIN_SIGNAL_SCORE)
        llm_rescore_threshold = float(local_settings.TRADING_LLM_RESCORE_MIN_SCORE)

        # Momentum, sentiment, and quote in parallel (quote shared for TA + execution)
        momentum_task = get_momentum_analysis(ticker)
        sentiment_task = get_sentiment(ticker)
        quote_task = get_quote(ticker)

        momentum, sentiment, quote = await asyncio.gather(
            momentum_task, sentiment_task, quote_task,
            return_exceptions=True
        )

        # Handle exceptions
        if isinstance(momentum, Exception):
            logger.error(f"Momentum analysis failed for {ticker}: {momentum}")
            return None
        if isinstance(sentiment, Exception):
            logger.error(f"Sentiment analysis failed for {ticker}: {sentiment}")
            return None
        if isinstance(quote, Exception):
            logger.error(f"Quote failed for {ticker}: {quote}")
            quote = {"price": 100, "change_percent": 0}

        momentum_score = momentum["momentum_score"]
        ai_score = sentiment["score"]  # Benzinga sentiment (news, earnings, ratings)

        current_price = float(quote.get("price", 100) or 100)
        price_change_pct = float(quote.get("change_percent", 0) or 0)
        news_age_h = sentiment.get("newest_article_age_hours")

        # Catalyst-first: reward strong AI + calm/under-reacted tape; penalize obvious chases.
        base_score = ai_score
        momentum_boost = 0.0
        momentum_warning = False

        if ai_score >= 62:
            if -1.0 <= price_change_pct <= 1.2:
                momentum_boost = 5.0 + min(6.0, max(0.0, ai_score - 62.0) * 0.14)
                if news_age_h is not None and news_age_h <= 1.0 and float(momentum_score) >= 45.0:
                    momentum_boost += 2.5
                if news_age_h is not None and news_age_h <= 0.25:
                    momentum_boost += 3.5
            elif 1.2 < price_change_pct <= 2.0:
                momentum_boost = 1.5 if news_age_h is not None and news_age_h <= 0.75 else 0.5
            elif 2.0 < price_change_pct <= 2.6:
                momentum_boost = -2.0
            elif price_change_pct > 2.6:
                momentum_boost = -12.0 - min(8.0, (price_change_pct - 2.6) * 3.5)
                momentum_warning = True
            elif price_change_pct < -2.0:
                momentum_boost = -6.0
                momentum_warning = True
            elif -2.0 <= price_change_pct < -1.2:
                momentum_boost = -1.0
        elif ai_score < 40 and momentum_score < 45:
            momentum_boost = 5.0

        combined_score = base_score + momentum_boost
        combined_score = max(0, min(100, combined_score))

        keyword_score = combined_score
        llm_used = False
        llm_reasoning = ""
        early_llm = bool(
            news_age_h is not None
            and news_age_h <= 5.0
            and ai_score >= 53
            and -1.6 <= price_change_pct <= 1.8
            and (
                float(momentum_score) >= 40.0
                or (-1.0 <= price_change_pct <= 1.2 and ai_score >= 57)
                or (news_age_h <= 1.0 and ai_score >= 60)
            )
        )
        if combined_score >= llm_rescore_threshold or combined_score <= 25 or early_llm:
            try:
                llm_sentiment = await get_sentiment(ticker, use_llm=True)
                llm_score = llm_sentiment.get("score", combined_score)
                llm_used = llm_sentiment.get("llm_enhanced", False)
                if llm_used:
                    combined_score = llm_score
                    combined_score = max(0, min(100, combined_score))
                    llm_reasoning = llm_sentiment.get("summary", "") or llm_sentiment.get("trading_implication", "")
            except Exception as e:
                logger.warning(f"LLM re-score failed for {ticker}, using keyword score: {e}")

        # Intraday technical context: trend, structure, ATR, and RVOL.
        tech_ctx = {
            "technical_veto": False,
            "technical_veto_reason": None,
            "technical_score": None,
            "technical_regime": None,
            "technical_rsi": None,
            "technical_bias_points": 0.0,
            "support": None,
            "resistance": None,
            "atr": 0.0,
            "relative_volume": None,
        }
        bars = []
        try:
            bars = await get_bars(ticker, timeframe="15Min", limit=80)
            tech_ctx = _technical_context_from_bars(ticker, current_price, bars or [])
        except Exception as e:
            logger.warning(f"Technical context failed for {ticker}: {e}")

        plan = build_trade_plan(
            price=current_price,
            catalyst_score=combined_score + float(tech_ctx.get("technical_bias_points") or 0),
            ai_score=ai_score,
            momentum_score=momentum_score,
            price_change_pct=price_change_pct,
            llm_enhanced=llm_used,
            momentum_warning=momentum_warning,
            technical_score=tech_ctx.get("technical_score"),
            technical_regime=tech_ctx.get("technical_regime"),
            technical_rsi=tech_ctx.get("technical_rsi"),
            support=tech_ctx.get("support"),
            resistance=tech_ctx.get("resistance"),
            relative_volume=tech_ctx.get("relative_volume"),
            bars=bars or [],
            buy_threshold=buy_threshold,
            news_age_hours=news_age_h,
        )
        timing_ctx = assess_entry_timing(
            price=current_price,
            bars=bars or [],
            price_change_pct=price_change_pct,
            ai_score=ai_score,
            momentum_score=momentum_score,
            news_age_hours=news_age_h,
        )

        combined_score = float(plan.get("setup_score", combined_score) or combined_score)
        action = plan.get("action", "WAIT")
        stop_loss_price = float(plan.get("stop_loss") or 0) or _entry_risk_levels(current_price, quote, tech_ctx, bars)[0]
        take_profit_price = float(plan.get("take_profit") or 0) or _entry_risk_levels(current_price, quote, tech_ctx, bars)[1]

        signal_confidence = min(
            max((combined_score / 100.0) + min(float(plan.get("risk_reward_ratio", 0) or 0), 3.0) * 0.03, 0.35),
            0.95,
        )

        reasoning_parts = []
        if llm_reasoning:
            reasoning_parts.append(llm_reasoning.strip())
        if plan.get("supporting_reasons"):
            reasoning_parts.append("Setup: " + ", ".join(plan["supporting_reasons"][:3]))
        if plan.get("timing_state"):
            reasoning_parts.append(
                f"Timing {plan.get('timing_state')} ({float(plan.get('timing_score', 50) or 50):.0f})"
            )
        gate_reasons = (plan.get("buy_gate") or {}).get("reasons", [])
        if gate_reasons:
            reasoning_parts.append("Blocked by " + ", ".join(gate_reasons[:3]))
        reasoning = " | ".join(part for part in reasoning_parts if part)[:500]

        momentum_signals = momentum.get("signals", [])[:2]
        if plan.get("supporting_reasons"):
            momentum_signals.extend(plan["supporting_reasons"][:2])

        return {
            "ticker": ticker,
            "action": action,
            "combined_score": round(combined_score, 1),
            "keyword_score": round(keyword_score, 1),
            "catalyst_score": round(base_score + momentum_boost, 1),
            "llm_enhanced": llm_used,
            "momentum_score": momentum_score,
            "ai_score": ai_score,
            "momentum_boost": round(momentum_boost, 1),
            "momentum_warning": momentum_warning,
            "entry_price": current_price,
            "price_change_pct": round(price_change_pct, 2),
            "newest_article_age_hours": news_age_h,
            "stop_loss": stop_loss_price,
            "take_profit": take_profit_price,
            "buy_gate": plan.get("buy_gate", {}),
            "risk_reward_ratio": plan.get("risk_reward_ratio"),
            "entry_timing_score": plan.get("timing_score", timing_ctx.get("timing_score")),
            "entry_timing_state": plan.get("timing_state", timing_ctx.get("timing_state")),
            "entry_window": plan.get("entry_window", plan.get("timing_state", timing_ctx.get("timing_state"))),
            "late_entry_risk": plan.get("late_entry_risk", timing_ctx.get("late_entry_risk")),
            "price_vs_vwap_pct": plan.get("price_vs_vwap_pct", timing_ctx.get("price_vs_vwap_pct")),
            "session_range_position": plan.get("session_range_position", timing_ctx.get("session_range_position")),
            "fresh_catalyst": plan.get("fresh_catalyst", timing_ctx.get("fresh_catalyst")),
            "relative_volume": plan.get("relative_volume"),
            "atr": plan.get("atr") or tech_ctx.get("atr"),
            "support": tech_ctx.get("support"),
            "resistance": tech_ctx.get("resistance"),
            "technical_veto": tech_ctx.get("technical_veto", False),
            "technical_veto_reason": tech_ctx.get("technical_veto_reason"),
            "technical_regime": tech_ctx.get("technical_regime"),
            "regime_at_entry": tech_ctx.get("technical_regime"),
            "technical_rsi": tech_ctx.get("technical_rsi"),
            "technical_score": tech_ctx.get("technical_score"),
            "technical_bias_points": tech_ctx.get("technical_bias_points"),
            "quantity": calculate_position_size(
                price=current_price,
                stop_loss_price=stop_loss_price,
                confidence=signal_confidence,
                signal_score=round(combined_score),
                performance_multiplier=float(plan.get("size_multiplier", 1.0) or 1.0),
            ),
            "position_size_multiplier": float(plan.get("size_multiplier", 1.0) or 1.0),
            "shrinkage": sentiment.get("shrinkage", {}),
            "signals": momentum_signals[:4],
            "strategy": plan.get("strategy_label", "catalyst_trend_follow"),
            "urgency": (
                "NOW" if action == "BUY" and (
                    plan.get("timing_state") == "early" or combined_score >= buy_threshold + 2
                )
                else ("SOON" if action in {"BUY", "HOLD"} else "WAIT")
            ),
            "reasoning": reasoning,
            "source": "watchlist",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    except Exception as e:
        logger.error(f"Error analyzing {ticker}: {e}")
        return None


@app.get("/api/trading/best-signal")
async def get_best_trading_signal():
    """Get the SINGLE BEST trading signal from all sources (momentum + AI)."""

    # Scan configured watchlist tickers - uses env var WATCHLIST_TICKERS
    settings = get_settings()
    candidates = settings.watchlist[:20]  # Limit to top 20 for performance

    # Fallback to defaults if watchlist is empty
    if not candidates:
        candidates = ["TSLA", "NVDA", "AMD", "AAPL", "META", "GOOGL", "MSFT"]

    logger.info(f"🔍 Scanning {len(candidates)} tickers: {candidates[:5]}...")

    # Analyze all tickers in parallel for speed
    results = await asyncio.gather(
        *[_analyze_ticker_for_signal(ticker) for ticker in candidates],
        return_exceptions=True
    )

    # Find best signal from results
    best_signal = None
    best_score = 0

    for result in results:
        if result is None or isinstance(result, Exception):
            continue
        if result.get("combined_score", 0) > best_score:
            best_signal = result
            best_score = result["combined_score"]

    # If no good signal, return wait status
    if not best_signal:
        return {
            "action": "WAIT",
            "message": "No strong trading signals detected",
            "timestamp": datetime.utcnow().isoformat()
        }

    return best_signal


# Cache for all decisions
_all_decisions_cache = {"data": None, "timestamp": 0}
ALL_DECISIONS_CACHE_TTL = 60  # Cache for 60 seconds (large watchlist)

@app.get("/api/trading/all-decisions")
async def get_all_trade_decisions():
    """Get trade decisions for ALL watchlist tickers (grouped by BUY/HOLD/SELL)."""
    global _all_decisions_cache

    now = datetime.utcnow().timestamp()

    # Check cache
    if _all_decisions_cache["data"] and (now - _all_decisions_cache["timestamp"]) < ALL_DECISIONS_CACHE_TTL:
        return _all_decisions_cache["data"]

    settings = get_settings()
    # Use full watchlist + dynamic tickers
    static_tickers = settings.watchlist
    dynamic_tickers = _get_dynamic_tickers() - set(static_tickers)
    tickers = static_tickers + list(dynamic_tickers)

    # Analyze all tickers with concurrency limit to avoid API overload
    sem = asyncio.Semaphore(20)
    async def analyze_limited(ticker):
        async with sem:
            return await _analyze_ticker_for_signal(ticker)

    results = await asyncio.gather(
        *[analyze_limited(ticker) for ticker in tickers],
        return_exceptions=True
    )

    # Group by action
    buy_decisions = []
    hold_decisions = []
    sell_decisions = []

    for result in results:
        if result is None or isinstance(result, Exception):
            continue

        action = result.get("action", "HOLD")
        ticker = result.get("ticker")
        trade_dec = _recent_trade_decisions.get(ticker, {})
        decision = {
            "ticker": ticker,
            "action": action,
            "confidence": result.get("combined_score", 50) / 100,
            "combinedScore": result.get("combined_score", 50),
            "keywordScore": result.get("keyword_score", result.get("combined_score", 50)),
            "llmEnhanced": result.get("llm_enhanced", False),
            "aiScore": result.get("ai_score", 50),
            "momentumScore": result.get("momentum_score", 50),
            "strategy": result.get("strategy", "UNKNOWN"),
            "urgency": result.get("urgency", "WAIT"),
            "entryPrice": result.get("entry_price", 0),
            "stopLoss": result.get("stop_loss", 0),
            "takeProfit": result.get("take_profit", 0),
            "shrinkage": result.get("shrinkage", {}),
            "scoredAt": result.get("timestamp"),
            "signals": result.get("signals", []),
            "reasoning": result.get("reasoning", ""),
            "tradeStatus": trade_dec.get("status"),
            "tradeReason": trade_dec.get("reason"),
        }

        if action == "BUY":
            buy_decisions.append(decision)
        elif action == "SELL":
            sell_decisions.append(decision)
        else:
            hold_decisions.append(decision)

    # Sort each group by combined score (descending)
    buy_decisions.sort(key=lambda x: x["combinedScore"], reverse=True)
    hold_decisions.sort(key=lambda x: x["combinedScore"], reverse=True)
    sell_decisions.sort(key=lambda x: x["combinedScore"], reverse=True)

    response = {
        "timestamp": datetime.utcnow().isoformat(),
        "total": len(buy_decisions) + len(hold_decisions) + len(sell_decisions),
        "buy": buy_decisions,
        "hold": hold_decisions,
        "sell": sell_decisions,
        "counts": {
            "buy": len(buy_decisions),
            "hold": len(hold_decisions),
            "sell": len(sell_decisions),
        }
    }

    # Cache the result
    _all_decisions_cache = {"data": response, "timestamp": now}

    return response


# Rate limiting for trade execution
_last_trade_execution: dict = {"time": 0, "ticker": None}
TRADE_COOLDOWN_SECONDS = 60  # 1 minute between trades

@app.post("/api/trading/execute")
async def execute_trade(auto: bool = False, ticker: Optional[str] = None):
    """Execute a trade on Alpaca paper trading.

    If ticker is provided, analyze and trade that specific ticker.
    If ticker is not provided, use the best overall signal.
    """
    global _last_trade_execution

    # Rate limiting check
    now = datetime.utcnow().timestamp()
    time_since_last = now - _last_trade_execution["time"]
    if time_since_last < TRADE_COOLDOWN_SECONDS:
        remaining = int(TRADE_COOLDOWN_SECONDS - time_since_last)
        return {
            "status": "rate_limited",
            "message": f"Please wait {remaining}s before next trade",
            "cooldown_remaining": remaining
        }

    # Get signal for specific ticker or best overall
    if ticker:
        # Analyze the specific ticker requested
        signal = await _analyze_ticker_for_signal(ticker)
        if signal is None:
            return {
                "status": "error",
                "message": f"Failed to analyze {ticker}",
            }
        logger.info(f"[Execute] Analyzing specific ticker: {ticker} -> {signal.get('action')} ({signal.get('combined_score', 0):.1f})")
    else:
        # Get best signal from all candidates
        signal = await get_best_trading_signal()

    if signal.get("action") == "WAIT" or signal.get("action") == "HOLD":
        return {
            "status": "no_trade",
            "message": f"No actionable signal for {signal.get('ticker', 'unknown')} (action: {signal.get('action')})",
            "signal": signal
        }

    # Check if we already have a large position in this ticker
    ticker = signal.get("ticker")
    positions = alpaca_trader.get_positions()
    existing_position = next((p for p in positions if p["symbol"] == ticker), None)
    if existing_position and abs(existing_position.get("qty", 0)) >= 100:
        return {
            "status": "position_limit",
            "message": f"Already have {existing_position['qty']} shares of {ticker}. Close or reduce position first.",
            "existing_position": existing_position
        }

    # Execute on Alpaca
    if auto or signal.get("combined_score", 0) >= 70:
        # Update rate limit tracker BEFORE execution
        _last_trade_execution = {"time": now, "ticker": ticker}

        result = alpaca_trader.execute_trade(signal)

        # Log the trade execution
        log_activity(
            log_type="TRADE",
            ticker=signal.get("ticker", "UNKNOWN"),
            action=signal.get("action", "BUY"),
            details={
                "price": signal.get("price"),
                "quantity": result.get("qty") if result else None,
                "score": signal.get("combined_score"),
                "reasoning": signal.get("reasoning", "")[:200],  # Truncate long reasoning
                "order_id": result.get("id") if result else None,
                "status": "executed"
            }
        )

        return {
            "status": "executed",
            "signal": signal,
            "execution": result,
            "mode": "PAPER TRADING"
        }
    else:
        return {
            "status": "pending_confirmation",
            "signal": signal,
            "message": "Signal ready - confirm to execute"
        }


class ManualTradeRequest(BaseModel):
    """Request model for manual trades with full control."""
    ticker: str
    side: str  # "buy" or "sell"
    quantity: float
    order_type: str = "market"  # "market", "limit", "stop", "bracket"
    limit_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    time_in_force: str = "day"  # "day", "gtc", "ioc", "fok"


@app.post("/api/trading/manual")
async def execute_manual_trade(trade: ManualTradeRequest):
    """
    Execute a manual trade with full user control.

    This bypasses AI recommendations and executes exactly what the user specifies.
    Supports market, limit, stop, and bracket orders.
    """
    global _last_trade_execution

    # Rate limiting check
    now = datetime.utcnow().timestamp()
    time_since_last = now - _last_trade_execution["time"]
    if time_since_last < TRADE_COOLDOWN_SECONDS:
        remaining = int(TRADE_COOLDOWN_SECONDS - time_since_last)
        return {
            "status": "rate_limited",
            "message": f"Please wait {remaining}s before next trade",
            "cooldown_remaining": remaining
        }

    # Validate inputs
    if trade.side not in ["buy", "sell"]:
        return {"status": "error", "message": "Side must be 'buy' or 'sell'"}

    if trade.quantity <= 0:
        return {"status": "error", "message": "Quantity must be positive"}

    if trade.order_type == "limit" and trade.limit_price is None:
        return {"status": "error", "message": "Limit price required for limit orders"}

    # Get current price for validation
    try:
        quote = alpaca_trader.get_quote(trade.ticker)
        current_price = quote.get("price", 0) if quote else 0
    except Exception:
        current_price = 0

    # Check if we have enough buying power
    account = alpaca_trader.get_account_status()
    if account:
        buying_power = float(account.get("daytrading_buying_power", 0)) or float(account.get("buying_power", 0))
        estimated_cost = trade.quantity * (trade.limit_price or current_price or 100)
        if trade.side == "buy" and estimated_cost > buying_power:
            return {
                "status": "error",
                "message": f"Insufficient buying power. Need ${estimated_cost:,.2f}, have ${buying_power:,.2f}"
            }

    # Import Alpaca order types
    from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, StopOrderRequest
    from alpaca.trading.requests import StopLossRequest, TakeProfitRequest
    from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass

    # Convert side string to enum
    order_side = OrderSide.BUY if trade.side.lower() == "buy" else OrderSide.SELL

    # Convert time_in_force string to enum
    tif = TimeInForce.DAY if trade.time_in_force.lower() == "day" else TimeInForce.GTC

    # Build order based on type
    if trade.order_type == "bracket" and trade.stop_loss and trade.take_profit:
        # Bracket order with stop loss and take profit
        order_request = MarketOrderRequest(
            symbol=trade.ticker,
            qty=trade.quantity,
            side=order_side,
            time_in_force=tif,
            order_class=OrderClass.BRACKET,
            stop_loss=StopLossRequest(stop_price=round(trade.stop_loss, 2)),
            take_profit=TakeProfitRequest(limit_price=round(trade.take_profit, 2))
        )
    elif trade.order_type == "limit":
        order_request = LimitOrderRequest(
            symbol=trade.ticker,
            qty=trade.quantity,
            side=order_side,
            time_in_force=tif,
            limit_price=round(trade.limit_price, 2)
        )
    elif trade.order_type == "stop":
        order_request = StopOrderRequest(
            symbol=trade.ticker,
            qty=trade.quantity,
            side=order_side,
            time_in_force=tif,
            stop_price=round(trade.stop_loss or trade.limit_price, 2)
        )
    else:
        # Market order
        order_request = MarketOrderRequest(
            symbol=trade.ticker,
            qty=trade.quantity,
            side=order_side,
            time_in_force=tif
        )

    # Update rate limit tracker
    _last_trade_execution = {"time": now, "ticker": trade.ticker}

    # Execute the order
    try:
        result = alpaca_trader.client.submit_order(order_data=order_request)

        # Log the manual trade
        log_activity(
            log_type="MANUAL_TRADE",
            ticker=trade.ticker,
            action=trade.side.upper(),
            details={
                "quantity": trade.quantity,
                "order_type": trade.order_type,
                "limit_price": trade.limit_price,
                "stop_loss": trade.stop_loss,
                "take_profit": trade.take_profit,
                "order_id": result.id if result else None,
                "status": "submitted"
            }
        )

        return {
            "status": "executed",
            "order": {
                "id": result.id,
                "symbol": result.symbol,
                "qty": str(result.qty),
                "side": result.side.value if hasattr(result.side, 'value') else str(result.side),
                "type": result.type.value if hasattr(result.type, 'value') else str(result.type),
                "status": result.status.value if hasattr(result.status, 'value') else str(result.status),
                "created_at": str(result.created_at)
            },
            "message": f"Manual {trade.side.upper()} order submitted for {trade.quantity} {trade.ticker}",
            "mode": "PAPER TRADING"  # Always paper trading for safety
        }
    except Exception as e:
        logger.error(f"Manual trade failed: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


@app.get("/api/trading/positions")
async def get_positions():
    """Get all open positions from Alpaca with associated stop/take profit orders."""
    positions = alpaca_trader.get_positions()

    # Get open orders to find stop loss and take profit legs
    open_orders = []
    if alpaca_trader.client:
        try:
            from alpaca.trading.requests import GetOrdersRequest
            from alpaca.trading.enums import QueryOrderStatus
            request = GetOrdersRequest(status=QueryOrderStatus.OPEN)
            open_orders = alpaca_trader.client.get_orders(filter=request)
        except Exception as e:
            logger.warning(f"Could not fetch open orders: {e}")

    # Map orders to positions
    for position in positions:
        ticker = position["symbol"]
        position["stop_loss"] = None
        position["take_profit"] = None

        # Find associated orders for this position
        for order in open_orders:
            if order.symbol != ticker:
                continue
            # Stop loss is a stop order
            if order.type.value == "stop" and order.stop_price:
                position["stop_loss"] = float(order.stop_price)
            # Take profit is a limit order (sell side for long positions)
            elif order.type.value == "limit" and order.limit_price:
                position["take_profit"] = float(order.limit_price)

        # Find entry time from filled buy orders
        position["entry_time"] = None
        for order in open_orders:
            pass  # open orders won't have fill time
        # Check closed/filled orders for entry time
        if alpaca_trader.client:
            try:
                from alpaca.trading.requests import GetOrdersRequest
                from alpaca.trading.enums import QueryOrderStatus, OrderSide as OS
                filled_req = GetOrdersRequest(
                    status=QueryOrderStatus.CLOSED,
                    symbols=[ticker],
                    side=OS.BUY,
                    limit=1,
                )
                filled_orders = alpaca_trader.client.get_orders(filter=filled_req)
                if filled_orders:
                    position["entry_time"] = str(filled_orders[0].filled_at) if filled_orders[0].filled_at else str(filled_orders[0].submitted_at)
            except Exception as e:
                logger.debug(f"Could not get entry time for {ticker}: {e}")

        # Check momentum for exit signals
        try:
            momentum = await get_momentum_analysis(ticker)

            # pnl_pct from Alpaca is a ratio (e.g. 0.02 = +2%, -0.01 = -1%)
            pnl_ratio = float(position.get("pnl_pct") or 0)
            if momentum["momentum_score"] < 40:
                position["exit_signal"] = "MOMENTUM LOST - CONSIDER EXIT"
            elif pnl_ratio >= 0.02:
                position["exit_signal"] = "TARGET HIT - TAKE PROFIT"
            elif pnl_ratio <= -0.01:
                position["exit_signal"] = "STOP LOSS - EXIT NOW"
            else:
                position["exit_signal"] = None

        except:
            position["exit_signal"] = None

    return {
        "positions": positions,
        "count": len(positions),
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/api/trading/close/{ticker}")
async def close_position(ticker: str, reason: str = "manual"):
    """Close a position."""
    result = alpaca_trader.close_position(ticker.upper())

    # Log the position exit
    log_activity(
        log_type="EXIT",
        ticker=ticker.upper(),
        action="CLOSE",
        details={
            "reason": reason,
            "pnl": result.get("pnl") if isinstance(result, dict) else None,
            "result": result.get("status") if isinstance(result, dict) else str(result)
        }
    )

    return result

@app.post("/api/trading/reduce/{ticker}")
async def reduce_position(ticker: str, quantity: int = 100):
    """Reduce a position by a specific quantity."""
    result = alpaca_trader.reduce_position(ticker.upper(), quantity)

    log_activity(
        log_type="REDUCE",
        ticker=ticker.upper(),
        action="REDUCE",
        details={
            "reduced_qty": quantity,
            "result": result.get("status") if isinstance(result, dict) else str(result)
        }
    )

    return result

@app.post("/api/trading/close-all")
async def close_all_positions():
    """Emergency: Close ALL positions."""
    result = alpaca_trader.close_all_positions()

    log_activity(
        log_type="EMERGENCY",
        ticker="ALL",
        action="CLOSE_ALL",
        details={"result": result.get("status") if isinstance(result, dict) else str(result)}
    )

    return result

# ============================================================
# AUTO-EXIT MONITORING
# ============================================================
EXIT_CONFIG = {
    "stop_loss_pct": -2.0,      # Exit if loss exceeds 2%
    "take_profit_pct": 5.0,     # Exit if profit exceeds 5%
    "momentum_exit": 35,        # Exit if momentum drops below 35
    "trailing_stop_pct": 1.5,   # Trailing stop: 1.5% from peak
}

# Track peak prices for trailing stops
_position_peaks: dict = {}

# Track tickers with pending exit orders to avoid duplicates
_pending_exit_orders: set = set()

async def check_position_exits():
    """Check all positions for exit signals and auto-close if needed."""
    global _pending_exit_orders

    positions = alpaca_trader.get_positions()
    exits_triggered = []

    # Get all pending orders to check which tickers already have exit orders
    try:
        if alpaca_trader.client:
            pending_orders = alpaca_trader.client.get_orders(status="open")
            tickers_with_pending = {order.symbol for order in pending_orders}
        else:
            tickers_with_pending = set()
    except Exception as e:
        logger.warning(f"Could not fetch pending orders: {e}")
        tickers_with_pending = _pending_exit_orders  # Use cached set

    for position in positions:
        ticker = position["symbol"]
        pnl_pct = position.get("pnl_pct", 0) * 100  # Convert to percentage
        current_price = position.get("current", 0)
        entry_price = position.get("entry", 0)

        # Skip if this ticker already has a pending order
        if ticker in tickers_with_pending or ticker in _pending_exit_orders:
            logger.debug(f"Skipping {ticker} - already has pending exit order")
            continue

        exit_reason = None

        # 1. Stop Loss Check
        if pnl_pct <= EXIT_CONFIG["stop_loss_pct"]:
            exit_reason = f"STOP_LOSS ({pnl_pct:.2f}%)"

        # 2. Take Profit Check
        elif pnl_pct >= EXIT_CONFIG["take_profit_pct"]:
            exit_reason = f"TAKE_PROFIT ({pnl_pct:.2f}%)"

        # 3. Trailing Stop Check
        else:
            # Track peak price
            if ticker not in _position_peaks or current_price > _position_peaks[ticker]:
                _position_peaks[ticker] = current_price

            peak = _position_peaks[ticker]
            if peak > 0:
                drawdown_from_peak = ((peak - current_price) / peak) * 100
                if drawdown_from_peak >= EXIT_CONFIG["trailing_stop_pct"] and pnl_pct > 0:
                    exit_reason = f"TRAILING_STOP (peak: ${peak:.2f}, drawdown: {drawdown_from_peak:.2f}%)"

        # 4. Momentum Check (only if in profit and no other exit triggered)
        if not exit_reason and pnl_pct > 0:
            try:
                momentum = await get_momentum_analysis(ticker)
                if momentum.get("momentum_score", 50) < EXIT_CONFIG["momentum_exit"]:
                    exit_reason = f"MOMENTUM_EXIT (score: {momentum.get('momentum_score')})"
            except:
                pass

        # Execute exit if triggered
        if exit_reason:
            logger.info(f"🚨 EXIT TRIGGERED: {ticker} - {exit_reason}")

            # Mark as pending BEFORE attempting to close
            _pending_exit_orders.add(ticker)

            result = alpaca_trader.close_position(ticker)

            # Check if order was successful
            if isinstance(result, dict):
                if result.get("status") == "error":
                    # Order failed - remove from pending
                    _pending_exit_orders.discard(ticker)
                    logger.warning(f"Exit order failed for {ticker}: {result.get('message')}")
                    # Don't log failed exits to avoid spam
                    continue
                elif result.get("status") in ["closed", "executed"]:
                    # Order succeeded - log it
                    log_activity(
                        log_type="AUTO_EXIT",
                        ticker=ticker,
                        action="CLOSE",
                        details={
                            "reason": exit_reason,
                            "pnl_pct": pnl_pct,
                            "entry": entry_price,
                            "exit_price": current_price,
                            "result": result.get("status")
                        }
                    )
                    exits_triggered.append({
                        "ticker": ticker,
                        "reason": exit_reason,
                        "pnl_pct": pnl_pct,
                        "result": result
                    })
                    # Clean up peak tracking
                    if ticker in _position_peaks:
                        del _position_peaks[ticker]
                    # Remove from pending after successful close
                    _pending_exit_orders.discard(ticker)

    return exits_triggered

@app.post("/api/trading/check-exits")
async def manual_check_exits():
    """Manually trigger exit check for all positions."""
    exits = await check_position_exits()
    return {
        "exits_triggered": len(exits),
        "details": exits,
        "config": EXIT_CONFIG,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/api/trading/exit-config")
async def get_exit_config():
    """Get current exit configuration."""
    return EXIT_CONFIG

@app.put("/api/trading/exit-config")
async def update_exit_config(
    stop_loss_pct: float = None,
    take_profit_pct: float = None,
    momentum_exit: int = None,
    trailing_stop_pct: float = None
):
    """Update exit configuration."""
    if stop_loss_pct is not None:
        EXIT_CONFIG["stop_loss_pct"] = stop_loss_pct
    if take_profit_pct is not None:
        EXIT_CONFIG["take_profit_pct"] = take_profit_pct
    if momentum_exit is not None:
        EXIT_CONFIG["momentum_exit"] = momentum_exit
    if trailing_stop_pct is not None:
        EXIT_CONFIG["trailing_stop_pct"] = trailing_stop_pct

    return {"status": "updated", "config": EXIT_CONFIG}

@app.get("/api/trading/account")
async def get_account():
    """Get Alpaca account status."""
    return alpaca_trader.get_account_status()


@app.get("/api/trading/orders")
async def get_orders(
    status: Optional[str] = Query("all", description="Order status: open, closed, all"),
    limit: int = Query(50, description="Maximum orders to return"),
    days: int = Query(7, description="Days to look back")
):
    """Get trade/order history from Alpaca."""
    if not alpaca_trader.client:
        # Return simulated orders if no client
        return {
            "orders": [
                {
                    "id": "sim-001",
                    "symbol": "AAPL",
                    "side": "buy",
                    "qty": 10,
                    "filled_qty": 10,
                    "type": "market",
                    "status": "filled",
                    "filled_avg_price": 234.50,
                    "submitted_at": (datetime.utcnow() - timedelta(hours=2)).isoformat(),
                    "filled_at": (datetime.utcnow() - timedelta(hours=2)).isoformat(),
                    "pnl": 28.50,
                    "pnl_pct": 1.22
                },
                {
                    "id": "sim-002",
                    "symbol": "NVDA",
                    "side": "buy",
                    "qty": 5,
                    "filled_qty": 5,
                    "type": "market",
                    "status": "filled",
                    "filled_avg_price": 142.30,
                    "submitted_at": (datetime.utcnow() - timedelta(hours=5)).isoformat(),
                    "filled_at": (datetime.utcnow() - timedelta(hours=5)).isoformat(),
                    "pnl": -15.75,
                    "pnl_pct": -2.21
                },
                {
                    "id": "sim-003",
                    "symbol": "TSLA",
                    "side": "sell",
                    "qty": 8,
                    "filled_qty": 8,
                    "type": "market",
                    "status": "filled",
                    "filled_avg_price": 351.20,
                    "submitted_at": (datetime.utcnow() - timedelta(days=1)).isoformat(),
                    "filled_at": (datetime.utcnow() - timedelta(days=1)).isoformat(),
                    "pnl": 124.80,
                    "pnl_pct": 4.44
                }
            ],
            "count": 3,
            "status": "simulated",
            "timestamp": datetime.utcnow().isoformat()
        }

    try:
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus

        # Map status string to enum
        status_map = {
            "open": QueryOrderStatus.OPEN,
            "closed": QueryOrderStatus.CLOSED,
            "all": QueryOrderStatus.ALL
        }
        query_status = status_map.get(status, QueryOrderStatus.ALL)

        # Get orders
        request = GetOrdersRequest(
            status=query_status,
            limit=limit,
            after=datetime.utcnow() - timedelta(days=days)
        )

        orders = alpaca_trader.client.get_orders(filter=request)

        order_list = []
        for order in orders:
            order_data = {
                "id": str(order.id),
                "symbol": order.symbol,
                "side": order.side.value if hasattr(order.side, 'value') else str(order.side),
                "qty": float(order.qty) if order.qty else 0,
                "filled_qty": float(order.filled_qty) if order.filled_qty else 0,
                "type": order.type.value if hasattr(order.type, 'value') else str(order.type),
                "status": order.status.value if hasattr(order.status, 'value') else str(order.status),
                "filled_avg_price": float(order.filled_avg_price) if order.filled_avg_price else None,
                "submitted_at": order.submitted_at.isoformat() if order.submitted_at else None,
                "filled_at": order.filled_at.isoformat() if order.filled_at else None,
                "expires_at": order.expires_at.isoformat() if getattr(order, "expires_at", None) else None,
                "limit_price": float(order.limit_price) if order.limit_price else None,
                "stop_price": float(order.stop_price) if order.stop_price else None,
            }
            order_list.append(order_data)

        # Newest first (Alpaca may return ascending); matches dashboard "Recent Orders"
        order_list.sort(
            key=lambda o: o.get("submitted_at") or "",
            reverse=True,
        )

        return {
            "orders": order_list,
            "count": len(order_list),
            "status": "connected",
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Error fetching orders: {e}")
        return {
            "orders": [],
            "count": 0,
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


@app.get("/api/portfolio/history")
async def get_portfolio_history(
    period: str = Query("1M", description="Period: 1D, 1W, 1M, 3M, 1A, all"),
    timeframe: str = Query("1D", description="Timeframe: 1Min, 5Min, 15Min, 1H, 1D")
):
    """Get portfolio value history from Alpaca."""
    if not alpaca_trader.client:
        return {"error": "No Alpaca connection", "data": []}

    try:
        from alpaca.trading.requests import GetPortfolioHistoryRequest

        req = GetPortfolioHistoryRequest(period=period, timeframe=timeframe)
        history = alpaca_trader.client.get_portfolio_history(req)

        # Convert to list of data points
        data_points = []
        for i, ts in enumerate(history.timestamp):
            data_points.append({
                "timestamp": ts,
                "date": datetime.fromtimestamp(ts).isoformat(),
                "equity": history.equity[i] if history.equity else 0,
                "profit_loss": history.profit_loss[i] if history.profit_loss else 0,
                "profit_loss_pct": (history.profit_loss_pct[i] * 100) if history.profit_loss_pct else 0,
            })

        # Calculate summary stats
        if data_points:
            start_equity = data_points[0]["equity"]
            end_equity = data_points[-1]["equity"]
            total_return = ((end_equity - start_equity) / start_equity * 100) if start_equity else 0
            max_equity = max(d["equity"] for d in data_points)
            min_equity = min(d["equity"] for d in data_points)
            max_drawdown = ((max_equity - min_equity) / max_equity * 100) if max_equity else 0

            # Find best and worst days
            best_day = max(data_points, key=lambda x: x["profit_loss_pct"])
            worst_day = min(data_points, key=lambda x: x["profit_loss_pct"])

            summary = {
                "start_equity": start_equity,
                "end_equity": end_equity,
                "total_return_pct": round(total_return, 2),
                "total_return_dollars": round(end_equity - start_equity, 2),
                "max_equity": max_equity,
                "min_equity": min_equity,
                "max_drawdown_pct": round(max_drawdown, 2),
                "best_day": {"date": best_day["date"], "pct": round(best_day["profit_loss_pct"], 2)},
                "worst_day": {"date": worst_day["date"], "pct": round(worst_day["profit_loss_pct"], 2)},
                "trading_days": len(data_points),
            }
        else:
            summary = {}

        return {
            "data": data_points,
            "summary": summary,
            "period": period,
            "timeframe": timeframe,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Error fetching portfolio history: {e}")
        return {
            "error": str(e),
            "data": [],
            "timestamp": datetime.utcnow().isoformat()
        }


@app.get("/api/trading/closed-trades")
async def get_closed_trades(
    limit: int = Query(50, description="Maximum trades to return"),
    days_back: int = Query(None, description="Filter trades to last N days (None = all time)")
):
    """Get closed trades with P&L from Alpaca order history."""
    try:
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus

        if not alpaca_trader.client:
            return {"trades": [], "count": 0, "summary": {"total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0, "total_pnl_pct": 0}, "timestamp": datetime.utcnow().isoformat()}

        # Calculate date range
        if days_back:
            after_date = datetime.utcnow() - timedelta(days=days_back)
        else:
            after_date = datetime.utcnow() - timedelta(days=30)  # Default to 30 days

        # Fetch filled orders from Alpaca
        request = GetOrdersRequest(
            status=QueryOrderStatus.CLOSED,
            after=after_date,
            limit=500  # Fetch more to find matching pairs
        )
        orders = alpaca_trader.client.get_orders(filter=request)

        # Group orders by symbol to match BUY/SELL pairs (round trips)
        symbol_orders = {}
        for order in orders:
            if order.status.value != "filled":
                continue
            symbol = order.symbol
            if symbol not in symbol_orders:
                symbol_orders[symbol] = {"buys": [], "sells": []}

            order_data = {
                "id": str(order.id),
                "filled_at": order.filled_at.isoformat() if order.filled_at else None,
                "filled_qty": float(order.filled_qty) if order.filled_qty else 0,
                "filled_avg_price": float(order.filled_avg_price) if order.filled_avg_price else 0,
            }

            if order.side.value == "buy":
                symbol_orders[symbol]["buys"].append(order_data)
            else:
                symbol_orders[symbol]["sells"].append(order_data)

        # Match BUY/SELL pairs to create closed trades (round trips)
        closed_trades = []
        for symbol, orders_dict in symbol_orders.items():
            buys = sorted(orders_dict["buys"], key=lambda x: x["filled_at"] or "")
            sells = sorted(orders_dict["sells"], key=lambda x: x["filled_at"] or "")

            # Simple matching: pair oldest buy with oldest sell
            while buys and sells:
                buy = buys.pop(0)
                sell = sells.pop(0)

                entry_price = buy["filled_avg_price"]
                exit_price = sell["filled_avg_price"]
                qty = min(buy["filled_qty"], sell["filled_qty"])

                if entry_price > 0 and exit_price > 0:
                    pnl_pct = ((exit_price - entry_price) / entry_price) * 100
                    pnl_dollars = (exit_price - entry_price) * qty

                    closed_trades.append({
                        "id": sell["id"],
                        "symbol": symbol,
                        "side": "sell",
                        "timestamp": sell["filled_at"],
                        "entry_price": round(entry_price, 2),
                        "exit_price": round(exit_price, 2),
                        "quantity": qty,
                        "pnl_pct": round(pnl_pct, 2),
                        "pnl_dollars": round(pnl_dollars, 2),
                        "reason": "Round trip",
                        "status": "closed"
                    })

        # Sort by timestamp descending (most recent first)
        closed_trades.sort(key=lambda x: x.get("timestamp") or "", reverse=True)

        # Calculate summary stats
        total_pnl_pct = sum(t.get("pnl_pct", 0) for t in closed_trades)
        total_pnl_dollars = sum(t.get("pnl_dollars", 0) for t in closed_trades)
        wins = len([t for t in closed_trades if (t.get("pnl_pct") or 0) > 0])
        losses = len([t for t in closed_trades if (t.get("pnl_pct") or 0) < 0])
        win_rate = (wins / len(closed_trades) * 100) if closed_trades else 0

        return {
            "trades": closed_trades[:limit],
            "count": len(closed_trades),
            "summary": {
                "total_trades": len(closed_trades),
                "wins": wins,
                "losses": losses,
                "win_rate": round(win_rate, 1),
                "total_pnl_pct": round(total_pnl_pct, 2),
                "total_pnl_dollars": round(total_pnl_dollars, 2)
            },
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Error fetching closed trades: {e}")
        import traceback
        traceback.print_exc()
        return {"trades": [], "count": 0, "summary": {"total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0, "total_pnl_pct": 0}, "error": str(e), "timestamp": datetime.utcnow().isoformat()}


@app.delete("/api/trading/orders")
async def cancel_all_orders():
    """Cancel all open orders."""
    if not alpaca_trader.client:
        return {"status": "simulated", "message": "No Alpaca connection"}

    try:
        alpaca_trader.client.cancel_orders()
        return {
            "status": "success",
            "message": "All open orders cancelled",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error cancelling orders: {e}")
        return {
            "status": "error",
            "message": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


@app.delete("/api/trading/orders/{order_id}")
async def cancel_order(order_id: str):
    """Cancel a specific order by ID."""
    if not alpaca_trader.client:
        return {"status": "simulated", "message": "No Alpaca connection"}

    try:
        alpaca_trader.client.cancel_order_by_id(order_id)
        return {
            "status": "success",
            "message": f"Order {order_id} cancelled",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error cancelling order {order_id}: {e}")
        return {
            "status": "error",
            "message": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


# Activity log storage - persisted to file
ACTIVITY_LOG_FILE = Path(__file__).parent.parent / "data" / "activity_log.json"
_activity_log = []

def _load_activity_log():
    """Load activity log from file on startup."""
    global _activity_log
    try:
        ACTIVITY_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        if ACTIVITY_LOG_FILE.exists():
            with open(ACTIVITY_LOG_FILE, 'r') as f:
                _activity_log = json.load(f)
            logger.info(f"Loaded {len(_activity_log)} activity log entries from disk")
    except Exception as e:
        logger.error(f"Failed to load activity log: {e}")
        _activity_log = []

def _save_activity_log():
    """Save activity log to file."""
    try:
        ACTIVITY_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(ACTIVITY_LOG_FILE, 'w') as f:
            json.dump(_activity_log, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save activity log: {e}")

# Load on module import
_load_activity_log()


def log_activity(log_type: str, ticker: str, action: str, details: dict):
    """Add an entry to the activity log and persist to disk."""
    import uuid
    entry = {
        "id": str(uuid.uuid4())[:8],
        "timestamp": datetime.utcnow().isoformat(),
        "type": log_type,
        "ticker": ticker,
        "action": action,
        "details": details
    }
    _activity_log.insert(0, entry)  # Most recent first
    _save_activity_log()  # Persist immediately


@app.get("/api/trading/activity-log")
async def get_activity_log(limit: int = Query(50, description="Max entries to return")):
    """Get trading activity log (entries, exits, signals)."""
    logs = _activity_log[:limit]
    return {
        "logs": logs,
        "total": len(_activity_log),
        "filtered": len(logs),
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/api/debug/scoring-snapshots")
async def get_scoring_snapshots(
    ticker: str = Query(None, description="Filter by ticker"),
    date: str = Query(None, description="Filter by date (YYYY-MM-DD)"),
    limit: int = Query(50, description="Max rows"),
):
    """Browse stored scoring snapshots for backtesting analysis."""
    try:
        conn = sqlite3.connect(_scoring_db_path)
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM scoring_snapshots WHERE 1=1"
        params = []
        if ticker:
            query += " AND ticker = ?"
            params.append(ticker.upper())
        if date:
            query += " AND timestamp LIKE ?"
            params.append(f"{date}%")
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        conn.close()
        results = []
        for row in rows:
            results.append({
                "id": row["id"],
                "ticker": row["ticker"],
                "timestamp": row["timestamp"],
                "mode": row["mode"],
                "score": row["score"],
                "shrinkage": json.loads(row["shrinkage"]) if row["shrinkage"] else None,
                "components": json.loads(row["components"]) if row["components"] else None,
                "news_count": len(json.loads(row["news_items"])) if row["news_items"] else 0,
                "earnings_count": len(json.loads(row["earnings_items"])) if row["earnings_items"] else 0,
                "ratings_count": len(json.loads(row["ratings_items"])) if row["ratings_items"] else 0,
            })
        return {"snapshots": results, "total": len(results)}
    except Exception as e:
        return {"error": str(e), "snapshots": []}


@app.get("/api/debug/replay-scoring")
async def replay_scoring(
    ticker: str = Query(..., description="Ticker to replay"),
    snapshot_id: int = Query(None, description="Specific snapshot ID"),
    date: str = Query(None, description="Date to replay (YYYY-MM-DD, uses latest snapshot)"),
):
    """Replay keyword scoring on a stored snapshot with current config. Compare old vs new score."""
    try:
        conn = sqlite3.connect(_scoring_db_path)
        conn.row_factory = sqlite3.Row
        if snapshot_id:
            row = conn.execute("SELECT * FROM scoring_snapshots WHERE id = ?", (snapshot_id,)).fetchone()
        elif date:
            row = conn.execute(
                "SELECT * FROM scoring_snapshots WHERE ticker = ? AND timestamp LIKE ? ORDER BY timestamp DESC LIMIT 1",
                (ticker.upper(), f"{date}%"),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM scoring_snapshots WHERE ticker = ? ORDER BY timestamp DESC LIMIT 1",
                (ticker.upper(),),
            ).fetchone()
        conn.close()

        if not row:
            raise HTTPException(status_code=404, detail="No snapshot found")

        # Parse stored data
        news_items = json.loads(row["news_items"]) if row["news_items"] else []
        earnings_items = json.loads(row["earnings_items"]) if row["earnings_items"] else []
        ratings_items = json.loads(row["ratings_items"]) if row["ratings_items"] else []
        original_score = row["score"]
        original_shrinkage = json.loads(row["shrinkage"]) if row["shrinkage"] else {}

        # Re-run keyword scoring with current config
        components = []
        net_signals = 0
        news_score = 50
        if news_items:
            positive_signals = 0
            negative_signals = 0
            seen_themes = set()
            for item in news_items:
                title = item.get("title", "").lower()
                theme_words = [w for w in ["upgrade", "downgrade", "beat", "miss", "earnings", "rating"] if w in title]
                theme_key = "_".join(sorted(theme_words)) if theme_words else title[:30]
                if theme_key in seen_themes:
                    continue
                seen_themes.add(theme_key)
                if any(word in title for word in ["upgrade", "beat", "beats", "surge", "rally", "soar",
                                                  "jump", "bullish", "outperform", "record", "breakthrough"]):
                    positive_signals += 1
                elif any(word in title for word in ["downgrade", "miss", "misses", "plunge", "crash",
                                                    "bearish", "underperform", "bankruptcy", "investigation"]):
                    negative_signals += 1
                elif any(word in title for word in ["gain", "rise", "strong", "growth"]):
                    positive_signals += 0.5
                elif any(word in title for word in ["fall", "drop", "loss", "weak", "concern", "decline"]):
                    negative_signals += 0.5
            net_signals = positive_signals - negative_signals
            if net_signals > 0:
                news_score = 50 + min(35, 12 * (net_signals ** 0.7))
            elif net_signals < 0:
                news_score = 50 - min(35, 12 * (abs(net_signals) ** 0.7))
            components.append(("news", news_score, 0.25))

        earnings_score = 50
        if earnings_items:
            earnings_signals = []
            for i, earning in enumerate(earnings_items):
                if earning.get("estimated_eps") and earning.get("actual_eps"):
                    try:
                        estimated = float(earning["estimated_eps"])
                        actual = float(earning["actual_eps"])
                        if estimated != 0:
                            surprise_pct = (actual - estimated) / abs(estimated)
                            recency_weight = 1.0 / (2 ** i)
                            earnings_signals.append((surprise_pct, recency_weight))
                    except (ValueError, TypeError):
                        pass
            if earnings_signals:
                total_weight = sum(w for _, w in earnings_signals)
                weighted_surprise = sum(s * w for s, w in earnings_signals) / total_weight
                adjustment = max(-25, min(25, weighted_surprise * 150))
                earnings_score = 50 + adjustment
                components.append(("earnings", earnings_score, 0.30))

        ratings_score = 50
        if ratings_items:
            upgrades = sum(1 for r in ratings_items if "upgrade" in r.get("rating_action", "").lower())
            downgrades = sum(1 for r in ratings_items if "downgrade" in r.get("rating_action", "").lower())
            if upgrades or downgrades:
                net = upgrades - downgrades
                if net > 0:
                    ratings_score = 50 + min(30, 10 * net)
                elif net < 0:
                    ratings_score = 50 - min(30, 10 * abs(net))
                components.append(("ratings", ratings_score, 0.25))

        # Shrinkage with current config
        replay_score = 50
        replay_shrinkage = {"mode": "keywords", "final_shrinkage": 0.0}
        if components:
            total_weight = sum(w for _, _, w in components)
            replay_score = sum(s * w for _, s, w in components) / total_weight
            categories_used = [cat for cat, _, _ in components]
            quality_map = {}
            shrinkage_per_cat = {}
            for cat, _, w in components:
                q = _compute_category_quality(cat, news_items=news_items, earnings_items=earnings_items,
                                              ratings_items=ratings_items, net_signals=net_signals)
                quality_map[cat] = round(q, 3)
                cfg = SHRINKAGE_CONFIG[cat]
                shrinkage_per_cat[cat] = cfg["max_shrinkage"] - q * (cfg["max_shrinkage"] - cfg["min_shrinkage"])
            blended_shrinkage = sum(shrinkage_per_cat[cat] * w for cat, _, w in components) / total_weight
            n_sources = min(len(components), 4)
            multi_factor = MULTI_SOURCE_SHRINKAGE.get(n_sources, 0.0)
            final_shrinkage = blended_shrinkage * multi_factor
            replay_score = 50 + (replay_score - 50) * (1 - final_shrinkage)
            replay_shrinkage = {
                "mode": "keywords", "categories_used": categories_used,
                "quality": quality_map, "final_shrinkage": round(final_shrinkage, 4),
            }

        replay_score = round(max(5, min(95, replay_score)), 1)

        return {
            "ticker": row["ticker"],
            "snapshot_timestamp": row["timestamp"],
            "original_mode": row["mode"],
            "original_score": original_score,
            "original_shrinkage": original_shrinkage,
            "replay_score": replay_score,
            "replay_shrinkage": replay_shrinkage,
            "delta": round(replay_score - original_score, 1),
            "data_summary": {
                "news_count": len(news_items),
                "earnings_count": len(earnings_items),
                "ratings_count": len(ratings_items),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============= POSITION MANAGEMENT WITH AUTO-EXIT =============

# Global position tracking for momentum monitoring
position_momentum = {}
exit_signals = {}

@app.post("/api/trading/monitor-positions")
async def monitor_positions_for_exit():
    """Monitor all positions for exit conditions (momentum loss, targets hit)."""
    positions = alpaca_trader.get_positions()

    exit_actions = []

    for position in positions:
        ticker = position["symbol"]
        entry_price = position["entry"]
        current_price = position["current"]
        pnl_pct = position["pnl_pct"]

        # Get current momentum
        momentum_data = await get_momentum_analysis(ticker)
        current_momentum = momentum_data["momentum_score"]

        # Track momentum history
        if ticker not in position_momentum:
            position_momentum[ticker] = {
                "peak_momentum": current_momentum,
                "entry_momentum": current_momentum,
                "momentum_history": [current_momentum]
            }
        else:
            position_momentum[ticker]["momentum_history"].append(current_momentum)
            position_momentum[ticker]["peak_momentum"] = max(
                position_momentum[ticker]["peak_momentum"],
                current_momentum
            )

        # Check exit conditions
        should_exit = False
        exit_reason = ""

        # 1. Momentum loss (drops below 40% from peak or below 30 absolute)
        momentum_loss = position_momentum[ticker]["peak_momentum"] - current_momentum
        if momentum_loss > 40 or current_momentum < 30:
            should_exit = True
            exit_reason = f"Momentum lost (current: {current_momentum}, peak: {position_momentum[ticker]['peak_momentum']})"

        # 2. Stop loss hit (2% loss)
        elif pnl_pct < -2:
            should_exit = True
            exit_reason = f"Stop loss hit ({pnl_pct:.2f}%)"

        # 3. Take profit hit (5% gain for fast momentum, 10% for normal)
        elif current_momentum > 70 and pnl_pct > 5:  # Fast momentum trade
            should_exit = True
            exit_reason = f"Fast momentum target hit (+{pnl_pct:.2f}%)"
        elif pnl_pct > 10:  # Normal take profit
            should_exit = True
            exit_reason = f"Take profit hit (+{pnl_pct:.2f}%)"

        # 4. Trailing stop for winners (protect 50% of gains after 3% profit)
        elif pnl_pct > 3:
            # Use trailing stop - exit if we lose 50% of gains
            max_pnl = max(position_momentum[ticker].get("max_pnl", pnl_pct), pnl_pct)
            position_momentum[ticker]["max_pnl"] = max_pnl

            if pnl_pct < (max_pnl * 0.5):
                should_exit = True
                exit_reason = f"Trailing stop hit (peak: +{max_pnl:.2f}%, current: +{pnl_pct:.2f}%)"

        if should_exit:
            exit_actions.append({
                "ticker": ticker,
                "action": "CLOSE",
                "reason": exit_reason,
                "current_price": current_price,
                "pnl_pct": pnl_pct,
                "momentum": current_momentum,
                "auto_execute": True
            })

            # Store exit signal for WebSocket broadcast
            exit_signals[ticker] = {
                "timestamp": datetime.utcnow().isoformat(),
                "reason": exit_reason,
                "pnl_pct": pnl_pct
            }

    # Execute exits if any
    executed_exits = []
    for exit_action in exit_actions:
        if exit_action["auto_execute"]:
            result = alpaca_trader.close_position(exit_action["ticker"])
            executed_exits.append({
                **exit_action,
                "execution_result": result
            })

            # Log the automatic exit
            log_activity(
                log_type="EXIT",
                ticker=exit_action["ticker"],
                action="SELL",
                details={
                    "reason": exit_action["reason"],
                    "pnl_pct": exit_action["pnl_pct"],
                    "momentum": exit_action["momentum"],
                    "price": exit_action["current_price"],
                    "auto": True
                }
            )

            # Clean up tracking
            if exit_action["ticker"] in position_momentum:
                del position_momentum[exit_action["ticker"]]

    return {
        "monitored_positions": len(positions),
        "exit_signals": exit_actions,
        "executed_exits": executed_exits,
        "momentum_tracking": {
            ticker: {
                "current": data["momentum_history"][-1] if data["momentum_history"] else 0,
                "peak": data["peak_momentum"],
                "entry": data["entry_momentum"]
            }
            for ticker, data in position_momentum.items()
        },
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/api/trading/position-momentum/{ticker}")
async def get_position_momentum(ticker: str):
    """Get momentum tracking for a specific position."""
    ticker = ticker.upper()

    if ticker not in position_momentum:
        return {
            "error": f"No position tracking for {ticker}",
            "status": "not_found"
        }

    tracking = position_momentum[ticker]

    # Get current momentum
    momentum_data = await get_momentum_analysis(ticker)

    return {
        "ticker": ticker,
        "current_momentum": momentum_data["momentum_score"],
        "peak_momentum": tracking["peak_momentum"],
        "entry_momentum": tracking["entry_momentum"],
        "momentum_change": momentum_data["momentum_score"] - tracking["entry_momentum"],
        "momentum_from_peak": momentum_data["momentum_score"] - tracking["peak_momentum"],
        "history": tracking["momentum_history"][-20:],  # Last 20 data points
        "exit_signal": exit_signals.get(ticker),
        "recommendation": "HOLD" if momentum_data["momentum_score"] > 40 else "CONSIDER_EXIT",
        "timestamp": datetime.utcnow().isoformat()
    }

# Background task for continuous position monitoring
async def auto_monitor_positions():
    """Background task that monitors positions every 30 seconds for exits."""
    while True:
        try:
            if is_market_open():
                # Only monitor if we have positions (avoid unnecessary API calls)
                positions = alpaca_trader.get_positions() if alpaca_trader else []
                if positions:
                    # Check for automatic exits (stop-loss, take-profit, trailing, momentum)
                    exits = await check_position_exits()
                    if exits:
                        logger.info(f"🚨 AUTO-EXITS TRIGGERED: {len(exits)} positions closed")
                        for exit in exits:
                            logger.info(f"   - {exit['ticker']}: {exit['reason']} (P&L: {exit['pnl_pct']:.2f}%)")
                    else:
                        logger.debug(f"Position monitoring: {len(positions)} positions, no exits triggered")
            await asyncio.sleep(30)  # Check every 30 seconds for day trading
        except Exception as e:
            logger.error(f"Error in position monitoring: {e}")
            await asyncio.sleep(30)

# Start position monitoring on startup (integrated into lifespan)

# ============= RISK MANAGEMENT HELPERS =============

def _check_daily_loss_limit() -> bool:
    """Check if daily loss limit has been hit. Returns True if trading should stop."""
    global _daily_loss_limit_hit
    try:
        account = alpaca_trader.get_account_status() if alpaca_trader else None
        if not account or account.get("status") == "error":
            return False
        equity = float(account.get("equity", 0))
        last_equity = float(account.get("last_equity", 0))
        if last_equity <= 0:
            return False
        day_pl_pct = (equity - last_equity) / last_equity
        if day_pl_pct <= DAILY_LOSS_LIMIT_PCT:
            if not _daily_loss_limit_hit:
                logger.warning(
                    f"🛑 [RISK] Daily loss limit hit! P&L: {day_pl_pct*100:.2f}% "
                    f"(${equity - last_equity:,.2f}). Stopping all new trades."
                )
                _daily_loss_limit_hit = True
            return True
        # Reset flag if we recover above the limit
        if _daily_loss_limit_hit and day_pl_pct > DAILY_LOSS_LIMIT_PCT:
            logger.info(f"🟢 [RISK] P&L recovered to {day_pl_pct*100:.2f}%, re-enabling trades")
            _daily_loss_limit_hit = False
        return False
    except Exception as e:
        logger.error(f"[RISK] Error checking daily loss limit: {e}")
        return False


def _check_spy_trend():
    """Check SPY trend. Returns (should_skip, spy_change_pct)."""
    try:
        if not alpaca_trader or not alpaca_trader.data_client:
            return False, 0.0
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame
        # Get today's SPY bar
        request = StockBarsRequest(
            symbol_or_symbols="SPY",
            timeframe=TimeFrame.Day,
            limit=1,
        )
        bars = alpaca_trader.data_client.get_stock_bars(request)
        spy_bars = bars.get("SPY", []) if isinstance(bars, dict) else getattr(bars, 'data', {}).get("SPY", [])
        if not spy_bars:
            # Fallback: use latest quote vs previous close
            quote = alpaca_trader.get_quote("SPY")
            return False, 0.0
        bar = spy_bars[-1] if isinstance(spy_bars, list) else list(spy_bars)[-1]
        open_price = float(bar.open)
        close_price = float(bar.close)
        change_pct = (close_price - open_price) / open_price
        should_skip = change_pct < SPY_TREND_THRESHOLD
        if should_skip:
            logger.info(f"🔴 [RISK] SPY down {change_pct*100:.2f}% today - skipping new buys")
        return should_skip, change_pct
    except Exception as e:
        logger.error(f"[RISK] Error checking SPY trend: {e}")
        return False, 0.0


# ============= PRE-MARKET GAP DETECTION =============

def _get_premarket_gaps_sync(watchlist: list, min_gap_pct: float = 3.0) -> list:
    """Fetch Alpaca snapshots for watchlist tickers, return gap movers. Sync — call via asyncio.to_thread()."""
    if not alpaca_trader or not alpaca_trader.data_client:
        return []
    try:
        from alpaca.data.requests import StockSnapshotRequest
        request = StockSnapshotRequest(symbol_or_symbols=watchlist)
        snapshots = alpaca_trader.data_client.get_stock_snapshot(request)
    except Exception as e:
        logger.error(f"[PRE-MARKET] Snapshot fetch failed: {e}")
        return []

    gappers = []
    for symbol, snap in snapshots.items():
        try:
            prev_close = float(snap.previous_daily_bar.close)
            current = float(snap.latest_trade.price)
            if prev_close <= 0 or current < 25:  # Min $25 price rule
                continue
            gap_pct = (current - prev_close) / prev_close * 100
            if abs(gap_pct) >= min_gap_pct:
                gappers.append({
                    "ticker": symbol,
                    "gap_pct": round(gap_pct, 2),
                    "prev_close": prev_close,
                    "current_price": current,
                    "source": "gap_scan",
                })
        except Exception:
            continue
    gappers.sort(key=lambda x: abs(x["gap_pct"]), reverse=True)
    return gappers[:20]


# ============= NEWS-PUSH: IMMEDIATE REACTION TO BREAKING NEWS =============

# Seen article IDs — prevents re-processing the same headline
_news_push_seen: set[str] = set()
_NEWS_PUSH_POLL_SECONDS = 15        # How often to check for new articles
_NEWS_PUSH_SEEN_MAX = 500           # Prune after this many stored IDs
_NEWS_PUSH_MAX_TRADES_PER_CYCLE = 1 # Don't fire-hose; best signal only


def _extract_tickers_from_article(article: dict) -> set[str]:
    """Pull ticker symbols out of a single Benzinga article."""
    tickers = set()
    for stock in (article.get("stocks") or []):
        sym = stock.get("symbol") or stock.get("ticker") or stock.get("name")
        if sym:
            tickers.add(sym.upper())
    for sym in (article.get("tickers") or []):
        if isinstance(sym, str):
            tickers.add(sym.upper())
    for sec in (article.get("securities") or []):
        sym = sec.get("symbol") or sec.get("ticker")
        if sym:
            tickers.add(sym.upper())
    return tickers


async def news_push_loop():
    """Fast-polling news monitor.  When a *new* article mentions a watchlist
    ticker, immediately run the full analysis → trade pipeline instead of
    waiting for the next scan cycle.

    This is the bridge between "polling every 26-60 s" and "react in seconds."
    """
    global _news_push_seen

    # Let the main loop start first so startup isn't contended
    await asyncio.sleep(8)
    logger.info("[NEWS-PUSH] News watcher started")

    while True:
        try:
            from zoneinfo import ZoneInfo
            now_et = datetime.now(ZoneInfo("America/New_York"))

            # Only run during market hours when auto-trade is on
            if not _auto_trade_enabled or not is_market_open():
                await asyncio.sleep(60)
                continue

            # Skip near close — same rule as the main loop
            if now_et.hour == 15 and now_et.minute >= 30:
                await asyncio.sleep(60)
                continue

            if not benzinga_client:
                await asyncio.sleep(60)
                continue

            # ---- Fetch latest articles (all tickers) ----
            raw = await benzinga_client.get_news(limit=15)
            articles = raw.get("results", []) if isinstance(raw, dict) else []

            # Detect new articles we haven't processed
            new_articles: list[dict] = []
            for art in articles:
                art_id = str(
                    art.get("id")
                    or art.get("url")
                    or (art.get("title") or "")[:60]
                )
                if art_id and art_id not in _news_push_seen:
                    _news_push_seen.add(art_id)
                    new_articles.append(art)

            # Prune memory
            if len(_news_push_seen) > _NEWS_PUSH_SEEN_MAX:
                _news_push_seen = set(list(_news_push_seen)[-250:])

            if not new_articles:
                await asyncio.sleep(_NEWS_PUSH_POLL_SECONDS)
                continue

            # ---- Match against watchlist ----
            settings = get_settings()
            watchlist = set(t.upper() for t in settings.watchlist)
            hot_tickers: dict[str, dict] = {}  # ticker -> article (keep first match)
            for art in new_articles:
                for sym in _extract_tickers_from_article(art):
                    if sym in watchlist and sym not in _EXCLUDED_TICKERS and sym not in hot_tickers:
                        hot_tickers[sym] = art

            if not hot_tickers:
                await asyncio.sleep(_NEWS_PUSH_POLL_SECONDS)
                continue

            logger.info(
                f"[NEWS-PUSH] New articles mention watchlist tickers: "
                f"{', '.join(hot_tickers.keys())}"
            )

            # ---- Risk checks (same as main loop) ----
            if _check_daily_loss_limit():
                await asyncio.sleep(_NEWS_PUSH_POLL_SECONDS)
                continue
            spy_skip, _ = _check_spy_trend()
            if spy_skip:
                await asyncio.sleep(_NEWS_PUSH_POLL_SECONDS)
                continue

            positions = alpaca_trader.get_positions() if alpaca_trader else []
            owned = {p["symbol"] for p in positions}

            # ---- Analyze hot tickers concurrently ----
            sem = asyncio.Semaphore(4)

            async def _analyze_one(ticker: str) -> Optional[dict]:
                if ticker in owned:
                    return None
                cd = _ticker_cooldowns.get(ticker)
                if cd and datetime.utcnow() < cd:
                    return None
                async with sem:
                    sig = await _analyze_ticker_for_signal(ticker)
                if not sig:
                    return None
                sig["source"] = "news_push"
                return sig

            results = await asyncio.gather(
                *[_analyze_one(t) for t in hot_tickers],
                return_exceptions=True,
            )

            # Filter to passing signals
            candidates = []
            for r in results:
                if r is None or isinstance(r, Exception):
                    continue
                gate_ok, gate_reason = _passes_live_auto_trade_gate(r, owned)
                if gate_ok:
                    candidates.append(r)
                else:
                    _log_trade_gate(
                        r["ticker"],
                        float(r.get("combined_score", 0)),
                        False,
                        gate_reason,
                        source="news_push",
                    )

            if not candidates:
                await asyncio.sleep(_NEWS_PUSH_POLL_SECONDS)
                continue

            # Sort by timing-first ranking (same as main loop)
            candidates.sort(key=_auto_trade_signal_rank, reverse=True)

            # ---- Execute best signal ----
            for signal in candidates[:_NEWS_PUSH_MAX_TRADES_PER_CYCLE]:
                ticker = signal["ticker"]
                trade_score = float(signal.get("combined_score", 0))

                _log_trade_gate(ticker, trade_score, True, "news_push executing", source="news_push")
                logger.info(
                    f"[NEWS-PUSH] Executing BUY {ticker} "
                    f"score={trade_score:.1f} timing={signal.get('entry_timing_state', '?')}"
                )

                result = alpaca_trader.execute_trade(signal)

                # Register with position manager
                pm = get_position_manager()
                if pm and result and result.get("status") == "executed":
                    pm.register_entry(
                        symbol=ticker,
                        entry_price=signal.get("entry_price", result.get("entry_price", 0)),
                        quantity=result.get("quantity", 1),
                        thesis=signal.get("reasoning", "")[:500],
                        stop_loss=result.get("stop_loss"),
                        take_profit=result.get("take_profit"),
                        atr=signal.get("atr"),
                        score_at_entry=signal.get("effective_score", signal.get("combined_score")),
                        rvol_at_entry=signal.get("relative_volume"),
                        regime_at_entry=signal.get("regime_at_entry") or signal.get("technical_regime"),
                        source="news_push",
                    )

                log_activity(
                    log_type="AUTO_TRADE",
                    ticker=ticker,
                    action="BUY",
                    details={
                        "price": signal.get("entry_price"),
                        "quantity": result.get("quantity") if result else None,
                        "score": trade_score,
                        "effective_score": signal.get("effective_score", trade_score),
                        "reasoning": (signal.get("reasoning") or "")[:200],
                        "order_id": result.get("order_id") if result else None,
                        "status": result.get("status") if result else None,
                        "source": "news_push",
                        "timing_state": signal.get("entry_timing_state"),
                        "size_multiplier": signal.get("position_size_multiplier", 1.0),
                        "auto": True,
                    },
                )

                _ticker_cooldowns[ticker] = datetime.utcnow() + timedelta(minutes=TICKER_COOLDOWN_MINUTES)
                owned.add(ticker)
                _recent_trade_decisions[ticker] = {
                    "status": "executed",
                    "reason": f"News push, score {trade_score:.0f}",
                    "timestamp": datetime.utcnow().isoformat(),
                }
                logger.info(f"[NEWS-PUSH] Trade executed: {ticker} -> {result}")

            await asyncio.sleep(_NEWS_PUSH_POLL_SECONDS)

        except Exception as e:
            logger.error(f"[NEWS-PUSH] Error: {e}", exc_info=True)
            await asyncio.sleep(30)


# ============= AUTO-TRADE BACKGROUND LOOP =============

async def auto_trade_loop():
    """Background task that automatically scans and trades when enabled."""
    global _auto_trade_enabled, _daily_loss_limit_hit, _premarket_ready_list, _premarket_built_today, _bell_rush_results, _bell_rush_date, _last_market_state

    while True:
        try:
            from zoneinfo import ZoneInfo
            now_et = datetime.now(ZoneInfo("America/New_York"))
            current_state = get_market_status()
            today_str = now_et.strftime("%Y-%m-%d")

            # === PRE-MARKET READY LIST (9:15 AM ET, once per day) ===
            if (_auto_trade_enabled
                and current_state == "pre_market"
                and now_et.hour == 9 and now_et.minute >= 15
                and _premarket_built_today != today_str):

                _premarket_built_today = today_str
                # Clear previous day's bell rush results
                if _bell_rush_date != today_str:
                    _bell_rush_results = []
                    _bell_rush_date = today_str
                logger.info("[PRE-MARKET] Building ready list...")

                try:
                    # 1. News-based scan (keyword pass; LLM available from 9:00 AM)
                    scan_result = await scan_watchlist()
                    trending_result = await scan_trending()

                    news_candidates = {}
                    for r in scan_result.get("results", []):
                        if r["score"] >= 65:
                            news_candidates[r["ticker"]] = r
                    for tr in trending_result.get("results", []):
                        if tr["score"] >= 65 and tr["ticker"] not in news_candidates:
                            news_candidates[tr["ticker"]] = tr

                    # 2. Gap detection via Alpaca snapshots
                    settings = get_settings()
                    gappers = await asyncio.to_thread(_get_premarket_gaps_sync, settings.watchlist)
                    for g in gappers:
                        ticker = g["ticker"]
                        if ticker in news_candidates:
                            news_candidates[ticker]["gap_pct"] = g["gap_pct"]
                            news_candidates[ticker]["source"] = "news+gap"
                        else:
                            news_candidates[ticker] = {
                                "ticker": ticker, "score": 50, "gap_pct": g["gap_pct"],
                                "source": "gap_scan", "sentiment": "unknown",
                            }

                    # 3. Sort: news+gap > gap-only (by gap%) > news-only (by score)
                    all_candidates = list(news_candidates.values())
                    all_candidates.sort(key=lambda x: (
                        x.get("source") == "news+gap",
                        abs(x.get("gap_pct", 0)),
                        x.get("score", 0),
                    ), reverse=True)

                    _premarket_ready_list = all_candidates[:30]
                    logger.info(f"[PRE-MARKET] Ready list: {len(_premarket_ready_list)} tickers")
                    for c in _premarket_ready_list[:10]:
                        gap_str = f" gap={c.get('gap_pct')}%" if c.get("gap_pct") else ""
                        logger.info(f"  {c['ticker']}: kw={c['score']:.0f}{gap_str} ({c.get('source', 'news')})")

                except Exception as e:
                    logger.error(f"[PRE-MARKET] Error building ready list: {e}")

            # === BELL RUSH: Market just opened ===
            if (current_state == "open" and _last_market_state != "open"
                and _premarket_ready_list and _auto_trade_enabled):

                logger.info(f"[BELL-RUSH] Market opened! Scoring {len(_premarket_ready_list)} pre-screened tickers...")

                try:
                    settings = get_settings()
                    min_score = float(settings.TRADING_MIN_SIGNAL_SCORE)
                    positions = alpaca_trader.get_positions() if alpaca_trader else []
                    owned = {p["symbol"] for p in positions}

                    rush_sem = asyncio.Semaphore(5)

                    async def rush_score(candidate):
                        async with rush_sem:
                            ticker = candidate["ticker"]
                            if ticker in owned:
                                return None
                            cooldown_until = _ticker_cooldowns.get(ticker)
                            if cooldown_until and datetime.utcnow() < cooldown_until:
                                return None
                            try:
                                llm_data = await get_sentiment(ticker, use_llm=True)
                                if llm_data["score"] >= min_score and llm_data.get("llm_enhanced"):
                                    return {
                                        "ticker": ticker, "score": llm_data["score"],
                                        "gap_pct": candidate.get("gap_pct"),
                                        "source": candidate.get("source", "news"),
                                    }
                            except Exception as e:
                                logger.warning(f"[BELL-RUSH] Score failed for {ticker}: {e}")
                            return None

                    rush_results = await asyncio.gather(*[rush_score(c) for c in _premarket_ready_list])
                    rush_buys = [r for r in rush_results if r is not None]
                    rush_buys.sort(key=lambda x: x["score"], reverse=True)

                    for buy in rush_buys:
                        ticker = buy["ticker"]
                        trade_score = buy["score"]
                        logger.info(f"[BELL-RUSH] BUY signal: {ticker} score={trade_score:.1f} gap={buy.get('gap_pct', 'N/A')}%")

                        # Get full signal data — respect the trade plan's action decision
                        signal = await _analyze_ticker_for_signal(ticker)
                        if not signal:
                            continue
                        # Use the higher of LLM score vs trade plan score (bell rush already LLM-scored)
                        if trade_score > float(signal.get("combined_score", 0)):
                            signal["combined_score"] = trade_score
                        # Only override action if trade plan also agrees or LLM score is high enough
                        if signal.get("action") != "BUY" and trade_score < 75:
                            logger.info(f"[BELL-RUSH] {ticker} trade plan says {signal.get('action')}, LLM={trade_score:.1f} — skipping")
                            continue
                        signal["action"] = "BUY"
                        signal["llm_enhanced"] = True
                        signal["source"] = f"bell_rush:{buy.get('source', 'news')}"

                        gate_ok, gate_reason = _passes_live_auto_trade_gate(signal, owned)
                        if not gate_ok:
                            _log_trade_gate(ticker, trade_score, False, gate_reason, source="bell_rush")
                            _recent_trade_decisions[ticker] = {"status": "blocked", "reason": gate_reason, "timestamp": datetime.utcnow().isoformat()}
                            continue

                        # For 90+ scores, free capital
                        if trade_score >= 90:
                            account = alpaca_trader.get_account_status()
                            acct_equity = float(account.get("equity", 0)) if account else 0
                            entry_price = float(signal.get("entry_price") or signal.get("price", 0))
                            if acct_equity > 0 and entry_price > 0:
                                await _free_capital_for_excellent_signal(ticker, entry_price, acct_equity)

                        result = alpaca_trader.execute_trade(signal)

                        pm = get_position_manager()
                        if pm and result and result.get("status") == "executed":
                            pm.register_entry(
                                symbol=ticker,
                                entry_price=signal.get("entry_price", result.get("entry_price", 0)),
                                quantity=result.get("quantity", 1),
                                thesis=signal.get("reasoning", "")[:500],
                                stop_loss=result.get("stop_loss"),
                                take_profit=result.get("take_profit"),
                                atr=signal.get("atr"),
                                score_at_entry=signal.get("effective_score", signal.get("combined_score")),
                                rvol_at_entry=signal.get("relative_volume"),
                                regime_at_entry=signal.get("regime_at_entry") or signal.get("technical_regime"),
                                source=signal.get("source"),
                            )

                        log_activity(
                            log_type="AUTO_TRADE",
                            ticker=ticker,
                            action="BUY",
                            details={
                                "price": signal.get("entry_price"),
                                "quantity": result.get("quantity") if result else None,
                                "score": trade_score,
                                "effective_score": signal.get("effective_score", trade_score),
                                "reasoning": (signal.get("reasoning") or "")[:200],
                                "order_id": result.get("order_id") if result else None,
                                "status": result.get("status") if result else None,
                                "source": f"bell_rush ({buy.get('source', 'news')})",
                                "gap_pct": buy.get("gap_pct"),
                                "size_multiplier": signal.get("position_size_multiplier", 1.0),
                                "auto": True,
                            }
                        )
                        _ticker_cooldowns[ticker] = datetime.utcnow() + timedelta(minutes=TICKER_COOLDOWN_MINUTES)
                        _recent_trade_decisions[ticker] = {"status": "executed", "reason": f"Bell rush, score {trade_score:.0f}", "timestamp": datetime.utcnow().isoformat()}
                        logger.info(f"[BELL-RUSH] Trade executed: {ticker} -> {result}")

                        _bell_rush_results.append({
                            "ticker": ticker,
                            "score": trade_score,
                            "gap_pct": buy.get("gap_pct"),
                            "source": buy.get("source", "news"),
                            "status": result.get("status") if result else "failed",
                            "quantity": result.get("quantity") if result else None,
                            "price": signal.get("entry_price"),
                        })

                        # Refresh owned set so we don't double-buy
                        owned.add(ticker)

                except Exception as e:
                    logger.error(f"[BELL-RUSH] Error during bell rush: {e}")

                _premarket_ready_list = []  # Clear after use

            _last_market_state = current_state

            if _auto_trade_enabled and is_market_open():
                _scan_sleep = min(
                    _auto_trade_interval,
                    26,
                ) if (
                    (now_et.hour == 9 and now_et.minute >= 30)
                    or (now_et.hour == 10 and now_et.minute <= 25)
                ) else _auto_trade_interval

                if now_et.hour == 15 and now_et.minute >= 30:
                    logger.info("🤖 [AUTO-TRADE] Skipping scan - too close to market close (3:30 PM+ ET)")
                    await asyncio.sleep(_scan_sleep)
                    continue

                logger.info("🤖 [AUTO-TRADE] Running automatic trade scan...")

                # === RISK CHECKS: Daily loss limit and market trend ===
                if _check_daily_loss_limit():
                    _log_trade_gate("*", 0, False, "daily loss limit hit")
                    await asyncio.sleep(_scan_sleep)
                    continue

                spy_skip, spy_change = _check_spy_trend()
                if spy_skip:
                    _log_trade_gate("*", 0, False, f"SPY down {spy_change*100:.2f}%")
                    await asyncio.sleep(_scan_sleep)
                    continue

                # Analyze all watchlist tickers with momentum + LLM (same pipeline as UI)
                try:
                    settings = get_settings()
                    min_score = float(settings.TRADING_MIN_SIGNAL_SCORE)
                    tickers = settings.watchlist[:20]

                    # Get current positions to skip tickers we already own
                    positions = alpaca_trader.get_positions() if alpaca_trader else []
                    owned_symbols = {p["symbol"] for p in positions}

                    # Analyze with concurrency limit
                    analyze_sem = asyncio.Semaphore(10)
                    async def analyze_limited(t):
                        async with analyze_sem:
                            return await _analyze_ticker_for_signal(t)

                    results = await asyncio.gather(
                        *[analyze_limited(t) for t in tickers],
                        return_exceptions=True
                    )

                    # Find tradeable signals after applying the stricter live gate.
                    buy_signals = []
                    for r in results:
                        if r is None or isinstance(r, Exception):
                            continue
                        r_ticker = r.get("ticker")
                        r_score = r.get("combined_score", 0)
                        r_action = r.get("action", "WAIT")

                        if r_ticker in owned_symbols:
                            _log_trade_gate(r_ticker, r_score, False, "already have position")
                            _recent_trade_decisions[r_ticker] = {"status": "blocked", "reason": "Already own position", "timestamp": datetime.utcnow().isoformat()}
                            continue

                        cooldown_until = _ticker_cooldowns.get(r_ticker)
                        if cooldown_until and datetime.utcnow() < cooldown_until:
                            remaining = (cooldown_until - datetime.utcnow()).total_seconds() / 60
                            _log_trade_gate(r_ticker, r_score, False, f"cooldown {remaining:.0f}min remaining")
                            _recent_trade_decisions[r_ticker] = {"status": "blocked", "reason": f"Cooldown ({remaining:.0f}m left)", "timestamp": datetime.utcnow().isoformat()}
                            continue

                        gate_ok, gate_reason = _passes_live_auto_trade_gate(r, owned_symbols)
                        if gate_ok:
                            buy_signals.append(r)
                        elif r_action == "BUY":
                            _log_trade_gate(r_ticker, r_score, False, gate_reason)
                            _recent_trade_decisions[r_ticker] = {"status": "blocked", "reason": gate_reason, "timestamp": datetime.utcnow().isoformat()}

                    buy_signals.sort(key=_auto_trade_signal_rank, reverse=True)

                    # Pick the best signal
                    signal = buy_signals[0] if buy_signals else None
                    score = signal.get("combined_score", 0) if signal else 0
                    action = signal.get("action", "WAIT") if signal else "WAIT"

                    should_trade = signal is not None

                    if should_trade:
                        ticker = signal.get("ticker")
                        signal["source"] = signal.get("source") or "watchlist_auto"
                        trade_score = float(signal.get("combined_score", 0))
                        keyword_score = float(signal.get("keyword_score", trade_score))
                        llm_enhanced = signal.get("llm_enhanced", False)

                        # Double-check we don't already own this ticker
                        if ticker in owned_symbols:
                            _log_trade_gate(ticker, trade_score, False, "position dedup (double-check)")

                        # LLM score is already in combined_score from _analyze_ticker_for_signal
                        # Log the keyword vs LLM score for transparency
                        elif llm_enhanced and keyword_score != trade_score:
                            logger.info(f"🤖 [AUTO-TRADE] {ticker}: keyword={keyword_score:.1f}, LLM={trade_score:.1f}")

                        if should_trade and ticker not in owned_symbols:
                            # For 90+ scores, close existing positions to free capital
                            if trade_score >= 90:
                                account = alpaca_trader.get_account_status()
                                acct_equity = float(account.get("equity", 0)) if account else 0
                                entry_price = float(signal.get("entry_price") or signal.get("price", 0))
                                if acct_equity > 0 and entry_price > 0:
                                    freed = await _free_capital_for_excellent_signal(ticker, entry_price, acct_equity)
                                    if not freed:
                                        logger.warning(f"🤖 [AUTO-TRADE] Could not free enough capital for 90+ signal on {ticker}, proceeding with available buying power")

                            # Execute the trade
                            _log_trade_gate(ticker, trade_score, True, f"executing buy (LLM={llm_enhanced})")
                            logger.info(f"🤖 [AUTO-TRADE] Executing BUY on {ticker} (LLM score: {trade_score:.1f})")
                            result = alpaca_trader.execute_trade(signal)

                            # Register with position manager for smart exit tracking
                            pm = get_position_manager()
                            if pm and result and result.get("status") == "executed":
                                pm.register_entry(
                                    symbol=ticker,
                                    entry_price=signal.get("entry_price", result.get("entry_price", 0)),
                                    quantity=result.get("quantity", 1),
                                    thesis=signal.get("reasoning", "")[:500],
                                    stop_loss=result.get("stop_loss"),
                                    take_profit=result.get("take_profit"),
                                    atr=signal.get("atr"),
                                    score_at_entry=signal.get("effective_score", signal.get("combined_score")),
                                    rvol_at_entry=signal.get("relative_volume"),
                                    regime_at_entry=signal.get("regime_at_entry") or signal.get("technical_regime"),
                                    source=signal.get("source"),
                                )
                                logger.info(f"🤖 [AUTO-TRADE] Registered {ticker} with Position Manager for exit tracking")

                            # Log the trade
                            log_activity(
                                log_type="AUTO_TRADE",
                                ticker=ticker,
                                action="BUY",
                                details={
                                    "price": signal.get("entry_price"),
                                    "quantity": result.get("quantity") if result else None,
                                    "score": trade_score,
                                    "effective_score": signal.get("effective_score", trade_score),
                                    "reasoning": (signal.get("reasoning") or "")[:200],
                                    "order_id": result.get("order_id") if result else None,
                                    "status": result.get("status") if result else None,
                                    "source": signal.get("source"),
                                    "size_multiplier": signal.get("position_size_multiplier", 1.0),
                                    "auto": True
                                }
                            )
                            # Set cooldown so we don't re-buy this ticker immediately
                            _ticker_cooldowns[ticker] = datetime.utcnow() + timedelta(minutes=TICKER_COOLDOWN_MINUTES)
                            owned_symbols.add(ticker)
                            _recent_trade_decisions[ticker] = {"status": "executed", "reason": f"Score {trade_score:.0f}, LLM confirmed", "timestamp": datetime.utcnow().isoformat()}
                            logger.info(f"🤖 [AUTO-TRADE] ✅ Trade executed: {result} (cooldown {TICKER_COOLDOWN_MINUTES}min)")
                    else:
                        # Log why we didn't trade
                        reason = "no signal passed live auto-trade gate"
                        if signal and signal.get("ticker"):
                            _log_trade_gate(signal["ticker"], float(score), False, reason)
                        else:
                            logger.info(f"🤖 [AUTO-TRADE] No trade - {reason}")

                    # === TRENDING PASS: Discover non-watchlist tickers from global news ===
                    try:
                        trending_result = await scan_trending()
                        trending_hits = trending_result.get("results", [])
                        if trending_hits:
                            logger.info(f"🤖 [TRENDING] {len(trending_hits)} trending tickers discovered")
                            trending_traded = False
                            for tr in trending_hits:
                                if trending_traded:
                                    break
                                tr_ticker = tr["ticker"]
                                tr_score = tr["score"]
                                tr_action = tr.get("recommendation", "HOLD")

                                if tr_action != "BUY" or tr_score < min_score:
                                    continue
                                if tr_ticker in owned_symbols:
                                    _log_trade_gate(tr_ticker, tr_score, False, "already have position", source="trending")
                                    _recent_trade_decisions[tr_ticker] = {"status": "blocked", "reason": "Already own position", "timestamp": datetime.utcnow().isoformat()}
                                    continue
                                cooldown_until = _ticker_cooldowns.get(tr_ticker)
                                if cooldown_until and datetime.utcnow() < cooldown_until:
                                    remaining = (cooldown_until - datetime.utcnow()).total_seconds() / 60
                                    _log_trade_gate(tr_ticker, tr_score, False, f"cooldown {remaining:.0f}min remaining", source="trending")
                                    _recent_trade_decisions[tr_ticker] = {"status": "blocked", "reason": f"Cooldown ({remaining:.0f}m left)", "timestamp": datetime.utcnow().isoformat()}
                                    continue

                                # Get full signal data — respect trade plan decisions
                                tr_signal = await _analyze_ticker_for_signal(tr_ticker)
                                if not tr_signal:
                                    continue
                                # Use higher of trending score vs trade plan score
                                if tr_score > float(tr_signal.get("combined_score", 0)):
                                    tr_signal["combined_score"] = tr_score
                                # Only override action if trade plan agrees or score is strong
                                if tr_signal.get("action") != "BUY" and tr_score < 75:
                                    logger.info(f"[TRENDING] {tr_ticker} trade plan says {tr_signal.get('action')}, score={tr_score:.1f} — skipping")
                                    continue
                                tr_signal["action"] = "BUY"
                                tr_signal["source"] = "trending"

                                # Must be LLM-confirmed for trading
                                if not tr.get("llm_enhanced"):
                                    # Try LLM scoring now
                                    try:
                                        llm_data = await get_sentiment(tr_ticker, use_llm=True)
                                        tr_signal["combined_score"] = llm_data["score"]
                                        tr_score = llm_data["score"]
                                        tr_signal["llm_enhanced"] = True
                                        if tr_score < min_score:
                                            _log_trade_gate(tr_ticker, tr_score, False, f"LLM rescore {tr_score:.1f} below {min_score}", source="trending")
                                            continue
                                    except Exception:
                                        _log_trade_gate(tr_ticker, tr_score, False, "LLM unavailable", source="trending")
                                        continue
                                else:
                                    tr_signal["llm_enhanced"] = True

                                gate_ok, gate_reason = _passes_live_auto_trade_gate(tr_signal, owned_symbols)
                                if not gate_ok:
                                    _log_trade_gate(tr_ticker, tr_score, False, gate_reason, source="trending")
                                    _recent_trade_decisions[tr_ticker] = {"status": "blocked", "reason": gate_reason, "timestamp": datetime.utcnow().isoformat()}
                                    continue

                                _log_trade_gate(tr_ticker, tr_score, True, f"executing buy (mentions={tr.get('mention_count', 1)})", source="trending")
                                logger.info(f"🤖 [TRENDING] Executing BUY on {tr_ticker} (score: {tr_score:.1f}, mentions: {tr.get('mention_count', 1)})")
                                result = alpaca_trader.execute_trade(tr_signal)

                                # Register with position manager
                                pm = get_position_manager()
                                if pm and result and result.get("status") == "executed":
                                    pm.register_entry(
                                        symbol=tr_ticker,
                                        entry_price=tr_signal.get("entry_price", result.get("entry_price", 0)),
                                        quantity=result.get("quantity", 1),
                                        thesis=tr_signal.get("reasoning", "")[:500],
                                        stop_loss=result.get("stop_loss"),
                                        take_profit=result.get("take_profit"),
                                        atr=tr_signal.get("atr"),
                                        score_at_entry=tr_signal.get("effective_score", tr_signal.get("combined_score")),
                                        rvol_at_entry=tr_signal.get("relative_volume"),
                                        regime_at_entry=tr_signal.get("regime_at_entry") or tr_signal.get("technical_regime"),
                                        source=tr_signal.get("source"),
                                    )

                                log_activity(
                                    log_type="AUTO_TRADE",
                                    ticker=tr_ticker,
                                    action="BUY",
                                    details={
                                        "price": tr_signal.get("entry_price"),
                                        "quantity": result.get("quantity") if result else None,
                                        "score": tr_score,
                                        "effective_score": tr_signal.get("effective_score", tr_score),
                                        "reasoning": (tr_signal.get("reasoning") or "")[:200],
                                        "order_id": result.get("order_id") if result else None,
                                        "status": result.get("status") if result else None,
                                        "source": "trending",
                                        "mention_count": tr.get("mention_count", 1),
                                        "size_multiplier": tr_signal.get("position_size_multiplier", 1.0),
                                        "auto": True,
                                    }
                                )
                                _ticker_cooldowns[tr_ticker] = datetime.utcnow() + timedelta(minutes=TICKER_COOLDOWN_MINUTES)
                                owned_symbols.add(tr_ticker)
                                _recent_trade_decisions[tr_ticker] = {"status": "executed", "reason": f"Trending, score {tr_score:.0f}", "timestamp": datetime.utcnow().isoformat()}
                                logger.info(f"🤖 [TRENDING] ✅ Trade executed: {result}")
                                trending_traded = True
                    except Exception as e:
                        logger.error(f"🤖 [TRENDING] Error in trending scan: {e}")

                except Exception as e:
                    logger.error(f"🤖 [AUTO-TRADE] Error getting signal: {e}")

            elif _auto_trade_enabled and not is_market_open():
                # Reset daily loss limit flag when market is closed (new day)
                if _daily_loss_limit_hit:
                    _daily_loss_limit_hit = False
                    logger.info("🤖 [AUTO-TRADE] Daily loss limit reset for new trading day")
                logger.debug("🤖 [AUTO-TRADE] Market closed, skipping scan")

            # Sleep longer outside trading hours to save resources
            from zoneinfo import ZoneInfo as _ZI
            _now_et = datetime.now(_ZI("America/New_York"))
            _in_hours = _now_et.weekday() < 5 and 7 <= _now_et.hour < 20
            _opening_drive = is_market_open() and (
                (_now_et.hour == 9 and _now_et.minute >= 30)
                or (_now_et.hour == 10 and _now_et.minute <= 25)
            )
            _round_sleep = _auto_trade_interval if _in_hours else 300
            if _opening_drive and _in_hours:
                _round_sleep = min(_round_sleep, 26)
            await asyncio.sleep(_round_sleep)

        except Exception as e:
            logger.error(f"🤖 [AUTO-TRADE] Loop error: {e}")
            await asyncio.sleep(_auto_trade_interval)


# ============= POSITION MANAGER API ENDPOINTS =============

@app.get("/api/position-manager/status")
async def get_position_manager_status():
    """Get smart position manager status and tracked positions."""
    pm = get_position_manager()
    if not pm:
        return {"status": "not_initialized"}
    return pm.get_status()


@app.post("/api/position-manager/register")
async def register_position_entry(
    symbol: str,
    entry_price: float,
    quantity: float,
    thesis: Optional[str] = None,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None
):
    """Manually register a position entry for smart exit tracking."""
    pm = get_position_manager()
    if not pm:
        raise HTTPException(status_code=500, detail="Position manager not initialized")

    pm.register_entry(
        symbol=symbol.upper(),
        entry_price=entry_price,
        quantity=quantity,
        thesis=thesis,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )

    return {
        "status": "registered",
        "symbol": symbol.upper(),
        "entry_price": entry_price,
        "quantity": quantity,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "message": f"Position {symbol} registered for smart exit management"
    }


@app.get("/api/position-manager/analyze/{symbol}")
async def analyze_position_exit(symbol: str):
    """Run LLM exit analysis for a specific position."""
    from app.services.agents.exit_strategy_agent import ExitStrategyAgent
    from app.services.position_manager import calculate_atr
    from app.services.technical_indicators import analyze_technical

    symbol = symbol.upper()
    positions = alpaca_trader.get_positions()
    position = next((p for p in positions if p["symbol"] == symbol), None)

    if not position:
        raise HTTPException(status_code=404, detail=f"No position found for {symbol}")

    pm = get_position_manager()
    pos_state = pm.state.positions.get(symbol) if pm else None

    current_price = position.get("current", 0)
    entry_price = pos_state.entry_price if pos_state else position.get("entry", 0)
    days_held = pos_state.days_held if pos_state else 0

    # Get bars for technical analysis
    bars = await pm._get_bars(symbol) if pm else []
    atr = calculate_atr(bars) if bars else current_price * 0.02

    tech_signal = analyze_technical(symbol, current_price, bars) if bars else None
    technical_data = {
        "rsi": tech_signal.rsi if tech_signal else 50,
        "trend": tech_signal.trend if tech_signal else "neutral",
        "momentum": tech_signal.momentum if tech_signal else "flat",
        "sma_20": tech_signal.sma_20 if tech_signal else current_price,
        "sma_50": tech_signal.sma_50 if tech_signal else current_price,
    }

    # Run exit analysis
    exit_plan = await ExitStrategyAgent.analyze_with_cache(
        ticker=symbol,
        position={
            "qty": position.get("qty"),
            "unrealized_pl": position.get("pnl", 0),
            "unrealized_plpc": position.get("pnl_pct", 0),
        },
        current_price=current_price,
        entry_price=entry_price,
        entry_thesis=pos_state.entry_thesis if pos_state else None,
        days_held=days_held,
        atr=atr,
        technical_data=technical_data,
        original_stop_loss=pos_state.original_stop_loss if pos_state else None,
        original_take_profit=pos_state.original_take_profit if pos_state else None,
        force=True,  # Force fresh analysis
    )

    return {
        "symbol": symbol,
        "position": position,
        "exit_analysis": exit_plan.to_dict(),
        "recommendation": {
            "action": exit_plan.action.value,
            "urgency": exit_plan.urgency.value,
            "stop_loss": exit_plan.stop_loss,
            "take_profit_levels": exit_plan.take_profit_levels,
            "reasoning": exit_plan.reasoning,
        }
    }


# ============= AUTO-TRADE API ENDPOINTS =============

@app.get("/api/auto-trade/status")
async def get_auto_trade_status():
    """Get current auto-trade status."""
    return {
        "enabled": _auto_trade_enabled,
        "interval": _auto_trade_interval,
        "market_open": is_market_open(),
        "updated_at": datetime.utcnow().isoformat()
    }


@app.get("/api/premarket/status")
async def get_premarket_status():
    """Get pre-market scanner status, ready list, and bell rush results."""
    from zoneinfo import ZoneInfo
    now_et = datetime.now(ZoneInfo("America/New_York"))
    today_str = now_et.strftime("%Y-%m-%d")
    market_status = get_market_status()

    # Determine phase
    if not _auto_trade_enabled or market_status in ("closed", "closed_weekend"):
        phase = "inactive"
    elif market_status == "after_hours":
        phase = "completed" if _bell_rush_date == today_str else "inactive"
    elif market_status == "open":
        if _bell_rush_results or (_bell_rush_date == today_str and not _premarket_ready_list):
            phase = "completed"
        elif _premarket_ready_list:
            phase = "bell_rush"
        else:
            phase = "completed"
    elif market_status == "pre_market":
        if _premarket_ready_list and _premarket_built_today == today_str:
            phase = "ready"
        elif _premarket_built_today == today_str:
            phase = "scanning"
        elif now_et.hour == 9 and now_et.minute >= 15:
            phase = "scanning"
        else:
            phase = "waiting"
    else:
        phase = "inactive"

    # Next event hint
    if phase == "waiting":
        next_event = "Ready list builds at 9:15 AM ET"
    elif phase == "scanning":
        next_event = "Building ready list..."
    elif phase == "ready":
        next_event = f"Bell rush at market open (9:30 AM ET) — {len(_premarket_ready_list)} tickers queued"
    elif phase == "bell_rush":
        next_event = "Bell rush in progress..."
    elif phase == "completed":
        traded = len([r for r in _bell_rush_results if r.get("status") == "executed"])
        next_event = f"Bell rush complete — {traded} trade(s) executed" if _bell_rush_results else "Pre-market complete"
    else:
        next_event = "Available during pre-market hours (4:00-9:30 AM ET)"

    return {
        "phase": phase,
        "ready_list": _premarket_ready_list if _premarket_built_today == today_str else [],
        "bell_rush_results": _bell_rush_results if _bell_rush_date == today_str else [],
        "built_today": _premarket_built_today,
        "market_status": market_status,
        "next_event": next_event,
    }


@app.post("/api/auto-trade/enable")
async def enable_auto_trade(interval: int = 60):
    """Enable auto-trading with specified interval (seconds)."""
    global _auto_trade_enabled, _auto_trade_interval

    _auto_trade_enabled = True
    _auto_trade_interval = max(30, min(300, interval))  # Clamp between 30s and 5min
    save_auto_trade_state()

    logger.info(f"🤖 [AUTO-TRADE] ENABLED with {_auto_trade_interval}s interval")

    return {
        "status": "enabled",
        "enabled": True,
        "interval": _auto_trade_interval,
        "message": f"Auto-trading enabled. Will scan every {_auto_trade_interval}s when market is open."
    }


@app.post("/api/auto-trade/disable")
async def disable_auto_trade():
    """Disable auto-trading."""
    global _auto_trade_enabled

    _auto_trade_enabled = False
    save_auto_trade_state()

    logger.info("🤖 [AUTO-TRADE] DISABLED")

    return {
        "status": "disabled",
        "enabled": False,
        "message": "Auto-trading disabled. No automatic trades will be executed."
    }


# ============= MOMENTUM TRADING & FLASH SIGNALS =============

@app.get("/api/momentum/{ticker}")
async def get_momentum_analysis(ticker: str):
    """Ultra-fast momentum analysis for quick trades."""
    ticker = ticker.upper()

    # Check cache first
    now = datetime.utcnow()
    if ticker in _momentum_cache:
        cached_data, cache_time = _momentum_cache[ticker]
        if (now - cache_time).total_seconds() < MOMENTUM_CACHE_TTL:
            logger.debug(f"Momentum cache HIT for {ticker}")
            return cached_data

    # Get real-time data
    quote_data = await get_quote(ticker)

    # Quick news check (last hour only for speed)
    if benzinga_client:
        news = await benzinga_client.get_news(
            tickers=ticker,
            published_gte=(datetime.utcnow() - timedelta(hours=1)).strftime("%Y-%m-%d"),
            limit=5
        )
    else:
        news = {"results": []}

    # Calculate momentum score (0-100)
    momentum_score = 50
    signals = []

    # Price momentum - continuous scaling based on daily change
    price_change = quote_data.get("change_percent", 0)

    # Softer intraday beta so "already up 2%" does not dominate the score (sentiment carries early edge).
    price_momentum = price_change * 5
    price_momentum = max(-30, min(30, price_momentum))  # Cap at +/- 30 points
    momentum_score += price_momentum

    # Anti-chase: already-up names get penalized (reduces buying blow-off tops on headline hype)
    if price_change > 1.85:
        chase_penalty = min(22.0, (price_change - 1.85) * 5.5)
        momentum_score -= chase_penalty
        signals.append(f"⚠️ Extended +{price_change:.1f}% day — chase penalty")
    elif -0.4 <= price_change <= 0.9:
        momentum_score += 3
        signals.append("⚖️ Calm tape — room for catalyst to reprice")

    # Add descriptive signals based on magnitude
    if price_change > 3:
        signals.append("🚀 STRONG UPWARD MOMENTUM")
    elif price_change > 1.5:
        signals.append("📈 POSITIVE MOMENTUM")
    elif price_change > 0.5:
        signals.append("📈 SLIGHT UPWARD")
    elif price_change < -3:
        signals.append("📉 STRONG DOWNWARD MOMENTUM")
    elif price_change < -1.5:
        signals.append("⬇️ NEGATIVE MOMENTUM")
    elif price_change < -0.5:
        signals.append("⬇️ SLIGHT DOWNWARD")

    # Breaking news momentum
    news_items = news.get("results", [])
    if news_items:
        # Count recent news (any news in last hour counts)
        recent_count = len(news_items)
        if recent_count > 0:
            # More news = more momentum (capped lower — sentiment path already consumes headlines)
            news_boost = min(6, recent_count * 2)
            momentum_score += news_boost
            signals.append(f"📰 {recent_count} recent news items")

            # Check news sentiment quickly
            bullish_count = 0
            bearish_count = 0
            for item in news_items[:5]:
                title = item.get("title", "").lower()
                if any(word in title for word in ["surge", "soar", "jump", "breakthrough", "beat", "upgrade", "bullish", "rally"]):
                    bullish_count += 1
                elif any(word in title for word in ["crash", "plunge", "fall", "miss", "warning", "downgrade", "bearish", "drop"]):
                    bearish_count += 1

            # Net news sentiment
            net_sentiment = bullish_count - bearish_count
            if net_sentiment > 0:
                momentum_score += min(10, net_sentiment * 5)
                signals.append(f"💥 {bullish_count} BULLISH headlines")
            elif net_sentiment < 0:
                momentum_score -= min(10, abs(net_sentiment) * 5)
                signals.append(f"⚠️ {bearish_count} BEARISH headlines")

    # Volatility indicator
    if abs(price_change) > 2:
        signals.append("🔥 HIGH VOLATILITY")
    elif abs(price_change) > 1:
        signals.append("📊 MODERATE ACTIVITY")

    # Cap score
    momentum_score = max(5, min(95, momentum_score))  # Wider range for differentiation

    # Generate instant trade decision
    if momentum_score >= 70:
        action = "🟢 BUY NOW"
        urgency = "IMMEDIATE"
        strategy = "MOMENTUM SCALP"
    elif momentum_score >= 65:
        action = "🟡 BUY READY"
        urgency = "QUICK"
        strategy = "QUICK TRADE"
    elif momentum_score <= 25:
        action = "🔴 SELL/SHORT"
        urgency = "IMMEDIATE"
        strategy = "EXIT NOW"
    elif momentum_score <= 35:
        action = "🟠 SELL READY"
        urgency = "QUICK"
        strategy = "REDUCE/EXIT"
    else:
        action = "⚪ NO ACTION"
        urgency = "WAIT"
        strategy = "MONITOR"

    current_price = quote_data.get("price", 100)

    result = {
        "ticker": ticker,
        "momentum_score": momentum_score,
        "action": action,
        "urgency": urgency,
        "strategy": strategy,
        "signals": signals,

        # Quick trade parameters
        "flash_trade": {
            "entry_price": current_price,
            "quick_target": round(current_price * 1.01, 2),  # 1% quick profit
            "scalp_target": round(current_price * 1.02, 2),  # 2% scalp target
            "momentum_target": round(current_price * 1.03, 2),  # 3% momentum target
            "stop_loss": _entry_risk_levels(current_price, quote_data)[0],
            "time_limit": "5-15 minutes",
            "exit_on": "Momentum loss or target hit"
        },

        # Momentum indicators
        "momentum_status": {
            "strength": "STRONG" if abs(momentum_score - 50) > 25 else "MODERATE" if abs(momentum_score - 50) > 15 else "WEAK",
            "direction": "UP" if momentum_score > 50 else "DOWN" if momentum_score < 50 else "FLAT",
            "speed": "FAST" if len(signals) >= 3 else "NORMAL",
            "news_driven": len(news_items) > 0,
            "price_change": f"{price_change:+.2f}%"
        },

        # Exit conditions
        "exit_triggers": [
            "Momentum score drops below 40" if momentum_score > 50 else "Momentum score rises above 60",
            "Price reverses 0.5% from entry",
            "5 minutes without continued momentum",
            "Target hit or stop triggered"
        ],

        "timestamp": datetime.utcnow().isoformat(),
        "analysis_time": "< 1 second"
    }

    # Cache the result
    _momentum_cache[ticker] = (result, now)

    return result

@app.get("/api/momentum/scan")
async def momentum_scanner():
    """Scan all tickers for momentum opportunities RIGHT NOW."""
    hot_tickers = ["TSLA", "NVDA", "AMD", "AAPL", "META", "GOOGL", "MSFT", "AMZN"]

    momentum_alerts = []

    for ticker in hot_tickers:
        try:
            momentum = await get_momentum_analysis(ticker)

            if momentum["momentum_score"] >= 65 or momentum["momentum_score"] <= 35:
                momentum_alerts.append({
                    "ticker": ticker,
                    "score": momentum["momentum_score"],
                    "action": momentum["action"],
                    "urgency": momentum["urgency"],
                    "signals": momentum["signals"][:2],  # Top 2 signals
                    "entry": momentum["flash_trade"]["entry_price"],
                    "target": momentum["flash_trade"]["quick_target"],
                    "stop": momentum["flash_trade"]["stop_loss"]
                })
        except:
            pass

    # Sort by urgency
    momentum_alerts.sort(key=lambda x: abs(x["score"] - 50), reverse=True)

    return {
        "scan_time": datetime.utcnow().isoformat(),
        "alerts_count": len(momentum_alerts),
        "hot_trades": momentum_alerts[:3],  # Top 3 opportunities
        "all_alerts": momentum_alerts,
        "market_status": "🔥 HOT" if len(momentum_alerts) >= 3 else "⚡ ACTIVE" if len(momentum_alerts) >= 1 else "😴 QUIET"
    }

# ============= AI INSIGHTS & ANALYSIS =============

@app.get("/api/ai/deep-analysis/{ticker}")
async def get_deep_ai_analysis(
    ticker: str,
    force: bool = Query(False, description="Force LLM calls even if cache is valid")
):
    """
    Get DEEP AI analysis using Claude + OpenAI agents WITH SMART CACHING.

    This endpoint runs the full multi-agent analysis:
    1. NewsIntelligenceAgent (Claude) - Deep news analysis
    2. TechnicalAnalysisAgent (OpenAI) - Technical signals
    3. SentimentSynthesisAgent (Claude) - Final trading decision

    LLMs are only called when:
    - No cached signal exists
    - Upstream data has changed since last run
    - Cache has expired
    - force=true is passed

    This keeps LLM costs low (~$40-80/month vs $150-200+).
    """
    ticker = ticker.upper()

    try:
        from app.services.ai_agents import run_full_analysis

        # Gather all data
        quote_data = await get_quote(ticker)
        current_price = quote_data.get("price", 100)

        # Get bars for technical analysis
        bars = await get_bars(ticker, timeframe="1H", limit=50)

        # Get news with timestamp for cache check
        latest_news_ts = None
        if benzinga_client:
            news_data = await benzinga_client.get_news(tickers=ticker, limit=10)
            news_items = news_data.get("results", [])
            # Extract latest news timestamp
            if news_items:
                newest = news_items[0]
                ts_str = newest.get("created", newest.get("published_at", ""))
                if ts_str:
                    try:
                        latest_news_ts = datetime.fromisoformat(
                            ts_str.replace("Z", "+00:00")
                        )
                    except ValueError:
                        pass
        else:
            news_items = []

        # Get earnings
        if benzinga_client:
            earnings_data = await benzinga_client.get_earnings(ticker=ticker, limit=3)
            earnings = earnings_data.get("results", [{}])[0] if earnings_data.get("results") else None
        else:
            earnings = None

        # Get account and positions
        account = alpaca_trader.get_account_status()
        positions_data = alpaca_trader.get_positions()

        # Calculate technical indicators (simple versions)
        closes = [b.get("close", 0) for b in bars[-20:]] if bars else []
        rsi = calculate_rsi(closes) if len(closes) >= 14 else None
        macd = calculate_macd(closes) if len(closes) >= 26 else None
        sma_20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
        sma_50 = sum([b.get("close", 0) for b in bars[-50:]]) / 50 if len(bars) >= 50 else None

        # Run full AI analysis WITH CACHING
        result = await run_full_analysis(
            ticker=ticker,
            news_items=news_items,
            current_price=current_price,
            bars=bars,
            rsi=rsi,
            macd=macd,
            sma_20=sma_20,
            sma_50=sma_50,
            earnings=earnings,
            account=account,
            positions=positions_data,
            latest_news_ts=latest_news_ts,
            force_llm=force,  # Pass force flag
        )

        return result

    except Exception as e:
        logger.error(f"Deep AI analysis error for {ticker}: {e}", exc_info=True)
        return {
            "ticker": ticker,
            "error": str(e),
            "final_action": "HOLD",
            "final_score": 50,
            "message": "AI analysis failed, using neutral stance"
        }


@app.get("/api/ai/quick-analysis/{ticker}")
async def get_quick_ai_analysis(ticker: str):
    """
    Get FAST analysis using only Python (NO LLM calls).

    This endpoint runs pure Python technical analysis without any LLM costs.
    Use this for the main loop / frequent updates.

    For deep analysis with LLMs, use /api/ai/deep-analysis/{ticker}.
    """
    ticker = ticker.upper()

    try:
        from app.services.ai_agents import run_quick_analysis

        # Get bars for technical analysis
        bars = await get_bars(ticker, timeframe="1H", limit=50)

        # Get current price
        quote_data = await get_quote(ticker)
        current_price = quote_data.get("price", 100)

        # Run quick analysis (no LLM)
        result = await run_quick_analysis(
            ticker=ticker,
            current_price=current_price,
            bars=bars,
        )

        return result

    except Exception as e:
        logger.error(f"Quick analysis error for {ticker}: {e}", exc_info=True)
        return {
            "ticker": ticker,
            "error": str(e),
            "score": 50,
            "message": "Quick analysis failed"
        }


@app.get("/api/ai/cache/status")
async def get_cache_status_endpoint(
    ticker: Optional[str] = Query(None, description="Specific ticker or None for overall stats")
):
    """
    Get agent cache status and statistics.

    This endpoint shows:
    - Cache hit/miss rates
    - LLM calls saved
    - Per-ticker cache status
    - Cache expiration times

    Use this to monitor LLM cost optimization.
    """
    from app.services.ai_agents import get_cache_status

    if ticker:
        return get_cache_status(ticker.upper())
    return get_cache_status()


@app.post("/api/ai/cache/clear")
async def clear_cache_endpoint(
    ticker: Optional[str] = Query(None, description="Specific ticker or None to clear all")
):
    """
    Clear agent caches.

    Use this to force fresh LLM analysis on next request.
    """
    from app.services.agent_cache import agent_cache

    if ticker:
        agent_cache.invalidate(ticker.upper())
        return {"message": f"Cache cleared for {ticker.upper()}"}
    else:
        agent_cache.invalidate_all()
        return {"message": "All caches cleared"}


def calculate_rsi(closes: list, period: int = 14) -> float:
    """Calculate RSI from closing prices."""
    if len(closes) < period + 1:
        return 50.0

    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calculate_macd(closes: list) -> dict:
    """Calculate MACD from closing prices."""
    if len(closes) < 26:
        return {"value": 0, "signal": 0, "histogram": 0}

    def ema(data, period):
        multiplier = 2 / (period + 1)
        ema_values = [data[0]]
        for price in data[1:]:
            ema_values.append((price * multiplier) + (ema_values[-1] * (1 - multiplier)))
        return ema_values[-1]

    ema_12 = ema(closes, 12)
    ema_26 = ema(closes, 26)
    macd_line = ema_12 - ema_26

    # Signal line (9-period EMA of MACD) - simplified
    signal = macd_line * 0.8  # Approximation

    return {
        "value": round(macd_line, 4),
        "signal": round(signal, 4),
        "histogram": round(macd_line - signal, 4)
    }


@app.get("/api/ai/analyze/{ticker}")
async def get_ai_analysis(ticker: str):
    """Get comprehensive AI analysis and insights for a ticker (legacy endpoint)."""
    ticker = ticker.upper()

    # Gather all available data
    sentiment_data = await get_sentiment(ticker)
    quote_data = await get_quote(ticker)

    # Fetch additional data for analysis
    news_task = benzinga_client.get_news(tickers=ticker, limit=10) if benzinga_client else None
    earnings_task = benzinga_client.get_earnings(ticker=ticker, limit=3) if benzinga_client else None

    if benzinga_client:
        news, earnings = await asyncio.gather(news_task, earnings_task, return_exceptions=True)
    else:
        news = earnings = None

    # Build comprehensive AI analysis
    analysis = {
        "ticker": ticker,
        "timestamp": datetime.utcnow().isoformat(),
        "current_price": quote_data.get("price"),
        "price_change": quote_data.get("change_percent"),

        # Overall AI Assessment
        "ai_score": sentiment_data.get("score"),
        "ai_sentiment": sentiment_data.get("sentiment"),
        "ai_recommendation": "STRONG BUY" if sentiment_data.get("score", 50) >= 85 else
                            "BUY" if sentiment_data.get("score", 50) >= 70 else
                            "HOLD" if sentiment_data.get("score", 50) >= 40 else
                            "SELL" if sentiment_data.get("score", 50) >= 15 else
                            "STRONG SELL",

        # Detailed Signal Analysis
        "signal_breakdown": {
            "technical_signals": {
                "momentum": "Bullish" if quote_data.get("change_percent", 0) > 1 else "Bearish" if quote_data.get("change_percent", 0) < -1 else "Neutral",
                "price_action": f"${quote_data.get('price', 0):.2f} ({quote_data.get('change_percent', 0):+.2f}%)",
                "trend": "Uptrend" if quote_data.get("change_percent", 0) > 0 else "Downtrend",
            },

            "sentiment_signals": {
                "news_sentiment": analyze_news_sentiment(news),
                "earnings_outlook": analyze_earnings_outlook(earnings),
                "social_buzz": "High" if sentiment_data.get("score", 50) > 70 else "Moderate" if sentiment_data.get("score", 50) > 50 else "Low",
            },

            "fundamental_signals": {
                "earnings_trend": "Positive" if earnings and has_positive_earnings_trend(earnings) else "Mixed",
                "analyst_consensus": "Bullish" if sentiment_data.get("score", 50) > 60 else "Neutral",
                "sector_momentum": "Strong" if ticker in ["NVDA", "MSFT", "GOOGL"] else "Moderate",
            }
        },

        # AI Reasoning & Logic
        "ai_reasoning": {
            "primary_factors": [],
            "risk_factors": [],
            "opportunity_factors": [],
            "confidence_level": "HIGH" if abs(sentiment_data.get("score", 50) - 50) > 30 else "MEDIUM" if abs(sentiment_data.get("score", 50) - 50) > 15 else "LOW",
        },

        # Actionable Insights
        "actionable_insights": {
            "entry_points": [],
            "exit_points": [],
            "position_sizing": "",
            "risk_management": "",
            "time_horizon": "",
        },

        # Decision Explanation
        "decision_explanation": "",
    }

    # Build AI reasoning based on score
    score = sentiment_data.get("score", 50)

    # Primary factors
    if score >= 70:
        analysis["ai_reasoning"]["primary_factors"] = [
            f"Strong bullish sentiment (score: {score})",
            f"Positive price momentum ({quote_data.get('change_percent', 0):+.2f}%)",
            "Multiple positive news catalysts detected",
            "Technical indicators favor upward movement"
        ]
        analysis["ai_reasoning"]["opportunity_factors"] = [
            "High probability of continued upward momentum",
            "Strong market sentiment supporting price appreciation",
            "Potential for breakout above resistance levels"
        ]
    elif score <= 30:
        analysis["ai_reasoning"]["primary_factors"] = [
            f"Strong bearish sentiment (score: {score})",
            "Negative news flow impacting stock",
            "Technical weakness detected",
            "Market sentiment turning negative"
        ]
        analysis["ai_reasoning"]["risk_factors"] = [
            "High probability of continued downward pressure",
            "Weak technical structure",
            "Negative catalysts outweigh positives"
        ]
    else:
        analysis["ai_reasoning"]["primary_factors"] = [
            f"Neutral market sentiment (score: {score})",
            "Mixed signals from news and data",
            "Consolidation phase likely",
            "Waiting for clearer direction"
        ]

    # Risk factors (always present)
    analysis["ai_reasoning"]["risk_factors"].extend([
        "Market volatility remains elevated",
        "Macro economic uncertainties",
        "Sector rotation risks"
    ])

    # Actionable insights based on AI score
    current_price = quote_data.get("price", 100)

    if score >= 70:
        analysis["actionable_insights"] = {
            "entry_points": [
                f"Immediate: ${current_price:.2f} (current)",
                f"On dip: ${current_price * 0.98:.2f} (-2%)",
                f"Breakout: ${current_price * 1.02:.2f} (+2%)"
            ],
            "exit_points": [
                f"Target 1: ${current_price * 1.05:.2f} (+5%)",
                f"Target 2: ${current_price * 1.10:.2f} (+10%)",
                f"Stop loss: ${current_price * 0.95:.2f} (-5%)"
            ],
            "position_sizing": "75-100% of planned allocation",
            "risk_management": "Use 5% stop loss, trail stops after +5% gain",
            "time_horizon": "2-4 weeks for full targets"
        }

        analysis["decision_explanation"] = f"""
        🤖 AI DECISION: BULLISH - RECOMMEND BUY

        The AI system has identified {ticker} as a strong buying opportunity based on:
        1. Sentiment score of {score}/100 indicates strong positive momentum
        2. Recent price action shows {quote_data.get('change_percent', 0):+.2f}% movement
        3. News analysis reveals {len(news.get('results', [])) if news else 0} recent positive catalysts
        4. Technical and fundamental factors align bullishly

        CONFIDENCE: {analysis['ai_reasoning']['confidence_level']}
        RISK/REWARD: Favorable (potential +10% upside vs -5% risk)
        """

    elif score <= 30:
        analysis["actionable_insights"] = {
            "entry_points": [
                "Not recommended at current levels",
                f"Wait for support at ${current_price * 0.90:.2f} (-10%)"
            ],
            "exit_points": [
                f"Exit existing positions at ${current_price:.2f}",
                f"Short target: ${current_price * 0.95:.2f} (-5%)"
            ],
            "position_sizing": "Reduce or exit positions",
            "risk_management": "Tight stops, consider hedging",
            "time_horizon": "Immediate action recommended"
        }

        analysis["decision_explanation"] = f"""
        🤖 AI DECISION: BEARISH - RECOMMEND SELL/AVOID

        The AI system warns against {ticker} based on:
        1. Weak sentiment score of {score}/100 indicates negative momentum
        2. Technical weakness and bearish patterns detected
        3. Negative news flow and deteriorating fundamentals
        4. High risk of further downside

        CONFIDENCE: {analysis['ai_reasoning']['confidence_level']}
        RISK/REWARD: Unfavorable (limited upside vs significant downside risk)
        """
    else:
        analysis["actionable_insights"] = {
            "entry_points": [
                f"Wait for breakout above ${current_price * 1.03:.2f}",
                f"Or support bounce at ${current_price * 0.97:.2f}"
            ],
            "exit_points": [
                f"Range top: ${current_price * 1.05:.2f}",
                f"Range bottom: ${current_price * 0.95:.2f}"
            ],
            "position_sizing": "25-50% of planned allocation",
            "risk_management": "Wide stops, wait for confirmation",
            "time_horizon": "Monitor for 1-2 weeks for clearer signals"
        }

        analysis["decision_explanation"] = f"""
        🤖 AI DECISION: NEUTRAL - HOLD/WAIT

        The AI system recommends patience with {ticker}:
        1. Mixed sentiment score of {score}/100 suggests consolidation
        2. Conflicting signals require more data
        3. No clear directional bias identified
        4. Better opportunities may exist elsewhere

        CONFIDENCE: {analysis['ai_reasoning']['confidence_level']}
        RISK/REWARD: Balanced (wait for better setup)
        """

    return analysis

def analyze_news_sentiment(news_data):
    """Analyze news sentiment from news data."""
    if not news_data or "results" not in news_data:
        return "No recent news"

    results = news_data.get("results", [])
    if not results:
        return "No recent news"

    positive_count = 0
    negative_count = 0

    for item in results[:10]:
        title = item.get("title", "").lower()
        if any(word in title for word in ["upgrade", "beat", "surge", "rally", "gain"]):
            positive_count += 1
        elif any(word in title for word in ["downgrade", "miss", "fall", "drop", "loss"]):
            negative_count += 1

    if positive_count > negative_count + 2:
        return f"Very Positive ({positive_count}+ articles)"
    elif positive_count > negative_count:
        return f"Positive ({positive_count} vs {negative_count})"
    elif negative_count > positive_count:
        return f"Negative ({negative_count} vs {positive_count})"
    else:
        return f"Mixed ({positive_count}/{negative_count})"

def analyze_earnings_outlook(earnings_data):
    """Analyze earnings outlook from earnings data."""
    if not earnings_data or "results" not in earnings_data:
        return "No upcoming earnings"

    results = earnings_data.get("results", [])
    if not results:
        return "No upcoming earnings"

    next_earnings = results[0]
    if next_earnings.get("importance", 0) >= 3:
        return f"High importance earnings soon"
    else:
        return "Regular earnings cycle"

def has_positive_earnings_trend(earnings_data):
    """Check if earnings show positive trend."""
    if not earnings_data or "results" not in earnings_data:
        return False

    for earning in earnings_data.get("results", [])[:3]:
        if earning.get("actual_eps") and earning.get("estimated_eps"):
            if earning["actual_eps"] > earning["estimated_eps"]:
                return True
    return False

# ============= WATCHLIST SCANNER =============

@app.get("/api/watchlist")
async def get_watchlist():
    """Return the configured watchlist tickers from .env."""
    return {
        "tickers": settings.watchlist,
        "count": {
            "watchlist": len(settings.watchlist),
            "dynamic": len(_dynamic_watchlist),
        }
    }


@app.get("/api/watchlist/dynamic")
async def get_dynamic_watchlist():
    """Return dynamically discovered tickers (auto-added when kw score >= 70)."""
    dynamic = _get_dynamic_tickers()
    return {
        "tickers": sorted(dynamic),
        "count": len(dynamic),
        "expiry_hours": DYNAMIC_WATCHLIST_EXPIRY_HOURS,
        "entries": {t: _dynamic_watchlist[t].isoformat() for t in sorted(dynamic)},
    }


@app.get("/api/scan/watchlist")
async def scan_watchlist():
    """Scan all watchlist tickers for opportunities."""
    scan_buy_threshold = float(settings.TRADING_SCAN_BUY_SCORE)
    llm_rescore_threshold = float(settings.TRADING_LLM_RESCORE_MIN_SCORE)

    # Check cache first
    cache_key = "watchlist"
    now = datetime.utcnow()
    if cache_key in _scan_cache:
        cached_data, cache_time = _scan_cache[cache_key]
        if (now - cache_time).total_seconds() < SCAN_CACHE_TTL:
            logger.debug("Scan watchlist cache HIT")
            return cached_data

    if not benzinga_client:
        return {
            "message": "Benzinga API not configured",
            "watchlist": settings.watchlist
        }

    async def scan_ticker(ticker: str):
        """Scan a single ticker and return result."""
        try:
            sentiment_data = await get_sentiment(ticker)
            return {
                "ticker": ticker,
                "sentiment": sentiment_data["sentiment"],
                "score": sentiment_data["score"],
                "shrinkage": sentiment_data.get("shrinkage", {}),
                "recommendation": "BUY" if sentiment_data["score"] >= scan_buy_threshold else
                                 "STRONG SELL" if sentiment_data["score"] <= 10 else
                                 "SELL" if sentiment_data["score"] <= 30 else "HOLD"
            }
        except Exception as e:
            logger.error(f"Error scanning {ticker}: {e}")
            return {
                "ticker": ticker,
                "sentiment": "unknown",
                "score": 50,
                "recommendation": "HOLD",
                "error": str(e)
            }

    # Run scans with limited concurrency (15 at a time — keyword-only, cheap API calls)
    scan_semaphore = asyncio.Semaphore(15)
    async def scan_with_limit(ticker):
        async with scan_semaphore:
            return await scan_ticker(ticker)

    # Merge static watchlist + dynamic tickers (discovered from trending)
    static_tickers = settings.watchlist
    dynamic_tickers = _get_dynamic_tickers() - set(static_tickers)
    all_tickers = static_tickers + list(dynamic_tickers)
    if dynamic_tickers:
        logger.info(f"[DYNAMIC-WL] Scanning {len(dynamic_tickers)} dynamic tickers: {sorted(dynamic_tickers)}")

    results = await asyncio.gather(*[scan_with_limit(t) for t in all_tickers])
    results = list(results)

    # === PASS 2: LLM re-scoring on candidates above strict gate ===
    # get_sentiment(use_llm=True) internally blocks LLM outside market hours & when no news
    candidates = [r for r in results if r["score"] >= llm_rescore_threshold or r["score"] <= 25]
    if candidates:
        logger.info(
            f"LLM second pass: re-scoring {len(candidates)} candidates "
            f"(score >= {llm_rescore_threshold:.0f} or <= 25)"
        )

        llm_semaphore = asyncio.Semaphore(3)  # Limit concurrent LLM calls

        async def llm_rescore(result_entry):
            async with llm_semaphore:
                try:
                    llm_sentiment = await get_sentiment(result_entry["ticker"], use_llm=True)
                    old_score = result_entry["score"]
                    result_entry["score"] = llm_sentiment["score"]
                    result_entry["sentiment"] = llm_sentiment["sentiment"]
                    result_entry["llm_enhanced"] = True
                    result_entry["keyword_score"] = old_score
                    result_entry["recommendation"] = (
                        "BUY" if llm_sentiment["score"] >= scan_buy_threshold else
                        "STRONG SELL" if llm_sentiment["score"] <= 10 else
                        "SELL" if llm_sentiment["score"] <= 30 else "HOLD"
                    )
                    logger.info(
                        f"LLM rescore {result_entry['ticker']}: "
                        f"{old_score:.1f} -> {llm_sentiment['score']:.1f}"
                    )
                except Exception as e:
                    logger.warning(f"LLM rescore failed for {result_entry['ticker']}: {e}")

        await asyncio.gather(*[llm_rescore(r) for r in candidates])

    # Sort by score (highest first) - re-sort after LLM rescoring
    results.sort(key=lambda x: x["score"], reverse=True)

    response = {
        "scan_time": datetime.utcnow().isoformat(),
        "watchlist_count": len(all_tickers),
        "dynamic_count": len(dynamic_tickers),
        "llm_rescored": len(candidates) if candidates else 0,
        "results": results,
        "top_opportunities": [r for r in results if r["score"] >= scan_buy_threshold],
        "warnings": [r for r in results if r["score"] <= 30]
    }

    # Cache the result
    _scan_cache[cache_key] = (response, now)
    return response


@app.get("/api/scan/trending")
async def scan_trending():
    """Discover high-scoring tickers from global news (not on watchlist)."""
    # Allow pre-market (8 AM+ ET weekdays) in addition to market hours
    from zoneinfo import ZoneInfo as _ZI_trend
    _now_trend = datetime.now(_ZI_trend("America/New_York"))
    _trend_allowed = is_market_open() or (_now_trend.weekday() < 5 and _now_trend.hour >= 8)
    if not _trend_allowed:
        return {"results": [], "message": "Market closed", "scan_time": datetime.utcnow().isoformat()}

    # Check cache
    cache_key = "trending"
    now = datetime.utcnow()
    if cache_key in _scan_cache:
        cached_data, cache_time = _scan_cache[cache_key]
        if (now - cache_time).total_seconds() < TRENDING_CACHE_TTL:
            logger.debug("[TRENDING] Cache HIT")
            return cached_data

    if not benzinga_client:
        return {"results": [], "message": "Benzinga API not configured"}

    settings = get_settings()
    watchlist_set = set(settings.watchlist)
    scan_buy_threshold = float(settings.TRADING_SCAN_BUY_SCORE)

    # Fetch 50 latest articles with NO ticker filter
    try:
        raw_news = await benzinga_client.get_news(limit=50)
        articles = raw_news.get("results", []) if isinstance(raw_news, dict) else []
    except Exception as e:
        logger.error(f"[TRENDING] Failed to fetch global news: {e}")
        return {"results": [], "error": str(e)}

    # Extract tickers from each article
    ticker_mentions = {}  # {ticker: count}
    strong_headline_keywords = {
        "surge", "soar", "plunge", "crash", "beats", "misses", "upgrade", "downgrade",
        "partnership", "approval", "contract", "breakthrough", "record", "bankruptcy",
        "raises guidance", "cuts guidance", "investigation", "probe",
    }

    for article in articles:
        # Extract tickers from all possible fields
        tickers_in_article = set()
        for stock in (article.get("stocks") or []):
            sym = stock.get("symbol") or stock.get("ticker") or stock.get("name")
            if sym:
                tickers_in_article.add(sym.upper())
        for sym in (article.get("tickers") or []):
            if isinstance(sym, str):
                tickers_in_article.add(sym.upper())
        for sec in (article.get("securities") or []):
            sym = sec.get("symbol") or sec.get("ticker")
            if sym:
                tickers_in_article.add(sym.upper())

        for sym in tickers_in_article:
            # Filter out excluded ETFs, watchlist tickers, and invalid symbols
            if sym in _EXCLUDED_TICKERS or sym in watchlist_set:
                continue
            if not sym.isalpha() or len(sym) > 5:
                continue
            ticker_mentions[sym] = ticker_mentions.get(sym, 0) + 1

    if not ticker_mentions:
        response = {"results": [], "scan_time": now.isoformat(), "discovered": 0}
        _scan_cache[cache_key] = (response, now)
        return response

    # Separate multi-mention (2+) from single-mention tickers
    multi_mention = {t: c for t, c in ticker_mentions.items() if c >= 2}
    single_mention = {t: c for t, c in ticker_mentions.items() if c == 1}

    # For single-mention: only keep if headline has strong keywords
    strong_singles = set()
    for article in articles:
        headline = (article.get("title") or article.get("headline") or "").lower()
        if any(kw in headline for kw in strong_headline_keywords):
            # Extract tickers from this article
            for stock in (article.get("stocks") or []):
                sym = (stock.get("symbol") or stock.get("ticker") or stock.get("name") or "").upper()
                if sym in single_mention:
                    strong_singles.add(sym)
            for sym in (article.get("tickers") or []):
                if isinstance(sym, str) and sym.upper() in single_mention:
                    strong_singles.add(sym.upper())

    # Build candidate list: all multi-mention + strong singles
    candidates = list(multi_mention.keys())[:15]
    remaining_slots = max(0, 15 - len(candidates))
    candidates.extend(list(strong_singles)[:remaining_slots])

    if not candidates:
        response = {"results": [], "scan_time": now.isoformat(), "discovered": 0}
        _scan_cache[cache_key] = (response, now)
        return response

    # Keyword-score each candidate
    scan_semaphore = asyncio.Semaphore(5)

    async def score_ticker(ticker):
        async with scan_semaphore:
            try:
                sentiment = await get_sentiment(ticker)
                return {
                    "ticker": ticker,
                    "score": sentiment["score"],
                    "sentiment": sentiment["sentiment"],
                    "mention_count": ticker_mentions.get(ticker, 1),
                    "source": "trending",
                    "recommendation": (
                        "BUY" if sentiment["score"] >= scan_buy_threshold else
                        "SELL" if sentiment["score"] <= 30 else "HOLD"
                    ),
                }
            except Exception as e:
                logger.warning(f"[TRENDING] Score failed for {ticker}: {e}")
                return None

    raw_results = await asyncio.gather(*[score_ticker(t) for t in candidates])
    results = [r for r in raw_results if r is not None and r["score"] >= 70]

    # Add all 70+ keyword-scoring tickers to dynamic watchlist
    for r in results:
        _add_to_dynamic_watchlist(r["ticker"], r["score"])

    # LLM re-score any tickers that passed keyword gate (>= 70)
    llm_candidates = [r for r in results if r["score"] >= 70]
    if llm_candidates:
        llm_semaphore = asyncio.Semaphore(3)

        async def llm_rescore(entry):
            async with llm_semaphore:
                try:
                    llm_data = await get_sentiment(entry["ticker"], use_llm=True)
                    old_score = entry["score"]
                    entry["score"] = llm_data["score"]
                    entry["sentiment"] = llm_data["sentiment"]
                    entry["llm_enhanced"] = True
                    entry["keyword_score"] = old_score
                    entry["recommendation"] = (
                        "BUY" if llm_data["score"] >= scan_buy_threshold else
                        "SELL" if llm_data["score"] <= 30 else "HOLD"
                    )
                    logger.info(f"[TRENDING] LLM rescore {entry['ticker']}: {old_score:.1f} -> {llm_data['score']:.1f}")
                except Exception as e:
                    logger.warning(f"[TRENDING] LLM rescore failed for {entry['ticker']}: {e}")

        await asyncio.gather(*[llm_rescore(r) for r in llm_candidates])

    # Re-filter after LLM (scores may have changed) and sort
    results = [r for r in results if r["score"] >= 70]
    results.sort(key=lambda x: x["score"], reverse=True)
    results = results[:15]

    logger.info(f"[TRENDING] Discovered {len(results)} tickers scoring 70+ from {len(ticker_mentions)} unique tickers")

    response = {
        "scan_time": now.isoformat(),
        "discovered": len(results),
        "total_tickers_seen": len(ticker_mentions),
        "results": results,
    }
    _scan_cache[cache_key] = (response, now)
    return response


# ============= WEBSOCKET =============

class ConnectionManager:
    """Manage WebSocket connections."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast to all connections."""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass


manager = ConnectionManager()


@app.websocket("/ws/production")
async def websocket_production(websocket: WebSocket):
    """PRODUCTION WebSocket - ONE unified signal, auto-execution, position management."""
    await manager.connect(websocket)

    try:
        await websocket.send_json({
            "type": "connected",
            "message": "🚀 PRODUCTION TRADING SYSTEM - PAPER MODE",
            "mode": "UNIFIED SIGNALS",
            "timestamp": datetime.utcnow().isoformat()
        })

        scan_counter = 0

        while True:
            try:
                # Check for commands
                data = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)

                if data == "execute":
                    # Manual execution trigger
                    result = await execute_trade(auto=True)
                    await websocket.send_json({
                        "type": "execution",
                        "result": result,
                        "timestamp": datetime.utcnow().isoformat()
                    })

                elif data.startswith("close:"):
                    # Close position
                    ticker = data.split(":")[1].upper()
                    result = alpaca_trader.close_position(ticker)
                    await websocket.send_json({
                        "type": "position_closed",
                        "result": result,
                        "timestamp": datetime.utcnow().isoformat()
                    })

            except asyncio.TimeoutError:
                scan_counter += 1

                # Every 10 seconds, scan for the BEST signal
                if scan_counter % 1 == 0:  # Every cycle (10 seconds)
                    # Get current positions first
                    positions = await get_positions()

                    # Get the single best signal
                    best_signal = await get_best_trading_signal()

                    # Check if we should execute
                    # Paper trading works 24/7, so we allow execution anytime
                    market_status = get_market_status()
                    is_paper_mode = True  # Alpaca is always in paper mode for safety
                    should_execute = (
                        best_signal.get("action") == "BUY" and
                        best_signal.get("combined_score", 0) >= 70 and
                        (is_market_open() or is_paper_mode)  # Paper mode allows 24/7 trading
                    )

                    # Send unified update
                    await websocket.send_json({
                        "type": "trading_update",

                        # THE ONE SIGNAL
                        "best_signal": best_signal,

                        # Current positions with exit signals
                        "positions": positions,

                        # Account status
                        "account": alpaca_trader.get_account_status(),

                        # Auto-execution status
                        "auto_execute": should_execute,
                        "execution_pending": should_execute and best_signal.get("action") == "BUY",

                        # Market status
                        "market_status": get_market_status(),

                        "timestamp": datetime.utcnow().isoformat(),
                        "next_scan": "10 seconds"
                    })

                    # Auto-execute if conditions met
                    if should_execute:
                        logger.info(f"🎯 AUTO-EXECUTING: {best_signal['ticker']} @ {best_signal['combined_score']:.1f}")
                        result = alpaca_trader.execute_trade(best_signal)
                        await websocket.send_json({
                            "type": "auto_execution",
                            "signal": best_signal,
                            "result": result,
                            "timestamp": datetime.utcnow().isoformat()
                        })
                        logger.info(f"✅ Execution result: {result}")
                    elif best_signal.get("combined_score", 0) >= 70 and best_signal.get("action") != "BUY":
                        logger.info(f"⏸️ Signal {best_signal['ticker']} score {best_signal['combined_score']:.1f} >= 70 but action is {best_signal.get('action')}")

                # Check for exit conditions on positions
                if scan_counter % 3 == 0:  # Every 30 seconds
                    positions = await get_positions()
                    for position in positions["positions"]:
                        if position.get("exit_signal"):
                            # Auto-exit if stop loss or strong signal
                            if "STOP LOSS" in position["exit_signal"] or "TARGET HIT" in position["exit_signal"]:
                                result = alpaca_trader.close_position(position["symbol"])
                                await websocket.send_json({
                                    "type": "auto_exit",
                                    "position": position,
                                    "reason": position["exit_signal"],
                                    "result": result,
                                    "timestamp": datetime.utcnow().isoformat()
                                })

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)

def get_market_status():
    """Get current market status."""
    from zoneinfo import ZoneInfo
    now_et = datetime.now(ZoneInfo("America/New_York"))
    weekday = now_et.weekday()

    if weekday >= 5:
        return "closed_weekend"
    elif now_et.hour >= 4 and now_et.hour < 9:
        return "pre_market"
    elif now_et.hour == 9 and now_et.minute < 30:
        return "pre_market"
    elif now_et.hour == 9 and now_et.minute >= 30:
        return "open"
    elif now_et.hour >= 10 and now_et.hour < 16:
        return "open"
    elif now_et.hour >= 16 and now_et.hour < 20:
        return "after_hours"
    else:
        return "closed"


def is_market_open() -> bool:
    """Check if the market is currently open."""
    status = get_market_status()
    return status == "open"

@app.websocket("/ws/signals")
async def websocket_signals(websocket: WebSocket):
    """WebSocket for real-time AI signals with detailed analysis."""
    await manager.connect(websocket)
    signal_counter = 0

    try:
        await websocket.send_json({
            "type": "connected",
            "message": "Connected to AI Trading Signals with Enhanced Insights",
            "timestamp": datetime.utcnow().isoformat()
        })

        # Send periodic AI signals and analysis
        while True:
            try:
                # Wait for client message or timeout after 30 seconds
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)

                # Handle client requests for specific analysis
                if data == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                elif data.startswith("analyze:"):
                    # Client requested analysis for specific ticker
                    ticker = data.split(":")[1].upper()
                    analysis = await get_ai_analysis(ticker)
                    await websocket.send_json({
                        "type": "ai_analysis",
                        "ticker": ticker,
                        "analysis": analysis,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                else:
                    # Echo for testing
                    await websocket.send_json({
                        "type": "echo",
                        "data": data,
                        "timestamp": datetime.utcnow().isoformat()
                    })

            except asyncio.TimeoutError:
                signal_counter += 1

                # Every 3rd heartbeat, send an AI signal instead
                if signal_counter % 3 == 0:
                    # Generate AI trading signal with detailed insights
                    watchlist = ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA", "META", "AMZN"]
                    ticker = random.choice(watchlist)

                    # Get quick sentiment
                    sentiment_data = await get_sentiment(ticker)
                    score = sentiment_data.get("score", 50)

                    # Build AI signal with reasoning
                    signal = {
                        "type": "ai_signal",
                        "ticker": ticker,
                        "action": "BUY" if score >= 70 else "STRONG SELL" if score <= 10 else "SELL" if score <= 30 else "HOLD",
                        "strength": "STRONG" if abs(score - 50) > 30 else "MODERATE" if abs(score - 50) > 15 else "WEAK",
                        "ai_score": score,
                        "confidence": "HIGH" if abs(score - 50) > 30 else "MEDIUM" if abs(score - 50) > 15 else "LOW",

                        # AI Reasoning
                        "ai_insights": {
                            "decision": "BUY SIGNAL" if score >= 70 else "SELL SIGNAL" if score <= 30 else "NEUTRAL",
                            "reasoning": [
                                f"Sentiment score: {score}/100",
                                f"Market conditions: {'Favorable' if score > 50 else 'Challenging'}",
                                f"Technical setup: {'Bullish' if score >= 70 else 'Bearish' if score <= 30 else 'Consolidating'}",
                                f"News flow: {sentiment_data.get('sources', {}).get('news_analyzed', 0)} articles analyzed"
                            ],
                            "key_factors": [
                                f"Primary trend: {'Upward' if score > 60 else 'Downward' if score < 40 else 'Sideways'}",
                                f"Risk level: {'Low' if score > 70 else 'High' if score < 30 else 'Medium'}",
                                f"Time horizon: {'Short-term' if abs(score - 50) > 30 else 'Medium-term'}"
                            ],
                            "recommendation": f"{'Strong Buy' if score >= 85 else 'Buy' if score >= 70 else 'Hold' if score >= 40 else 'Sell' if score >= 15 else 'Strong Sell'}"
                        },

                        # Actionable data
                        "targets": {
                            "entry": f"Current market price",
                            "stop_loss": f"-5% from entry" if score > 50 else "-3% from entry",
                            "take_profit_1": f"+5% from entry" if score > 50 else "+3% from entry",
                            "take_profit_2": f"+10% from entry" if score > 70 else "+5% from entry"
                        },

                        "timestamp": datetime.utcnow().isoformat()
                    }

                    await websocket.send_json(signal)

                else:
                    # Regular heartbeat with market status
                    from datetime import timezone

                    # Get current time in Eastern Time
                    now_utc = datetime.now(timezone.utc)
                    et_hour = (now_utc.hour - 5) % 24
                    weekday = now_utc.weekday()

                    # Determine market status
                    if weekday >= 5:
                        market_status = "closed_weekend"
                    elif et_hour >= 4 and et_hour < 9:
                        market_status = "pre_market"
                    elif et_hour == 9 and now_utc.minute >= 30:
                        market_status = "open"
                    elif et_hour >= 10 and et_hour < 16:
                        market_status = "open"
                    elif et_hour >= 16 and et_hour < 20:
                        market_status = "after_hours"
                    else:
                        market_status = "closed"

                    # Include AI system status in heartbeat
                    await websocket.send_json({
                        "type": "heartbeat",
                        "timestamp": now_utc.isoformat(),
                        "market_status": market_status,
                        "et_time": f"{et_hour:02d}:{now_utc.minute:02d} ET",
                        "ai_status": {
                            "active": True,
                            "scanning": True,
                            "signals_generated": signal_counter // 3,
                            "next_signal_in": f"{(3 - (signal_counter % 3)) * 30} seconds"
                        }
                    })

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


@app.websocket("/ws/momentum")
async def websocket_momentum(websocket: WebSocket):
    """High-speed WebSocket for momentum trading signals - updates every 5 seconds."""
    await manager.connect(websocket)
    momentum_tickers = ["TSLA", "NVDA", "AMD", "AAPL", "META"]
    active_positions = {}

    try:
        await websocket.send_json({
            "type": "connected",
            "message": "⚡ Connected to High-Speed Momentum Trading",
            "timestamp": datetime.utcnow().isoformat(),
            "update_frequency": "5 seconds"
        })

        while True:
            try:
                # Check for client messages (non-blocking with short timeout)
                data = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)

                if data.startswith("track:"):
                    # Add ticker to momentum tracking
                    ticker = data.split(":")[1].upper()
                    if ticker not in momentum_tickers:
                        momentum_tickers.append(ticker)
                    await websocket.send_json({
                        "type": "tracking_added",
                        "ticker": ticker,
                        "message": f"Now tracking {ticker} for momentum"
                    })

                elif data.startswith("enter:"):
                    # Simulate position entry
                    ticker = data.split(":")[1].upper()
                    active_positions[ticker] = {
                        "entry_time": datetime.utcnow().isoformat(),
                        "entry_price": (await get_quote(ticker)).get("price", 100)
                    }
                    await websocket.send_json({
                        "type": "position_entered",
                        "ticker": ticker,
                        "entry_price": active_positions[ticker]["entry_price"]
                    })

            except asyncio.TimeoutError:
                # Send momentum updates every 5 seconds
                momentum_updates = []

                for ticker in momentum_tickers[:5]:  # Top 5 tickers for speed
                    try:
                        momentum = await get_momentum_analysis(ticker)

                        # Check if we should alert
                        should_alert = (
                            momentum["momentum_score"] >= 70 or
                            momentum["momentum_score"] <= 30 or
                            ticker in active_positions
                        )

                        if should_alert:
                            update = {
                                "ticker": ticker,
                                "score": momentum["momentum_score"],
                                "action": momentum["action"],
                                "signals": momentum["signals"][:2],
                                "flash_trade": momentum["flash_trade"],
                                "momentum_status": momentum["momentum_status"]
                            }

                            # Check position status if we have one
                            if ticker in active_positions:
                                entry_price = active_positions[ticker]["entry_price"]
                                current_price = momentum["flash_trade"]["entry_price"]
                                pnl = ((current_price - entry_price) / entry_price) * 100

                                update["position"] = {
                                    "entry": entry_price,
                                    "current": current_price,
                                    "pnl": f"{pnl:+.2f}%",
                                    "exit_signal": momentum["momentum_score"] < 45 if pnl > 0 else momentum["momentum_score"] < 35
                                }

                                # Auto-exit recommendation
                                if update["position"]["exit_signal"]:
                                    update["alert"] = "🚨 MOMENTUM LOST - CONSIDER EXIT"
                                elif pnl >= 2:
                                    update["alert"] = "🎯 TARGET HIT - TAKE PROFIT"
                                elif pnl <= -1:
                                    update["alert"] = "⛔ STOP LOSS - EXIT NOW"

                            momentum_updates.append(update)
                    except:
                        pass

                # Send consolidated update
                if momentum_updates:
                    await websocket.send_json({
                        "type": "momentum_update",
                        "updates": momentum_updates,
                        "timestamp": datetime.utcnow().isoformat(),
                        "active_positions": len(active_positions),
                        "next_update": "5 seconds"
                    })
                else:
                    # Send heartbeat if no momentum
                    await websocket.send_json({
                        "type": "heartbeat",
                        "message": "No momentum detected",
                        "timestamp": datetime.utcnow().isoformat(),
                        "scanning": momentum_tickers
                    })

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)

@app.websocket("/ws/trades")
async def websocket_trades(websocket: WebSocket):
    """WebSocket for real-time trade updates."""
    await manager.connect(websocket)
    try:
        await websocket.send_json({
            "type": "connected",
            "message": "Connected to Trade Stream",
            "timestamp": datetime.utcnow().isoformat()
        })

        # Keep connection alive and handle messages
        while True:
            try:
                # Wait for client message or timeout after 30 seconds
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)

                # Handle client requests
                if data == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                else:
                    # Echo for testing
                    await websocket.send_json({
                        "type": "trade_echo",
                        "data": data,
                        "timestamp": datetime.utcnow().isoformat()
                    })

            except asyncio.TimeoutError:
                # Send simulated trade update with more realistic prices
                # Approximate real prices as of Nov 2024
                ticker_prices = {
                    "AAPL": (220, 230),    # Apple ~$225
                    "GOOGL": (170, 180),   # Google ~$175
                    "MSFT": (485, 495),    # Microsoft ~$490
                    "TSLA": (340, 360),    # Tesla ~$350
                    "NVDA": (140, 150),    # NVIDIA ~$145
                    "META": (560, 580),    # Meta ~$570
                    "AMZN": (210, 220),    # Amazon ~$215
                }

                ticker = random.choice(list(ticker_prices.keys()))
                price_range = ticker_prices[ticker]
                base_price = random.uniform(price_range[0], price_range[1])

                # Add small random variation for realistic movement
                price_variation = random.uniform(-2, 2)
                price = round(base_price + price_variation, 2)

                # Determine action based on price movement simulation
                action = random.choice(["BUY", "SELL", "BUY", "HOLD"])  # Slightly favor BUY

                await websocket.send_json({
                    "type": "trade_update",
                    "ticker": ticker,
                    "action": action,
                    "quantity": random.randint(1, 100),
                    "price": price,
                    "timestamp": datetime.utcnow().isoformat(),
                    "note": "Simulated trade - connect to real broker for live data"
                })

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


@app.websocket("/ws/status")
async def websocket_status(websocket: WebSocket):
    """WebSocket for system status updates."""
    await manager.connect(websocket)
    try:
        await websocket.send_json({
            "type": "connected",
            "message": "Connected to System Status",
            "timestamp": datetime.utcnow().isoformat()
        })

        # Keep connection alive and handle messages
        while True:
            try:
                # Wait for client message or timeout after 10 seconds for more frequent status updates
                data = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)

                # Handle client requests
                if data == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                else:
                    # Echo for testing
                    await websocket.send_json({
                        "type": "status_echo",
                        "data": data,
                        "timestamp": datetime.utcnow().isoformat()
                    })

            except asyncio.TimeoutError:
                # Send status update
                await websocket.send_json({
                    "type": "status",
                    "system": "healthy",
                    "trading_mode": settings.ALPACA_ENV,
                    "is_paper": settings.is_paper_trading,
                    "connections": len(manager.active_connections),
                    "api_status": {
                        "benzinga": benzinga_client is not None,
                        "alpaca": bool(settings.ALPACA_API_KEY_ID)
                    },
                    "timestamp": datetime.utcnow().isoformat()
                })

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# ============= DEBATE SYSTEM ENDPOINTS =============

@app.get("/api/debate/{ticker}")
async def run_debate_analysis(
    ticker: str,
    force: bool = Query(False, description="Force new debate even if cached")
):
    """
    Run a full multi-agent debate for a trading decision.

    Returns the complete debate including:
    - Initial agent positions
    - Challenges and rebuttals
    - Final weighted decision
    - Risk warnings
    """
    from app.services.debate.debate_engine import DebateEngine
    from app.services.memory.memory_store import MemoryStore
    from app.services.memory.weight_adjuster import WeightAdjuster

    ticker = ticker.upper()

    try:
        # Initialize components
        memory_store = MemoryStore()
        weight_adjuster = WeightAdjuster(memory_store)

        # Get adjusted weights
        adjusted_weights = await weight_adjuster.get_adjusted_weights()

        # Initialize debate engine with adjusted weights
        engine = DebateEngine(agent_weights=adjusted_weights)

        # Gather market data
        market_data = {"quote": {"price": 100}, "bars": [], "news": []}

        # Get quote
        if alpaca_trader:
            quote = alpaca_trader.get_quote(ticker)
            if quote:
                market_data["quote"] = {"price": quote.get("price", 100)}

        # Get news
        if benzinga_client:
            news_result = await benzinga_client.get_news(tickers=ticker, limit=10)
            market_data["news"] = news_result.get("results", [])

        # Get account and positions
        account = {"equity": 100000, "buying_power": 50000}
        positions = []
        if alpaca_trader:
            account = alpaca_trader.get_account_status() or account
            positions = alpaca_trader.get_positions() or []

        # Run debate
        outcome = await engine.run_debate(
            ticker=ticker,
            market_data=market_data,
            account=account,
            positions=positions,
        )

        return {
            "ticker": ticker,
            "timestamp": datetime.utcnow().isoformat(),
            "outcome": outcome.to_dict(),
            "agent_weights": adjusted_weights,
        }

    except Exception as e:
        logger.error(f"Debate error for {ticker}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/memory/similar-trades/{ticker}")
async def get_similar_trades(
    ticker: str,
    market_regime: Optional[str] = None,
    limit: int = 10,
):
    """Get similar past trades for context."""
    from app.services.memory.memory_store import MemoryStore

    try:
        store = MemoryStore()
        trades = await store.get_similar_situations(
            ticker=ticker.upper(),
            market_regime=market_regime or "neutral",
            technical_regime="neutral",
            limit=limit,
        )

        return {
            "ticker": ticker.upper(),
            "similar_trades": [t.to_dict() for t in trades],
            "count": len(trades),
        }

    except Exception as e:
        logger.error(f"Memory retrieval error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/memory/stats")
async def get_memory_stats():
    """Get trading memory statistics."""
    from app.services.memory.memory_store import MemoryStore

    try:
        store = MemoryStore()
        stats = await store.get_stats()
        return stats

    except Exception as e:
        logger.error(f"Memory stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/agents/performance")
async def get_agent_performance(
    period: str = Query("month", description="day, week, month, all"),
    market_regime: Optional[str] = None,
):
    """Get performance metrics for all agents."""
    from app.services.memory.memory_store import MemoryStore

    try:
        store = MemoryStore()
        agents = ["news", "technical", "macro", "contrarian", "risk", "timing", "exit"]

        performance = {}
        for agent in agents:
            perf = await store.get_agent_accuracy(agent, period, market_regime)
            performance[agent] = perf

        return {
            "period": period,
            "market_regime": market_regime,
            "agents": performance,
        }

    except Exception as e:
        logger.error(f"Agent performance error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/agents/weights")
async def get_current_weights():
    """Get current agent weights (adjusted for performance)."""
    from app.services.memory.memory_store import MemoryStore
    from app.services.memory.weight_adjuster import WeightAdjuster

    try:
        store = MemoryStore()
        adjuster = WeightAdjuster(store)

        weights = await adjuster.get_adjusted_weights()

        return {
            "weights": weights,
            "default_weights": WeightAdjuster.DEFAULT_WEIGHTS,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Weight retrieval error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/context/{ticker}")
async def get_decision_context(
    ticker: str,
    market_regime: str = "neutral",
    technical_regime: str = "neutral",
):
    """Get historical context for a trading decision."""
    from app.services.memory.memory_store import MemoryStore
    from app.services.memory.context_retriever import ContextRetriever

    try:
        store = MemoryStore()
        retriever = ContextRetriever(store)

        context = await retriever.get_decision_context(
            ticker=ticker.upper(),
            market_regime=market_regime,
            technical_regime=technical_regime,
            news_sentiment="neutral",
        )

        return {
            "ticker": ticker.upper(),
            "context": context.to_dict(),
            "formatted_prompt": retriever.format_for_prompt(context),
        }

    except Exception as e:
        logger.error(f"Context retrieval error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    import asyncio

    port = int(os.getenv("PORT", "8000"))

    print(f"\n🚀 Starting AI Trading System on http://localhost:{port}")
    print(f"📚 API Documentation: http://localhost:{port}/docs")
    print(f"🔍 Health Check: http://localhost:{port}/health")
    print(f"📊 System Status: http://localhost:{port}/status")
    print(f"📰 Real News: http://localhost:{port}/api/news?ticker=AAPL")
    print(f"💹 Sentiment: http://localhost:{port}/api/sentiment/AAPL")
    print(f"🔎 Scan Watchlist: http://localhost:{port}/api/scan/watchlist")
    print(f"📡 Scan Trending: http://localhost:{port}/api/scan/trending\n")

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )
