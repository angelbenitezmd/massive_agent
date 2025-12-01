# Streamlit Frontend for AI Trading Intelligence System

## How to Run

1. **Install dependencies:**
```bash
cd frontend
pip install -r requirements.txt
```

2. **Ensure backend is running:**
```bash
# In backend directory
cd ../
source venv/bin/activate
python -m app.main_simple
```

3. **Start Streamlit app:**
```bash
# In frontend directory
streamlit run streamlit_app.py --server.port 8501
```

4. **Access the UI:**
Open browser to http://localhost:8501

## Configuration

- Backend URL: Default is `http://localhost:8000`, configurable in sidebar
- The app will automatically connect to your running FastAPI backend
- All API endpoints are accessible through the tabbed interface

## Features

- **Overview Tab**: System health, API status, watchlist summary
- **News Tab**: Real-time market news by ticker
- **Earnings Tab**: Upcoming earnings calendar
- **Ratings Tab**: Analyst ratings and price targets
- **Consensus Tab**: Aggregated analyst consensus
- **Sentiment Tab**: AI-powered sentiment scoring
- **Scans Tab**: Watchlist, Universe, and Spicy ticker scanning
- **Streams Tab**: WebSocket connections for live data

## Notes

- Backend must be running on specified URL (default: http://localhost:8000)
- WebSocket connections available for real-time updates
- Data cached for 30 seconds to reduce API calls
- Error messages displayed when backend unavailable