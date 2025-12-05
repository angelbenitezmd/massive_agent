"use client";

import {
  Shield,
  Wallet,
  TrendingUp,
  TrendingDown,
  Activity,
  AlertTriangle,
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
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
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
    <TooltipProvider>
      <Card className="card-hover">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5 text-primary" />
            Risk & Account
            <Tooltip>
              <TooltipTrigger asChild>
                <Info className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground cursor-help" />
              </TooltipTrigger>
              <TooltipContent side="bottom" className="max-w-[300px] p-3">
                <div className="space-y-2 text-xs">
                  <p className="font-semibold">Risk Management</p>
                  <div className="space-y-1.5">
                    <p><strong>Circuit Breaker:</strong> Automatic trading limits based on daily P&L.</p>
                    <p className="pl-2 text-muted-foreground">GREEN: Normal | YELLOW: -2% | ORANGE: -3% | RED: -5%</p>
                    <p><strong>Buying Power:</strong> Available capital for new trades (includes margin).</p>
                    <p><strong>Daily P&L:</strong> Today&apos;s profit/loss across all positions.</p>
                  </div>
                </div>
              </TooltipContent>
            </Tooltip>
          </CardTitle>
          <CardDescription>Portfolio status, risk controls, and positions</CardDescription>
        </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left: Circuit Breaker & Risk */}
          <div className="space-y-4">
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
          </div>

          {/* Middle: Account Summary */}
          <div className="space-y-4">
            {account && (
              <div className="p-4 rounded-lg bg-secondary/30 space-y-3">
                <div className="flex items-center gap-2 mb-2">
                  <Wallet className="h-4 w-4 text-muted-foreground" />
                  <span className="font-medium">Account Summary</span>
                </div>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div className="space-y-1">
                    <div className="text-muted-foreground">Equity</div>
                    <div className="font-semibold text-xl">
                      {formatCurrency(account.equity)}
                    </div>
                  </div>
                  <div className="space-y-1">
                    <div className="text-muted-foreground">Cash</div>
                    <div className="font-semibold text-xl">
                      {formatCurrency(account.cash)}
                    </div>
                  </div>
                  <div className="space-y-1">
                    <div className="text-muted-foreground">Buying Power</div>
                    <div className="font-medium text-lg">
                      {formatCurrency(account.buyingPower)}
                    </div>
                  </div>
                  <div className="space-y-1">
                    <div className="text-muted-foreground">Day Trades</div>
                    <div className="font-medium text-lg">
                      {account.dayTradeCount}
                      {account.equity >= 25000 && (
                        <span className="text-xs text-muted-foreground ml-1 block">(no PDT limit)</span>
                      )}
                      {account.equity < 25000 && (
                        <span className="text-xs text-muted-foreground ml-1 block">/ 3 (5-day)</span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Right: All Positions */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Activity className="h-4 w-4 text-muted-foreground" />
                <span className="font-medium">All Positions</span>
              </div>
              {positions && positions.length > 0 && (
                <Badge variant="outline">{positions.length} open</Badge>
              )}
            </div>

            {(!positions || positions.length === 0) ? (
              <div className="text-sm text-muted-foreground text-center py-8 bg-secondary/30 rounded-lg">
                No open positions
              </div>
            ) : (
              <div className="space-y-2 max-h-[180px] overflow-y-auto pr-1">
                {positions.map((position) => {
                  const isSelected = position.symbol === selectedTicker;
                  const isProfit = position.unrealizedPL >= 0;
                  return (
                    <div
                      key={position.symbol}
                      className={cn(
                        "p-3 rounded-lg border text-sm transition-colors",
                        isSelected
                          ? "bg-primary/10 border-primary/30"
                          : "bg-secondary/30 border-transparent hover:bg-secondary/50"
                      )}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold">{position.symbol}</span>
                          {isSelected && (
                            <Badge variant="secondary" className="text-xs">Selected</Badge>
                          )}
                        </div>
                        <div
                          className={cn(
                            "flex items-center gap-1 font-medium",
                            isProfit ? "text-green-500" : "text-red-500"
                          )}
                        >
                          {isProfit ? (
                            <TrendingUp className="h-3 w-3" />
                          ) : (
                            <TrendingDown className="h-3 w-3" />
                          )}
                          {formatPercent(position.unrealizedPLPercent * 100)}
                        </div>
                      </div>
                      <div className="grid grid-cols-4 gap-2 text-xs">
                        <div>
                          <div className="text-muted-foreground">Qty</div>
                          <div className="font-medium">{position.quantity}</div>
                        </div>
                        <div>
                          <div className="text-muted-foreground">Entry</div>
                          <div className="font-medium">{formatCurrency(position.avgEntryPrice)}</div>
                        </div>
                        <div>
                          <div className="text-muted-foreground">Current</div>
                          <div className="font-medium">{formatCurrency(position.currentPrice)}</div>
                        </div>
                        <div>
                          <div className="text-muted-foreground">P&L</div>
                          <div className={cn("font-medium", isProfit ? "text-green-500" : "text-red-500")}>
                            {formatCurrency(position.unrealizedPL)}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Total P&L Summary */}
            {positions && positions.length > 0 && (
              <div className="flex items-center justify-between pt-2 border-t text-sm">
                <span className="text-muted-foreground">Total Unrealized P&L</span>
                <span
                  className={cn(
                    "font-semibold text-lg",
                    positions.reduce((sum, p) => sum + p.unrealizedPL, 0) >= 0
                      ? "text-green-500"
                      : "text-red-500"
                  )}
                >
                  {formatCurrency(positions.reduce((sum, p) => sum + p.unrealizedPL, 0))}
                </span>
              </div>
            )}
          </div>
        </div>
      </CardContent>
      </Card>
    </TooltipProvider>
  );
}
