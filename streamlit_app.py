import json
import queue
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlparse
from copy import deepcopy

import httpx
import streamlit as st
import websocket
try:
    from streamlit_autorefresh import st_autorefresh
except Exception:  # pragma: no cover - optional dependency
    st_autorefresh = None


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def get_base_url() -> str:
    """Return sanitized backend base URL."""
    base = st.session_state.get("base_url", "http://localhost:8000").strip()
    return base.rstrip("/")


@st.cache_data(ttl=30)
def fetch_json(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """GET helper with simple error wrapping."""
    url = f"{get_base_url()}{path}"
    try:
        with httpx.Client(timeout=20) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        return {"error": str(exc)}


def ws_listener(endpoint: str, control_flag: threading.Event, msg_queue: queue.Queue):
    """Listen to a websocket endpoint and push messages to a queue."""
    try:
        ws = websocket.WebSocket()
        ws.settimeout(45)  # Slightly longer than server heartbeat (30s)
        ws.connect(endpoint)
        msg_queue.put({"type": "status", "message": f"Connected to {endpoint}"})
        while not control_flag.is_set():
            try:
                payload = ws.recv()
                msg_queue.put({"type": "message", "message": payload})
            except websocket.WebSocketTimeoutException:
                # No message received within timeout, send ping to keep alive
                try:
                    ws.send("ping")
                except Exception:
                    msg_queue.put({"type": "error", "message": "Connection lost"})
                    break
            except Exception as exc:
                msg_queue.put({"type": "error", "message": str(exc)})
                break
    except Exception as exc:
        msg_queue.put({"type": "error", "message": str(exc)})
    finally:
        msg_queue.put({"type": "status", "message": "Disconnected"})
        try:
            ws.close()
        except Exception:
            pass


def normalize_ws_endpoint(raw: str) -> str:
    """
    Normalize user-entered endpoint:
    - If no scheme, treat as relative to backend base and use ws:// or wss:// accordingly
    - If http/https, convert to ws/wss
    """
    raw = raw.strip()
    if not raw:
        return ""

    parsed = urlparse(raw)
    # No scheme means relative path
    if not parsed.scheme:
        base = get_base_url()
        base_parsed = urlparse(base)
        ws_scheme = "wss" if base_parsed.scheme == "https" else "ws"
        return f"{ws_scheme}://{base_parsed.netloc}{raw if raw.startswith('/') else '/' + raw}"

    if parsed.scheme in ("http", "https"):
        ws_scheme = "wss" if parsed.scheme == "https" else "ws"
        return raw.replace(f"{parsed.scheme}://", f"{ws_scheme}://", 1)

    return raw


def parse_time(ts: str) -> Optional[datetime]:
    """Parse timestamp safely."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def human_age(ts: str) -> str:
    """Return 'x min ago' style age."""
    dt = parse_time(ts)
    if not dt:
        return ""
    delta = datetime.now(timezone.utc) - dt
    mins = int(delta.total_seconds() // 60)
    if mins < 1:
        return "just now"
    if mins < 60:
        return f"{mins} min ago"
    hours = mins // 60
    return f"{hours} hr ago"


def first_ticker_from_news(item: Dict[str, Any]) -> Optional[str]:
    """Try to extract a primary ticker from a news item."""
    if not isinstance(item, dict):
        return None
    if item.get("ticker"):
        return str(item["ticker"])
    stocks = item.get("stocks") or item.get("tickers") or []
    if isinstance(stocks, list) and stocks:
        first = stocks[0]
        if isinstance(first, dict) and "ticker" in first:
            return str(first["ticker"])
        return str(first)
    return None


def sentiment_badge(score: float) -> str:
    """Return BUY/SELL/HOLD text from score."""
    if score >= 70:
        return "BUY"
    if score <= 30:
        return "SELL"
    return "HOLD"


# -------------------------------------------------------------------
# Page setup
# -------------------------------------------------------------------

st.set_page_config(page_title="AI Trading Intelligence System", layout="wide")
st.title("🚀 AI Trading Intelligence System")

# Sidebar controls
with st.sidebar:
    st.header("Settings")
    base_url_input = st.text_input("Backend Base URL", value=get_base_url(), placeholder="http://localhost:8000")
    st.session_state["base_url"] = base_url_input
    default_ticker = st.text_input("Default Ticker", value=st.session_state.get("default_ticker", "AAPL"))
    st.session_state["default_ticker"] = default_ticker
    st.caption("Ensure backend FastAPI server is running before using the dashboard.")

# Preload health/status
health = fetch_json("/health")
status = fetch_json("/status")

# Overview
tab_overview, tab_news, tab_earnings, tab_ratings, tab_consensus, tab_sentiment, tab_scans, tab_streams = st.tabs(
    ["📊 Overview", "📰 News", "📅 Earnings", "⭐ Ratings", "🎯 Consensus", "💹 Sentiment", "🔍 Scans", "📡 Streams"]
)

# -------------------------------------------------------------------
# Overview
# -------------------------------------------------------------------
with tab_overview:
    cols = st.columns(4)
    cols[0].metric("Env", health.get("environment", "n/a"), help="Trading environment")
    cols[1].metric("Paper Trading", "Yes" if health.get("paper_trading") else "No")
    cols[2].metric("Backend", "Healthy" if health.get("status") == "healthy" else "Unknown")
    cols[3].metric("Watchlist Size", len(status.get("watchlist", [])) if isinstance(status, dict) else 0)

    st.subheader("Risk Settings")
    risk = status.get("risk_settings", {}) if isinstance(status, dict) else {}
    st.write(
        {
            "Max Position Risk": risk.get("max_position_risk"),
            "Daily Max Drawdown": risk.get("daily_max_drawdown"),
            "Min Signal Score": risk.get("min_signal_score"),
            "Hybrid Interval (s)": status.get("hybrid_interval"),
        }
    )

    st.subheader("API Keys Configured")
    api_keys = status.get("api_keys_configured", {}) if isinstance(status, dict) else {}
    st.write({k: "Yes" if v else "No" for k, v in api_keys.items()})

# -------------------------------------------------------------------
# News
# -------------------------------------------------------------------
with tab_news:
    st.subheader("📰 News")

    st.markdown("**Live Watchlist Feed (polls REST)**")
    live_watchlist = ",".join(status.get("watchlist", [])) if isinstance(status, dict) else default_ticker
    live_tickers = st.text_input("Tickers to watch (comma-separated)", value=live_watchlist, key="live_news_tickers")
    live_limit = st.slider("Max items", min_value=5, max_value=100, value=30, key="live_news_limit")
    live_days = st.number_input("Days back", min_value=1, max_value=7, value=1, key="live_news_days")
    auto_refresh = st.checkbox("Auto-refresh", value=False, help="Refresh periodically to catch breaking headlines.")
    interval_sec = st.slider("Refresh interval (sec)", min_value=10, max_value=120, value=30, key="live_news_interval")
    manual_refresh = st.button("Refresh live feed")

    auto_tick = 0
    if auto_refresh and st_autorefresh:
        auto_tick = st_autorefresh(interval=interval_sec * 1000, limit=None, key="live_news_autorefresh")
    elif auto_refresh and not st_autorefresh:
        st.warning("Install streamlit-autorefresh for background refresh, or click Refresh manually.")

    if manual_refresh or (auto_refresh and auto_tick):
        live_data = fetch_json(
            "/api/news",
            params={"ticker": live_tickers or None, "days_back": live_days, "limit": live_limit},
        )
        if "error" in live_data:
            st.error(live_data["error"])
        else:
            results = live_data.get("results", [])
            if results:
                # sort newest first if possible
                results_sorted = sorted(
                    results,
                    key=lambda x: parse_time(x.get("published_at") or x.get("created_at") or ""),
                    reverse=True,
                )
                # Attach quick sentiment for first few items
                enriched = []
                for item in results_sorted[:10]:
                    enriched_item = deepcopy(item)
                    ticker_guess = first_ticker_from_news(item)
                    if ticker_guess:
                        sent = fetch_json(f"/api/sentiment/{ticker_guess}")
                        if "error" not in sent:
                            score = sent.get("score", 0)
                            enriched_item["agent_score"] = score
                            enriched_item["agent_decision"] = sentiment_badge(score)
                    enriched_item["age"] = human_age(item.get("published_at") or item.get("created_at") or "")
                    enriched.append(enriched_item)
                # keep remainder un-enriched to save calls
                enriched.extend(results_sorted[10:])
                st.caption(f"Fetched {len(results)} items • Last refresh: {datetime.utcnow().isoformat(timespec='seconds')}Z")
                st.dataframe(enriched)
            else:
                st.info("No news returned for the selected window.")

    st.divider()
    with st.form("news_form"):
        ticker = st.text_input("Ticker(s)", value=default_ticker)
        channels = st.text_input("Channels", value="")
        days_back = st.number_input("Days back", min_value=1, max_value=30, value=1)
        limit = st.slider("Limit", min_value=1, max_value=100, value=20)
        submitted = st.form_submit_button("Fetch News")
    if submitted:
        data = fetch_json(
            "/api/news",
            params={"ticker": ticker or None, "channels": channels or None, "days_back": days_back, "limit": limit},
        )
        if "error" in data:
            st.error(data["error"])
        else:
            st.dataframe(data.get("results", []))
            # Quick sentiment/decision from agents for primary ticker
            main_ticker = (ticker or default_ticker).split(",")[0].strip()
            if main_ticker:
                sent = fetch_json(f"/api/sentiment/{main_ticker}")
                if "error" not in sent:
                    score = sent.get("score", 0)
                    recommendation = "BUY" if score >= 70 else "SELL" if score <= 30 else "HOLD"
                    st.success(f"Agent snapshot for {main_ticker}: {recommendation} (score {score})")

# -------------------------------------------------------------------
# Earnings
# -------------------------------------------------------------------
with tab_earnings:
    st.subheader("📅 Earnings")
    with st.form("earnings_form"):
        ticker = st.text_input("Ticker", value=default_ticker, key="earnings_ticker")
        days_ahead = st.number_input("Days ahead", min_value=1, max_value=90, value=7)
        importance_min = st.slider("Min importance", min_value=0, max_value=5, value=0)
        limit = st.slider("Limit ", min_value=1, max_value=100, value=20, key="earnings_limit")
        submitted = st.form_submit_button("Fetch Earnings")
    if submitted:
        data = fetch_json(
            "/api/earnings",
            params={
                "ticker": ticker or None,
                "days_ahead": days_ahead,
                "importance_min": importance_min,
                "limit": limit,
            },
        )
        if "error" in data:
            st.error(data["error"])
        else:
            st.dataframe(data.get("results", []))

# -------------------------------------------------------------------
# Ratings
# -------------------------------------------------------------------
with tab_ratings:
    st.subheader("⭐ Ratings")
    with st.form("ratings_form"):
        ticker = st.text_input("Ticker", value=default_ticker, key="ratings_ticker")
        days_back = st.number_input("Days back", min_value=1, max_value=30, value=7, key="ratings_days")
        action = st.text_input("Action filter", value="")
        limit = st.slider("Limit", min_value=1, max_value=100, value=20, key="ratings_limit")
        submitted = st.form_submit_button("Fetch Ratings")
    if submitted:
        data = fetch_json(
            "/api/ratings",
            params={
                "ticker": ticker or None,
                "days_back": days_back,
                "action": action or None,
                "limit": limit,
            },
        )
        if "error" in data:
            st.error(data["error"])
        else:
            st.dataframe(data.get("results", []))

# -------------------------------------------------------------------
# Consensus
# -------------------------------------------------------------------
with tab_consensus:
    st.subheader("🎯 Consensus")
    ticker = st.text_input("Ticker", value=default_ticker, key="consensus_ticker")
    if st.button("Fetch Consensus"):
        data = fetch_json(f"/api/consensus/{ticker}")
        if "error" in data:
            st.error(data["error"])
        else:
            st.json(data)

# -------------------------------------------------------------------
# Sentiment
# -------------------------------------------------------------------
with tab_sentiment:
    st.subheader("💹 Sentiment")
    ticker = st.text_input("Ticker", value=default_ticker, key="sentiment_ticker")
    if st.button("Fetch Sentiment"):
        data = fetch_json(f"/api/sentiment/{ticker}")
        if "error" in data:
            st.error(data["error"])
        else:
            score = data.get("score", 0)
            st.metric("Score", f"{score:.1f}")
            st.json(data)

# -------------------------------------------------------------------
# Scans
# -------------------------------------------------------------------
with tab_scans:
    st.subheader("🔍 Scans")
    col_a, col_b, col_c = st.columns(3)
    if col_a.button("Scan Watchlist"):
        data = fetch_json("/api/scan/watchlist")
        col_a.write(data)
    if col_b.button("Scan Universe"):
        data = fetch_json("/api/scan/universe")
        col_b.write(data)
    if col_c.button("Scan Spicy"):
        data = fetch_json("/api/scan/spicy")
        col_c.write(data)

# -------------------------------------------------------------------
# Streams
# -------------------------------------------------------------------
with tab_streams:
    st.subheader("📡 Live Data Streams")

    if "ws_messages" not in st.session_state:
        st.session_state.ws_messages = []
    if "ws_error" not in st.session_state:
        st.session_state.ws_error = None
    if "ws_flag" not in st.session_state:
        st.session_state.ws_flag = threading.Event()
    if "ws_thread" not in st.session_state:
        st.session_state.ws_thread = None
    if "ws_queue" not in st.session_state:
        st.session_state.ws_queue = queue.Queue()

    endpoint = st.text_input(
        "WebSocket Endpoint",
        value=normalize_ws_endpoint("/ws/signals"),
        help="Try /ws/signals, /ws/trades, or /ws/status",
    )

    status_col, btn_col = st.columns([1, 3])
    is_connected = bool(st.session_state.ws_thread and st.session_state.ws_thread.is_alive())
    with status_col:
        status_text = "🟢 Connected" if is_connected else "⚪ Not connected"
        st.markdown(f"**Status:** {status_text}")
    with btn_col:
        connect_clicked = st.button("Connect", disabled=is_connected)
        disconnect_clicked = st.button("Disconnect")
        quick_status = st.button("Quick-connect /ws/status", disabled=is_connected)

    target_endpoint = normalize_ws_endpoint(endpoint)
    if quick_status:
        target_endpoint = normalize_ws_endpoint("/ws/status")
        connect_clicked = True

    if connect_clicked:
        st.session_state.ws_messages = []
        st.session_state.ws_error = None
        st.session_state.ws_flag.clear()
        st.session_state.ws_thread = threading.Thread(
            target=ws_listener, args=(target_endpoint, st.session_state.ws_flag, st.session_state.ws_queue), daemon=True
        )
        st.session_state.ws_thread.start()

    if disconnect_clicked and st.session_state.ws_thread:
        st.session_state.ws_flag.set()

    # Drain queue
    while not st.session_state.ws_queue.empty():
        item = st.session_state.ws_queue.get_nowait()
        if item["type"] == "message":
            st.session_state.ws_messages.append(item["message"])
        elif item["type"] == "error":
            st.session_state.ws_error = item["message"]
        elif item["type"] == "status":
            st.session_state.ws_messages.append(item["message"])

    if st.session_state.ws_error:
        st.error(st.session_state.ws_error)

    st.markdown("**Live Messages**")
    if st.session_state.ws_messages:
        for msg in reversed(st.session_state.ws_messages[-200:]):
            try:
                st.code(json.dumps(json.loads(msg), indent=2))
            except Exception:
                st.code(msg)
    else:
        st.caption("No messages yet. Connect to start receiving data.")

# -------------------------------------------------------------------
# Run instructions
# -------------------------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.markdown(
    "Run: `pip install -r streamlit-requirements.txt && streamlit run streamlit_app.py --server.port 8501`"
)
