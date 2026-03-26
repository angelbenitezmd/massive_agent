"use client";

import {
  Shield,
  Wallet,
  TrendingUp,
  TrendingDown,
  Activity,
  AlertTriangle,
  Info,
  X,
  Clock,
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

function formatDuration(entryTime: string | null | undefined): string {
  if (!entryTime) return "";
  const entry = new Date(entryTime);
  if (isNaN(entry.getTime())) return "";
  const now = new Date();
  const diffMs = now.getTime() - entry.getTime();
  const mins = Math.floor(diffMs / 60000);
  const hours = Math.floor(mins / 60);
  const days = Math.floor(hours / 24);
  if (days > 0) return `${days}d ${hours % 24}h`;
  if (hours > 0) return `${hours}h ${mins % 60}m`;
  return `${mins}m`;
}
import type { Account, Position, RiskStatus } from "@/types";

interface RiskPanelProps {
  account: Account | undefined;
  positions: Position[] | undefined;
  riskStatus: RiskStatus | undefined;
  selectedTicker: string;
  isLoading: boolean;
  onClosePosition?: (ticker: string) => void;
  isClosingPosition?: boolean;
}

export function RiskPanel({
  account,
  positions,
  riskStatus,
  selectedTicker,
  isLoading,
  onClosePosition,
  isClosingPosition,
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
        <CardHeader className="pb-2 px-4 pt-3">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Shield className="h-4 w-4 text-primary" />
            Risk & Account
          </CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-3 space-y-3">
          {/* Circuit Breaker */}
          {riskStatus && (
            <div className="p-3 rounded-lg bg-secondary/30 space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">Circuit Breaker</span>
                <div className="flex items-center gap-2">
                  <div
                    className={cn(
                      "w-2.5 h-2.5 rounded-full animate-pulse",
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
                    className="text-xs"
                  >
                    {riskStatus.circuitBreaker}
                  </Badge>
                </div>
              </div>
              <p className="text-xs text-muted-foreground">
                {getCircuitBreakerLabel(riskStatus.circuitBreaker)}
              </p>

              <div className="flex items-center justify-between text-sm gap-2">
                <span className="text-muted-foreground inline-flex items-center gap-1">
                  Daily P&L
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Info className="h-3.5 w-3.5 cursor-help opacity-60 hover:opacity-100" />
                    </TooltipTrigger>
                    <TooltipContent side="bottom" className="max-w-[260px] text-xs">
                      Same idea as Alpaca&apos;s portfolio day change: current equity vs last equity
                      (prior reference). Includes realized P&amp;L and fees from trades closed today, not
                      only your open positions&apos; move.
                    </TooltipContent>
                  </Tooltip>
                </span>
                <span
                  className={cn(
                    "font-semibold text-right",
                    riskStatus.dailyPL >= 0 ? "text-green-500" : "text-red-500"
                  )}
                >
                  {formatCurrency(riskStatus.dailyPL)} ({formatPercent(riskStatus.dailyPLPercent)})
                </span>
              </div>

              <div className="space-y-1">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Drawdown</span>
                  <span className="font-medium">
                    {formatPercent(riskStatus.currentDrawdown)} / {formatPercent(riskStatus.maxDailyLoss * 100)} max
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
                <span className="font-semibold">{riskStatus.tradesToday}</span>
              </div>
            </div>
          )}

          {/* Account Summary */}
          {account && (
            <div className="p-3 rounded-lg bg-secondary/30 space-y-2.5">
              <div className="flex items-center gap-2">
                <Wallet className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm font-medium">Account</span>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <div className="text-xs text-muted-foreground">Equity</div>
                  <div className="text-base font-bold">{formatCurrency(account.equity)}</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground">Cash</div>
                  <div className="text-base font-bold">{formatCurrency(account.cash)}</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground">Buying Power</div>
                  <div className="text-sm font-semibold">{formatCurrency(account.buyingPower)}</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground">Day Trades</div>
                  <div className="text-sm font-semibold">
                    {account.dayTradeCount}
                    <span className="text-[10px] text-muted-foreground ml-1">
                      {account.equity >= 25000 ? "(no PDT)" : "/ 3"}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Positions */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Activity className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm font-medium">Positions</span>
              </div>
              {positions && positions.length > 0 && (
                <Badge variant="outline" className="text-xs">{positions.length} open</Badge>
              )}
            </div>

            {(!positions || positions.length === 0) ? (
              <div className="text-sm text-muted-foreground text-center py-4 bg-secondary/30 rounded-lg">
                No open positions
              </div>
            ) : (
              <div className="space-y-1.5 max-h-[200px] overflow-y-auto pr-1">
                {positions.map((position) => {
                  const isSelected = position.symbol === selectedTicker;
                  const isShort = position.quantity < 0;
                  const qtyAbs = Math.abs(position.quantity);
                  const isProfit = position.unrealizedPL >= 0;
                  const intradayUp = position.intradayPL >= 0;
                  return (
                    <div
                      key={position.symbol}
                      className={cn(
                        "p-2.5 rounded-lg border transition-colors",
                        isSelected
                          ? "bg-primary/10 border-primary/30"
                          : "bg-secondary/30 border-transparent hover:bg-secondary/50"
                      )}
                    >
                      <div className="flex items-center justify-between mb-1.5 gap-2">
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="text-sm font-bold">{position.symbol}</span>
                          <Badge variant="outline" className="text-[10px] shrink-0">
                            {isShort ? "Short" : "Long"}
                          </Badge>
                        </div>
                        {isProfit ? (
                          <TrendingUp className="h-4 w-4 text-green-500 shrink-0" />
                        ) : (
                          <TrendingDown className="h-4 w-4 text-red-500 shrink-0" />
                        )}
                      </div>
                      <div className="space-y-1 text-[11px] mb-1.5 pl-0.5">
                        <div className="flex justify-between gap-2">
                          <span className="text-muted-foreground">Since entry</span>
                          <span
                            className={cn(
                              "font-medium tabular-nums",
                              isProfit ? "text-green-500" : "text-red-500"
                            )}
                          >
                            {formatCurrency(position.unrealizedPL)} ({formatPercent(position.unrealizedPLPercent)})
                          </span>
                        </div>
                        <div className="flex justify-between gap-2">
                          <span className="text-muted-foreground">Today&apos;s move</span>
                          <span
                            className={cn(
                              "font-medium tabular-nums",
                              intradayUp ? "text-green-500" : "text-red-500"
                            )}
                          >
                            {formatCurrency(position.intradayPL)} ({formatPercent(position.intradayPLPercent)})
                          </span>
                        </div>
                      </div>
                      <div className="grid grid-cols-3 gap-2 text-xs mb-1.5">
                        <div>
                          <span className="text-muted-foreground">Qty </span>
                          <span className="font-medium">{qtyAbs}</span>
                        </div>
                        <div>
                          <span className="text-muted-foreground">Entry </span>
                          <span className="font-medium">{formatCurrency(position.avgEntryPrice)}</span>
                        </div>
                        <div>
                          <span className="text-muted-foreground">Now </span>
                          <span className="font-medium">{formatCurrency(position.currentPrice)}</span>
                        </div>
                      </div>
                      {position.entryTime && (
                        <div className="flex items-center gap-1 text-[11px] text-muted-foreground mb-1">
                          <Clock className="h-3 w-3" />
                          {new Date(position.entryTime).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", hour12: true })}
                          {" · "}
                          {formatDuration(position.entryTime)} held
                        </div>
                      )}
                      <div className="flex items-center justify-between">
                        <div className="flex gap-3 text-xs">
                          {position.stopLoss && (
                            <span>
                              <span className="text-red-500 font-medium">SL {formatCurrency(position.stopLoss)}</span>
                              <span className="text-muted-foreground ml-0.5">
                                ({((position.stopLoss - position.avgEntryPrice) / position.avgEntryPrice * 100).toFixed(1)}%)
                              </span>
                            </span>
                          )}
                          {position.takeProfit && (
                            <span>
                              <span className="text-green-500 font-medium">TP {formatCurrency(position.takeProfit)}</span>
                              <span className="text-muted-foreground ml-0.5">
                                (+{((position.takeProfit - position.avgEntryPrice) / position.avgEntryPrice * 100).toFixed(1)}%)
                              </span>
                            </span>
                          )}
                        </div>
                        {onClosePosition && (
                          <Button
                            variant="destructive"
                            size="sm"
                            className="h-6 px-2 text-xs"
                            onClick={(e) => {
                              e.stopPropagation();
                              if (confirm(`Close ${position.symbol} position at market price?`)) {
                                onClosePosition(position.symbol);
                              }
                            }}
                            disabled={isClosingPosition}
                          >
                            <X className="h-3 w-3 mr-1" />
                            Close
                          </Button>
                        )}
                      </div>
                      {position.exitSignal && (
                        <div className="text-xs font-medium text-yellow-500 bg-yellow-500/10 px-2 py-1 rounded mt-1">
                          {position.exitSignal}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {positions && positions.length > 0 && (
              <div className="flex items-center justify-between pt-2 border-t text-sm gap-2">
                <div className="text-muted-foreground">
                  <div>Open unrealized</div>
                  <div className="text-[10px] font-normal opacity-80">Sum since entry (not daily P&amp;L)</div>
                </div>
                <span
                  className={cn(
                    "font-bold text-base shrink-0",
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
        </CardContent>
      </Card>
    </TooltipProvider>
  );
}
