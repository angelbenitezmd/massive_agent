"use client";

import { Users, Newspaper, Brain, Activity, LineChart, Clock, Flame, Info } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { TradeDecision } from "@/types";

interface AgentScoresCardProps {
  decision: TradeDecision | undefined;
  ticker: string;
}

// Each row in the breakdown table. Weight is the planner's allocation
// (catalyst 50%, timing 22%, technical 18%, momentum 10%); bonuses are
// separate adjustments on top of the weighted blend.
interface AgentRow {
  icon: React.ReactNode;
  label: string;
  score: number | undefined;
  weight: number; // 0-1, share of base setup score
  tooltip: string;
  badge?: string;
}

export function AgentScoresCard({ decision, ticker }: AgentScoresCardProps) {
  if (!decision) {
    return (
      <Card className="card-hover">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2">
            <Users className="h-5 w-5 text-primary" />
            Agent Scores
          </CardTitle>
          <CardDescription>Per-agent breakdown for the selected ticker</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="text-xs text-muted-foreground py-6 text-center">
            Select a ticker and run analysis to see agent scores.
          </div>
        </CardContent>
      </Card>
    );
  }

  // The "catalyst" weight (0.50) covers the LLM-enhanced sentiment if
  // available, otherwise the keyword sentiment.
  const catalystScore = decision.llmEnhanced
    ? decision.aiScore
    : decision.sentimentScore ?? decision.aiScore;

  const rows: AgentRow[] = [
    {
      icon: <Newspaper className="h-3.5 w-3.5 text-purple-500" />,
      label: decision.llmEnhanced ? "News + AI (LLM)" : "News (Keyword)",
      score: catalystScore,
      weight: 0.5,
      tooltip: decision.llmEnhanced
        ? "Catalyst score: LLM read article bodies + keyword sentiment. Largest weight (50%)."
        : "Catalyst score: keyword sentiment only — LLM did not confirm. Largest weight (50%).",
      badge: decision.llmEnhanced ? "LLM ✓" : "KW only",
    },
    {
      icon: <Clock className="h-3.5 w-3.5 text-cyan-500" />,
      label: "Timing",
      score: decision.timingScore,
      weight: 0.22,
      tooltip:
        "Entry timing — penalizes chasing. Early entries get bonus, late/extended get penalty.",
      badge: decision.entryTimingState?.toUpperCase(),
    },
    {
      icon: <LineChart className="h-3.5 w-3.5 text-blue-500" />,
      label: "Technical",
      score: decision.technicalScore,
      weight: 0.18,
      tooltip: "RSI + MACD + trend composite from 15-min bars.",
      badge: decision.technicalRegime?.replace("_", " ").toUpperCase(),
    },
    {
      icon: <Activity className="h-3.5 w-3.5 text-pink-500" />,
      label: "Momentum",
      score: decision.momentumScore,
      weight: 0.1,
      tooltip: "Price/volume momentum.",
      badge:
        typeof decision.priceChangePct === "number"
          ? `${decision.priceChangePct > 0 ? "+" : ""}${decision.priceChangePct.toFixed(2)}%`
          : undefined,
    },
  ];

  const baseScore = rows.reduce((acc, r) => {
    if (typeof r.score !== "number") return acc;
    return acc + r.score * r.weight;
  }, 0);

  const finalScore = decision.combinedScore ?? Math.round(decision.confidence * 100);
  const bonusOrPenalty = finalScore - baseScore;

  // Action = backend's verdict (BUY only when actually tradeable).
  // Score band ruler stays on the bottom as reference for the user.
  const rawAction = decision.action;
  const masterAction: "BUY" | "HOLD" | "SELL" =
    rawAction === "BUY" ? "BUY" : rawAction === "SELL" ? "SELL" : "HOLD";

  return (
    <TooltipProvider>
      <Card className="card-hover">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2">
            <Users className="h-5 w-5 text-primary" />
            Agent Scores
            <Badge variant="outline" className="text-[10px] font-bold ml-1">
              {ticker}
            </Badge>
            <Tooltip>
              <TooltipTrigger asChild>
                <Info className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground cursor-help" />
              </TooltipTrigger>
              <TooltipContent side="bottom" className="max-w-[300px] p-3 text-xs">
                <p className="font-semibold mb-1">How the final score is built:</p>
                <p className="text-muted-foreground">
                  Each agent produces an independent 0–100 score. They&apos;re combined with
                  fixed weights (News 50%, Timing 22%, Technical 18%, Momentum 10%), then
                  the planner adds bonuses (early entry, fresh catalyst, bullish regime)
                  or penalties (late, extended, bearish), and clamps the result to [0, 100].
                </p>
              </TooltipContent>
            </Tooltip>
          </CardTitle>
          <CardDescription>
            Independent agent decisions and how they combine into the final verdict
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-2">
            {rows.map((r) => (
              <AgentScoreRow key={r.label} row={r} />
            ))}
          </div>

          {/* Catalyst-freshness modifier (not a score, just context) */}
          <div className="bg-muted/30 rounded-md p-2 flex items-center justify-between text-xs">
            <div className="flex items-center gap-1.5">
              <Flame className={cn(
                "h-3.5 w-3.5",
                decision.freshCatalyst ? "text-orange-500" : "text-muted-foreground"
              )} />
              <span className="text-muted-foreground">Catalyst Freshness</span>
            </div>
            <span className="font-medium">
              {decision.freshCatalyst ? "FRESH" : "STALE"}
              {typeof decision.newsAgeHours === "number" && (
                <span className="text-muted-foreground font-normal ml-1">
                  ({decision.newsAgeHours.toFixed(1)}h)
                </span>
              )}
            </span>
          </div>

          {/* Math summary */}
          <div className="border-t border-border pt-3 space-y-1.5">
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">Weighted base score</span>
              <span className="font-medium">{baseScore.toFixed(1)}</span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">
                Bonuses / penalties
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Info className="h-3 w-3 inline ml-1 text-muted-foreground hover:text-foreground cursor-help" />
                  </TooltipTrigger>
                  <TooltipContent side="bottom" className="max-w-[260px] p-2 text-xs">
                    Adjustments applied by the planner: early entry +10, fresh
                    catalyst +2.5, very fresh +4, LLM confirmed +3, strong
                    bullish +4, calm entry +2.5, late −12, extended −20,
                    bearish −8, etc. Then clamped to [0, 100].
                  </TooltipContent>
                </Tooltip>
              </span>
              <span
                className={cn(
                  "font-medium",
                  bonusOrPenalty > 0 ? "text-green-500" : bonusOrPenalty < 0 ? "text-red-500" : "text-muted-foreground"
                )}
              >
                {bonusOrPenalty > 0 ? "+" : ""}
                {bonusOrPenalty.toFixed(1)}
              </span>
            </div>
            <div className="flex items-center justify-between pt-1.5 border-t border-border">
              <span className="text-sm font-semibold">Final Setup Score</span>
              <div className="flex items-center gap-2">
                <span className="text-xl font-bold">
                  {Math.round(finalScore)}
                  <span className="text-xs text-muted-foreground font-normal">/100</span>
                </span>
                <Badge
                  className={cn(
                    "text-[10px]",
                    masterAction === "BUY" && "bg-green-600 text-white",
                    masterAction === "HOLD" && "bg-yellow-600 text-white",
                    masterAction === "SELL" && "bg-red-600 text-white"
                  )}
                >
                  {masterAction}
                </Badge>
              </div>
            </div>
            <div className="flex justify-between text-[10px] text-muted-foreground pt-0.5">
              <span>SELL 0–29</span>
              <span>HOLD 30–69</span>
              <span>BUY 70–100</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </TooltipProvider>
  );
}

