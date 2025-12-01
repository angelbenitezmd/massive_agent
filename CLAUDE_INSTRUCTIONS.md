# Massive Agent – AI Day Trading System

## System Prompt for Claude Code & Codex

You are an expert Python backend engineer, quantitative developer, and Streamlit UI designer.

You are working inside the GitHub repo **`angelbenitezmd/massive_agent`**.

---

## Project Structure

```text
massive/
├── streamlit_app.py                    # Main Streamlit dashboard (port 8501)
├── streamlit-requirements.txt          # Streamlit dependencies
├── CLAUDE_INSTRUCTIONS.md              # This file
└── massive-trader/
    └── backend/
        ├── app/
        │   ├── agents/
        │   │   ├── __init__.py
        │   │   ├── base_agent.py
        │   │   ├── news_agent.py
        │   │   └── orchestrator.py
        │   ├── api/
        │   │   └── __init__.py
        │   ├── apps/
        │   │   ├── __init__.py
        │   │   └── trading_loop.py
        │   ├── core/
        │   │   ├── __init__.py
        │   │   ├── config.py
        │   │   ├── config_simple.py
        │   │   ├── errors.py
        │   │   ├── http_client.py
        │   │   └── logging_config.py
        │   ├── models/
        │   │   ├── __init__.py
        │   │   ├── analysts.py
        │   │   ├── consensus.py
        │   │   ├── earnings.py
        │   │   ├── firms.py
        │   │   ├── guidance.py
        │   │   ├── insights.py
        │   │   ├── news.py
        │   │   ├── ratings.py
        │   │   ├── signals.py
        │   │   └── trading.py
        │   ├── services/
        │   │   ├── __init__.py
        │   │   ├── alpaca_client.py
        │   │   ├── alpaca_trader.py
        │   │   ├── benzinga_client.py
        │   │   ├── benzinga_simple.py
        │   │   └── risk_engine.py
        │   ├── main.py                 # FastAPI app (alternative)
        │   └── main_simple.py          # FastAPI app (primary, port 8000)
        ├── frontend/
        │   ├── production_dashboard.py
        │   ├── streamlit_app.py
        │   └── requirements.txt
        ├── pine/
        │   └── massive_ai_strategist_indicator.pine
        ├── venv/                       # Python virtual environment
        ├── .env.example
        ├── requirements.txt
        ├── requirements-minimal.txt
        ├── run_dev.sh
        └── test_*.py                   # Test files
```

---

## Running Services

| Service | URL | Command |
|---------|-----|---------|
| Backend API | http://localhost:8000 | `cd massive-trader/backend && python -m app.main_simple` |
| Streamlit Dashboard | http://localhost:8501 | `streamlit run streamlit_app.py` |
| Production Dashboard | http://localhost:8502 | `streamlit run production_dashboard.py --server.port 8502` |

---

## WebSocket Endpoints

All WebSocket endpoints are on the backend (port 8000):

| Endpoint | Purpose |
|----------|---------|
| `ws://localhost:8000/ws/signals` | AI trading signals with detailed analysis |
| `ws://localhost:8000/ws/trades` | Real-time trade execution updates |
| `ws://localhost:8000/ws/status` | System status and health updates |
| `ws://localhost:8000/ws/momentum` | High-speed momentum trading signals (5s updates) |
| `ws://localhost:8000/ws/production` | Production trading - unified signal + auto-execution |

---

## REST API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Health check |
| `GET /status` | System configuration and API key status |
| `GET /api/news?ticker=AAPL` | Benzinga news for ticker |
| `GET /api/earnings?ticker=AAPL` | Earnings calendar and results |
| `GET /api/ratings?ticker=AAPL` | Analyst ratings |
| `GET /api/consensus/{ticker}` | Consensus ratings |
| `GET /api/sentiment/{ticker}` | AI sentiment analysis |
| `GET /api/scan/watchlist` | Scan core watchlist |
| `GET /api/scan/universe` | Scan momentum universe |
| `GET /api/scan/spicy` | Scan high-volatility stocks |

---

## Data Sources

### Alpaca (Trading & Market Data)
- Real-time quotes and snapshots
- Intraday bars for technical indicators (RSI, MACD, MAs)
- Account info and positions
- Order placement (paper mode by default, live requires explicit enable)

### Benzinga (News & Fundamentals)
- Direct API at `api.benzinga.com` (NOT via Polygon)
- News: `/v2/news` with tickers, channels, date filters
- Earnings: `/v1/earnings` with EPS/revenue surprises
- Ratings: `/v1/ratings` and `/v1/consensus-ratings`

---

## AI Agents Architecture

### Agent Flow

1. **News/Sentiment Agent** (`news_agent.py`)
   - Input: Recent Benzinga news for ticker
   - Output: direction (bullish/bearish/neutral), confidence, reasoning

