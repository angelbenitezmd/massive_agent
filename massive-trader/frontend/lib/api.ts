import type {
  AnalysisResponse,
  Quote,
  NewsItem,
  Earnings,
  Technicals,
  AgentSignal,
  TradeDecision,
  Account,
  Position,
  RiskStatus,
  SystemStatus,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchAPI<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API Error: ${res.status} ${res.statusText} - ${text}`);
  }

  return res.json();
}

// System Status
export async function getSystemStatus(): Promise<SystemStatus> {
  try {
    const status = await fetchAPI<any>("/status");
    return {
      backendConnected: true,
      alpacaConnected: status.api_keys_configured?.alpaca || false,
      benzingaConnected: status.api_keys_configured?.benzinga || false,
      tradingMode: status.is_paper ? "paper" : "live",
      lastUpdate: new Date().toISOString(),
    };
  } catch (error) {
    return {
      backendConnected: false,
      alpacaConnected: false,
      benzingaConnected: false,
      tradingMode: "paper",
      lastUpdate: new Date().toISOString(),
    };
  }
}

// Quote & Market Data
export async function getQuote(ticker: string): Promise<Quote> {
  const data = await fetchAPI<any>(`/api/quote/${ticker}`);
  return {
    symbol: ticker,
    price: data.price || data.last || 0,
    change: data.change || 0,
    changePercent: data.change_percent || data.changePercent || 0,
    volume: data.volume || 0,
    high: data.high || 0,
    low: data.low || 0,
    open: data.open || 0,
    previousClose: data.previous_close || data.prevClose || 0,
    timestamp: data.timestamp || new Date().toISOString(),
  };
}

export async function getBars(
  ticker: string,
  timeframe: string = "1Min",
  limit: number = 100
): Promise<any[]> {
  return fetchAPI(`/api/bars/${ticker}?timeframe=${timeframe}&limit=${limit}`);
}

// News (supports global feed when ticker is omitted)
// For global news (no ticker), uses hours_back=1 for speed
export async function getNews(ticker?: string, limit: number = 15, hoursBack: number = 1): Promise<NewsItem[]> {
  const params = new URLSearchParams();
  if (ticker) {
    params.set("ticker", ticker);
    params.set("limit", limit.toString());
    params.set("days_back", "1");  // 1 day for ticker-specific
  } else {
    // Global news - limit to 1 hour and 15 items for speed
    params.set("limit", Math.min(limit, 15).toString());
    params.set("hours_back", hoursBack.toString());
  }

  const endpoint = `/api/news${params.toString() ? `?${params.toString()}` : ""}`;

  const response = await fetchAPI<any>(endpoint);
  // Benzinga returns { results: [...] }
  const data = response.results || response || [];
  if (!Array.isArray(data)) return [];
  return data.map((item: any) => ({
    id: item.id || item.benzinga_id?.toString?.() || item.url,
    headline: item.title || item.headline,
    summary: item.teaser || item.summary,
    author: item.author,
    source: item.source || "Benzinga",
    url: item.url,
    publishedAt: item.published || item.created || item.published_at || item.updated || item.last_updated,
    symbols: item.tickers || item.stocks?.map((s: any) => s.name) || item.symbols || (ticker ? [ticker] : []),
    tags: item.channels || item.tags || [],
    sentiment: item.sentiment,
  }));
}

// Earnings
export async function getEarnings(ticker: string): Promise<Earnings[]> {
  const response = await fetchAPI<any>(`/api/earnings?ticker=${ticker}`);
  // Benzinga returns { results: [...] }
  const data = response.results || response || [];
  if (!Array.isArray(data)) return [];
  return data.map((item: any) => ({
    symbol: item.ticker || ticker,
    fiscalQuarter: item.period || item.fiscal_quarter || "Q?",
    fiscalYear: item.period_year || item.fiscal_year || new Date().getFullYear(),
    reportDate: item.date || item.report_date,
    reportTime: item.time || item.report_time || "after",
    epsEstimate: item.eps_est || item.eps_estimate,
    epsActual: item.eps || item.eps_actual,
    epsSurprise: item.eps_surprise,
    epsSurprisePercent: item.eps_surprise_percent,
    revenueEstimate: item.revenue_est || item.revenue_estimate,
    revenueActual: item.revenue || item.revenue_actual,
    revenueSurprise: item.revenue_surprise,
    revenueSurprisePercent: item.revenue_surprise_percent,
    importance: item.importance || 3,
  }));
}

// AI Analysis - uses dashboard + best-signal endpoints for complete data
export async function runAnalysis(ticker: string): Promise<AnalysisResponse> {
  // Validate ticker before making API call
  if (!ticker || typeof ticker !== "string" || ticker.trim() === "") {
    throw new Error("Invalid ticker: ticker must be a non-empty string");
  }

  const normalizedTicker = ticker.trim().toUpperCase();

  try {
    // Fetch dashboard and best-signal in parallel
    const [dashboard, bestSignal] = await Promise.all([
      fetchAPI<any>(`/api/dashboard/${normalizedTicker}`),
      fetchAPI<any>(`/api/trading/best-signal`).catch(() => null),
    ]);

    // Transform dashboard response to expected format
    const agents = dashboard.consensus?.contributing_agents || {};

    // Use best-signal data if available and matches ticker
    const signal = bestSignal?.ticker === normalizedTicker ? bestSignal : null;

    // Transform technicals from backend format to frontend format
    const rawTechnicals = dashboard.market?.technicals || {};
    const currentPrice = dashboard.market?.quote?.last || dashboard.market?.quote?.price || 0;

    const technicals: Technicals = {
      rsi: rawTechnicals.rsi ?? null,
      macd: {
        value: rawTechnicals.macd ?? null,
        signal: rawTechnicals.macd_signal ?? null,
        histogram: rawTechnicals.macd_histogram ?? null,
      },
      sma20: rawTechnicals.sma_20 ?? null,
      sma50: rawTechnicals.sma_50 ?? null,
      sma200: rawTechnicals.sma_200 ?? null,
      ema20: rawTechnicals.ema_20 ?? null,
      ema50: rawTechnicals.ema_50 ?? null,
      // Calculate price vs SMA relationships
      priceVsSma20: rawTechnicals.sma_20 && currentPrice
        ? (currentPrice > rawTechnicals.sma_20 ? "above" : "below")
        : undefined,
      priceVsSma50: rawTechnicals.sma_50 && currentPrice
        ? (currentPrice > rawTechnicals.sma_50 ? "above" : "below")
        : undefined,
      priceVsSma200: rawTechnicals.sma_200 && currentPrice
        ? (currentPrice > rawTechnicals.sma_200 ? "above" : "below")
        : undefined,
    };

    const result = {
      agents: {
        news: agents.news || { score: 50, sentiment: 0, confidence: 0, notes: "No data" },
        earnings: agents.earnings || { score: 50, sentiment: 0, confidence: 0, notes: "No data" },
        technical: agents.technical || { score: 50, sentiment: 0, confidence: 0, notes: "No data" },
      },
      decision: {
        action: signal?.action || dashboard.consensus?.action || "HOLD",
        confidence: signal ? signal.combined_score / 100 : (dashboard.consensus?.final_score || 50) / 100,
        ticker: normalizedTicker,
        symbol: normalizedTicker,
        reasoning: `Score: ${signal?.combined_score?.toFixed(1) || dashboard.consensus?.final_score?.toFixed(1) || 50}/100`,
        stopLoss: signal?.stop_loss || dashboard.consensus?.stop_loss_pct || 0.03,
        takeProfit: signal?.take_profit || dashboard.consensus?.take_profit_pct || 0.03,
        entryPrice: signal?.entry_price || dashboard.market?.quote?.price || 0,
        quantity: signal?.quantity || 10,
        contributingAgents: ["News Agent", "Earnings Agent", "Technical Agent"],
        // Score breakdown from best-signal
        combinedScore: signal?.combined_score,
        aiScore: signal?.ai_score,
        momentumScore: signal?.momentum_score,
        strategy: signal?.strategy,
      },
      technicals,
      raw: dashboard, // Keep raw response for debugging
    };

    console.log("[API] Transformed technicals:", result.technicals);
    return result as any;
  } catch (error) {
    console.error("Dashboard analysis failed:", error);
    // Return default empty response
    return {
      agents: {
        news: { score: 50, sentiment: 0, confidence: 0, notes: "Error loading" },
        earnings: { score: 50, sentiment: 0, confidence: 0, notes: "Error loading" },
        technical: { score: 50, sentiment: 0, confidence: 0, notes: "Error loading" },
      },
      decision: {
        action: "HOLD",
        confidence: 0.5,
        ticker: normalizedTicker,
        symbol: normalizedTicker,
        reasoning: "Analysis unavailable",
        stopLoss: 0.03,
        takeProfit: 0.03,
        contributingAgents: [],
      },
      technicals: {
        rsi: null,
        macd: { value: null, signal: null, histogram: null },
        sma20: null,
        sma50: null,
        sma200: null,
        ema20: null,
        ema50: null,
        priceVsSma20: undefined,
        priceVsSma50: undefined,
        priceVsSma200: undefined,
      },
    } as any;
  }
}

export async function getSentiment(ticker: string): Promise<AgentSignal> {
  return fetchAPI(`/api/sentiment/${ticker}`);
}

// Trading
export async function getAccount(): Promise<Account> {
  try {
    const data = await fetchAPI<any>("/api/trading/account");
    return {
      equity: parseFloat(data.equity) || parseFloat(data.portfolio_value) || 0,
      cash: parseFloat(data.cash) || 0,
      buyingPower: parseFloat(data.buying_power) || parseFloat(data.daytrading_buying_power) || 0,
      portfolioValue: parseFloat(data.portfolio_value) || parseFloat(data.equity) || 0,
      dayTradeCount: data.daytrade_count || 0,
    };
  } catch {
    return {
      equity: 100000,
      cash: 100000,
      buyingPower: 400000,
      portfolioValue: 100000,
      dayTradeCount: 0,
    };
  }
}

export async function getPositions(): Promise<Position[]> {
  try {
    const data = await fetchAPI<any>("/api/trading/positions");
    const positions = data.positions || data || [];
    return positions.map((pos: any) => {
      // Calculate market value if not provided
      const qty = parseFloat(pos.qty) || pos.quantity || 0;
      const currentPrice = parseFloat(pos.current) || parseFloat(pos.current_price) || 0;
      const marketValue = parseFloat(pos.market_value) || Math.abs(qty * currentPrice);

      // pnl_pct from API is a ratio (0.03 = 3%), convert to percentage
      const pnlPctRatio = parseFloat(pos.pnl_pct) || parseFloat(pos.unrealized_plpc) || 0;
      const unrealizedPLPercent = pnlPctRatio * 100;

      return {
        symbol: pos.symbol,
        qty, // Keep for heatmap compatibility
        quantity: qty,
        avgEntryPrice: parseFloat(pos.entry) || parseFloat(pos.avg_entry_price) || 0,
        currentPrice,
        marketValue,
        unrealizedPL: parseFloat(pos.pnl) || parseFloat(pos.unrealized_pl) || 0,
        unrealizedPLPercent,
      };
    });
  } catch {
    return [];
  }
}

export async function getRiskStatus(): Promise<RiskStatus> {
  try {
    // Fetch account and positions in parallel to avoid waterfall
    const [account, positions] = await Promise.all([
      getAccount(),
      getPositions()
    ]);

    // Calculate daily P&L from positions
    const dailyPL = positions.reduce((sum, p) => sum + p.unrealizedPL, 0);
    const dailyPLPercent = account.equity > 0 ? (dailyPL / account.equity) * 100 : 0;

    // Determine circuit breaker level
    let circuitBreaker: "GREEN" | "YELLOW" | "ORANGE" | "RED" = "GREEN";
    if (dailyPLPercent <= -5) circuitBreaker = "RED";
    else if (dailyPLPercent <= -3) circuitBreaker = "ORANGE";
    else if (dailyPLPercent <= -2) circuitBreaker = "YELLOW";

    return {
      circuitBreaker,
      dailyPL,
      dailyPLPercent,
      tradesToday: positions.length,
      maxDailyLoss: 0.05,
      currentDrawdown: Math.min(dailyPLPercent, 0),
    };
  } catch {
    return {
      circuitBreaker: "GREEN",
      dailyPL: 0,
      dailyPLPercent: 0,
      tradesToday: 0,
      maxDailyLoss: 0.05,
      currentDrawdown: 0,
    };
  }
}

export async function executeTrade(decision: TradeDecision): Promise<any> {
  // Use the trading execute endpoint with specific ticker
  try {
    const ticker = decision.ticker || decision.symbol;
    const res = await fetch(`${API_BASE}/api/trading/execute?auto=true&ticker=${encodeURIComponent(ticker)}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
    });

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`Trade execution failed: ${res.status} ${res.statusText} - ${text}`);
    }

    return res.json();
  } catch (error) {
    // Provide more helpful error message
    if (error instanceof TypeError && error.message === "Failed to fetch") {
      throw new Error("Cannot connect to trading server. Please check if the backend is running on port 8000.");
    }
    throw error;
  }
}

