"""
Agent Output Caching Layer.

Implements smart caching for LLM agent outputs to reduce API costs.
Agents only run when upstream data has changed since their last execution.

Key principle: LLMs are the expensive "brain", not the heartbeat.
The heartbeat every minute should be mostly cheap (Alpaca + indicators + scanner).
LLMs should only run when there is new information or a strong reason.
"""
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class AgentType(Enum):
    """Types of AI agents in the system."""
    NEWS = "news"
    EARNINGS = "earnings"
    ANALYST = "analyst"
    TECHNICAL = "technical"
    CONSENSUS = "consensus"
    # New specialized agents
    MACRO = "macro"
    CONTRARIAN = "contrarian"
    RISK = "risk"
    EXIT = "exit"
    TIMING = "timing"
    # Debate system
    DEBATE = "debate"


@dataclass
class CachedSignal:
    """Cached agent output with metadata."""
    ticker: str
    agent_type: AgentType
    signal: Dict[str, Any]
    timestamp: datetime
    input_hash: str  # Hash of inputs used to generate this signal
    upstream_timestamps: Dict[str, datetime] = field(default_factory=dict)

    def is_expired(self, max_age_minutes: int = 15) -> bool:
        """Check if this cached signal has expired."""
        age = datetime.utcnow() - self.timestamp
        return age > timedelta(minutes=max_age_minutes)

    def age_seconds(self) -> float:
        """Return age of this cache entry in seconds."""
        return (datetime.utcnow() - self.timestamp).total_seconds()


@dataclass
class UpstreamData:
    """Tracks upstream data timestamps for change detection."""
    news_timestamp: Optional[datetime] = None
    earnings_timestamp: Optional[datetime] = None
    analyst_timestamp: Optional[datetime] = None
    technical_regime: Optional[str] = None  # "bullish", "bearish", "neutral"
    technical_hash: Optional[str] = None
    risk_state_hash: Optional[str] = None


