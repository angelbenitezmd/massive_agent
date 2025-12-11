"use client";

import { useState, useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  TrendingUp,
  TrendingDown,
  Calendar,
  DollarSign,
  Percent,
  BarChart3,
  ArrowUpRight,
  ArrowDownRight,
} from "lucide-react";
import { cn, formatCurrency, formatPercent } from "@/lib/utils";
import { usePortfolioHistory } from "@/hooks/use-trading-data";
import type { PortfolioHistoryPoint } from "@/lib/api";

const PERIODS = [
  { value: "1W", label: "1W" },
  { value: "1M", label: "1M" },
  { value: "3M", label: "3M" },
  { value: "1A", label: "1Y" },
];

interface MiniChartProps {
  data: PortfolioHistoryPoint[];
  dataKey: "equity" | "profit_loss" | "profit_loss_pct";
  color: string;
  height?: number;
}

function MiniChart({ data, dataKey, color, height = 60 }: MiniChartProps) {
  if (!data || data.length < 2) return null;

  const values = data.map((d) => d[dataKey]);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;

  const points = data
    .map((d, i) => {
      const x = (i / (data.length - 1)) * 100;
      const y = 100 - ((d[dataKey] - min) / range) * 100;
      return `${x},${y}`;
    })
    .join(" ");

  // Create area fill
  const areaPoints = `0,100 ${points} 100,100`;

  return (
    <svg
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      className="w-full"
      style={{ height }}
    >
      {/* Area fill */}
      <polygon
        points={areaPoints}
        fill={color}
        fillOpacity="0.1"
      />
      {/* Line */}
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="2"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

export function PortfolioChart() {
  const [period, setPeriod] = useState("1M");
  const { data: history, isLoading } = usePortfolioHistory(period, "1D");

  const chartData = history?.data || [];
  const summary = history?.summary;

  // Calculate if overall trend is positive
  const isPositive = (summary?.total_return_pct || 0) >= 0;

  // Format date for display
  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  };

  // Daily P&L bars data
  const dailyPnL = useMemo(() => {
    if (!chartData.length) return [];
    const maxAbsPnL = Math.max(...chartData.map((d) => Math.abs(d.profit_loss_pct ?? 0)));
    return chartData.map((d) => ({
      ...d,
      barHeight: maxAbsPnL > 0 ? (Math.abs(d.profit_loss_pct ?? 0) / maxAbsPnL) * 100 : 0,
    }));
  }, [chartData]);

  if (isLoading) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <BarChart3 className="h-4 w-4 text-primary" />
            Portfolio Performance
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-[200px] flex items-center justify-center text-muted-foreground">
            Loading...
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <TooltipProvider>
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2 text-sm">
              <BarChart3 className="h-4 w-4 text-primary" />
              Portfolio Performance
            </CardTitle>
            <div className="flex gap-1">
              {PERIODS.map((p) => (
                <Button
                  key={p.value}
                  variant={period === p.value ? "default" : "ghost"}
                  size="sm"
                  className="h-6 px-2 text-xs"
                  onClick={() => setPeriod(p.value)}
                >
                  {p.label}
                </Button>
              ))}
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Summary Stats */}
          {summary && (
            <div className="grid grid-cols-4 gap-3">
              {/* Total Return */}
              <div className="space-y-1">
                <div className="flex items-center gap-1 text-xs text-muted-foreground">
                  {isPositive ? (
                    <ArrowUpRight className="h-3 w-3 text-green-500" />
                  ) : (
                    <ArrowDownRight className="h-3 w-3 text-red-500" />
                  )}
                  Total Return
                </div>
                <div
                  className={cn(
                    "text-lg font-bold",
                    isPositive ? "text-green-500" : "text-red-500"
                  )}
                >
                  {(summary.total_return_pct ?? 0) >= 0 ? "+" : ""}
                  {(summary.total_return_pct ?? 0).toFixed(2)}%
                </div>
                <div className="text-xs text-muted-foreground">
                  {formatCurrency(summary.total_return_dollars ?? 0)}
                </div>
              </div>

              {/* Max Drawdown */}
              <div className="space-y-1">
                <div className="flex items-center gap-1 text-xs text-muted-foreground">
                  <TrendingDown className="h-3 w-3 text-orange-500" />
                  Max Drawdown
                </div>
                <div className="text-lg font-bold text-orange-500">
                  -{(summary.max_drawdown_pct ?? 0).toFixed(2)}%
                </div>
                <div className="text-xs text-muted-foreground">
                  Peak to trough
                </div>
              </div>

              {/* Best Day */}
              <div className="space-y-1">
                <div className="flex items-center gap-1 text-xs text-muted-foreground">
                  <TrendingUp className="h-3 w-3 text-green-500" />
                  Best Day
                </div>
                <div className="text-lg font-bold text-green-500">
                  +{(summary.best_day?.pct ?? 0).toFixed(2)}%
                </div>
                <div className="text-xs text-muted-foreground">
                  {summary.best_day?.date ? formatDate(summary.best_day.date) : "N/A"}
                </div>
              </div>

              {/* Worst Day */}
              <div className="space-y-1">
                <div className="flex items-center gap-1 text-xs text-muted-foreground">
                  <TrendingDown className="h-3 w-3 text-red-500" />
                  Worst Day
                </div>
                <div className="text-lg font-bold text-red-500">
                  {(summary.worst_day?.pct ?? 0).toFixed(2)}%
                </div>
                <div className="text-xs text-muted-foreground">
                  {summary.worst_day?.date ? formatDate(summary.worst_day.date) : "N/A"}
                </div>
              </div>
            </div>
          )}

          {/* Equity Chart */}
          <div className="space-y-1">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>Portfolio Value</span>
              {summary && (
                <span>
                  {formatCurrency(summary.start_equity)} → {formatCurrency(summary.end_equity)}
                </span>
              )}
            </div>
            <div className="border rounded-md p-2 bg-muted/20">
              <MiniChart
                data={chartData}
                dataKey="equity"
                color={isPositive ? "#22c55e" : "#ef4444"}
                height={80}
              />
            </div>
          </div>

          {/* Daily P&L Bars */}
          <div className="space-y-1">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>Daily P&L</span>
              <span>{summary?.trading_days || 0} trading days</span>
            </div>
            <div className="border rounded-md p-2 bg-muted/20">
              <div className="flex items-end justify-between gap-px h-[60px]">
                {dailyPnL.map((day, i) => (
                  <Tooltip key={day.timestamp}>
                    <TooltipTrigger asChild>
                      <div
                        className={cn(
                          "flex-1 min-w-[3px] max-w-[12px] rounded-t-sm cursor-pointer transition-opacity hover:opacity-80",
                          (day.profit_loss_pct ?? 0) >= 0 ? "bg-green-500" : "bg-red-500"
                        )}
                        style={{ height: `${Math.max(day.barHeight, 5)}%` }}
                      />
                    </TooltipTrigger>
                    <TooltipContent>
                      <div className="text-xs space-y-1">
                        <div className="font-semibold">{formatDate(day.date)}</div>
                        <div
                          className={cn(
                            (day.profit_loss ?? 0) >= 0 ? "text-green-500" : "text-red-500"
                          )}
                        >
                          {(day.profit_loss ?? 0) >= 0 ? "+" : ""}
                          {formatCurrency(day.profit_loss ?? 0)} ({(day.profit_loss_pct ?? 0) >= 0 ? "+" : ""}
                          {(day.profit_loss_pct ?? 0).toFixed(2)}%)
                        </div>
                        <div className="text-muted-foreground">
                          Equity: {formatCurrency(day.equity)}
                        </div>
                      </div>
                    </TooltipContent>
                  </Tooltip>
                ))}
              </div>
            </div>
          </div>

          {/* Period Info */}
          <div className="flex items-center justify-between text-xs text-muted-foreground pt-1 border-t">
            <div className="flex items-center gap-1">
              <Calendar className="h-3 w-3" />
              {chartData.length > 0 && (
                <span>
                  {formatDate(chartData[0].date)} - {formatDate(chartData[chartData.length - 1].date)}
                </span>
              )}
            </div>
            {summary && (
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="text-xs">
                  High: {formatCurrency(summary.max_equity)}
                </Badge>
                <Badge variant="outline" className="text-xs">
                  Low: {formatCurrency(summary.min_equity)}
                </Badge>
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </TooltipProvider>
  );
}
