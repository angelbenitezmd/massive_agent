import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ ticker: string }> }
) {
  const { ticker: rawTicker } = await params;
  const ticker = rawTicker.toUpperCase();

  try {
    // Fetch all data in parallel
    const [quoteRes, newsRes, earningsRes, barsRes, sentimentRes, accountRes, riskRes] = await Promise.allSettled([
      fetch(`${BACKEND_URL}/api/quote/${ticker}`),
      fetch(`${BACKEND_URL}/api/news?ticker=${ticker}`),
      fetch(`${BACKEND_URL}/api/earnings?ticker=${ticker}`),
      fetch(`${BACKEND_URL}/api/bars/${ticker}?timeframe=1Min&limit=100`),
      fetch(`${BACKEND_URL}/api/sentiment/${ticker}`),
      fetch(`${BACKEND_URL}/api/account`),
      fetch(`${BACKEND_URL}/api/risk`),
    ]);

    // Extract data with fallbacks
    const quote = quoteRes.status === "fulfilled" && quoteRes.value.ok
      ? await quoteRes.value.json()
      : null;

    const news = newsRes.status === "fulfilled" && newsRes.value.ok
      ? await newsRes.value.json()
      : [];

    const earnings = earningsRes.status === "fulfilled" && earningsRes.value.ok
      ? await earningsRes.value.json()
      : [];

    const bars = barsRes.status === "fulfilled" && barsRes.value.ok
      ? await barsRes.value.json()
      : [];

    const sentiment = sentimentRes.status === "fulfilled" && sentimentRes.value.ok
      ? await sentimentRes.value.json()
      : null;

    const account = accountRes.status === "fulfilled" && accountRes.value.ok
      ? await accountRes.value.json()
      : null;

    const risk = riskRes.status === "fulfilled" && riskRes.value.ok
      ? await riskRes.value.json()
      : null;

    // Calculate technicals from bars
    const technicals = calculateTechnicals(bars, quote?.price);

    // Generate agent signals
    const newsAgent = generateNewsAgentSignal(news, sentiment);
    const earningsAgent = generateEarningsAgentSignal(earnings);
    const technicalAgent = generateTechnicalAgentSignal(technicals);

    // Generate consensus decision
    const decision = generateTradeDecision(
      ticker,
      quote?.price || 0,
      [newsAgent, earningsAgent, technicalAgent],
      account,
      risk
    );

    return NextResponse.json({
      quote,
      technicals,
      bars,
      news,
      earnings,
      agents: {
        news: newsAgent,
        earnings: earningsAgent,
        technical: technicalAgent,
      },
      decision,
      account,
      risk,
    });
  } catch (error) {
    console.error("Analysis error:", error);
    return NextResponse.json(
      { error: "Analysis failed" },
      { status: 500 }
    );
  }
}

function calculateTechnicals(bars: any[], currentPrice?: number) {
  if (!bars || bars.length === 0) {
    return {
      rsi: 50,
      macd: { value: 0, signal: 0, histogram: 0 },
      sma20: 0,
      sma50: 0,
      sma200: 0,
      ema20: 0,
      ema50: 0,
      priceVsSma20: "above" as const,
      priceVsSma50: "above" as const,
      priceVsSma200: "above" as const,
    };
  }

  const closes = bars.map((b) => b.close || b.c);
  const price = currentPrice || closes[closes.length - 1];

  // Calculate RSI
  const rsi = calculateRSI(closes, 14);

  // Calculate SMAs
  const sma20 = calculateSMA(closes, 20);
  const sma50 = calculateSMA(closes, 50);
  const sma200 = calculateSMA(closes, 200);

  // Calculate EMAs
  const ema20 = calculateEMA(closes, 20);
  const ema50 = calculateEMA(closes, 50);

  // Calculate MACD
  const ema12 = calculateEMA(closes, 12);
  const ema26 = calculateEMA(closes, 26);
  const macdValue = ema12 - ema26;
  const macdSignal = calculateEMA([...Array(8).fill(0), macdValue], 9);
  const macdHistogram = macdValue - macdSignal;

  return {
    rsi,
    macd: {
      value: macdValue,
      signal: macdSignal,
      histogram: macdHistogram,
    },
    sma20,
    sma50,
    sma200,
    ema20,
    ema50,
    priceVsSma20: price > sma20 ? "above" as const : "below" as const,
    priceVsSma50: price > sma50 ? "above" as const : "below" as const,
    priceVsSma200: price > sma200 ? "above" as const : "below" as const,
  };
}

