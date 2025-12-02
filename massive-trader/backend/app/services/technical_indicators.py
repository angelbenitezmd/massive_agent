"""
Pure Python Technical Indicators.

This module provides technical analysis WITHOUT LLM dependency.
The main loop can calculate these cheaply every minute.
LLMs should only be called when regime/score changes significantly.
"""
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class TechnicalRegime(Enum):
    """Market regime classification."""
    STRONG_BULLISH = "strong_bullish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    STRONG_BEARISH = "strong_bearish"


@dataclass
class TechnicalSignal:
    """Technical analysis signal without LLM."""
    ticker: str
    score: float  # 0-100, 50 is neutral
    regime: TechnicalRegime
    trend: str  # "bullish", "bearish", "neutral"
    momentum: str  # "increasing", "decreasing", "flat"
    confidence: float  # 0-100

    # Individual indicators
    rsi: Optional[float] = None
    rsi_signal: str = "neutral"

    macd_value: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    macd_crossover: str = "neutral"

    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    ma_alignment: str = "mixed"

    # Price levels
    support: Optional[float] = None
    resistance: Optional[float] = None

    # Summary
    signals: List[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "ticker": self.ticker,
            "score": round(self.score, 1),
            "regime": self.regime.value,
            "trend": self.trend,
            "momentum": self.momentum,
            "confidence": round(self.confidence, 1),
            "rsi": round(self.rsi, 2) if self.rsi else None,
            "rsi_signal": self.rsi_signal,
            "macd": {
                "value": round(self.macd_value, 4) if self.macd_value else None,
                "signal": round(self.macd_signal, 4) if self.macd_signal else None,
                "histogram": round(self.macd_histogram, 4) if self.macd_histogram else None,
            },
            "macd_crossover": self.macd_crossover,
            "moving_averages": {
                "sma_20": round(self.sma_20, 2) if self.sma_20 else None,
                "sma_50": round(self.sma_50, 2) if self.sma_50 else None,
                "sma_200": round(self.sma_200, 2) if self.sma_200 else None,
            },
            "ma_alignment": self.ma_alignment,
            "support": round(self.support, 2) if self.support else None,
            "resistance": round(self.resistance, 2) if self.resistance else None,
            "signals": self.signals or [],
            "provider": "local_python",  # No LLM used
        }


def calculate_rsi(closes: List[float], period: int = 14) -> Optional[float]:
    """
    Calculate Relative Strength Index.

    Args:
        closes: List of closing prices (oldest first)
        period: RSI period (default 14)

    Returns:
        RSI value (0-100) or None if insufficient data
    """
    if len(closes) < period + 1:
        return None

    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]

    # Use exponential moving average for smoother RSI
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calculate_ema(data: List[float], period: int) -> List[float]:
    """
    Calculate Exponential Moving Average.

    Args:
        data: List of values
        period: EMA period

    Returns:
        List of EMA values
    """
    if len(data) < period:
        return []

    multiplier = 2 / (period + 1)
    ema_values = [sum(data[:period]) / period]  # Start with SMA

    for price in data[period:]:
        ema_values.append((price * multiplier) + (ema_values[-1] * (1 - multiplier)))

    return ema_values


def calculate_sma(data: List[float], period: int) -> Optional[float]:
    """
    Calculate Simple Moving Average.

    Args:
        data: List of values
        period: SMA period

    Returns:
        SMA value or None if insufficient data
    """
    if len(data) < period:
        return None
    return sum(data[-period:]) / period


