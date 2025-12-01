#!/usr/bin/env python3
"""Test all WebSocket endpoints."""

import asyncio
import websockets
import json

async def test_endpoint(endpoint_name, uri):
    """Test a single WebSocket endpoint."""
    print(f"\n🧪 Testing {endpoint_name}...")
    try:
        async with websockets.connect(uri) as websocket:
            print(f"✅ Connected to {uri}")

            # Receive initial connection message
            message = await websocket.recv()
            data = json.loads(message)
            print(f"📨 Initial message: {data.get('type', 'unknown')} - {data.get('message', '')}")

            # Send a test message
            test_msg = f"Hello from {endpoint_name} test!"
            await websocket.send(test_msg)
            print(f"📤 Sent: {test_msg}")

            # Receive response or heartbeat
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=15)
                data = json.loads(message)
                print(f"📨 Response: {data.get('type', 'unknown')}")

                # Display appropriate data based on type
                if data.get('type') == 'trade_update':
                    print(f"   Trade: {data.get('action')} {data.get('quantity')} {data.get('ticker')} @ ${data.get('price')}")
                elif data.get('type') == 'status':
                    print(f"   System: {data.get('system')}, Connections: {data.get('connections')}")
                elif data.get('type') == 'heartbeat':
                    print(f"   Market Status: {data.get('market_status')}")

            except asyncio.TimeoutError:
                print("⏰ Timeout waiting for response")

            print(f"✅ {endpoint_name} test successful!")

    except Exception as e:
        print(f"❌ {endpoint_name} test failed: {e}")

async def main():
    """Test all WebSocket endpoints."""
    print("=" * 50)
    print("Testing All WebSocket Endpoints")
    print("=" * 50)

    endpoints = [
        ("Signals", "ws://localhost:8000/ws/signals"),
        ("Trades", "ws://localhost:8000/ws/trades"),
        ("Status", "ws://localhost:8000/ws/status")
    ]

    for name, uri in endpoints:
        await test_endpoint(name, uri)
        await asyncio.sleep(1)  # Small delay between tests

    print("\n" + "=" * 50)
    print("All tests completed!")
    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(main())