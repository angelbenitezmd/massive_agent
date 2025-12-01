# Signalist AI Day Trader

A modern, Signalist-style AI-powered day trading dashboard built with Next.js 15, Shadcn UI, and Tailwind CSS.

## Features

- **Real-time Market Data**: Live quotes, charts, and technical indicators
- **AI-Powered Analysis**: Multi-agent system for trading decisions
  - News/Sentiment Agent
  - Earnings Agent
  - Technical Momentum Agent
  - Consensus & Risk Agent
- **Benzinga Integration**: News, earnings, and analyst ratings
- **Alpaca Trading**: Paper and live trading support
- **Risk Management**: Circuit breakers, position sizing, daily loss limits
- **Dark Theme**: Modern, trader-friendly UI

## Tech Stack

- **Framework**: Next.js 15 (App Router)
- **UI Components**: Shadcn UI + Radix Primitives
- **Styling**: Tailwind CSS
- **Data Fetching**: TanStack Query (React Query)
- **Charts**: Recharts
- **TypeScript**: Full type safety

## Getting Started

### Prerequisites

- Node.js 18+
- Backend API running on port 8000 (see `../backend/`)

### Installation

```bash
# Install dependencies
npm install

# Copy environment file
cp .env.local.example .env.local

# Start development server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) to view the dashboard.

### Environment Variables

```env
# Backend API URL
NEXT_PUBLIC_API_URL=http://localhost:8000
BACKEND_URL=http://localhost:8000
```

## Project Structure

```
frontend/
├── app/                    # Next.js App Router
│   ├── api/               # API routes
│   ├── globals.css        # Global styles
│   ├── layout.tsx         # Root layout
│   ├── page.tsx           # Main dashboard
│   └── providers.tsx      # React Query provider
├── components/
│   ├── dashboard/         # Dashboard components
│   │   ├── header.tsx     # Header with search & controls
│   │   ├── market-snapshot.tsx   # Price, chart, technicals
│   │   ├── news-panel.tsx        # Benzinga news
│   │   ├── earnings-panel.tsx    # Earnings data
│   │   ├── ai-agents-panel.tsx   # AI agent signals
│   │   ├── trade-decision-panel.tsx  # Trade recommendations
│   │   └── risk-panel.tsx        # Account & risk status
│   └── ui/                # Shadcn UI components
├── hooks/
│   └── use-trading-data.ts  # Data fetching hooks
├── lib/
│   ├── api.ts             # API client
│   └── utils.ts           # Utility functions
└── types/
    └── index.ts           # TypeScript types
```

## Dashboard Sections

### Header
- App title with environment badge (Paper/Live)
- Ticker search with watchlist autocomplete
- Run Analysis button
- Auto-refresh and Auto-trade toggles

### Market Snapshot
- Current price with change percentage
- Intraday price chart
- Technical indicators (RSI, MACD, Moving Averages)

### News Panel
- Real-time Benzinga news for selected ticker
- Sentiment tags and timestamps

### Earnings Panel
- Recent earnings with EPS/Revenue surprise
- Importance scoring

### AI Agents Panel
- Individual agent cards showing:
  - Direction (Bullish/Bearish/Neutral)
  - Confidence score
  - Reasoning explanation

### Trade Decision Panel
- Consensus recommendation (BUY/SELL/HOLD/NO_BUY)
- Position sizing with entry, stop-loss, take-profit
- Execute Trade button with confirmation dialog

### Risk & Account Panel
- Circuit breaker status
- Daily P&L and drawdown
- Account equity and buying power
- Current positions

## API Integration

The frontend connects to the FastAPI backend on port 8000:

- `GET /status` - System status
- `GET /api/quote/{ticker}` - Real-time quote
- `GET /api/news?ticker=X` - Benzinga news
- `GET /api/earnings?ticker=X` - Earnings data
- `GET /api/sentiment/{ticker}` - AI sentiment
- `GET /api/trading/account` - Alpaca account
- `GET /api/trading/positions` - Open positions
- `POST /api/trading/execute` - Execute trade

## Development

```bash
# Development with hot reload
npm run dev

# Type checking
npx tsc --noEmit

# Build for production
npm run build

# Start production server
npm start
```

## License

MIT
