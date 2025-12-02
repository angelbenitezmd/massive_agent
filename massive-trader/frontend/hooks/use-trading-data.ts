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
    refetchInterval: 10000,
    staleTime: 5000,
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

export function useScanWatchlist() {
  return useQuery({
    queryKey: ["scan", "watchlist"],
    queryFn: api.scanWatchlist,
    staleTime: 60000,
  });
}

export function useScanUniverse() {
  return useQuery({
    queryKey: ["scan", "universe"],
    queryFn: api.scanUniverse,
    staleTime: 60000,
  });
}

export function useScanSpicy() {
  return useQuery({
    queryKey: ["scan", "spicy"],
    queryFn: api.scanSpicy,
    staleTime: 60000,
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
