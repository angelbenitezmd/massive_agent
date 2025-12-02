"use client";

import { useMemo, useState } from "react";
import {
  TrendingUp,
  TrendingDown,
  Minus,
  BarChart3,
  Activity,
  CandlestickChart,
  Clock,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";
import {
  formatCurrency,
  formatPercent,
  formatVolume,
  formatNumber,
  cn,
} from "@/lib/utils";
import type { Quote, Technicals } from "@/types";
import {
  ComposedChart,
  Line,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Area,
  Cell,
} from "recharts";

interface MarketSnapshotProps {
  quote: Quote | undefined;
  technicals: Technicals | undefined;
  bars: any[] | undefined;
  isLoading: boolean;
}

// Custom candlestick shape
const CandlestickBar = (props: any) => {
  const { x, y, width, height, open, close, high, low, yScale } = props;
  const isGreen = close >= open;
  const color = isGreen ? "#22c55e" : "#ef4444";

  const candleWidth = Math.max(width * 0.8, 2);
  const wickWidth = 1;

  const highY = yScale ? yScale(high) : y;
  const lowY = yScale ? yScale(low) : y + height;
  const openY = yScale ? yScale(open) : y;
  const closeY = yScale ? yScale(close) : y + height;

  const bodyTop = Math.min(openY, closeY);
  const bodyHeight = Math.abs(closeY - openY) || 1;

  return (
    <g>
      {/* Wick */}
      <line
        x1={x + candleWidth / 2}
        y1={highY}
        x2={x + candleWidth / 2}
        y2={lowY}
        stroke={color}
        strokeWidth={wickWidth}
      />
      {/* Body */}
      <rect
        x={x}
        y={bodyTop}
        width={candleWidth}
        height={bodyHeight}
        fill={isGreen ? color : color}
        stroke={color}
        strokeWidth={1}
      />
    </g>
  );
};

// Custom tooltip
const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload || !payload.length) return null;

  const data = payload[0]?.payload;
  if (!data) return null;

  const isGreen = data.close >= data.open;
  const change = data.close - data.open;
  const changePercent = (change / data.open) * 100;

  return (
    <div className="bg-popover border border-border rounded-lg p-3 shadow-lg">
      <div className="flex items-center gap-2 mb-2">
        <Clock className="h-3 w-3 text-muted-foreground" />
        <span className="text-xs text-muted-foreground">Bar {data.time + 1}</span>
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
        <div className="flex justify-between">
          <span className="text-muted-foreground">Open:</span>
          <span className="font-medium">{formatCurrency(data.open)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">High:</span>
          <span className="font-medium text-green-500">{formatCurrency(data.high)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">Close:</span>
          <span className={cn("font-medium", isGreen ? "text-green-500" : "text-red-500")}>
            {formatCurrency(data.close)}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">Low:</span>
          <span className="font-medium text-red-500">{formatCurrency(data.low)}</span>
        </div>
      </div>
      <Separator className="my-2" />
      <div className="flex justify-between text-sm">
        <span className="text-muted-foreground">Change:</span>
        <span className={cn("font-medium", isGreen ? "text-green-500" : "text-red-500")}>
          {isGreen ? "+" : ""}{formatCurrency(change)} ({isGreen ? "+" : ""}{changePercent.toFixed(2)}%)
        </span>
      </div>
      <div className="flex justify-between text-sm">
        <span className="text-muted-foreground">Volume:</span>
        <span className="font-medium">{formatVolume(data.volume)}</span>
      </div>
      {data.sma20 && (
        <div className="flex justify-between text-sm">
          <span className="text-muted-foreground">SMA 20:</span>
          <span className="font-medium text-blue-500">{formatCurrency(data.sma20)}</span>
        </div>
      )}
    </div>
  );
};

export function MarketSnapshot({
  quote,
  technicals,
  bars,
  isLoading,
}: MarketSnapshotProps) {
  const [showVolume, setShowVolume] = useState(true);
  const [showSMA, setShowSMA] = useState(true);

  const chartData = useMemo(() => {
    if (!bars || bars.length === 0) return [];

    // Calculate SMA 20
    const sma20Period = 20;

    return bars.map((bar, index) => {
      // Calculate SMA 20 if we have enough data
      let sma20 = null;
      if (index >= sma20Period - 1) {
        const sum = bars
          .slice(index - sma20Period + 1, index + 1)
          .reduce((acc, b) => acc + (b.close || b.c), 0);
        sma20 = sum / sma20Period;
      }

      return {
        time: index,
        open: bar.open || bar.o,
        high: bar.high || bar.h,
        low: bar.low || bar.l,
        close: bar.close || bar.c,
        volume: bar.volume || bar.v,
        sma20,
      };
    });
  }, [bars]);

  // Calculate chart statistics
  const chartStats = useMemo(() => {
    if (!chartData.length) return null;

    const prices = chartData.map(d => d.close);
    const volumes = chartData.map(d => d.volume);
    const highs = chartData.map(d => d.high);
    const lows = chartData.map(d => d.low);

    const first = chartData[0];
    const last = chartData[chartData.length - 1];
    const priceChange = last.close - first.open;
    const priceChangePercent = (priceChange / first.open) * 100;

    const avgVolume = volumes.reduce((a, b) => a + b, 0) / volumes.length;
    const maxVolume = Math.max(...volumes);

    const greenBars = chartData.filter(d => d.close >= d.open).length;
    const redBars = chartData.length - greenBars;

    return {
      priceChange,
      priceChangePercent,
      avgVolume,
      maxVolume,
      periodHigh: Math.max(...highs),
      periodLow: Math.min(...lows),
      greenBars,
      redBars,
      totalBars: chartData.length,
    };
  }, [chartData]);

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

  // Calculate min/max for Y axis
  const yDomain = useMemo(() => {
    if (!chartData.length) return [0, 100];
    const allPrices = chartData.flatMap(d => [d.high, d.low]);
    const min = Math.min(...allPrices);
    const max = Math.max(...allPrices);
    const padding = (max - min) * 0.1;
    return [min - padding, max + padding];
  }, [chartData]);

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
          <div className="flex items-center gap-2">
            <Button
              variant={showSMA ? "default" : "outline"}
              size="sm"
              onClick={() => setShowSMA(!showSMA)}
              className="text-xs"
            >
              SMA
            </Button>
            <Button
              variant={showVolume ? "default" : "outline"}
              size="sm"
              onClick={() => setShowVolume(!showVolume)}
              className="text-xs"
            >
              Vol
            </Button>
          </div>
        </div>

        {/* Quick Stats Bar */}
        <div className="flex items-center gap-4 mt-2 text-sm text-muted-foreground flex-wrap">
          <div>
            <span className="font-medium">Vol:</span>{" "}
            {quote ? formatVolume(quote.volume) : "---"}
          </div>
          <div>
            <span className="font-medium">H:</span>{" "}
            <span className="text-green-500">{quote ? formatCurrency(quote.high) : "---"}</span>
          </div>
          <div>
            <span className="font-medium">L:</span>{" "}
            <span className="text-red-500">{quote ? formatCurrency(quote.low) : "---"}</span>
          </div>
          {chartStats && (
            <>
              <Separator orientation="vertical" className="h-4" />
              <div>
                <span className="font-medium">Period:</span>{" "}
                <span className={cn(chartStats.priceChange >= 0 ? "text-green-500" : "text-red-500")}>
                  {chartStats.priceChange >= 0 ? "+" : ""}{formatPercent(chartStats.priceChangePercent)}
                </span>
              </div>
              <div>
                <span className="font-medium">Bars:</span>{" "}
                <span className="text-green-500">{chartStats.greenBars}</span>
                {" / "}
                <span className="text-red-500">{chartStats.redBars}</span>
              </div>
            </>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Price Chart with Candlesticks */}
        <div className="h-[280px] w-full">
          {chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                <XAxis
                  dataKey="time"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
                  tickFormatter={(value) => `${value + 1}`}
                  interval="preserveStartEnd"
                />
                <YAxis
                  yAxisId="price"
                  domain={yDomain}
                  axisLine={false}
                  tickLine={false}
                  tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
                  tickFormatter={(value) => `$${value.toFixed(0)}`}
                  width={50}
                />
                {showVolume && (
                  <YAxis
                    yAxisId="volume"
                    orientation="right"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
                    tickFormatter={(value) => formatVolume(value)}
                    width={50}
                  />
                )}
                <Tooltip content={<CustomTooltip />} />

                {/* Previous close reference line */}
                {quote?.previousClose && (
                  <ReferenceLine
                    yAxisId="price"
                    y={quote.previousClose}
                    stroke="hsl(var(--muted-foreground))"
                    strokeDasharray="5 5"
                    strokeWidth={1}
                    label={{
                      value: `Prev: ${formatCurrency(quote.previousClose)}`,
                      position: 'right',
                      fontSize: 10,
                      fill: 'hsl(var(--muted-foreground))',
                    }}
                  />
                )}

                {/* Volume bars */}
                {showVolume && (
                  <Bar
                    yAxisId="volume"
                    dataKey="volume"
                    opacity={0.3}
                    maxBarSize={20}
                  >
                    {chartData.map((entry, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={entry.close >= entry.open ? "#22c55e" : "#ef4444"}
                      />
                    ))}
                  </Bar>
                )}

                {/* SMA 20 line */}
                {showSMA && (
                  <Line
                    yAxisId="price"
                    type="monotone"
                    dataKey="sma20"
                    stroke="#3b82f6"
                    strokeWidth={1.5}
                    dot={false}
                    connectNulls={false}
                    name="SMA 20"
                  />
                )}

                {/* Candlestick area (high-low range) */}
                <Area
                  yAxisId="price"
                  type="monotone"
                  dataKey="high"
                  stroke="none"
                  fill="none"
                />

                {/* Price line (close) with gradient fill */}
                <Line
                  yAxisId="price"
                  type="monotone"
                  dataKey="close"
                  stroke={isPositive ? "#22c55e" : "#ef4444"}
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 6, fill: isPositive ? "#22c55e" : "#ef4444", stroke: "white", strokeWidth: 2 }}
                />

                {/* High-Low range visualization */}
                {chartData.map((entry, index) => {
                  const isGreen = entry.close >= entry.open;
                  return (
                    <ReferenceLine
                      key={`range-${index}`}
                      yAxisId="price"
                      segment={[
                        { x: index, y: entry.low },
                        { x: index, y: entry.high }
                      ]}
                      stroke={isGreen ? "#22c55e40" : "#ef444440"}
                      strokeWidth={8}
                    />
                  );
                })}
              </ComposedChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex items-center justify-center h-full text-muted-foreground">
              No chart data available
            </div>
          )}
        </div>

        {/* Chart Legend */}
        {chartData.length > 0 && (
          <div className="flex items-center justify-center gap-6 text-xs text-muted-foreground">
            <div className="flex items-center gap-1">
              <div className="w-3 h-3 rounded-full bg-green-500" />
              <span>Bullish</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="w-3 h-3 rounded-full bg-red-500" />
              <span>Bearish</span>
            </div>
            {showSMA && (
              <div className="flex items-center gap-1">
                <div className="w-6 h-0.5 bg-blue-500" />
                <span>SMA 20</span>
              </div>
            )}
            <div className="flex items-center gap-1">
              <div className="w-6 h-0.5 border-t border-dashed border-muted-foreground" />
              <span>Prev Close</span>
            </div>
          </div>
        )}

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
              <div className="flex-1 h-2 bg-secondary rounded-full overflow-hidden relative">
                {/* Overbought/Oversold zones */}
                <div className="absolute inset-0 flex">
                  <div className="w-[30%] bg-green-500/20" />
                  <div className="w-[40%] bg-yellow-500/20" />
                  <div className="w-[30%] bg-red-500/20" />
                </div>
                <div
                  className={cn(
                    "h-full transition-all relative z-10",
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
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>Oversold (30)</span>
              <span>Overbought (70)</span>
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
                  <span className="text-muted-foreground">Value:</span>
                  <span className={cn(
                    technicals?.macd?.value
                      ? technicals.macd.value > 0
                        ? "text-green-500"
                        : "text-red-500"
                      : ""
                  )}>
                    {technicals?.macd
                      ? formatNumber(technicals.macd.value, 3)
                      : "---"}
                  </span>
                </div>
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
