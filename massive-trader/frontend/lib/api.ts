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

// News
export async function getNews(ticker: string): Promise<NewsItem[]> {
  const response = await fetchAPI<any>(`/api/news?ticker=${ticker}`);
  // Benzinga returns { results: [...] }
  const data = response.results || response || [];
  if (!Array.isArray(data)) return [];
  return data.map((item: any) => ({
    id: item.id || item.url,
    headline: item.title || item.headline,
    summary: item.teaser || item.summary,
    author: item.author,
    source: item.source || "Benzinga",
    url: item.url,
    publishedAt: item.created || item.published_at || item.updated,
    symbols: item.stocks?.map((s: any) => s.name) || item.symbols || [ticker],
    tags: item.channels?.map((c: any) => c.name) || item.tags || [],
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

// AI Analysis - uses the Next.js API route which aggregates backend data
export async function runAnalysis(ticker: string): Promise<AnalysisResponse> {
  // First try the dashboard endpoint for aggregated data
  try {
    const dashboard = await fetchAPI<any>(`/api/dashboard/${ticker}`);
    return dashboard;
  } catch {
    // Fall back to calling Next.js API route
    const res = await fetch(`/api/analyze/${ticker}`, { method: "POST" });
    if (!res.ok) throw new Error("Analysis failed");
    return res.json();
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
    return positions.map((pos: any) => ({
      symbol: pos.symbol,
      quantity: parseFloat(pos.qty) || pos.quantity || 0,
      avgEntryPrice: parseFloat(pos.entry) || parseFloat(pos.avg_entry_price) || 0,
      currentPrice: parseFloat(pos.current) || parseFloat(pos.current_price) || 0,
      marketValue: parseFloat(pos.market_value) || 0,
      unrealizedPL: parseFloat(pos.pnl) || parseFloat(pos.unrealized_pl) || 0,
      unrealizedPLPercent: parseFloat(pos.pnl_pct) / 100 || 0,
    }));
  } catch {
    return [];
  }
}

export async function getRiskStatus(): Promise<RiskStatus> {
  try {
    // Risk status is derived from account and positions
    const account = await getAccount();
    const positions = await getPositions();

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
  // Use the trading execute endpoint
  return fetchAPI("/api/trading/execute?auto=true", {
    method: "POST",
  });
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

// Scan endpoints
export async function scanWatchlist(): Promise<any[]> {
  return fetchAPI("/api/scan/watchlist");
}

export async function scanUniverse(): Promise<any[]> {
  return fetchAPI("/api/scan/universe");
}

export async function scanSpicy(): Promise<any[]> {
  return fetchAPI("/api/scan/spicy");
}
