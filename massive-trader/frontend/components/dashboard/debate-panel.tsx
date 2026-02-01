"use client";

import { useState } from "react";
import {
  Users,
  Scale,
  ShieldAlert,
  TrendingUp,
  TrendingDown,
  Minus,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  CheckCircle,
  XCircle,
  RefreshCw,
  Brain,
  Target,
  Clock,
  BarChart3,
  Lightbulb,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useDebate, useAgentWeights, useMemoryStats } from "@/hooks/use-trading-data";
import type { DebateResponse, DebateOutcome, AgentPosition, DebateDirection } from "@/types";

interface DebatePanelProps {
  ticker: string;
}

const AGENT_ICONS: Record<string, React.ElementType> = {
  news: Brain,
  technical: BarChart3,
  macro: TrendingUp,
  contrarian: Scale,
  risk: ShieldAlert,
  timing: Clock,
  exit: Target,
};

const AGENT_LABELS: Record<string, string> = {
  news: "News Intelligence",
  technical: "Technical Analysis",
  macro: "Macro Regime",
  contrarian: "Contrarian",
  risk: "Risk Management",
  timing: "Trade Timing",
  exit: "Exit Strategy",
};

function getDirectionColor(direction: DebateDirection | string): string {
  switch (direction) {
    case "STRONG_BUY":
    case "BUY":
      return "bg-green-500/20 text-green-500 border-green-500/30";
    case "STRONG_SELL":
    case "SELL":
      return "bg-red-500/20 text-red-500 border-red-500/30";
    default:
      return "bg-yellow-500/20 text-yellow-500 border-yellow-500/30";
  }
}

function getDirectionIcon(direction: DebateDirection | string) {
  switch (direction) {
    case "STRONG_BUY":
    case "BUY":
      return <TrendingUp className="h-4 w-4" />;
    case "STRONG_SELL":
    case "SELL":
      return <TrendingDown className="h-4 w-4" />;
    default:
      return <Minus className="h-4 w-4" />;
  }
}

function AgentVoteCard({
  agentName,
  vote,
  weight,
}: {
  agentName: string;
  vote: string;
  weight: number;
}) {
  const Icon = AGENT_ICONS[agentName] || Brain;
  const label = AGENT_LABELS[agentName] || agentName;

  return (
    <div className="flex items-center justify-between p-2 rounded-lg bg-secondary/30 hover:bg-secondary/50 transition-colors">
      <div className="flex items-center gap-2">
        <Icon className="h-4 w-4 text-muted-foreground" />
        <span className="text-sm font-medium">{label}</span>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-foreground">
          {(weight * 100).toFixed(0)}%
        </span>
        <Badge variant="outline" className={cn("text-xs", getDirectionColor(vote))}>
          {getDirectionIcon(vote)}
          <span className="ml-1">{vote}</span>
        </Badge>
      </div>
    </div>
  );
}

