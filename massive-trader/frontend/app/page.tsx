"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Header,
  MarketSnapshot,
  NewsPanel,
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
} from "@/components/dashboard";
import {
  useQuote,
  useBars,
  useNews,
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
} from "@/hooks/use-trading-data";
import type { AgentSignal, TradeDecision, Technicals } from "@/types";

export default function DashboardPage() {
  const [selectedTicker, setSelectedTicker] = useState("AAPL");
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
  const { data: bars, isLoading: barsLoading } = useBars(selectedTicker);
  const { data: news, isLoading: newsLoading } = useNews(selectedTicker);
  const { data: earnings, isLoading: earningsLoading } = useEarnings(selectedTicker);
  const { data: account, isLoading: accountLoading } = useAccount();
  const { data: positions } = usePositions();
  const { data: riskStatus } = useRiskStatus();
  const { data: ordersData, isLoading: ordersLoading } = useOrders("all", 20, 7);
  const { data: ratings, isLoading: ratingsLoading } = useAnalystRatings(selectedTicker, 30, 10);
  const { data: watchlistScan, isLoading: watchlistScanLoading } = useScanWatchlist();
  const { data: spicyScan, isLoading: spicyScanLoading } = useScanSpicy();

  // Mutations
  const analysisMutation = useAnalysis(selectedTicker);
  const executeTradeMutation = useExecuteTrade();
  const deepAnalysisMutation = useDeepAnalysis(selectedTicker);

  // Deep analysis result state
  const [deepAnalysisResult, setDeepAnalysisResult] = useState<any>(null);

  // Handle analysis
  const runAnalysis = useCallback(async () => {
    try {
      const result = await analysisMutation.mutateAsync();
      setAnalysisResult(result as any);
    } catch (error) {
      console.error("Analysis failed:", error);
    }
  }, [analysisMutation]);

  // Handle trade execution
  const executeTrade = useCallback(async () => {
    if (!analysisResult?.decision) return;
    try {
      await executeTradeMutation.mutateAsync(analysisResult.decision);
    } catch (error) {
      console.error("Trade execution failed:", error);
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

  // Auto-trade effect
  useEffect(() => {
    if (!autoTrade || !analysisResult?.decision) return;

    const decision = analysisResult.decision;
    if (
      decision.action === "BUY" &&
      decision.confidence >= 0.7 &&
      riskStatus?.circuitBreaker === "GREEN"
    ) {
      executeTrade();
    }
  }, [autoTrade, analysisResult?.decision, riskStatus?.circuitBreaker, executeTrade]);

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

      <main className="container mx-auto px-4 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left Column - Market Snapshot (spans 2 columns on large screens) */}
          <div className="lg:col-span-2 space-y-6">
            <MarketSnapshot
              quote={quote}
              technicals={analysisResult?.technicals}
              bars={bars}
              isLoading={quoteLoading || barsLoading}
            />

            <NewsPanel news={news} isLoading={newsLoading} />

            {/* New: Trade Journal and Analyst Ratings side by side */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <TradeJournal
                orders={ordersData?.orders}
                isLoading={ordersLoading}
              />
              <AnalystRatings
                ratings={ratings}
                selectedTicker={selectedTicker}
                isLoading={ratingsLoading}
              />
            </div>

            {/* Market Movers - fills remaining space */}
            <MarketMovers
              watchlistResults={watchlistScan?.results}
              spicyResults={spicyScan?.results}
              onSelectTicker={setSelectedTicker}
              isLoading={watchlistScanLoading || spicyScanLoading}
            />
          </div>

          {/* Right Column - AI Analysis & Trading */}
          <div className="space-y-6">
            <ScannerPanel
              selectedTicker={selectedTicker}
              onSelectTicker={setSelectedTicker}
            />

            <AIAgentsPanel
              newsAgent={analysisResult?.agents?.news}
              earningsAgent={analysisResult?.agents?.earnings}
              technicalAgent={analysisResult?.agents?.technical}
              isLoading={analysisMutation.isPending}
            />

            {/* Deep AI Analysis Panel */}
            <DeepAnalysisPanel
              ticker={selectedTicker}
              result={deepAnalysisResult}
              isLoading={deepAnalysisMutation.isPending}
              onRunAnalysis={runDeepAnalysis}
            />

            <TradeDecisionPanel
              decision={analysisResult?.decision}
              riskStatus={riskStatus}
              onExecuteTrade={executeTrade}
              isExecuting={executeTradeMutation.isPending}
              tradingMode={status?.tradingMode || "paper"}
            />

            <EarningsPanel earnings={earnings} isLoading={earningsLoading} />

            {/* New: Performance Stats */}
            <PerformanceStats
              account={account}
              positions={positions}
              riskStatus={riskStatus}
            />
          </div>
        </div>

        {/* Full Width Bottom Row - Risk & Positions */}
        <div className="mt-6">
          <RiskPanel
            account={account}
            positions={positions}
            riskStatus={riskStatus}
            selectedTicker={selectedTicker}
            isLoading={accountLoading}
          />
        </div>
      </main>
    </div>
  );
}
