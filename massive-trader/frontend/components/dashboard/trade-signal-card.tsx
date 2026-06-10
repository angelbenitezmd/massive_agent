"use client";

import { memo, useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  TrendingUp,
  TrendingDown,
  Minus,
  Target,
  BarChart3,
  Brain,
  Zap,
  Activity,
  Radio,
  Clock,
  CheckCircle,
  XCircle,
  Info,
} from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { AllDecisionsResponse, TradeDecisionItem } from "@/lib/api";
import { useAutoTradeStatus } from "@/hooks/use-trading-data";

function formatScoreTime(isoStr?: string) {
  if (!isoStr) return null;
  const d = new Date(isoStr);
  if (isNaN(d.getTime())) return null;
  return d.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
    timeZone: "America/New_York",
  });
}

interface TradeSignalCardProps {
  decisions?: AllDecisionsResponse;
  onSelectTicker?: (ticker: string) => void;
  selectedTicker?: string;
  isLoading?: boolean;
}

export const TradeSignalCard = memo(function TradeSignalCard({
  decisions,
  onSelectTicker,
  selectedTicker,
  isLoading,
}: TradeSignalCardProps) {
  const { data: autoTradeStatus } = useAutoTradeStatus();
  const [countdown, setCountdown] = useState(0);

  // Countdown timer for next scan
  useEffect(() => {
    if (!autoTradeStatus?.enabled) return;

    const interval = autoTradeStatus.interval || 60;
    setCountdown(interval);

    const timer = setInterval(() => {
      setCountdown((prev) => (prev <= 1 ? interval : prev - 1));
    }, 1000);

    return () => clearInterval(timer);
  }, [autoTradeStatus?.enabled, autoTradeStatus?.interval]);

  // Auto-trade status banner
  const AutoTradeStatusBanner = () => {
    if (!autoTradeStatus) return null;

    const isActive = autoTradeStatus.enabled && autoTradeStatus.market_open;
    const isEnabled = autoTradeStatus.enabled;
    const marketOpen = autoTradeStatus.market_open;

    return (
      <div className={cn(
        "flex items-center justify-between px-4 py-2 rounded-t-lg border-b",
        isActive
          ? "bg-green-500/10 border-green-500/30"
          : isEnabled
            ? "bg-yellow-500/10 border-yellow-500/30"
            : "bg-muted/50 border-border"
      )}>
        <div className="flex items-center gap-3">
          {/* Live indicator */}
          <div className="flex items-center gap-2">
            {isActive ? (
              <>
                <div className="relative flex h-3 w-3">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-green-500"></span>
                </div>
                <span className="text-green-500 font-semibold text-sm">AUTO-TRADE ACTIVE</span>
              </>
            ) : isEnabled ? (
              <>
                <Radio className="h-4 w-4 text-yellow-500" />
                <span className="text-yellow-500 font-medium text-sm">
                  {marketOpen ? "SCANNING" : "WAITING — Market Closed"}
                </span>
              </>
            ) : (
              <>
                <Activity className="h-4 w-4 text-muted-foreground" />
                <span className="text-muted-foreground text-sm">Auto-Trade Disabled</span>
              </>
            )}
          </div>

          {/* Scan countdown */}
          {isActive && (
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <Clock className="h-3 w-3" />
              <span>Next scan: {countdown}s</span>
            </div>
          )}
        </div>

        {/* Trade threshold indicator */}
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="text-xs bg-background">
            Min Score: 70+
          </Badge>
          {autoTradeStatus.market_open && (
            <Badge variant="outline" className="text-xs border-green-500 text-green-500 bg-green-500/10">
              Market Open
            </Badge>
          )}
        </div>
      </div>
    );
  };

  // SACRED RULE: BUY column = will actually be traded. HOLD = not traded.
  // The backend's `action` field already encodes this (BUY only when the
  // execution gate passes), so trust it as the source of truth here.
  // Score is sorted desc within each column for visibility.
  const sortByScore = (items: TradeDecisionItem[]) =>
    [...items].sort((a, b) => (b.combinedScore ?? 0) - (a.combinedScore ?? 0));

  const buy = sortByScore(decisions?.buy ?? []);
  const hold = sortByScore(decisions?.hold ?? []);
  const sell = sortByScore(decisions?.sell ?? []);
  const counts = { buy: buy.length, hold: hold.length, sell: sell.length };

  return (
    <Card className="overflow-hidden">
      <AutoTradeStatusBanner />
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Brain className="h-5 w-5 text-primary" />
            <span className="text-base font-semibold">AI Trade Decisions</span>
            {counts.buy > 0 && autoTradeStatus?.enabled && autoTradeStatus?.market_open && (
              <Badge className="bg-green-500 text-white animate-pulse">
                {counts.buy} READY TO TRADE
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-2 text-xs">
            <Badge variant="outline" className="border-green-500 text-green-500 bg-green-500/10">
              {counts.buy} BUY
            </Badge>
            <Badge variant="outline" className="border-yellow-500 text-yellow-500 bg-yellow-500/10">
              {counts.hold} HOLD
            </Badge>
            <Badge variant="outline" className="border-red-500 text-red-500 bg-red-500/10">
              {counts.sell} SELL
            </Badge>
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div className="grid grid-cols-3 divide-x divide-border">
          {/* BUY Column */}
          <DecisionColumn
            title="BUY"
            icon={<TrendingUp className="h-4 w-4" />}
            decisions={buy}
            colorClass="green"
            onSelectTicker={onSelectTicker}
            selectedTicker={selectedTicker}
          />

          {/* HOLD Column - only LLM-analyzed */}
          <DecisionColumn
            title="HOLD"
            icon={<Minus className="h-4 w-4" />}
            decisions={hold}
            colorClass="yellow"
            onSelectTicker={onSelectTicker}
            selectedTicker={selectedTicker}
          />

          {/* SELL Column */}
          <DecisionColumn
            title="SELL"
            icon={<TrendingDown className="h-4 w-4" />}
            decisions={sell}
            colorClass="red"
            onSelectTicker={onSelectTicker}
            selectedTicker={selectedTicker}
          />
        </div>
      </CardContent>
    </Card>
  );
});

interface DecisionColumnProps {
  title: string;
  icon: React.ReactNode;
  decisions: TradeDecisionItem[];
  colorClass: "green" | "yellow" | "red";
  onSelectTicker?: (ticker: string) => void;
  selectedTicker?: string;
}

function DecisionColumn({
  title,
  icon,
  decisions,
  colorClass,
  onSelectTicker,
  selectedTicker,
}: DecisionColumnProps) {
  const colors = {
    green: {
      header: "bg-green-500/10 text-green-500",
      text: "text-green-500",
      bg: "bg-green-500",
      border: "border-green-500",
      hover: "hover:bg-green-500/10",
      selected: "bg-green-500/20 ring-1 ring-green-500",
    },
    yellow: {
      header: "bg-yellow-500/10 text-yellow-500",
      text: "text-yellow-500",
      bg: "bg-yellow-500",
      border: "border-yellow-500",
      hover: "hover:bg-yellow-500/10",
      selected: "bg-yellow-500/20 ring-1 ring-yellow-500",
    },
    red: {
      header: "bg-red-500/10 text-red-500",
      text: "text-red-500",
      bg: "bg-red-500",
      border: "border-red-500",
      hover: "hover:bg-red-500/10",
      selected: "bg-red-500/20 ring-1 ring-red-500",
    },
  };

  const c = colors[colorClass];

  return (
    <div className="flex flex-col">
      {/* Column Header */}
      <div className={cn("flex flex-col items-center justify-center py-2 px-3", c.header)}>
        <div className="flex items-center gap-1.5">
          {icon}
          <span className="font-semibold text-sm">{title}</span>
          <span className="text-xs opacity-70">({decisions.length})</span>
        </div>
        <span className="text-[10px] opacity-80 mt-0.5">
          {title === "BUY" ? "70+" : title === "SELL" ? "0-30" : "31-69"}
        </span>
      </div>

      {/* Decision List */}
      <ScrollArea className="h-[130px]">
        <div className="p-2 space-y-1">
          {decisions.length === 0 ? (
            <div className="flex items-center justify-center h-[100px] text-muted-foreground text-xs">
              No {title.toLowerCase()} decisions
            </div>
          ) : (
            decisions.map((decision, index) => (
              <button
                key={decision.ticker}
                onClick={() => onSelectTicker?.(decision.ticker)}
                className={cn(
                  "w-full flex flex-col gap-1 p-2 rounded-md transition-all text-left",
                  c.hover,
                  selectedTicker === decision.ticker && c.selected
                )}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 min-w-0">
                    {/* Rank indicator for top 3 */}
                    {index < 3 && (
                      <div className={cn(
                        "flex items-center justify-center w-5 h-5 rounded-full text-xs font-bold shrink-0",
                        index === 0 && "bg-amber-500/20 text-amber-500",
                        index === 1 && "bg-slate-400/20 text-slate-400",
                        index === 2 && "bg-orange-600/20 text-orange-600"
                      )}>
                        {index + 1}
                      </div>
                    )}
                    {index >= 3 && <div className="w-5 shrink-0" />}

                    <span className="font-bold text-sm truncate">{decision.ticker}</span>
                  </div>

                  {/* Signal Strength */}
                  <div className="flex items-center gap-1 shrink-0">
                    <span className={cn("font-bold text-lg", c.text)}>
                      {Math.round(decision.confidence * 100)}
                    </span>
                  </div>
                </div>

                {/* Score breakdown */}
                <div className="flex items-center gap-2 text-[10px] text-muted-foreground pl-7">
                  {decision.llmEnhanced ? (
                    <div className="flex items-center gap-0.5">
                      <Brain className="h-3 w-3 text-purple-400" />
                      <span className="text-purple-400">LLM: {decision.combinedScore}</span>
                      {decision.keywordScore != null && decision.keywordScore !== decision.combinedScore && (
                        <span className="opacity-80 line-through" style={{
                          color: `hsl(${Math.max(0, Math.min(100, decision.keywordScore)) * 1.2}, 85%, 50%)`
                        }}>{decision.keywordScore}</span>
                      )}
                    </div>
                  ) : (
                    <div className="flex items-center gap-0.5">
                      <Brain className="h-3 w-3" />
                      <span>AI: {decision.aiScore}</span>
                    </div>
                  )}
                  <div className="flex items-center gap-0.5">
                    <Zap className="h-3 w-3" />
                    <span>Mom: {decision.momentumScore}</span>
                  </div>
                  <Badge
                    variant="outline"
                    className={cn(
                      "text-[9px] px-1 py-0 h-4",
                      decision.urgency === "NOW" && "border-green-500 text-green-500",
                      decision.urgency === "SOON" && "border-yellow-500 text-yellow-500",
                      decision.urgency === "WAIT" && "border-muted-foreground text-muted-foreground"
                    )}
                  >
                    {decision.urgency}
                  </Badge>
                  {decision.shrinkage && (decision.shrinkage.final_shrinkage ?? 0) > 0 && (
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <div className="flex items-center gap-0.5 cursor-help">
                            {decision.shrinkage.categories_used?.map((cat) => (
                              <span key={cat} className={cn(
                                "w-1.5 h-1.5 rounded-full",
                                cat === "news" && "bg-blue-400",
                                cat === "earnings" && "bg-amber-400",
                                cat === "ratings" && "bg-purple-400",
                                cat === "consensus" && "bg-gray-400",
                              )} />
                            ))}
                            <span className={cn(
                              "text-[9px]",
                              (decision.shrinkage.final_shrinkage ?? 0) > 0.4
                                ? "text-orange-400"
                                : "text-muted-foreground"
                            )}>
                              Shrink: {Math.round((decision.shrinkage.final_shrinkage ?? 0) * 100)}%
                            </span>
                          </div>
                        </TooltipTrigger>
                        <TooltipContent side="top" className="text-xs max-w-[220px]">
                          <div className="space-y-1">
                            <p>Score: {decision.shrinkage.pre_shrinkage_score} → {decision.shrinkage.post_shrinkage_score}</p>
                            <p>Categories: {decision.shrinkage.categories_used?.map(
                              (c) => `${c} (q=${decision.shrinkage?.quality?.[c] ?? "?"})`
                            ).join(", ")}</p>
                            <p>Shrinkage: {Math.round((decision.shrinkage.blended_shrinkage ?? 0) * 100)}% × {decision.shrinkage.multi_source_factor} ({decision.shrinkage.categories_used?.length === 1 ? "single" : "multi"} source)</p>
                          </div>
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  )}
                </div>

                {/* Timestamp + trade status + reasoning */}
                <div className="flex items-center gap-2 text-[10px] text-muted-foreground pl-7 flex-wrap">
                    <div className="flex items-center gap-0.5">
                      <Clock className="h-3 w-3" />
                      <span>{formatScoreTime(decision.scoredAt) || "—"}</span>
                    </div>
                    {decision.tradeStatus === "executed" && (
                      <div className="flex items-center gap-0.5 text-green-500">
                        <CheckCircle className="h-3 w-3" />
                        <span>TRADED</span>
                      </div>
                    )}
                    {decision.tradeStatus === "blocked" && (
                      <div className="flex items-center gap-0.5 text-orange-400">
                        <XCircle className="h-3 w-3" />
                        <span className="truncate max-w-[140px]">{decision.tradeReason || "Blocked"}</span>
                      </div>
                    )}
                    {decision.reasoning && (
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Info className="h-3 w-3 cursor-help text-purple-400" />
                          </TooltipTrigger>
                          <TooltipContent side="top" className="text-xs max-w-[280px]">
                            <p>{decision.reasoning}</p>
                            {decision.signals && decision.signals.length > 0 && (
                              <p className="mt-1 opacity-70">Signals: {decision.signals.join(", ")}</p>
                            )}
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    )}
                </div>

                {/* Confidence bar */}
                <div className="w-full h-1 bg-secondary rounded-full overflow-hidden ml-7 pr-2">
                  <div
                    className={cn("h-full rounded-full", c.bg)}
                    style={{ width: `${decision.confidence * 100}%` }}
                  />
                </div>
              </button>
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
