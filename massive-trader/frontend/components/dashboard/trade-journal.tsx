"use client";

import { memo, useState, useEffect, useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { BookOpen, TrendingUp, TrendingDown, Clock, Info, XCircle, Loader2 } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { Order } from "@/types";
import { API_BASE, getClosedTrades, type ClosedTrade, type ClosedTradesResponse } from "@/lib/api";

type TimePeriod = "today" | "yesterday" | "week" | "month" | "all";

const TIME_PERIODS: { value: TimePeriod; label: string; daysBack?: number }[] = [
  { value: "today", label: "Today", daysBack: 1 },
  { value: "yesterday", label: "2D", daysBack: 2 },
  { value: "week", label: "1W", daysBack: 7 },
  { value: "month", label: "1M", daysBack: 30 },
  { value: "all", label: "All" },
];

interface TradeJournalProps {
  orders?: Order[];
  isLoading?: boolean;
  onOrdersCanceled?: () => void;
}

function formatTime(dateString: string | null): string {
  if (!dateString) return "-";
  const date = new Date(dateString);
  return date.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true, timeZone: "America/New_York" }) +
    " " + date.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "America/New_York" });
}

function formatPrice(price: number | null | undefined): string {
  if (price === null || price === undefined) return "-";
  return `$${price.toFixed(2)}`;
}

