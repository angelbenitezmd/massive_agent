"use client";

import { useState, useEffect, useCallback, useRef } from "react";
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
  useScanSpicy,
  useDeepAnalysis,
  useActivityLog,
  useLatestNews,
  useNews,
} from "@/hooks/use-trading-data";
import type { AgentSignal, TradeDecision, Technicals } from "@/types";

export default function DashboardPage() {
  const [selectedTicker, setSelectedTicker] = useState("AAPL");
  const [selectedTimeframe, setSelectedTimeframe] = useState("1Min");
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [autoTrade, setAutoTrade] = useState(false);
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
  const { data: account, isLoading: accountLoading } = useAccount();
  const { data: positions } = usePositions();
  const { data: riskStatus } = useRiskStatus();
  const { data: ordersData, isLoading: ordersLoading } = useOrders("all", 20, 7);
  const { data: ratings, isLoading: ratingsLoading } = useAnalystRatings(selectedTicker, 30, 10);
  const { data: watchlistScan, isLoading: watchlistScanLoading } = useScanWatchlist();
  const { data: spicyScan, isLoading: spicyScanLoading } = useScanSpicy();
  const { data: activityLog, isLoading: activityLogLoading } = useActivityLog(50);

  // Mutations
  const analysisMutation = useAnalysis(selectedTicker);
  const executeTradeMutation = useExecuteTrade();
  const deepAnalysisMutation = useDeepAnalysis(selectedTicker);

  // Deep analysis result state
  const [deepAnalysisResult, setDeepAnalysisResult] = useState<any>(null);

  // Execution management - prevent duplicate trades
  const lastExecutedSignalRef = useRef<string | null>(null);
  const isExecutingRef = useRef<boolean>(false);
  const lastExecutionTimeRef = useRef<number>(0);
  const EXECUTION_COOLDOWN_MS = 60000; // 1 minute cooldown between trades

  // Handle analysis
  const runAnalysis = useCallback(async () => {
    try {
      const result = await analysisMutation.mutateAsync();
      setAnalysisResult(result as any);
    } catch (error) {
      console.error("Analysis failed:", error);
    }
  }, [analysisMutation]);

  // Handle manual trade execution (from button click)
  const executeTrade = useCallback(async () => {
    if (!analysisResult?.decision) return;
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
      console.log(`[ManualTrade] Executing: ${analysisResult.decision.ticker}`);
      await executeTradeMutation.mutateAsync(analysisResult.decision);
    } catch (error) {
      console.error("[ManualTrade] Failed:", error);
    } finally {
      isExecutingRef.current = false;
    }
  }, [analysisResult?.decision, executeTradeMutation]);

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
      runAnalysis();
    }, 30000); // Every 30 seconds when auto-refresh is on

    return () => clearInterval(interval);
  }, [autoRefresh, runAnalysis]);

  // Auto-trade effect - with robust duplicate prevention
  useEffect(() => {
    // Early exits - must pass ALL checks
    if (!autoTrade) return;
    if (!analysisResult?.decision) return;
    if (isExecutingRef.current) return; // Already executing
    if (executeTradeMutation.isPending) return; // Mutation in progress

    const decision = analysisResult.decision;
    const now = Date.now();

    // Cooldown check - prevent rapid executions
    const timeSinceLastExecution = now - lastExecutionTimeRef.current;
    if (timeSinceLastExecution < EXECUTION_COOLDOWN_MS) {
      console.log(`[AutoTrade] Cooldown active: ${Math.ceil((EXECUTION_COOLDOWN_MS - timeSinceLastExecution) / 1000)}s remaining`);
      return;
    }

    // Create unique signal ID - only changes when ticker or action changes
    const signalId = `${decision.ticker}-${decision.action}`;

    // Skip if we already executed this exact signal
    if (lastExecutedSignalRef.current === signalId) {
      return;
    }

    // Check trade conditions
    const shouldTrade =
      decision.action === "BUY" &&
      decision.confidence >= 0.7 &&
      riskStatus?.circuitBreaker === "GREEN";

    if (!shouldTrade) return;

    // Lock execution
    isExecutingRef.current = true;
    lastExecutedSignalRef.current = signalId;
    lastExecutionTimeRef.current = now;

    console.log(`[AutoTrade] Executing: ${decision.ticker} ${decision.action} (confidence: ${decision.confidence})`);

    // Execute trade
    executeTradeMutation.mutateAsync(decision)
      .then((result) => {
        console.log(`[AutoTrade] Success:`, result);
      })
      .catch((error) => {
        console.error(`[AutoTrade] Failed:`, error);
        // Reset signal ID on failure so it can retry
        lastExecutedSignalRef.current = null;
      })
      .finally(() => {
        isExecutingRef.current = false;
      });

  }, [autoTrade, analysisResult?.decision, riskStatus?.circuitBreaker, executeTradeMutation]);

  // Reset signal tracking when ticker changes (allow new trades for new ticker)
  useEffect(() => {
    lastExecutedSignalRef.current = null;
  }, [selectedTicker]);

  return (
    <div className="min-h-screen bg-background">
      <Header
        selectedTicker={selectedTicker}
        onTickerChange={setSelectedTicker}
        autoRefresh={autoRefresh}
        onAutoRefreshChange={setAutoRefresh}
        autoTrade={autoTrade}
        onAutoTradeChange={setAutoTrade}
        onAnalyze={runAnalysis}
        isAnalyzing={analysisMutation.isPending}
        watchlist={watchlist || []}
      />

      <main className="container mx-auto px-4 py-3">
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

        {/* Top Row: News + Scanner/AI side by side */}
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-3 mb-3">
          {/* News Panels - Left 2 columns */}
          <NewsFeed
            news={globalNews}
            isLoading={globalNewsLoading}
            onTickerClick={setSelectedTicker}
          />
          <NewsFeed
            news={tickerNews}
            isLoading={tickerNewsLoading}
            onTickerClick={setSelectedTicker}
            selectedTicker={selectedTicker}
          />
          {/* Scanner + AI Agents - Right 2 columns */}
          <ScannerPanel
            selectedTicker={selectedTicker}
            onSelectTicker={setSelectedTicker}
          />
          <AIAgentsPanel
            ticker={selectedTicker}
            newsAgent={analysisResult?.agents?.news}
            earningsAgent={analysisResult?.agents?.earnings}
            technicalAgent={analysisResult?.agents?.technical}
            isLoading={analysisMutation.isPending}
          />
        </div>

        {/* Middle Row: Chart + Deep Analysis + Trade Decision */}
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-3 mb-3">
          {/* Market Snapshot - spans 2 columns */}
          <div className="lg:col-span-2">
            <MarketSnapshot
              quote={quote}
              technicals={analysisResult?.technicals}
              bars={bars}
              isLoading={quoteLoading || barsLoading}
              timeframe={selectedTimeframe}
              onTimeframeChange={setSelectedTimeframe}
            />
          </div>
          {/* Deep Analysis */}
          <DeepAnalysisPanel
            ticker={selectedTicker}
            result={deepAnalysisResult}
            isLoading={deepAnalysisMutation.isPending}
            onRunAnalysis={runDeepAnalysis}
          />
          {/* Trade Decision */}
          <TradeDecisionPanel
            decision={analysisResult?.decision}
            riskStatus={riskStatus}
            onExecuteTrade={executeTrade}
            isExecuting={executeTradeMutation.isPending}
            tradingMode={status?.tradingMode || "paper"}
          />
        </div>

        {/* Portfolio Heatmap */}
        {positions && positions.length > 0 && (
          <div className="mb-3">
            <PortfolioHeatmap
              positions={positions}
              onSelectTicker={setSelectedTicker}
              selectedTicker={selectedTicker}
            />
          </div>
        )}

        {/* Bottom Grid: 3x2 layout */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 mb-3">
          <TradeJournal
            orders={ordersData?.orders}
            isLoading={ordersLoading}
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
            spicyResults={spicyScan?.results}
            onSelectTicker={setSelectedTicker}
            isLoading={watchlistScanLoading || spicyScanLoading}
          />
        </div>

        {/* Full Width - Risk & Account */}
        <RiskPanel
          account={account}
          positions={positions}
          riskStatus={riskStatus}
          selectedTicker={selectedTicker}
          isLoading={accountLoading}
        />
      </main>
    </div>
  );
}
