# 🚀 Quick Start Guide - AI Trading System

## Prerequisites Checklist

- [ ] Python 3.11+ installed
- [ ] Benzinga/Massive API key
- [ ] Alpaca account (paper trading recommended)
- [ ] Anthropic API key for Claude Opus

## 5-Minute Setup

### 1. Initial Setup (First Time Only)

```bash
# Clone or navigate to project
cd massive-trader/backend

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Setup environment
cp .env.example .env
```

### 2. Configure API Keys

Edit `.env` file:

```env
# CRITICAL - Add your keys here
BENZINGA_API_KEY=your_benzinga_key
ALPACA_API_KEY_ID=your_alpaca_key_id
ALPACA_API_SECRET_KEY=your_alpaca_secret
ANTHROPIC_API_KEY=your_anthropic_key

# SAFETY - Keep this as 'paper' for testing
ALPACA_ENV=paper
```

### 3. Start the System

```bash
# Terminal 1 - Start API server
chmod +x run_dev.sh
./run_dev.sh

# Terminal 2 - Start trading loop (optional)
source venv/bin/activate
python -m app.apps.trading_loop
```

### 4. Verify System

- API Docs: http://localhost:8000/docs
- Health Check: http://localhost:8000/health
- System Status: http://localhost:8000/status

> **Security note (local use only)**  
> This app is designed to run on your local machine. The backend API has **no authentication**; do **not** expose it directly to the public internet or untrusted networks.

## Key Endpoints to Test

### Get Market News
```bash
curl http://localhost:8000/api/news?tickers=AAPL&limit=5
```

### Check System Status
```bash
curl http://localhost:8000/status
```

### WebSocket Test (JavaScript Console)
```javascript
const ws = new WebSocket('ws://localhost:8001/ws/signals');
ws.onmessage = (event) => console.log(JSON.parse(event.data));
```

## Pine Script Setup (TradingView)

1. Open TradingView
2. Pine Editor → New → Paste contents of `pine/ai_strategist_indicator.pine`
3. Add to Chart
4. Configure alerts as needed

## Safety Reminders

⚠️ **DEFAULT IS PAPER TRADING** - Keep `ALPACA_ENV=paper` unless you want real trading

✅ **Test First** - Always test strategies in paper mode before going live

🔒 **Risk Limits** - System enforces 1% per trade, 5% daily drawdown by default

## Common Issues

### "No module named 'langchain'"
```bash
pip install -r requirements.txt
```

### "API key not found"
Check your `.env` file has all required keys

### "Connection refused"
Make sure the FastAPI server is running on port 8000

## Next Steps

1. **Monitor Logs**: `tail -f trading_system.log`
2. **Test Signals**: Use paper trading to verify system behavior
3. **Adjust Parameters**: Edit `.env` for risk settings
4. **Add Watchlist**: Update `WATCHLIST_TICKERS` in `.env`

## Support

- Logs: `backend/trading_system.log`
- API Docs: http://localhost:8000/docs
- Check `.env` configuration
- Verify market hours for trading

---

**Remember: Start with paper trading. Real trading = real risk!**