def calculate_macd(
    closes: List[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Calculate MACD (Moving Average Convergence Divergence).

    Args:
        closes: List of closing prices
        fast_period: Fast EMA period (default 12)
        slow_period: Slow EMA period (default 26)
        signal_period: Signal line period (default 9)

    Returns:
        Tuple of (MACD line, Signal line, Histogram)
    """
    if len(closes) < slow_period + signal_period:
        return None, None, None

    fast_ema = calculate_ema(closes, fast_period)
    slow_ema = calculate_ema(closes, slow_period)

    if not fast_ema or not slow_ema:
        return None, None, None

    # Align the EMAs
    offset = slow_period - fast_period
    macd_line = [
        fast_ema[i + offset] - slow_ema[i]
        for i in range(len(slow_ema))
    ]

    if len(macd_line) < signal_period:
        return None, None, None

    # Calculate signal line
    signal_ema = calculate_ema(macd_line, signal_period)
    if not signal_ema:
        return None, None, None

    macd_value = macd_line[-1]
    signal_value = signal_ema[-1]
    histogram = macd_value - signal_value

    return macd_value, signal_value, histogram


def calculate_support_resistance(
    highs: List[float],
    lows: List[float],
    current_price: float,
    lookback: int = 20
) -> Tuple[Optional[float], Optional[float]]:
    """
    Calculate simple support and resistance levels.

    Uses recent swing highs/lows as S/R levels.

    Args:
        highs: List of high prices
        lows: List of low prices
        current_price: Current price
        lookback: Period to look back

    Returns:
        Tuple of (support, resistance)
    """
    if len(highs) < lookback or len(lows) < lookback:
        return None, None

    recent_highs = highs[-lookback:]
    recent_lows = lows[-lookback:]

    # Find nearest support (highest low below current price)
    supports = [l for l in recent_lows if l < current_price]
    support = max(supports) if supports else min(recent_lows)

    # Find nearest resistance (lowest high above current price)
    resistances = [h for h in recent_highs if h > current_price]
    resistance = min(resistances) if resistances else max(recent_highs)

    return support, resistance


def analyze_technical(
    ticker: str,
    current_price: float,
    bars: List[Dict[str, Any]],
) -> TechnicalSignal:
    """
    Perform technical analysis using pure Python (no LLM).

    This should run every minute as part of the main loop.
    It's cheap and doesn't require LLM calls.

    Args:
        ticker: Stock ticker
        current_price: Current stock price
        bars: List of price bars with open, high, low, close, volume

    Returns:
        TechnicalSignal with all indicators and regime classification
    """
    ticker = ticker.upper()
    signals = []
    score = 50  # Start neutral

    # Extract price data
    closes = [b.get("close", 0) for b in bars if b.get("close")]
    highs = [b.get("high", 0) for b in bars if b.get("high")]
    lows = [b.get("low", 0) for b in bars if b.get("low")]
    volumes = [b.get("volume", 0) for b in bars if b.get("volume")]

    # Calculate RSI
    rsi = calculate_rsi(closes)
    rsi_signal = "neutral"
    if rsi is not None:
        if rsi > 70:
            rsi_signal = "overbought"
            score -= 10
            signals.append(f"RSI overbought ({rsi:.1f})")
        elif rsi > 60:
            rsi_signal = "slightly_overbought"
            score -= 5
        elif rsi < 30:
            rsi_signal = "oversold"
            score += 10
            signals.append(f"RSI oversold ({rsi:.1f})")
        elif rsi < 40:
            rsi_signal = "slightly_oversold"
            score += 5

    # Calculate MACD
    macd_value, macd_signal_line, macd_histogram = calculate_macd(closes)
    macd_crossover = "neutral"
    if macd_value is not None and macd_signal_line is not None:
        if macd_histogram > 0:
            if macd_value > 0:
                macd_crossover = "bullish"
                score += 10
                signals.append("MACD bullish above zero")
            else:
                macd_crossover = "bullish_below_zero"
                score += 5
                signals.append("MACD turning bullish")
        else:
            if macd_value < 0:
                macd_crossover = "bearish"
                score -= 10
                signals.append("MACD bearish below zero")
            else:
                macd_crossover = "bearish_above_zero"
                score -= 5
                signals.append("MACD turning bearish")

    # Calculate Moving Averages
    sma_20 = calculate_sma(closes, 20)
    sma_50 = calculate_sma(closes, 50)
    sma_200 = calculate_sma(closes, 200) if len(closes) >= 200 else None

    ma_alignment = "mixed"
    if sma_20 and sma_50:
        if current_price > sma_20 > sma_50:
            ma_alignment = "bullish"
            score += 15
            signals.append("Price above rising MAs (bullish)")
        elif current_price < sma_20 < sma_50:
            ma_alignment = "bearish"
            score -= 15
            signals.append("Price below falling MAs (bearish)")
        elif current_price > sma_20 and sma_20 < sma_50:
            ma_alignment = "recovering"
            score += 5
        elif current_price < sma_20 and sma_20 > sma_50:
            ma_alignment = "weakening"
            score -= 5

        # Check for golden/death cross
        if sma_200:
            if sma_50 > sma_200 and sma_20 > sma_50:
                score += 10
                signals.append("Golden cross alignment (bullish)")
            elif sma_50 < sma_200 and sma_20 < sma_50:
                score -= 10
                signals.append("Death cross alignment (bearish)")

    # Calculate Support/Resistance
    support, resistance = calculate_support_resistance(
        highs, lows, current_price
    )

    # Price relative to S/R
    if support and resistance:
        price_range = resistance - support
        if price_range > 0:
            position = (current_price - support) / price_range
            if position > 0.9:
                signals.append("Near resistance - caution")
                score -= 5
            elif position < 0.1:
                signals.append("Near support - potential bounce")
                score += 5

    # Determine momentum from recent price action
    momentum = "flat"
    if len(closes) >= 5:
        recent_change = (closes[-1] - closes[-5]) / closes[-5] * 100
        if recent_change > 2:
            momentum = "increasing"
            score += 5
        elif recent_change < -2:
            momentum = "decreasing"
            score -= 5

    # Volume trend (if available)
    if len(volumes) >= 10:
        recent_vol = sum(volumes[-5:]) / 5
        older_vol = sum(volumes[-10:-5]) / 5
        if recent_vol > older_vol * 1.5:
            signals.append("Volume expanding")
            # Volume confirms direction
            if score > 50:
                score += 5
            elif score < 50:
                score -= 5

    # Clamp score
    score = max(0, min(100, score))

    # Determine trend and regime
    if score >= 70:
        trend = "bullish"
        regime = TechnicalRegime.STRONG_BULLISH
    elif score >= 60:
        trend = "bullish"
        regime = TechnicalRegime.BULLISH
    elif score <= 30:
        trend = "bearish"
        regime = TechnicalRegime.STRONG_BEARISH
    elif score <= 40:
        trend = "bearish"
        regime = TechnicalRegime.BEARISH
    else:
        trend = "neutral"
        regime = TechnicalRegime.NEUTRAL

    # Calculate confidence based on signal agreement
    confidence = min(100, 50 + abs(score - 50))

    return TechnicalSignal(
        ticker=ticker,
        score=score,
        regime=regime,
        trend=trend,
        momentum=momentum,
        confidence=confidence,
        rsi=rsi,
        rsi_signal=rsi_signal,
        macd_value=macd_value,
        macd_signal=macd_signal_line,
        macd_histogram=macd_histogram,
        macd_crossover=macd_crossover,
        sma_20=sma_20,
        sma_50=sma_50,
        sma_200=sma_200,
        ma_alignment=ma_alignment,
        support=support,
        resistance=resistance,
        signals=signals,
    )


def get_regime_string(regime: TechnicalRegime) -> str:
    """Convert regime to simple string for comparison."""
    if regime in [TechnicalRegime.STRONG_BULLISH, TechnicalRegime.BULLISH]:
        return "bullish"
    elif regime in [TechnicalRegime.STRONG_BEARISH, TechnicalRegime.BEARISH]:
        return "bearish"
    return "neutral"


def calculate_scanner_score(
    technical: TechnicalSignal,
    momentum_score: float,
    sentiment_score: float,
) -> float:
    """
    Calculate combined scanner score from multiple signals.

    This is the quick score used for the main loop scanner.
    No LLM required.

    Args:
        technical: Technical analysis signal
        momentum_score: Momentum score (0-100)
        sentiment_score: Sentiment score (0-100)

    Returns:
        Combined score (0-100)
    """
    # Weight: Technical 40%, Momentum 40%, Sentiment 20%
    # (Sentiment is keyword-based, less reliable without LLM)
    combined = (
        technical.score * 0.40 +
        momentum_score * 0.40 +
        sentiment_score * 0.20
    )
    return round(combined, 1)
