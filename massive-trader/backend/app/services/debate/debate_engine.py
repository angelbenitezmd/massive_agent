"""
Debate Engine - Orchestrates Multi-Agent Trading Debates.

This is the core engine that:
1. Gathers initial positions from all agents
2. Has the contrarian agent challenge the consensus
3. Collects rebuttals
4. Calculates weighted votes
5. Applies risk veto if needed
6. Returns the final decision
"""

import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from app.services.debate.models import (
    DebatePhase,
    AgentPosition,
    Challenge,
    Rebuttal,
    DebateRound,
    DebateOutcome,
)

# Import all agents
from app.services.ai_agents import (
    NewsIntelligenceAgent,
    TechnicalAnalysisAgent,
    SentimentSynthesisAgent,
)
from app.services.agents.macro_agent import MacroAgent, MacroSignal
from app.services.agents.contrarian_agent import ContrarianAgent, ContrarianSignal
from app.services.agents.risk_management_agent import RiskManagementAgent, RiskAssessment
from app.services.agents.exit_strategy_agent import ExitStrategyAgent
from app.services.agents.trade_timing_agent import TradeTimingAgent

logger = logging.getLogger(__name__)


class DebateEngine:
    """
    Orchestrates multi-agent debates for trading decisions.

    Flow:
    1. Each agent presents initial position
    2. Contrarian agent challenges the consensus
    3. Agents provide rebuttals
    4. Weighted voting determines outcome
    5. Risk agent can VETO if risk too high
    """

    # Default agent weights (can be updated by memory system)
    DEFAULT_WEIGHTS = {
        "news": 0.20,
        "technical": 0.20,
        "macro": 0.15,
        "contrarian": 0.10,
        "risk": 0.15,
        "timing": 0.10,
        "exit": 0.10,
    }

    # Minimum consensus threshold to take action
    CONSENSUS_THRESHOLD = 0.60

    # Risk veto threshold - if risk score below this, veto the trade
    RISK_VETO_THRESHOLD = 30

    def __init__(
        self,
        agent_weights: Optional[Dict[str, float]] = None,
        consensus_threshold: float = 0.60,
        risk_veto_threshold: float = 30,
    ):
        """
        Initialize the debate engine.

        Args:
            agent_weights: Custom weights for each agent (must sum to 1)
            consensus_threshold: Minimum consensus % to take action
            risk_veto_threshold: Risk score below which trade is vetoed
        """
        self.agent_weights = agent_weights or self.DEFAULT_WEIGHTS.copy()
        self.consensus_threshold = consensus_threshold
        self.risk_veto_threshold = risk_veto_threshold

        # Normalize weights
        total = sum(self.agent_weights.values())
        if total != 1.0:
            self.agent_weights = {k: v / total for k, v in self.agent_weights.items()}

    def update_weights(self, new_weights: Dict[str, float]) -> None:
        """Update agent weights (from memory system)."""
        self.agent_weights = new_weights
        # Normalize
        total = sum(self.agent_weights.values())
        if total != 1.0:
            self.agent_weights = {k: v / total for k, v in self.agent_weights.items()}

    async def run_debate(
        self,
        ticker: str,
        market_data: Dict[str, Any],
        account: Dict[str, Any],
        positions: List[Dict[str, Any]],
        historical_context: Optional[Dict[str, Any]] = None,
    ) -> DebateOutcome:
        """
        Run a full debate cycle for a trading decision.

        Args:
            ticker: Stock ticker to analyze
            market_data: All market data (price, bars, news, etc.)
            account: Account info (equity, buying power)
            positions: Current positions
            historical_context: Context from memory system

        Returns:
            DebateOutcome with final decision
        """
        start_time = datetime.utcnow()
        ticker = ticker.upper()

        logger.info(f"Starting debate for {ticker}")

        # Initialize debate round
        debate = DebateRound(
            ticker=ticker,
            phase=DebatePhase.INITIAL_POSITION,
            positions=[],
            challenges=[],
            rebuttals=[],
        )

        try:
            # Phase 1: Gather initial positions from all agents
            logger.info(f"{ticker}: Phase 1 - Gathering initial positions")
            positions_list = await self._gather_initial_positions(
                ticker, market_data, account, positions, historical_context
            )
            debate.positions = positions_list

            # Determine consensus direction
            consensus_direction, consensus_strength = self._determine_consensus(positions_list)
            logger.info(
                f"{ticker}: Initial consensus: {consensus_direction} "
                f"(strength: {consensus_strength:.1f}%)"
            )

            # Phase 2: Contrarian challenges
            logger.info(f"{ticker}: Phase 2 - Generating challenges")
            debate.phase = DebatePhase.CHALLENGE
            challenges = await self._generate_challenges(
                ticker, positions_list, consensus_direction, market_data
            )
            debate.challenges = challenges

            # Phase 3: Gather rebuttals (simplified - adjust confidence based on challenges)
            logger.info(f"{ticker}: Phase 3 - Processing rebuttals")
            debate.phase = DebatePhase.REBUTTAL
            adjusted_positions = self._process_challenges(positions_list, challenges)

            # Phase 4: Calculate final outcome
            logger.info(f"{ticker}: Phase 4 - Calculating final outcome")
            debate.phase = DebatePhase.FINAL_VOTE
            outcome = await self._calculate_outcome(
                ticker, adjusted_positions, debate, market_data, account, positions
            )

            # Record timing
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()
            debate.end_time = end_time.isoformat()
            debate.duration_seconds = duration
            outcome.debate_duration_seconds = duration

            logger.info(
                f"{ticker}: Debate complete in {duration:.2f}s. "
                f"Action: {outcome.final_action} (confidence: {outcome.consensus_confidence:.1f}%)"
            )

            return outcome

        except Exception as e:
            logger.error(f"Debate error for {ticker}: {e}", exc_info=True)
            # Return safe HOLD outcome on error
            return DebateOutcome(
                ticker=ticker,
                final_action="HOLD",
                consensus_confidence=0,
                weighted_score=50,
                vote_breakdown={},
                vote_weights={},
                total_votes={},
                risk_warnings=[f"Debate error: {str(e)}"],
                debate_summary=f"Error during debate: {str(e)}",
            )

    async def _gather_initial_positions(
        self,
        ticker: str,
        market_data: Dict[str, Any],
        account: Dict[str, Any],
        positions: List[Dict[str, Any]],
        historical_context: Optional[Dict[str, Any]] = None,
    ) -> List[AgentPosition]:
        """
        Gather initial positions from all agents in parallel.
        """
        # Extract data for agents
        current_price = market_data.get("quote", {}).get("price", 0)
        bars = market_data.get("bars", [])
        news = market_data.get("news", [])
        technical = market_data.get("technical", {})
        macro = market_data.get("macro", {})

        # Run agents in parallel with timeout
        tasks = [
            self._get_news_position(ticker, news, current_price),
            self._get_technical_position(ticker, current_price, bars, technical),
            self._get_macro_position(ticker, macro, market_data),
            self._get_timing_position(ticker, current_price, market_data),
        ]

        # Wait for all with timeout
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=15.0  # 15 second total timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"{ticker}: Agent position gathering timed out")
            results = []

        # Collect valid positions
        agent_positions = []
        for result in results:
            if isinstance(result, AgentPosition):
                agent_positions.append(result)
            elif isinstance(result, Exception):
                logger.warning(f"Agent error: {result}")

        return agent_positions

    async def _get_news_position(
        self,
        ticker: str,
        news: List[Dict],
        current_price: float,
    ) -> AgentPosition:
        """Get position from news agent."""
        try:
            result = await NewsIntelligenceAgent.analyze_with_cache(
                news_items=news,
                ticker=ticker,
            )

            # Convert result to AgentPosition
            score = result.get("score", 50)
            sentiment = result.get("sentiment", "neutral")

            if score >= 70:
                direction = "BUY"
            elif score >= 60:
                direction = "HOLD"
            elif score <= 30:
                direction = "SELL"
            else:
                direction = "HOLD"

            return AgentPosition(
                agent_name="news",
                direction=direction,
                confidence=result.get("confidence", 50),
                score=score,
                reasoning=result.get("summary", result.get("analysis", "")),
                key_arguments=result.get("catalysts", []),
                risks_identified=result.get("risks", []),
                data_cited={"sentiment": sentiment, "magnitude": result.get("magnitude", 5)},
            )
        except Exception as e:
            logger.error(f"News agent error: {e}")
            return AgentPosition(
                agent_name="news",
                direction="HOLD",
                confidence=30,
                score=50,
                reasoning=f"Error: {str(e)}",
                key_arguments=[],
                risks_identified=["Agent error"],
            )

    async def _get_technical_position(
        self,
        ticker: str,
        current_price: float,
        bars: List[Dict],
        technical: Dict[str, Any],
    ) -> AgentPosition:
        """Get position from technical agent."""
        try:
            result = await TechnicalAnalysisAgent.analyze_with_cache(
                ticker=ticker,
                current_price=current_price,
                bars=bars,
                rsi=technical.get("rsi"),
                macd=technical.get("macd"),
                sma_20=technical.get("sma_20"),
                sma_50=technical.get("sma_50"),
                sma_200=technical.get("sma_200"),
            )

            score = result.get("score", 50)
            trend = result.get("trend", "neutral")

            if score >= 70:
                direction = "BUY"
            elif score >= 60:
                direction = "HOLD"
            elif score <= 30:
                direction = "SELL"
            else:
                direction = "HOLD"

            key_args = []
            if result.get("rsi_signal"):
                key_args.append(f"RSI: {result['rsi_signal']}")
            if result.get("macd_signal"):
                key_args.append(f"MACD: {result['macd_signal']}")
            if result.get("ma_alignment"):
                key_args.append(f"MA alignment: {result['ma_alignment']}")

            return AgentPosition(
                agent_name="technical",
                direction=direction,
                confidence=result.get("confidence", 50),
                score=score,
                reasoning=result.get("summary", f"Trend: {trend}"),
                key_arguments=key_args,
                risks_identified=[],
                data_cited={
                    "trend": trend,
                    "momentum": result.get("momentum", "flat"),
                    "support": result.get("support_levels", []),
                    "resistance": result.get("resistance_levels", []),
                },
            )
        except Exception as e:
            logger.error(f"Technical agent error: {e}")
            return AgentPosition(
                agent_name="technical",
                direction="HOLD",
                confidence=30,
                score=50,
                reasoning=f"Error: {str(e)}",
                key_arguments=[],
                risks_identified=["Agent error"],
            )

    async def _get_macro_position(
        self,
        ticker: str,
        macro: Dict[str, Any],
        market_data: Dict[str, Any],
    ) -> AgentPosition:
        """Get position from macro agent."""
        try:
            vix = market_data.get("vix", 20)
            spy_data = market_data.get("spy", {})
            sectors = market_data.get("sectors", {})

            signal = await MacroAgent.analyze_with_cache(
                vix_level=vix,
                spy_data=spy_data,
                sector_performance=sectors,
            )

            score = signal.score
            if score >= 70:
                direction = "BUY"
            elif score >= 60:
                direction = "HOLD"
            elif score <= 30:
                direction = "SELL"
            else:
                direction = "HOLD"

            return AgentPosition(
                agent_name="macro",
                direction=direction,
                confidence=signal.confidence,
                score=score,
                reasoning=signal.reasoning,
                key_arguments=signal.key_factors,
                risks_identified=signal.risks,
                data_cited={
                    "regime": signal.regime.value,
                    "risk_environment": signal.risk_environment.value,
                    "vix_assessment": signal.vix_assessment,
                },
            )
        except Exception as e:
            logger.error(f"Macro agent error: {e}")
            return AgentPosition(
                agent_name="macro",
                direction="HOLD",
                confidence=30,
                score=50,
                reasoning=f"Error: {str(e)}",
                key_arguments=[],
                risks_identified=["Agent error"],
            )

    async def _get_timing_position(
        self,
        ticker: str,
        current_price: float,
        market_data: Dict[str, Any],
    ) -> AgentPosition:
        """Get position from timing agent."""
        try:
            vwap = market_data.get("vwap", current_price)
            intraday_bars = market_data.get("intraday_bars", [])
            spread = market_data.get("spread", 0.01)
            volume = market_data.get("volume", 100000)
            avg_volume = market_data.get("avg_volume", 100000)
            time_of_day = market_data.get("time_of_day", "morning")

            signal = await TradeTimingAgent.analyze_with_cache(
                ticker=ticker,
                current_price=current_price,
                action="BUY",  # Default to analyzing buy timing
                vwap=vwap,
                intraday_bars=intraday_bars,
                current_spread=spread,
                current_volume=volume,
                avg_volume=avg_volume,
                time_of_day=time_of_day,
            )

            # Timing agent influences entry, not direction
            # High timing score = good time to enter
            # Low timing score = wait for better entry
            score = signal.score
            urgency = signal.urgency

            if urgency > 70:
                direction = "BUY"  # Good timing, proceed
            elif urgency < 30:
                direction = "HOLD"  # Bad timing, wait
            else:
                direction = "HOLD"

            return AgentPosition(
                agent_name="timing",
                direction=direction,
                confidence=signal.confidence,
                score=score,
                reasoning=signal.reasoning,
                key_arguments=signal.entry_signals,
                risks_identified=signal.wait_signals,
                data_cited={
                    "action": signal.action.value,
                    "price_vs_vwap": signal.price_vs_vwap,
                    "liquidity_score": signal.liquidity_score,
                },
            )
        except Exception as e:
            logger.error(f"Timing agent error: {e}")
            return AgentPosition(
                agent_name="timing",
                direction="HOLD",
                confidence=30,
                score=50,
                reasoning=f"Error: {str(e)}",
                key_arguments=[],
                risks_identified=["Agent error"],
            )

    def _determine_consensus(
        self,
        positions: List[AgentPosition],
    ) -> Tuple[str, float]:
        """
        Determine the consensus direction and strength.

        Returns:
            Tuple of (consensus_direction, consensus_strength_percent)
        """
        direction_scores = {"BUY": 0.0, "SELL": 0.0, "HOLD": 0.0}

        for pos in positions:
            weight = self.agent_weights.get(pos.agent_name.lower(), 0.1)
            normalized_confidence = pos.confidence / 100

            # Map STRONG_BUY/STRONG_SELL to BUY/SELL with higher weight
            if pos.direction in ["STRONG_BUY", "BUY"]:
                multiplier = 1.5 if pos.direction == "STRONG_BUY" else 1.0
                direction_scores["BUY"] += weight * normalized_confidence * multiplier
            elif pos.direction in ["STRONG_SELL", "SELL"]:
                multiplier = 1.5 if pos.direction == "STRONG_SELL" else 1.0
                direction_scores["SELL"] += weight * normalized_confidence * multiplier
            else:
                direction_scores["HOLD"] += weight * normalized_confidence

        # Determine winner
        total = sum(direction_scores.values())
        if total == 0:
            return "HOLD", 0

        consensus = max(direction_scores, key=direction_scores.get)
        strength = (direction_scores[consensus] / total) * 100

        return consensus, strength

    async def _generate_challenges(
        self,
        ticker: str,
        positions: List[AgentPosition],
        consensus_direction: str,
        market_data: Dict[str, Any],
    ) -> List[Challenge]:
        """
        Have the contrarian agent challenge the consensus.
        """
        try:
            # Build consensus summary for contrarian
            consensus_confidence = sum(
                p.confidence for p in positions
                if p.direction in ["BUY", "STRONG_BUY"] if consensus_direction == "BUY"
            ) / len(positions) if positions else 50

            # Run contrarian agent
            news_sentiment = {"sentiment": "neutral", "score": 50}
            for pos in positions:
                if pos.agent_name == "news":
                    news_sentiment = {
                        "sentiment": pos.data_cited.get("sentiment", "neutral"),
                        "score": pos.score,
                    }
                    break

            technical_trend = "neutral"
            for pos in positions:
                if pos.agent_name == "technical":
                    technical_trend = pos.data_cited.get("trend", "neutral")
                    break

            contrarian = await ContrarianAgent.analyze_with_cache(
                ticker=ticker,
                consensus_direction=consensus_direction.lower(),
                consensus_confidence=consensus_confidence,
                news_sentiment=news_sentiment,
                technical_trend=technical_trend,
                agent_positions=[p.to_dict() for p in positions],
            )

            # Generate challenges from contrarian findings
            challenges = []
            for i, counter_arg in enumerate(contrarian.counter_arguments[:3]):
                challenges.append(Challenge(
                    challenger="contrarian",
                    challenged="consensus",
                    challenge_type="logic_flaw",
                    challenge_text=counter_arg,
                    severity="medium" if i > 0 else "high",
                ))

            for concern in contrarian.positioning_concerns[:2]:
                challenges.append(Challenge(
                    challenger="contrarian",
                    challenged="consensus",
                    challenge_type="overconfidence",
                    challenge_text=concern,
                    severity="medium",
                ))

            return challenges

        except Exception as e:
            logger.error(f"Challenge generation error: {e}")
            return []

    def _process_challenges(
        self,
        positions: List[AgentPosition],
        challenges: List[Challenge],
    ) -> List[AgentPosition]:
        """
        Process challenges and adjust agent confidences.

        High-severity challenges reduce confidence of challenged positions.
        """
        adjusted = []
        challenge_count = len(challenges)

        for pos in positions:
            new_confidence = pos.confidence

            # Reduce confidence based on challenges
            if challenge_count > 0:
                # High severity challenges have more impact
                high_severity = sum(1 for c in challenges if c.severity == "high")
                confidence_reduction = (high_severity * 10) + (challenge_count * 3)
                new_confidence = max(20, pos.confidence - confidence_reduction)

            adjusted.append(AgentPosition(
                agent_name=pos.agent_name,
                direction=pos.direction,
                confidence=new_confidence,
                score=pos.score,
                reasoning=pos.reasoning,
                key_arguments=pos.key_arguments,
                risks_identified=pos.risks_identified + [c.challenge_text for c in challenges[:2]],
                data_cited=pos.data_cited,
                timestamp=pos.timestamp,
            ))

        return adjusted

    async def _calculate_outcome(
        self,
        ticker: str,
        positions: List[AgentPosition],
        debate: DebateRound,
        market_data: Dict[str, Any],
        account: Dict[str, Any],
        current_positions: List[Dict[str, Any]],
    ) -> DebateOutcome:
        """
        Calculate the final outcome with weighted voting.
        """
        # Calculate weighted votes
        vote_scores = {"BUY": 0.0, "SELL": 0.0, "HOLD": 0.0}
        vote_breakdown = {}
        vote_weights = {}

        for pos in positions:
            agent_weight = self.agent_weights.get(pos.agent_name.lower(), 0.1)
            normalized_conf = pos.confidence / 100

            # Determine vote direction
            if pos.direction in ["STRONG_BUY", "BUY"]:
                vote_dir = "BUY"
            elif pos.direction in ["STRONG_SELL", "SELL"]:
                vote_dir = "SELL"
            else:
                vote_dir = "HOLD"

            vote_scores[vote_dir] += agent_weight * normalized_conf
            vote_breakdown[pos.agent_name] = vote_dir
            vote_weights[pos.agent_name] = agent_weight

        # Normalize votes
        total_votes = sum(vote_scores.values())
        if total_votes > 0:
            vote_scores = {k: v / total_votes for k, v in vote_scores.items()}

        # Determine winning action
        final_action = max(vote_scores, key=vote_scores.get)
        consensus_confidence = vote_scores[final_action] * 100

        # Check consensus threshold
        if consensus_confidence < self.consensus_threshold * 100:
            final_action = "HOLD"
            consensus_confidence = 50

        # Calculate weighted score
        weighted_score = sum(
            pos.score * self.agent_weights.get(pos.agent_name.lower(), 0.1)
            for pos in positions
        ) / sum(self.agent_weights.get(pos.agent_name.lower(), 0.1) for pos in positions)

        # Run risk assessment
        current_price = market_data.get("quote", {}).get("price", 100)
        volatility = market_data.get("technical", {}).get("volatility", 2)
        proposed_qty = int(account.get("equity", 100000) * 0.02 / current_price)  # 2% risk

        risk_assessment = await RiskManagementAgent.analyze_with_cache(
            ticker=ticker,
            proposed_action=final_action,
            proposed_quantity=proposed_qty,
            current_price=current_price,
            ticker_volatility=volatility,
            current_positions=current_positions,
            account=account,
        )

        # Apply risk veto
        risk_veto = risk_assessment.veto
        risk_veto_reason = risk_assessment.veto_reason

        if risk_veto:
            final_action = "HOLD"
            consensus_confidence = min(consensus_confidence, 40)

        # Extract agreements and disagreements
        key_agreements = []
        unresolved_disagreements = []

        # Find agreements (multiple agents with same direction)
        direction_agents = {}
        for pos in positions:
            dir_key = "BUY" if pos.direction in ["BUY", "STRONG_BUY"] else \
                      "SELL" if pos.direction in ["SELL", "STRONG_SELL"] else "HOLD"
            if dir_key not in direction_agents:
                direction_agents[dir_key] = []
            direction_agents[dir_key].append(pos.agent_name)

        for direction, agents in direction_agents.items():
            if len(agents) >= 2:
                key_agreements.append(f"{', '.join(agents)} agree on {direction}")

        # Find disagreements
        for c in debate.challenges:
            unresolved_disagreements.append(c.challenge_text[:100])

        # Build risk warnings
        risk_warnings = risk_assessment.warnings + risk_assessment.risk_factors

        # Generate summary
        debate_summary = self._generate_summary(
            positions, final_action, consensus_confidence, risk_assessment
        )

        return DebateOutcome(
            ticker=ticker,
            final_action=final_action,
            consensus_confidence=consensus_confidence,
            weighted_score=weighted_score,
            vote_breakdown=vote_breakdown,
            vote_weights=vote_weights,
            total_votes={k: v * 100 for k, v in vote_scores.items()},
            risk_veto=risk_veto,
            risk_veto_reason=risk_veto_reason,
            suggested_shares=risk_assessment.suggested_shares,
            max_position_value=risk_assessment.max_dollar_amount,
            stop_loss=current_price * 0.97 if final_action in ["BUY", "STRONG_BUY"] else None,
            take_profit=current_price * 1.05 if final_action in ["BUY", "STRONG_BUY"] else None,
            key_agreements=key_agreements,
            unresolved_disagreements=unresolved_disagreements[:3],
            risk_warnings=risk_warnings[:5],
            debate_summary=debate_summary,
            reasoning=f"Consensus {final_action} with {consensus_confidence:.0f}% confidence",
        )

    def _generate_summary(
        self,
        positions: List[AgentPosition],
        final_action: str,
        confidence: float,
        risk: RiskAssessment,
    ) -> str:
        """Generate a human-readable debate summary."""
        agent_votes = []
        for pos in positions:
            agent_votes.append(f"{pos.agent_name}: {pos.direction}")

        summary = f"Debate concluded with {final_action} ({confidence:.0f}% confidence). "
        summary += f"Votes: {', '.join(agent_votes)}. "

        if risk.veto:
            summary += f"VETOED by risk agent: {risk.veto_reason}. "
        else:
            summary += f"Risk score: {risk.score:.0f}/100, suggested size: {risk.suggested_shares} shares."

        return summary
