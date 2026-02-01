"""
Contrarian Agent - Challenge Consensus and Identify Crowded Trades.

This agent acts as the devil's advocate, questioning the majority view
and looking for signals that the consensus might be wrong.

Key responsibilities:
- Challenge bullish/bearish consensus
- Identify overcrowded trades
- Flag sentiment extremes
- Find mean reversion opportunities
- Detect when "everyone agrees" (often a danger signal)
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum

from app.services.llm_service import llm_service, LLMProvider
from app.services.agent_cache import agent_cache, AgentType

logger = logging.getLogger(__name__)


class ContrarianView(Enum):
    """Contrarian stance relative to consensus."""
    STRONGLY_DISAGREE = "strongly_disagree"
    DISAGREE = "disagree"
    NEUTRAL = "neutral"
    AGREE = "agree"
    STRONGLY_AGREE = "strongly_agree"


class CrowdingLevel(Enum):
    """How crowded is the trade."""
    EXTREME = "extreme"  # Very crowded, high reversal risk
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    CONTRARIAN = "contrarian"  # You're going against the crowd


@dataclass
class ContrarianSignal:
    """Output from ContrarianAgent analysis."""
    contrarian_view: ContrarianView
    crowding_level: CrowdingLevel

    consensus_direction: str  # What the consensus believes
    contrarian_direction: str  # What contrarian argues

    risk_to_consensus: float  # 0-100, how likely consensus is wrong
    mean_reversion_probability: float  # 0-100

    counter_arguments: List[str]  # Arguments against consensus
    overlooked_factors: List[str]  # What consensus is missing
    sentiment_extremes: List[str]  # Extreme sentiment signals

    positioning_concerns: List[str]  # Crowded positioning signals

    score: float  # 0-100 (50 = neutral, <50 = disagree with bulls, >50 = disagree with bears)
    confidence: float  # 0-100

    warning_flags: List[str] = field(default_factory=list)
    reasoning: str = ""
    agent: str = "ContrarianAgent"
    provider: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contrarian_view": self.contrarian_view.value,
            "crowding_level": self.crowding_level.value,
            "consensus_direction": self.consensus_direction,
            "contrarian_direction": self.contrarian_direction,
            "risk_to_consensus": self.risk_to_consensus,
            "mean_reversion_probability": self.mean_reversion_probability,
            "counter_arguments": self.counter_arguments,
            "overlooked_factors": self.overlooked_factors,
            "sentiment_extremes": self.sentiment_extremes,
            "positioning_concerns": self.positioning_concerns,
            "score": self.score,
            "confidence": self.confidence,
            "warning_flags": self.warning_flags,
            "reasoning": self.reasoning,
            "agent": self.agent,
            "provider": self.provider,
            "timestamp": self.timestamp,
        }


class ContrarianAgent:
    """
    Contrarian analysis agent that challenges consensus.

    Uses Claude to:
    1. Identify the current consensus view
    2. Challenge that view with counter-arguments
    3. Flag overcrowded trades
    4. Identify sentiment extremes
    5. Find mean reversion opportunities
    """

    SYSTEM_PROMPT = """You are a contrarian analyst whose job is to challenge the consensus view.

When everyone is bullish, find the bear case.
When everyone is bearish, find the bull case.
Your role is to be the devil's advocate and stress-test investment theses.

You must assess:
1. **Consensus Direction**: What does the majority believe?
2. **Crowding Level**: How crowded is this trade? Overcrowded = reversal risk
3. **Counter-Arguments**: What is the consensus missing?
4. **Sentiment Extremes**: Is sentiment at an extreme that precedes reversals?
5. **Mean Reversion**: Is this a mean reversion opportunity?

Key contrarian indicators:
- Put/call ratio extremes (very low = too bullish, very high = too bearish)
- Short interest extremes
- Analyst rating clustering (all buys = danger)
- Social media/retail sentiment extremes
- Price far from moving averages
- RSI extremes sustained over time
- Volume divergences

