#!/usr/bin/env python3
"""Test Alpaca paper trading connection."""

import os
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient

# Load environment variables
load_dotenv()

# Get credentials from environment
api_key = os.getenv("ALPACA_API_KEY_ID")
secret_key = os.getenv("ALPACA_API_SECRET_KEY")

print("Testing Alpaca paper trading connection...")
print(f"API Key: {api_key[:10] if api_key else 'Not found'}...")
print(f"Secret Key: {'*' * 10 if secret_key else 'Not found'}...")

if not api_key or not secret_key:
    print("❌ API keys not found in environment")
    exit(1)

try:
    # Create client with paper=True for paper trading
    client = TradingClient(
        api_key=api_key,
        secret_key=secret_key,
        paper=True
    )

    # Get account info
    account = client.get_account()

    print("\n✅ Successfully connected to Alpaca paper trading!")
    print(f"Account Status: {account.status}")
    print(f"Account Number: {account.account_number}")
    print(f"Buying Power: ${float(account.buying_power):,.2f}")
    print(f"Cash: ${float(account.cash):,.2f}")
    print(f"Portfolio Value: ${float(account.equity):,.2f}")

    # Get positions
    positions = client.get_all_positions()
    print(f"\nOpen Positions: {len(positions)}")
    for pos in positions[:5]:  # Show first 5 positions
        print(f"  - {pos.symbol}: {pos.qty} shares @ ${float(pos.avg_entry_price):.2f}")

except Exception as e:
    print(f"\n❌ Error connecting to Alpaca: {e}")
    print("\nPlease check:")
    print("1. Your API keys are correct")
    print("2. The keys are for paper trading (not live)")
    print("3. Your paper trading account is active")