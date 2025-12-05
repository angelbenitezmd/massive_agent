"use client";

import { memo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { BookOpen, TrendingUp, TrendingDown, Clock, Info } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { Order } from "@/types";

interface TradeJournalProps {
  orders?: Order[];
  isLoading?: boolean;
}

function formatTime(dateString: string | null): string {
  if (!dateString) return "-";
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

function formatPrice(price: number | null): string {
  if (price === null || price === undefined) return "-";
  return `$${price.toFixed(2)}`;
}

export const TradeJournal = memo(function TradeJournal({ orders = [], isLoading }: TradeJournalProps) {
  // Calculate summary stats
  const filledOrders = orders.filter((o) => o.status === "filled");
  const totalTrades = filledOrders.length;
  const winningTrades = filledOrders.filter((o) => (o.pnl || 0) > 0).length;
  const totalPnl = filledOrders.reduce((sum, o) => sum + (o.pnl || 0), 0);
  const winRate = totalTrades > 0 ? (winningTrades / totalTrades) * 100 : 0;

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
                <p>Historical record of all executed trades from Alpaca.</p>
                <div className="space-y-1 pt-1">
                  <p><strong>Win Rate:</strong> Percentage of profitable trades</p>
                  <p><strong>Total P&L:</strong> Cumulative profit/loss</p>
                  <p><strong>W/L:</strong> Wins vs losses count</p>
                </div>
                <p className="text-muted-foreground">Shows your 10 most recent trades with entry details.</p>
              </div>
            </TooltipContent>
          </Tooltip>
          {totalTrades > 0 && (
            <Badge variant="secondary" className="ml-auto text-xs">
              {totalTrades} trades
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        {/* Summary Stats */}
        <div className="grid grid-cols-3 gap-2 mb-4 text-center">
          <div className="bg-muted/50 rounded-lg p-2">
            <div className="text-xs text-muted-foreground">Win Rate</div>
            <div
              className={`text-sm font-semibold ${
                winRate >= 50 ? "text-green-500" : "text-red-500"
              }`}
            >
              {winRate.toFixed(0)}%
            </div>
          </div>
          <div className="bg-muted/50 rounded-lg p-2">
            <div className="text-xs text-muted-foreground">Total P&L</div>
            <div
              className={`text-sm font-semibold ${
                totalPnl >= 0 ? "text-green-500" : "text-red-500"
              }`}
            >
              {totalPnl >= 0 ? "+" : ""}${totalPnl.toFixed(2)}
            </div>
          </div>
          <div className="bg-muted/50 rounded-lg p-2">
            <div className="text-xs text-muted-foreground">W/L</div>
            <div className="text-sm font-semibold">
              <span className="text-green-500">{winningTrades}</span>
              <span className="text-muted-foreground">/</span>
              <span className="text-red-500">{totalTrades - winningTrades}</span>
            </div>
          </div>
        </div>

        {/* Trade List */}
        <ScrollArea className="h-[160px]">
          {isLoading ? (
            <div className="flex items-center justify-center h-full text-muted-foreground">
              Loading trades...
            </div>
          ) : orders.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
              <BookOpen className="h-8 w-8 mb-2 opacity-50" />
              <p className="text-sm">No trades yet</p>
            </div>
          ) : (
            <div className="space-y-2">
              {orders.slice(0, 10).map((order) => (
                <div
                  key={order.id}
                  className="flex items-center justify-between p-2 rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    {order.side === "buy" ? (
                      <TrendingUp className="h-4 w-4 text-green-500" />
                    ) : (
                      <TrendingDown className="h-4 w-4 text-red-500" />
                    )}
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-sm">{order.symbol}</span>
                        <Badge
                          variant={order.side === "buy" ? "default" : "destructive"}
                          className="text-[10px] px-1.5 py-0"
                        >
                          {order.side.toUpperCase()}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-2 text-xs text-muted-foreground">
                        <span>{order.filled_qty} shares</span>
                        <span>@</span>
                        <span>{formatPrice(order.filled_avg_price)}</span>
                      </div>
                    </div>
                  </div>
                  <div className="text-right">
                    {order.pnl !== undefined && (
                      <div
                        className={`text-sm font-medium ${
                          order.pnl >= 0 ? "text-green-500" : "text-red-500"
                        }`}
                      >
                        {order.pnl >= 0 ? "+" : ""}${order.pnl.toFixed(2)}
                      </div>
                    )}
                    <div className="flex items-center gap-1 text-xs text-muted-foreground">
                      <Clock className="h-3 w-3" />
                      {formatTime(order.filled_at || order.submitted_at)}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
    </TooltipProvider>
  );
});