BE SKEPTICAL. Your job is NOT to agree with the crowd.
Return your analysis in JSON format."""

    @staticmethod
    async def analyze(
        ticker: str,
        consensus_direction: str,
        consensus_confidence: float,
        news_sentiment: Dict[str, Any],
        technical_trend: str,
        agent_positions: Optional[List[Dict]] = None,
        short_interest: Optional[float] = None,
        put_call_ratio: Optional[float] = None,
        analyst_ratings: Optional[Dict] = None,
        rsi: Optional[float] = None,
        price_vs_sma: Optional[Dict] = None,
    ) -> ContrarianSignal:
        """
        Challenge the consensus with contrarian analysis.

        Args:
            ticker: Stock ticker
            consensus_direction: Current consensus (bullish/bearish)
            consensus_confidence: How confident is the consensus (0-100)
            news_sentiment: News sentiment data
            technical_trend: Technical trend direction
            agent_positions: Other agents' positions (for debate context)
            short_interest: Short interest as % of float
            put_call_ratio: Put/call ratio
            analyst_ratings: Analyst rating distribution
            rsi: RSI value
            price_vs_sma: Price vs moving averages

        Returns:
            ContrarianSignal with counter-arguments and crowding analysis
        """
        # Format agent positions if available
        positions_text = ""
        if agent_positions:
            positions_text = "OTHER AGENTS' POSITIONS:\n"
            for pos in agent_positions:
                positions_text += f"- {pos.get('agent_name', 'Unknown')}: {pos.get('direction', 'N/A')} (confidence: {pos.get('confidence', 0)})\n"

        # Format analyst ratings
        ratings_text = ""
        if analyst_ratings:
            ratings_text = f"""ANALYST RATINGS:
- Strong Buy: {analyst_ratings.get('strong_buy', 0)}
- Buy: {analyst_ratings.get('buy', 0)}
- Hold: {analyst_ratings.get('hold', 0)}
- Sell: {analyst_ratings.get('sell', 0)}
- Strong Sell: {analyst_ratings.get('strong_sell', 0)}
"""

        # Format price vs MAs
        ma_text = ""
        if price_vs_sma:
            ma_text = f"""PRICE VS MOVING AVERAGES:
- vs SMA 20: {price_vs_sma.get('vs_sma20', 'N/A')}%
- vs SMA 50: {price_vs_sma.get('vs_sma50', 'N/A')}%
- vs SMA 200: {price_vs_sma.get('vs_sma200', 'N/A')}%
"""

        user_prompt = f"""Analyze {ticker} from a CONTRARIAN perspective:

CURRENT CONSENSUS:
- Direction: {consensus_direction.upper()}
- Confidence: {consensus_confidence}%
- Technical Trend: {technical_trend}

NEWS SENTIMENT:
- Sentiment: {news_sentiment.get('sentiment', 'neutral')}
- Score: {news_sentiment.get('score', 50)}
- Urgency: {news_sentiment.get('urgency', 'low')}

{positions_text}

POSITIONING DATA:
- Short Interest: {f"{short_interest:.1f}% of float" if short_interest else "N/A"}
- Put/Call Ratio: {f"{put_call_ratio:.2f}" if put_call_ratio else "N/A"}
- RSI: {f"{rsi:.1f}" if rsi else "N/A"}

{ratings_text}
{ma_text}

