"""Trade gating and decision metrics for local auto-trading."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple


STRICT_BUY_MIN_SCORE = 78.0
STRICT_BUY_MIN_AI_SCORE = 65.0
STRICT_BUY_MIN_MOMENTUM_SCORE = 58.0
STRICT_BUY_MAX_VOLATILITY_PCT = 4.5
STRICT_BUY_MIN_AGREEMENT = 2


def evaluate_buy_gate(
    combined_score: float,
    ai_score: float,
    momentum_score: float,
    price_change_pct: float,
    momentum_warning: bool = False,
) -> Dict[str, Any]:
    """Apply strict local BUY gating to reduce low-quality entries."""
    score_ok = combined_score >= STRICT_BUY_MIN_SCORE
    ai_ok = ai_score >= STRICT_BUY_MIN_AI_SCORE
    momentum_ok = momentum_score >= STRICT_BUY_MIN_MOMENTUM_SCORE
    volatility_ok = abs(price_change_pct) <= STRICT_BUY_MAX_VOLATILITY_PCT
    warning_ok = not momentum_warning

    bullish_votes = int(ai_ok) + int(momentum_ok) + int(score_ok)
    agreement_ok = bullish_votes >= STRICT_BUY_MIN_AGREEMENT

    passed = score_ok and agreement_ok and volatility_ok and warning_ok
    reasons = []
    if not score_ok:
        reasons.append("score_below_threshold")
    if not ai_ok:
        reasons.append("ai_score_below_threshold")
    if not momentum_ok:
        reasons.append("momentum_below_threshold")
    if not agreement_ok:
        reasons.append("insufficient_agent_agreement")
    if not volatility_ok:
        reasons.append("volatility_too_high")
    if not warning_ok:
        reasons.append("momentum_warning")

    return {
        "passed": passed,
        "score_ok": score_ok,
        "ai_ok": ai_ok,
        "momentum_ok": momentum_ok,
        "agreement_ok": agreement_ok,
        "volatility_ok": volatility_ok,
        "warning_ok": warning_ok,
        "bullish_votes": bullish_votes,
        "agreement_required": STRICT_BUY_MIN_AGREEMENT,
        "reasons": reasons,
        "thresholds": {
            "combined_score_min": STRICT_BUY_MIN_SCORE,
            "ai_score_min": STRICT_BUY_MIN_AI_SCORE,
            "momentum_score_min": STRICT_BUY_MIN_MOMENTUM_SCORE,
            "max_abs_price_change_pct": STRICT_BUY_MAX_VOLATILITY_PCT,
        },
    }


def should_execute_auto_trade(signal: Dict[str, Any], min_score: float = 70.0) -> Tuple[bool, str]:
    """Execution policy: BUY-only, strict gate must pass, and score minimum."""
    if not signal:
        return False, "no_signal"
    action = signal.get("action", "WAIT")
    score = float(signal.get("combined_score", 0))
    gate = signal.get("buy_gate") or {}

    if action != "BUY":
        return False, f"action={action}"
    if score < min_score:
        return False, f"score={score:.1f}<min={min_score:.1f}"
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
        return round(sum(float(i.get(key, 0)) for i in items) / len(items), 2)

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
        },
        "after": {
            "buy_candidates": len(strict_buys),
            "buy_rate": round((len(strict_buys) / total) * 100, 2) if total else 0.0,
            "avg_combined_score": _avg(strict_buys, "combined_score"),
            "avg_ai_score": _avg(strict_buys, "ai_score"),
            "avg_momentum_score": _avg(strict_buys, "momentum_score"),
        },
        "reduction": {
            "removed_candidates": len(rejected),
            "removed_pct_of_before": round((len(rejected) / len(baseline_buys)) * 100, 2) if baseline_buys else 0.0,
            "top_reject_reasons": sorted(
                [{"reason": k, "count": v} for k, v in top_reasons.items()],
                key=lambda x: x["count"],
                reverse=True,
            )[:5],
        },
    }

