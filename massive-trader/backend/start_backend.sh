#!/bin/bash
cd /Users/angelbenitez/Desktop/massive/massive-trader/backend
source venv/bin/activate
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
