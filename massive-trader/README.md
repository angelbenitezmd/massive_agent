# AI Trading Intelligence System with Benzinga & Alpaca

## ⚠️ CRITICAL SAFETY NOTICE

**This system defaults to PAPER TRADING (simulation) mode.** To use live trading:
1. You must explicitly set `ALPACA_ENV=live` in your `.env` file
2. Restart all services after changing the environment
3. **LIVE TRADING INVOLVES REAL MONEY AND RISK OF LOSS**

## 🏗️ System Architecture

### Core Components

1. **Benzinga Data Pipeline**: Real-time market intelligence
   - News, earnings, guidance, ratings, analyst insights
   - RESTful API wrapper with full parameter support

2. **Multi-Agent AI System** (LangChain + Claude Opus):
   - News Agent: Sentiment & urgency analysis
   - Earnings Agent: Surprise & trend evaluation
   - Consensus Agent: Rating distribution analysis
   - Guidance Agent: Forward-looking assessment
   - Risk Agent: Volatility & conflict detection
   - Strategist Agent: Unified decision making

3. **Hybrid Trading Mode**:
   - Event-driven: React to breaking news/ratings
   - Interval-based: Regular portfolio rebalancing (60s default)

4. **Risk Management Engine**:
   - Position sizing (Kelly Criterion simplified)
   - Daily drawdown limits (5% default)
   - Per-trade risk limits (1% default)
   - Correlation exposure tracking

5. **Alpaca Integration**:
   - Paper trading by default
   - Live trading requires explicit configuration
   - Market/limit/bracket order support

## 📁 Project Structure

```
massive-trader/
├── backend/
│   ├── app/
│   │   ├── api/            # FastAPI routers
│   │   ├── core/           # Config, HTTP client, logging
│   │   ├── models/         # Pydantic models
│   │   ├── services/       # Benzinga, Alpaca, Risk Engine
│   │   ├── agents/         # AI multi-agent system
│   │   └── main.py         # FastAPI application
│   ├── requirements.txt
│   └── .env.example
├── frontend/               # Next.js 15 visualization
├── pine/                   # TradingView indicator
└── README.md
```

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+ (for frontend)
- API Keys:
  - Benzinga/Massive API key
  - Alpaca API credentials (paper or live)
  - Anthropic API key (for Claude Opus)

### Backend Setup

1. **Clone and navigate to project:**
```bash
cd massive-trader/backend
```

2. **Create Python virtual environment:**
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

4. **Configure environment:**
```bash
cp .env.example .env
# Edit .env with your API keys
```

5. **Start FastAPI server:**
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`
API docs at `http://localhost:8000/docs`

### Running the Trading Loop

In a separate terminal:
```bash
cd backend
source venv/bin/activate
python -m app.apps.trading_loop
```

This starts the hybrid orchestrator that:
- Monitors for market events
- Runs interval-based analysis
- Executes trades via Alpaca

## 🔑 Configuration

### Essential Environment Variables

```env
# Benzinga API
BENZINGA_BASE_URL=https://api.massive.xyz
BENZINGA_API_KEY=your_key_here

# Alpaca Trading (CRITICAL)
ALPACA_ENV=paper  # Change to "live" only if you want real trading
ALPACA_API_KEY_ID=your_key_id
ALPACA_API_SECRET_KEY=your_secret

# AI/LLM
ANTHROPIC_API_KEY=your_claude_key

# Risk Parameters
TRADING_DEFAULT_MAX_POSITION_RISK=0.01  # 1% per trade
TRADING_DAILY_MAX_DRAWDOWN=0.05        # 5% daily limit
TRADING_MIN_SIGNAL_SCORE=70            # Minimum score to trade (strict 70+)
```

### Auto-Trade Exit Rules

The system uses aggressive exit rules to protect capital:

| Rule | Threshold | Action |
|------|-----------|--------|
| Take Profit | +5% | Close position |
| Emergency Stop | -5% | Close immediately |
| Quick Stop | -3% after 30min | Close (bad trade) |
| Auto Trailing | +2% profit | Activate 2% trail |
| Time Exit | 4 hours, not profitable | Close |
| Day Limit | 1 day held | Close regardless |

