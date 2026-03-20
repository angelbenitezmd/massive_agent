"use client";

import {
  Brain,
  TrendingUp,
  ChevronRight,
  Activity,
  Zap,
  Info,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn, getDirectionBgColor } from "@/lib/utils";
import type { Direction } from "@/types";

interface AIAgentsPanelProps {
  ticker?: string;
  aiScore?: number;
  momentumScore?: number;
  combinedScore?: number;
  llmEnhanced?: boolean;
  action?: string;
  isLoading: boolean;
}

function scoreToDirection(score: number | undefined): Direction {
  if (score === undefined) return "neutral";
  if (score >= 60) return "bullish";
  if (score <= 40) return "bearish";
  return "neutral";
}

function DirectionIcon({ direction }: { direction: Direction }) {
  switch (direction) {
    case "bullish":
      return <TrendingUp className="h-4 w-4" />;
    case "bearish":
      return <TrendingUp className="h-4 w-4 rotate-180" />;
    default:
      return <ChevronRight className="h-4 w-4" />;
  }
}

function ScoreCard({
  score,
  icon: Icon,
  title,
}: {
  score: number | undefined;
  icon: React.ElementType;
  title: string;
}) {
  if (score === undefined) {
    return (
      <div className="p-3 rounded-lg bg-secondary/30 space-y-1">
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-muted-foreground" />
          <span className="font-medium text-sm">{title}</span>
        </div>
        <p className="text-xs text-muted-foreground">Select a ticker with trade data...</p>
      </div>
    );
  }

  const direction = scoreToDirection(score);

  return (
    <div className="p-3 rounded-lg bg-secondary/30 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-primary" />
          <span className="font-medium text-sm">{title}</span>
        </div>
        <Badge className={cn("capitalize text-xs", getDirectionBgColor(direction))}>
          <DirectionIcon direction={direction} />
          <span className="ml-1">{direction}</span>
        </Badge>
      </div>

      <div className="flex items-center gap-2">
        <Progress
          value={score}
          className={cn(
            "h-1.5 flex-1",
            direction === "bullish" && "[&>div]:bg-green-500",
            direction === "bearish" && "[&>div]:bg-red-500",
            direction === "neutral" && "[&>div]:bg-yellow-500"
          )}
        />
        <span className="text-xs font-medium w-10">
          {Math.round(score)}
        </span>
      </div>
    </div>
  );
}

export function AIAgentsPanel({
  ticker,
  aiScore,
  momentumScore,
  combinedScore,
  llmEnhanced,
  action,
  isLoading,
}: AIAgentsPanelProps) {
  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Brain className="h-5 w-5" />
            AI Agents
            {ticker && <Badge variant="outline" className="text-[10px] font-bold">{ticker}</Badge>}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="animate-pulse">
                <div className="h-20 bg-secondary rounded-lg" />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  const hasData = combinedScore !== undefined;
  const combinedDirection = scoreToDirection(combinedScore);

  return (
    <TooltipProvider>
      <Card className="card-hover">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2">
            <Brain className="h-5 w-5 text-primary" />
            AI Agents Analysis
            {ticker && <Badge variant="outline" className="text-[10px] font-bold">{ticker}</Badge>}
            {hasData && (
              <Badge variant={llmEnhanced ? "default" : "secondary"} className="text-[10px]">
                {llmEnhanced ? "LLM" : "Keyword"}
              </Badge>
            )}
            <Tooltip>
              <TooltipTrigger asChild>
                <Info className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground cursor-help" />
              </TooltipTrigger>
              <TooltipContent side="bottom" className="max-w-[300px] p-3">
                <div className="space-y-2 text-xs">
                  <p className="font-semibold">Trade-Driving Scores</p>
                  <div className="space-y-1.5">
                    <p><strong>Sentiment:</strong> News + earnings + analyst ratings analysis. LLM-enhanced when keyword score passes gate.</p>
                    <p><strong>Momentum:</strong> Price action, volume, and trend strength signals.</p>
                    <p><strong>Combined:</strong> Weighted blend that drives auto-trade decisions.</p>
                  </div>
                  <div className="pt-1 border-t border-border">
                    <p className="text-muted-foreground">These are the actual scores used by the auto-trader, not separate estimates.</p>
                  </div>
                </div>
              </TooltipContent>
            </Tooltip>
          </CardTitle>
          <CardDescription>
            Scores driving auto-trade decisions
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 pt-0">
          {/* Combined Score - prominent display */}
          {hasData ? (
            <div className={cn(
              "p-4 rounded-lg border space-y-2",
              combinedDirection === "bullish" && "border-green-500/30 bg-green-500/5",
              combinedDirection === "bearish" && "border-red-500/30 bg-red-500/5",
              combinedDirection === "neutral" && "border-yellow-500/30 bg-yellow-500/5",
            )}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Zap className="h-4 w-4 text-primary" />
                  <span className="font-semibold text-sm">Combined Score</span>
                </div>
                {action && (
                  <Badge className={cn(
                    "text-xs font-bold",
                    action === "BUY" && "bg-green-600",
                    action === "SELL" && "bg-red-600",
                    action === "HOLD" && "bg-yellow-600",
                  )}>
                    {action}
                  </Badge>
                )}
              </div>
              <div className="flex items-center gap-3">
                <span className={cn(
                  "text-3xl font-bold tabular-nums",
                  combinedDirection === "bullish" && "text-green-400",
                  combinedDirection === "bearish" && "text-red-400",
                  combinedDirection === "neutral" && "text-yellow-400",
                )}>
                  {combinedScore!.toFixed(1)}
                </span>
                <span className="text-xs text-muted-foreground">/100</span>
              </div>
              <p className="text-[10px] text-muted-foreground">Drives auto-trades</p>
            </div>
          ) : (
            <div className="p-4 rounded-lg bg-secondary/30 text-center">
              <p className="text-xs text-muted-foreground">Select a ticker with trade data to see scores</p>
            </div>
          )}

          <ScoreCard
            score={aiScore}
            icon={Activity}
            title="Sentiment Agent"
          />
          <ScoreCard
            score={momentumScore}
            icon={TrendingUp}
            title="Momentum Agent"
          />
        </CardContent>
      </Card>
    </TooltipProvider>
  );
}