function calculateRSI(closes: number[], period: number): number {
  if (closes.length < period + 1) return 50;

  let gains = 0;
  let losses = 0;

  for (let i = closes.length - period; i < closes.length; i++) {
    const change = closes[i] - closes[i - 1];
    if (change > 0) gains += change;
    else losses -= change;
  }

  const avgGain = gains / period;
  const avgLoss = losses / period;

  if (avgLoss === 0) return 100;
  const rs = avgGain / avgLoss;
  return 100 - 100 / (1 + rs);
}

function calculateSMA(data: number[], period: number): number {
  if (data.length < period) return data[data.length - 1] || 0;
  const slice = data.slice(-period);
  return slice.reduce((a, b) => a + b, 0) / period;
}

function calculateEMA(data: number[], period: number): number {
  if (data.length < period) return calculateSMA(data, data.length);

  const multiplier = 2 / (period + 1);
  let ema = calculateSMA(data.slice(0, period), period);

  for (let i = period; i < data.length; i++) {
    ema = (data[i] - ema) * multiplier + ema;
  }

  return ema;
}

function generateNewsAgentSignal(news: any, sentiment: any) {
  // Handle both array and { results: [...] } format
  const newsArray = Array.isArray(news) ? news : (news?.results || []);
  const newsCount = newsArray.length || 0;
  let direction: "bullish" | "bearish" | "neutral" = "neutral";
  let confidence = 0.5;
  let reasoning = "No significant news detected.";

  if (sentiment) {
    direction = sentiment.direction || sentiment.sentiment || "neutral";
    confidence = sentiment.confidence || (sentiment.score ? sentiment.score / 100 : 0.5);
    reasoning = sentiment.reasoning || `Sentiment score: ${sentiment.score}`;
  } else if (newsCount > 0) {
    // Simple heuristic based on news count and recency
    const recentNews = newsArray.slice(0, 5);
    const bullishKeywords = ["surge", "rally", "beat", "upgrade", "positive", "growth"];
    const bearishKeywords = ["drop", "fall", "miss", "downgrade", "negative", "decline"];

    let bullishCount = 0;
    let bearishCount = 0;

    recentNews.forEach((item: { headline?: string; title?: string }) => {
      const headline = (item.headline || item.title || "").toLowerCase();
      bullishKeywords.forEach((kw) => {
        if (headline.includes(kw)) bullishCount++;
      });
      bearishKeywords.forEach((kw) => {
        if (headline.includes(kw)) bearishCount++;
      });
    });

    if (bullishCount > bearishCount) {
      direction = "bullish";
      confidence = Math.min(0.4 + bullishCount * 0.1, 0.8);
      reasoning = `Found ${bullishCount} positive headlines in recent news.`;
    } else if (bearishCount > bullishCount) {
      direction = "bearish";
      confidence = Math.min(0.4 + bearishCount * 0.1, 0.8);
      reasoning = `Found ${bearishCount} negative headlines in recent news.`;
    } else {
      reasoning = `Analyzed ${newsCount} news items. No clear sentiment direction.`;
    }
  }

  return {
    agentName: "News/Sentiment Agent",
    direction,
    confidence,
    reasoning,
    timestamp: new Date().toISOString(),
    newsCount,
    keyHeadlines: newsArray.slice(0, 3).map((n: any) => n.title || n.headline),
  };
}