## 📊 TradingView Integration

1. Open TradingView and create a new Pine Script
2. Copy contents of `pine/ai_strategist_indicator.pine`
3. Add to chart
4. Configure alert webhooks to send signals to your backend

Webhook format:
```json
{
  "action": "BUY",
  "ticker": "AAPL",
  "price": "150.25",
  "score": "75.5"
}
```

## 🔒 Safety Features

1. **Paper Trading Default**: System starts in paper mode unless explicitly changed
2. **Position Limits**: Max 1% risk per trade, 10% per position
3. **Daily Drawdown**: Stops trading if down 5% for the day
4. **Signal Validation**: Minimum score threshold before trading
5. **Correlation Checks**: Warns about concentrated positions

## 📈 Hybrid Trading Mode

The system operates in two modes simultaneously:

### Event-Driven Mode
- Triggered by: Breaking news, earnings releases, rating changes
- Response time: Near real-time (seconds)
- Use case: Capture momentum from catalysts

### Interval Mode
- Frequency: Every 60 seconds (configurable)
- Actions: Rebalance, adjust stops, exit positions
- Use case: Systematic portfolio management

## 🧪 Testing with Paper Trading

1. Ensure `ALPACA_ENV=paper` in `.env`
2. Start the system as described above
3. Monitor logs for trade signals and executions
4. Check Alpaca paper account dashboard for positions

## ⚡ Performance Optimization

- **Async Everything**: All API calls are asynchronous
- **Connection Pooling**: Reuses HTTP connections
- **Caching**: Settings cached with LRU
- **Batch Processing**: Groups API calls when possible

## 🐛 Debugging

Enable debug logging:
```env
LOG_LEVEL=DEBUG
```

Check logs:
```bash
tail -f trading_system.log
```

## 📝 API Endpoints

### Benzinga Data
- `GET /api/news` - Real-time news
- `GET /api/earnings` - Earnings calendar
- `GET /api/guidance` - Corporate guidance
- `GET /api/consensus/{ticker}` - Consensus ratings
- `GET /api/ratings` - Analyst ratings

### Trading Operations
- `POST /api/trade/signal` - Submit manual signal
- `GET /api/trade/positions` - Current positions
- `DELETE /api/trade/position/{ticker}` - Close position

### WebSocket Streams
- `ws://localhost:8001/ws/signals` - Real-time signals
- `ws://localhost:8001/ws/trades` - Trade executions
- `ws://localhost:8001/ws/status` - System status

## 🚨 Switching to Live Trading

**WARNING: LIVE TRADING RISKS REAL MONEY**

1. Get live Alpaca credentials
2. Update `.env`:
   ```env
   ALPACA_ENV=live  # ⚠️ DANGER ZONE
   ```
3. Restart all services
4. Monitor carefully with small positions initially

## 📚 Key Files Reference

| File | Purpose |
|------|---------|
| `backend/app/core/config.py` | Configuration management |
| `backend/app/services/benzinga_client.py` | Benzinga API wrapper |
| `backend/app/services/alpaca_client.py` | Alpaca trading client |
| `backend/app/services/risk_engine.py` | Risk management |
| `backend/app/agents/strategist_agent.py` | AI decision making |
| `pine/ai_strategist_indicator.pine` | TradingView indicator |

## 🤝 Contributing

1. Always test in paper mode first
2. Add comprehensive error handling
3. Document risk parameters
4. Include unit tests for critical paths

## 📄 License

This software is provided as-is for educational purposes. Trading involves risk of loss. The authors assume no responsibility for trading losses.

## 🆘 Support

- Check logs first: `tail -f trading_system.log`
- Verify API keys are correct
- Ensure market hours for trading
- Paper account may have delayed data

---

**Remember: Start with paper trading. Only move to live when you fully understand the system and risks involved.**