// Watchlist
export async function getWatchlist(): Promise<string[]> {
  try {
    const data = await fetchAPI<any>("/api/watchlist");
    return data.tickers || data || [];
  } catch {
    return ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"];
  }
}

// Closed trades with P&L
export interface ClosedTrade {
  id: string;
  symbol: string;
  side: string;
  timestamp: string;
  entry_price: number;
  exit_price: number;
  pnl_pct: number;
  reason: string;
  status: string;
}

export interface ClosedTradesResponse {
  trades: ClosedTrade[];
  count: number;
  summary: {
    total_trades: number;
    wins: number;
    losses: number;
    win_rate: number;
    total_pnl_pct: number;
  };
}

export async function getClosedTrades(limit: number = 20): Promise<ClosedTradesResponse> {
  try {
    return await fetchAPI<ClosedTradesResponse>(`/api/trading/closed-trades?limit=${limit}`);
  } catch {
    return {
      trades: [],
      count: 0,
      summary: { total_trades: 0, wins: 0, losses: 0, win_rate: 0, total_pnl_pct: 0 }
    };
  }
}

// Portfolio History
export interface PortfolioHistoryPoint {
  timestamp: number;
  date: string;
  equity: number;
  profit_loss: number;
  profit_loss_pct: number;
}

export interface PortfolioHistorySummary {
  start_equity: number;
  end_equity: number;
  total_return_pct: number;
  total_return_dollars: number;
  max_equity: number;
  min_equity: number;
  max_drawdown_pct: number;
  best_day: { date: string; pct: number };
  worst_day: { date: string; pct: number };
  trading_days: number;
}

