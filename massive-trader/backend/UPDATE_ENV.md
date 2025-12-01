# Massive API Configuration Guide

## Update your .env file with:

```bash
# Massive API (provides Benzinga data)
BENZINGA_BASE_URL=https://api.massive.com  # Or the actual Massive API URL
BENZINGA_API_KEY=your_actual_massive_api_key_here

# Common Massive API endpoints might be:
# - https://api.massive.com
# - https://massive-api.com
# - https://api.massive.io
# - Or a custom endpoint provided by Massive
```

## To update your .env:

1. Edit the .env file:
   ```bash
   nano .env
   # or
   vim .env
   ```

2. Replace the placeholder values with your actual Massive API credentials

3. Save the file

4. The app will automatically reload with the new configuration

## Test the connection:

Once updated, test with:
```bash
curl "http://localhost:8000/api/news?ticker=AAPL&limit=3"
```

## Massive API Features Available:

Through the Massive API, you can access:
- ✅ Benzinga real-time news
- ✅ Earnings calendar
- ✅ Analyst ratings
- ✅ Corporate guidance
- ✅ Consensus ratings
- ✅ Analyst insights
- ✅ Firm details

All Benzinga endpoints are proxied through Massive's infrastructure.