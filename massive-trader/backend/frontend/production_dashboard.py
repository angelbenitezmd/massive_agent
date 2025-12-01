#!/usr/bin/env python3
"""
Production Trading Dashboard for Alpaca Paper Trading
Monitors the ONE best signal and auto-executes trades
"""

import streamlit as st
import httpx
import websocket
import json
import time
import threading
from datetime import datetime, timedelta
import queue

# Page config
st.set_page_config(
    page_title="Production Trading Dashboard",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Initialize session state
if "ws_connected" not in st.session_state:
    st.session_state.ws_connected = False
if "latest_signal" not in st.session_state:
    st.session_state.latest_signal = None
if "positions" not in st.session_state:
    st.session_state.positions = []
if "account_info" not in st.session_state:
    st.session_state.account_info = None
if "execution_log" not in st.session_state:
    st.session_state.execution_log = []
if "ws_messages" not in st.session_state:
    st.session_state.ws_messages = queue.Queue()

# API client
client = httpx.Client(base_url="http://localhost:8000", timeout=30.0)

# Title and status header
col1, col2, col3 = st.columns([3, 1, 1])
with col1:
    st.title("🚀 Production Trading Dashboard")
with col2:
    if st.session_state.ws_connected:
        st.success("🟢 Live Connected")
    else:
        st.error("🔴 Disconnected")
with col3:
    if st.button("🔄 Refresh"):
        st.rerun()

# Divider
st.markdown("---")

# Main layout: Signal Monitor, Positions, Execution Log
main_col1, main_col2 = st.columns([1, 1])

with main_col1:
    st.header("📡 Best Trading Signal")

    # Get the best signal
    try:
        response = client.get("/api/trading/best-signal")
        signal = response.json()
        st.session_state.latest_signal = signal

        if signal and signal.get("ticker"):
            # Signal strength indicator
            combined_score = signal.get("combined_score", 0)

            # Color code based on score
            if combined_score >= 75:
                color = "🟢"
                status = "AUTO-EXECUTE"
                st.success(f"{color} **Strong Signal - {status}**")
            elif combined_score >= 60:
                color = "🟡"
                status = "MONITOR"
                st.warning(f"{color} **Moderate Signal - {status}**")
            else:
                color = "🔴"
                status = "WEAK"
                st.info(f"{color} **Weak Signal - {status}**")

            # Signal details
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("Ticker", signal["ticker"])
                st.metric("Action", signal["action"])

            with col2:
                st.metric("Combined Score", f"{combined_score:.1f}/100")
                confidence = signal.get("confidence", "HIGH" if combined_score >= 75 else "MODERATE")
                st.metric("Confidence", confidence)

            with col3:
                st.metric("Entry Price", f"${signal['entry_price']:.2f}")
                if signal.get("stop_loss"):
                    st.metric("Stop Loss", f"${signal['stop_loss']:.2f}")

            # Momentum vs AI breakdown
            st.subheader("📊 Signal Components")
            col1, col2 = st.columns(2)

            with col1:
                momentum = signal.get("momentum_score", 0)
                st.metric(
                    "Momentum Score (70% weight)",
                    f"{momentum:.1f}/100",
                    f"{momentum * 0.7:.1f} pts"
                )

            with col2:
                ai_score = signal.get("ai_score", 0)
                st.metric(
                    "AI Score (30% weight)",
                    f"{ai_score:.1f}/100",
                    f"{ai_score * 0.3:.1f} pts"
                )

            # Source of signal
            st.info(f"📰 Source: {signal.get('source', 'Unknown')}")

            # Execute button (manual override)
            if combined_score < 75:  # Only show for non-auto signals
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("🎯 Execute Trade", type="primary"):
                        exec_response = client.post("/api/trading/execute", json=signal)
                        exec_result = exec_response.json()

                        if exec_result.get("status") == "executed":
                            st.success(f"✅ Trade executed! Order ID: {exec_result['order_id']}")
                            st.session_state.execution_log.append({
                                "timestamp": datetime.now().isoformat(),
                                "signal": signal,
                                "result": exec_result
                            })
                        else:
                            st.error(f"❌ Execution failed: {exec_result.get('message', 'Unknown error')}")

                with col2:
                    if st.button("🚫 Ignore Signal"):
                        st.info("Signal ignored")
        else:
            st.info("No active signals at the moment. Monitoring markets...")

    except Exception as e:
        st.error(f"Error fetching signal: {e}")

with main_col2:
    st.header("💼 Open Positions")

    # Get positions
    try:
        response = client.get("/api/trading/positions")
        positions_data = response.json()

        # Handle both list and dict response formats
        if isinstance(positions_data, dict):
            positions = positions_data.get("positions", [])
        else:
            positions = positions_data

        st.session_state.positions = positions

        if positions and len(positions) > 0:
            for pos in positions:
                # Position card
                with st.container():
                    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])

                    with col1:
                        st.markdown(f"**{pos['symbol']}**")
                        st.caption(f"{pos['qty']} shares")

                    with col2:
                        entry = pos['entry']
                        current = pos['current']
                        st.metric("Entry", f"${entry:.2f}")
                        st.metric("Current", f"${current:.2f}")

                    with col3:
                        pnl = pos['pnl']
                        pnl_pct = pos['pnl_pct']
                        delta_color = "normal" if pnl >= 0 else "inverse"
                        st.metric(
                            "P&L",
                            f"${pnl:.2f}",
                            f"{pnl_pct:.2f}%",
                            delta_color=delta_color
                        )

                    with col4:
                        # Get momentum for this position
                        mom_response = client.get(f"/api/trading/position-momentum/{pos['symbol']}")
                        if mom_response.status_code == 200:
                            mom_data = mom_response.json()
                            current_mom = mom_data.get("current_momentum", 0)

                            # Show momentum with color
                            if current_mom > 60:
                                st.success(f"🔥 Mom: {current_mom:.0f}")
                            elif current_mom > 40:
                                st.warning(f"📈 Mom: {current_mom:.0f}")
                            else:
                                st.error(f"📉 Mom: {current_mom:.0f}")

                            # Exit recommendation
                            if mom_data.get("recommendation") == "CONSIDER_EXIT":
                                if st.button(f"🚪 Close {pos['symbol']}", key=f"close_{pos['symbol']}"):
                                    close_resp = client.post(f"/api/trading/close/{pos['symbol']}")
                                    if close_resp.status_code == 200:
                                        st.success(f"Position closed!")
                                        st.rerun()

                    st.markdown("---")
        else:
            st.info("No open positions. Waiting for signals...")

    except Exception as e:
        st.error(f"Error fetching positions: {e}")