function AgentScoreRow({ row }: { row: AgentRow }) {
  const hasScore = typeof row.score === "number";
  const v = hasScore ? Math.round(row.score!) : null;
  const color =
    v === null
      ? "text-muted-foreground"
      : v >= 70
      ? "text-green-500"
      : v >= 30
      ? "text-yellow-500"
      : "text-red-500";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div className="space-y-1">
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-1.5 min-w-0">
              {row.icon}
              <span className="font-medium truncate">{row.label}</span>
              {row.badge && (
                <Badge variant="outline" className="text-[9px] px-1 py-0">
                  {row.badge}
                </Badge>
              )}
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <span className={cn("font-semibold tabular-nums", color)}>
                {v === null ? "—" : v}
              </span>
              <span className="text-[10px] text-muted-foreground tabular-nums w-12 text-right">
                × {(row.weight * 100).toFixed(0)}%
              </span>
            </div>
          </div>
          <Progress
            value={v ?? 0}
            className={cn(
              "h-1.5",
              v !== null && v >= 70 && "[&>div]:bg-green-500",
              v !== null && v >= 30 && v < 70 && "[&>div]:bg-yellow-500",
              v !== null && v < 30 && "[&>div]:bg-red-500"
            )}
          />
        </div>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="max-w-[260px] p-2 text-xs">
        {row.tooltip}
      </TooltipContent>
    </Tooltip>
  );
}