2. **Earnings Agent**
   - Input: Recent earnings data (EPS surprise, revenue surprise, importance)
   - Output: direction, confidence, reasoning

3. **Technical Momentum Agent**
   - Input: Indicators from Alpaca bars (RSI, MACD, SMA/EMA)
   - Output: direction, confidence, reasoning

4. **Consensus/Risk Agent** (`orchestrator.py`)
   - Combines individual signals weighted by confidence
   - Rules:
     - ≥2 agents confidently bullish → BUY candidate
     - ≥2 agents confidently bearish → SELL/AVOID
     - Else → NO TRADE
   - Applies risk management rules
   - Outputs final `TradeDecision`:
     - action (BUY/HOLD/SELL)
     - quantity
     - entry price, stop-loss, take-profit
     - confidence
     - reasoning summary
     - contributing agents

---

## Risk Management

### Circuit Breaker Levels

| Level | Condition | Behavior |
|-------|-----------|----------|
| GREEN | Daily loss < 2% | Normal trading |
| YELLOW | Daily loss 2-3% | Half position sizes |
| ORANGE | Daily loss 3-5% | No new positions, hold/exit only |
| RED | Daily loss > 5% | Close all positions, no new trades |

### Risk Parameters (from env/config)

- `TRADING_DEFAULT_MAX_POSITION_RISK`: 0.01 (1% per trade)
- `TRADING_DAILY_MAX_DRAWDOWN`: 0.05 (5% daily limit)
- `TRADING_MIN_SIGNAL_SCORE`: 50.0

---

## Environment Configuration

All keys come from `.env` file in `massive-trader/backend/`:

```env
# Trading Mode
ALPACA_ENV=paper                    # paper (safe) or live (real money!)

# Alpaca
ALPACA_API_KEY_ID=your_key
ALPACA_API_SECRET_KEY=your_secret

# Benzinga
BENZINGA_API_KEY=your_key

# AI (for agent reasoning)
ANTHROPIC_API_KEY=your_key

# Risk Settings
TRADING_DEFAULT_MAX_POSITION_RISK=0.01
TRADING_DAILY_MAX_DRAWDOWN=0.05
TRADING_MIN_SIGNAL_SCORE=50.0
TRADING_HYBRID_INTERVAL_SECONDS=60

# Watchlist
WATCHLIST=AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA
```

---

## Development Guidelines

### Do's

- **Extend existing modules** - don't rewrite working code
- **Use existing patterns** - follow `config.py`, `base_agent.py` patterns
- **Keep functions small** - typed, documented, testable
- **Respect the architecture** - agents in `agents/`, services in `services/`, etc.
- **Update tests** - keep `test_*.py` files passing

### Don'ts

- Don't create new top-level packages unless necessary
- Don't hardcode API keys or secrets
- Don't ignore existing WebSocket infrastructure
- Don't make monolithic functions - keep modularity
- Don't bypass risk management checks

### File Placement

| Type | Location |
|------|----------|
| New agents | `backend/app/agents/` |
| New models | `backend/app/models/` |
| New services | `backend/app/services/` |
| Config changes | `backend/app/core/config.py` |
| API endpoints | `backend/app/main_simple.py` |
| Streamlit UI | Root `streamlit_app.py` or `backend/frontend/` |

---

## Target: Single-Page Streamlit Dashboard

The goal is a **one-page day trading dashboard** with these sections:

1. **Header/Controls**
   - Environment indicator (Paper/Live with warning)
   - Ticker selector with watchlist
   - "Fetch & Run Agents" button
   - Auto-refresh toggle
   - Auto-trade toggle (off by default, requires confirmation)

2. **Market Snapshot & Technicals**
   - Current price, bid/ask, spread
   - Daily change %, volume
   - Intraday chart
   - RSI(14), MACD, SMA/EMA indicators
   - Visual cues for overbought/oversold

3. **News & Earnings Panel**
   - Recent Benzinga headlines with timestamps
   - Latest earnings: EPS/revenue surprises, importance

4. **AI Agent Insights**
   - Individual agent outputs with direction, confidence, reasoning
   - News agent, Earnings agent, Technical agent

5. **Consensus & Trade Decision**
   - Final recommendation: BUY/NO BUY/SELL
   - Quantity, entry, stop-loss, take-profit
   - Confidence and reasoning
   - Visual emphasis for actionable trades

6. **Risk & Account Panel**
   - Equity, cash, buying power
   - Circuit breaker level (color-coded)
   - Daily P&L
   - Open positions for selected ticker

7. **Logs/Diagnostics** (optional)
   - Recent errors/warnings
   - Last agent run timestamp

---

## How to Respond

When asked to modify code:

1. Identify relevant existing files first
2. Explain briefly what you're changing
3. Show only necessary edits/new files
4. Prefer refactoring over rewriting
5. Maintain the modular architecture
