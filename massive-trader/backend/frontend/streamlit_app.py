import httpx
import pandas as pd
import streamlit as st
from datetime import datetime
from typing import Any, Dict, List, Optional

st.set_page_config(
    page_title="Massive Agent – AI Day Trading",
    page_icon="📈",
    layout="wide",
)

# ---- Session defaults ----
if "backend_url" not in st.session_state:
    st.session_state.backend_url = "http://localhost:8000"
if "selected_ticker" not in st.session_state:
    st.session_state.selected_ticker = "AAPL"
if "dashboard_data" not in st.session_state:
    st.session_state.dashboard_data = None
if "auto_trade" not in st.session_state:
    st.session_state.auto_trade = False


# ---- Data fetchers ----
@st.cache_data(ttl=15)
def fetch_status(backend_url: str) -> Dict[str, Any]:
    try:
        resp = httpx.get(f"{backend_url}/status", timeout=8.0)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Unable to reach backend status: {exc}")
        return {}


@st.cache_data(ttl=15)
def fetch_dashboard(backend_url: str, ticker: str) -> Dict[str, Any]:
    try:
        resp = httpx.get(f"{backend_url}/api/dashboard/{ticker}", timeout=20.0)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to fetch dashboard data: {exc}")
        return {}


# ---- Helpers ----
def format_pct(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"{value*100:.2f}%"


def format_price(value: Optional[float]) -> str:
    if value is None:
        return "—"
    return f"${value:,.2f}"


def circuit_badge(level: str) -> str:
    colors = {
        "GREEN": "✅",
        "YELLOW": "🟡",
        "ORANGE": "🟠",
        "RED": "🔴",
        "UNKNOWN": "⚪",
    }
    return f"{colors.get(level, '⚪')} {level}"


def build_price_df(bars: List[Dict[str, Any]]) -> Optional[pd.DataFrame]:
    if not bars:
        return None
    df = pd.DataFrame(bars)
    time_key = "t" if "t" in df.columns else "timestamp" if "timestamp" in df.columns else None
    close_key = "c" if "c" in df.columns else "close" if "close" in df.columns else None
    if not time_key or not close_key:
        return None
    df[time_key] = pd.to_datetime(df[time_key])
    df = df.sort_values(time_key)
    df = df[[time_key, close_key]].rename(columns={time_key: "time", close_key: "close"})
    return df


# ---- Layout ----
status = fetch_status(st.session_state.backend_url)
watchlist = status.get("watchlist", ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN"])
paper_mode = status.get("is_paper", True)
current_circuit_level = (
    st.session_state.dashboard_data.get("risk", {}).get("circuit_breaker")
    if st.session_state.dashboard_data
    else "UNKNOWN"
)
auto_trade_disabled = current_circuit_level in ["ORANGE", "RED"]

header_col1, header_col2, header_col3 = st.columns([2, 1, 1])
with header_col1:
    st.title("Massive Agent – AI Day Trading")
    st.caption("Benzinga via Polygon + Alpaca + Multi-Agent AI (paper by default)")
with header_col2:
    env_label = "Paper Trading" if paper_mode else "⚠️ LIVE TRADING"
    env_color = "green" if paper_mode else "red"
    st.markdown(f"**Environment:** :{env_color}[{env_label}]")
    st.text(f"Backend: {st.session_state.backend_url}")
with header_col3:
    st.markdown("**Circuit Breaker**")
    # Placeholder until data loaded
    st.code("—")

# Controls
controls_col1, controls_col2, controls_col3, controls_col4 = st.columns([2, 2, 1, 1])
with controls_col1:
    backend_url = st.text_input("Backend URL", st.session_state.backend_url)
    if backend_url != st.session_state.backend_url:
        st.session_state.backend_url = backend_url
with controls_col2:
    ticker_selection = st.selectbox(
        "Ticker",
        options=watchlist,
        index=watchlist.index(st.session_state.selected_ticker) if st.session_state.selected_ticker in watchlist else 0,
    )
    custom_ticker = st.text_input("Custom Ticker (overrides selection)", value="")
    chosen_ticker = custom_ticker.upper().strip() or ticker_selection
    st.session_state.selected_ticker = chosen_ticker
with controls_col3:
    auto_refresh = st.toggle("Auto-refresh", value=False, help="Refresh every interval below")
    refresh_seconds = st.slider("Interval (sec)", 10, 120, 30, disabled=not auto_refresh)
with controls_col4:
    st.session_state.auto_trade = st.toggle(
        "Auto-Trade",
        value=st.session_state.auto_trade,
        disabled=auto_trade_disabled,
        help="Off by default. No live orders unless explicitly enabled server-side.",
    )

trigger = st.button("Fetch Data & Run Agents", type="primary")
if auto_refresh:
    st.markdown(
        f"<meta http-equiv='refresh' content='{refresh_seconds}'>",
        unsafe_allow_html=True,
    )
    trigger = True

if trigger:
    st.session_state.dashboard_data = fetch_dashboard(st.session_state.backend_url, chosen_ticker)

data = st.session_state.dashboard_data

if not data:
    st.info("Load data to view the dashboard.")
    st.stop()

# Update circuit badge with actual data
circuit_level = data.get("risk", {}).get("circuit_breaker", "UNKNOWN")
header_col3.code(circuit_badge(circuit_level))
if circuit_level in ["ORANGE", "RED"] and st.session_state.auto_trade:
    st.session_state.auto_trade = False
    st.warning("Auto-Trade disabled due to circuit breaker level.")

# ---- Market Snapshot & Technicals ----
market = data.get("market", {})
quote = market.get("quote") or {}
technicals = market.get("technicals") or {}
bars_df = build_price_df(market.get("bars", []))

snapshot_col1, snapshot_col2, snapshot_col3, snapshot_col4 = st.columns(4)
with snapshot_col1:
    st.subheader("Price")
    st.metric("Last", format_price(quote.get("last")))
    st.metric("Bid / Ask", f"{format_price(quote.get('bid'))} / {format_price(quote.get('ask'))}")
with snapshot_col2:
    st.subheader("Spread & Size")
    if quote.get("bid") and quote.get("ask"):
        spread = quote["ask"] - quote["bid"]
    else:
        spread = None
    st.metric("Spread", format_price(spread))
    st.metric("Bid Size / Ask Size", f"{quote.get('bid_size', '—')} / {quote.get('ask_size', '—')}")
with snapshot_col3:
    st.subheader("Technicals")
    st.metric("RSI(14)", f"{technicals.get('rsi', '—'):.1f}" if technicals.get("rsi") else "—")
    st.metric("MACD Hist", f"{technicals.get('macd_histogram', 0):.4f}" if technicals.get("macd_histogram") else "—")
with snapshot_col4:
    st.subheader("Moving Averages")
    st.metric("SMA 20", format_price(technicals.get("sma_20")))
    st.metric("SMA 50", format_price(technicals.get("sma_50")))

if bars_df is not None and not bars_df.empty:
    st.line_chart(bars_df.rename(columns={"time": "index"}).set_index("index"))

# ---- News & Earnings ----
st.markdown("### News & Earnings")
ne_col1, ne_col2 = st.columns(2)

news_items = data.get("news", {}).get("items", [])
with ne_col1:
    st.subheader("Latest News")
    if news_items:
        for item in news_items:
            published = item.get("published")
            title = item.get("title", "No title")
            teaser = item.get("teaser", "")
            st.write(f"**{title}**")
            st.caption(f"{published} | Channels: {', '.join(item.get('channels', []))}")
            if teaser:
                st.write(teaser[:200] + ("..." if len(teaser) > 200 else ""))
            st.divider()
    else:
        st.info("No recent news found.")

earnings_items = data.get("earnings", {}).get("items", [])
with ne_col2:
    st.subheader("Recent Earnings")
    if earnings_items:
        earnings_df = pd.DataFrame(earnings_items)
        display_cols = [
            "date",
            "time",
            "eps_actual",
            "eps_estimate",
            "eps_surprise_pct",
            "revenue_actual",
            "revenue_estimate",
            "revenue_surprise_pct",
            "importance",
        ]
        existing_cols = [c for c in display_cols if c in earnings_df.columns]
        st.dataframe(earnings_df[existing_cols], use_container_width=True)
    else:
        st.info("No recent earnings data.")

# ---- AI Agent Insights ----
st.markdown("### AI Agent Insights")
agents = data.get("consensus", {}).get("contributing_agents", {})

agent_col1, agent_col2, agent_col3 = st.columns(3)
with agent_col1:
    news_agent = agents.get("news", {})
    st.metric("News Signal", f"{news_agent.get('score', 50):.1f}/100")
    st.caption(f"Sentiment: {news_agent.get('sentiment', 0):.2f} | Confidence: {news_agent.get('confidence', 0):.2f}")
with agent_col2:
    earnings_agent = agents.get("earnings", {})
    st.metric("Earnings Signal", f"{earnings_agent.get('score', 50):.1f}/100")
    st.caption(f"Sentiment: {earnings_agent.get('sentiment', 0):.2f} | Confidence: {earnings_agent.get('confidence', 0):.2f}")
with agent_col3:
    tech_agent = agents.get("technical", {})
    st.metric("Technical Signal", f"{tech_agent.get('score', 50):.1f}/100")
    st.caption(f"Sentiment: {tech_agent.get('sentiment', 0):.2f} | Confidence: {tech_agent.get('confidence', 0):.2f}")

# ---- Consensus & Trade Decision ----
st.markdown("### Consensus & Trade Decision")
consensus = data.get("consensus", {})
action_display = consensus.get("action", "HOLD")
if circuit_level in ["ORANGE", "RED"] and action_display == "BUY":
    action_display = "NO TRADE"
decision_col1, decision_col2, decision_col3, decision_col4 = st.columns(4)
with decision_col1:
    st.metric("Action", action_display)
with decision_col2:
    st.metric("Final Score", f"{consensus.get('final_score', 0):.1f}")
with decision_col3:
    st.metric("Stop Loss", format_pct(consensus.get("stop_loss_pct")))
with decision_col4:
    st.metric("Take Profit", format_pct(consensus.get("take_profit_pct")))

st.caption(
    f"Time Horizon: {consensus.get('time_horizon', '—')} | "
    f"Fast Reaction: {consensus.get('fast_reaction_mode', False)}"
)

# ---- Risk & Account ----
st.markdown("### Risk & Account")
risk = data.get("risk", {})
account = data.get("account") or {}
positions = data.get("positions", [])

risk_col1, risk_col2, risk_col3 = st.columns(3)
with risk_col1:
    st.metric("Circuit Breaker", circuit_badge(circuit_level))
    pnl_pct = risk.get("daily_pnl_pct")
    st.metric("Daily P&L", format_pct(pnl_pct))
with risk_col2:
    st.metric("Equity", format_price(account.get("equity")))
    st.metric("Buying Power", format_price(account.get("buying_power")))
with risk_col3:
    st.metric("Cash", format_price(account.get("cash")))
    st.metric("Open Positions", len(positions))

decision = risk.get("decision") or {}
if decision:
    st.success(
        f"Risk Decision: {decision.get('reason', 'Approved')} | "
        f"Suggested Shares: {decision.get('suggested_shares', '—')}"
    )
if risk.get("message"):
    st.warning(f"Risk Warning: {risk['message']}")
if data.get("errors"):
    for err in data["errors"]:
        st.error(err)

if positions:
    pos_df = pd.DataFrame(positions)
    pos_cols = ["symbol", "side", "qty", "avg_entry_price", "current_price", "unrealized_plpc", "market_value"]
    existing = [c for c in pos_cols if c in pos_df.columns]
    st.dataframe(pos_df[existing], use_container_width=True)

# ---- Footer ----
st.caption(
    "Auto-Trade toggle is client-side only; live trading requires ALPACA_ENV=live and backend approval. "
    "Paper mode is recommended for testing."
)