function OutcomeDisplay({ outcome }: { outcome: DebateOutcome }) {
  const [showDetails, setShowDetails] = useState(false);

  return (
    <div className="space-y-4">
      {/* Main Decision */}
      <div className="flex items-center justify-between p-4 rounded-lg bg-secondary/40">
        <div className="flex items-center gap-3">
          <div className={cn(
            "p-2 rounded-full",
            outcome.finalAction.includes("BUY") ? "bg-green-500/20" :
            outcome.finalAction.includes("SELL") ? "bg-red-500/20" : "bg-yellow-500/20"
          )}>
            {getDirectionIcon(outcome.finalAction)}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xl font-bold">{outcome.finalAction}</span>
              {outcome.riskVeto && (
                <Badge variant="destructive" className="text-xs">
                  <XCircle className="h-3 w-3 mr-1" />
                  VETOED
                </Badge>
              )}
            </div>
            <p className="text-sm text-muted-foreground">
              Consensus: {outcome.consensusConfidence.toFixed(0)}%
            </p>
          </div>
        </div>
        <div className="text-right">
          {outcome.suggestedShares > 0 && (
            <div>
              <span className="text-lg font-semibold">{outcome.suggestedShares} shares</span>
              <p className="text-xs text-muted-foreground">
                Max ${outcome.maxPositionValue.toLocaleString()}
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Risk Veto Warning */}
      {outcome.riskVeto && outcome.riskVetoReason && (
        <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/30">
          <div className="flex items-start gap-2">
            <ShieldAlert className="h-5 w-5 text-destructive mt-0.5" />
            <div>
              <p className="font-medium text-destructive">Risk Veto Active</p>
              <p className="text-sm text-muted-foreground">{outcome.riskVetoReason}</p>
            </div>
          </div>
        </div>
      )}

      {/* Vote Breakdown */}
      <div className="space-y-2">
        <h4 className="text-sm font-medium flex items-center gap-2">
          <Users className="h-4 w-4" />
          Agent Votes
        </h4>
        <div className="space-y-1">
          {Object.entries(outcome.voteBreakdown || {}).map(([agent, vote]) => (
            <AgentVoteCard
              key={agent}
              agentName={agent}
              vote={vote}
              weight={outcome.voteWeights?.[agent] || 0.1}
            />
          ))}
        </div>
      </div>

      {/* Collapsible Details */}
      <Button
        variant="ghost"
        size="sm"
        className="w-full"
        onClick={() => setShowDetails(!showDetails)}
      >
        {showDetails ? (
          <>
            <ChevronUp className="h-4 w-4 mr-2" />
            Hide Details
          </>
        ) : (
          <>
            <ChevronDown className="h-4 w-4 mr-2" />
            Show Details
          </>
        )}
      </Button>
      {showDetails && (
        <div className="space-y-4 mt-4">
          {/* Risk Warnings */}
          {outcome.riskWarnings && outcome.riskWarnings.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-sm font-medium flex items-center gap-2 text-yellow-500">
                <AlertTriangle className="h-4 w-4" />
                Risk Warnings
              </h4>
              <ul className="space-y-1">
                {outcome.riskWarnings.map((warning, i) => (
                  <li key={i} className="text-sm text-muted-foreground pl-6">
                    • {warning}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Key Agreements */}
          {outcome.keyAgreements && outcome.keyAgreements.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-sm font-medium flex items-center gap-2 text-green-500">
                <CheckCircle className="h-4 w-4" />
                Key Agreements
              </h4>
              <ul className="space-y-1">
                {outcome.keyAgreements.map((agreement, i) => (
                  <li key={i} className="text-sm text-muted-foreground pl-6">
                    • {agreement}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Unresolved Disagreements */}
          {outcome.unresolvedDisagreements && outcome.unresolvedDisagreements.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-sm font-medium flex items-center gap-2 text-orange-500">
                <Scale className="h-4 w-4" />
                Unresolved Disagreements
              </h4>
              <ul className="space-y-1">
                {outcome.unresolvedDisagreements.map((disagreement, i) => (
                  <li key={i} className="text-sm text-muted-foreground pl-6">
                    • {disagreement}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Debate Summary */}
          {outcome.debateSummary && (
            <div className="space-y-2">
              <h4 className="text-sm font-medium flex items-center gap-2">
                <Lightbulb className="h-4 w-4" />
                Summary
              </h4>
              <p className="text-sm text-muted-foreground pl-6">
                {outcome.debateSummary}
              </p>
            </div>
          )}

          {/* Trade Levels */}
          {(outcome.stopLoss || outcome.takeProfit) && (
            <div className="grid grid-cols-2 gap-4">
              {outcome.stopLoss && (
                <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/20">
                  <p className="text-xs text-red-500 font-medium">Stop Loss</p>
                  <p className="text-lg font-semibold">${outcome.stopLoss.toFixed(2)}</p>
                </div>
              )}
              {outcome.takeProfit && (
                <div className="p-3 rounded-lg bg-green-500/10 border border-green-500/20">
                  <p className="text-xs text-green-500 font-medium">Take Profit</p>
                  <p className="text-lg font-semibold">${outcome.takeProfit.toFixed(2)}</p>
                </div>
              )}
            </div>
          )}

          {/* Debate Duration */}
          {outcome.debateDurationSeconds && (
            <p className="text-xs text-muted-foreground text-center">
              Debate completed in {outcome.debateDurationSeconds.toFixed(1)}s
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export function DebatePanel({ ticker }: DebatePanelProps) {
  const { mutate: runDebate, data: debateResult, isPending, isError, error } = useDebate(ticker);
  const { data: weightsData } = useAgentWeights();
  const { data: memoryStats } = useMemoryStats();

  return (
    <TooltipProvider>
      <Card className="card-hover">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Scale className="h-5 w-5 text-primary" />
              Agent Debate
              {ticker && (
                <Badge variant="outline" className="text-[10px] font-bold">
                  {ticker}
                </Badge>
              )}
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={() => runDebate()}
              disabled={isPending || !ticker}
            >
              {isPending ? (
                <>
                  <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                  Debating...
                </>
              ) : (
                <>
                  <RefreshCw className="h-4 w-4 mr-2" />
                  Run Debate
                </>
              )}
            </Button>
          </CardTitle>
          <CardDescription>
            Multi-agent debate for consensus decision
          </CardDescription>
        </CardHeader>

        <CardContent className="space-y-4">
          {/* Memory Stats */}
          {memoryStats && memoryStats.totalTrades > 0 && (
            <div className="flex items-center justify-between p-2 rounded-lg bg-secondary/30 text-sm">
              <span className="text-muted-foreground">Historical trades:</span>
              <span className="font-medium">
                {memoryStats.completedTrades} trades | {(memoryStats.winRate * 100).toFixed(0)}% win rate
              </span>
            </div>
          )}

          {/* Loading State */}
          {isPending && (
            <div className="space-y-4 animate-pulse">
              <div className="h-24 bg-secondary rounded-lg" />
              <div className="space-y-2">
                {[1, 2, 3, 4, 5].map((i) => (
                  <div key={i} className="h-10 bg-secondary/50 rounded-lg" />
                ))}
              </div>
            </div>
          )}

          {/* Error State */}
          {isError && (
            <div className="p-4 rounded-lg bg-destructive/10 border border-destructive/30">
              <div className="flex items-start gap-2">
                <AlertTriangle className="h-5 w-5 text-destructive mt-0.5" />
                <div>
                  <p className="font-medium text-destructive">Debate Failed</p>
                  <p className="text-sm text-muted-foreground">
                    {error instanceof Error ? error.message : "Failed to run debate analysis"}
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Debate Result */}
          {debateResult?.outcome && !isPending && (
            <OutcomeDisplay outcome={debateResult.outcome} />
          )}

          {/* Empty State */}
          {!debateResult && !isPending && !isError && (
            <div className="text-center py-8 space-y-3">
              <Scale className="h-12 w-12 mx-auto text-muted-foreground/30" />
              <div>
                <p className="text-sm text-muted-foreground">
                  Click &ldquo;Run Debate&rdquo; to start multi-agent analysis
                </p>
                <p className="text-xs text-muted-foreground/60 mt-1">
                  7 specialized agents will debate and vote on the best action
                </p>
              </div>
            </div>
          )}

          {/* Agent Weights Summary */}
          {weightsData?.weights && Object.keys(weightsData.weights).length > 0 && !isPending && (
            <div className="pt-4 border-t border-border">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-medium text-muted-foreground">Current Agent Weights</span>
                <Tooltip>
                  <TooltipTrigger>
                    <span className="text-xs text-muted-foreground cursor-help">
                      Performance-adjusted
                    </span>
                  </TooltipTrigger>
                  <TooltipContent>
                    <p className="text-xs">Weights are adjusted based on historical accuracy</p>
                  </TooltipContent>
                </Tooltip>
              </div>
              <div className="flex flex-wrap gap-1">
                {Object.entries(weightsData.weights).map(([agent, weight]) => (
                  <Badge key={agent} variant="secondary" className="text-xs">
                    {AGENT_LABELS[agent] || agent}: {((weight as number) * 100).toFixed(0)}%
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </TooltipProvider>
  );
}
