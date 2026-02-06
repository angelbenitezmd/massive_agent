"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Radar,
  TrendingUp,
  TrendingDown,
  Zap,
  RefreshCw,
  ChevronRight,
  Info,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { API_BASE } from "@/lib/api";

interface ScanResult {
  ticker: string;
  sentiment: string;
  score: number;
  recommendation: string;
}

interface ScannerPanelProps {
  selectedTicker: string;
  onSelectTicker: (ticker: string) => void;
}

export function ScannerPanel({ selectedTicker, onSelectTicker }: ScannerPanelProps) {
  const [scanType, setScanType] = useState<"watchlist" | "spicy">("watchlist");

  const { data, isLoading, refetch, isFetching, dataUpdatedAt } = useQuery({
    queryKey: ["scan", scanType],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/api/scan/${scanType}`);
      if (!res.ok) throw new Error("Scan failed");
      return res.json();
    },
    refetchInterval: 15000, // Auto-refresh every 15 seconds for real-time
    staleTime: 5000, // Consider stale after 5 seconds
    refetchOnWindowFocus: true,
    refetchIntervalInBackground: false,
  });

  const results: ScanResult[] = data?.results || [];

  // Sort by score descending
  const sortedResults = [...results].sort((a, b) => b.score - a.score);

  // Get top opportunities (BUY recommendations with score >= 70)
  const topOpportunities = sortedResults.filter(
    (r) => r.recommendation === "BUY" && r.score >= 70
  );

  const getScoreColor = (score: number) => {
    if (score >= 80) return "text-green-500";
    if (score >= 70) return "text-green-400";
    if (score >= 60) return "text-yellow-500";
    if (score >= 50) return "text-orange-500";
    return "text-red-500";
  };

  const getRecommendationBadge = (rec: string) => {
    switch (rec) {
      case "BUY":
        return <Badge variant="success" className="text-xs">BUY</Badge>;
      case "SELL":
        return <Badge variant="destructive" className="text-xs">SELL</Badge>;
      default:
        return <Badge variant="secondary" className="text-xs">HOLD</Badge>;
    }
  };

  const getSentimentIcon = (sentiment: string) => {
    if (sentiment.includes("bullish")) {
      return <TrendingUp className="h-3 w-3 text-green-500" />;
    }
    if (sentiment.includes("bearish")) {
      return <TrendingDown className="h-3 w-3 text-red-500" />;
    }
    return null;
  };

  return (
    <TooltipProvider>
    <Card className="card-hover">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Radar className="h-5 w-5 text-primary" />
              Stock Scanner
              <Tooltip>
                <TooltipTrigger asChild>
                  <Info className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground cursor-help" />
                </TooltipTrigger>
                <TooltipContent side="bottom" className="max-w-[280px] p-3">
                  <div className="space-y-2 text-xs">
                    <p className="font-semibold">Stock Scanner</p>
                    <p>Scans your watchlist and high-volatility stocks for trading opportunities using AI analysis.</p>
                    <div className="space-y-1 pt-1">
                      <p><strong>Watchlist:</strong> Stocks you&apos;re tracking</p>
                      <p><strong>High Volatility:</strong> Stocks with unusual movement</p>
                    </div>
                    <p className="text-muted-foreground">Score 70+ with BUY = strong opportunity. Click any ticker to analyze.</p>
                  </div>
                </TooltipContent>
              </Tooltip>
            </CardTitle>
            <CardDescription>
              {topOpportunities.length > 0
                ? `${topOpportunities.length} opportunities found`
                : "Scanning for opportunities..."}
            </CardDescription>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            disabled={isFetching}
          >
            <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} />
          </Button>
        </div>

        {/* Scan Type Toggle */}
        <div className="flex gap-2 mt-2">
          <Button
            variant={scanType === "watchlist" ? "default" : "outline"}
            size="sm"
            onClick={() => setScanType("watchlist")}
            className="text-xs"
          >
            Watchlist
          </Button>
          <Button
            variant={scanType === "spicy" ? "default" : "outline"}
            size="sm"
            onClick={() => setScanType("spicy")}
            className="text-xs"
          >
            <Zap className="h-3 w-3 mr-1" />
            High Volatility
          </Button>
        </div>
      </CardHeader>

      <CardContent>
        {/* Top Opportunities Alert */}
        {topOpportunities.length > 0 && (
          <div className="mb-3 p-2 rounded-lg bg-green-500/10 border border-green-500/20">
            <div className="flex items-center gap-2 text-sm font-medium text-green-500">
              <Zap className="h-4 w-4" />
              Top Opportunities
            </div>
            <div className="flex flex-wrap gap-1 mt-1">
              {topOpportunities.slice(0, 5).map((r) => (
                <Button
                  key={r.ticker}
                  variant="ghost"
                  size="sm"
                  className="h-6 px-2 text-xs font-bold text-green-500 hover:bg-green-500/20"
                  onClick={() => onSelectTicker(r.ticker)}
                >
                  {r.ticker} ({r.score})
                </Button>
              ))}
            </div>
          </div>
        )}

        {/* All Results */}
        <ScrollArea className="h-[140px]">
          {isLoading ? (
            <div className="space-y-2">
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="animate-pulse h-12 bg-secondary rounded" />
              ))}
            </div>
          ) : sortedResults.length > 0 ? (
            <div className="space-y-1">
              {sortedResults.map((result) => (
                <button
                  key={result.ticker}
                  onClick={() => onSelectTicker(result.ticker)}
                  className={cn(
                    "w-full flex items-center justify-between p-2 rounded-lg transition-colors text-left",
                    selectedTicker === result.ticker
                      ? "bg-primary/10 border border-primary/30"
                      : "hover:bg-secondary/50"
                  )}
                >
                  <div className="flex items-center gap-3">
                    <div className="flex items-center gap-1">
                      {getSentimentIcon(result.sentiment)}
                      <span className="font-semibold">{result.ticker}</span>
                    </div>
                    {getRecommendationBadge(result.recommendation)}
                  </div>
                  <div className="flex items-center gap-2">
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span className={cn("font-bold cursor-help", getScoreColor(result.score))}>
                          {result.score}
                        </span>
                      </TooltipTrigger>
                      <TooltipContent side="left" className="text-xs">
                        AI Score (0-100)
                      </TooltipContent>
                    </Tooltip>
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground py-8">
              <Radar className="h-12 w-12 mb-4 opacity-50" />
              <p>No scan results</p>
            </div>
          )}
        </ScrollArea>

        {/* Last Update */}
        <div className="mt-2 text-xs text-muted-foreground text-center flex items-center justify-center gap-2">
          {isFetching && <RefreshCw className="h-3 w-3 animate-spin" />}
          {dataUpdatedAt ? (
            <span>
              Updated: {new Date(dataUpdatedAt).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "America/New_York" })} ET
            </span>
          ) : (
            <span>Loading...</span>
          )}
        </div>
      </CardContent>
    </Card>
    </TooltipProvider>
  );
}
