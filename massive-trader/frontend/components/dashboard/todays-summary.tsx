"use client";

import { memo } from "react";
import {
  TrendingUp,
  TrendingDown,
  Activity,
  Target,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Flame,
  Snowflake,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn, formatCurrency, formatPercent } from "@/lib/utils";
import type { Account, Position } from "@/types";

interface TodaysSummaryProps {
  account?: Account | null;
  positions?: Position[];
  riskStatus?: {
    circuitBreaker: string;
    dailyPL: number;
    dailyPLPercent: number;
    tradesToday: number;
  };
  activityLog?: Array<{
    type: string;
    ticker: string;
    details: {
      pnl_pct?: number;
      reason?: string;
    };
  }>;
  realizedPL?: number;  // P&L from closed trades today
}

export const TodaysSummary = memo(function TodaysSummary({
  account,
  positions = [],
  riskStatus,
  activityLog = [],
  realizedPL = 0,
}: TodaysSummaryProps) {
  // Calculate today's stats - TOTAL = realized (closed trades) + unrealized (open positions)
  const totalUnrealizedPL = positions.reduce((sum, p) => sum + p.unrealizedPL, 0);
  const totalPL = realizedPL + totalUnrealizedPL;  // Combined P&L
  const totalPLPct = account?.portfolioValue
    ? (totalPL / account.portfolioValue) * 100
    : 0;

  // Count winning/losing positions
  const winningPositions = positions.filter((p) => p.unrealizedPL > 0).length;
  const losingPositions = positions.filter((p) => p.unrealizedPL < 0).length;

  // Find best and worst performers
  const sortedByPL = [...positions].sort((a, b) => b.unrealizedPLPercent - a.unrealizedPLPercent);
  const bestPerformer = sortedByPL[0];
  const worstPerformer = sortedByPL[sortedByPL.length - 1];

  // Count today's trades from activity log
  const todaysTrades = activityLog.filter((log) =>
    log.type === "TRADE" || log.type === "AUTO_EXIT"
  ).length;

  // Calculate win rate from exits
  const exits = activityLog.filter((log) => log.type === "AUTO_EXIT");
  const profitableExits = exits.filter((log) => (log.details?.pnl_pct || 0) > 0).length;
  const winRate = exits.length > 0 ? (profitableExits / exits.length) * 100 : 0;

  // Determine market sentiment based on positions
  const bullishCount = positions.filter((p) => p.unrealizedPLPercent > 2).length;
  const bearishCount = positions.filter((p) => p.unrealizedPLPercent < -2).length;
  const sentiment = bullishCount > bearishCount ? "bullish" : bearishCount > bullishCount ? "bearish" : "neutral";

  return (
    <Card className="bg-gradient-to-r from-card to-card/80 border-primary/20">
      <CardContent className="py-3 px-4">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          {/* Today's P&L (Realized + Unrealized) */}
          <div className="flex items-center gap-3">
            <div className={cn(
              "p-2 rounded-lg",
              totalPL >= 0 ? "bg-green-500/20" : "bg-red-500/20"
            )}>
              {totalPL >= 0 ? (
                <TrendingUp className="h-5 w-5 text-green-500" />
              ) : (
                <TrendingDown className="h-5 w-5 text-red-500" />
              )}
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Today&apos;s P&L</div>
              <div className={cn(
                "text-lg font-bold",
                totalPL >= 0 ? "text-green-500" : "text-red-500"
              )}>
                {totalPL >= 0 ? "+" : ""}{formatCurrency(totalPL)}
                <span className="text-xs font-normal ml-1">
                  ({formatPercent(totalPLPct)})
                </span>
              </div>
            </div>
          </div>

          {/* Win/Loss */}
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1">
              <CheckCircle className="h-4 w-4 text-green-500" />
              <span className="font-semibold text-green-500">{winningPositions}</span>
            </div>
            <span className="text-muted-foreground">/</span>
            <div className="flex items-center gap-1">
              <XCircle className="h-4 w-4 text-red-500" />
              <span className="font-semibold text-red-500">{losingPositions}</span>
            </div>
            <span className="text-xs text-muted-foreground ml-1">positions</span>
          </div>

          {/* Best Performer */}
          {bestPerformer && bestPerformer.unrealizedPLPercent > 0 && (
            <div className="flex items-center gap-2">
              <Flame className="h-4 w-4 text-orange-500" />
              <div>
                <div className="text-xs text-muted-foreground">Hot</div>
                <div className="flex items-center gap-1">
                  <span className="font-semibold text-sm">{bestPerformer.symbol}</span>
                  <Badge variant="success" className="text-[10px]">
                    +{bestPerformer.unrealizedPLPercent.toFixed(1)}%
                  </Badge>
                </div>
              </div>
            </div>
          )}

          {/* Worst Performer */}
          {worstPerformer && worstPerformer.unrealizedPLPercent < 0 && (
            <div className="flex items-center gap-2">
              <Snowflake className="h-4 w-4 text-blue-500" />
              <div>
                <div className="text-xs text-muted-foreground">Cold</div>
                <div className="flex items-center gap-1">
                  <span className="font-semibold text-sm">{worstPerformer.symbol}</span>
                  <Badge variant="danger" className="text-[10px]">
                    {worstPerformer.unrealizedPLPercent.toFixed(1)}%
                  </Badge>
                </div>
              </div>
            </div>
          )}

          {/* Trades Today */}
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-primary" />
            <div>
              <div className="text-xs text-muted-foreground">Trades</div>
              <div className="font-semibold">{todaysTrades}</div>
            </div>
          </div>

          {/* Circuit Breaker Status */}
          <div className="flex items-center gap-2">
            {riskStatus?.circuitBreaker === "GREEN" ? (
              <Badge variant="success" className="gap-1">
                <Target className="h-3 w-3" />
                Trading Active
              </Badge>
            ) : riskStatus?.circuitBreaker === "ORANGE" ? (
              <Badge variant="warning" className="gap-1">
                <AlertTriangle className="h-3 w-3" />
                Caution
              </Badge>
            ) : (
              <Badge variant="destructive" className="gap-1">
                <AlertTriangle className="h-3 w-3" />
                Circuit Breaker
              </Badge>
            )}
          </div>

          {/* Portfolio Sentiment */}
          <div className="flex items-center gap-2">
            <Badge
              variant="outline"
              className={cn(
                "capitalize",
                sentiment === "bullish" && "border-green-500 text-green-500",
                sentiment === "bearish" && "border-red-500 text-red-500",
                sentiment === "neutral" && "border-yellow-500 text-yellow-500"
              )}
            >
              {sentiment === "bullish" && <TrendingUp className="h-3 w-3 mr-1" />}
              {sentiment === "bearish" && <TrendingDown className="h-3 w-3 mr-1" />}
              {sentiment}
            </Badge>
          </div>
        </div>
      </CardContent>
    </Card>
  );
});
