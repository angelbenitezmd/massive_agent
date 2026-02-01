"""
Debate Facilitator - CIO Agent that Synthesizes Debate Outcomes.

The facilitator is an enhanced version of the SentimentSynthesisAgent
that understands debate context and can make nuanced decisions based
on the quality of arguments, not just vote counts.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.services.llm_service import llm_service, LLMProvider
from app.services.debate.models import (
    AgentPosition,
    Challenge,
    DebateRound,
    DebateOutcome,
)

logger = logging.getLogger(__name__)


class DebateFacilitator:
    """
    Enhanced CIO that facilitates debates and makes final calls.

    Unlike simple weighted voting, the facilitator uses an LLM to:
    1. Understand the quality of arguments
    2. Weigh challenges and rebuttals
    3. Consider risk/reward holistically
    4. Make a decisive final recommendation
    """

    SYSTEM_PROMPT = """You are the Chief Investment Officer facilitating a trading debate.

Multiple agents have presented their positions. Your job is to:
1. Synthesize all arguments objectively
2. Identify the strongest arguments on each side
3. Weigh challenges and rebuttals
4. Consider risk/reward
5. Make a DECISIVE final recommendation

You must:
- Be decisive, not wishy-washy
- Consider conviction levels and data quality
- Give more weight to agents with stronger evidence
- Account for dissenting views (they may see something others miss)
- Prioritize capital preservation when uncertain

Return your synthesis in JSON format."""

    @staticmethod
    async def synthesize(
        ticker: str,
        debate: DebateRound,
        market_context: Dict[str, Any],
        risk_assessment: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Synthesize a debate into a final decision.

        Unlike weighted voting, this uses LLM judgment to assess
        the QUALITY of arguments, not just quantity.

        Args:
            ticker: Stock ticker
            debate: The complete debate round with positions/challenges
            market_context: Current market data
            risk_assessment: Risk agent's assessment

        Returns:
            Dict with final decision and reasoning
        """
        # Format positions for the prompt
        positions_text = ""
        for pos in debate.positions:
            positions_text += f"""
{pos.agent_name.upper()} AGENT:
- Direction: {pos.direction}
- Confidence: {pos.confidence}%
- Reasoning: {pos.reasoning}
- Key Arguments: {', '.join(pos.key_arguments[:3]) if pos.key_arguments else 'None'}
- Risks Identified: {', '.join(pos.risks_identified[:2]) if pos.risks_identified else 'None'}
"""

        # Format challenges
        challenges_text = ""
        if debate.challenges:
            challenges_text = "\nCHALLENGES RAISED:\n"
            for c in debate.challenges:
                challenges_text += f"- [{c.severity.upper()}] {c.challenge_text}\n"

        # Format risk assessment
        risk_text = ""
        if risk_assessment:
            risk_text = f"""
RISK ASSESSMENT:
- Risk Level: {risk_assessment.get('risk_level', 'unknown')}
- Veto: {risk_assessment.get('veto', False)}
- Suggested Position Size: {risk_assessment.get('suggested_shares', 0)} shares
- Warnings: {', '.join(risk_assessment.get('warnings', [])[:3])}
"""

        # Market context
        current_price = market_context.get("quote", {}).get("price", 0)
        context_text = f"""
MARKET CONTEXT:
- Ticker: {ticker}
- Current Price: ${current_price:.2f}
- VIX: {market_context.get('vix', 'N/A')}
"""

        user_prompt = f"""Synthesize this trading debate and make a final decision:

{context_text}

AGENT POSITIONS:
{positions_text}

{challenges_text}

{risk_text}

Based on the quality of arguments (not just vote counts), provide your synthesis:
{{
    "final_decision": "STRONG_BUY" | "BUY" | "HOLD" | "SELL" | "STRONG_SELL",
    "conviction": <1-10>,
    "confidence": <0-100>,
    "primary_reasoning": "<main argument for your decision>",
    "supporting_agents": ["<agents whose arguments you found most compelling>"],
    "dissenting_views_considered": ["<opposing arguments you weighed>"],
    "key_uncertainty": "<biggest unknown>",
    "risk_mitigations": ["<steps to address concerns raised>"],
    "would_override_vote": <true if your decision differs from simple vote count>,
    "override_reason": "<why you disagree with the majority, if applicable>",
    "summary": "<2-3 sentence summary of your decision>"
}}"""

        result = await llm_service.analyze(
            system_prompt=DebateFacilitator.SYSTEM_PROMPT,
            user_prompt=user_prompt,
            prefer=LLMProvider.CLAUDE,
            temperature=0.2
        )

        if result.get("error"):
            logger.warning(f"DebateFacilitator error: {result['error']}")
            # Fall back to vote-based decision
            return DebateFacilitator._fallback_synthesis(debate)

        result["ticker"] = ticker
        result["timestamp"] = datetime.utcnow().isoformat()
        return result

    @staticmethod
    def _fallback_synthesis(debate: DebateRound) -> Dict[str, Any]:
        """Simple fallback when LLM is unavailable."""
        # Count votes
        votes = {"BUY": 0, "SELL": 0, "HOLD": 0}
        for pos in debate.positions:
            if pos.direction in ["BUY", "STRONG_BUY"]:
                votes["BUY"] += pos.confidence / 100
            elif pos.direction in ["SELL", "STRONG_SELL"]:
                votes["SELL"] += pos.confidence / 100
            else:
                votes["HOLD"] += pos.confidence / 100

        # Determine winner
        total = sum(votes.values())
        if total == 0:
            winner = "HOLD"
            confidence = 50
        else:
            winner = max(votes, key=votes.get)
            confidence = (votes[winner] / total) * 100

        return {
            "final_decision": winner,
            "conviction": int(confidence / 10),
            "confidence": confidence,
            "primary_reasoning": "Fallback: based on simple vote count",
            "supporting_agents": [],
            "dissenting_views_considered": [],
            "key_uncertainty": "LLM unavailable for synthesis",
            "risk_mitigations": [],
            "would_override_vote": False,
            "override_reason": None,
            "summary": f"Fallback decision: {winner} based on vote count",
            "provider": "fallback",
        }

    @staticmethod
    async def resolve_deadlock(
        ticker: str,
        debate: DebateRound,
        market_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Resolve a deadlock when agents are evenly split.

        Uses conservative approach: when uncertain, don't trade.
        """
        prompt = f"""The agents are deadlocked on {ticker}.

Positions are evenly split between buy and sell signals.

In trading, when experts disagree and there's no clear edge,
the prudent action is usually to STAY OUT and preserve capital.

However, if there's a compelling asymmetric risk/reward,
we might take a smaller position.

Based on the debate, should we:
1. HOLD (stay out) - the safe choice
2. Take a small exploratory position

Provide your recommendation:
{{
    "decision": "HOLD" | "SMALL_BUY" | "SMALL_SELL",
    "reasoning": "<why>",
    "position_size_modifier": <0.0-0.5, multiply normal size by this>
}}"""

        result = await llm_service.analyze(
            system_prompt="You are a risk-conscious CIO resolving a trading deadlock.",
            user_prompt=prompt,
            prefer=LLMProvider.CLAUDE,
            temperature=0.1
        )

        if result.get("error"):
            return {
                "decision": "HOLD",
                "reasoning": "Deadlock - staying out",
                "position_size_modifier": 0,
            }

        return result
