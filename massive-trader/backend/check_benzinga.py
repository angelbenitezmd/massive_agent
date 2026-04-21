#!/usr/bin/env python3
"""Quick check of which Benzinga data sources return data (vs subscription errors)."""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

# Use same client as main app
from app.services.benzinga_simple import BenzingaClient
from app.core.config_simple import get_settings

async def main():
    settings = get_settings()
    if not settings.BENZINGA_API_KEY:
        print("❌ BENZINGA_API_KEY not set in .env")
        return

    client = BenzingaClient(
        base_url=settings.BENZINGA_BASE_URL,
        api_key=settings.BENZINGA_API_KEY
    )

    ticker = "AAPL"

    print("Testing Benzinga data sources (ticker=AAPL)...\n")

    # 1. News (ticker-specific)
    print("1. NEWS (ticker=AAPL)")
    news = await client.get_news(tickers=ticker, limit=5)
    if news.get("error"):
        print(f"   ❌ Error: {news.get('error')} - {news.get('message', '')}")
    else:
        items = news.get("results", [])
        print(f"   ✅ OK - {len(items)} articles")
        if items:
            print(f"      Sample: {items[0].get('title', '')[:60]}...")
    print()

    # 2. Earnings
    print("2. EARNINGS")
    earnings = await client.get_earnings(ticker=ticker, limit=3)
    if earnings.get("error"):
        print(f"   ❌ Error: {earnings.get('error')} - {earnings.get('message', '')}")
    else:
        items = earnings.get("results", [])
        print(f"   ✅ OK - {len(items)} items")
        if items:
            e = items[0]
            print(f"      Sample: EPS est {e.get('estimated_eps')} vs actual {e.get('actual_eps')}")
    print()

    # 3. Ratings
    print("3. RATINGS (analyst upgrades/downgrades)")
    ratings = await client.get_ratings(ticker=ticker, limit=5)
    if ratings.get("error"):
        print(f"   ❌ Error: {ratings.get('error')} - {ratings.get('message', '')}")
    else:
        items = ratings.get("results", [])
        if not items:
            print("   ⚠️  Empty (no subscription or no recent ratings)")
        else:
            print(f"   ✅ OK - {len(items)} ratings")
            r = items[0]
            print(f"      Sample: {r.get('rating_action')} - {r.get('analyst_firm', r.get('firm', 'N/A'))}")
    print()

    # 4. Consensus
    print("4. CONSENSUS (analyst consensus rating)")
    consensus = await client.get_consensus(ticker)
    if consensus.get("error"):
        print(f"   ❌ Error: {consensus.get('error')} - {consensus.get('message', '')}")
    else:
        results = consensus.get("results", [])
        if not results:
            print("   ⚠️  Empty (no subscription or no consensus)")
        else:
            c = results[0] if isinstance(results, list) else results
            print(f"   ✅ OK")
            print(f"      Sample: {c.get('consensus_rating')} | Target: ${c.get('target_price', c.get('consensus_price_target', 'N/A'))}")
    print()

    print("--- Summary ---")
    news_ok = not news.get("error") and len(news.get("results", [])) > 0
    earn_ok = not earnings.get("error") and len(earnings.get("results", [])) > 0
    rat_ok = not ratings.get("error") and len(ratings.get("results", [])) > 0
    con_ok = not consensus.get("error") and (consensus.get("results") or [])
    if isinstance(con_ok, list):
        con_ok = len(con_ok) > 0

    print(f"News:      {'✅ In use' if news_ok else '❌ Not working'}")
    print(f"Earnings:  {'✅ In use' if earn_ok else '❌ Not working'}")
    print(f"Ratings:  {'✅ In use' if rat_ok else '❌ Empty or blocked'}")
    print(f"Consensus:{'✅ In use' if con_ok else '❌ Empty or blocked'}")

if __name__ == "__main__":
    asyncio.run(main())
