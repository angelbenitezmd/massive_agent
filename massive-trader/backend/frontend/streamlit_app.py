import streamlit as st
import httpx
import asyncio
import json
import pandas as pd
from datetime import datetime, timedelta
import websocket
from typing import Dict, List, Optional, Any
import time

# Page config
st.set_page_config(
    page_title="AI Trading Intelligence System",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if 'ws_messages' not in st.session_state:
    st.session_state.ws_messages = []
if 'ws_connected' not in st.session_state:
    st.session_state.ws_connected = False
if 'ws_connection' not in st.session_state:
    st.session_state.ws_connection = None
if 'backend_url' not in st.session_state:
    st.session_state.backend_url = "http://localhost:8000"

# Helper functions
@st.cache_data(ttl=30)
def fetch_data(endpoint: str, params: Optional[Dict] = None) -> Dict:
    """Fetch data from backend with caching."""
    try:
        url = f"{st.session_state.backend_url}{endpoint}"
        # Use longer timeout for scan endpoints
        timeout = 60.0 if "/scan/" in endpoint else 10.0
        response = httpx.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        st.error(f"HTTP {e.response.status_code}: {e.response.text}")
        return {}
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return {}

def get_sentiment_color(score: float) -> str:
    """Return color based on sentiment score."""
    if score >= 70:
        return "green"
    elif score >= 60:
        return "lightgreen"
    elif score <= 30:
        return "red"
    elif score <= 40:
        return "orange"
    return "gray"

def format_datetime(dt_str: str) -> str:
    """Format datetime string for display."""
    try:
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        return dt.strftime("%Y-%m-%d %H:%M")
    except:
        return dt_str

# WebSocket handler - Simplified for better Streamlit compatibility
def create_websocket_connection(ws_url):
    """Create a simple WebSocket connection"""
    try:
        ws = websocket.create_connection(ws_url, timeout=5)
        return ws
    except Exception as e:
        return None

def receive_websocket_message(ws):
    """Receive a message from WebSocket (non-blocking)"""
    try:
        ws.settimeout(0.1)  # Short timeout for non-blocking
        message = ws.recv()
        return json.loads(message)
    except websocket.WebSocketTimeoutException:
        return None  # No message available
    except Exception as e:
        return None

# Sidebar configuration
with st.sidebar:
    st.title("⚙️ Configuration")

    # Backend URL
    backend_url = st.text_input(
        "Backend URL",
        value=st.session_state.backend_url,
        help="FastAPI backend URL"
    )
    if backend_url != st.session_state.backend_url:
        st.session_state.backend_url = backend_url

    # System status
    st.divider()
    health = fetch_data("/health")
    if health:
        if health.get("status") == "healthy":
            st.success(f"✅ System: {health.get('status', 'unknown')}")
            env = health.get("environment", "unknown")
            if env == "live":
                st.error("⚠️ LIVE TRADING MODE")
            else:
                st.info(f"📝 Paper Trading: {health.get('paper_trading', True)}")
        else:
            st.warning("⚠️ System unavailable")

    # Default parameters
    st.divider()
    st.subheader("Default Parameters")

    default_ticker = st.text_input("Default Ticker", value="AAPL")
    default_days_back = st.slider("Days Back (News/Ratings)", 1, 30, 7)
    default_days_ahead = st.slider("Days Ahead (Earnings)", 1, 30, 7)
    default_limit = st.slider("Default Result Limit", 5, 50, 10)

    # Risk settings from status
    status = fetch_data("/status")
    if status and "risk_settings" in status:
        st.divider()
        st.subheader("Risk Settings")
        risk = status["risk_settings"]
        st.metric("Max Position Risk", f"{risk.get('max_position_risk', 0)*100:.1f}%")
        st.metric("Daily Max Drawdown", f"{risk.get('daily_max_drawdown', 0)*100:.1f}%")
        st.metric("Min Signal Score", risk.get('min_signal_score', 50))

# Main content area
st.title("🚀 AI Trading Intelligence System")

# Create tabs
tab_overview, tab_momentum, tab_ai_insights, tab_news, tab_earnings, tab_ratings, tab_consensus, tab_sentiment, tab_scans, tab_streams = st.tabs([
    "📊 Overview", "⚡ Momentum", "🤖 AI Insights", "📰 News", "📅 Earnings", "⭐ Ratings",
    "🎯 Consensus", "💹 Sentiment", "🔍 Scans", "📡 Streams"
])

# Overview Tab
with tab_overview:
    st.header("System Overview")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("Health Status")
        health_data = fetch_data("/health")
        if health_data:
            for key, value in health_data.items():
                if key == "benzinga_connected":
                    st.metric("Benzinga", "✅ Connected" if value else "❌ Disconnected")
                elif key == "paper_trading":
                    st.metric("Trading Mode", "Paper" if value else "Live")

    with col2:
        st.subheader("API Status")
        status_data = fetch_data("/status")
        if status_data and "api_keys_configured" in status_data:
            apis = status_data["api_keys_configured"]
            for api, configured in apis.items():
                st.metric(api.title(), "✅" if configured else "❌")

    with col3:
        st.subheader("Watchlist")
        if status_data and "watchlist" in status_data:
            watchlist = status_data["watchlist"]
            st.write(f"📌 {len(watchlist)} tickers monitored")
            st.write(", ".join(watchlist[:5]) + ("..." if len(watchlist) > 5 else ""))

# Momentum Trading Tab
with tab_momentum:
    st.header("⚡ High-Speed Momentum Trading")
    st.caption("React to news in seconds • Trade momentum • Exit on weakness")

    # Quick action buttons
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("🔥 SCAN NOW", key="momentum_scan", type="primary"):
            with st.spinner("Scanning for momentum..."):
                scan_data = fetch_data("/api/momentum/scan")

                if scan_data and scan_data.get("hot_trades"):
                    st.subheader(f"🎯 {scan_data['market_status']} - {scan_data['alerts_count']} Alerts")

                    for alert in scan_data["hot_trades"]:
                        alert_col1, alert_col2, alert_col3 = st.columns([2, 2, 3])

                        with alert_col1:
                            st.metric(alert["ticker"], f"Score: {alert['score']}")

                        with alert_col2:
                            if "BUY" in alert["action"]:
                                st.success(alert["action"])
                            elif "SELL" in alert["action"]:
                                st.error(alert["action"])
                            else:
                                st.warning(alert["action"])

                        with alert_col3:
                            st.write(f"Entry: ${alert['entry']:.2f}")
                            st.write(f"Target: ${alert['target']:.2f} (+1%)")
                            st.write(f"Stop: ${alert['stop']:.2f} (-0.5%)")

                        # Show signals
                        for signal in alert.get("signals", []):
                            st.caption(signal)

                        st.divider()
                else:
                    st.info("😴 No momentum detected - markets quiet")

    with col2:
        momentum_ticker = st.text_input("Quick Check", placeholder="TSLA", key="momentum_ticker")

    with col3:
        if st.button("⚡ ANALYZE", key="analyze_momentum"):
            if momentum_ticker:
                with st.spinner(f"Analyzing {momentum_ticker} momentum..."):
                    momentum_data = fetch_data(f"/api/momentum/{momentum_ticker}")

                    if momentum_data:
                        # Display momentum analysis
                        st.subheader(f"{momentum_ticker} Momentum Analysis")

                        # Score and action
                        score = momentum_data.get("momentum_score", 50)
                        if score >= 75:
                            st.success(f"🚀 {momentum_data['action']} - Score: {score}/100")
                        elif score >= 65:
                            st.warning(f"🟡 {momentum_data['action']} - Score: {score}/100")
                        elif score <= 25:
                            st.error(f"🔴 {momentum_data['action']} - Score: {score}/100")
                        else:
                            st.info(f"⚪ {momentum_data['action']} - Score: {score}/100")

                        # Urgency and strategy
                        st.write(f"**Urgency:** {momentum_data.get('urgency', 'N/A')}")
                        st.write(f"**Strategy:** {momentum_data.get('strategy', 'N/A')}")

                        # Signals
                        if momentum_data.get("signals"):
                            st.write("**Momentum Signals:**")
                            for signal in momentum_data["signals"]:
                                st.write(f"• {signal}")

                        # Flash trade parameters
                        flash = momentum_data.get("flash_trade", {})
                        col1, col2, col3 = st.columns(3)

                        with col1:
                            st.metric("Entry", f"${flash.get('entry_price', 0):.2f}")
                            st.metric("Stop Loss", f"${flash.get('stop_loss', 0):.2f}")

                        with col2:
                            st.metric("Quick Target (+1%)", f"${flash.get('quick_target', 0):.2f}")
                            st.metric("Scalp Target (+2%)", f"${flash.get('scalp_target', 0):.2f}")

                        with col3:
                            st.metric("Momentum Target (+3%)", f"${flash.get('momentum_target', 0):.2f}")
                            st.write(f"**Time Limit:** {flash.get('time_limit', 'N/A')}")

                        # Exit triggers
                        st.subheader("⚠️ Exit Conditions")
                        for trigger in momentum_data.get("exit_triggers", []):
                            st.write(f"• {trigger}")

    # Live momentum connection info
    st.divider()
    st.subheader("🚀 Connect to Live Momentum Feed")

    momentum_info = st.info("""
    **⚡ High-Speed WebSocket Available**

    For real-time momentum updates every 5 seconds:
    1. Go to **📡 Streams** tab
    2. Select `/ws/momentum` endpoint
    3. Click Connect

    Features:
    • Updates every 5 seconds (not 30!)
    • Tracks top momentum movers
    • Auto-detects momentum loss
    • Exit signals when momentum fades
    • Position P&L tracking

    Send commands:
    • `track:TICKER` - Add ticker to monitoring
    • `enter:TICKER` - Mark position entry
    """)

    # Auto-refresh option
    if st.checkbox("Auto-refresh momentum scan (every 10 seconds)", key="auto_momentum"):
        st.info("Auto-refresh enabled - momentum scan will update automatically")
        time.sleep(10)
        st.rerun()

# AI Insights Tab
with tab_ai_insights:
    st.header("🤖 AI Trading Intelligence & Analysis")

    ai_ticker = st.text_input("Enter Ticker for AI Analysis", value="MSFT", key="ai_ticker")

    if st.button("🧠 Get AI Analysis", key="analyze_ai"):
        with st.spinner(f"AI analyzing {ai_ticker}..."):
            ai_data = fetch_data(f"/api/ai/analyze/{ai_ticker}")

            if ai_data:
                # Main metrics row
                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    score = ai_data.get('ai_score', 50)
                    color = "🟢" if score >= 70 else "🔴" if score <= 30 else "🟡"
                    st.metric("AI Score", f"{color} {score}/100")

                with col2:
                    st.metric("Recommendation", ai_data.get('ai_recommendation', 'N/A'))

                with col3:
                    st.metric("Confidence", ai_data.get('ai_reasoning', {}).get('confidence_level', 'N/A'))

                with col4:
                    st.metric("Current Price", f"${ai_data.get('current_price', 0):.2f}")

                # AI Decision Explanation
                st.subheader("🎯 AI Decision & Explanation")
                decision_text = ai_data.get('decision_explanation', 'No explanation available')
                st.info(decision_text)

                # Two column layout for detailed insights
                col_left, col_right = st.columns(2)

                with col_left:
                    # Signal Breakdown
                    st.subheader("📊 Signal Analysis")
                    signals = ai_data.get('signal_breakdown', {})

                    # Technical Signals
                    with st.expander("📈 Technical Signals", expanded=True):
                        tech = signals.get('technical_signals', {})
                        st.write(f"**Momentum:** {tech.get('momentum', 'N/A')}")
                        st.write(f"**Price Action:** {tech.get('price_action', 'N/A')}")
                        st.write(f"**Trend:** {tech.get('trend', 'N/A')}")

                    # Sentiment Signals
                    with st.expander("💭 Sentiment Signals", expanded=True):
                        sent = signals.get('sentiment_signals', {})
                        st.write(f"**News:** {sent.get('news_sentiment', 'N/A')}")
                        st.write(f"**Earnings:** {sent.get('earnings_outlook', 'N/A')}")
                        st.write(f"**Buzz:** {sent.get('social_buzz', 'N/A')}")

                    # Fundamental Signals
                    with st.expander("📋 Fundamental Signals", expanded=True):
                        fund = signals.get('fundamental_signals', {})
                        st.write(f"**Earnings Trend:** {fund.get('earnings_trend', 'N/A')}")
                        st.write(f"**Analyst View:** {fund.get('analyst_consensus', 'N/A')}")
                        st.write(f"**Sector:** {fund.get('sector_momentum', 'N/A')}")

                    # AI Reasoning
                    st.subheader("🧠 AI Reasoning")
                    reasoning = ai_data.get('ai_reasoning', {})

                    if reasoning.get('primary_factors'):
                        st.write("**Primary Factors:**")
                        for factor in reasoning['primary_factors']:
                            st.write(f"• {factor}")

                    if reasoning.get('opportunity_factors'):
                        st.write("**Opportunities:**")
                        for opp in reasoning['opportunity_factors']:
                            st.write(f"✅ {opp}")

                    if reasoning.get('risk_factors'):
                        st.write("**Risks:**")
                        for risk in reasoning['risk_factors']:
                            st.write(f"⚠️ {risk}")

                with col_right:
                    # Actionable Insights
                    st.subheader("💡 Actionable Insights")
                    insights = ai_data.get('actionable_insights', {})

                    # Entry Points
                    with st.expander("🎯 Entry Points", expanded=True):
                        entries = insights.get('entry_points', [])
                        if entries:
                            for entry in entries:
                                st.success(entry)
                        else:
                            st.info("No specific entry points")

                    # Exit Points
                    with st.expander("🚪 Exit Points & Targets", expanded=True):
                        exits = insights.get('exit_points', [])
                        if exits:
                            for exit_point in exits:
                                if "Target" in exit_point:
                                    st.info(exit_point)
                                elif "Stop" in exit_point:
                                    st.warning(exit_point)
                                else:
                                    st.write(exit_point)
                        else:
                            st.info("No specific exit points")

                    # Risk Management
                    with st.expander("🛡️ Risk Management", expanded=True):
                        st.write(f"**Position Size:** {insights.get('position_sizing', 'N/A')}")
                        st.write(f"**Risk Strategy:** {insights.get('risk_management', 'N/A')}")
                        st.write(f"**Time Horizon:** {insights.get('time_horizon', 'N/A')}")

                    # Real-time Updates Section
                    st.subheader("📡 Live AI Monitoring")
                    st.info("""
                    💡 **Pro Tip:** Connect to the WebSocket signals stream to receive:
                    - Real-time AI trading signals every 90 seconds
                    - Instant analysis updates
                    - Market condition changes

                    Go to the **📡 Streams** tab and connect to `/ws/signals`
                    """)

                # Bottom summary
                st.divider()
                confidence = reasoning.get('confidence_level', 'UNKNOWN')
                if confidence == "HIGH":
                    st.success(f"✅ **HIGH CONFIDENCE** - AI has strong conviction in this analysis")
                elif confidence == "MEDIUM":
                    st.warning(f"⚠️ **MEDIUM CONFIDENCE** - AI suggests caution and further monitoring")
                else:
                    st.error(f"❌ **LOW CONFIDENCE** - AI recommends waiting for clearer signals")

# News Tab
with tab_news:
    st.header("📰 Market News")

    col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
    with col1:
        news_ticker = st.text_input("Ticker (comma-separated)", value=default_ticker, key="news_ticker")
    with col2:
        news_channels = st.text_input("Channels (optional)", key="news_channels")
    with col3:
        news_days = st.number_input("Days Back", 1, 30, default_days_back, key="news_days")
    with col4:
        news_limit = st.number_input("Limit", 1, 100, default_limit, key="news_limit")

    if st.button("Fetch News", key="fetch_news"):
        with st.spinner("Fetching news..."):
            news_data = fetch_data("/api/news", {
                "ticker": news_ticker,
                "channels": news_channels,
                "days_back": news_days,
                "limit": news_limit
            })

            if news_data and "results" in news_data:
                results = news_data["results"]
                if results:
                    for item in results:
                        with st.expander(f"📄 {item.get('title', 'No title')[:100]}"):
                            col1, col2 = st.columns([3, 1])
                            with col1:
                                st.write(f"**Source:** {item.get('source', 'Unknown')}")
                                st.write(f"**Published:** {format_datetime(item.get('published_at', ''))}")
                                if item.get('summary'):
                                    st.write(item['summary'][:500])
                            with col2:
                                if item.get('tickers'):
                                    st.write("**Tickers:**")
                                    for ticker in item['tickers'][:5]:
                                        st.code(ticker)
                else:
                    st.info("No news found")

# Earnings Tab
with tab_earnings:
    st.header("📅 Earnings Calendar")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        earn_ticker = st.text_input("Ticker (optional)", key="earn_ticker")
    with col2:
        earn_days = st.number_input("Days Ahead", 1, 30, default_days_ahead, key="earn_days")
    with col3:
        earn_importance = st.slider("Min Importance", 0, 5, 0, key="earn_importance")
    with col4:
        earn_limit = st.number_input("Limit", 1, 100, default_limit, key="earn_limit")

    if st.button("Fetch Earnings", key="fetch_earnings"):
        with st.spinner("Fetching earnings..."):
            params = {
                "days_ahead": earn_days,
                "importance_min": earn_importance,
                "limit": earn_limit
            }
            if earn_ticker:
                params["ticker"] = earn_ticker

            earn_data = fetch_data("/api/earnings", params)

            if earn_data and "results" in earn_data:
                results = earn_data["results"]
                if results:
                    df = pd.DataFrame(results)
                    display_cols = ['ticker', 'date', 'eps_estimate', 'eps_actual', 'revenue_estimate', 'revenue_actual']
                    available_cols = [col for col in display_cols if col in df.columns]
                    if available_cols:
                        st.dataframe(df[available_cols])
                    else:
                        st.dataframe(df)
                else:
                    st.info("No earnings found")

# Ratings Tab
with tab_ratings:
    st.header("⭐ Analyst Ratings")

    st.info("ℹ️ **Note:** Analyst ratings require a Benzinga Ratings subscription ($99/month)")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        rating_ticker = st.text_input("Ticker (optional)", key="rating_ticker")
    with col2:
        rating_days = st.number_input("Days Back", 1, 30, default_days_back, key="rating_days")
    with col3:
        rating_action = st.selectbox("Action", ["", "upgrades", "downgrades", "maintains"], key="rating_action")
    with col4:
        rating_limit = st.number_input("Limit", 1, 100, default_limit, key="rating_limit")

    if st.button("Fetch Ratings", key="fetch_ratings"):
        with st.spinner("Fetching ratings..."):
            params = {
                "days_back": rating_days,
                "limit": rating_limit
            }
            if rating_ticker:
                params["ticker"] = rating_ticker
            if rating_action:
                params["action"] = rating_action

            rating_data = fetch_data("/api/ratings", params)

            if rating_data and "results" in rating_data:
                results = rating_data["results"]
                if results:
                    for item in results:
                        col1, col2, col3 = st.columns([2, 2, 1])
                        with col1:
                            st.write(f"**{item.get('ticker', 'N/A')}** - {item.get('rating_action', 'N/A')}")
                            st.write(f"Firm: {item.get('firm', 'Unknown')}")
                        with col2:
                            st.write(f"Rating: {item.get('rating', 'N/A')}")
                            st.write(f"Target: ${item.get('price_target', 'N/A')}")
                        with col3:
                            st.write(f"Date: {format_datetime(item.get('date', ''))}")
                        st.divider()
                else:
                    st.info("No ratings found")

# Consensus Tab
with tab_consensus:
    st.header("🎯 Consensus Ratings")

    st.info("ℹ️ **Note:** Consensus ratings require a Benzinga Consensus subscription ($99/month)")

    cons_ticker = st.text_input("Enter Ticker Symbol", value=default_ticker, key="cons_ticker")

    if st.button("Get Consensus", key="fetch_consensus"):
        with st.spinner("Fetching consensus..."):
            cons_data = fetch_data(f"/api/consensus/{cons_ticker}")

            if cons_data and "results" in cons_data:
                results = cons_data["results"]
                if results and len(results) > 0:
                    result = results[0]

                    col1, col2, col3 = st.columns(3)
                    with col1:
                        consensus = result.get('consensus_rating', 'N/A')
                        if consensus == 'buy':
                            st.success(f"🟢 Consensus: {consensus.upper()}")
                        elif consensus == 'sell':
                            st.error(f"🔴 Consensus: {consensus.upper()}")
                        else:
                            st.info(f"⚪ Consensus: {consensus.upper()}")

                        st.metric("Price Target", f"${result.get('consensus_price_target', 0):.2f}")
                        st.metric("Rating Score", f"{result.get('consensus_rating_value', 0):.2f}/5")

                    with col2:
                        st.metric("High Target", f"${result.get('high_price_target', 0):.2f}")
                        st.metric("Low Target", f"${result.get('low_price_target', 0):.2f}")

                        # Calculate upside if we have current price
                        consensus_target = result.get('consensus_price_target', 0)
                        if consensus_target > 0:
                            st.info(f"Range: ${result.get('low_price_target', 0):.0f} - ${result.get('high_price_target', 0):.0f}")

                    with col3:
                        st.metric("Total Analysts", result.get('ratings_contributors', 0))
                        st.metric("Price Analysts", result.get('price_target_contributors', 0))

                        # Show buy/sell breakdown
                        strong_buy = result.get('strong_buy_ratings', 0)
                        buy = result.get('buy_ratings', 0)
                        hold = result.get('hold_ratings', 0)
                        sell = result.get('sell_ratings', 0)
                        strong_sell = result.get('strong_sell_ratings', 0)

                        st.caption(f"🟢 Buy: {strong_buy + buy} | ⚪ Hold: {hold} | 🔴 Sell: {sell + strong_sell}")
                else:
                    st.warning("⚠️ This feature requires a Benzinga Consensus subscription. You currently have News + Earnings subscriptions.")

# Sentiment Tab
with tab_sentiment:
    st.header("💹 Sentiment Analysis")

    sent_ticker = st.text_input("Enter Ticker Symbol", value=default_ticker, key="sent_ticker")

    if st.button("Analyze Sentiment", key="fetch_sentiment"):
        with st.spinner("Analyzing sentiment..."):
            sent_data = fetch_data(f"/api/sentiment/{sent_ticker}")

            if sent_data:
                col1, col2 = st.columns([1, 2])

                with col1:
                    score = sent_data.get('score', 50)
                    sentiment = sent_data.get('sentiment', 'neutral')

                    # Create gauge-like display
                    color = get_sentiment_color(score)
                    st.metric("Score", f"{score}/100")
                    st.progress(score/100)

                    if sentiment == "bullish":
                        st.success(f"🐂 {sentiment.upper()}")
                    elif sentiment == "bearish":
                        st.error(f"🐻 {sentiment.upper()}")
                    else:
                        st.info(f"➖ {sentiment.upper()}")

                with col2:
                    sources = sent_data.get('sources', {})
                    st.write("**Data Sources:**")
                    st.write(f"📰 News Analyzed: {sources.get('news_analyzed', 0)}")
                    st.write(f"⭐ Ratings Analyzed: {sources.get('ratings_analyzed', 0)}")
                    st.write(f"🎯 Has Consensus: {'✅' if sources.get('has_consensus') else '❌'}")
                    st.write(f"🕐 Updated: {format_datetime(sent_data.get('timestamp', ''))}")

# Scans Tab
with tab_scans:
    st.header("🔍 Market Scans")

    scan_type = st.selectbox("Select Scan Type", [
        "Core Watchlist",
        "Momentum Universe",
        "Spicy High-Vol"
    ])

    if st.button("Run Scan", key="run_scan"):
        endpoint_map = {
            "Core Watchlist": "/api/scan/watchlist",
            "Momentum Universe": "/api/scan/universe",
            "Spicy High-Vol": "/api/scan/spicy"
        }

        with st.spinner(f"Scanning {scan_type}..."):
            scan_data = fetch_data(endpoint_map[scan_type])

            if scan_data:
                col1, col2 = st.columns([1, 1])

                # Summary metrics
                with col1:
                    st.metric("Total Scanned", scan_data.get(
                        'watchlist_count',
                        scan_data.get('universe_count',
                        scan_data.get('spicy_count', 0))
                    ))

                with col2:
                    opportunities = scan_data.get('top_opportunities', [])
                    warnings = scan_data.get('warnings', [])
                    st.metric("Opportunities", len(opportunities))
                    st.metric("Warnings", len(warnings))

                # Risk warning for spicy
                if scan_type == "Spicy High-Vol" and scan_data.get('risk_warning'):
                    st.warning(scan_data['risk_warning'])

                # Results table
                results = scan_data.get('results', [])
                if results:
                    df = pd.DataFrame(results)

                    # Style the dataframe
                    def color_score(val):
                        if isinstance(val, (int, float)):
                            if val >= 70:
                                return 'background-color: lightgreen'
                            elif val <= 30:
                                return 'background-color: lightcoral'
                        return ''

                    styled_df = df.style.applymap(color_score, subset=['score'] if 'score' in df.columns else [])
                    st.dataframe(styled_df, use_container_width=True)

                    # Show top opportunities
                    if opportunities:
                        st.subheader("🎯 Top Opportunities")
                        for opp in opportunities[:5]:
                            st.success(f"{opp['ticker']}: Score {opp['score']} - {opp.get('recommendation', 'N/A')}")

                    # Show warnings
                    if warnings:
                        st.subheader("⚠️ Warnings")
                        for warn in warnings[:5]:
                            st.error(f"{warn['ticker']}: Score {warn['score']} - {warn.get('recommendation', 'N/A')}")

# Streams Tab
with tab_streams:
    st.header("📡 Live Data Streams")

    ws_endpoint = st.selectbox("WebSocket Endpoint", [
        "/ws/momentum",  # New high-speed option first
        "/ws/signals",
        "/ws/trades",
        "/ws/status"
    ], help="⚡ /ws/momentum - Updates every 5 seconds for fast trading")

    col1, col2, col3 = st.columns([1, 1, 4])

    with col1:
        if not st.session_state.ws_connected:
            if st.button("🟢 Connect", key="ws_connect"):
                ws_url = st.session_state.backend_url.replace("http://", "ws://").replace("https://", "wss://")
                ws_url = f"{ws_url}{ws_endpoint}"

                # Try to connect
                ws = create_websocket_connection(ws_url)
                if ws:
                    st.session_state.ws_connection = ws
                    st.session_state.ws_connected = True
                    st.success(f"Connected to {ws_url}")
                    st.rerun()
                else:
                    st.error(f"Failed to connect to {ws_url}")
        else:
            if st.button("🔴 Disconnect", key="ws_disconnect"):
                if st.session_state.ws_connection:
                    try:
                        st.session_state.ws_connection.close()
                    except:
                        pass
                st.session_state.ws_connected = False
                st.session_state.ws_connection = None
                st.session_state.ws_messages = []
                st.rerun()

    with col2:
        if st.button("🗑️ Clear Messages"):
            st.session_state.ws_messages = []
            st.rerun()

    with col3:
        if st.session_state.ws_connected:
            st.success("🟢 Connected to WebSocket")
        else:
            st.info("⚪ Not connected")

    # Display messages
    st.subheader("Live Messages")

    # If connected, try to receive messages
    if st.session_state.ws_connected and st.session_state.ws_connection:
        # Try to receive a message
        try:
            message_data = receive_websocket_message(st.session_state.ws_connection)
            if message_data:
                # Add new message to the list
                st.session_state.ws_messages.append({
                    'time': datetime.now().strftime("%H:%M:%S"),
                    'data': message_data
                })
                # Keep only last 100 messages
                if len(st.session_state.ws_messages) > 100:
                    st.session_state.ws_messages = st.session_state.ws_messages[-100:]
        except Exception as e:
            st.error(f"Connection lost: {e}")
            st.session_state.ws_connected = False
            st.session_state.ws_connection = None

    # Display messages
    if st.session_state.ws_messages:
        # Create a container for messages
        message_container = st.container()

        with message_container:
            for msg in reversed(st.session_state.ws_messages[-20:]):  # Show last 20 messages
                col1, col2 = st.columns([1, 5])
                with col1:
                    st.code(msg['time'])
                with col2:
                    st.json(msg['data'])

        # Auto-refresh every second when connected to get new messages
        if st.session_state.ws_connected:
            time.sleep(1)
            st.rerun()
    else:
        st.info("No messages yet. Connect to start receiving data.")

# Footer
st.divider()
st.caption("AI Trading Intelligence System - Real-time market data powered by Massive API")