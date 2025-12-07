"use client";

import { memo } from "react";
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
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { AllDecisionsResponse, TradeDecisionItem } from "@/lib/api";

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
  if (isLoading) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Target className="h-4 w-4 text-muted-foreground" />
            Trade Decisions
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
            <div className="flex items-center gap-2">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
              Analyzing watchlist...
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (!decisions || decisions.total === 0) {
    return (
      <Card className="border-dashed">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Target className="h-4 w-4 text-muted-foreground" />
            Trade Decisions
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
            No trade decisions available
          </div>
        </CardContent>
      </Card>
    );
  }

  const { buy, hold, sell, counts } = decisions;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Brain className="h-5 w-5 text-primary" />
            <span className="text-base font-semibold">AI Trade Decisions</span>
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

          {/* HOLD Column */}
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
      <div className={cn("flex items-center justify-center gap-1.5 py-2 px-3", c.header)}>
        {icon}
        <span className="font-semibold text-sm">{title}</span>
        <span className="text-xs opacity-70">({decisions.length})</span>
      </div>

      {/* Decision List */}
      <ScrollArea className="h-[220px]">
        <div className="p-2 space-y-1">
          {decisions.length === 0 ? (
            <div className="flex items-center justify-center h-[200px] text-muted-foreground text-xs">
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
                  <div className="flex items-center gap-0.5">
                    <Brain className="h-3 w-3" />
                    <span>AI: {decision.aiScore}</span>
                  </div>
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
