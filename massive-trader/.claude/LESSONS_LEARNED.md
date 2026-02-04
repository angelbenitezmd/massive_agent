# Lessons Learned - Trading Bot Development

## Session: 2026-02-03

### Issue 1: Hardcoded Ticker Lists
**Problem**: Auto-trade loop used hardcoded 7 tickers instead of configured watchlist.
**Location**: `backend/app/main.py` - `get_best_trading_signal()`
**Fix**: Use `settings.watchlist` from config instead of hardcoded list.
**Lesson**: Always use configuration values, never hardcode lists that should be configurable.

### Issue 2: Disconnected Signal Sources
**Problem**: UI showed BUY signals from `/api/scan/watchlist` (sentiment-based), but auto-trade used `/api/trading/best-signal` (momentum+AI combined) - different scoring systems led to signals in UI not being traded.
**Fix**: Modified auto-trade to first check `scan_watchlist()` for BUY opportunities before falling back to best-signal.
**Lesson**: Ensure the trading logic uses the SAME signals the user sees in the UI. Consistency between display and execution is critical.

### Issue 3: HOLD Signals Rejected
**Problem**: Signals scoring 60-70 produced action="HOLD" which was silently rejected.
**Fix**: Accept both BUY and HOLD actions when score >= 60.
**Lesson**: Don't reject potentially good trades just because the action label is "HOLD" - the score is what matters.

### Issue 4: Python 3.9 F-String Compatibility
**Problem**: `macro_agent.py` had f-strings with `\n` inside expressions, which Python 3.9 doesn't support.
**Location**: Lines 188-192
**Fix**: Use `chr(10)` instead of `\n` inside f-string expressions, or extract to variables.
**Lesson**: When targeting Python 3.9, avoid backslashes in f-string expressions.

### Issue 5: Format String Type Errors
**Problem**: `score:.1f` format specifier failed when score was None or non-numeric.
**Fix**: Always cast to float before formatting: `float(score):.1f`
**Lesson**: Always validate/cast types before string formatting, especially with values from dictionaries.

### Issue 6: Signal Reasoning Could Be None
**Problem**: `signal.get("reasoning", "")[:200]` could fail if reasoning was explicitly None.
**Fix**: Use `(signal.get("reasoning") or "")[:200]` to handle None values.
**Lesson**: Default values in `.get()` don't protect against explicit None values.

### Issue 7: Port Conflicts on Restart
**Problem**: Backend restarts failed with "address already in use" due to zombie processes.
**Fix**: Kill processes on port before starting: `lsof -ti :8000 | xargs kill -9`
**Lesson**: Always ensure clean port state before starting servers.

---

## Architecture Notes

### Signal Flow (After Fixes)
1. `auto_trade_loop()` runs every 60s when market is open
2. First checks `scan_watchlist()` for BUY opportunities (score >= 70)
3. If found, uses that signal for trading
4. Falls back to `get_best_trading_signal()` if no scan BUY signals
5. Executes if: score >= 60 AND action in [BUY, HOLD] AND no existing position

### Two Scoring Systems
1. **Scan endpoints** (`/api/scan/*`): Pure Benzinga sentiment score
2. **Best-signal endpoint**: Combined momentum (50%) + AI sentiment (50%)

Both should be considered for trading opportunities.

### Key Configuration
- `TRADING_MIN_SIGNAL_SCORE`: Minimum score to trade (default 50, auto-trade uses max(60, this))
- `WATCHLIST_TICKERS`: Comma-separated list of tickers to scan
- Auto-trade checks top 20 tickers from watchlist

---

### Issue 8: No Automatic Profit Taking / Slow Loss Cutting
**Problem**: Positions were held too long. Emergency stop at -10% was too late. No auto profit taking. Signals don't last forever but positions were held indefinitely.
**Location**: `backend/app/services/position_manager.py` - `_check_simple_rules()`
**Fix**: Implemented aggressive exit rules:

**Loss Protection (Cut losers fast):**
- Emergency stop: -5% (was -10%)
- Quick exit: -3% loss after 30 minutes

**Profit Taking (Don't let winners become losers):**
- Auto take profit at +5%
- Auto-activate trailing stop at +2% profit
- Tighter 2% trailing stop (was 3%)

**Time-Based Exits (Signals don't last forever):**
- Force exit after 4 hours if not profitable
- Force exit after 1 day regardless (day trading style)
- Monitor/warn at 2 hours

**Lesson**: Day trading / momentum trading requires aggressive exits. Signals have a limited lifespan - entry timing matters but so does exit timing. Don't let winners turn into losers, and cut losers quickly.
