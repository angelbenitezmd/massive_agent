"use client";

import { useState, useEffect, useCallback, useRef, useMemo, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import {
  Header,
  MarketSnapshot,
  NewsPanel,
  NewsFeed,
  EarningsPanel,
  AIAgentsPanel,
  TradeDecisionPanel,
  RiskPanel,
  ScannerPanel,
  TradeJournal,
  AnalystRatings,
  PerformanceStats,
  MarketMovers,
  DeepAnalysisPanel,
  ActivityLog,
  MarketStatus,
  TodaysSummary,
  PortfolioHeatmap,
  PortfolioChart,
  TradeSignalCard,
  ManualTradePanel,
  DebatePanel,
  TokenMonitor,
} from "@/components/dashboard";
import {
  useQuote,
  useBars,
  useEarnings,
  useAccount,
  usePositions,
  useRiskStatus,
  useWatchlist,
  useAnalysis,
  useExecuteTrade,
  useSystemStatus,
  useOrders,
  useAnalystRatings,
  useScanWatchlist,
  useScanTrending,
  useDeepAnalysis,
  useActivityLog,
  useLatestNews,
  useNews,
  useAllDecisions,
  useManualTrade,
  useClosePosition,
} from "@/hooks/use-trading-data";
import type { AgentSignal, TradeDecision, Technicals } from "@/types";
// Day P&L now sourced from Alpaca account data

function Dashboard() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const [selectedTicker, setSelectedTicker] = useState(
    () => searchParams.get("ticker") || "AAPL"
  );
  const [selectedTimeframe, setSelectedTimeframe] = useState(
    () => searchParams.get("tf") || "1Min"
  );

  const updateTicker = useCallback((ticker: string) => {
    setSelectedTicker(ticker);
    const params = new URLSearchParams(searchParams.toString());
    params.set("ticker", ticker);
    router.replace(`?${params.toString()}`, { scroll: false });
  }, [searchParams, router]);

  const updateTimeframe = useCallback((tf: string) => {
    setSelectedTimeframe(tf);
    const params = new URLSearchParams(searchParams.toString());
    params.set("tf", tf);
    router.replace(`?${params.toString()}`, { scroll: false });
  }, [searchParams, router]);
  const [autoRefresh, setAutoRefresh] = useState(true); // Always on by default
  // Note: autoTrade state is now managed by the backend (24/7 operation)
  const [analysisResult, setAnalysisResult] = useState<{
    agents: {
      news: AgentSignal;
      earnings: AgentSignal;
      technical: AgentSignal;
    };
    decision: TradeDecision;
    technicals: Technicals;
  } | null>(null);

  // Data fetching hooks
  const { data: status } = useSystemStatus();
  const { data: watchlist } = useWatchlist();
  const { data: quote, isLoading: quoteLoading } = useQuote(selectedTicker);
  const { data: bars, isLoading: barsLoading } = useBars(selectedTicker, selectedTimeframe);
  const { data: globalNews, isLoading: globalNewsLoading } = useLatestNews();
  const { data: tickerNews, isLoading: tickerNewsLoading } = useNews(selectedTicker);
  const { data: earnings, isLoading: earningsLoading } = useEarnings(selectedTicker);
  const {
    data: account,
    isLoading: accountLoading,
    isError: accountIsError,
    error: accountError,
  } = useAccount();
  const { data: positions } = usePositions();
  const { data: riskStatus } = useRiskStatus();
  const { data: ordersData, isLoading: ordersLoading, refetch: refetchOrders } = useOrders("all", 20, 7);
  const { data: ratings, isLoading: ratingsLoading } = useAnalystRatings(selectedTicker, 30, 10);
  const {
    data: watchlistScan,
    isLoading: watchlistScanLoading,
    isFetching: watchlistScanFetching,
    refetch: refetchWatchlistScan,
    dataUpdatedAt: watchlistScanUpdatedAt,
  } = useScanWatchlist();
  const { data: trendingScan } = useScanTrending();
  const { data: activityLog, isLoading: activityLogLoading } = useActivityLog(50);
  const { data: allDecisions, isLoading: allDecisionsLoading } = useAllDecisions();

  // Mutations
  const analysisMutation = useAnalysis(selectedTicker);
  const executeTradeMutation = useExecuteTrade();
  const deepAnalysisMutation = useDeepAnalysis(selectedTicker);
  const manualTradeMutation = useManualTrade();
  const closePositionMutation = useClosePosition();

  // Deep analysis result state
  const [deepAnalysisResult, setDeepAnalysisResult] = useState<any>(null);

  // Day P&L now comes directly from Alpaca account data (equity - last_equity)

  // Get the correct decision for the selected ticker from allDecisions
  // This ensures consistency between AI Trade Decisions card and Trade Decision panel
  const selectedTickerDecision = useMemo(() => {
    if (!allDecisions) return analysisResult?.decision;

    // Search in all groups for the selected ticker
    const allItems = [...(allDecisions.buy || []), ...(allDecisions.hold || []), ...(allDecisions.sell || [])];
    const found = allItems.find(d => d.ticker === selectedTicker);

    if (found) {
      // Convert to the TradeDecision format expected by TradeDecisionPanel
      return {
        ticker: found.ticker,
        symbol: found.ticker,
        action: found.action,
        confidence: found.confidence,
        combinedScore: found.combinedScore,
        aiScore: found.aiScore,
        momentumScore: found.momentumScore,
        strategy: found.strategy,
        entryPrice: found.entryPrice,
        stopLoss: found.stopLoss,
        takeProfit: found.takeProfit,
        quantity: 10, // Default quantity
        reasoning: `AI Score: ${found.aiScore}/100, Momentum: ${found.momentumScore}/100, Combined: ${found.combinedScore.toFixed(1)}/100`,
        contributingAgents: ["AI Analyst", "Momentum Scanner"],
        timestamp: new Date().toISOString(),
      };
    }

    // Fallback to analysis result if ticker not in allDecisions
    return analysisResult?.decision;
  }, [allDecisions, selectedTicker, analysisResult?.decision]);

  const accountErrorMessage = useMemo(() => {
    if (!accountIsError) return "";
    if (accountError instanceof Error) return accountError.message;
    return "Unable to load Alpaca account data.";
  }, [accountIsError, accountError]);

  // Execution management - prevent duplicate trades
  const lastExecutedSignalRef = useRef<string | null>(null);
  const isExecutingRef = useRef<boolean>(false);
  const lastExecutionTimeRef = useRef<number>(0);
  const EXECUTION_COOLDOWN_MS = 60000; // 1 minute cooldown between trades

  // Handle analysis
  const runAnalysis = useCallback(async () => {
    try {
      const result = await analysisMutation.mutateAsync();
      console.log("[Page] Analysis result received:", result);
      console.log("[Page] Technicals from result:", result?.technicals);
      setAnalysisResult(result as any);
    } catch (error) {
      console.error("Analysis failed:", error);
    }
  }, [analysisMutation]);

  // Handle manual trade execution (from button click)
  const executeTrade = useCallback(async () => {
    if (!selectedTickerDecision) return;
    if (isExecutingRef.current) {
      console.log("[ManualTrade] Already executing, please wait");
      return;
    }

    const now = Date.now();
    const timeSinceLastExecution = now - lastExecutionTimeRef.current;
    if (timeSinceLastExecution < EXECUTION_COOLDOWN_MS) {
      console.log(`[ManualTrade] Cooldown active: ${Math.ceil((EXECUTION_COOLDOWN_MS - timeSinceLastExecution) / 1000)}s remaining`);
      return;
    }

    isExecutingRef.current = true;
    lastExecutionTimeRef.current = now;

    try {
      console.log(`[ManualTrade] Executing: ${selectedTickerDecision.ticker}`);
      await executeTradeMutation.mutateAsync(selectedTickerDecision);
    } catch (error) {
      console.error("[ManualTrade] Failed:", error);
    } finally {
      isExecutingRef.current = false;
    }
  }, [selectedTickerDecision, executeTradeMutation]);

  // Handle deep AI analysis
  const runDeepAnalysis = useCallback(async () => {
    try {
      const result = await deepAnalysisMutation.mutateAsync();
      setDeepAnalysisResult(result);
    } catch (error) {
      console.error("Deep analysis failed:", error);
    }
  }, [deepAnalysisMutation]);

  // Run analysis on mount and ticker change
  useEffect(() => {
    runAnalysis();
    setDeepAnalysisResult(null); // Clear deep analysis when ticker changes
  }, [selectedTicker]); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-refresh effect
  useEffect(() => {
    if (!autoRefresh) return;

    const interval = setInterval(() => {
      if (typeof document !== "undefined" && document.visibilityState !== "visible") {
        return;
      }
      runAnalysis();
    }, 60000); // Every 60 seconds when auto-refresh is on

    return () => clearInterval(interval);
  }, [autoRefresh, runAnalysis]);

  // Note: Auto-trade is now handled by the backend 24/7
  // The frontend toggle just enables/disables the backend auto-trade loop

  return (
    <div className="min-h-screen bg-background">
      <Header
        selectedTicker={selectedTicker}
        onTickerChange={updateTicker}
        autoRefresh={autoRefresh}
        onAutoRefreshChange={setAutoRefresh}
        onAnalyze={runAnalysis}
        isAnalyzing={analysisMutation.isPending}
        watchlist={watchlist || []}
        activeSignal={selectedTickerDecision?.ticker ? {
          ticker: selectedTickerDecision.ticker,
          action: selectedTickerDecision.action,
          confidence: selectedTickerDecision.confidence,
        } : undefined}
      />

      <main className="container mx-auto px-4 py-3">
        {accountIsError && (
          <div className="mb-3 rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200">
            <span className="font-semibold">Alpaca disconnected:</span>{" "}
            {accountErrorMessage} Check `ALPACA_API_KEY_ID` and `ALPACA_API_SECRET_KEY`, then restart backend.
          </div>
        )}

        {/* Market Status Bar */}
        <div className="flex items-center justify-between gap-3 mb-3">
          <MarketStatus />
          <TodaysSummary
            account={account}
            positions={positions}
            riskStatus={riskStatus}
            activityLog={activityLog?.logs}
          />
        </div>

        {/* AI Trade Decisions - BUY/HOLD/SELL columns */}
        <div className="mb-3">
          <TradeSignalCard
            decisions={allDecisions}
            onSelectTicker={updateTicker}
            selectedTicker={selectedTicker}
            isLoading={allDecisionsLoading}
          />
        </div>

        {/* Top Row: News + Scanner/AI side by side */}
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-3 mb-3">
          {/* News Panels - Left 2 columns */}
          <NewsFeed
            news={globalNews}
            isLoading={globalNewsLoading}
            onTickerClick={updateTicker}
            watchlist={watchlist}
          />
          <NewsFeed
            news={tickerNews}
            isLoading={tickerNewsLoading}
            onTickerClick={updateTicker}
            selectedTicker={selectedTicker}
            watchlist={watchlist}
          />
          {/* Scanner + AI Agents - Right 2 columns */}
          <ScannerPanel
            selectedTicker={selectedTicker}
            onSelectTicker={updateTicker}
            watchlistResults={watchlistScan?.results}
            trendingResults={trendingScan?.results}
            isLoading={watchlistScanLoading}
            isFetching={watchlistScanFetching}
            updatedAt={watchlistScanUpdatedAt}
            onRefresh={() => void refetchWatchlistScan()}
          />
          <AIAgentsPanel
            ticker={selectedTicker}
            aiScore={selectedTickerDecision?.aiScore}
            momentumScore={selectedTickerDecision?.momentumScore}
            combinedScore={selectedTickerDecision?.combinedScore}
            llmEnhanced={(allDecisions ? [...(allDecisions.buy || []), ...(allDecisions.hold || []), ...(allDecisions.sell || [])].find(d => d.ticker === selectedTicker) : undefined)?.llmEnhanced}
            action={selectedTickerDecision?.action}
            isLoading={allDecisionsLoading}
          />
        </div>

        {/* Chart Row - Full Width */}
        <div className="mb-3">
          <MarketSnapshot
            quote={quote}
            technicals={analysisResult?.technicals}
            bars={bars}
            isLoading={quoteLoading || barsLoading}
            timeframe={selectedTimeframe}
            onTimeframeChange={updateTimeframe}
          />
        </div>

        {/* Analysis & Trade Row: Deep Analysis + Debate + Trade Decision + Manual Trade */}
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-3 mb-3">
          {/* Deep Analysis */}
          <DeepAnalysisPanel
            ticker={selectedTicker}
            result={deepAnalysisResult}
            isLoading={deepAnalysisMutation.isPending}
            onRunAnalysis={runDeepAnalysis}
          />
          {/* Multi-Agent Debate */}
          <DebatePanel ticker={selectedTicker} />
          {/* Trade Decision */}
          <TradeDecisionPanel
            decision={selectedTickerDecision}
            riskStatus={riskStatus}
            onExecuteTrade={executeTrade}
            isExecuting={executeTradeMutation.isPending}
            tradingMode={status?.tradingMode || "paper"}
          />
          {/* Manual Trade */}
          <ManualTradePanel
            ticker={selectedTicker}
            currentPrice={quote?.price || 0}
            buyingPower={account?.buyingPower || 0}
            onTrade={manualTradeMutation.mutateAsync}
            isExecuting={manualTradeMutation.isPending}
            tradingMode={status?.tradingMode || "paper"}
          />
        </div>

        {/* Portfolio Heatmap */}
        {positions && positions.length > 0 && (
          <div className="mb-3">
            <PortfolioHeatmap
              positions={positions}
              onSelectTicker={updateTicker}
              selectedTicker={selectedTicker}
            />
          </div>
        )}

        {/* Portfolio Performance Chart */}
        <div className="mb-3">
          <PortfolioChart />
        </div>

        {/* Bottom Grid: 3x2 layout */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 mb-3">
          <TradeJournal
            orders={ordersData?.orders}
            isLoading={ordersLoading}
            onOrdersCanceled={() => refetchOrders()}
          />
          <AnalystRatings
            ratings={ratings}
            selectedTicker={selectedTicker}
            isLoading={ratingsLoading}
          />
          <ActivityLog
            logs={activityLog?.logs}
            isLoading={activityLogLoading}
          />
          <EarningsPanel earnings={earnings} isLoading={earningsLoading} />
          <PerformanceStats
            account={account}
            positions={positions}
            riskStatus={riskStatus}
          />
          <MarketMovers
            watchlistResults={watchlistScan?.results}
            onSelectTicker={updateTicker}
            isLoading={watchlistScanLoading}
          />
        </div>

        {/* Token Usage Monitor */}
        <div className="mb-3">
          <TokenMonitor />
        </div>

        {/* Full Width - Risk & Account */}
        <RiskPanel
          account={account}
          positions={positions}
          riskStatus={riskStatus}
          selectedTicker={selectedTicker}
          isLoading={accountLoading}
          onClosePosition={(ticker) => closePositionMutation.mutate(ticker)}
          isClosingPosition={closePositionMutation.isPending}
        />
      </main>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <Suspense>
      <Dashboard />
    </Suspense>
  );
}
