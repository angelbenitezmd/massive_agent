"use client";

import { memo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Grid3X3, Info } from "lucide-react";
import { cn, formatCurrency, formatPercent } from "@/lib/utils";
import type { Position } from "@/types";

interface PortfolioHeatmapProps {
  positions: Position[];
  onSelectTicker?: (ticker: string) => void;
  selectedTicker?: string;
}

function getHeatColor(pctChange: number): string {
  if (pctChange >= 10) return "bg-green-600 hover:bg-green-500";
  if (pctChange >= 5) return "bg-green-500 hover:bg-green-400";
  if (pctChange >= 2) return "bg-green-500/70 hover:bg-green-500/60";
  if (pctChange >= 0.5) return "bg-green-500/40 hover:bg-green-500/30";
  if (pctChange > -0.5) return "bg-gray-600 hover:bg-gray-500";
  if (pctChange > -2) return "bg-red-500/40 hover:bg-red-500/30";
  if (pctChange > -5) return "bg-red-500/70 hover:bg-red-500/60";
  if (pctChange > -10) return "bg-red-500 hover:bg-red-400";
  return "bg-red-600 hover:bg-red-500";
}

function getTextColor(pctChange: number): string {
  const absChange = Math.abs(pctChange);
  if (absChange >= 2) return "text-white";
  return "text-white/90";
}

export const PortfolioHeatmap = memo(function PortfolioHeatmap({
  positions,
  onSelectTicker,
  selectedTicker,
}: PortfolioHeatmapProps) {
  // Sort by market value (size) for visual importance
  const sortedPositions = [...positions].sort(
    (a, b) => Math.abs(b.marketValue) - Math.abs(a.marketValue)
  );

  // Calculate total market value for sizing
  const totalValue = positions.reduce((sum, p) => sum + Math.abs(p.marketValue), 0);

  if (positions.length === 0) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Grid3X3 className="h-4 w-4 text-primary" />
            Portfolio Heatmap
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center h-24 text-muted-foreground text-sm">
            No positions to display
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <TooltipProvider>
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Grid3X3 className="h-4 w-4 text-primary" />
            Portfolio Heatmap
            <Tooltip>
              <TooltipTrigger asChild>
                <Info className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground cursor-help" />
              </TooltipTrigger>
              <TooltipContent side="bottom" className="max-w-[250px] p-3">
                <div className="space-y-2 text-xs">
                  <p className="font-semibold">Portfolio Heatmap</p>
                  <p>Visual representation of position performance. Size = position weight. Color = P&L %.</p>
                  <div className="flex gap-1 pt-1">
                    <div className="w-4 h-4 bg-green-600 rounded" />
                    <div className="w-4 h-4 bg-green-500 rounded" />
                    <div className="w-4 h-4 bg-gray-600 rounded" />
                    <div className="w-4 h-4 bg-red-500 rounded" />
                    <div className="w-4 h-4 bg-red-600 rounded" />
                  </div>
                  <p className="text-muted-foreground">Green = profit, Red = loss, Gray = flat</p>
                </div>
              </TooltipContent>
            </Tooltip>
            <Badge variant="secondary" className="ml-auto text-xs">
              {positions.length} positions
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
          <div className="flex flex-wrap gap-1">
            {sortedPositions.map((position) => {
              // Calculate relative size (min 60px, max based on weight)
              const weight = Math.abs(position.marketValue) / totalValue;
              const minWidth = 60;
              const maxWidth = 120;
              const width = Math.max(minWidth, Math.min(maxWidth, weight * 400));

              return (
                <Tooltip key={position.symbol}>
                  <TooltipTrigger asChild>
                    <button
                      onClick={() => onSelectTicker?.(position.symbol)}
                      className={cn(
                        "rounded-md p-2 transition-all cursor-pointer",
                        getHeatColor(position.unrealizedPLPercent),
                        getTextColor(position.unrealizedPLPercent),
                        selectedTicker === position.symbol && "ring-2 ring-white ring-offset-2 ring-offset-background"
                      )}
                      style={{ width: `${width}px` }}
                    >
                      <div className="font-bold text-xs truncate">{position.symbol}</div>
                      <div className="text-[10px] opacity-90">
                        {position.unrealizedPLPercent >= 0 ? "+" : ""}
                        {position.unrealizedPLPercent.toFixed(1)}%
                      </div>
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="top" className="p-3">
                    <div className="space-y-1 text-xs">
                      <div className="font-bold">{position.symbol}</div>
                      <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                        <span className="text-muted-foreground">Qty:</span>
                        <span>{position.qty}</span>
                        <span className="text-muted-foreground">Value:</span>
                        <span>{formatCurrency(position.marketValue)}</span>
                        <span className="text-muted-foreground">P&L:</span>
                        <span className={position.unrealizedPL >= 0 ? "text-green-500" : "text-red-500"}>
                          {formatCurrency(position.unrealizedPL)} ({formatPercent(position.unrealizedPLPercent)})
                        </span>
                        <span className="text-muted-foreground">Entry:</span>
                        <span>{formatCurrency(position.avgEntryPrice)}</span>
                        <span className="text-muted-foreground">Current:</span>
                        <span>{formatCurrency(position.currentPrice)}</span>
                      </div>
                    </div>
                  </TooltipContent>
                </Tooltip>
              );
            })}
          </div>

          {/* Legend */}
          <div className="flex items-center justify-center gap-2 mt-3 text-[10px] text-muted-foreground">
            <span>-10%</span>
            <div className="flex gap-0.5">
              <div className="w-4 h-2 bg-red-600 rounded-sm" />
              <div className="w-4 h-2 bg-red-500 rounded-sm" />
              <div className="w-4 h-2 bg-red-500/40 rounded-sm" />
              <div className="w-4 h-2 bg-gray-600 rounded-sm" />
              <div className="w-4 h-2 bg-green-500/40 rounded-sm" />
              <div className="w-4 h-2 bg-green-500 rounded-sm" />
              <div className="w-4 h-2 bg-green-600 rounded-sm" />
            </div>
            <span>+10%</span>
          </div>
        </CardContent>
      </Card>
    </TooltipProvider>
  );
});