export interface PortfolioHistoryResponse {
  data: PortfolioHistoryPoint[];
  summary: PortfolioHistorySummary;
  period: string;
  timeframe: string;
  timestamp: string;
}

export async function getPortfolioHistory(
  period: string = "1M",
  timeframe: string = "1D"
): Promise<PortfolioHistoryResponse> {
  try {
    return await fetchAPI<PortfolioHistoryResponse>(
      `/api/portfolio/history?period=${period}&timeframe=${timeframe}`
    );
  } catch {
    return {
      data: [],
      summary: {} as PortfolioHistorySummary,
      period,
      timeframe,
      timestamp: new Date().toISOString(),
    };
  }
}

// Emergency: Close all positions and cancel all orders (PANIC)
export async function panicCloseAll(): Promise<{ positions: any; orders: any }> {
  const [positions, orders] = await Promise.all([
    fetch(`${API_BASE}/api/trading/close-all`, { method: "POST" }).then(r => r.json()),
    fetch(`${API_BASE}/api/trading/orders`, { method: "DELETE" }).then(r => r.json()),
  ]);
  return { positions, orders };
}

// Cancel all open orders only
export async function cancelAllOrders(): Promise<any> {
  return fetch(`${API_BASE}/api/trading/orders`, { method: "DELETE" }).then(r => r.json());
}

