"use client";

import {
  Shield,
  Wallet,
  TrendingUp,
  TrendingDown,
  Activity,
  AlertTriangle,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import {
  formatCurrency,
  formatPercent,
  getCircuitBreakerColor,
  cn,
} from "@/lib/utils";
import type { Account, Position, RiskStatus } from "@/types";

interface RiskPanelProps {
  account: Account | undefined;
  positions: Position[] | undefined;
  riskStatus: RiskStatus | undefined;
  selectedTicker: string;
  isLoading: boolean;
}

export function RiskPanel({
  account,
  positions,
  riskStatus,
  selectedTicker,
  isLoading,
}: RiskPanelProps) {
  const currentPosition = positions?.find((p) => p.symbol === selectedTicker);

  const getCircuitBreakerLabel = (level: string) => {
    switch (level) {
      case "GREEN":
        return "Normal Trading";
      case "YELLOW":
        return "Reduced Position Size";
      case "ORANGE":
        return "No New Positions";
      case "RED":
        return "Trading Halted";
      default:
        return "Unknown";
    }
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Risk & Account
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="animate-pulse space-y-4">
            <div className="h-24 bg-secondary rounded" />
            <div className="h-16 bg-secondary rounded" />
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="card-hover">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2">
          <Shield className="h-5 w-5 text-primary" />
          Risk & Account
        </CardTitle>
        <CardDescription>Portfolio status and risk controls</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Circuit Breaker Status */}
        {riskStatus && (
          <div className="p-4 rounded-lg bg-secondary/30 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <AlertTriangle className="h-5 w-5" />
                <span className="font-medium">Circuit Breaker</span>
              </div>
              <div className="flex items-center gap-2">
                <div
                  className={cn(
                    "w-3 h-3 rounded-full animate-pulse",
                    getCircuitBreakerColor(riskStatus.circuitBreaker)
                  )}
                />
                <Badge
                  variant={
                    riskStatus.circuitBreaker === "GREEN"
                      ? "success"
                      : riskStatus.circuitBreaker === "RED"
                      ? "destructive"
                      : "warning"
                  }
                >
                  {riskStatus.circuitBreaker}
                </Badge>
              </div>
            </div>
            <p className="text-sm text-muted-foreground">
              {getCircuitBreakerLabel(riskStatus.circuitBreaker)}
            </p>

            {/* Daily P&L */}
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Daily P&L</span>
              <span
                className={cn(
                  "font-medium",
                  riskStatus.dailyPL >= 0 ? "text-green-500" : "text-red-500"
                )}
              >
                {formatCurrency(riskStatus.dailyPL)} (
                {formatPercent(riskStatus.dailyPLPercent)})
              </span>
            </div>

            {/* Drawdown Progress */}
            <div className="space-y-1">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Drawdown</span>
                <span>
                  {formatPercent(riskStatus.currentDrawdown)} /{" "}
                  {formatPercent(riskStatus.maxDailyLoss * 100)} max
                </span>
              </div>
              <Progress
                value={
                  (Math.abs(riskStatus.currentDrawdown) /
                    (riskStatus.maxDailyLoss * 100)) *
                  100
                }
                className={cn(
                  "h-2",
                  riskStatus.currentDrawdown < -3
                    ? "[&>div]:bg-red-500"
                    : "[&>div]:bg-yellow-500"
                )}
              />
            </div>

            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Trades Today</span>
              <span className="font-medium">{riskStatus.tradesToday}</span>
            </div>
          </div>
        )}

        <Separator />

        {/* Account Summary */}
        {account && (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <Wallet className="h-4 w-4 text-muted-foreground" />
              <span className="font-medium">Account Summary</span>
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="space-y-1">
                <div className="text-muted-foreground">Equity</div>
                <div className="font-medium text-lg">
                  {formatCurrency(account.equity)}
                </div>
              </div>
              <div className="space-y-1">
                <div className="text-muted-foreground">Cash</div>
                <div className="font-medium text-lg">
                  {formatCurrency(account.cash)}
                </div>
              </div>
              <div className="space-y-1">
                <div className="text-muted-foreground">Buying Power</div>
                <div className="font-medium">
                  {formatCurrency(account.buyingPower)}
                </div>
              </div>
              <div className="space-y-1">
                <div className="text-muted-foreground">Day Trades</div>
                <div className="font-medium">{account.dayTradeCount} / 3</div>
              </div>
            </div>
          </div>
        )}

        {/* Current Position */}
        {currentPosition && (
          <>
            <Separator />
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <Activity className="h-4 w-4 text-muted-foreground" />
                <span className="font-medium">
                  Position in {currentPosition.symbol}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div className="space-y-1">
                  <div className="text-muted-foreground">Quantity</div>
                  <div className="font-medium">
                    {currentPosition.quantity} shares
                  </div>
                </div>
                <div className="space-y-1">
                  <div className="text-muted-foreground">Avg Entry</div>
                  <div className="font-medium">
                    {formatCurrency(currentPosition.avgEntryPrice)}
                  </div>
                </div>
                <div className="space-y-1">
                  <div className="text-muted-foreground">Market Value</div>
                  <div className="font-medium">
                    {formatCurrency(currentPosition.marketValue)}
                  </div>
                </div>
                <div className="space-y-1">
                  <div className="text-muted-foreground">Unrealized P&L</div>
                  <div
                    className={cn(
                      "font-medium flex items-center gap-1",
                      currentPosition.unrealizedPL >= 0
                        ? "text-green-500"
                        : "text-red-500"
                    )}
                  >
                    {currentPosition.unrealizedPL >= 0 ? (
                      <TrendingUp className="h-3 w-3" />
                    ) : (
                      <TrendingDown className="h-3 w-3" />
                    )}
                    {formatCurrency(currentPosition.unrealizedPL)} (
                    {formatPercent(currentPosition.unrealizedPLPercent * 100)})
                  </div>
                </div>
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
