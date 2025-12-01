#!/usr/bin/env python3
"""Test WebSocket connection to the backend."""

import asyncio
import websockets
import json

async def test_websocket():
    uri = "ws://localhost:8000/ws/signals"

    try:
        async with websockets.connect(uri) as websocket:
            print(f"✅ Connected to {uri}")

            # Receive initial connection message
            message = await websocket.recv()
            data = json.loads(message)
            print(f"📨 Received: {data}")

            # Send a test message
            await websocket.send("Hello from test client!")
            print("📤 Sent: Hello from test client!")

            # Receive echo response
            message = await websocket.recv()
            data = json.loads(message)
            print(f"📨 Received echo: {data}")

            # Wait for a heartbeat
            print("⏰ Waiting for heartbeat (30 seconds)...")
            message = await asyncio.wait_for(websocket.recv(), timeout=35)
            data = json.loads(message)
            print(f"💓 Received heartbeat: {data}")

            print("✅ WebSocket test successful!")

    except Exception as e:
        print(f"❌ WebSocket test failed: {e}")

if __name__ == "__main__":
    print("🧪 Testing WebSocket connection...")
    asyncio.run(test_websocket())