class AgentCache:
    """
    In-memory cache for agent outputs with change detection.

    Each agent checks if its upstream data has changed before running.
    If no change, returns cached output instead of calling LLM.
    """

    def __init__(self):
        # Per-ticker caches for each agent type
        self._cache: Dict[str, Dict[AgentType, CachedSignal]] = {}

        # Track upstream data state per ticker
        self._upstream: Dict[str, UpstreamData] = {}

        # Configuration for cache expiration
        # COST OPTIMIZATION: LLM calls are expensive. Cache aggressively.
        # During market hours, news changes matter but intraday technical
        # noise does not justify re-running LLMs every 5 minutes.
        self.config = {
            AgentType.NEWS: {
                "max_age_minutes": 10,       # Re-check news every 10 min
                "min_interval_seconds": 120,  # At most once per 2 min — speed matters for fresh catalysts
            },
            AgentType.EARNINGS: {
                "max_age_minutes": 120,      # Earnings don't change often
                "min_interval_seconds": 600,  # Check every 10 minutes max
                "earnings_window_days": 1,   # Days around earnings to run agent
            },
            AgentType.ANALYST: {
                "max_age_minutes": 60,       # Ratings change infrequently
                "min_interval_seconds": 1800, # Check every 30 minutes max
            },
            AgentType.TECHNICAL: {
                "max_age_minutes": 15,       # Technical every 15 min is plenty
                "min_interval_seconds": 300,  # Once per 5 min
                "threshold_change": 20,      # Only re-run on big score swings
            },
            AgentType.CONSENSUS: {
                "max_age_minutes": 15,       # Final decision cache 15 min
                "min_interval_seconds": 300,  # Once per 5 min
            },
            # New specialized agents
            AgentType.MACRO: {
                "max_age_minutes": 30,       # Macro changes slowly
                "min_interval_seconds": 900,  # Every 15 minutes max
            },
            AgentType.CONTRARIAN: {
                "max_age_minutes": 15,       # Check every 15 min
                "min_interval_seconds": 300,  # Once per 5 min
            },
            AgentType.RISK: {
                "max_age_minutes": 10,       # Risk every 10 min
                "min_interval_seconds": 300,  # Once per 5 min
            },
            AgentType.EXIT: {
                "max_age_minutes": 10,       # Exit strategy every 10 min
                "min_interval_seconds": 300,  # Once per 5 min
            },
            AgentType.TIMING: {
                "max_age_minutes": 10,       # Timing every 10 min
                "min_interval_seconds": 300,  # Once per 5 min
            },
            AgentType.DEBATE: {
                "max_age_minutes": 15,       # Full debate outcome
                "min_interval_seconds": 300,  # Once per 5 min
            },
        }

        # Stats for monitoring
        self.stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "llm_calls_saved": 0,
        }

    def _get_ticker_cache(self, ticker: str) -> Dict[AgentType, CachedSignal]:
        """Get or create cache dict for a ticker."""
        ticker = ticker.upper()
        if ticker not in self._cache:
            self._cache[ticker] = {}
        return self._cache[ticker]

    def _get_upstream(self, ticker: str) -> UpstreamData:
        """Get or create upstream data tracker for a ticker."""
        ticker = ticker.upper()
        if ticker not in self._upstream:
            self._upstream[ticker] = UpstreamData()
        return self._upstream[ticker]

    @staticmethod
    def _hash_data(data: Any) -> str:
        """Create a hash of data for change detection."""
        if data is None:
            return "none"
        if isinstance(data, dict):
            # Sort keys for consistent hashing
            content = str(sorted(data.items()))
        elif isinstance(data, list):
            content = str(data)
        else:
            content = str(data)
        return hashlib.md5(content.encode()).hexdigest()[:12]

    def get_cached_signal(
        self,
        ticker: str,
        agent_type: AgentType
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached signal if valid, None otherwise.

        Args:
            ticker: Stock ticker
            agent_type: Type of agent

        Returns:
            Cached signal dict or None if cache miss/expired
        """
        ticker = ticker.upper()
        cache = self._get_ticker_cache(ticker)

        if agent_type not in cache:
            self.stats["cache_misses"] += 1
            return None

        cached = cache[agent_type]
        config = self.config.get(agent_type, {})
        max_age = config.get("max_age_minutes", 10)

        if cached.is_expired(max_age):
            self.stats["cache_misses"] += 1
            logger.debug(f"Cache expired for {ticker}/{agent_type.value}")
            return None

        self.stats["cache_hits"] += 1
        self.stats["llm_calls_saved"] += 1
        logger.info(
            f"Cache HIT for {ticker}/{agent_type.value} "
            f"(age: {cached.age_seconds():.0f}s)"
        )

        # Add cache metadata to response
        signal = cached.signal.copy()
        signal["_cached"] = True
        signal["_cache_age_seconds"] = cached.age_seconds()

        return signal

    def set_cached_signal(
        self,
        ticker: str,
        agent_type: AgentType,
        signal: Dict[str, Any],
        input_hash: str = "",
        upstream_timestamps: Optional[Dict[str, datetime]] = None
    ) -> None:
        """
        Store agent output in cache.

        Args:
            ticker: Stock ticker
            agent_type: Type of agent
            signal: Agent output to cache
            input_hash: Hash of inputs used
            upstream_timestamps: Timestamps of upstream data used
        """
        ticker = ticker.upper()
        cache = self._get_ticker_cache(ticker)

        cache[agent_type] = CachedSignal(
            ticker=ticker,
            agent_type=agent_type,
            signal=signal,
            timestamp=datetime.utcnow(),
            input_hash=input_hash,
            upstream_timestamps=upstream_timestamps or {}
        )

        logger.debug(f"Cached signal for {ticker}/{agent_type.value}")

    def should_run_news_agent(
        self,
        ticker: str,
        latest_news_ts: Optional[datetime],
    ) -> bool:
        """
        Check if news agent should run for this ticker.

        Run if:
        - No cached signal exists
        - New news arrived since last agent run
        - Cache is expired

        Args:
            ticker: Stock ticker
            latest_news_ts: Timestamp of most recent news article

        Returns:
            True if agent should run, False to use cache
        """
        ticker = ticker.upper()
        cache = self._get_ticker_cache(ticker)
        upstream = self._get_upstream(ticker)
        config = self.config[AgentType.NEWS]

        # No cache - must run
        if AgentType.NEWS not in cache:
            logger.info(f"News agent for {ticker}: No cache, will run")
            return True

        cached = cache[AgentType.NEWS]
        age_seconds = cached.age_seconds()

        # NEW NEWS BEATS MIN INTERVAL — this is critical for early entry.
        # If breaking news arrived since the last LLM run, re-score immediately
        # (only enforce a short floor of 30s to avoid hammering the API).
        if latest_news_ts:
            last_run_news_ts = upstream.news_timestamp
            if last_run_news_ts is None or latest_news_ts > last_run_news_ts:
                if age_seconds >= 30:
                    logger.info(
                        f"News agent for {ticker}: New news detected, re-scoring now"
                    )
                    upstream.news_timestamp = latest_news_ts
                    return True
                else:
                    logger.debug(
                        f"News agent for {ticker}: New news but too soon ({age_seconds:.0f}s < 30s)"
                    )
                    return False

        # Check minimum interval (only applies when no new news)
        if age_seconds < config["min_interval_seconds"]:
            logger.debug(
                f"News agent for {ticker}: Too soon "
                f"({age_seconds:.0f}s < {config['min_interval_seconds']}s)"
            )
            return False

        # Check if cache expired
        if cached.is_expired(config["max_age_minutes"]):
            logger.info(f"News agent for {ticker}: Cache expired, will run")
            return True

        logger.debug(f"News agent for {ticker}: No change, using cache")
        return False

    def should_run_earnings_agent(
        self,
        ticker: str,
        latest_earnings_ts: Optional[datetime],
        next_earnings_date: Optional[datetime] = None,
    ) -> bool:
        """
        Check if earnings agent should run for this ticker.

        Run if:
        - No cached signal exists
        - New earnings data arrived
        - Within earnings window (day before/after earnings)
        - Cache is expired

        Args:
            ticker: Stock ticker
            latest_earnings_ts: Timestamp of most recent earnings data
            next_earnings_date: Date of next earnings report

        Returns:
            True if agent should run, False to use cache
        """
        ticker = ticker.upper()
        cache = self._get_ticker_cache(ticker)
        upstream = self._get_upstream(ticker)
        config = self.config[AgentType.EARNINGS]

        # No cache - must run
        if AgentType.EARNINGS not in cache:
            logger.info(f"Earnings agent for {ticker}: No cache, will run")
            return True

        cached = cache[AgentType.EARNINGS]

        # Check minimum interval
        age_seconds = cached.age_seconds()
        if age_seconds < config["min_interval_seconds"]:
            logger.debug(
                f"Earnings agent for {ticker}: Too soon "
                f"({age_seconds:.0f}s < {config['min_interval_seconds']}s)"
            )
            return False

        # Check if cache expired
        if cached.is_expired(config["max_age_minutes"]):
            logger.info(f"Earnings agent for {ticker}: Cache expired, will run")
            return True

        # Check if within earnings window
        if next_earnings_date:
            now = datetime.utcnow()
            window_days = config.get("earnings_window_days", 1)
            days_until = (next_earnings_date - now).days
            if abs(days_until) <= window_days:
                logger.info(
                    f"Earnings agent for {ticker}: Within earnings window "
                    f"({days_until} days), will run"
                )
                return True

        # Check if new earnings data
        if latest_earnings_ts:
            last_run_ts = upstream.earnings_timestamp
            if last_run_ts is None or latest_earnings_ts > last_run_ts:
                logger.info(
                    f"Earnings agent for {ticker}: New earnings data, will run"
                )
                upstream.earnings_timestamp = latest_earnings_ts
                return True

        logger.debug(f"Earnings agent for {ticker}: No change, using cache")
        return False

    def should_run_analyst_agent(
        self,
        ticker: str,
        latest_rating_ts: Optional[datetime],
    ) -> bool:
        """
        Check if analyst/ratings agent should run for this ticker.

        Run if:
        - No cached signal exists
        - New analyst rating or price target arrived
        - Cache is expired (15 minutes)

        Args:
            ticker: Stock ticker
            latest_rating_ts: Timestamp of most recent rating

        Returns:
            True if agent should run, False to use cache
        """
        ticker = ticker.upper()
        cache = self._get_ticker_cache(ticker)
        upstream = self._get_upstream(ticker)
        config = self.config[AgentType.ANALYST]

        # No cache - must run
        if AgentType.ANALYST not in cache:
            logger.info(f"Analyst agent for {ticker}: No cache, will run")
            return True

        cached = cache[AgentType.ANALYST]

        # Check minimum interval (10 minutes for ratings)
        age_seconds = cached.age_seconds()
        if age_seconds < config["min_interval_seconds"]:
            logger.debug(
                f"Analyst agent for {ticker}: Too soon "
                f"({age_seconds:.0f}s < {config['min_interval_seconds']}s)"
            )
            return False

        # Check if cache expired
        if cached.is_expired(config["max_age_minutes"]):
            logger.info(f"Analyst agent for {ticker}: Cache expired, will run")
            return True

        # Check if new rating arrived
        if latest_rating_ts:
            last_run_ts = upstream.analyst_timestamp
            if last_run_ts is None or latest_rating_ts > last_run_ts:
                logger.info(
                    f"Analyst agent for {ticker}: New rating, will run"
                )
                upstream.analyst_timestamp = latest_rating_ts
                return True

        logger.debug(f"Analyst agent for {ticker}: No change, using cache")
        return False

    def should_run_technical_agent(
        self,
        ticker: str,
        current_regime: str,
        technical_score: float,
        score_threshold: float = 10.0,
    ) -> bool:
        """
        Check if technical agent should run.

        Prefer pure Python logic without LLMs using local indicators.
        Only run LLM when regime changes or score crosses threshold.

        Args:
            ticker: Stock ticker
            current_regime: Current technical regime (bullish/bearish/neutral)
            technical_score: Current technical score (0-100)
            score_threshold: Score change threshold to trigger re-run

        Returns:
            True if agent should run, False to use cache
        """
        ticker = ticker.upper()
        cache = self._get_ticker_cache(ticker)
        upstream = self._get_upstream(ticker)
        config = self.config[AgentType.TECHNICAL]

        # No cache - must run
        if AgentType.TECHNICAL not in cache:
            logger.info(f"Technical agent for {ticker}: No cache, will run")
            upstream.technical_regime = current_regime
            return True

        cached = cache[AgentType.TECHNICAL]

        # Check minimum interval
        age_seconds = cached.age_seconds()
        if age_seconds < config["min_interval_seconds"]:
            logger.debug(
                f"Technical agent for {ticker}: Too soon "
                f"({age_seconds:.0f}s < {config['min_interval_seconds']}s)"
            )
            return False

        # Check if cache expired
        if cached.is_expired(config["max_age_minutes"]):
            logger.info(f"Technical agent for {ticker}: Cache expired, will run")
            return True

        # Check if regime changed
        last_regime = upstream.technical_regime
        if last_regime and last_regime != current_regime:
            logger.info(
                f"Technical agent for {ticker}: Regime changed "
                f"({last_regime} -> {current_regime}), will run"
            )
            upstream.technical_regime = current_regime
            return True

        # Check if score changed significantly
        cached_score = cached.signal.get("score", 50)
        score_change = abs(technical_score - cached_score)
        threshold = config.get("threshold_change", score_threshold)

        if score_change >= threshold:
            logger.info(
                f"Technical agent for {ticker}: Score changed significantly "
                f"({cached_score:.0f} -> {technical_score:.0f}), will run"
            )
            return True

        logger.debug(f"Technical agent for {ticker}: No significant change, using cache")
        return False

    def should_run_consensus_agent(
        self,
        ticker: str,
        news_signal_hash: str,
        earnings_signal_hash: str,
        analyst_signal_hash: str,
        technical_signal_hash: str,
        risk_state_hash: str,
    ) -> bool:
        """
        Check if consensus/synthesis agent should run.

        Only run when at least one underlying signal changed:
        - News signal changed
        - Earnings signal changed
        - Analyst signal changed
        - Technical regime changed
        - Risk state changed significantly

        Args:
            ticker: Stock ticker
            *_signal_hash: Hashes of upstream agent outputs
            risk_state_hash: Hash of current risk state

        Returns:
            True if agent should run, False to use cache
        """
        ticker = ticker.upper()
        cache = self._get_ticker_cache(ticker)
        config = self.config[AgentType.CONSENSUS]

        # No cache - must run
        if AgentType.CONSENSUS not in cache:
            logger.info(f"Consensus agent for {ticker}: No cache, will run")
            return True

        cached = cache[AgentType.CONSENSUS]

        # Check minimum interval
        age_seconds = cached.age_seconds()
        if age_seconds < config["min_interval_seconds"]:
            logger.debug(
                f"Consensus agent for {ticker}: Too soon "
                f"({age_seconds:.0f}s < {config['min_interval_seconds']}s)"
            )
            return False

        # Check if cache expired
        if cached.is_expired(config["max_age_minutes"]):
            logger.info(f"Consensus agent for {ticker}: Cache expired, will run")
            return True

        # Check if any upstream signals changed
        old_hashes = cached.upstream_timestamps

        changes = []
        if old_hashes.get("news") != news_signal_hash:
            changes.append("news")
        if old_hashes.get("earnings") != earnings_signal_hash:
            changes.append("earnings")
        if old_hashes.get("analyst") != analyst_signal_hash:
            changes.append("analyst")
        if old_hashes.get("technical") != technical_signal_hash:
            changes.append("technical")
        if old_hashes.get("risk") != risk_state_hash:
            changes.append("risk")

        if changes:
            logger.info(
                f"Consensus agent for {ticker}: Upstream changed "
                f"({', '.join(changes)}), will run"
            )
            return True

        logger.debug(f"Consensus agent for {ticker}: No upstream changes, using cache")
        return False

    def update_upstream_hashes(
        self,
        ticker: str,
        news_hash: Optional[str] = None,
        earnings_hash: Optional[str] = None,
        analyst_hash: Optional[str] = None,
        technical_hash: Optional[str] = None,
        risk_hash: Optional[str] = None,
    ) -> None:
        """Update stored hashes for consensus change detection."""
        ticker = ticker.upper()
        cache = self._get_ticker_cache(ticker)

        if AgentType.CONSENSUS in cache:
            cached = cache[AgentType.CONSENSUS]
            if news_hash:
                cached.upstream_timestamps["news"] = news_hash
            if earnings_hash:
                cached.upstream_timestamps["earnings"] = earnings_hash
            if analyst_hash:
                cached.upstream_timestamps["analyst"] = analyst_hash
            if technical_hash:
                cached.upstream_timestamps["technical"] = technical_hash
            if risk_hash:
                cached.upstream_timestamps["risk"] = risk_hash

    def invalidate(self, ticker: str, agent_type: Optional[AgentType] = None) -> None:
        """
        Invalidate cache for a ticker.

        Args:
            ticker: Stock ticker
            agent_type: Specific agent to invalidate, or None for all
        """
        ticker = ticker.upper()
        cache = self._get_ticker_cache(ticker)

        if agent_type:
            if agent_type in cache:
                del cache[agent_type]
                logger.info(f"Invalidated cache for {ticker}/{agent_type.value}")
        else:
            cache.clear()
            logger.info(f"Invalidated all caches for {ticker}")

    def invalidate_all(self) -> None:
        """Clear all caches."""
        self._cache.clear()
        self._upstream.clear()
        logger.info("Invalidated all agent caches")

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_requests = self.stats["cache_hits"] + self.stats["cache_misses"]
        hit_rate = (
            self.stats["cache_hits"] / total_requests * 100
            if total_requests > 0 else 0
        )

        return {
            **self.stats,
            "total_requests": total_requests,
            "hit_rate_percent": round(hit_rate, 1),
            "cached_tickers": len(self._cache),
            "cached_signals": sum(len(c) for c in self._cache.values()),
        }

    def get_cache_status(self, ticker: str) -> Dict[str, Any]:
        """Get cache status for a specific ticker."""
        ticker = ticker.upper()
        cache = self._get_ticker_cache(ticker)

        status = {}
        for agent_type in AgentType:
            if agent_type in cache:
                cached = cache[agent_type]
                config = self.config.get(agent_type, {})
                status[agent_type.value] = {
                    "cached": True,
                    "age_seconds": cached.age_seconds(),
                    "max_age_minutes": config.get("max_age_minutes", 10),
                    "expired": cached.is_expired(config.get("max_age_minutes", 10)),
                    "timestamp": cached.timestamp.isoformat(),
                }
            else:
                status[agent_type.value] = {"cached": False}

        return {
            "ticker": ticker,
            "agents": status,
            "upstream": {
                "news_ts": self._upstream.get(ticker, UpstreamData()).news_timestamp,
                "earnings_ts": self._upstream.get(ticker, UpstreamData()).earnings_timestamp,
                "analyst_ts": self._upstream.get(ticker, UpstreamData()).analyst_timestamp,
                "technical_regime": self._upstream.get(ticker, UpstreamData()).technical_regime,
            }
        }


# Global singleton instance
agent_cache = AgentCache()
