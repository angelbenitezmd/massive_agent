"""
Powerful AI Agents using Claude and OpenAI with Smart Caching.

These agents provide deep analysis of market data using LLMs.
Each agent specializes in a different aspect of trading intelligence.

IMPORTANT: LLMs are expensive. These agents should only run when:
- No cached signal exists
- Upstream data has changed since last run
- Cache has expired

Use the agent_cache module to check before calling these agents.
"""
import logging
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.services.llm_service import llm_service, LLMProvider
from app.services.agent_cache import agent_cache, AgentType
from app.services.technical_indicators import (
    analyze_technical,
    get_regime_string,
    TechnicalSignal,
)

logger = logging.getLogger(__name__)


class NewsIntelligenceAgent:
    """
    Deep news analysis using Claude.

    Unlike simple keyword matching, this agent actually reads and understands
    news articles, extracts key information, and assesses market impact.
    """

    SYSTEM_PROMPT = """You are an elite financial analyst at a top hedge fund scoring stocks for INTRADAY trades.

SCORING SCALE (use the FULL range):
  85-95: EXCEPTIONAL — breaking catalyst with clear directional impact (major earnings beat, FDA approval, transformative deal). Rare.
  75-84: STRONG BUY — fresh catalyst within 2 hours, multiple confirming signals (upgrade + news, beat + guidance raise). This is your primary actionable zone.
  65-74: LEAN BULLISH — modest positive signal or aging catalyst. Tradeable only with strong technicals.
  45-64: NEUTRAL — no fresh edge, mixed signals, or already priced in. Most stocks most days.
  30-44: LEAN BEARISH — negative signals, downgrade, miss, or deteriorating outlook.
  10-29: STRONG SELL — severe negative catalyst (fraud, massive miss, regulatory action).

DATA YOU RECEIVE:
- News articles with freshness labels ([BREAKING] < 15min, [FRESH] < 1h, [RECENT] < 4h, [STALE] > 4h)
- Earnings data (EPS beats/misses, revenue)
- Analyst rating changes (upgrades/downgrades with price targets)
- Overall analyst consensus

CRITICAL RULES:
- A "Strong Buy" consensus with NO recent news = 50-55. Consensus alone is NOT a catalyst.
- [BREAKING] or [FRESH] positive catalyst with confirming data = 75-85. Score aggressively for genuine opportunities.
- [STALE] news = discount heavily. If the catalyst is >4h old, the move has likely happened.
- Earnings beat already reported days ago = priced in = ~50 unless new analyst actions confirm upside.
- Multiple confirming signals (news + upgrade + beat) deserve scores in the 80s.
- DO NOT anchor at 50. If the data clearly supports a buy, score 75+. If it clearly supports avoiding, score <40.

Return JSON with your analysis."""

    @staticmethod
    async def analyze(
        news_items: List[Dict],
        ticker: str,
        earnings_data: Optional[List[Dict]] = None,
        ratings_data: Optional[List[Dict]] = None,
        consensus_data: Optional[Dict] = None,
        market_context: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Analyze all available market data using Claude.

        Args:
            news_items: List of news articles
            ticker: Stock ticker being analyzed
            earnings_data: Recent earnings results (EPS beat/miss)
            ratings_data: Recent analyst rating changes
            consensus_data: Overall analyst consensus

        Returns:
            Deep analysis with sentiment, catalysts, and trading signals
        """
        if not news_items and not earnings_data and not ratings_data:
            return {
                "sentiment": "neutral",
                "score": 50,
                "confidence": 0,
                "analysis": "No data available",
                "catalysts": [],
                "risks": [],
                "agent": "NewsIntelligenceAgent",
                "provider": "none"
            }

        # === Format all data for the LLM ===
        prompt_parts = [f"Full analysis for {ticker}:\n"]

        # News articles (with freshness labels)
        if news_items:
            prompt_parts.append("== RECENT NEWS ==")
            now = datetime.utcnow()
            for i, item in enumerate(news_items[:5], 1):
                title = item.get("title", "")
                teaser = item.get("teaser", item.get("body", ""))[:400]
                published = item.get("published", item.get("created", ""))
                # Calculate age and add freshness label
                age_label = ""
                if published:
                    try:
                        pub_dt = datetime.fromisoformat(str(published).replace("Z", "+00:00"))
                        if pub_dt.tzinfo:
                            pub_dt = pub_dt.replace(tzinfo=None)
                        age_minutes = (now - pub_dt).total_seconds() / 60
                        if age_minutes < 15:
                            age_label = f"[BREAKING - {int(age_minutes)}m]"
                        elif age_minutes < 60:
                            age_label = f"[FRESH - {int(age_minutes)}m]"
                        elif age_minutes < 240:
                            age_label = f"[RECENT - {age_minutes / 60:.1f}h]"
                        else:
                            age_label = f"[STALE - {age_minutes / 60:.1f}h]"
                    except (ValueError, TypeError):
                        pass
                prompt_parts.append(f"[{i}] {age_label} {title}\n    Published: {published}\n    {teaser}\n")
        else:
            prompt_parts.append("== RECENT NEWS ==\nNo recent news articles found.\n")

        # Earnings
        if earnings_data:
            prompt_parts.append("== EARNINGS ==")
            for earn in earnings_data[:2]:
                date = earn.get("date", "")
                est_eps = earn.get("estimated_eps", "N/A")
                act_eps = earn.get("actual_eps", "N/A")
                est_rev = earn.get("estimated_revenue", "N/A")
                act_rev = earn.get("actual_revenue", "N/A")
                prompt_parts.append(f"  Date: {date} | EPS: est {est_eps} vs actual {act_eps} | Revenue: est {est_rev} vs actual {act_rev}")
            prompt_parts.append("")

        # Analyst ratings
        if ratings_data:
            prompt_parts.append("== RECENT ANALYST ACTIONS ==")
            for r in ratings_data[:5]:
                analyst = r.get("analyst", "Unknown")
                firm = r.get("analyst_firm", r.get("firm", ""))
                action = r.get("rating_action", "")
                current = r.get("rating_current", "")
                pt_current = r.get("pt_current", "")
                date = r.get("date", "")
                prompt_parts.append(f"  {date} | {firm}: {action} to {current} (PT: ${pt_current})")
            prompt_parts.append("")

        # Consensus
        if consensus_data and consensus_data.get("results"):
            cons = consensus_data["results"][0] if isinstance(consensus_data["results"], list) else consensus_data["results"]
            rating = cons.get("consensus_rating", "N/A")
            pt = cons.get("target_price", cons.get("consensus_price_target", "N/A"))
            prompt_parts.append(f"== ANALYST CONSENSUS ==\n  Rating: {rating} | Target Price: ${pt}\n")

        # Market context (momentum, volume, SPY, RSI, earnings dates) when available
        if market_context:
            prompt_parts.append("== MARKET CONTEXT ==")
            prompt_parts.append(f"  Price: ${market_context.get('price', 'N/A')}")
            prompt_parts.append(f"  Day Change: {market_context.get('change_pct', 'N/A')}%")
            mom5 = market_context.get('momentum_5d_pct')
            if mom5 is not None:
                prompt_parts.append(f"  5-Day Momentum: {mom5:+.1f}%")
            rsi_val = market_context.get('rsi')
            if rsi_val is not None:
                prompt_parts.append(f"  RSI(14): {rsi_val} (overbought >70, oversold <30)")
            prompt_parts.append(f"  Volume: {market_context.get('volume', 'N/A'):,}" if isinstance(market_context.get('volume'), (int, float)) else f"  Volume: {market_context.get('volume', 'N/A')}")
            vol_vs_avg = market_context.get('volume_vs_avg')
            if vol_vs_avg is not None:
                elev = " (elevated)" if market_context.get('volume_elevated') else ""
                prompt_parts.append(f"  Volume vs 20d Avg: {vol_vs_avg:.1f}x{elev}")
            spy = market_context.get('spy_change_pct')
            if spy is not None:
                prompt_parts.append(f"  SPY (market) today: {spy}%")
            next_earn = market_context.get('next_earnings_date')
            last_earn = market_context.get('last_earnings_date')
            if next_earn:
                prompt_parts.append(f"  Next earnings: {next_earn}")
            if last_earn:
                prompt_parts.append(f"  Last earnings: {last_earn}")
            prompt_parts.append("")

        data_text = "\n".join(prompt_parts)

        user_prompt = f"""{data_text}
Based on ALL the data above, provide your trading analysis in this JSON format:
{{
    "sentiment": "bullish" | "bearish" | "neutral",
    "score": <0-100, where 50 is neutral, >70 is strong buy signal, <30 is strong sell>,
    "confidence": <0-100>,
    "summary": "<2-3 sentence summary of why to trade or not trade>",
    "catalysts": ["<specific actionable catalysts>"],
    "risks": ["<risks to the thesis>"],
    "trading_implication": "<BUY / SELL / HOLD with brief reason>"
}}"""

        result = await llm_service.analyze(
            system_prompt=NewsIntelligenceAgent.SYSTEM_PROMPT,
            user_prompt=user_prompt,
            prefer=LLMProvider.CLAUDE,
            temperature=0.2,
            agent_type="news",
        )

        if result.get("error"):
            logger.warning(f"NewsIntelligenceAgent error: {result['error']}")
            return {
                "sentiment": "neutral",
                "score": 50,
                "confidence": 0,
                "analysis": f"LLM unavailable: {result.get('error')}",
                "agent": "NewsIntelligenceAgent",
                "provider": "fallback"
            }

        result["agent"] = "NewsIntelligenceAgent"
        return result

    @staticmethod
    async def analyze_with_cache(
        news_items: List[Dict],
        ticker: str,
        latest_news_ts: Optional[datetime] = None,
        force: bool = False,
        earnings_data: Optional[List[Dict]] = None,
        ratings_data: Optional[List[Dict]] = None,
        consensus_data: Optional[Dict] = None,
        market_context: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Analyze with caching - only calls LLM if needed.

        Args:
            news_items: List of news articles
            ticker: Stock ticker being analyzed
            latest_news_ts: Timestamp of most recent news article
            force: Force LLM call even if cache is valid
            earnings_data: Recent earnings results
            ratings_data: Recent analyst rating changes
            consensus_data: Overall analyst consensus
            market_context: Optional momentum, volume, price (when LLM runs with full context)

        Returns:
            Analysis result (may be cached)
        """
        ticker = ticker.upper()

        # Check if we should run the agent
        if not force and not agent_cache.should_run_news_agent(ticker, latest_news_ts):
            cached = agent_cache.get_cached_signal(ticker, AgentType.NEWS)
            if cached:
                logger.info(f"NewsAgent for {ticker}: Using cached result")
                return cached

        # Run the agent with all available data (news, earnings, ratings, consensus, market context)
        logger.info(f"NewsAgent for {ticker}: Running LLM analysis")
        result = await NewsIntelligenceAgent.analyze(
            news_items, ticker,
            earnings_data=earnings_data,
            ratings_data=ratings_data,
            consensus_data=consensus_data,
            market_context=market_context,
        )

        # Cache the result
        agent_cache.set_cached_signal(
            ticker=ticker,
            agent_type=AgentType.NEWS,
            signal=result,
            input_hash=agent_cache._hash_data(news_items[:3] if news_items else None),
        )

        return result


class TechnicalAnalysisAgent:
    """
    Advanced technical analysis using OpenAI.

    Analyzes price action, volume, and technical indicators to generate
    trading signals with specific entry/exit points.
    """

    SYSTEM_PROMPT = """You are a professional technical analyst and quantitative trader.
Your job is to analyze price charts and technical indicators to identify trading opportunities.

You must assess:
1. **Trend**: What is the current trend direction and strength?
2. **Momentum**: Is momentum increasing or decreasing?
3. **Support/Resistance**: Key price levels to watch
4. **Volume**: Is volume confirming price action?
5. **Patterns**: Any chart patterns forming?
6. **Entry/Exit**: Specific price levels for trades

Technical indicators to consider:
- RSI (overbought >70, oversold <30)
- MACD (crossovers, divergences)
- Moving Averages (SMA 20, 50, 200)
- Volume trends
- Bollinger Bands
- Price action patterns

Return JSON with your analysis."""

    @staticmethod
    async def analyze(
        ticker: str,
        current_price: float,
        bars: List[Dict],
        rsi: Optional[float] = None,
        macd: Optional[Dict] = None,
        sma_20: Optional[float] = None,
        sma_50: Optional[float] = None,
        sma_200: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Analyze technical indicators using OpenAI.

        Args:
            ticker: Stock ticker
            current_price: Current stock price
            bars: Recent price bars
            rsi: RSI value
            macd: MACD values dict
            sma_20/50/200: Moving averages

        Returns:
            Technical analysis with signals and levels
        """
        # Calculate basic stats from bars
        if bars:
            recent_bars = bars[-20:] if len(bars) >= 20 else bars
            highs = [b.get("high", b.get("close", 0)) for b in recent_bars]
            lows = [b.get("low", b.get("close", 0)) for b in recent_bars]
            closes = [b.get("close", 0) for b in recent_bars]
            volumes = [b.get("volume", 0) for b in recent_bars]

            recent_high = max(highs) if highs else current_price
            recent_low = min(lows) if lows else current_price
            avg_volume = sum(volumes) / len(volumes) if volumes else 0
            price_change = ((closes[-1] - closes[0]) / closes[0] * 100) if closes and closes[0] > 0 else 0
        else:
            recent_high = current_price
            recent_low = current_price
            avg_volume = 0
            price_change = 0

        user_prompt = f"""Analyze {ticker} at ${current_price:.2f}:

PRICE DATA:
- Current Price: ${current_price:.2f}
- 20-period High: ${recent_high:.2f}
- 20-period Low: ${recent_low:.2f}
- Period Change: {price_change:+.2f}%
- Average Volume: {avg_volume:,.0f}

TECHNICAL INDICATORS:
- RSI(14): {f'{rsi:.1f}' if rsi else 'N/A'}
- MACD: {macd.get('value', 'N/A') if macd else 'N/A'}
- MACD Signal: {macd.get('signal', 'N/A') if macd else 'N/A'}
- MACD Histogram: {macd.get('histogram', 'N/A') if macd else 'N/A'}
- SMA 20: {f'${sma_20:.2f}' if sma_20 else 'N/A'}
- SMA 50: {f'${sma_50:.2f}' if sma_50 else 'N/A'}
- SMA 200: {f'${sma_200:.2f}' if sma_200 else 'N/A'}

Provide your analysis in this JSON format:
{{
    "trend": "bullish" | "bearish" | "neutral",
    "trend_strength": "strong" | "moderate" | "weak",
    "score": <0-100, where 50 is neutral>,
    "confidence": <0-100>,
    "momentum": "increasing" | "decreasing" | "flat",
    "rsi_signal": "overbought" | "oversold" | "neutral",
    "macd_signal": "bullish_crossover" | "bearish_crossover" | "neutral",
    "ma_alignment": "bullish" | "bearish" | "mixed",
    "support_levels": [<price levels>],
    "resistance_levels": [<price levels>],
    "entry_zone": {{"low": <price>, "high": <price>}},
    "stop_loss": <price>,
    "target_1": <price>,
    "target_2": <price>,
    "pattern": "<any chart pattern identified>",
    "summary": "<2-3 sentence technical outlook>"
}}"""

        result = await llm_service.analyze(
            system_prompt=TechnicalAnalysisAgent.SYSTEM_PROMPT,
            user_prompt=user_prompt,
            prefer=LLMProvider.OPENAI,  # Use OpenAI for technical
            temperature=0.2,
            agent_type="technical",
        )

        if result.get("error"):
            logger.warning(f"TechnicalAnalysisAgent error: {result['error']}")
            # Fallback to simple analysis
            return TechnicalAnalysisAgent._simple_analysis(
                ticker, current_price, rsi, macd, sma_20, sma_50, sma_200
            )

        result["agent"] = "TechnicalAnalysisAgent"
        return result

    @staticmethod
    async def analyze_with_cache(
        ticker: str,
        current_price: float,
        bars: List[Dict],
        rsi: Optional[float] = None,
        macd: Optional[Dict] = None,
        sma_20: Optional[float] = None,
        sma_50: Optional[float] = None,
        sma_200: Optional[float] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Analyze technical indicators with caching.

        PREFERRED: Use pure Python technical_indicators.analyze_technical()
        for the main loop. Only call this LLM version when regime changes
        significantly or for deep analysis requests.

        Args:
            ticker: Stock ticker
            current_price: Current stock price
            bars: Recent price bars
            rsi, macd, sma_*: Technical indicators
            force: Force LLM call even if cache is valid

        Returns:
            Technical analysis with signals and levels (may be cached)
        """
        ticker = ticker.upper()

        # First, get pure Python analysis (always cheap)
        local_analysis = analyze_technical(ticker, current_price, bars)
        current_regime = get_regime_string(local_analysis.regime)
        technical_score = local_analysis.score

        # Check if we should run the LLM agent
        if not force and not agent_cache.should_run_technical_agent(
            ticker, current_regime, technical_score
        ):
            cached = agent_cache.get_cached_signal(ticker, AgentType.TECHNICAL)
            if cached:
                logger.info(f"TechnicalAgent for {ticker}: Using cached LLM result")
                # Merge with fresh local analysis
                cached["local_indicators"] = local_analysis.to_dict()
                return cached

        # Run the LLM agent
        logger.info(f"TechnicalAgent for {ticker}: Running LLM analysis (regime: {current_regime})")
        result = await TechnicalAnalysisAgent.analyze(
            ticker, current_price, bars, rsi, macd, sma_20, sma_50, sma_200
        )

        # Cache the result
        agent_cache.set_cached_signal(
            ticker=ticker,
            agent_type=AgentType.TECHNICAL,
            signal=result,
            input_hash=agent_cache._hash_data({
                "regime": current_regime,
                "score": technical_score,
            }),
        )

        # Include local analysis
        result["local_indicators"] = local_analysis.to_dict()

        return result

    @staticmethod
    def _simple_analysis(
        ticker: str,
        price: float,
        rsi: Optional[float],
        macd: Optional[Dict],
        sma_20: Optional[float],
        sma_50: Optional[float],
        sma_200: Optional[float]
    ) -> Dict[str, Any]:
        """Simple fallback analysis without LLM."""
        score = 50
        signals = []

        if rsi:
            if rsi > 70:
                score -= 15
                signals.append("RSI overbought")
            elif rsi < 30:
                score += 15
                signals.append("RSI oversold")

        if macd and macd.get("histogram"):
            if macd["histogram"] > 0:
                score += 10
                signals.append("MACD bullish")
            else:
                score -= 10
                signals.append("MACD bearish")

        if sma_20 and sma_50:
            if price > sma_20 > sma_50:
                score += 10
                signals.append("Above MAs (bullish)")
            elif price < sma_20 < sma_50:
                score -= 10
                signals.append("Below MAs (bearish)")

        return {
            "trend": "bullish" if score > 55 else "bearish" if score < 45 else "neutral",
            "score": max(0, min(100, score)),
            "confidence": 50,
            "signals": signals,
            "agent": "TechnicalAnalysisAgent",
            "provider": "fallback"
        }


class SentimentSynthesisAgent:
    """
    Combines multiple signals into a final trading decision using Claude.

    This agent takes outputs from other agents and synthesizes them into
    a coherent trading strategy with position sizing recommendations.
    """

    SYSTEM_PROMPT = """You are the Chief Investment Officer at a quantitative hedge fund.
Your job is to synthesize multiple analysis signals into a final trading decision.

You receive:
1. News/Sentiment analysis
2. Technical analysis
3. Earnings data
4. Current positions and risk metrics

You must decide:
1. **Action**: BUY, SELL, HOLD, or AVOID
2. **Conviction**: How strong is this signal? (1-10)
3. **Position Size**: What % of portfolio to allocate
4. **Timing**: Enter now or wait?
5. **Risk Management**: Stop loss and take profit levels

Consider:
- Risk/reward ratio (minimum 2:1 for new positions)
- Current portfolio exposure
- Correlation with existing positions
- Market conditions
- News catalysts vs technical setups

Be decisive but prudent. Capital preservation is paramount.
Return JSON with your final recommendation."""

    @staticmethod
    async def synthesize(
        ticker: str,
        news_analysis: Dict,
        technical_analysis: Dict,
        earnings_data: Optional[Dict] = None,
        current_price: float = 0,
        account: Optional[Dict] = None,
        positions: Optional[List] = None
    ) -> Dict[str, Any]:
        """
        Synthesize all signals into final trading decision.

        Args:
            ticker: Stock ticker
            news_analysis: Output from NewsIntelligenceAgent
            technical_analysis: Output from TechnicalAnalysisAgent
            earnings_data: Recent earnings info
            current_price: Current stock price
            account: Account info (equity, buying power)
            positions: Current positions

        Returns:
            Final trading decision with full recommendation
        """
        # Check if already has position
        has_position = False
        position_size = 0
        position_pnl = 0
        if positions:
            for pos in positions:
                if pos.get("symbol") == ticker:
                    has_position = True
                    position_size = pos.get("qty", 0)
                    position_pnl = pos.get("unrealized_plpc", 0) * 100

        user_prompt = f"""Synthesize analysis for {ticker} at ${current_price:.2f}:

NEWS ANALYSIS:
{_format_dict(news_analysis)}

TECHNICAL ANALYSIS:
{_format_dict(technical_analysis)}

EARNINGS DATA:
{_format_dict(earnings_data) if earnings_data else 'No recent earnings'}

PORTFOLIO CONTEXT:
- Has Existing Position: {has_position}
- Position Size: {position_size} shares
- Position P&L: {position_pnl:.2f}%
- Account Equity: ${account.get('equity', 100000):,.2f} (if available)
- Buying Power: ${account.get('buying_power', 50000):,.2f} (if available)

Provide your FINAL trading decision in this JSON format:
{{
    "action": "STRONG_BUY" | "BUY" | "HOLD" | "SELL" | "STRONG_SELL" | "AVOID",
    "conviction": <1-10>,
    "score": <0-100 composite score>,
    "confidence": <0-100>,

    "position_recommendation": {{
        "size_percent": <% of portfolio to allocate, 0-5%>,
        "shares": <suggested number of shares>,
        "dollar_amount": <suggested dollar amount>
    }},

    "entry_strategy": {{
        "timing": "immediate" | "wait_for_pullback" | "wait_for_breakout",
        "entry_price": <target entry price>,
        "entry_zone_low": <lower bound>,
        "entry_zone_high": <upper bound>
    }},

    "risk_management": {{
        "stop_loss": <stop loss price>,
        "stop_loss_percent": <% from entry>,
        "take_profit_1": <first target>,
        "take_profit_2": <second target>,
        "risk_reward_ratio": <calculated R:R>
    }},

    "thesis": "<2-3 sentence investment thesis>",
    "bull_case": "<best case scenario>",
    "bear_case": "<worst case scenario>",
    "key_risks": ["<list of key risks>"],
    "catalysts": ["<upcoming catalysts to watch>"],
    "time_horizon": "scalp" | "day_trade" | "swing" | "position"
}}"""

        result = await llm_service.analyze(
            system_prompt=SentimentSynthesisAgent.SYSTEM_PROMPT,
            user_prompt=user_prompt,
            prefer=LLMProvider.CLAUDE,
            temperature=0.3,
            agent_type="synthesis",
        )

        if result.get("error"):
            logger.warning(f"SentimentSynthesisAgent error: {result['error']}")
            return SentimentSynthesisAgent._simple_synthesis(
                news_analysis, technical_analysis
            )

        result["agent"] = "SentimentSynthesisAgent"
        return result

    @staticmethod
    async def synthesize_with_cache(
        ticker: str,
        news_analysis: Dict,
        technical_analysis: Dict,
        earnings_data: Optional[Dict] = None,
        current_price: float = 0,
        account: Optional[Dict] = None,
        positions: Optional[List] = None,
        risk_state: Optional[Dict] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Synthesize signals with caching - only calls LLM if upstream changed.

        Args:
            ticker: Stock ticker
            news_analysis: Output from NewsIntelligenceAgent
            technical_analysis: Output from TechnicalAnalysisAgent
            earnings_data: Recent earnings info
            current_price: Current stock price
            account: Account info (equity, buying power)
            positions: Current positions
            risk_state: Current risk state (circuit breaker level, etc.)
            force: Force LLM call even if cache is valid

        Returns:
            Final trading decision (may be cached)
        """
        ticker = ticker.upper()

        # Create hashes of upstream signals
        news_hash = agent_cache._hash_data(news_analysis)
        tech_hash = agent_cache._hash_data(technical_analysis)
        earnings_hash = agent_cache._hash_data(earnings_data) if earnings_data else "none"
        analyst_hash = "none"  # TODO: Add analyst agent
        risk_hash = agent_cache._hash_data(risk_state) if risk_state else "none"

        # Check if we should run the consensus agent
        if not force and not agent_cache.should_run_consensus_agent(
            ticker, news_hash, earnings_hash, analyst_hash, tech_hash, risk_hash
        ):
            cached = agent_cache.get_cached_signal(ticker, AgentType.CONSENSUS)
            if cached:
                logger.info(f"ConsensusAgent for {ticker}: Using cached result")
                return cached

        # Run the agent
        logger.info(f"ConsensusAgent for {ticker}: Running LLM synthesis")
        result = await SentimentSynthesisAgent.synthesize(
            ticker=ticker,
            news_analysis=news_analysis,
            technical_analysis=technical_analysis,
            earnings_data=earnings_data,
            current_price=current_price,
            account=account,
            positions=positions,
        )

        # Cache the result with upstream hashes
        agent_cache.set_cached_signal(
            ticker=ticker,
            agent_type=AgentType.CONSENSUS,
            signal=result,
            input_hash=f"{news_hash}_{tech_hash}_{risk_hash}",
            upstream_timestamps={
                "news": news_hash,
                "technical": tech_hash,
                "earnings": earnings_hash,
                "analyst": analyst_hash,
                "risk": risk_hash,
            },
        )

        return result

    @staticmethod
    def _simple_synthesis(news: Dict, technical: Dict) -> Dict[str, Any]:
        """Simple fallback synthesis without LLM."""
        news_score = news.get("score", 50)
        tech_score = technical.get("score", 50)

        # Weight news slightly higher
        composite = (news_score * 0.55) + (tech_score * 0.45)

        if composite >= 70:
            action = "BUY"
        elif composite >= 60:
            action = "HOLD"
        elif composite <= 30:
            action = "SELL"
        elif composite <= 40:
            action = "AVOID"
        else:
            action = "HOLD"

        return {
            "action": action,
            "score": round(composite),
            "confidence": 50,
            "conviction": round((abs(composite - 50) / 50) * 10),
            "thesis": f"News score {news_score}, Technical score {tech_score}",
            "agent": "SentimentSynthesisAgent",
            "provider": "fallback"
        }


def _format_dict(d: Optional[Dict]) -> str:
    """Format dict for prompt, handling None."""
    if not d:
        return "N/A"
    # Filter out large/irrelevant fields
    filtered = {k: v for k, v in d.items()
                if k not in ["raw_response", "provider", "agent"] and v is not None}
    return "\n".join(f"- {k}: {v}" for k, v in filtered.items())


# Convenience function to run full analysis
async def run_full_analysis(
    ticker: str,
    news_items: List[Dict],
    current_price: float,
    bars: List[Dict],
    rsi: Optional[float] = None,
    macd: Optional[Dict] = None,
    sma_20: Optional[float] = None,
    sma_50: Optional[float] = None,
    sma_200: Optional[float] = None,
    earnings: Optional[Dict] = None,
    earnings_items: Optional[List[Dict]] = None,
    ratings_data: Optional[List[Dict]] = None,
    consensus_data: Optional[Dict] = None,
    market_context: Optional[Dict] = None,
    account: Optional[Dict] = None,
    positions: Optional[List] = None,
    latest_news_ts: Optional[datetime] = None,
    risk_state: Optional[Dict] = None,
    force_llm: bool = False,
) -> Dict[str, Any]:
    """
    Run full multi-agent analysis WITH SMART CACHING.

    All three agents work together before producing a trade score:
    1. NewsIntelligenceAgent (news + earnings + ratings + consensus + market context)
    2. TechnicalAnalysisAgent (price bars, RSI, MACD, MAs)
    3. SentimentSynthesisAgent (synthesizes both into final BUY/SELL/HOLD + score)

    The trade score (final_score) comes from the synthesis - never from a single agent.

    Args:
        ticker: Stock ticker
        news_items: List of news articles
        current_price: Current price
        bars: Price bars
        rsi, macd, sma_*: Technical indicators
        earnings: Earnings dict for synthesis (legacy)
        earnings_items: Earnings list for News agent (Benzinga)
        ratings_data: Analyst ratings for News agent
        consensus_data: Analyst consensus for News agent
        market_context: Price, volume, momentum, SPY for News agent
        account: Account info
        positions: Current positions
        latest_news_ts: Timestamp of most recent news (for cache check)
        risk_state: Current risk state for consensus cache check
        force_llm: Force LLM calls even if cache valid

    Returns:
        Complete analysis with synthesis.final_score as the trade score
    """
    ticker = ticker.upper()

    # Run news and technical analysis in parallel (with caching)
    # News agent gets full context: earnings, ratings, consensus, market (same as feed LLM path)
    news_task = NewsIntelligenceAgent.analyze_with_cache(
        news_items, ticker, latest_news_ts, force=force_llm,
        earnings_data=earnings_items,
        ratings_data=ratings_data,
        consensus_data=consensus_data,
        market_context=market_context,
    )
    tech_task = TechnicalAnalysisAgent.analyze_with_cache(
        ticker, current_price, bars, rsi, macd, sma_20, sma_50, sma_200,
        force=force_llm
    )

    news_result, tech_result = await asyncio.gather(news_task, tech_task)

    # Synthesize into final decision (with caching)
    synthesis = await SentimentSynthesisAgent.synthesize_with_cache(
        ticker=ticker,
        news_analysis=news_result,
        technical_analysis=tech_result,
        earnings_data=earnings,
        current_price=current_price,
        account=account,
        positions=positions,
        risk_state=risk_state,
        force=force_llm,
    )

    # Gather cache stats
    cache_stats = agent_cache.get_stats()

    return {
        "ticker": ticker,
        "timestamp": datetime.utcnow().isoformat(),
        "current_price": current_price,
        "agents": {
            "news": news_result,
            "technical": tech_result
        },
        "synthesis": synthesis,
        "final_action": synthesis.get("action", "HOLD"),
        "final_score": synthesis.get("score", 50),
        "confidence": synthesis.get("confidence", 50),
        "cache_stats": cache_stats,
        "cached_agents": {
            "news": news_result.get("_cached", False),
            "technical": tech_result.get("_cached", False),
            "consensus": synthesis.get("_cached", False),
        },
    }


async def run_quick_analysis(
    ticker: str,
    current_price: float,
    bars: List[Dict],
) -> Dict[str, Any]:
    """
    Run FAST analysis using only Python (NO LLM calls).

    This should be called every minute as part of the main loop.
    It's cheap and provides technical signals without LLM costs.

    For deep analysis with LLMs, use run_full_analysis().

    Args:
        ticker: Stock ticker
        current_price: Current price
        bars: Price bars

    Returns:
        Technical analysis from pure Python indicators
    """
    ticker = ticker.upper()

    # Pure Python technical analysis
    technical = analyze_technical(ticker, current_price, bars)

    return {
        "ticker": ticker,
        "timestamp": datetime.utcnow().isoformat(),
        "current_price": current_price,
        "technical": technical.to_dict(),
        "score": technical.score,
        "regime": technical.regime.value,
        "trend": technical.trend,
        "signals": technical.signals,
        "provider": "local_python",
        "llm_called": False,
    }


def get_cache_status(ticker: Optional[str] = None) -> Dict[str, Any]:
    """
    Get cache status for monitoring.

    Args:
        ticker: Specific ticker or None for overall stats

    Returns:
        Cache statistics and status
    """
    if ticker:
        return agent_cache.get_cache_status(ticker)
    return agent_cache.get_stats()