function generateEarningsAgentSignal(earnings: any) {
  // Handle both array and { results: [...] } format
  const earningsArray = Array.isArray(earnings) ? earnings : (earnings?.results || []);
  let direction: "bullish" | "bearish" | "neutral" = "neutral";
  let confidence = 0.5;
  let reasoning = "No recent earnings data available.";
  let epsSurprise = 0;
  let revenueSurprise = 0;

  if (earningsArray && earningsArray.length > 0) {
    const latest = earningsArray[0];
    epsSurprise = latest.eps_surprise_percent || latest.epsSurprisePercent || 0;
    revenueSurprise = latest.revenue_surprise_percent || latest.revenueSurprisePercent || 0;

    if (epsSurprise > 5 || revenueSurprise > 5) {
      direction = "bullish";
      confidence = Math.min(0.5 + Math.max(epsSurprise, revenueSurprise) / 20, 0.9);
      reasoning = `Strong earnings beat: EPS ${epsSurprise > 0 ? "+" : ""}${epsSurprise.toFixed(1)}%, Revenue ${revenueSurprise > 0 ? "+" : ""}${revenueSurprise.toFixed(1)}%`;
    } else if (epsSurprise < -5 || revenueSurprise < -5) {
      direction = "bearish";
      confidence = Math.min(0.5 + Math.abs(Math.min(epsSurprise, revenueSurprise)) / 20, 0.9);
      reasoning = `Earnings miss: EPS ${epsSurprise.toFixed(1)}%, Revenue ${revenueSurprise.toFixed(1)}%`;
    } else {
      reasoning = `Earnings inline: EPS ${epsSurprise > 0 ? "+" : ""}${epsSurprise.toFixed(1)}%, Revenue ${revenueSurprise > 0 ? "+" : ""}${revenueSurprise.toFixed(1)}%`;
    }
  }

  return {
    agentName: "Earnings Agent",
    direction,
    confidence,
    reasoning,
    timestamp: new Date().toISOString(),
    epsSurprise,
    revenueSurprise,
  };
}

function generateTechnicalAgentSignal(technicals: any) {
  let direction: "bullish" | "bearish" | "neutral" = "neutral";
  let confidence = 0.5;
  let bullishSignals = 0;
  let bearishSignals = 0;
  const reasons: string[] = [];

  // RSI analysis
  if (technicals.rsi < 30) {
    bullishSignals++;
    reasons.push("RSI oversold");
  } else if (technicals.rsi > 70) {
    bearishSignals++;
    reasons.push("RSI overbought");
  }

  // MACD analysis
  if (technicals.macd.histogram > 0 && technicals.macd.value > technicals.macd.signal) {
    bullishSignals++;
    reasons.push("MACD bullish");
  } else if (technicals.macd.histogram < 0 && technicals.macd.value < technicals.macd.signal) {
    bearishSignals++;
    reasons.push("MACD bearish");
  }

  // Moving average analysis
  if (technicals.priceVsSma20 === "above") bullishSignals++;
  else bearishSignals++;

  if (technicals.priceVsSma50 === "above") bullishSignals++;
  else bearishSignals++;

  if (technicals.priceVsSma200 === "above") {
    bullishSignals++;
    reasons.push("Above 200 SMA");
  } else {
    bearishSignals++;
    reasons.push("Below 200 SMA");
  }

  // Determine direction
  const total = bullishSignals + bearishSignals;
  if (bullishSignals > bearishSignals) {
    direction = "bullish";
    confidence = 0.5 + (bullishSignals / total) * 0.4;
  } else if (bearishSignals > bullishSignals) {
    direction = "bearish";
    confidence = 0.5 + (bearishSignals / total) * 0.4;
  }

  const reasoning = reasons.length > 0
    ? reasons.join(", ") + `. RSI: ${technicals.rsi.toFixed(1)}`
    : `Neutral technical setup. RSI: ${technicals.rsi.toFixed(1)}`;

  return {
    agentName: "Technical Momentum Agent",
    direction,
    confidence,
    reasoning,
    timestamp: new Date().toISOString(),
    rsi: technicals.rsi,
    macdSignal: technicals.macd.histogram > 0 ? "bullish" : technicals.macd.histogram < 0 ? "bearish" : "neutral",
    trendDirection: technicals.priceVsSma50 === "above" ? "up" : "down",
  };
}

