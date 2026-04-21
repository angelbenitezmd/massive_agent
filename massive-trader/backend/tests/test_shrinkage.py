"""Tests for the nuanced sparse-data shrinkage system in keyword scoring."""
import sys
import os
from datetime import datetime, timedelta

import pytest

# Add backend root to path so we can import from app.main
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import (
    _newest_article_age_hours,
    _compute_category_quality,
    SHRINKAGE_CONFIG,
    MULTI_SOURCE_SHRINKAGE,
)


# ---- _newest_article_age_hours tests ----

class TestNewestArticleAgeHours:
    def test_single_article(self):
        now = datetime(2026, 3, 26, 14, 0, 0)
        articles = [{"published": "2026-03-26T12:00:00"}]
        age = _newest_article_age_hours(articles, now)
        assert age is not None
        assert abs(age - 2.0) < 0.1

    def test_multiple_picks_newest(self):
        now = datetime(2026, 3, 26, 14, 0, 0)
        articles = [
            {"published": "2026-03-26T10:00:00"},  # 4h old
            {"published": "2026-03-26T13:00:00"},  # 1h old (newest)
            {"published": "2026-03-25T14:00:00"},  # 24h old
        ]
        age = _newest_article_age_hours(articles, now)
        assert age is not None
        assert abs(age - 1.0) < 0.1

    def test_no_dates_returns_none(self):
        articles = [{"title": "No date here"}, {"title": "Also none"}]
        age = _newest_article_age_hours(articles, datetime.utcnow())
        assert age is None

    def test_created_fallback(self):
        now = datetime(2026, 3, 26, 14, 0, 0)
        articles = [{"created": "2026-03-26T11:00:00"}]
        age = _newest_article_age_hours(articles, now)
        assert age is not None
        assert abs(age - 3.0) < 0.1

    def test_empty_list(self):
        assert _newest_article_age_hours([], datetime.utcnow()) is None


# ---- _compute_category_quality tests ----

class TestComputeCategoryQuality:
    def test_news_fresh_and_strong(self):
        now = datetime(2026, 3, 26, 14, 0, 0)
        articles = [
            {"published": "2026-03-26T13:00:00", "title": "Stock surges"},
            {"published": "2026-03-26T12:30:00", "title": "Upgrade announced"},
            {"published": "2026-03-26T12:00:00", "title": "Earnings beat"},
        ]
        q = _compute_category_quality("news", news_items=articles, net_signals=3, now=now)
        assert q > 0.7  # Fresh, multiple articles, strong signals

    def test_news_stale_and_weak(self):
        now = datetime(2026, 3, 26, 14, 0, 0)
        articles = [{"published": "2026-03-23T14:00:00", "title": "Old news"}]
        q = _compute_category_quality("news", news_items=articles, net_signals=0, now=now)
        assert q < 0.4  # Stale, single article, no signals

    def test_earnings_recent_big_surprise(self):
        now = datetime(2026, 3, 26, 14, 0, 0)
        earnings = [{
            "date": "2026-03-20",
            "estimated_eps": "1.00",
            "actual_eps": "1.20",  # 20% surprise
        }]
        q = _compute_category_quality("earnings", earnings_items=earnings, now=now)
        assert q > 0.7

    def test_earnings_old_small_surprise(self):
        now = datetime(2026, 3, 26, 14, 0, 0)
        earnings = [{
            "date": "2025-11-01",
            "estimated_eps": "1.00",
            "actual_eps": "1.02",  # 2% surprise
        }]
        q = _compute_category_quality("earnings", earnings_items=earnings, now=now)
        assert q < 0.5

    def test_ratings_many_recent(self):
        now = datetime(2026, 3, 26, 14, 0, 0)
        ratings = [
            {"date": "2026-03-24", "rating_action": "upgrade"},
            {"date": "2026-03-23", "rating_action": "upgrade"},
            {"date": "2026-03-22", "rating_action": "upgrade"},
            {"date": "2026-03-21", "rating_action": "upgrade"},
            {"date": "2026-03-20", "rating_action": "upgrade"},
        ]
        q = _compute_category_quality("ratings", ratings_items=ratings, now=now)
        assert q > 0.8

    def test_ratings_single_old(self):
        now = datetime(2026, 3, 26, 14, 0, 0)
        ratings = [{"date": "2025-12-01", "rating_action": "upgrade"}]
        q = _compute_category_quality("ratings", ratings_items=ratings, now=now)
        assert q < 0.5

    def test_consensus_always_half(self):
        q = _compute_category_quality("consensus")
        assert q == 0.5


# ---- Full shrinkage formula tests ----

def _apply_shrinkage(raw_score: float, components: list[tuple[str, float]]) -> float:
    """Apply the shrinkage formula given (category, quality) pairs. Returns shrunk score."""
    n = min(len(components), 4)
    if n == 0:
        return 50.0
    multi_factor = MULTI_SOURCE_SHRINKAGE.get(n, 0.0)

    total_w = 0
    blended = 0
    for cat, q in components:
        cfg = SHRINKAGE_CONFIG[cat]
        cat_shrinkage = cfg["max_shrinkage"] - q * (cfg["max_shrinkage"] - cfg["min_shrinkage"])
        # Use equal weights for simplicity in tests
        w = 1.0
        blended += cat_shrinkage * w
        total_w += w
    blended /= total_w
    final_shrinkage = blended * multi_factor
    return 50 + (raw_score - 50) * (1 - final_shrinkage)


class TestFullShrinkageFormula:
    def test_single_high_quality_news_less_shrunk_than_low_quality_consensus(self):
        raw = 72.0
        news_score = _apply_shrinkage(raw, [("news", 0.9)])
        consensus_score = _apply_shrinkage(raw, [("consensus", 0.3)])
        # High-quality news should retain more of its signal
        assert news_score > consensus_score

    def test_two_sources_less_shrunk_than_one(self):
        raw = 72.0
        one_source = _apply_shrinkage(raw, [("news", 0.7)])
        two_sources = _apply_shrinkage(raw, [("news", 0.7), ("earnings", 0.5)])
        assert two_sources > one_source  # Less shrinkage with more sources

    def test_four_sources_no_shrinkage(self):
        raw = 72.0
        result = _apply_shrinkage(raw, [
            ("news", 0.5), ("earnings", 0.5),
            ("ratings", 0.5), ("consensus", 0.5)
        ])
        assert result == raw  # multi_source_factor = 0.0 for 4 sources

    def test_pulls_toward_50_bullish(self):
        raw = 75.0
        result = _apply_shrinkage(raw, [("consensus", 0.5)])
        assert 50 < result < raw

    def test_pulls_toward_50_bearish(self):
        raw = 30.0
        result = _apply_shrinkage(raw, [("consensus", 0.5)])
        assert raw < result < 50

    def test_monotonicity_ordering(self):
        """Same raw score: (a) consensus low quality < (b) consensus high quality < (c) news+consensus."""
        raw = 68.0
        a = _apply_shrinkage(raw, [("consensus", 0.2)])   # Low quality single source
        b = _apply_shrinkage(raw, [("consensus", 0.8)])   # High quality single source
        c = _apply_shrinkage(raw, [("news", 0.7), ("consensus", 0.5)])  # Two sources

        # (a) most shrunk (closest to 50), then (b), then (c) least shrunk (closest to raw)
        assert a < b < c
        # All should be between 50 and raw
        assert 50 < a < raw
        assert 50 < b < raw
        assert 50 < c < raw
