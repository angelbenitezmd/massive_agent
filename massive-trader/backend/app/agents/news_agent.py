"""News analysis agent for processing Benzinga news data."""
import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta

from app.agents.base_agent import BaseAgent
from app.models.news import NewsItem
from app.models.signals import AgentScore

logger = logging.getLogger(__name__)


class NewsAgent(BaseAgent):
    """Agent specialized in analyzing news sentiment and urgency."""

    def __init__(self):
        super().__init__(name="NewsAgent")

        # Define important channels and tags
        self.high_impact_channels = {
            "earnings", "movers", "price target", "guidance",
            "merger", "acquisition", "fda", "sec"
        }

        self.urgent_tags = {
            "breaking", "alert", "urgent", "halt", "investigation",
            "bankruptcy", "delisting", "scandal"
        }

    def get_system_prompt(self) -> str:
        """Get the system prompt for news analysis."""
        return """You are an expert financial news analyst specializing in real-time market intelligence.
Your role is to analyze news articles and determine their potential market impact.

Key responsibilities:
1. Assess sentiment (positive, negative, neutral)
2. Determine urgency (breaking news vs old news)
3. Evaluate importance based on channels and tags
4. Identify potential price catalysts
5. Consider market context and timing

Focus on:
- Earnings surprises and guidance changes
- Analyst rating changes
- M&A activity
- Regulatory decisions
- Major product launches or failures
- Executive changes
- Legal issues

Provide scores that reflect immediate tradable opportunities."""

    def prepare_data(self, data: Dict[str, Any]) -> str:
        """
        Prepare news data for analysis.

        Args:
            data: Dict containing 'news_items' list

        Returns:
            Formatted string for LLM analysis
        """
        news_items: List[NewsItem] = data.get("news_items", [])

        if not news_items:
            return "No news items available for analysis."

        # Sort by publication date (most recent first)
        news_items.sort(key=lambda x: x.published, reverse=True)

        # Prepare summary
        summary_parts = [f"Analyzing {len(news_items)} news items:\n"]

        for i, item in enumerate(news_items[:5], 1):  # Analyze top 5 most recent
            # Calculate age
            age = datetime.utcnow() - item.published
            age_str = self._format_age(age)

            # Determine importance
            importance = self._assess_importance(item)

            summary_parts.append(f"""
Article {i}:
- Title: {item.title}
- Published: {age_str} ago
- Author: {item.author or 'Unknown'}
- Channels: {', '.join(item.channels[:3]) if item.channels else 'None'}
- Tags: {', '.join(item.tags[:5]) if item.tags else 'None'}
- Importance: {importance}
- Teaser: {item.teaser[:200] if item.teaser else 'No summary available'}
""")

        return "\n".join(summary_parts)

    def _format_age(self, age: timedelta) -> str:
        """Format age of news for display."""
        if age.days > 0:
            return f"{age.days} days"
        elif age.seconds > 3600:
            return f"{age.seconds // 3600} hours"
        else:
            return f"{age.seconds // 60} minutes"

    def _assess_importance(self, item: NewsItem) -> str:
        """Assess the importance of a news item."""
        score = 0

        # Check channels
        for channel in item.channels:
            if channel.lower() in self.high_impact_channels:
                score += 2

        # Check tags
        for tag in item.tags:
            if tag.lower() in self.urgent_tags:
                score += 3

        # Check ticker mentions
        if len(item.tickers) > 0:
            score += 1

        if score >= 5:
            return "HIGH"
        elif score >= 2:
            return "MEDIUM"
        else:
            return "LOW"

    async def analyze(self, data: Dict[str, Any]) -> AgentScore:
        """
        Analyze news data and return score.

        Override to add custom logic before calling parent.
        """
        news_items = data.get("news_items", [])

        # Quick scoring for empty or old news
        if not news_items:
            return AgentScore(
                score=50.0,
                sentiment=0.0,
                confidence=0.0,
                urgency=0.0,
                notes="No news available"
            )

        # Check if news is fresh
        latest_news = news_items[0]
        age = datetime.utcnow() - latest_news.published

        # Adjust urgency based on age
        if age.total_seconds() < 300:  # Less than 5 minutes
            data["urgency_boost"] = 0.9
        elif age.total_seconds() < 3600:  # Less than 1 hour
            data["urgency_boost"] = 0.5
        else:
            data["urgency_boost"] = 0.1

        # Call parent analyze method
        return await super().analyze(data)


class NewsAnalyzer:
    """Helper class for quick news analysis without LLM."""

    @staticmethod
    def quick_sentiment(news_items: List[NewsItem]) -> Dict[str, float]:
        """
        Quick sentiment analysis based on keywords.

        Args:
            news_items: List of news items

        Returns:
            Dict with sentiment metrics
        """
        positive_keywords = {
            "upgrade", "beat", "surpass", "exceed", "positive", "growth",
            "profit", "revenue", "bullish", "buy", "outperform", "strong"
        }

        negative_keywords = {
            "downgrade", "miss", "below", "negative", "loss", "decline",
            "bearish", "sell", "underperform", "weak", "concern", "risk"
        }

        positive_count = 0
        negative_count = 0
        total_count = len(news_items)

        for item in news_items:
            text = (item.title + " " + (item.teaser or "")).lower()

            for keyword in positive_keywords:
                if keyword in text:
                    positive_count += 1
                    break

            for keyword in negative_keywords:
                if keyword in text:
                    negative_count += 1
                    break

        if total_count == 0:
            return {"sentiment": 0.0, "confidence": 0.0}

        sentiment = (positive_count - negative_count) / total_count
        confidence = (positive_count + negative_count) / total_count

        return {
            "sentiment": max(-1, min(1, sentiment)),
            "confidence": min(1, confidence),
            "positive_ratio": positive_count / total_count if total_count > 0 else 0,
            "negative_ratio": negative_count / total_count if total_count > 0 else 0
        }