// Close all positions only
export async function closeAllPositions(): Promise<any> {
  return fetch(`${API_BASE}/api/trading/close-all`, { method: "POST" }).then(r => r.json());
}

// All Trade Decisions (BUY/HOLD/SELL grouped)
export interface TradeDecisionItem {
  ticker: string;
  action: "BUY" | "HOLD" | "SELL";
  confidence: number;
  combinedScore: number;
  aiScore: number;
  momentumScore: number;
  strategy: string;
  urgency: string;
  entryPrice: number;
  stopLoss: number;
  takeProfit: number;
}

export interface AllDecisionsResponse {
  timestamp: string;
  total: number;
  buy: TradeDecisionItem[];
  hold: TradeDecisionItem[];
  sell: TradeDecisionItem[];
  counts: {
    buy: number;
    hold: number;
    sell: number;
  };
}

export async function getAllDecisions(): Promise<AllDecisionsResponse> {
  return fetchAPI("/api/trading/all-decisions");
}

// Scan endpoints
export async function scanWatchlist(): Promise<{ results: any[] }> {
  return fetchAPI("/api/scan/watchlist");
}

export async function scanUniverse(): Promise<{ results: any[] }> {
  return fetchAPI("/api/scan/universe");
}

export async function scanSpicy(): Promise<{ results: any[] }> {
  return fetchAPI("/api/scan/spicy");
}

