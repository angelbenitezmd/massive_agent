"use client";

import { memo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  BarChart3,
  TrendingUp,
  TrendingDown,
  Activity,
  Zap,
  Target,
  Info,
} from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { Account, Position } from "@/types";

interface PerformanceStatsProps {
  account?: Account | null;
  positions?: Position[];
  riskStatus?: {
    circuitBreaker: string;
    dailyPL: number;
    dailyPLPercent: number;
    tradesToday: number;
  };
}

export const PerformanceStats = memo(function PerformanceStats({
  account,
  positions = [],
  riskStatus,
}: PerformanceStatsProps) {
  // Calculate portfolio stats
  const totalUnrealizedPL = positions.reduce((sum, p) => sum + p.unrealizedPL, 0);
  const totalMarketValue = positions.reduce((sum, p) => sum + p.marketValue, 0);

  // Calculate sector/diversification (simplified)
  const uniqueSymbols = new Set(positions.map((p) => p.symbol)).size;

  // Position size distribution
  const largestPosition = positions.length > 0
    ? Math.max(...positions.map((p) => Math.abs(p.marketValue)))
    : 0;
  const portfolioConcentration = account?.portfolioValue && largestPosition > 0
    ? (largestPosition / account.portfolioValue) * 100
    : 0;

  // Risk metrics
  const maxDrawdown = riskStatus?.dailyPLPercent
    ? Math.min(0, riskStatus.dailyPLPercent)
    : 0;
  const drawdownProgress = Math.abs(maxDrawdown) / 5; // 5% max drawdown scale

  return (
    <TooltipProvider>
    <Card className="bg-card border-border">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <BarChart3 className="h-4 w-4 text-primary" />
          Performance Stats
          <Tooltip>
            <TooltipTrigger asChild>
              <Info className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground cursor-help" />
            </TooltipTrigger>
            <TooltipContent side="bottom" className="max-w-[300px] p-3">
              <div className="space-y-2 text-xs">
                <p className="font-semibold">Performance Stats</p>
                <div className="space-y-1.5">
                  <p><strong>Unrealized P&L:</strong> Profit/loss on open positions (not yet sold).</p>
                  <p><strong>Daily Drawdown:</strong> Today&apos;s loss from peak. Triggers circuit breaker at -5%.</p>
                  <p><strong>Largest Position:</strong> Concentration risk. Green &lt;20%, Yellow &lt;40%, Red 40%+.</p>
                  <p><strong>Buying Power:</strong> Capital available for new trades (includes margin).</p>
                </div>
              </div>
            </TooltipContent>
          </Tooltip>
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0 space-y-4">
        {/* Quick Stats Grid */}
        <div className="grid grid-cols-2 gap-2">
          {/* Unrealized P&L */}
          <div className="bg-muted/50 rounded-lg p-3">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
              {totalUnrealizedPL >= 0 ? (
                <TrendingUp className="h-3 w-3 text-green-500" />
              ) : (
                <TrendingDown className="h-3 w-3 text-red-500" />
              )}
              Unrealized P&L
            </div>
            <div
              className={`text-lg font-bold ${
                totalUnrealizedPL >= 0 ? "text-green-500" : "text-red-500"
              }`}
            >
              {totalUnrealizedPL >= 0 ? "+" : ""}${totalUnrealizedPL.toFixed(2)}
            </div>
          </div>

          {/* Trades Today */}
          <div className="bg-muted/50 rounded-lg p-3">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
              <Zap className="h-3 w-3" />
              Trades Today
            </div>
            <div className="text-lg font-bold">
              {riskStatus?.tradesToday || 0}
            </div>
          </div>

          {/* Active Positions */}
          <div className="bg-muted/50 rounded-lg p-3">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
              <Activity className="h-3 w-3" />
              Active Positions
            </div>
            <div className="text-lg font-bold">{positions.length}</div>
            <div className="text-[10px] text-muted-foreground">
              {uniqueSymbols} unique symbols
            </div>
          </div>

          {/* Market Value */}
          <div className="bg-muted/50 rounded-lg p-3">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
              <Target className="h-3 w-3" />
              Total Exposure
            </div>
            <div className="text-lg font-bold">
              ${totalMarketValue.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </div>
            {account?.portfolioValue && (
              <div className="text-[10px] text-muted-foreground">
                {((totalMarketValue / account.portfolioValue) * 100).toFixed(1)}% of portfolio
              </div>
            )}
          </div>
        </div>

        {/* Risk Gauges */}
        <div className="space-y-3">
          {/* Drawdown Gauge */}
          <div>
            <div className="flex items-center justify-between text-xs mb-1">
              <span className="text-muted-foreground">Daily Drawdown</span>
              <span
                className={
                  maxDrawdown === 0
                    ? "text-green-500"
                    : maxDrawdown > -2
                    ? "text-yellow-500"
                    : "text-red-500"
                }
              >
                {maxDrawdown.toFixed(2)}%
              </span>
            </div>
            <Progress
              value={drawdownProgress * 100}
              className="h-2"
            />
            <div className="flex justify-between text-[10px] text-muted-foreground mt-0.5">
              <span>0%</span>
              <span>-5% limit</span>
            </div>
          </div>

          {/* Portfolio Concentration */}
          <div>
            <div className="flex items-center justify-between text-xs mb-1">
              <span className="text-muted-foreground">Largest Position</span>
              <span
                className={
                  portfolioConcentration < 20
                    ? "text-green-500"
                    : portfolioConcentration < 40
                    ? "text-yellow-500"
                    : "text-red-500"
                }
              >
                {portfolioConcentration.toFixed(1)}%
              </span>
            </div>
            <Progress
              value={portfolioConcentration}
              className="h-2"
            />
            <div className="flex justify-between text-[10px] text-muted-foreground mt-0.5">
              <span>Diversified</span>
              <span>Concentrated</span>
            </div>
          </div>
        </div>

        {/* Buying Power Indicator */}
        {account && (
          <div className="bg-muted/30 rounded-lg p-3">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-xs text-muted-foreground">Available Buying Power</div>
                <div className="text-lg font-bold text-green-500">
                  ${account.buyingPower.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </div>
              </div>
              <div className="text-right">
                <div className="text-xs text-muted-foreground">Cash</div>
                <div className="text-sm font-medium">
                  ${account.cash.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </div>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
    </TooltipProvider>
  );
});
