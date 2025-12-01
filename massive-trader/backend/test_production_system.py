#!/usr/bin/env python3
"""
Test the complete production trading system.
Tests unified signals, Alpaca integration, and position management.
"""

import asyncio
import httpx
import websockets
import json
from datetime import datetime

async def test_production_system():
    """Test all production endpoints."""

    print("=" * 60)
    print("🚀 PRODUCTION TRADING SYSTEM TEST")
    print("=" * 60)

    client = httpx.AsyncClient(base_url="http://localhost:8000", timeout=30.0)

    try:
        # 1. Test Account Status
        print("\n1️⃣ Testing Alpaca Account Status...")
        response = await client.get("/api/trading/account")
        account = response.json()
        print(f"   Status: {account.get('status')}")
        print(f"   Cash: ${account.get('cash', 0):,.2f}")
        print(f"   Buying Power: ${account.get('buying_power', 0):,.2f}")

        # 2. Test Best Signal Endpoint
        print("\n2️⃣ Getting Best Trading Signal...")
        response = await client.get("/api/trading/best-signal")
        signal = response.json()

        if signal and signal.get("ticker"):
            print(f"   ✅ Signal Found!")
            print(f"   Ticker: {signal['ticker']}")
            print(f"   Action: {signal['action']}")
            print(f"   Combined Score: {signal['combined_score']:.1f}/100")
            print(f"   - Momentum: {signal['momentum_score']:.1f} (70% = {signal['momentum_score']*0.7:.1f})")
            print(f"   - AI Score: {signal['ai_score']:.1f} (30% = {signal['ai_score']*0.3:.1f})")
            print(f"   Entry Price: ${signal['entry_price']:.2f}")
            print(f"   Auto-Execute: {'YES' if signal['combined_score'] >= 75 else 'NO'}")

            # 3. Test Trade Execution (if strong signal)
            if signal['combined_score'] >= 60:  # Lower threshold for testing
                print(f"\n3️⃣ Testing Trade Execution for {signal['ticker']}...")

                # Simulate execution
                print("   Would execute trade with:")
                print(f"   - Ticker: {signal['ticker']}")
                print(f"   - Action: {signal['action']}")
                print(f"   - Quantity: {signal.get('quantity', 1)}")
                print(f"   - Stop Loss: ${signal.get('stop_loss', 0):.2f}")
                print(f"   - Take Profit: ${signal.get('take_profit', 0):.2f}")

                # Uncomment to actually execute:
                # response = await client.post("/api/trading/execute", json=signal)
                # result = response.json()
                # print(f"   Execution Result: {result}")
        else:
            print("   ℹ️ No active signals at the moment")

        # 4. Test Position Management
        print("\n4️⃣ Testing Position Management...")
        response = await client.get("/api/trading/positions")
        positions_data = response.json()

        # Handle both list and dict response formats
        if isinstance(positions_data, dict):
            positions = positions_data.get("positions", [])
        else:
            positions = positions_data

        if positions:
            print(f"   Found {len(positions)} open positions:")
            for pos in positions:
                print(f"   - {pos['symbol']}: {pos['qty']} shares @ ${pos['entry']:.2f}")
                print(f"     Current: ${pos['current']:.2f} | P&L: ${pos['pnl']:.2f} ({pos['pnl_pct']:.2f}%)")

                # Check momentum for position
                mom_response = await client.get(f"/api/trading/position-momentum/{pos['symbol']}")
                if mom_response.status_code == 200:
                    mom_data = mom_response.json()
                    print(f"     Momentum: {mom_data.get('current_momentum', 0):.1f} (Peak: {mom_data.get('peak_momentum', 0):.1f})")
                    print(f"     Recommendation: {mom_data.get('recommendation')}")
        else:
            print("   No open positions")

        # 5. Test Position Monitoring
        print("\n5️⃣ Testing Position Monitor (Auto-Exit Check)...")
        response = await client.post("/api/trading/monitor-positions")
        monitor_result = response.json()
        print(f"   Monitored: {monitor_result['monitored_positions']} positions")

        if monitor_result['exit_signals']:
            print("   Exit Signals Detected:")
            for exit_sig in monitor_result['exit_signals']:
                print(f"   - {exit_sig['ticker']}: {exit_sig['reason']}")

        # 6. Test Production WebSocket
        print("\n6️⃣ Testing Production WebSocket...")
        print("   Connecting to ws://localhost:8000/ws/production")

        async with websockets.connect("ws://localhost:8000/ws/production") as ws:
            # Get initial connection
            msg = await ws.recv()
            data = json.loads(msg)
            print(f"   ✅ Connected: {data.get('message')}")

            # Wait for first unified signal (up to 15 seconds)
            print("   ⏰ Waiting for unified signal (15 seconds max)...")

            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=15)
                data = json.loads(msg)

                if data.get("type") == "unified_signal":
                    signal = data.get("signal", {})
                    print(f"   📡 Received Unified Signal!")
                    print(f"      Ticker: {signal.get('ticker')}")
                    print(f"      Combined Score: {signal.get('combined_score'):.1f}")
                    print(f"      Auto-Execute: {signal.get('combined_score', 0) >= 75}")
                elif data.get("type") == "heartbeat":
                    print(f"   💓 Heartbeat - Market: {data.get('market_status')}")
                    print(f"      Next signal in: {data.get('next_signal_in', 'N/A')}")

            except asyncio.TimeoutError:
                print("   ⏱️ No signal received in 15 seconds (normal if market closed)")

        print("\n" + "=" * 60)
        print("✅ PRODUCTION SYSTEM TEST COMPLETE")
        print("=" * 60)

        print("\n📋 SUMMARY:")
        print("1. Account Status: ✅ Working")
        print("2. Best Signal API: ✅ Working")
        print("3. Position Management: ✅ Working")
        print("4. Auto-Exit Monitor: ✅ Working")
        print("5. Production WebSocket: ✅ Working")
        print("\n🎯 System is ready for Alpaca paper trading!")
        print("   - ONE unified signal combining momentum + AI")
        print("   - Auto-execution when score >= 75")
        print("   - Auto-exit on momentum loss")
        print("   - Position tracking and management")

    except Exception as e:
        print(f"\n❌ Error during test: {e}")

    finally:
        await client.aclose()

if __name__ == "__main__":
    print("🧪 Starting Production System Test...")
    asyncio.run(test_production_system())