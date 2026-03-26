"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import * as api from "@/lib/api";
import type { TradeDecision } from "@/types";

export function useSystemStatus() {
  return useQuery({
    queryKey: ["systemStatus"],
    queryFn: api.getSystemStatus,
    refetchInterval: 30000,
    staleTime: 10000,
  });
}

export function useQuote(ticker: string, enabled: boolean = true) {
  return useQuery({
    queryKey: ["quote", ticker],
    queryFn: () => api.getQuote(ticker),
    enabled: enabled && !!ticker,
    refetchInterval: 5000,
    staleTime: 2000,
  });
}

export function useBars(
  ticker: string,
  timeframe: string = "1Min",
  limit: number = 100
) {
  return useQuery({
    queryKey: ["bars", ticker, timeframe, limit],
    queryFn: () => api.getBars(ticker, timeframe, limit),
    enabled: !!ticker,
    staleTime: 30000,
  });
}

export function useNews(ticker: string) {
  return useQuery({
    queryKey: ["news", ticker],
    queryFn: () => api.getNews(ticker),
    enabled: !!ticker,
    staleTime: 60000,
  });
}

// Global news feed (no ticker filter) - full day of news
export function useLatestNews(limit: number = 30) {
  return useQuery({
    queryKey: ["news", "all", limit],
    queryFn: () => api.getNews(undefined, limit),
    staleTime: 60000,  // Cache for 1 minute
    refetchInterval: 120000,  // Refresh every 2 minutes
  });
}

// Live news feed that drives the scan (feed-first: last 30 min, same as scanner)
export function useNewsFeed() {
  return useQuery({
    queryKey: ["news", "feed"],
    queryFn: api.getNewsFeed,
    refetchInterval: 15000,  // Match scanner refresh
    staleTime: 10000,
  });
}

export function useEarnings(ticker: string) {
  return useQuery({
    queryKey: ["earnings", ticker],
    queryFn: () => api.getEarnings(ticker),
    enabled: !!ticker,
    staleTime: 300000,
  });
}

export function useAnalysis(ticker: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.runAnalysis(ticker),
    onSuccess: (data) => {
      queryClient.setQueryData(["analysis", ticker], data);
    },
  });
}

export function useSentiment(ticker: string) {
  return useQuery({
    queryKey: ["sentiment", ticker],
    queryFn: () => api.getSentiment(ticker),
    enabled: !!ticker,
    staleTime: 60000,
  });
}

export function useAccount() {
  return useQuery({
    queryKey: ["account"],
    queryFn: api.getAccount,
    refetchInterval: 30000,
    staleTime: 10000,
  });
}

export function usePositions() {
  return useQuery({
    queryKey: ["positions"],
    queryFn: api.getPositions,
    refetchInterval: 5000,  // Every 5 sec for real-time P&L
    staleTime: 2000,
    refetchOnWindowFocus: true,
  });
}

export function useRiskStatus() {
  return useQuery({
    queryKey: ["risk"],
    queryFn: api.getRiskStatus,
    refetchInterval: 15000,
    staleTime: 5000,
  });
}

export function useWatchlist() {
  return useQuery({
    queryKey: ["watchlist"],
    queryFn: api.getWatchlist,
    staleTime: 300000,
  });
}

export function useExecuteTrade() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (decision: TradeDecision) => api.executeTrade(decision),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["account"] });
      queryClient.invalidateQueries({ queryKey: ["positions"] });
      queryClient.invalidateQueries({ queryKey: ["risk"] });
    },
  });
}

export function usePanicClose() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.panicCloseAll(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["account"] });
      queryClient.invalidateQueries({ queryKey: ["positions"] });
      queryClient.invalidateQueries({ queryKey: ["risk"] });
      queryClient.invalidateQueries({ queryKey: ["orders"] });
    },
  });
}

export function useCancelAllOrders() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.cancelAllOrders(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["orders"] });
    },
  });
}

export function useCloseAllPositions() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.closeAllPositions(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["account"] });
      queryClient.invalidateQueries({ queryKey: ["positions"] });
      queryClient.invalidateQueries({ queryKey: ["risk"] });
    },
  });
}

export function useClosePosition() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (ticker: string) => api.closePosition(ticker),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["account"] });
      queryClient.invalidateQueries({ queryKey: ["positions"] });
      queryClient.invalidateQueries({ queryKey: ["risk"] });
    },
  });
}

export function usePremarketStatus() {
  return useQuery({
    queryKey: ["premarket", "status"],
    queryFn: api.getPremarketStatus,
    refetchInterval: 15000, // 15s — pre-market changes slowly
    staleTime: 10000,
  });
}

export function useScanWatchlist() {
  return useQuery({
    queryKey: ["scan", "watchlist"],
    queryFn: api.scanWatchlist,
    staleTime: 10000,  // 10 sec
    refetchInterval: 20000,  // Refresh every 20 sec
    refetchOnWindowFocus: true,
  });
}

export function useScanTrending() {
  return useQuery({
    queryKey: ["scan", "trending"],
    queryFn: api.scanTrending,
    staleTime: 60000,  // 1 min
    refetchInterval: 300000,  // 5 min (matches backend cache TTL)
  });
}

export function useAllDecisions() {
  return useQuery({
    queryKey: ["trading", "all-decisions"],
    queryFn: api.getAllDecisions,
    staleTime: 10000,  // 10 sec - stay fresh
    refetchInterval: 20000,  // Refresh every 20 sec for real-time
    refetchOnWindowFocus: true,
  });
}


