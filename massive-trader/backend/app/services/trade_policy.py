"""Trade gating, risk/reward planning, and decision metrics for auto-trading."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


STRICT_BUY_MIN_SCORE = 72.0
STRICT_BUY_MIN_AI_SCORE = 62.0
STRICT_BUY_MIN_MOMENTUM_SCORE = 52.0
STRICT_BUY_MIN_MOMENTUM_SCORE_EARLY = 47.0  # calm tape + fresh catalyst: do not require a big green day
STRICT_BUY_MAX_VOLATILITY_PCT = 5.0
STRICT_BUY_MIN_AGREEMENT = 2

STRICT_BUY_MIN_TECHNICAL_SCORE = 50.0
STRICT_BUY_MAX_RSI = 75.0
STRICT_BUY_MIN_RELATIVE_VOLUME = 0.70
STRICT_BUY_MIN_RISK_REWARD = 1.5
STRICT_BUY_MIN_RESISTANCE_ROOM_PCT = 0.012
STRICT_BUY_MIN_SETUP_SCORE = 70.0
FRESH_CATALYST_MAX_AGE_HOURS = 2.5
VERY_FRESH_CATALYST_MAX_AGE_HOURS = 0.85

# Minimum stock price to avoid volatile penny stocks
MIN_STOCK_PRICE = 25.0


def _clamp(value: float, lower: float, upper: float) -> float:
    """Clamp a float into a fixed range."""
    return max(lower, min(upper, value))


def _has_fresh_catalyst(news_age_hours: Optional[float], ai_score: float) -> bool:
    """Fresh headlines deserve faster entries than stale confirmation."""
    return bool(
        news_age_hours is not None
        and news_age_hours <= FRESH_CATALYST_MAX_AGE_HOURS
        and ai_score >= 64
    )


def _has_very_fresh_catalyst(news_age_hours: Optional[float], ai_score: float) -> bool:
    """Very recent headlines can justify entering before full technical catch-up."""
    return bool(
        news_age_hours is not None
        and news_age_hours <= VERY_FRESH_CATALYST_MAX_AGE_HOURS
        and ai_score >= 65
    )


def _setup_momentum_signal(
    momentum_score: float,
    price_change_pct: float,
    ai_score: float,
) -> float:
    """De-emphasize chase; lift momentum when tape is calm but AI is hot (early window)."""
    m = float(momentum_score)
    if -1.2 <= price_change_pct <= 1.4 and ai_score >= 62:
        m = max(m, 56.0)
    if price_change_pct > 2.35:
        m -= (price_change_pct - 2.35) * 7.0
    return round(_clamp(m, 5.0, 95.0), 1)


def calculate_atr(bars: List[Dict[str, Any]], period: int = 14) -> float:
    """Calculate ATR from OHLC bars."""
    if len(bars) < period + 1:
        return 0.0

    true_ranges: List[float] = []
    for i in range(1, len(bars)):
        high = float(bars[i].get("high", 0) or 0)
        low = float(bars[i].get("low", 0) or 0)
        prev_close = float(bars[i - 1].get("close", 0) or 0)
        if high <= 0 or low <= 0 or prev_close <= 0:
            continue
        true_ranges.append(
            max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close),
            )
        )

    if not true_ranges:
        return 0.0
    if len(true_ranges) < period:
        return sum(true_ranges) / len(true_ranges)
    return sum(true_ranges[-period:]) / period


def calculate_relative_volume(
    bars: List[Dict[str, Any]],
    recent_window: int = 5,
    baseline_window: int = 20,
) -> Optional[float]:
    """Estimate relative volume from recent bars."""
    if len(bars) < max(recent_window, baseline_window):
        return None

    recent = [
        float(bar.get("volume", 0) or 0)
        for bar in bars[-recent_window:]
        if float(bar.get("volume", 0) or 0) > 0
    ]
    baseline = [
        float(bar.get("volume", 0) or 0)
        for bar in bars[-baseline_window:]
        if float(bar.get("volume", 0) or 0) > 0
    ]
    if not recent or not baseline:
        return None

    baseline_avg = sum(baseline) / len(baseline)
    if baseline_avg <= 0:
        return None

    recent_avg = sum(recent) / len(recent)
    return round(recent_avg / baseline_avg, 2)


def calculate_vwap(bars: List[Dict[str, Any]]) -> Optional[float]:
    """Estimate VWAP from intraday bars."""
    if not bars:
        return None

    total_pv = 0.0
    total_volume = 0.0
    for bar in bars:
        volume = float(bar.get("volume", 0) or 0)
        if volume <= 0:
            continue
        high = float(bar.get("high", 0) or 0)
        low = float(bar.get("low", 0) or 0)
        close = float(bar.get("close", 0) or 0)
        typical = ((high + low + close) / 3.0) if high and low and close else close
        if typical <= 0:
            continue
        total_pv += typical * volume
        total_volume += volume

    if total_volume <= 0:
        return None
    return round(total_pv / total_volume, 4)


def assess_entry_timing(
    *,
    price: float,
    bars: Optional[List[Dict[str, Any]]] = None,
    price_change_pct: float = 0.0,
    ai_score: float = 50.0,
    momentum_score: float = 50.0,
    news_age_hours: Optional[float] = None,
) -> Dict[str, Any]:
    """Judge whether the current tape is early, acceptable, or already extended."""
    bars = bars or []
    vwap = calculate_vwap(bars)
    session_high = max((float(bar.get("high", 0) or 0) for bar in bars), default=0.0)
    session_low = min((float(bar.get("low", 0) or 0) for bar in bars if float(bar.get("low", 0) or 0) > 0), default=0.0)

    price_vs_vwap_pct = None
    if vwap and vwap > 0 and price > 0:
        price_vs_vwap_pct = round(((price - vwap) / vwap) * 100, 2)

    session_range_position = None
    if session_high > session_low > 0 and price > 0:
        session_range_position = round((price - session_low) / (session_high - session_low), 3)

    fresh_catalyst = _has_fresh_catalyst(news_age_hours, ai_score)
    very_fresh = _has_very_fresh_catalyst(news_age_hours, ai_score)
    underreacted_tape = (
        -0.8 <= price_change_pct <= 1.2
        and (price_vs_vwap_pct is None or price_vs_vwap_pct <= 0.9)
        and (session_range_position is None or session_range_position <= 0.78)
    )

    timing_score = 50.0
    reasons: List[str] = []

    if fresh_catalyst and underreacted_tape:
        timing_score += 22.0
        reasons.append("fresh_catalyst_underreacted")
    elif fresh_catalyst and -1.0 <= price_change_pct <= 1.6:
        timing_score += 12.0
        reasons.append("fresh_catalyst_not_extended")
    if very_fresh and underreacted_tape:
        timing_score += 8.0
        reasons.append("very_fresh_window")
    if price_vs_vwap_pct is not None:
        if price_vs_vwap_pct <= 0.25 and ai_score >= 68:
            timing_score += 5.0
            reasons.append("near_vwap_entry")
        elif price_vs_vwap_pct > 1.45:
            timing_score -= 14.0
        elif price_vs_vwap_pct > 0.95:
            timing_score -= 8.0
    if session_range_position is not None:
        if session_range_position <= 0.68 and fresh_catalyst:
            timing_score += 5.0
            reasons.append("before_range_expansion")
        elif session_range_position >= 0.92:
            timing_score -= 14.0
        elif session_range_position >= 0.84 and price_change_pct > 0.8:
            timing_score -= 9.0
    if price_change_pct > 1.8:
        timing_score -= 8.0
    if price_change_pct > 2.8:
        timing_score -= 12.0
    if news_age_hours is not None and news_age_hours > 4 and price_change_pct > 0.8:
        timing_score -= 7.0
    if fresh_catalyst and 44 <= momentum_score <= 60:
        timing_score += 4.0
        reasons.append("momentum_early_but_acceptable")

    timing_score = round(_clamp(timing_score, 0.0, 100.0), 1)

    timing_state = "standard"
    if fresh_catalyst and underreacted_tape and timing_score >= 60:
        timing_state = "early"
    if (
        price_change_pct > 1.9
        or (price_vs_vwap_pct is not None and price_vs_vwap_pct > 0.95)
        or (session_range_position is not None and session_range_position > 0.84)
    ):
        timing_state = "late"
    if (
        price_change_pct > 2.9
        or (price_vs_vwap_pct is not None and price_vs_vwap_pct > 1.45)
        or (session_range_position is not None and session_range_position > 0.92)
    ):
        timing_state = "extended"

    late_entry_risk = 0.0
    if timing_state == "late":
        late_entry_risk = 68.0
    elif timing_state == "extended":
        late_entry_risk = 86.0
    elif timing_state == "early":
        late_entry_risk = 14.0
    else:
        late_entry_risk = 42.0

    return {
        "vwap": vwap,
        "price_vs_vwap_pct": price_vs_vwap_pct,
        "session_high": round(session_high, 2) if session_high else None,
        "session_low": round(session_low, 2) if session_low else None,
        "session_range_position": session_range_position,
        "timing_score": timing_score,
        "timing_state": timing_state,
        "timing_reasons": reasons[:4],
        "fresh_catalyst": fresh_catalyst,
        "late_entry_risk": late_entry_risk,
    }


def build_trade_levels(
    *,
    price: float,
    bars: Optional[List[Dict[str, Any]]] = None,
    support: Optional[float] = None,
    resistance: Optional[float] = None,
    technical_score: Optional[float] = None,
    relative_volume: Optional[float] = None,
) -> Dict[str, Any]:
    """Derive stop, target, and sizing hints from volatility and nearby levels."""
    bars = bars or []
    atr = calculate_atr(bars)
    atr_pct = (atr / price) if price > 0 and atr > 0 else 0.0
    if relative_volume is None:
        relative_volume = calculate_relative_volume(bars)

    support_room_pct = (
        (price - support) / price
        if price > 0 and support is not None and 0 < support < price
        else None
    )
    resistance_room_pct = (
        (resistance - price) / price
        if price > 0 and resistance is not None and resistance > price
        else None
    )

    volatility_stop_pct = _clamp(max(0.018, atr_pct * 2.0 if atr_pct else 0.025), 0.018, 0.08)
    support_stop_pct = None
    if support_room_pct is not None:
        support_stop_pct = _clamp(support_room_pct + 0.005, 0.018, 0.08)

    stop_pct = max(volatility_stop_pct, support_stop_pct or 0.0)
    if technical_score is not None and technical_score < 55:
        stop_pct = _clamp(stop_pct * 1.10, 0.018, 0.08)

    target_pct = max(stop_pct * 2.0, 0.03)
    if resistance_room_pct is not None:
        if resistance_room_pct >= stop_pct * 1.5:
            target_pct = max(target_pct, resistance_room_pct * 0.85)
        else:
            target_pct = max(resistance_room_pct * 0.9, stop_pct * 1.5)
        target_pct = min(target_pct, 0.18)
    else:
        fallback_target = atr_pct * 3.0 if atr_pct else 0.04
        target_pct = min(max(target_pct, fallback_target), 0.18)

    risk_reward_ratio = round(target_pct / stop_pct, 2) if stop_pct > 0 else 0.0

    size_multiplier = 0.75
    if risk_reward_ratio >= 2.4:
        size_multiplier += 0.15
    elif risk_reward_ratio < STRICT_BUY_MIN_RISK_REWARD:
        size_multiplier -= 0.15

    if technical_score is not None:
        size_multiplier += _clamp((technical_score - 60) / 80, -0.15, 0.15)

    if relative_volume is not None:
        if relative_volume >= 1.4:
            size_multiplier += 0.08
        elif relative_volume < 0.8:
            size_multiplier -= 0.12

    size_multiplier = _clamp(size_multiplier, 0.4, 1.1)

    return {
        "atr": round(atr, 4) if atr else 0.0,
        "atr_pct": round(atr_pct * 100, 2) if atr_pct else 0.0,
        "stop_pct": round(stop_pct * 100, 2),
        "target_pct": round(target_pct * 100, 2),
        "stop_loss": round(price * (1 - stop_pct), 2) if price > 0 else 0.0,
        "take_profit": round(price * (1 + target_pct), 2) if price > 0 else 0.0,
        "risk_reward_ratio": risk_reward_ratio,
        "support_room_pct": round((support_room_pct or 0.0) * 100, 2),
        "resistance_room_pct": round((resistance_room_pct or 0.0) * 100, 2),
        "relative_volume": relative_volume,
        "size_multiplier": round(size_multiplier, 2),
    }


def evaluate_buy_gate(
    combined_score: float,
    ai_score: float,
    momentum_score: float,
    price_change_pct: float,
    momentum_warning: bool = False,
    technical_score: Optional[float] = None,
    technical_regime: Optional[str] = None,
    technical_rsi: Optional[float] = None,
    relative_volume: Optional[float] = None,
    resistance_room_pct: Optional[float] = None,
    risk_reward_ratio: Optional[float] = None,
    llm_enhanced: Optional[bool] = None,
    price: Optional[float] = None,
    news_age_hours: Optional[float] = None,
    entry_timing_score: Optional[float] = None,
    entry_timing_state: Optional[str] = None,
    price_vs_vwap_pct: Optional[float] = None,
    session_range_position: Optional[float] = None,
) -> Dict[str, Any]:
    """Apply strict BUY gating to reduce low-quality entries."""
    fresh_catalyst = (
        _has_fresh_catalyst(news_age_hours, ai_score)
        and -1.2 <= price_change_pct <= 1.6
    )
    very_fresh = _has_very_fresh_catalyst(news_age_hours, ai_score)
    early_entry = bool(
        fresh_catalyst
        and entry_timing_state == "early"
        and -1.0 <= price_change_pct <= 1.25
    )
    price_ok = price is None or price >= MIN_STOCK_PRICE
    score_min = (
        STRICT_BUY_MIN_SCORE - 4.0
        if early_entry
        else (STRICT_BUY_MIN_SCORE - 2.0 if fresh_catalyst else STRICT_BUY_MIN_SCORE)
    )
    score_ok = combined_score >= score_min
    ai_min = STRICT_BUY_MIN_AI_SCORE - 2.0 if early_entry and very_fresh else STRICT_BUY_MIN_AI_SCORE
    ai_ok = ai_score >= ai_min
    early_tape = (
        price_change_pct is not None
        and -1.2 <= price_change_pct <= 1.5
        and ai_score >= 62
    )
    if early_entry:
        mom_need = max(44.0, STRICT_BUY_MIN_MOMENTUM_SCORE_EARLY - 3.0)
    else:
        mom_need = STRICT_BUY_MIN_MOMENTUM_SCORE_EARLY if early_tape else STRICT_BUY_MIN_MOMENTUM_SCORE
    momentum_ok = momentum_score >= mom_need
    volatility_ok = abs(price_change_pct) <= STRICT_BUY_MAX_VOLATILITY_PCT
    warning_ok = not momentum_warning

    technical_min = (
        STRICT_BUY_MIN_TECHNICAL_SCORE - 8.0
        if early_entry
        else (STRICT_BUY_MIN_TECHNICAL_SCORE - 5.0 if fresh_catalyst else STRICT_BUY_MIN_TECHNICAL_SCORE)
    )
    rsi_max = (
        STRICT_BUY_MAX_RSI + 7.0
        if early_entry
        else (STRICT_BUY_MAX_RSI + 5.0 if fresh_catalyst else STRICT_BUY_MAX_RSI)
    )
    timing_min = 55.0 if early_entry else (44.0 if fresh_catalyst else 50.0)

    technical_ok = technical_score is None or technical_score >= technical_min
    regime_ok = technical_regime is None or technical_regime not in {"bearish", "strong_bearish"}
    rsi_ok = technical_rsi is None or technical_rsi <= rsi_max
    timing_ok = entry_timing_score is None or entry_timing_score >= timing_min
    vwap_extension_ok = price_vs_vwap_pct is None or price_vs_vwap_pct <= (0.95 if early_entry else (1.2 if fresh_catalyst else 1.0))
    session_position_ok = session_range_position is None or session_range_position <= (0.82 if early_entry else (0.88 if fresh_catalyst else 0.84))
    volume_ok = relative_volume is None or relative_volume >= STRICT_BUY_MIN_RELATIVE_VOLUME
    resistance_ok = (
        resistance_room_pct is None or resistance_room_pct >= STRICT_BUY_MIN_RESISTANCE_ROOM_PCT * 100
    )
    risk_reward_ok = risk_reward_ratio is None or risk_reward_ratio >= STRICT_BUY_MIN_RISK_REWARD
    llm_ok = llm_enhanced is None or llm_enhanced

    bullish_votes = (
        int(score_ok)
        + int(ai_ok)
        + int(momentum_ok)
        + int(technical_ok)
        + int(timing_ok)
        + int(risk_reward_ok)
        + int(volume_ok)
    )
    agreement_required = STRICT_BUY_MIN_AGREEMENT if technical_score is None else (3 if fresh_catalyst else 4)
    agreement_ok = bullish_votes >= agreement_required

    passed = (
        price_ok
        and score_ok
        and ai_ok
        and momentum_ok
        and agreement_ok
        and volatility_ok
        and warning_ok
        and technical_ok
        and regime_ok
        and rsi_ok
        and timing_ok
        and vwap_extension_ok
        and session_position_ok
        and volume_ok
        and resistance_ok
        and risk_reward_ok
        and llm_ok
    )

    reasons = []
    if not price_ok:
        reasons.append(f"price_below_${MIN_STOCK_PRICE:.0f}_minimum")
    if not score_ok:
        reasons.append("score_below_threshold")
    if not ai_ok:
        reasons.append("ai_score_below_threshold")
    if not momentum_ok:
        reasons.append("momentum_below_threshold")
    if not technical_ok:
        reasons.append("technical_score_below_threshold")
    if not regime_ok:
        reasons.append("bearish_regime")
    if not rsi_ok:
        reasons.append("rsi_too_hot")
    if not timing_ok:
        reasons.append("timing_score_too_low")
    if not vwap_extension_ok:
        reasons.append("too_far_above_vwap")
    if not session_position_ok:
        reasons.append("near_session_high_chase")
    if not volume_ok:
        reasons.append("relative_volume_too_low")
    if not resistance_ok:
        reasons.append("resistance_too_close")
    if not risk_reward_ok:
        reasons.append("risk_reward_too_low")
    if not agreement_ok:
        reasons.append("insufficient_agent_agreement")
    if not volatility_ok:
        reasons.append("volatility_too_high")
    if not warning_ok:
        reasons.append("momentum_warning")
    if not llm_ok:
        reasons.append("llm_confirmation_required")

    return {
        "passed": passed,
        "price_ok": price_ok,
        "score_ok": score_ok,
        "ai_ok": ai_ok,
        "momentum_ok": momentum_ok,
        "technical_ok": technical_ok,
        "regime_ok": regime_ok,
        "rsi_ok": rsi_ok,
        "timing_ok": timing_ok,
        "vwap_extension_ok": vwap_extension_ok,
        "session_position_ok": session_position_ok,
        "volume_ok": volume_ok,
        "resistance_ok": resistance_ok,
        "risk_reward_ok": risk_reward_ok,
        "agreement_ok": agreement_ok,
        "volatility_ok": volatility_ok,
        "warning_ok": warning_ok,
        "llm_ok": llm_ok,
        "bullish_votes": bullish_votes,
        "agreement_required": agreement_required,
        "reasons": reasons,
        "thresholds": {
            "combined_score_min": score_min,
            "ai_score_min": ai_min,
            "momentum_score_min": mom_need,
            "momentum_score_min_relaxed": STRICT_BUY_MIN_MOMENTUM_SCORE_EARLY,
            "technical_score_min": technical_min,
            "max_abs_price_change_pct": STRICT_BUY_MAX_VOLATILITY_PCT,
            "max_rsi": rsi_max,
            "timing_score_min": timing_min,
            "min_relative_volume": STRICT_BUY_MIN_RELATIVE_VOLUME,
            "min_risk_reward_ratio": STRICT_BUY_MIN_RISK_REWARD,
        },
    }


def build_trade_plan(
    *,
    price: float,
    catalyst_score: float,
    ai_score: float,
    momentum_score: float,
    price_change_pct: float,
    llm_enhanced: bool,
    momentum_warning: bool = False,
    technical_score: Optional[float] = None,
    technical_regime: Optional[str] = None,
    technical_rsi: Optional[float] = None,
    support: Optional[float] = None,
    resistance: Optional[float] = None,
    relative_volume: Optional[float] = None,
    bars: Optional[List[Dict[str, Any]]] = None,
    buy_threshold: float = STRICT_BUY_MIN_SETUP_SCORE,
    news_age_hours: Optional[float] = None,
) -> Dict[str, Any]:
    """Build a single entry plan from catalyst, tape, and reward/risk inputs."""
    levels = build_trade_levels(
        price=price,
        bars=bars,
        support=support,
        resistance=resistance,
        technical_score=technical_score,
        relative_volume=relative_volume,
    )
    technical_component = technical_score if technical_score is not None else 50.0
    setup_momentum = _setup_momentum_signal(momentum_score, price_change_pct, ai_score)

    # Entry timing: reward early entries, penalize chasing
    timing = assess_entry_timing(
        price=price,
        bars=bars,
        price_change_pct=price_change_pct,
        ai_score=ai_score,
        momentum_score=momentum_score,
        news_age_hours=news_age_hours,
    )
    timing_component = float(timing.get("timing_score", 50.0) or 50.0)
    fresh_catalyst = bool(timing.get("fresh_catalyst"))
    very_fresh = bool(
        _has_very_fresh_catalyst(news_age_hours, ai_score)
        and -1.0 <= price_change_pct <= 1.35
    )
    timing_state = timing.get("timing_state", "standard")
    early_entry = timing_state == "early" and fresh_catalyst

    if early_entry:
        setup_score = (
            catalyst_score * 0.64 +
            timing_component * 0.22 +
            technical_component * 0.08 +
            setup_momentum * 0.06
        )
    elif fresh_catalyst:
        setup_score = (
            catalyst_score * 0.58 +
            timing_component * 0.22 +
            technical_component * 0.12 +
            setup_momentum * 0.08
        )
    else:
        setup_score = (
            catalyst_score * 0.50 +
            timing_component * 0.22 +
            technical_component * 0.18 +
            setup_momentum * 0.10
        )

    supporting_reasons: List[str] = []

    # Entry timing adjustments
    if timing_state == "early":
        setup_score += 10.0
        supporting_reasons.append("early_entry_window")
    elif timing_state == "late":
        setup_score -= 12.0
    elif timing_state == "extended":
        setup_score -= 20.0

    if fresh_catalyst:
        setup_score += 2.5
        supporting_reasons.append("fresh_catalyst")
    if very_fresh:
        setup_score += 4.0
        supporting_reasons.append("very_fresh")
    if early_entry and price_change_pct <= 1.0:
        setup_score += 3.5
        supporting_reasons.append("window_still_open")
    if timing_component >= 64:
        setup_score += 4.0
        supporting_reasons.append("timing_aligned")
    elif timing_component < 45:
        setup_score -= 8.0

    if llm_enhanced:
        setup_score += 3.0
        supporting_reasons.append("llm_confirmed")
    else:
        setup_score -= 3.0

    if technical_regime == "strong_bullish":
        setup_score += 4.0
        supporting_reasons.append("strong_bullish_regime")
    elif technical_regime == "bullish":
        setup_score += 2.0
        supporting_reasons.append("bullish_regime")
    elif technical_regime in {"bearish", "strong_bearish"}:
        setup_score -= 8.0

    if technical_rsi is not None:
        if technical_rsi >= 70 and not fresh_catalyst:
            setup_score -= 5.0
        elif technical_rsi >= 65 and not fresh_catalyst:
            setup_score -= 2.0
        elif technical_rsi >= 82 and fresh_catalyst:
            setup_score -= 5.0
        elif technical_rsi >= 78 and fresh_catalyst:
            setup_score -= 3.0
        elif technical_rsi <= 45:
            setup_score += 1.5
            supporting_reasons.append("not_overextended")

    if abs(price_change_pct) <= 0.9:
        setup_score += 2.5
        supporting_reasons.append("calm_entry")
    elif abs(price_change_pct) <= 1.2:
        setup_score += 1.5
        supporting_reasons.append("calm_entry")
    elif price_change_pct > 2.0:
        setup_score -= min(5.0, (price_change_pct - 2.0) * 1.8)
    elif price_change_pct < -1.5 and ai_score >= 70:
        setup_score -= 2.0

    plan_rvol = levels.get("relative_volume")
    if plan_rvol is not None:
        if plan_rvol >= 1.25:
            setup_score += 2.5
            supporting_reasons.append("volume_confirmation")
        elif plan_rvol < 0.8:
            setup_score -= 4.0

    risk_reward_ratio = float(levels.get("risk_reward_ratio", 0) or 0)
    if risk_reward_ratio >= 2.2:
        setup_score += 2.5
        supporting_reasons.append("reward_to_risk_favorable")
    elif risk_reward_ratio < STRICT_BUY_MIN_RISK_REWARD:
        setup_score -= 6.0

    if momentum_warning:
        setup_score -= 5.0

    resistance_room_pct = float(levels.get("resistance_room_pct", 0) or 0)
    if resistance_room_pct >= 3.0:
        supporting_reasons.append("room_to_run")
    elif resistance_room_pct and resistance_room_pct < 2.0:
        setup_score -= 4.0

    price_vs_vwap_pct = timing.get("price_vs_vwap_pct")
    if price_vs_vwap_pct is not None:
        if early_entry and price_vs_vwap_pct <= 0.7:
            setup_score += 3.5
            supporting_reasons.append("not_chasing_vwap")
        elif fresh_catalyst and price_vs_vwap_pct <= 0.9:
            setup_score += 2.5
            supporting_reasons.append("not_chasing_vwap")
        elif price_vs_vwap_pct > 0.9:
            setup_score -= min(10.0, (price_vs_vwap_pct - 0.9) * 6.0 + 2.0)

    session_range_position = timing.get("session_range_position")
    if session_range_position is not None:
        if early_entry and session_range_position <= 0.7:
            setup_score += 3.0
            supporting_reasons.append("before_range_expansion")
        elif fresh_catalyst and session_range_position <= 0.75:
            setup_score += 2.0
        elif session_range_position > 0.9:
            setup_score -= 10.0
        elif session_range_position > 0.82 and price_change_pct > 0.8:
            setup_score -= 7.0

    if news_age_hours is not None and news_age_hours > 4 and price_change_pct > 0.8:
        setup_score -= 7.0

    supporting_reasons.extend((timing.get("timing_reasons") or [])[:2])

    early_tape_ok = -1.2 <= price_change_pct <= 1.5 and ai_score >= 65
    momentum_factor_ok = momentum_score >= 60 or (early_tape_ok and momentum_score >= (48 if early_entry else 51))
    positive_factors = sum(
        [
            llm_enhanced,
            ai_score >= 70,
            momentum_factor_ok,
            technical_component >= (42 if early_entry else (48 if fresh_catalyst else 62)),
            risk_reward_ratio >= STRICT_BUY_MIN_RISK_REWARD,
            bool(plan_rvol is not None and plan_rvol >= 1.0),
            timing_component >= (58 if early_entry else 50),
        ]
    )
    if positive_factors < (4 if fresh_catalyst else 5):
        setup_score -= 3.0

    setup_score = round(_clamp(setup_score, 0.0, 100.0), 1)

    gate = evaluate_buy_gate(
        combined_score=setup_score,
        ai_score=ai_score,
        momentum_score=momentum_score,
        price_change_pct=price_change_pct,
        momentum_warning=momentum_warning,
        technical_score=technical_score,
        technical_regime=technical_regime,
        technical_rsi=technical_rsi,
        relative_volume=plan_rvol,
        resistance_room_pct=resistance_room_pct,
        risk_reward_ratio=risk_reward_ratio,
        llm_enhanced=llm_enhanced,
        price=price,
        news_age_hours=news_age_hours,
        entry_timing_score=timing_component,
        entry_timing_state=timing_state,
        price_vs_vwap_pct=price_vs_vwap_pct,
        session_range_position=session_range_position,
    )

    buy_threshold_effective = (
        buy_threshold - 4.0 if early_entry else (buy_threshold - 2.5 if fresh_catalyst else buy_threshold)
    )
    tradeable = gate["passed"] and setup_score >= buy_threshold_effective
    if tradeable:
        action = "BUY"
    elif setup_score >= max(0.0, buy_threshold_effective - 6.0) and not gate["reasons"]:
        action = "HOLD"
    else:
        action = "WAIT"

    score_based_size = _clamp(0.55 + max(0.0, setup_score - 75.0) / 35.0, 0.45, 1.15)
    size_multiplier = round(
        _clamp(float(levels.get("size_multiplier", 0.75) or 0.75) * score_based_size, 0.35, 1.1),
        2,
    )

    strategy_label = (
        "fresh_catalyst_early"
        if tradeable and early_entry
        else ("catalyst_trend_follow" if tradeable else "watch_only")
    )

    return {
        "setup_score": setup_score,
        "action": action,
        "tradeable": tradeable,
        "strategy_label": strategy_label,
        "supporting_reasons": list(dict.fromkeys(supporting_reasons))[:5],
        "buy_gate": gate,
        "size_multiplier": size_multiplier,
        "setup_momentum": setup_momentum,
        "timing_state": timing.get("timing_state"),
        "timing_score": timing.get("timing_score"),
        "entry_window": "early" if early_entry else timing.get("timing_state"),
        "late_entry_risk": timing.get("late_entry_risk"),
        "fresh_catalyst": fresh_catalyst,
        "price_vs_vwap_pct": price_vs_vwap_pct,
        "session_range_position": session_range_position,
        **levels,
    }


def should_execute_auto_trade(signal: Dict[str, Any], min_score: float = 70.0) -> Tuple[bool, str]:
    """Execution policy: BUY-only, strict gate must pass, and score minimum."""
    if not signal:
        return False, "no_signal"

    action = signal.get("action", "WAIT")
    score = float(signal.get("effective_score", signal.get("combined_score", 0)) or 0)
    gate = signal.get("buy_gate") or {}
    risk_reward_ratio = float(signal.get("risk_reward_ratio", 0) or 0)

    if action != "BUY":
        return False, f"action={action}"
    if score < min_score:
        return False, f"score={score:.1f}<min={min_score:.1f}"
    if risk_reward_ratio and risk_reward_ratio < STRICT_BUY_MIN_RISK_REWARD:
        return False, f"risk_reward={risk_reward_ratio:.2f}<min={STRICT_BUY_MIN_RISK_REWARD:.1f}"
    if not gate.get("passed", False):
        reasons = ",".join(gate.get("reasons", [])[:3]) or "gate_failed"
        return False, reasons
    return True, "passed"


def summarize_decision_metrics(signals: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compare baseline versus strict gating quality metrics."""
    valid = [s for s in signals if s]
    total = len(valid)
    baseline_buys = [s for s in valid if float(s.get("combined_score", 0)) >= 70]
    strict_buys = [s for s in valid if (s.get("buy_gate") or {}).get("passed")]

    def _avg(items: List[Dict[str, Any]], key: str) -> float:
        if not items:
            return 0.0
        return round(sum(float(i.get(key, 0) or 0) for i in items) / len(items), 2)

    rejected = [s for s in baseline_buys if not (s.get("buy_gate") or {}).get("passed")]
    top_reasons: Dict[str, int] = {}
    for item in rejected:
        for reason in (item.get("buy_gate") or {}).get("reasons", []):
            top_reasons[reason] = top_reasons.get(reason, 0) + 1

    return {
        "universe_count": total,
        "before": {
            "buy_candidates": len(baseline_buys),
            "buy_rate": round((len(baseline_buys) / total) * 100, 2) if total else 0.0,
            "avg_combined_score": _avg(baseline_buys, "combined_score"),
            "avg_ai_score": _avg(baseline_buys, "ai_score"),
            "avg_momentum_score": _avg(baseline_buys, "momentum_score"),
            "avg_risk_reward_ratio": _avg(baseline_buys, "risk_reward_ratio"),
        },
        "after": {
            "buy_candidates": len(strict_buys),
            "buy_rate": round((len(strict_buys) / total) * 100, 2) if total else 0.0,
            "avg_combined_score": _avg(strict_buys, "combined_score"),
            "avg_ai_score": _avg(strict_buys, "ai_score"),
            "avg_momentum_score": _avg(strict_buys, "momentum_score"),
            "avg_risk_reward_ratio": _avg(strict_buys, "risk_reward_ratio"),
        },
        "reduction": {
            "removed_candidates": len(rejected),
            "removed_pct_of_before": round((len(rejected) / len(baseline_buys)) * 100, 2) if baseline_buys else 0.0,
            "top_reject_reasons": sorted(
                [{"reason": key, "count": count} for key, count in top_reasons.items()],
                key=lambda item: item["count"],
                reverse=True,
            )[:5],
        },
    }
