"use client";

import { useMemo } from "react";
import {
  TrendingUp,
  TrendingDown,
  Minus,
  BarChart3,
  Activity,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  formatCurrency,
  formatPercent,
  formatVolume,
  formatNumber,
  cn,
} from "@/lib/utils";
import type { Quote, Technicals } from "@/types";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";

interface MarketSnapshotProps {
  quote: Quote | undefined;
  technicals: Technicals | undefined;
  bars: any[] | undefined;
  isLoading: boolean;
}

export function MarketSnapshot({
  quote,
  technicals,
  bars,
  isLoading,
}: MarketSnapshotProps) {
  const chartData = useMemo(() => {
    if (!bars) return [];
    return bars.map((bar, index) => ({
      time: index,
      price: bar.close || bar.c,
      volume: bar.volume || bar.v,
    }));
  }, [bars]);

  const isPositive = quote ? quote.changePercent >= 0 : false;

  const getRsiStatus = (rsi: number | undefined) => {
    if (!rsi) return { label: "N/A", color: "text-muted-foreground" };
    if (rsi > 70) return { label: "Overbought", color: "text-red-500" };
    if (rsi < 30) return { label: "Oversold", color: "text-green-500" };
    return { label: "Neutral", color: "text-yellow-500" };
  };

  const getMacdStatus = (macd: Technicals["macd"] | undefined) => {
    if (!macd) return { label: "N/A", color: "text-muted-foreground" };
    if (macd.histogram > 0 && macd.value > macd.signal)
      return { label: "Bullish", color: "text-green-500" };
    if (macd.histogram < 0 && macd.value < macd.signal)
      return { label: "Bearish", color: "text-red-500" };
    return { label: "Neutral", color: "text-yellow-500" };
  };

  const rsiStatus = getRsiStatus(technicals?.rsi);
  const macdStatus = getMacdStatus(technicals?.macd);

  if (isLoading) {
    return (
      <Card className="col-span-2">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <BarChart3 className="h-5 w-5" />
            Market Snapshot
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center h-[400px]">
            <Activity className="h-8 w-8 animate-pulse text-muted-foreground" />
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="col-span-2 card-hover">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <CardTitle className="text-2xl font-bold">
              {quote?.symbol || "---"}
            </CardTitle>
            <div className="flex items-center gap-2">
              <span className="text-3xl font-bold">
                {quote ? formatCurrency(quote.price) : "---"}
              </span>
              {quote && (
                <div
                  className={cn(
                    "flex items-center gap-1",
                    isPositive ? "text-green-500" : "text-red-500"
                  )}
                >
                  {isPositive ? (
                    <TrendingUp className="h-5 w-5" />
                  ) : (
                    <TrendingDown className="h-5 w-5" />
                  )}
                  <span className="font-semibold">
                    {formatPercent(quote.changePercent)}
                  </span>
                  <span className="text-sm">
                    ({isPositive ? "+" : ""}
                    {formatCurrency(quote.change)})
                  </span>
                </div>
              )}
            </div>
          </div>
          <div className="flex items-center gap-4 text-sm text-muted-foreground">
            <div>
              <span className="font-medium">Vol:</span>{" "}
              {quote ? formatVolume(quote.volume) : "---"}
            </div>
            <div>
              <span className="font-medium">H:</span>{" "}
              {quote ? formatCurrency(quote.high) : "---"}
            </div>
            <div>
              <span className="font-medium">L:</span>{" "}
              {quote ? formatCurrency(quote.low) : "---"}
            </div>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Price Chart */}
        <div className="h-[250px] w-full">
          {chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <XAxis dataKey="time" hide />
                <YAxis
                  domain={["dataMin - 0.5", "dataMax + 0.5"]}
                  hide
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "hsl(var(--popover))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: "0.5rem",
                  }}
                  formatter={(value: number) => [
                    formatCurrency(value),
                    "Price",
                  ]}
                />
                {quote && (
                  <ReferenceLine
                    y={quote.previousClose}
                    stroke="hsl(var(--muted-foreground))"
                    strokeDasharray="3 3"
                  />
                )}
                <Line
                  type="monotone"
                  dataKey="price"
                  stroke={isPositive ? "#22c55e" : "#ef4444"}
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-full text-muted-foreground">
              No chart data available
            </div>
          )}
        </div>

        <Separator />

        {/* Technical Indicators */}
        <div className="grid grid-cols-3 gap-4">
          {/* RSI */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">RSI (14)</span>
              <Badge variant="outline" className={rsiStatus.color}>
                {rsiStatus.label}
              </Badge>
            </div>
            <div className="flex items-center gap-2">
              <div className="flex-1 h-2 bg-secondary rounded-full overflow-hidden">
                <div
                  className={cn(
                    "h-full transition-all",
                    technicals?.rsi && technicals.rsi > 70
                      ? "bg-red-500"
                      : technicals?.rsi && technicals.rsi < 30
                      ? "bg-green-500"
                      : "bg-yellow-500"
                  )}
                  style={{ width: `${technicals?.rsi || 50}%` }}
                />
              </div>
              <span className="text-sm font-bold w-12 text-right">
                {technicals?.rsi ? formatNumber(technicals.rsi, 1) : "---"}
              </span>
            </div>
          </div>

          {/* MACD */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">MACD</span>
              <Badge variant="outline" className={macdStatus.color}>
                {macdStatus.label}
              </Badge>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <div className="flex-1">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Signal:</span>
                  <span>
                    {technicals?.macd
                      ? formatNumber(technicals.macd.signal, 3)
                      : "---"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Histogram:</span>
                  <span
                    className={cn(
                      technicals?.macd?.histogram
                        ? technicals.macd.histogram > 0
                          ? "text-green-500"
                          : "text-red-500"
                        : ""
                    )}
                  >
                    {technicals?.macd
                      ? formatNumber(technicals.macd.histogram, 3)
                      : "---"}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Moving Averages */}
          <div className="space-y-2">
            <span className="text-sm font-medium">Moving Averages</span>
            <div className="space-y-1 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">SMA 20:</span>
                <span className="flex items-center gap-1">
                  {technicals?.sma20 ? formatCurrency(technicals.sma20) : "---"}
                  {technicals?.priceVsSma20 === "above" ? (
                    <TrendingUp className="h-3 w-3 text-green-500" />
                  ) : technicals?.priceVsSma20 === "below" ? (
                    <TrendingDown className="h-3 w-3 text-red-500" />
                  ) : (
                    <Minus className="h-3 w-3 text-muted-foreground" />
                  )}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">SMA 50:</span>
                <span className="flex items-center gap-1">
                  {technicals?.sma50 ? formatCurrency(technicals.sma50) : "---"}
                  {technicals?.priceVsSma50 === "above" ? (
                    <TrendingUp className="h-3 w-3 text-green-500" />
                  ) : technicals?.priceVsSma50 === "below" ? (
                    <TrendingDown className="h-3 w-3 text-red-500" />
                  ) : (
                    <Minus className="h-3 w-3 text-muted-foreground" />
                  )}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">SMA 200:</span>
                <span className="flex items-center gap-1">
                  {technicals?.sma200
                    ? formatCurrency(technicals.sma200)
                    : "---"}
                  {technicals?.priceVsSma200 === "above" ? (
                    <TrendingUp className="h-3 w-3 text-green-500" />
                  ) : technicals?.priceVsSma200 === "below" ? (
                    <TrendingDown className="h-3 w-3 text-red-500" />
                  ) : (
                    <Minus className="h-3 w-3 text-muted-foreground" />
                  )}
                </span>
              </div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
