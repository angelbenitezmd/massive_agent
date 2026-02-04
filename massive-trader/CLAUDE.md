# Claude Code Context - Massive Trader

## Project Overview
AI-powered paper trading system with multi-agent analysis, Benzinga data integration, and Alpaca execution.

## Tech Stack
- **Backend**: Python 3.9, FastAPI, uvicorn
- **Frontend**: Next.js 15, React, TypeScript
- **APIs**: Alpaca (trading), Benzinga (market data), Anthropic/OpenAI (LLM analysis)

## Running the App
```bash
# Backend (port 8000)
cd backend && source .venv/bin/activate && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend (port 3000)
cd frontend && npm run dev
```

## Key Files
- `backend/app/main.py` - Main FastAPI app, auto-trade loop, signal endpoints
- `backend/app/core/config_simple.py` - Settings and watchlist config
- `backend/app/services/alpaca_trader.py` - Trade execution
- `backend/app/services/position_manager.py` - Position monitoring and exits
- `backend/.env` - API keys and configuration

## Auto-Trade Flow
1. Scans configured watchlist every 60s (when market open)
2. Checks for BUY signals (score >= 70) from scan
3. Executes if no existing position in that ticker
4. Registers with PositionManager for exit tracking

## Common Issues
See `.claude/LESSONS_LEARNED.md` for documented issues and fixes.

## Environment Variables
- `ALPACA_API_KEY_ID` / `ALPACA_API_SECRET_KEY` - Alpaca credentials
- `BENZINGA_API_KEY` - Benzinga/Massive API key
- `WATCHLIST_TICKERS` - Comma-separated ticker list
- `TRADING_MIN_SIGNAL_SCORE` - Minimum score threshold (default 50)
