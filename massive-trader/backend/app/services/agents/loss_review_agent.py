"""Loss Review Agent - Converts losing trades into reusable lessons."""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.services.llm_service import llm_service, LLMProvider

logger = logging.getLogger(__name__)


@dataclass
class LossReview:
    """Structured review of a losing trade."""
    mistake_patterns: List[str]
    primary_cause: str
    setup_quality: float
    repeat_risk: float
    confidence: float
    suggested_actions: List[str]
    score_penalty: float
    size_multiplier: float
    veto_future_similar: bool
    reasoning: str
    agent: str = "LossReviewAgent"
    provider: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mistake_patterns": self.mistake_patterns,
            "primary_cause": self.primary_cause,
            "setup_quality": self.setup_quality,
            "repeat_risk": self.repeat_risk,
            "confidence": self.confidence,
            "suggested_actions": self.suggested_actions,
            "score_penalty": self.score_penalty,
            "size_multiplier": self.size_multiplier,
            "veto_future_similar": self.veto_future_similar,
            "reasoning": self.reasoning,
            "agent": self.agent,
            "provider": self.provider,
            "timestamp": self.timestamp,
        }


class LossReviewAgent:
    """Analyze a losing trade and extract bounded lessons."""

    SYSTEM_PROMPT = """You are a trading postmortem analyst.

Your job is to review losing trades and extract repeatable mistakes WITHOUT overreacting.
You must identify patterns that are actionable for future trade filtering.

Focus on these mistake families when relevant:
- weak_entry_quality
- borderline_score_entry
- momentum_not_confirmed
- late_chase
- crowded_news_chase
- bad_regime_alignment
- overconcentration
- oversized_position
- stop_too_tight_for_volatility
- thesis_mismatch

Return STRICT JSON only with this schema:
{
  "mistake_patterns": ["snake_case_pattern"],
  "primary_cause": "short_snake_case_label",
  "setup_quality": <0-100>,
  "repeat_risk": <0-100>,
  "confidence": <0-100>,
  "suggested_actions": ["short action"],
  "score_penalty": <0-20>,
  "size_multiplier": <0.25-1.0>,
  "veto_future_similar": <true|false>,
  "reasoning": "1-3 concise sentences"
}

Rules:
- Keep recommendations bounded and conservative.
- Do not suggest rewriting the whole strategy.
- Only set veto_future_similar=true when the loss looks repeatable, not random."""

    @staticmethod
    async def analyze(
        *,
        ticker: str,
        side: str,
        entry_price: float,
        exit_price: float,
        pnl_pct: float,
        hold_time_minutes: float,
        score_at_entry: Optional[float] = None,
        atr_at_entry: Optional[float] = None,
        regime_at_entry: Optional[str] = None,
        source: Optional[str] = None,
        exit_reason: Optional[str] = None,
        entry_thesis: Optional[str] = None,
        recent_similar_losses: Optional[List[Dict[str, Any]]] = None,
    ) -> LossReview:
        """Review a losing trade and produce structured lessons."""
        recent_losses = recent_similar_losses or []
        user_prompt = f"""Review this losing trade:

TRADE:
- Ticker: {ticker}
- Side: {side}
- Entry price: {entry_price:.2f}
- Exit price: {exit_price:.2f}
- PnL %: {pnl_pct:.2f}
- Hold time minutes: {hold_time_minutes:.1f}
- Score at entry: {score_at_entry if score_at_entry is not None else "unknown"}
- ATR at entry: {atr_at_entry if atr_at_entry is not None else "unknown"}
- Regime at entry: {regime_at_entry or "unknown"}
- Source: {source or "unknown"}
- Exit reason: {exit_reason or "unknown"}
- Entry thesis: {(entry_thesis or "none provided")[:600]}

RECENT SIMILAR LOSSES:
{recent_losses[:5]}

Classify the most likely mistake patterns and return only JSON."""

        result = await llm_service.analyze(
            system_prompt=LossReviewAgent.SYSTEM_PROMPT,
            user_prompt=user_prompt,
            prefer=LLMProvider.CLAUDE,
            temperature=0.2,
            agent_type="loss_review",
        )

        if result.get("error"):
            logger.warning(f"LossReviewAgent error for {ticker}: {result['error']}")
            return LossReviewAgent._fallback_review(
                ticker=ticker,
                pnl_pct=pnl_pct,
                hold_time_minutes=hold_time_minutes,
                score_at_entry=score_at_entry,
                atr_at_entry=atr_at_entry,
                source=source,
                exit_reason=exit_reason,
            )

        try:
            return LossReview(
                mistake_patterns=result.get("mistake_patterns", []) or [],
                primary_cause=result.get("primary_cause", "unclear_loss_driver"),
                setup_quality=float(result.get("setup_quality", 40)),
                repeat_risk=float(result.get("repeat_risk", 50)),
                confidence=float(result.get("confidence", 50)),
                suggested_actions=result.get("suggested_actions", []) or [],
                score_penalty=float(result.get("score_penalty", 5)),
                size_multiplier=float(result.get("size_multiplier", 0.75)),
                veto_future_similar=bool(result.get("veto_future_similar", False)),
                reasoning=result.get("reasoning", ""),
                provider=result.get("provider", "llm"),
            )
        except Exception as exc:
            logger.error(f"Error parsing LossReviewAgent result for {ticker}: {exc}")
            return LossReviewAgent._fallback_review(
                ticker=ticker,
                pnl_pct=pnl_pct,
                hold_time_minutes=hold_time_minutes,
                score_at_entry=score_at_entry,
                atr_at_entry=atr_at_entry,
                source=source,
                exit_reason=exit_reason,
            )

    @staticmethod
    def _fallback_review(
        *,
        ticker: str,
        pnl_pct: float,
        hold_time_minutes: float,
        score_at_entry: Optional[float],
        atr_at_entry: Optional[float],
        source: Optional[str],
        exit_reason: Optional[str],
    ) -> LossReview:
        """Fallback heuristic review when LLM is unavailable."""
        patterns: List[str] = []
        actions: List[str] = []
        reason_parts: List[str] = []
        primary_cause = "unclear_loss_driver"
        score_penalty = 5.0
        size_multiplier = 0.75
        veto_future_similar = False

        reason_lower = (exit_reason or "").lower()
        source_lower = (source or "").lower()

        if score_at_entry is not None and score_at_entry < 75:
            patterns.append("borderline_score_entry")
            actions.append("require_higher_entry_score")
            primary_cause = "borderline_score_entry"
            score_penalty = max(score_penalty, 7.0)
            reason_parts.append(f"entry score was only {score_at_entry:.1f}")

        if "stop" in reason_lower:
            patterns.append("stop_too_tight_for_volatility")
            actions.append("review_stop_distance_vs_volatility")
            primary_cause = "stop_too_tight_for_volatility"
            size_multiplier = min(size_multiplier, 0.65)
            reason_parts.append("trade exited via stop-based logic")

        if hold_time_minutes < 30:
            patterns.append("weak_entry_quality")
            actions.append("avoid_immediate_reentry_on_similar_setup")
            reason_parts.append(f"loss happened quickly ({hold_time_minutes:.1f}m)")

        if atr_at_entry and atr_at_entry > 0 and "stop" in reason_lower:
            reason_parts.append(f"ATR at entry was {atr_at_entry:.2f}")

        if "trending" in source_lower or "bell_rush" in source_lower:
            patterns.append("crowded_news_chase")
            actions.append("reduce_size_on_crowded_sources")
            if primary_cause == "unclear_loss_driver":
                primary_cause = "crowded_news_chase"
            size_multiplier = min(size_multiplier, 0.6)
            reason_parts.append(f"source was {source}")

        if pnl_pct <= -2.0:
            actions.append("penalize_repeat_setup")
            veto_future_similar = len(patterns) >= 2
            reason_parts.append(f"loss was material at {pnl_pct:.2f}%")

        if not patterns:
            patterns = ["weak_entry_quality"]
            actions.append("collect_more_context_before_repeat")
            primary_cause = "weak_entry_quality"

        setup_quality = 35.0 if "borderline_score_entry" in patterns else 45.0
        repeat_risk = 70.0 if veto_future_similar else 55.0
        reasoning = "; ".join(reason_parts) if reason_parts else f"{ticker} produced a loss with limited context."

        return LossReview(
            mistake_patterns=patterns,
            primary_cause=primary_cause,
            setup_quality=setup_quality,
            repeat_risk=repeat_risk,
            confidence=55.0,
            suggested_actions=actions,
            score_penalty=score_penalty,
            size_multiplier=size_multiplier,
            veto_future_similar=veto_future_similar,
            reasoning=reasoning,
            provider="fallback",
        )
