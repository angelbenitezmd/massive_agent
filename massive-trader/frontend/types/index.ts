// Market Data Types
export interface Quote {
  symbol: string;
  price: number;
  change: number;
  changePercent: number;
  volume: number;
  high: number;
  low: number;
  open: number;
  previousClose: number;
  timestamp: string;
}

export interface Bar {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Technicals {
  rsi: number | null;
  macd: {
    value: number | null;
    signal: number | null;
    histogram: number | null;
  };
  sma20: number | null;
  sma50: number | null;
  sma200: number | null;
  ema20: number | null;
  ema50: number | null;
  priceVsSma20?: "above" | "below";
  priceVsSma50?: "above" | "below";
  priceVsSma200?: "above" | "below";
}

// News Types
export interface NewsItem {
  id: string;
  headline: string;
  summary?: string;
  author?: string;
  source: string;
  url: string;
  publishedAt: string;
  symbols: string[];
  tags?: string[];
  sentiment?: "bullish" | "bearish" | "neutral";
}

// Earnings Types
export interface Earnings {
  symbol: string;
  fiscalQuarter: string;
  fiscalYear: number;
  reportDate: string;
  reportTime: "before" | "after" | "during";
  epsEstimate: number | null;
  epsActual: number | null;
  epsSurprise: number | null;
  epsSurprisePercent: number | null;
  revenueEstimate: number | null;
  revenueActual: number | null;
  revenueSurprise: number | null;
  revenueSurprisePercent: number | null;
  importance: number;
}

// AI Agent Types
export type Direction = "bullish" | "bearish" | "neutral";

export interface AgentSignal {
  agentName: string;
  direction: Direction;
  confidence: number;
  reasoning: string;
  timestamp: string;
}

export interface NewsAgentSignal extends AgentSignal {
  agentName: "News/Sentiment Agent";
  newsCount: number;
  keyHeadlines: string[];
}

export interface EarningsAgentSignal extends AgentSignal {
  agentName: "Earnings Agent";
  epsSurprise?: number;
  revenueSurprise?: number;
}

export interface TechnicalAgentSignal extends AgentSignal {
  agentName: "Technical Momentum Agent";
  rsi: number;
  macdSignal: "bullish" | "bearish" | "neutral";
  trendDirection: "up" | "down" | "sideways";
}

// Trade Decision Types
export type TradeAction = "BUY" | "SELL" | "HOLD" | "NO_BUY";

export interface TradeDecision {
  action: TradeAction;
  symbol: string;
  ticker?: string;
  quantity: number;
  entryPrice: number;
  stopLoss: number;
  takeProfit: number;
  confidence: number;
  reasoning: string;
  contributingAgents: string[];
  timestamp: string;
  // Score breakdown
  combinedScore?: number;
  aiScore?: number;
  momentumScore?: number;
  strategy?: string;
}

// Account & Risk Types
export type CircuitBreakerLevel = "GREEN" | "YELLOW" | "ORANGE" | "RED";

export interface Account {
  equity: number;
  cash: number;
  buyingPower: number;
  portfolioValue: number;
  dayTradeCount: number;
}

export interface Position {
  symbol: string;
  quantity: number;
  avgEntryPrice: number;
  currentPrice: number;
  marketValue: number;
  unrealizedPL: number;
  unrealizedPLPercent: number;
}

export interface RiskStatus {
  circuitBreaker: CircuitBreakerLevel;
  dailyPL: number;
  dailyPLPercent: number;
  tradesToday: number;
  maxDailyLoss: number;
  currentDrawdown: number;
}

// Dashboard State
export interface DashboardState {
  selectedTicker: string;
  autoRefresh: boolean;
  autoTrade: boolean;
  tradingMode: "paper" | "live";
}

// API Response Types
export interface AnalysisResponse {
  quote: Quote;
  technicals: Technicals;
  bars: Bar[];
  news: NewsItem[];
  earnings: Earnings[];
  agents: {
    news: NewsAgentSignal;
    earnings: EarningsAgentSignal;
    technical: TechnicalAgentSignal;
  };
  decision: TradeDecision;
  account: Account;
  positions: Position[];
  risk: RiskStatus;
}

export interface SystemStatus {
  backendConnected: boolean;
  alpacaConnected: boolean;
  benzingaConnected: boolean;
  tradingMode: "paper" | "live";
  lastUpdate: string;
}

// Trade History / Orders
export interface Order {
  id: string;
  symbol: string;
  side: "buy" | "sell";
  qty: number;
  filled_qty: number;
  type: string;
  status: string;
  filled_avg_price: number | null;
  submitted_at: string | null;
  filled_at: string | null;
  limit_price?: number | null;
  stop_price?: number | null;
  pnl?: number;
  pnl_pct?: number;
}

// Analyst Ratings
export interface AnalystRating {
  id: string;
  ticker: string;
  company_name: string;
  firm: string;
  analyst?: string;
  rating?: string;
  previous_rating?: string;
  rating_action?: "upgrades" | "downgrades" | "maintains" | "initiates_coverage_on" | "reiterates";
  price_target?: number;
  previous_price_target?: number;
  price_target_action?: "raises" | "lowers" | "maintains" | "announces" | "sets";
  date: string;
  importance?: number;
}