export function useOrders(status: string = "all", limit: number = 50, days: number = 7) {
  return useQuery({
    queryKey: ["orders", status, limit, days],
    queryFn: () => api.getOrders(status, limit, days),
    staleTime: 30000,
    refetchInterval: 60000,
  });
}

export function useAnalystRatings(ticker?: string, daysBack: number = 30, limit: number = 20) {
  return useQuery({
    queryKey: ["ratings", ticker, daysBack, limit],
    queryFn: () => api.getAnalystRatings(ticker, daysBack, limit),
    staleTime: 300000,
  });
}

export function useConsensusRating(ticker: string) {
  return useQuery({
    queryKey: ["consensus", ticker],
    queryFn: () => api.getConsensusRating(ticker),
    enabled: !!ticker,
    staleTime: 300000,
  });
}

export function useDeepAnalysis(ticker: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.getDeepAnalysis(ticker),
    onSuccess: (data) => {
      queryClient.setQueryData(["deepAnalysis", ticker], data);
    },
  });
}

export function useActivityLog(limit: number = 50) {
  return useQuery({
    queryKey: ["activityLog", limit],
    queryFn: () => api.getActivityLog(limit),
    refetchInterval: 10000,
    staleTime: 5000,
  });
}

export function usePortfolioHistory(period: string = "1M", timeframe: string = "1D") {
  return useQuery({
    queryKey: ["portfolioHistory", period, timeframe],
    queryFn: () => api.getPortfolioHistory(period, timeframe),
    staleTime: 60000, // 1 minute
    refetchInterval: 300000, // 5 minutes
  });
}

// Auto-Trade hooks (backend-controlled 24/7 trading)
export function useAutoTradeStatus() {
  return useQuery({
    queryKey: ["autoTradeStatus"],
    queryFn: api.getAutoTradeStatus,
    refetchInterval: 10000, // Check status every 10s
    staleTime: 5000,
  });
}

export function useEnableAutoTrade() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (interval: number = 60) => api.enableAutoTrade(interval),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["autoTradeStatus"] });
    },
  });
}

export function useDisableAutoTrade() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.disableAutoTrade,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["autoTradeStatus"] });
    },
  });
}

// Manual Trade hook
export interface ManualTradeRequest {
  ticker: string;
  side: "buy" | "sell";
  quantity: number;
  order_type: "market" | "limit" | "stop" | "bracket";
  limit_price?: number;
  stop_loss?: number;
  take_profit?: number;
  time_in_force: "day" | "gtc";
}

export function useManualTrade() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (trade: ManualTradeRequest) => api.executeManualTrade(trade),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["account"] });
      queryClient.invalidateQueries({ queryKey: ["positions"] });
      queryClient.invalidateQueries({ queryKey: ["risk"] });
      queryClient.invalidateQueries({ queryKey: ["orders"] });
      queryClient.invalidateQueries({ queryKey: ["activityLog"] });
    },
  });
}

// ============= DEBATE SYSTEM HOOKS =============

// Run multi-agent debate for a ticker (mutation - expensive operation)
export function useDebate(ticker: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.getDebate(ticker),
    onSuccess: (data) => {
      queryClient.setQueryData(["debate", ticker], data);
    },
  });
}

// Get cached debate result for a ticker
export function useDebateResult(ticker: string) {
  return useQuery({
    queryKey: ["debate", ticker],
    queryFn: () => api.getDebate(ticker),
    enabled: false, // Only fetch when explicitly triggered
    staleTime: 60000, // Cache for 1 minute
  });
}

// Get agent performance metrics
export function useAgentPerformance(period: string = "month", regime?: string) {
  return useQuery({
    queryKey: ["agentPerformance", period, regime],
    queryFn: () => api.getAgentPerformance(period, regime),
    staleTime: 300000, // 5 minutes
    refetchInterval: 600000, // 10 minutes
  });
}

// Get current agent weights
export function useAgentWeights(regime?: string) {
  return useQuery({
    queryKey: ["agentWeights", regime],
    queryFn: () => api.getAgentWeights(regime),
    staleTime: 300000, // 5 minutes
    refetchInterval: 600000, // 10 minutes
  });
}

// Get similar past trades for a ticker
export function useSimilarTrades(ticker: string, limit: number = 10) {
  return useQuery({
    queryKey: ["similarTrades", ticker, limit],
    queryFn: () => api.getSimilarTrades(ticker, limit),
    enabled: !!ticker,
    staleTime: 60000, // 1 minute
  });
}

// Get memory statistics
export function useMemoryStats() {
  return useQuery({
    queryKey: ["memoryStats"],
    queryFn: api.getMemoryStats,
    staleTime: 60000, // 1 minute
    refetchInterval: 300000, // 5 minutes
  });
}

// Ranked news dashboard (keyword-scored, refreshes every 60s)
export function useRankedNews() {
  return useQuery({
    queryKey: ["rankedNews"],
    queryFn: api.getRankedNews,
    refetchInterval: 60000,
    staleTime: 30000,
  });
}

// Token usage monitoring
export function useTokenUsage() {
  return useQuery({
    queryKey: ["tokenUsage"],
    queryFn: api.getTokenUsage,
    refetchInterval: 10000,
    staleTime: 5000,
  });
}

// Get decision context for a ticker
export function useDecisionContext(ticker: string) {
  return useQuery({
    queryKey: ["decisionContext", ticker],
    queryFn: () => api.getDecisionContext(ticker),
    enabled: !!ticker,
    staleTime: 60000, // 1 minute
  });
}