export const TradeJournal = memo(function TradeJournal({ orders = [], isLoading, onOrdersCanceled }: TradeJournalProps) {
  const [isCanceling, setIsCanceling] = useState(false);
  const [closedTrades, setClosedTrades] = useState<ClosedTradesResponse | null>(null);
  const [timePeriod, setTimePeriod] = useState<TimePeriod>("week");
  const [isLoadingTrades, setIsLoadingTrades] = useState(false);

  // Fetch closed trades with P&L based on selected time period
  useEffect(() => {
    const selectedPeriod = TIME_PERIODS.find(p => p.value === timePeriod);
    setIsLoadingTrades(true);
    getClosedTrades(50, selectedPeriod?.daysBack)
      .then(setClosedTrades)
      .finally(() => setIsLoadingTrades(false));
  }, [timePeriod]);

  const sortedRecentOrders = useMemo(() => {
    return [...(orders || [])].sort((a, b) => {
      const tb = new Date(b.submitted_at || 0).getTime();
      const ta = new Date(a.submitted_at || 0).getTime();
      return tb - ta;
    });
  }, [orders]);

  // Count pending orders that can be canceled
  const pendingOrders = orders.filter((o) =>
    ["new", "held", "pending_new", "accepted", "partially_filled"].includes(o.status)
  );

  // Use closed trades data for summary
  const summary = closedTrades?.summary || { total_trades: 0, wins: 0, losses: 0, win_rate: 0, total_pnl_pct: 0 };
  const trades = closedTrades?.trades || [];

  const handleCancelAllOrders = async () => {
    if (!confirm(`Cancel all ${pendingOrders.length} pending orders?`)) return;

    setIsCanceling(true);
    try {
      const response = await fetch(`${API_BASE}/api/trading/orders`, {
        method: "DELETE",
      });
      const result = await response.json();
      if (result.status === "success" || result.status === "cancelled") {
        onOrdersCanceled?.();
      } else {
        console.error("Failed to cancel orders:", result);
      }
    } catch (error) {
      console.error("Error canceling orders:", error);
    } finally {
      setIsCanceling(false);
    }
  };

  return (
    <TooltipProvider>
    <Card className="bg-card border-border">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <BookOpen className="h-4 w-4 text-primary" />
          Trade Journal
          <Tooltip>
            <TooltipTrigger asChild>
              <Info className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground cursor-help" />
            </TooltipTrigger>
            <TooltipContent side="bottom" className="max-w-[280px] p-3">
              <div className="space-y-2 text-xs">
                <p className="font-semibold">Trade Journal</p>
                <p><strong>Recent orders</strong> mirrors Alpaca (all fills &amp; statuses). <strong>Round trips</strong> below pairs buy/sell FIFO for a simple P&amp;L log — it will not match every broker row.</p>
                <div className="space-y-1 pt-1">
                  <p><strong>Win Rate:</strong> Percentage of profitable closed trades</p>
                  <p><strong>Total P&L:</strong> Cumulative P&L percentage</p>
                  <p><strong>W/L:</strong> Wins vs losses count</p>
                </div>
              </div>
            </TooltipContent>
          </Tooltip>
          <div className="ml-auto flex items-center gap-2">
            {pendingOrders.length > 0 && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleCancelAllOrders}
                    disabled={isCanceling}
                    className="h-7 text-xs text-red-500 hover:text-red-600 hover:bg-red-500/10 border-red-500/30"
                  >
                    {isCanceling ? (
                      <Loader2 className="h-3 w-3 animate-spin mr-1" />
                    ) : (
                      <XCircle className="h-3 w-3 mr-1" />
                    )}
                    Cancel ({pendingOrders.length})
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  <p>Cancel all {pendingOrders.length} pending orders</p>
                </TooltipContent>
              </Tooltip>
            )}
          </div>
        </CardTitle>
        {/* Time Period Tabs */}
        <Tabs value={timePeriod} onValueChange={(v) => setTimePeriod(v as TimePeriod)} className="mt-2">
          <TabsList className="grid w-full grid-cols-5 h-8">
            {TIME_PERIODS.map((period) => (
              <TabsTrigger
                key={period.value}
                value={period.value}
                className="text-xs h-6"
              >
                {period.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </CardHeader>
      <CardContent className="pt-0 space-y-4">
        {/* Live Alpaca order history (same source as Alpaca Recent Orders) */}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs font-semibold text-foreground">Recent orders</span>
            <span className="text-[10px] text-muted-foreground">
              {sortedRecentOrders.length} loaded
            </span>
          </div>
          {isLoading ? (
            <div className="flex items-center justify-center py-6 text-muted-foreground text-xs">
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
              Loading orders…
            </div>
          ) : sortedRecentOrders.length === 0 ? (
            <div className="text-xs text-muted-foreground py-3 px-2 rounded-md bg-muted/30 text-center">
              No orders in the last week from Alpaca. Check API keys or widen the date range in the backend.
            </div>
          ) : (
            <div className="rounded-md border border-border overflow-x-auto max-h-[200px] overflow-y-auto">
              <table className="w-full text-[10px] sm:text-xs text-left">
                <thead>
                  <tr className="border-b border-border bg-muted/40 sticky top-0">
                    <th className="px-1.5 py-1 font-medium">Sym</th>
                    <th className="px-1.5 py-1 font-medium">Side</th>
                    <th className="px-1.5 py-1 font-medium">Type</th>
                    <th className="px-1.5 py-1 font-medium text-right">Qty</th>
                    <th className="px-1.5 py-1 font-medium text-right">Fill</th>
                    <th className="px-1.5 py-1 font-medium text-right">Avg</th>
                    <th className="px-1.5 py-1 font-medium">Status</th>
                    <th className="px-1.5 py-1 font-medium whitespace-nowrap">Submitted</th>
                    <th className="px-1.5 py-1 font-medium whitespace-nowrap">Filled</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedRecentOrders.map((o) => (
                    <tr key={o.id} className="border-b border-border/60 hover:bg-muted/20">
                      <td className="px-1.5 py-1 font-semibold">{o.symbol}</td>
                      <td className="px-1.5 py-1 uppercase">{String(o.side)}</td>
                      <td className="px-1.5 py-1 capitalize">{o.type}</td>
                      <td className="px-1.5 py-1 text-right tabular-nums">{o.qty}</td>
                      <td className="px-1.5 py-1 text-right tabular-nums">{o.filled_qty}</td>
                      <td className="px-1.5 py-1 text-right tabular-nums">{formatPrice(o.filled_avg_price)}</td>
                      <td className="px-1.5 py-1 capitalize">{o.status}</td>
                      <td className="px-1.5 py-1 text-muted-foreground whitespace-nowrap">{formatTime(o.submitted_at)}</td>
                      <td className="px-1.5 py-1 text-muted-foreground whitespace-nowrap">{formatTime(o.filled_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="border-t border-border pt-3">
          <div className="text-xs font-semibold mb-2">Round trips (journal)</div>
        {/* Summary Stats */}
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-muted-foreground">
            {TIME_PERIODS.find(p => p.value === timePeriod)?.label} Stats
          </span>
          {summary.total_trades > 0 && (
            <Badge variant="secondary" className="text-xs">
              {summary.total_trades} trade{summary.total_trades !== 1 ? 's' : ''}
            </Badge>
          )}
        </div>
        <div className="grid grid-cols-3 gap-2 mb-4 text-center">
          <div className="bg-muted/50 rounded-lg p-2">
            <div className="text-xs text-muted-foreground">Win Rate</div>
            <div
              className={`text-sm font-semibold ${
                summary.win_rate >= 50 ? "text-green-500" : summary.win_rate > 0 ? "text-red-500" : "text-muted-foreground"
              }`}
            >
              {summary.win_rate.toFixed(0)}%
            </div>
          </div>
          <div className="bg-muted/50 rounded-lg p-2">
            <div className="text-xs text-muted-foreground">Total P&L</div>
            <div
              className={`text-sm font-semibold ${
                summary.total_pnl_pct >= 0 ? "text-green-500" : "text-red-500"
              }`}
            >
              {summary.total_pnl_pct >= 0 ? "+" : ""}{summary.total_pnl_pct.toFixed(1)}%
            </div>
          </div>
          <div className="bg-muted/50 rounded-lg p-2">
            <div className="text-xs text-muted-foreground">W/L</div>
            <div className="text-sm font-semibold">
              <span className="text-green-500">{summary.wins}</span>
              <span className="text-muted-foreground">/</span>
              <span className="text-red-500">{summary.losses}</span>
            </div>
          </div>
        </div>

        {/* Trade List */}
        <ScrollArea className="h-[110px]">
          {isLoadingTrades ? (
            <div className="flex items-center justify-center h-full text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
              Loading trades...
            </div>
          ) : trades.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
              <BookOpen className="h-8 w-8 mb-2 opacity-50" />
              <p className="text-sm">No closed trades {timePeriod === "all" ? "yet" : `in ${TIME_PERIODS.find(p => p.value === timePeriod)?.label || timePeriod}`}</p>
            </div>
          ) : (
            <div className="space-y-2">
              {trades.slice(0, 20).map((trade) => {
                const isProfit = (trade.pnl_pct || 0) > 0;

                return (
                  <div
                    key={trade.id}
                    className="flex items-center justify-between p-2 rounded-lg transition-colors bg-muted/30 hover:bg-muted/50"
                  >
                    <div className="flex items-center gap-2">
                      {isProfit ? (
                        <TrendingUp className="h-4 w-4 text-green-500" />
                      ) : (
                        <TrendingDown className="h-4 w-4 text-red-500" />
                      )}
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-sm">{trade.symbol}</span>
                          <Badge
                            variant={isProfit ? "default" : "destructive"}
                            className="text-[10px] px-1.5 py-0"
                          >
                            {isProfit ? "WIN" : "LOSS"}
                          </Badge>
                        </div>
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          <span>{formatPrice(trade.entry_price)}</span>
                          <span>→</span>
                          <span>{formatPrice(trade.exit_price)}</span>
                        </div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div
                        className={`text-sm font-medium ${
                          isProfit ? "text-green-500" : "text-red-500"
                        }`}
                      >
                        {isProfit ? "+" : ""}{trade.pnl_pct?.toFixed(1)}%
                      </div>
                      <div className="flex items-center gap-1 text-xs text-muted-foreground">
                        <Clock className="h-3 w-3" />
                        {formatTime(trade.timestamp)}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </ScrollArea>
        </div>
      </CardContent>
    </Card>
    </TooltipProvider>
  );
});