# Account Status Section
st.markdown("---")
st.header("💰 Account Status")

try:
    response = client.get("/api/trading/account")
    account = response.json()
    st.session_state.account_info = account

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Trading Mode", "PAPER" if account.get("status") == "connected" else "SIMULATED")

    with col2:
        cash = account.get("cash", 0)
        st.metric("Cash Available", f"${cash:,.2f}")

    with col3:
        buying_power = account.get("buying_power", 0)
        st.metric("Buying Power", f"${buying_power:,.2f}")

    with col4:
        equity = account.get("equity", 0)
        st.metric("Total Equity", f"${equity:,.2f}")

except Exception as e:
    st.error(f"Error fetching account: {e}")

# Execution Log Section
st.markdown("---")
with st.expander("📋 Execution Log", expanded=False):
    if st.session_state.execution_log:
        for log_entry in reversed(st.session_state.execution_log[-10:]):  # Show last 10
            timestamp = log_entry["timestamp"]
            signal = log_entry["signal"]
            result = log_entry["result"]

            col1, col2, col3 = st.columns([1, 2, 1])

            with col1:
                st.caption(timestamp)

            with col2:
                st.write(f"{signal['ticker']} - {signal['action']}")

            with col3:
                if result["status"] == "executed":
                    st.success("✅ Executed")
                else:
                    st.error("❌ Failed")
    else:
        st.info("No executions yet")

# Live WebSocket Connection
st.markdown("---")
st.subheader("🔴 Live Production Feed")

# WebSocket message display
ws_container = st.container()

def ws_client():
    """WebSocket client for production feed."""
    try:
        ws = websocket.WebSocket()
        ws.connect("ws://localhost:8000/ws/production")
        st.session_state.ws_connected = True

        while True:
            message = ws.recv()
            if message:
                data = json.loads(message)
                st.session_state.ws_messages.put(data)

    except Exception as e:
        st.session_state.ws_connected = False
        print(f"WebSocket error: {e}")

# Start WebSocket in background thread
if not st.session_state.ws_connected:
    ws_thread = threading.Thread(target=ws_client, daemon=True)
    ws_thread.start()

# Display WebSocket messages
with ws_container:
    messages_to_display = []
    while not st.session_state.ws_messages.empty():
        messages_to_display.append(st.session_state.ws_messages.get())

    if messages_to_display:
        for msg in messages_to_display[-5:]:  # Show last 5 messages
            msg_type = msg.get("type", "unknown")

            if msg_type == "unified_signal":
                signal = msg.get("signal", {})
                if signal.get("ticker"):
                    combined = signal.get("combined_score", 0)

                    if combined >= 75:
                        st.success(f"🎯 **AUTO-EXECUTE**: {signal['ticker']} - {signal['action']} (Score: {combined:.1f})")
                    else:
                        st.warning(f"📊 Signal: {signal['ticker']} - {signal['action']} (Score: {combined:.1f})")

            elif msg_type == "execution":
                st.info(f"⚡ Trade Executed: {msg.get('ticker')} - {msg.get('status')}")

            elif msg_type == "exit_signal":
                st.error(f"🚪 Exit Signal: {msg.get('ticker')} - {msg.get('reason')}")

            elif msg_type == "heartbeat":
                market_status = msg.get("market_status", "unknown")
                if market_status == "open":
                    st.caption(f"💓 Market Open - Monitoring...")
                else:
                    st.caption(f"💤 Market Closed")

# Auto-refresh every 10 seconds
time.sleep(10)
st.rerun()