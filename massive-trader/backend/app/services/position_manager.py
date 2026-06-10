"""
Position Manager - Monitors open positions and executes exits.

This is the missing piece that connects entry to exit.
Runs on an interval, monitors all positions, and:
1. Calls ExitStrategyAgent to evaluate each position
2. Executes exits when conditions are met
3. Adjusts stop orders when needed
4. Logs all decisions to trade journal
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from app.services.alpaca_trader import alpaca_trader, AlpacaTrader
from app.services.agents.exit_strategy_agent import (
    ExitStrategyAgent,
    ExitAction,
    ExitUrgency,
    ExitPlan,
)
from app.services.technical_indicators import analyze_technical
from app.core.config import get_settings

logger = logging.getLogger(__name__)


def calculate_atr(bars: List[Dict], period: int = 14) -> float:
    """
    Calculate Average True Range for volatility measurement.

    Args:
        bars: List of OHLC bars
        period: ATR period (default 14)

    Returns:
        ATR value or 0 if insufficient data
    """
    if len(bars) < period + 1:
        return 0.0

    true_ranges = []
    for i in range(1, len(bars)):
        high = bars[i].get("high", 0)
        low = bars[i].get("low", 0)
        prev_close = bars[i - 1].get("close", 0)

        if high and low and prev_close:
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)

    if len(true_ranges) < period:
        return sum(true_ranges) / len(true_ranges) if true_ranges else 0.0

    return sum(true_ranges[-period:]) / period


@dataclass
class PositionState:
    """Track state for a managed position."""
    symbol: str
    entry_price: float
    entry_time: datetime
    quantity: float
    entry_thesis: Optional[str] = None
    original_stop_loss: Optional[float] = None
    original_take_profit: Optional[float] = None
    current_stop_loss: Optional[float] = None
    last_exit_analysis: Optional[ExitPlan] = None
    last_analysis_time: Optional[datetime] = None
    trailing_stop_active: bool = False
    trailing_stop_price: Optional[float] = None
    # Adaptive exit state
    breakeven_armed: bool = False  # stop moved to entry once +0.8% reached
    partial_taken: bool = False    # 50% scale-out at first profit target executed
    # Trading intelligence fields
    atr: Optional[float] = None
    score_at_entry: Optional[float] = None
    rvol_at_entry: Optional[float] = None
    regime_at_entry: Optional[str] = None
    source: Optional[str] = None

    @property
    def days_held(self) -> int:
        """Calculate days position has been held."""
        return (datetime.utcnow() - self.entry_time).days


@dataclass
class PositionManagerState:
    """Global state for the position manager."""
    positions: Dict[str, PositionState] = field(default_factory=dict)
    last_run: Optional[datetime] = None
    run_count: int = 0

    # Stats
    positions_closed: int = 0
    positions_adjusted: int = 0
    total_realized_pnl: float = 0.0


class PositionManager:
    """
    Monitors open positions and manages exits.

    This runs alongside the trading loop and handles:
    1. Position monitoring every N seconds
    2. Exit strategy evaluation via LLM
    3. Stop loss adjustments (tighten, trail)
    4. Partial and full exits
    5. Trade journaling
    """

    def __init__(
        self,
        trader: Optional[AlpacaTrader] = None,
        check_interval: int = 30,
        min_analysis_interval: int = 60,
    ):
        """
        Initialize position manager.

        Args:
            trader: Alpaca trader instance (default: global instance)
            check_interval: Seconds between position checks
            min_analysis_interval: Minimum seconds between LLM analysis for same position
        """
        self.settings = get_settings()
        self.trader = trader or alpaca_trader
        self.check_interval = check_interval
        self.min_analysis_interval = min_analysis_interval

        self.state = PositionManagerState()
        self._running = False
        self._task: Optional[asyncio.Task] = None

        logger.info(
            f"PositionManager initialized: check_interval={check_interval}s, "
            f"min_analysis_interval={min_analysis_interval}s"
        )

    async def start(self):
        """Start the position monitoring loop."""
        if self._running:
            logger.warning("PositionManager already running")
            return

        self._running = True
        logger.info("Starting PositionManager...")
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self):
        """Stop the position monitoring loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("PositionManager stopped")

    def _is_trading_hours(self) -> bool:
        """Check if we're in or near trading hours (no need to run at 1 AM)."""
        now_et = datetime.now(ZoneInfo("America/New_York"))
        # Skip weekends entirely
        if now_et.weekday() >= 5:
            return False
        # Only run between 7 AM and 8 PM ET (pre-market through after-hours)
        return 7 <= now_et.hour < 20

    async def _run_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                if self._is_trading_hours():
                    await self._check_positions()
                    self.state.run_count += 1
                    self.state.last_run = datetime.utcnow()
                else:
                    logger.debug("PositionManager: Outside trading hours, sleeping")
            except Exception as e:
                logger.error(f"PositionManager error: {e}", exc_info=True)

            # Sleep longer outside trading hours (5 min vs normal interval)
            sleep_time = self.check_interval if self._is_trading_hours() else 300
            await asyncio.sleep(sleep_time)

    async def _check_positions(self):
        """Check all open positions and evaluate exits."""
        # Get current positions from Alpaca
        positions = self.trader.get_positions()

        if not positions:
            logger.debug("No open positions to monitor")
            return

        logger.info(f"Monitoring {len(positions)} positions...")

        for pos in positions:
            try:
                await self._evaluate_position(pos)
            except Exception as e:
                logger.error(f"Error evaluating {pos.get('symbol')}: {e}")

    async def _evaluate_position(self, position: Dict[str, Any]):
        """
        Evaluate a single position for exit.

        Args:
            position: Position dict from Alpaca
        """
        symbol = position.get("symbol")
        if not symbol:
            return

        # Get or create position state
        if symbol not in self.state.positions:
            # New position we haven't seen - initialize tracking
            self.state.positions[symbol] = PositionState(
                symbol=symbol,
                entry_price=position.get("entry", position.get("avg_entry_price", 0)),
                entry_time=datetime.utcnow(),  # Approximate since we don't have exact time
                quantity=abs(float(position.get("qty", 0))),
            )
            logger.info(f"Started tracking new position: {symbol}")

        pos_state = self.state.positions[symbol]
        current_price = position.get("current", 0)
        entry_price = pos_state.entry_price or position.get("entry", 0)

        if not current_price or not entry_price:
            logger.warning(f"{symbol}: Missing price data, skipping")
            return

        # ALWAYS check simple rules FIRST - these are fast protective checks
        # that should run regardless of LLM analysis status
        await self._check_simple_rules(symbol, position, pos_state)

        # If position was closed by simple rules, stop here
        if symbol not in self.state.positions:
            return

        # Check if we need to run LLM analysis for more nuanced decisions
        should_analyze = self._should_analyze(pos_state, position)

        if should_analyze:
            exit_plan = await self._run_exit_analysis(symbol, position, pos_state)
            if exit_plan:
                await self._execute_exit_plan(symbol, position, exit_plan, pos_state)

    def _should_analyze(self, pos_state: PositionState, position: Dict) -> bool:
        """Determine if we should run LLM exit analysis."""
        # Always analyze if never analyzed
        if pos_state.last_analysis_time is None:
            return True

        # Check time since last analysis
        time_since = (datetime.utcnow() - pos_state.last_analysis_time).total_seconds()
        if time_since < self.min_analysis_interval:
            return False

        # Check for significant price change since last analysis
        if pos_state.last_exit_analysis:
            last_price = pos_state.last_exit_analysis.stop_loss  # Proxy for last price context
            current_price = position.get("current", 0)
            if last_price and current_price:
                price_change = abs(current_price - last_price) / last_price
                if price_change > 0.02:  # >2% change triggers re-analysis
                    return True

        # Check P&L thresholds
        pnl_pct = position.get("pnl_pct", 0) * 100
        if abs(pnl_pct) > 5:  # >5% P&L triggers analysis
            return True

        # Default: analyze every 5 minutes
        return time_since > 300

    async def _run_exit_analysis(
        self,
        symbol: str,
        position: Dict,
        pos_state: PositionState
    ) -> Optional[ExitPlan]:
        """Run LLM-powered exit analysis."""
        try:
            current_price = position.get("current", 0)
            entry_price = pos_state.entry_price

            # Get technical data
            # Note: In production, get bars from Alpaca data client
            bars = await self._get_bars(symbol)
            atr = calculate_atr(bars) if bars else current_price * 0.02  # Default 2% ATR

            tech_signal = analyze_technical(symbol, current_price, bars) if bars else None
            technical_data = {
                "rsi": tech_signal.rsi if tech_signal else 50,
                "trend": tech_signal.trend if tech_signal else "neutral",
                "momentum": tech_signal.momentum if tech_signal else "flat",
                "sma_20": tech_signal.sma_20 if tech_signal else current_price,
                "sma_50": tech_signal.sma_50 if tech_signal else current_price,
            }

            # Run exit strategy agent
            exit_plan = await ExitStrategyAgent.analyze_with_cache(
                ticker=symbol,
                position={
                    "qty": position.get("qty"),
                    "unrealized_pl": position.get("pnl", 0),
                    "unrealized_plpc": position.get("pnl_pct", 0),
                },
                current_price=current_price,
                entry_price=entry_price,
                entry_thesis=pos_state.entry_thesis,
                days_held=pos_state.days_held,
                atr=atr,
                technical_data=technical_data,
                original_stop_loss=pos_state.original_stop_loss,
                original_take_profit=pos_state.original_take_profit,
            )

            # Update state
            pos_state.last_exit_analysis = exit_plan
            pos_state.last_analysis_time = datetime.utcnow()

            logger.info(
                f"{symbol}: Exit analysis - action={exit_plan.action.value}, "
                f"urgency={exit_plan.urgency.value}, score={exit_plan.score:.0f}"
            )

            return exit_plan

        except Exception as e:
            logger.error(f"{symbol}: Exit analysis failed: {e}")
            return None

    async def _execute_exit_plan(
        self,
        symbol: str,
        position: Dict,
        exit_plan: ExitPlan,
        pos_state: PositionState
    ):
        """Execute the exit plan recommendations."""
        action = exit_plan.action
        urgency = exit_plan.urgency

        logger.info(f"{symbol}: Executing exit plan - {action.value} ({urgency.value})")

        # Handle different exit actions
        if action == ExitAction.FULL_EXIT:
            if urgency in [ExitUrgency.IMMEDIATE, ExitUrgency.SOON]:
                await self._close_position(symbol, position, exit_plan.reasoning)
            else:
                logger.info(f"{symbol}: Full exit planned but not urgent, monitoring")

        elif action == ExitAction.PARTIAL_EXIT:
            pct = exit_plan.partial_exit_percent
            if pct > 0:
                await self._partial_exit(symbol, position, pct, exit_plan.reasoning)

        elif action == ExitAction.TAKE_PROFIT:
            # Check if we're at take profit level
            current_price = position.get("current", 0)
            for tp_level in exit_plan.take_profit_levels:
                if current_price >= tp_level:
                    await self._close_position(
                        symbol, position,
                        f"Take profit hit at ${tp_level:.2f}"
                    )
                    break

        elif action == ExitAction.TIGHTEN_STOP:
            new_stop = exit_plan.stop_loss
            if new_stop and new_stop != pos_state.current_stop_loss:
                await self._update_stop_loss(symbol, new_stop, pos_state)

        elif action == ExitAction.TRAIL_STOP:
            if exit_plan.trailing_stop.enabled:
                await self._activate_trailing_stop(
                    symbol, position, exit_plan.trailing_stop, pos_state
                )

        elif action == ExitAction.HOLD:
            logger.debug(f"{symbol}: Holding position per exit analysis")

    async def _check_simple_rules(
        self,
        symbol: str,
        position: Dict,
        pos_state: PositionState
    ):
        """Check simple exit rules without LLM - ATR-based + direction-aware."""
        current_price = position.get("current", 0)
        pnl_pct = position.get("pnl_pct", 0) * 100
        entry_price = pos_state.entry_price
        qty = float(position.get("qty", 0))
        is_short = qty < 0  # Negative qty = short position
        atr = pos_state.atr

        # ===== END-OF-DAY LIQUIDATION (No overnight holds) =====
        now_et = datetime.now(ZoneInfo("America/New_York"))
        market_close_warning = now_et.replace(hour=15, minute=50, second=0, microsecond=0)
        market_close_hard = now_et.replace(hour=15, minute=55, second=0, microsecond=0)
        is_market_day = now_et.weekday() < 5  # Mon-Fri

        if is_market_day and now_et >= market_close_hard:
            logger.warning(f"{symbol}: EOD LIQUIDATION - closing all positions before market close ({pnl_pct:+.1f}%)")
            await self._close_position(symbol, position, f"EOD liquidation: {pnl_pct:+.1f}% P&L")
            return

        if is_market_day and now_et >= market_close_warning:
            logger.info(f"{symbol}: Market closing soon - will liquidate at 3:55 PM ET ({pnl_pct:+.1f}%)")

        # ===== LOSS PROTECTION =====

        mins_held = (datetime.utcnow() - pos_state.entry_time).total_seconds() / 60
        hours_held = mins_held / 60

        # ATR-based stop loss (if ATR available)
        if atr and atr > 0 and current_price and entry_price:
            if is_short:
                # Short: stop if price >= entry + 1.2*ATR (price moving against us)
                atr_stop = entry_price + 1.2 * atr
                atr_tp = entry_price - 2.0 * atr
                if current_price >= atr_stop:
                    logger.warning(f"{symbol}: ATR stop (short) at ${current_price:.2f} >= ${atr_stop:.2f} (entry+1.2*ATR)")
                    await self._close_position(symbol, position, f"ATR stop (short): price ${current_price:.2f} >= ${atr_stop:.2f}")
                    return
                if current_price <= atr_tp and mins_held >= 60:
                    logger.info(f"{symbol}: ATR take-profit (short) at ${current_price:.2f} <= ${atr_tp:.2f}")
                    await self._close_position(symbol, position, f"ATR TP (short): ${current_price:.2f} <= ${atr_tp:.2f}")
                    return
            else:
                # Long: stop if price <= entry - 1.5*ATR
                atr_stop = entry_price - 1.5 * atr
                atr_tp = entry_price + 2.5 * atr
                if current_price <= atr_stop:
                    logger.warning(f"{symbol}: ATR stop (long) at ${current_price:.2f} <= ${atr_stop:.2f} (entry-1.5*ATR)")
                    await self._close_position(symbol, position, f"ATR stop (long): price ${current_price:.2f} <= ${atr_stop:.2f}")
                    return
                if current_price >= atr_tp and mins_held >= 60:
                    logger.info(f"{symbol}: ATR take-profit (long) at ${current_price:.2f} >= ${atr_tp:.2f}")
                    await self._close_position(symbol, position, f"ATR TP (long): ${current_price:.2f} >= ${atr_tp:.2f}")
                    return
        else:
            # Fallback: fixed % emergency stop when no ATR
            if pnl_pct < -5:
                logger.warning(f"{symbol}: Emergency stop triggered at {pnl_pct:.1f}%")
                await self._close_position(symbol, position, f"Emergency stop: {pnl_pct:.1f}% loss")
                return

        # ===== BREAKEVEN ARM (works inside the 60-min min-hold window) =====
        # Once a long is up +0.8% (or short up +0.8%), shift effective stop to entry.
        # Protects against giving back early gains while waiting for the full thesis to play out.
        if not pos_state.breakeven_armed and current_price and entry_price:
            arm_threshold = 0.8
            if (not is_short and pnl_pct >= arm_threshold) or (is_short and pnl_pct >= arm_threshold):
                pos_state.breakeven_armed = True
                logger.info(f"{symbol}: Breakeven armed at {pnl_pct:+.1f}% — stop now ${entry_price:.2f}")

        # If breakeven armed and we slip back to entry-or-worse, exit (preserves the won 0.8% as flat).
        if pos_state.breakeven_armed and current_price and entry_price:
            if not is_short and current_price <= entry_price:
                logger.info(f"{symbol}: Breakeven stop hit at ${current_price:.2f}")
                await self._close_position(symbol, position, f"Breakeven stop: {pnl_pct:+.1f}%")
                return
            if is_short and current_price >= entry_price:
                logger.info(f"{symbol}: Breakeven stop (short) hit at ${current_price:.2f}")
                await self._close_position(symbol, position, f"Breakeven stop (short): {pnl_pct:+.1f}%")
                return

        # Minimum hold time: 30 min before any non-emergency exit (was 60).
        # Tighter window prevents winners from EOD-decaying and lets stops act faster on losers.
        if mins_held < 30:
            if pnl_pct < -3:
                logger.info(f"{symbol}: Down {pnl_pct:.1f}% but only {mins_held:.0f}min held - holding (min 30min)")
            return

        # ===== PARTIAL SCALE-OUT @ +1R (locks half the win, lets rest ride trailing stop) =====
        if not pos_state.partial_taken and current_price and entry_price:
            # Use ATR-implied 1R if available, else +1.2% as proxy
            r_distance_pct = (atr / entry_price * 100) if atr else 1.2
            tp1_threshold = max(1.2, min(2.5, r_distance_pct))
            if (not is_short and pnl_pct >= tp1_threshold) or (is_short and pnl_pct >= tp1_threshold):
                logger.info(f"{symbol}: TP1 scale-out 50% at {pnl_pct:+.1f}% (threshold {tp1_threshold:.1f}%)")
                await self._partial_exit(symbol, position, 50.0, f"TP1 scale-out at {pnl_pct:+.1f}%")
                pos_state.partial_taken = True
                return

        # ===== PROFIT TAKING (fallback when no ATR TP hit) =====

        if not atr:
            if pnl_pct >= 5:
                logger.info(f"{symbol}: Taking profit at {pnl_pct:.1f}%")
                await self._close_position(symbol, position, f"Take profit: +{pnl_pct:.1f}%")
                return

        # ===== TRAILING STOP (ATR-based width when available) =====
        # Activates earlier (+1.5% instead of +2%) so we capture more on quick movers.
        trail_width = atr / current_price if atr and current_price else 0.015  # ATR-based or 1.5%
        trail_arm_pct = 1.5

        if is_short:
            # Short trailing: activate when price drops trail_arm_pct%+ below entry (profitable)
            if pnl_pct >= trail_arm_pct and not pos_state.trailing_stop_active and current_price and entry_price:
                pos_state.trailing_stop_active = True
                pos_state.trailing_stop_price = current_price * (1 + trail_width)
                logger.info(f"{symbol}: Trailing stop (short) activated at ${pos_state.trailing_stop_price:.2f}")

            if pos_state.trailing_stop_active and pos_state.trailing_stop_price:
                if current_price >= pos_state.trailing_stop_price:
                    logger.info(f"{symbol}: Trailing stop (short) hit at ${pos_state.trailing_stop_price:.2f}")
                    await self._close_position(symbol, position, "Trailing stop hit (short)")
                    return
                new_trail = current_price * (1 + trail_width)
                if new_trail < pos_state.trailing_stop_price:
                    pos_state.trailing_stop_price = new_trail
                    logger.info(f"{symbol}: Trailing stop (short) lowered to ${new_trail:.2f}")
        else:
            # Long trailing
            if pnl_pct >= trail_arm_pct and not pos_state.trailing_stop_active and current_price and entry_price:
                pos_state.trailing_stop_active = True
                pos_state.trailing_stop_price = current_price * (1 - trail_width)
                logger.info(f"{symbol}: Trailing stop activated at ${pos_state.trailing_stop_price:.2f}")

            if pos_state.trailing_stop_active and pos_state.trailing_stop_price:
                if current_price <= pos_state.trailing_stop_price:
                    logger.info(f"{symbol}: Trailing stop hit at ${pos_state.trailing_stop_price:.2f}")
                    await self._close_position(symbol, position, "Trailing stop hit")
                    return
                new_trail = current_price * (1 - trail_width)
                if new_trail > pos_state.trailing_stop_price:
                    pos_state.trailing_stop_price = new_trail
                    logger.info(f"{symbol}: Trailing stop raised to ${new_trail:.2f}")

        # Warn at 2 hours
        if hours_held >= 2 and hours_held < 2.5:
            logger.info(
                f"{symbol}: Position held {hours_held:.1f} hours, "
                f"P&L: {pnl_pct:.1f}% - monitoring for exit"
            )

    async def _close_position(
        self,
        symbol: str,
        position: Dict,
        reason: str
    ):
        """Close entire position with retry logic for stuck orders."""
        logger.info(f"{symbol}: CLOSING POSITION - {reason}")

        # Retry up to 5 times with increasing waits for broker to release shares
        max_retries = 5
        for attempt in range(max_retries):
            result = self.trader.close_position(symbol)

            if result.get("status") == "closed":
                pnl = result.get("pnl", position.get("pnl", 0))
                self.state.positions_closed += 1
                self.state.total_realized_pnl += pnl

                # Record completed trade for performance tracking
                pos_state = self.state.positions.get(symbol)
                if pos_state:
                    try:
                        from app.services.memory.memory_store import MemoryStore
                        store = MemoryStore()
                        current_price = position.get("current", 0)
                        qty = abs(float(position.get("qty", 0)))
                        is_short = float(position.get("qty", 0)) < 0
                        mins_held = (datetime.utcnow() - pos_state.entry_time).total_seconds() / 60
                        entry_val = pos_state.entry_price * qty
                        pnl_pct = (pnl / entry_val * 100) if entry_val > 0 else 0
                        trade_id = store.record_completed_trade(
                            ticker=symbol,
                            side="short" if is_short else "long",
                            entry_price=pos_state.entry_price,
                            exit_price=current_price,
                            entry_time=pos_state.entry_time.isoformat(),
                            exit_time=datetime.utcnow().isoformat(),
                            quantity=qty,
                            pnl=pnl,
                            pnl_pct=pnl_pct,
                            hold_time_minutes=mins_held,
                            score_at_entry=pos_state.score_at_entry,
                            atr_at_entry=pos_state.atr,
                            rvol_at_entry=pos_state.rvol_at_entry,
                            regime_at_entry=pos_state.regime_at_entry,
                            source=pos_state.source,
                            exit_reason=reason,
                        )
                        if trade_id and pnl_pct < 0:
                            from app.services.agents.loss_review_agent import LossReviewAgent
                            from app.services.memory.memory_store import LossPostmortem

                            similar_losses = store.get_similar_loss_postmortems(
                                ticker=symbol,
                                regime_at_entry=pos_state.regime_at_entry,
                                source=pos_state.source,
                                limit=5,
                            )
                            review = await LossReviewAgent.analyze(
                                ticker=symbol,
                                side="short" if is_short else "long",
                                entry_price=pos_state.entry_price,
                                exit_price=current_price,
                                pnl_pct=pnl_pct,
                                hold_time_minutes=mins_held,
                                score_at_entry=pos_state.score_at_entry,
                                atr_at_entry=pos_state.atr,
                                regime_at_entry=pos_state.regime_at_entry,
                                source=pos_state.source,
                                exit_reason=reason,
                                entry_thesis=pos_state.entry_thesis,
                                recent_similar_losses=[item.to_dict() for item in similar_losses],
                            )
                            store.store_loss_postmortem(
                                LossPostmortem(
                                    trade_id=trade_id,
                                    ticker=symbol,
                                    created_at=datetime.utcnow(),
                                    pnl_pct=pnl_pct,
                                    primary_cause=review.primary_cause,
                                    mistake_patterns=review.mistake_patterns,
                                    score_penalty=review.score_penalty,
                                    size_multiplier=review.size_multiplier,
                                    veto_future_similar=review.veto_future_similar,
                                    reasoning=review.reasoning,
                                    regime_at_entry=pos_state.regime_at_entry,
                                    source=pos_state.source,
                                    exit_reason=reason,
                                    hold_time_minutes=mins_held,
                                )
                            )
                    except Exception as e:
                        logger.warning(f"{symbol}: Failed to record completed trade: {e}")

                # Remove from tracking
                if symbol in self.state.positions:
                    del self.state.positions[symbol]

                logger.info(
                    f"{symbol}: Position closed, P&L: ${pnl:+,.2f}, "
                    f"Total closed: {self.state.positions_closed}"
                )

                # Log to trade journal
                await self._log_trade(symbol, "CLOSE", result, reason)
                return  # Success - exit the retry loop

            # Check if it's a "held_for_orders" error - retry with longer wait
            error_msg = str(result.get("message", ""))
            if "held_for_orders" in error_msg or "available" in error_msg:
                wait_time = (attempt + 1) * 3  # 3s, 6s, 9s, 12s, 15s
                logger.warning(
                    f"{symbol}: Shares held by orders, waiting {wait_time}s (attempt {attempt+1}/{max_retries})"
                )
                await asyncio.sleep(wait_time)
            else:
                # Different error - don't retry
                logger.error(f"{symbol}: Failed to close position: {result}")
                return

        # All retries exhausted
        logger.error(f"{symbol}: Failed to close after {max_retries} attempts - shares still held")

    async def _partial_exit(
        self,
        symbol: str,
        position: Dict,
        percent: float,
        reason: str
    ):
        """Partially exit a position."""
        qty = abs(float(position.get("qty", 0)))
        exit_qty = int(qty * (percent / 100))

        if exit_qty < 1:
            logger.info(f"{symbol}: Partial exit qty too small ({exit_qty}), skipping")
            return

        logger.info(f"{symbol}: PARTIAL EXIT {percent:.0f}% ({exit_qty} shares) - {reason}")

        result = self.trader.reduce_position(symbol, exit_qty)

        if result.get("status") == "reduced":
            self.state.positions_adjusted += 1
            logger.info(
                f"{symbol}: Partial exit complete, "
                f"remaining: {result.get('remaining_qty')} shares"
            )

            # Update position state
            if symbol in self.state.positions:
                self.state.positions[symbol].quantity = result.get("remaining_qty", 0)

            await self._log_trade(symbol, "PARTIAL_EXIT", result, reason)
        else:
            logger.error(f"{symbol}: Failed to reduce position: {result}")

    async def _update_stop_loss(
        self,
        symbol: str,
        new_stop: float,
        pos_state: PositionState
    ):
        """Update stop loss for a position."""
        old_stop = pos_state.current_stop_loss
        pos_state.current_stop_loss = new_stop
        self.state.positions_adjusted += 1

        old_str = f"${old_stop:.2f}" if old_stop else "none"
        logger.info(
            f"{symbol}: Stop loss updated: {old_str} -> ${new_stop:.2f}"
        )

        # Note: To actually update Alpaca order, we'd need to:
        # 1. Cancel existing stop order
        # 2. Create new stop order
        # For bracket orders, this is more complex
        # TODO: Implement Alpaca stop order management

    async def _activate_trailing_stop(
        self,
        symbol: str,
        position: Dict,
        trail_config,
        pos_state: PositionState
    ):
        """Activate trailing stop for a position."""
        current_price = position.get("current", 0)

        if trail_config.type == "percentage":
            trail_price = current_price * (1 - trail_config.distance / 100)
        elif trail_config.type == "fixed":
            trail_price = current_price - trail_config.distance
        else:  # ATR-based handled by distance already
            trail_price = current_price - trail_config.distance

        pos_state.trailing_stop_active = True
        pos_state.trailing_stop_price = trail_price
        self.state.positions_adjusted += 1

        logger.info(
            f"{symbol}: Trailing stop activated at ${trail_price:.2f} "
            f"({trail_config.type}, distance={trail_config.distance})"
        )

    async def _get_bars(self, symbol: str, limit: int = 50) -> List[Dict]:
        """Get historical bars for technical analysis."""
        # This would integrate with Alpaca data client
        # For now, return empty to use fallback
        try:
            if hasattr(self.trader, 'data_client') and self.trader.data_client:
                from alpaca.data.requests import StockBarsRequest
                from alpaca.data.timeframe import TimeFrame

                request = StockBarsRequest(
                    symbol_or_symbols=symbol,
                    timeframe=TimeFrame.Day,
                    limit=limit
                )
                bars = self.trader.data_client.get_stock_bars(request)
                if bars and symbol in bars:
                    return [
                        {
                            "open": b.open,
                            "high": b.high,
                            "low": b.low,
                            "close": b.close,
                            "volume": b.volume
                        }
                        for b in bars[symbol]
                    ]
        except Exception as e:
            logger.debug(f"Could not get bars for {symbol}: {e}")

        return []

    async def _log_trade(
        self,
        symbol: str,
        action: str,
        result: Dict,
        reason: str
    ):
        """Log trade to journal."""
        # This integrates with your trade journal
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "symbol": symbol,
            "action": action,
            "reason": reason,
            "result": result,
            "manager_stats": {
                "positions_closed": self.state.positions_closed,
                "total_realized_pnl": self.state.total_realized_pnl,
            }
        }

        logger.info(f"Trade logged: {log_entry}")
        # TODO: Write to trade journal file/database

    def get_status(self) -> Dict[str, Any]:
        """Get current position manager status."""
        return {
            "running": self._running,
            "run_count": self.state.run_count,
            "last_run": self.state.last_run.isoformat() if self.state.last_run else None,
            "positions_tracked": len(self.state.positions),
            "positions_closed": self.state.positions_closed,
            "positions_adjusted": self.state.positions_adjusted,
            "total_realized_pnl": self.state.total_realized_pnl,
            "tracked_positions": {
                symbol: {
                    "entry_price": ps.entry_price,
                    "days_held": ps.days_held,
                    "trailing_stop_active": ps.trailing_stop_active,
                    "trailing_stop_price": ps.trailing_stop_price,
                    "last_analysis": ps.last_exit_analysis.action.value if ps.last_exit_analysis else None,
                }
                for symbol, ps in self.state.positions.items()
            },
            "check_interval": self.check_interval,
            "min_analysis_interval": self.min_analysis_interval,
        }

    def register_entry(
        self,
        symbol: str,
        entry_price: float,
        quantity: float,
        thesis: Optional[str] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        atr: Optional[float] = None,
        score_at_entry: Optional[float] = None,
        rvol_at_entry: Optional[float] = None,
        regime_at_entry: Optional[str] = None,
        source: Optional[str] = None,
    ):
        """
        Register a new position entry for tracking.

        Call this when a trade is executed to track it properly.
        """
        self.state.positions[symbol] = PositionState(
            symbol=symbol,
            entry_price=entry_price,
            entry_time=datetime.utcnow(),
            quantity=quantity,
            entry_thesis=thesis,
            original_stop_loss=stop_loss,
            original_take_profit=take_profit,
            current_stop_loss=stop_loss,
            atr=atr,
            score_at_entry=score_at_entry,
            rvol_at_entry=rvol_at_entry,
            regime_at_entry=regime_at_entry,
            source=source,
        )

        stop_str = f"${stop_loss:.2f}" if stop_loss else "none"
        target_str = f"${take_profit:.2f}" if take_profit else "none"
        atr_str = f"${atr:.2f}" if atr else "none"
        logger.info(
            f"Registered entry: {symbol} @ ${entry_price:.2f}, "
            f"qty={quantity}, stop={stop_str}, target={target_str}, "
            f"atr={atr_str}, score={score_at_entry}, regime={regime_at_entry}, source={source}"
        )


# Global instance
position_manager: Optional[PositionManager] = None


def get_position_manager() -> Optional[PositionManager]:
    """Get the global position manager instance."""
    return position_manager


def init_position_manager(
    check_interval: int = 30,
    min_analysis_interval: int = 60,
) -> PositionManager:
    """Initialize the global position manager."""
    global position_manager
    position_manager = PositionManager(
        check_interval=check_interval,
        min_analysis_interval=min_analysis_interval,
    )
    return position_manager
