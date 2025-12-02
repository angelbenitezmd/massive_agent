"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Flame, TrendingUp, TrendingDown, ArrowRight } from "lucide-react";

interface MoverItem {
  ticker: string;
  score: number;
  sentiment?: string;
  recommendation?: string;
}

interface MarketMoversProps {
  watchlistResults?: MoverItem[];
  spicyResults?: MoverItem[];
  onSelectTicker?: (ticker: string) => void;
  isLoading?: boolean;
}

export function MarketMovers({
  watchlistResults = [],
  spicyResults = [],
  onSelectTicker,
  isLoading,
}: MarketMoversProps) {
  // Get top gainers and losers from combined results
  const allResults = [...watchlistResults, ...spicyResults];
  const uniqueResults = allResults.filter(
    (item, index, self) => index === self.findIndex((t) => t.ticker === item.ticker)
  );

  const topBullish = uniqueResults
    .filter((r) => r.score >= 60)
    .sort((a, b) => b.score - a.score)
    .slice(0, 4);

  const topBearish = uniqueResults
    .filter((r) => r.score <= 40)
    .sort((a, b) => a.score - b.score)
    .slice(0, 4);

  const hotMomentum = spicyResults
    .filter((r) => r.score >= 65)
    .sort((a, b) => b.score - a.score)
    .slice(0, 3);

  return (
    <Card className="bg-card border-border">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Flame className="h-4 w-4 text-orange-500" />
          Market Movers
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="grid grid-cols-3 gap-4">
          {/* Bullish */}
          <div>
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-2">
              <TrendingUp className="h-3 w-3 text-green-500" />
              Bullish Signals
            </div>
            <div className="space-y-1.5">
              {isLoading ? (
                <div className="text-xs text-muted-foreground">Loading...</div>
              ) : topBullish.length === 0 ? (
                <div className="text-xs text-muted-foreground">No signals</div>
              ) : (
                topBullish.map((item) => (
                  <button
                    key={item.ticker}
                    onClick={() => onSelectTicker?.(item.ticker)}
                    className="w-full flex items-center justify-between p-1.5 rounded bg-green-500/10 hover:bg-green-500/20 transition-colors text-left"
                  >
                    <span className="font-medium text-sm text-green-500">
                      {item.ticker}
                    </span>
                    <Badge variant="secondary" className="text-[10px] bg-green-500/20 text-green-500">
                      {item.score}
                    </Badge>
                  </button>
                ))
              )}
            </div>
          </div>

          {/* Bearish */}
          <div>
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-2">
              <TrendingDown className="h-3 w-3 text-red-500" />
              Bearish Signals
            </div>
            <div className="space-y-1.5">
              {isLoading ? (
                <div className="text-xs text-muted-foreground">Loading...</div>
              ) : topBearish.length === 0 ? (
                <div className="text-xs text-muted-foreground">No signals</div>
              ) : (
                topBearish.map((item) => (
                  <button
                    key={item.ticker}
                    onClick={() => onSelectTicker?.(item.ticker)}
                    className="w-full flex items-center justify-between p-1.5 rounded bg-red-500/10 hover:bg-red-500/20 transition-colors text-left"
                  >
                    <span className="font-medium text-sm text-red-500">
                      {item.ticker}
                    </span>
                    <Badge variant="secondary" className="text-[10px] bg-red-500/20 text-red-500">
                      {item.score}
                    </Badge>
                  </button>
                ))
              )}
            </div>
          </div>

          {/* Hot Momentum */}
          <div>
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-2">
              <Flame className="h-3 w-3 text-orange-500" />
              Hot Momentum
            </div>
            <div className="space-y-1.5">
              {isLoading ? (
                <div className="text-xs text-muted-foreground">Loading...</div>
              ) : hotMomentum.length === 0 ? (
                <div className="text-xs text-muted-foreground">No hot picks</div>
              ) : (
                hotMomentum.map((item) => (
                  <button
                    key={item.ticker}
                    onClick={() => onSelectTicker?.(item.ticker)}
                    className="w-full flex items-center justify-between p-1.5 rounded bg-orange-500/10 hover:bg-orange-500/20 transition-colors text-left"
                  >
                    <span className="font-medium text-sm text-orange-500">
                      {item.ticker}
                    </span>
                    <div className="flex items-center gap-1">
                      <Badge variant="secondary" className="text-[10px] bg-orange-500/20 text-orange-500">
                        {item.score}
                      </Badge>
                      <ArrowRight className="h-3 w-3 text-orange-500" />
                    </div>
                  </button>
                ))
              )}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