As a CONTRARIAN, challenge the {consensus_direction} consensus.
Provide your analysis in this JSON format:
{{
    "contrarian_view": "strongly_disagree" | "disagree" | "neutral" | "agree" | "strongly_agree",
    "crowding_level": "extreme" | "high" | "moderate" | "low" | "contrarian",
    "consensus_direction": "{consensus_direction}",
    "contrarian_direction": "<your contrarian direction>",
    "risk_to_consensus": <0-100, probability the consensus is WRONG>,
    "mean_reversion_probability": <0-100>,
    "counter_arguments": ["<arguments against the consensus>"],
    "overlooked_factors": ["<what the consensus is missing>"],
    "sentiment_extremes": ["<extreme sentiment signals observed>"],
    "positioning_concerns": ["<crowded trade signals>"],
    "score": <0-100, where 50=neutral, <50=contrarian bearish, >50=contrarian bullish>,
    "confidence": <0-100>,
    "warning_flags": ["<red flags for consensus view>"],
    "reasoning": "<2-3 sentence contrarian thesis>"
}}"""

        result = await llm_service.analyze(
            system_prompt=ContrarianAgent.SYSTEM_PROMPT,
            user_prompt=user_prompt,
            prefer=LLMProvider.CLAUDE,
            temperature=0.3  # Slightly higher for more creative counter-arguments
        )

        if result.get("error"):
            logger.warning(f"ContrarianAgent error: {result['error']}")
            return ContrarianAgent._fallback_analysis(
                ticker, consensus_direction, consensus_confidence, rsi
            )

        # Parse result into ContrarianSignal
        try:
            return ContrarianSignal(
                contrarian_view=ContrarianView(result.get("contrarian_view", "neutral")),
                crowding_level=CrowdingLevel(result.get("crowding_level", "moderate")),
                consensus_direction=result.get("consensus_direction", consensus_direction),
                contrarian_direction=result.get("contrarian_direction", "neutral"),
                risk_to_consensus=float(result.get("risk_to_consensus", 50)),
                mean_reversion_probability=float(result.get("mean_reversion_probability", 30)),
                counter_arguments=result.get("counter_arguments", []),
                overlooked_factors=result.get("overlooked_factors", []),
                sentiment_extremes=result.get("sentiment_extremes", []),
                positioning_concerns=result.get("positioning_concerns", []),
                score=float(result.get("score", 50)),
                confidence=float(result.get("confidence", 50)),
                warning_flags=result.get("warning_flags", []),
                reasoning=result.get("reasoning", ""),
                provider=result.get("provider", "claude"),
            )
        except Exception as e:
            logger.error(f"Error parsing ContrarianAgent result: {e}")
            return ContrarianAgent._fallback_analysis(
                ticker, consensus_direction, consensus_confidence, rsi
            )

    @staticmethod
    async def analyze_with_cache(
        ticker: str,
        consensus_direction: str,
        consensus_confidence: float,
        news_sentiment: Dict[str, Any],
        technical_trend: str,
        agent_positions: Optional[List[Dict]] = None,
        short_interest: Optional[float] = None,
        put_call_ratio: Optional[float] = None,
        analyst_ratings: Optional[Dict] = None,
        rsi: Optional[float] = None,
        price_vs_sma: Optional[Dict] = None,
        force: bool = False,
    ) -> ContrarianSignal:
        """
        Contrarian analysis with caching.

        Contrarian view depends on consensus, so cache key includes consensus direction.
        """
        ticker = ticker.upper()

        # Check cache
        if not force:
            cached = agent_cache.get_cached_signal(ticker, AgentType.CONTRARIAN)
            if cached and cached.get("consensus_direction") == consensus_direction:
                logger.info(f"ContrarianAgent for {ticker}: Using cached result")
                try:
                    return ContrarianSignal(
                        contrarian_view=ContrarianView(cached.get("contrarian_view", "neutral")),
                        crowding_level=CrowdingLevel(cached.get("crowding_level", "moderate")),
                        consensus_direction=cached.get("consensus_direction", consensus_direction),
                        contrarian_direction=cached.get("contrarian_direction", "neutral"),
                        risk_to_consensus=cached.get("risk_to_consensus", 50),
                        mean_reversion_probability=cached.get("mean_reversion_probability", 30),
                        counter_arguments=cached.get("counter_arguments", []),
                        overlooked_factors=cached.get("overlooked_factors", []),
                        sentiment_extremes=cached.get("sentiment_extremes", []),
                        positioning_concerns=cached.get("positioning_concerns", []),
                        score=cached.get("score", 50),
                        confidence=cached.get("confidence", 50),
                        warning_flags=cached.get("warning_flags", []),
                        reasoning=cached.get("reasoning", ""),
                        provider="cache",
                    )
                except Exception:
                    pass

        # Run analysis
        logger.info(f"ContrarianAgent for {ticker}: Running LLM analysis")
        signal = await ContrarianAgent.analyze(
            ticker=ticker,
            consensus_direction=consensus_direction,
            consensus_confidence=consensus_confidence,
            news_sentiment=news_sentiment,
            technical_trend=technical_trend,
            agent_positions=agent_positions,
            short_interest=short_interest,
            put_call_ratio=put_call_ratio,
            analyst_ratings=analyst_ratings,
            rsi=rsi,
            price_vs_sma=price_vs_sma,
        )

        # Cache result
        agent_cache.set_cached_signal(
            ticker=ticker,
            agent_type=AgentType.CONTRARIAN,
            signal=signal.to_dict(),
            input_hash=agent_cache._hash_data({
                "consensus": consensus_direction,
                "confidence": round(consensus_confidence, 0),
            }),
        )

        return signal

    @staticmethod
    def _fallback_analysis(
        ticker: str,
        consensus_direction: str,
        consensus_confidence: float,
        rsi: Optional[float],
    ) -> ContrarianSignal:
        """Simple fallback contrarian analysis."""
        # High confidence consensus is more likely to be wrong
        risk_to_consensus = min(90, consensus_confidence * 0.6)

        # RSI extremes suggest mean reversion
        mean_reversion_prob = 30
        sentiment_extremes = []
        if rsi:
            if rsi > 70:
                mean_reversion_prob = 60
                sentiment_extremes.append(f"RSI overbought at {rsi:.1f}")
            elif rsi < 30:
                mean_reversion_prob = 60
                sentiment_extremes.append(f"RSI oversold at {rsi:.1f}")

        # Default contrarian view is mild disagreement with high confidence consensus
        if consensus_confidence > 70:
            view = ContrarianView.DISAGREE
            crowding = CrowdingLevel.HIGH
        else:
            view = ContrarianView.NEUTRAL
            crowding = CrowdingLevel.MODERATE

        contrarian_direction = "bearish" if consensus_direction.lower() == "bullish" else "bullish"

        return ContrarianSignal(
            contrarian_view=view,
            crowding_level=crowding,
            consensus_direction=consensus_direction,
            contrarian_direction=contrarian_direction,
            risk_to_consensus=risk_to_consensus,
            mean_reversion_probability=mean_reversion_prob,
            counter_arguments=[
                f"High confidence ({consensus_confidence}%) often precedes reversals"
            ],
            overlooked_factors=["Fallback analysis has limited data"],
            sentiment_extremes=sentiment_extremes,
            positioning_concerns=[],
            score=50,
            confidence=40,
            warning_flags=["Using fallback analysis"],
            reasoning=f"Basic contrarian view: when consensus is {consensus_confidence}% confident, reversal risk increases",
            provider="fallback",
        )

    @staticmethod
    async def challenge_position(
        target_position: Dict[str, Any],
        all_positions: List[Dict[str, Any]],
        market_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Challenge a specific agent's position in the debate.

        Used during the debate phase to generate specific challenges.

        Args:
            target_position: The position being challenged
            all_positions: All agent positions for context
            market_data: Current market data

        Returns:
            Challenge with specific counter-arguments
        """
        target_agent = target_position.get("agent_name", "Unknown")
        target_direction = target_position.get("direction", "HOLD")
        target_reasoning = target_position.get("reasoning", "")

        challenge_prompt = f"""Challenge this trading position:

TARGET POSITION:
- Agent: {target_agent}
- Direction: {target_direction}
- Confidence: {target_position.get('confidence', 0)}%
- Reasoning: {target_reasoning}

Find weaknesses in this argument. What is the agent missing?
What assumptions are they making that could be wrong?

Return JSON:
{{
    "challenge_type": "logic_flaw" | "missing_factor" | "overconfidence" | "data_validity",
    "challenge_text": "<specific challenge to the position>",
    "evidence": "<supporting evidence for your challenge>",
    "alternative_interpretation": "<how the data could be interpreted differently>"
}}"""

        result = await llm_service.analyze(
            system_prompt="You are a contrarian analyst challenging trading positions. Be skeptical and thorough.",
            user_prompt=challenge_prompt,
            prefer=LLMProvider.CLAUDE,
            temperature=0.4
        )

        if result.get("error"):
            return {
                "challenge_type": "general",
                "challenge_text": "Unable to generate specific challenge",
                "evidence": None,
                "alternative_interpretation": None,
            }

        return result