// Trade History / Orders
export async function getOrders(
  status: string = "all",
  limit: number = 50,
  days: number = 7
): Promise<{ orders: any[]; count: number }> {
  try {
    const response = await fetchAPI<any>(
      `/api/trading/orders?status=${status}&limit=${limit}&days=${days}`
    );
    return {
      orders: response.orders || [],
      count: response.count || 0,
    };
  } catch {
    return { orders: [], count: 0 };
  }
}

// Analyst Ratings
export async function getAnalystRatings(
  ticker?: string,
  daysBack: number = 30,
  limit: number = 20
): Promise<any[]> {
  try {
    const params = new URLSearchParams({
      days_back: daysBack.toString(),
      limit: limit.toString(),
    });
    if (ticker) {
      params.set("ticker", ticker);
    }
    const response = await fetchAPI<any>(`/api/ratings?${params.toString()}`);
    const results = response.results || response || [];
    return Array.isArray(results) ? results : [];
  } catch {
    return [];
  }
}

// Consensus Ratings for a specific ticker
export async function getConsensusRating(ticker: string): Promise<any | null> {
  try {
    const response = await fetchAPI<any>(`/api/consensus/${ticker}`);
    const results = response.results || response || [];
    return Array.isArray(results) && results.length > 0 ? results[0] : null;
  } catch {
    return null;
  }
}

// Deep AI Analysis (Claude + OpenAI multi-agent)
export async function getDeepAnalysis(ticker: string): Promise<any> {
  try {
    const response = await fetchAPI<any>(`/api/ai/deep-analysis/${ticker}`);
    return response;
  } catch (error) {
    console.error("Deep analysis error:", error);
    return {
      error: "Failed to get deep analysis",
      final_action: "HOLD",
      final_score: 50
    };
  }
}

// Trading Activity Log
export async function getActivityLog(limit: number = 50): Promise<{
  logs: ActivityLogEntry[];
  total: number;
  filtered: number;
  timestamp: string;
}> {
  try {
    const response = await fetchAPI<any>(`/api/trading/activity-log?limit=${limit}`);
    return {
      logs: response.logs || [],
      total: response.total || 0,
      filtered: response.filtered || 0,
      timestamp: response.timestamp || new Date().toISOString(),
    };
  } catch {
    return {
      logs: [],
      total: 0,
      filtered: 0,
      timestamp: new Date().toISOString(),
    };
  }
}

// Type for activity log entries
export interface ActivityLogEntry {
  id: string;
  timestamp: string;
  type: "ENTRY_SUCCESS" | "ENTRY_ERROR" | "EXIT_SIGNAL" | "EXIT_SUCCESS" | "EXIT_ERROR" | "EXIT_WARNING" | "TRADE" | "AUTO_EXIT";
  ticker: string;
  action: string;
  details: {
    reason?: string;
    error?: string;
    order_id?: string;
    quantity?: number;
    entry_price?: number;
    entry?: number;
    exit_price?: number;
    current_price?: number;
    price?: number;
    stop_loss?: number;
    take_profit?: number;
    pnl?: number;
    pnl_pct?: number;
    confidence?: number;
    momentum?: number;
    score?: number;
    reasoning?: string;
    status?: string;  // "executed", "pending", "filled", "canceled", etc.
    result?: string;  // "closed", etc.
  };
}

// Auto-Trade Status
export interface AutoTradeStatus {
  enabled: boolean;
  interval: number;
  market_open: boolean;
  updated_at: string;
}

export async function getAutoTradeStatus(): Promise<AutoTradeStatus> {
  try {
    return await fetchAPI<AutoTradeStatus>("/api/auto-trade/status");
  } catch {
    return {
      enabled: false,
      interval: 60,
      market_open: false,
      updated_at: new Date().toISOString(),
    };
  }
}

export async function enableAutoTrade(interval: number = 60): Promise<AutoTradeStatus> {
  return fetchAPI<AutoTradeStatus>(`/api/auto-trade/enable?interval=${interval}`, {
    method: "POST",
  });
}

export async function disableAutoTrade(): Promise<AutoTradeStatus> {
  return fetchAPI<AutoTradeStatus>("/api/auto-trade/disable", {
    method: "POST",
  });
}
