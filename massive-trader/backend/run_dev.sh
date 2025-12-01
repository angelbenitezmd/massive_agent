#!/bin/bash

# Development run script for AI Trading System

echo "=========================================="
echo "AI Trading System - Development Mode"
echo "=========================================="

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install/update requirements
echo "Installing requirements..."
pip install -r requirements.txt

# Check for .env file
if [ ! -f ".env" ]; then
    echo "WARNING: .env file not found!"
    echo "Creating from .env.example..."
    cp .env.example .env
    echo "Please edit .env with your API keys before continuing"
    exit 1
fi

# Check trading mode
if grep -q "ALPACA_ENV=live" .env; then
    echo "⚠️⚠️⚠️ WARNING: LIVE TRADING MODE DETECTED ⚠️⚠️⚠️"
    echo "Real money will be at risk!"
    read -p "Are you sure you want to continue? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        echo "Exiting..."
        exit 1
    fi
else
    echo "✅ Paper trading mode (safe)"
fi

# Start the FastAPI server
echo "Starting FastAPI server..."
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --log-level info