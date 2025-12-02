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
import { cn } from "@/lib/utils";

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

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function ScannerPanel({ selectedTicker, onSelectTicker }: ScannerPanelProps) {
  const [scanType, setScanType] = useState<"watchlist" | "spicy">("watchlist");

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["scan", scanType],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/api/scan/${scanType}`);
      if (!res.ok) throw new Error("Scan failed");
      return res.json();
    },
    refetchInterval: 60000, // Auto-refresh every minute
    staleTime: 30000,
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
    <Card className="card-hover">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Radar className="h-5 w-5 text-primary" />
              Stock Scanner
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
        <ScrollArea className="h-[280px]">
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
                    <span className={cn("font-bold", getScoreColor(result.score))}>
                      {result.score}
                    </span>
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
        {data?.scan_time && (
          <div className="mt-2 text-xs text-muted-foreground text-center">
            Last scan: {new Date(data.scan_time).toLocaleTimeString()}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
