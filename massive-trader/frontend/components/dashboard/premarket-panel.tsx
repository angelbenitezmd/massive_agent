"use client";

import { Sunrise, Zap, Clock, CheckCircle2, AlertCircle } from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import type { PremarketStatus } from "@/lib/api";

interface PremarketPanelProps {
  data?: PremarketStatus;
  isLoading?: boolean;
  onSelectTicker?: (ticker: string) => void;
}

const phaseBadge: Record<string, { label: string; className: string }> = {
  waiting: { label: "Waiting", className: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30" },
  scanning: { label: "Scanning", className: "bg-blue-500/20 text-blue-400 border-blue-500/30 animate-pulse" },
  ready: { label: "Ready", className: "bg-green-500/20 text-green-400 border-green-500/30" },
  bell_rush: { label: "Bell Rush", className: "bg-orange-500/20 text-orange-400 border-orange-500/30 animate-pulse" },
  completed: { label: "Completed", className: "bg-zinc-500/20 text-zinc-400 border-zinc-500/30" },
  inactive: { label: "Inactive", className: "bg-zinc-700/20 text-zinc-500 border-zinc-700/30" },
};

const sourceBadge: Record<string, { label: string; className: string }> = {
  "news+gap": { label: "News+Gap", className: "bg-purple-500/20 text-purple-400 border-purple-500/30" },
  "gap_scan": { label: "Gap", className: "bg-orange-500/20 text-orange-400 border-orange-500/30" },
  "news": { label: "News", className: "bg-blue-500/20 text-blue-400 border-blue-500/30" },
  "trending": { label: "Trending", className: "bg-cyan-500/20 text-cyan-400 border-cyan-500/30" },
};

export function PremarketPanel({ data, isLoading, onSelectTicker }: PremarketPanelProps) {
  const phase = data?.phase || "inactive";
  const badge = phaseBadge[phase] || phaseBadge.inactive;
  const readyList = data?.ready_list || [];
  const rushResults = data?.bell_rush_results || [];
  const hasRushResults = rushResults.length > 0;

  // Collapsed summary for completed phase during market hours
  if (phase === "completed" && data?.market_status === "open") {
    const executedCount = rushResults.filter(r => r.status === "executed").length;
    return (
      <Card className="border-border/40 bg-card/50">
        <CardHeader className="pb-1 pt-3 px-4">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Sunrise className="h-4 w-4 text-zinc-500" />
              Pre-Market
            </CardTitle>
            <Badge variant="outline" className={cn("text-xs", badge.className)}>
              {executedCount > 0 ? `${executedCount} traded` : "No trades"}
            </Badge>
          </div>
        </CardHeader>
        {hasRushResults && (
          <CardContent className="px-4 pb-3 pt-1">
            <div className="flex flex-wrap gap-1.5">
              {rushResults.map((r) => (
                <button
                  key={r.ticker}
                  onClick={() => onSelectTicker?.(r.ticker)}
                  className="text-xs px-1.5 py-0.5 rounded bg-zinc-800/50 hover:bg-zinc-700/60 transition-colors"
                >
                  <span className="font-medium">{r.ticker}</span>
                  <span className={cn("ml-1", r.status === "executed" ? "text-green-400" : "text-red-400")}>
                    {r.status === "executed" ? `${r.score}` : "fail"}
                  </span>
                </button>
              ))}
            </div>
          </CardContent>
        )}
      </Card>
    );
  }

  return (
    <Card className="border-border/40 bg-card/50">
      <CardHeader className="pb-2 pt-3 px-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Sunrise className="h-4 w-4 text-amber-400" />
            Pre-Market Scanner
          </CardTitle>
          <Badge variant="outline" className={cn("text-xs", badge.className)}>
            {badge.label}
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground mt-1">{data?.next_event || "Loading..."}</p>
      </CardHeader>

      <CardContent className="px-4 pb-3 pt-0">
        {/* Ready list */}
        {readyList.length > 0 && (
          <div className="mb-2">
            <div className="text-xs text-muted-foreground mb-1.5 font-medium">
              Ready List ({readyList.length})
            </div>
            <ScrollArea className="h-[140px]">
              <div className="space-y-1">
                {readyList.map((item) => {
                  const src = sourceBadge[item.source] || sourceBadge.news;
                  return (
                    <button
                      key={item.ticker}
                      onClick={() => onSelectTicker?.(item.ticker)}
                      className="w-full flex items-center justify-between px-2 py-1.5 rounded text-xs hover:bg-zinc-800/60 transition-colors group"
                    >
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-foreground group-hover:text-amber-400 transition-colors">
                          {item.ticker}
                        </span>
                        <Badge variant="outline" className={cn("text-[10px] px-1 py-0", src.className)}>
                          {src.label}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-3">
                        {item.gap_pct != null && (
                          <span className={cn(
                            "font-mono",
                            item.gap_pct > 0 ? "text-green-400" : "text-red-400"
                          )}>
                            {item.gap_pct > 0 ? "+" : ""}{item.gap_pct.toFixed(1)}%
                          </span>
                        )}
                        <span className="text-muted-foreground font-mono w-8 text-right">
                          {item.score}
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>
            </ScrollArea>
          </div>
        )}

        {/* Bell rush results */}
        {hasRushResults && (
          <div>
            <div className="text-xs text-muted-foreground mb-1.5 font-medium flex items-center gap-1">
              <Zap className="h-3 w-3 text-orange-400" />
              Bell Rush Results
            </div>
            <ScrollArea className={cn(readyList.length > 0 ? "h-[80px]" : "h-[140px]")}>
              <div className="space-y-1">
                {rushResults.map((r) => {
                  const isExecuted = r.status === "executed";
                  return (
                    <button
                      key={r.ticker}
                      onClick={() => onSelectTicker?.(r.ticker)}
                      className="w-full flex items-center justify-between px-2 py-1.5 rounded text-xs hover:bg-zinc-800/60 transition-colors"
                    >
                      <div className="flex items-center gap-2">
                        {isExecuted ? (
                          <CheckCircle2 className="h-3 w-3 text-green-400" />
                        ) : (
                          <AlertCircle className="h-3 w-3 text-red-400" />
                        )}
                        <span className="font-medium">{r.ticker}</span>
                        {r.quantity && r.price && (
                          <span className="text-muted-foreground">
                            {r.quantity} @ ${r.price.toFixed(2)}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        {r.gap_pct != null && (
                          <span className={cn(
                            "font-mono",
                            r.gap_pct > 0 ? "text-green-400" : "text-red-400"
                          )}>
                            {r.gap_pct > 0 ? "+" : ""}{r.gap_pct.toFixed(1)}%
                          </span>
                        )}
                        <span className="font-mono">{r.score}</span>
                        <Badge
                          variant="outline"
                          className={cn(
                            "text-[10px] px-1 py-0",
                            isExecuted
                              ? "bg-green-500/20 text-green-400 border-green-500/30"
                              : "bg-red-500/20 text-red-400 border-red-500/30"
                          )}
                        >
                          {r.status}
                        </Badge>
                      </div>
                    </button>
                  );
                })}
              </div>
            </ScrollArea>
          </div>
        )}

        {/* Empty states */}
        {phase === "waiting" && readyList.length === 0 && !hasRushResults && (
          <div className="flex flex-col items-center justify-center h-[100px] text-muted-foreground">
            <Clock className="h-6 w-6 mb-2 opacity-50" />
            <span className="text-xs">Ready list builds at 9:15 AM ET</span>
          </div>
        )}

        {phase === "inactive" && (
          <div className="flex flex-col items-center justify-center h-[100px] text-muted-foreground">
            <Sunrise className="h-6 w-6 mb-2 opacity-50" />
            <span className="text-xs">Available during pre-market hours</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