function generateTradeDecision(
  symbol: string,
  price: number,
  agents: any[],
  account: any,
  risk: any
) {
  let action: "BUY" | "SELL" | "HOLD" | "NO_BUY" = "NO_BUY";
  let confidence = 0;
  let reasoning = "";

  // Check circuit breaker
  const circuitBreaker = risk?.circuit_breaker || risk?.circuitBreaker || "GREEN";
  if (circuitBreaker === "RED") {
    return {
      action: "NO_BUY" as const,
      symbol,
      quantity: 0,
      entryPrice: price,
      stopLoss: price * 0.98,
      takeProfit: price * 1.04,
      confidence: 0,
      reasoning: "Circuit breaker RED - trading halted",
      contributingAgents: [],
      timestamp: new Date().toISOString(),
    };
  }

  // Weighted confidence scoring
  // Technical agent gets higher weight since it has real data
  const weights: Record<string, number> = {
    "Technical Momentum Agent": 1.5,
    "News/Sentiment Agent": 1.0,
    "Earnings Agent": 0.8,
  };

  let bullishScore = 0;
  let bearishScore = 0;
  let totalWeight = 0;
  const contributingSignals: string[] = [];

  agents.forEach((agent) => {
    const weight = weights[agent.agentName] || 1.0;
    const weightedConfidence = agent.confidence * weight;
    totalWeight += weight;

    if (agent.direction === "bullish") {
      bullishScore += weightedConfidence;
      if (agent.confidence >= 0.6) {
        contributingSignals.push(`${agent.agentName.split(" ")[0]} bullish (${Math.round(agent.confidence * 100)}/100)`);
      }
    } else if (agent.direction === "bearish") {
      bearishScore += weightedConfidence;
      if (agent.confidence >= 0.6) {
        contributingSignals.push(`${agent.agentName.split(" ")[0]} bearish (${Math.round(agent.confidence * 100)}/100)`);
      }
    }
    // Neutral agents don't add to scores but don't block either
  });

  // Normalize scores
  const normalizedBullish = bullishScore / totalWeight;
  const normalizedBearish = bearishScore / totalWeight;
  const signalStrength = Math.abs(normalizedBullish - normalizedBearish);

  // Decision thresholds
  const buyThreshold = 0.25;  // Lower threshold for weighted system
  const sellThreshold = 0.25;
  const highConfidenceThreshold = 0.75; // Single agent with very high confidence

  // Check for single high-confidence signal
  const highConfidenceBullish = agents.find(a => a.direction === "bullish" && a.confidence >= highConfidenceThreshold);
  const highConfidenceBearish = agents.find(a => a.direction === "bearish" && a.confidence >= highConfidenceThreshold);

  if (normalizedBullish - normalizedBearish >= buyThreshold || highConfidenceBullish) {
    action = "BUY";
    confidence = Math.min(normalizedBullish + 0.1, 0.95);
    if (highConfidenceBullish && contributingSignals.length === 1) {
      reasoning = `Strong signal: ${highConfidenceBullish.agentName} with score ${Math.round(highConfidenceBullish.confidence * 100)}/100.`;
    } else {
      reasoning = contributingSignals.length > 0
        ? `Bullish consensus: ${contributingSignals.join(", ")}.`
        : `Weighted bullish score: ${Math.round(normalizedBullish * 100)}/100`;
    }
  } else if (normalizedBearish - normalizedBullish >= sellThreshold || highConfidenceBearish) {
    action = "SELL";
    confidence = Math.min(normalizedBearish + 0.1, 0.95);
    if (highConfidenceBearish && contributingSignals.length === 1) {
      reasoning = `Strong signal: ${highConfidenceBearish.agentName} with score ${Math.round(highConfidenceBearish.confidence * 100)}/100.`;
    } else {
      reasoning = contributingSignals.length > 0
        ? `Bearish consensus: ${contributingSignals.join(", ")}.`
        : `Weighted bearish score: ${Math.round(normalizedBearish * 100)}/100`;
    }
  } else {
    action = "HOLD";
    confidence = 0.5 + signalStrength;
    reasoning = signalStrength < 0.1
      ? "Signals too weak or conflicting. Waiting for clearer setup."
      : `Mixed signals: ${contributingSignals.join(", ") || "No strong signals"}.`;
  }

  // Calculate position size based on risk
  const equity = account?.equity || account?.portfolio_value || 100000;
  const maxPositionPct = circuitBreaker === "YELLOW" ? 0.025 : 0.05;
  const positionValue = equity * maxPositionPct;
  const quantity = Math.floor(positionValue / price);

  // Calculate stop loss and take profit
  const stopLossPct = 0.02; // 2%
  const riskRewardRatio = 2;
  const stopLoss = price * (1 - stopLossPct);
  const takeProfit = price * (1 + stopLossPct * riskRewardRatio);

  return {
    action,
    symbol,
    quantity,
    entryPrice: price,
    stopLoss,
    takeProfit,
    confidence,
    reasoning,
    contributingAgents: agents.map((a) => a.agentName),
    timestamp: new Date().toISOString(),
  };
}
