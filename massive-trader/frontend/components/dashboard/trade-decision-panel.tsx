"use client";

import { useState } from "react";
import {
  Target,
  ShieldCheck,
  AlertTriangle,
  TrendingUp,
  TrendingDown,
  Ban,
  CheckCircle2,
  Info,
  Brain,
  Activity,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { formatCurrency, formatPercent, cn } from "@/lib/utils";
import type { TradeDecision, RiskStatus, TradeAction } from "@/types";

interface TradeDecisionPanelProps {
  decision: TradeDecision | undefined;
  riskStatus: RiskStatus | undefined;
  onExecuteTrade: () => void;
  isExecuting: boolean;
  tradingMode: "paper" | "live";
}

export function TradeDecisionPanel({
  decision,
  riskStatus,
  onExecuteTrade,
  isExecuting,
  tradingMode,
}: TradeDecisionPanelProps) {
  const [confirmDialogOpen, setConfirmDialogOpen] = useState(false);

  const getActionBadge = (action: TradeAction) => {
    switch (action) {
      case "BUY":
        return (
          <Badge className="bg-green-600 text-white text-lg px-4 py-1">
            <TrendingUp className="h-4 w-4 mr-1" />
            BUY
          </Badge>
        );
      case "SELL":
        return (
          <Badge className="bg-red-600 text-white text-lg px-4 py-1">
            <TrendingDown className="h-4 w-4 mr-1" />
            SELL
          </Badge>
        );
      case "HOLD":
        return (
          <Badge className="bg-yellow-600 text-white text-lg px-4 py-1">
            <ShieldCheck className="h-4 w-4 mr-1" />
            HOLD
          </Badge>
        );
      default:
        return (
          <Badge className="bg-gray-600 text-white text-lg px-4 py-1">
            <Ban className="h-4 w-4 mr-1" />
            NO BUY
          </Badge>
        );
    }
  };

  const canTrade = () => {
    if (!decision || !riskStatus) return false;
    if (decision.action !== "BUY" && decision.action !== "SELL") return false;
    if (riskStatus.circuitBreaker === "RED") return false;
    if (riskStatus.circuitBreaker === "ORANGE") return false;
    if (decision.confidence < 0.6) return false;
    return true;
  };

  const getDisabledReason = () => {
    if (!decision) return "No analysis available";
    if (!riskStatus) return "Risk status unavailable";
    if (riskStatus.circuitBreaker === "RED") return "Circuit breaker: RED";
    if (riskStatus.circuitBreaker === "ORANGE")
      return "Circuit breaker: ORANGE - No new positions";
    if (decision.action !== "BUY" && decision.action !== "SELL")
      return "No actionable signal";
    if (decision.confidence < 0.6) return "Signal strength too low (<60)";
    return null;
  };

  const handleConfirmTrade = () => {
    setConfirmDialogOpen(false);
    onExecuteTrade();
  };

  return (
    <TooltipProvider>
      <Card className="card-hover border-primary/20">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2">
            <Target className="h-5 w-5 text-primary" />
            Trade Decision
            {decision?.ticker && (
              <Badge variant="outline" className="text-[10px] font-bold">
                {decision.ticker}
              </Badge>
            )}
            <Tooltip>
              <TooltipTrigger asChild>
                <Info className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground cursor-help" />
              </TooltipTrigger>
              <TooltipContent side="bottom" className="max-w-[280px] p-3">
                <div className="space-y-2 text-xs">
                  <p className="font-semibold">Trade Decision Explained</p>
                  <div className="space-y-1.5">
                    <p><strong>BUY:</strong> Strong bullish signals across agents. Consider entering a long position.</p>
                    <p><strong>SELL:</strong> Bearish signals detected. Consider exiting or shorting.</p>
                    <p><strong>HOLD:</strong> Mixed or neutral signals. Wait for clearer direction.</p>
                  </div>
                  <div className="pt-1 border-t border-border">
                    <p className="text-muted-foreground">Signal Strength is a sentiment score (0-100), not a probability. Higher scores indicate more bullish signals from news, earnings, and analyst ratings.</p>
                  </div>
                </div>
              </TooltipContent>
            </Tooltip>
          </CardTitle>
          <CardDescription>AI consensus recommendation</CardDescription>
        </CardHeader>
      <CardContent className="space-y-4">
        {decision ? (
          <>
            {/* Action & Signal Strength */}
            <div className="flex items-center justify-between">
              {getActionBadge(decision.action)}
              <div className="text-right">
                <div className="text-sm text-muted-foreground">Signal Strength</div>
                <div className="text-2xl font-bold">
                  {Math.round(decision.confidence * 100)}/100
                </div>
              </div>
            </div>

            <Progress
              value={decision.confidence * 100}
              className={cn(
                "h-2",
                decision.action === "BUY" && "[&>div]:bg-green-500",
                decision.action === "SELL" && "[&>div]:bg-red-500",
                decision.action === "HOLD" && "[&>div]:bg-yellow-500"
              )}
            />

            {/* Score Breakdown */}
            {(decision.aiScore !== undefined || decision.momentumScore !== undefined) && (
              <TooltipProvider>
                <div className="bg-muted/30 rounded-lg p-3 space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-1.5">
                      <Brain className="h-3.5 w-3.5 text-purple-500" />
                      <span className="text-muted-foreground">AI Score</span>
                    </div>
                    <span className={cn(
                      "font-medium",
                      (decision.aiScore || 0) >= 80 ? "text-green-500" :
                      (decision.aiScore || 0) >= 60 ? "text-yellow-500" : "text-red-500"
                    )}>
                      {decision.aiScore || 0}/100
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-1.5">
                      <Activity className="h-3.5 w-3.5 text-blue-500" />
                      <span className="text-muted-foreground">Momentum</span>
                    </div>
                    <span className={cn(
                      "font-medium",
                      (decision.momentumScore || 0) >= 70 ? "text-green-500" :
                      (decision.momentumScore || 0) >= 50 ? "text-yellow-500" : "text-red-500"
                    )}>
                      {decision.momentumScore || 0}/100
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-xs pt-1 border-t border-border">
                    <div className="flex items-center gap-1.5">
                      <span className="text-muted-foreground">Combined</span>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Info className="h-3 w-3 text-muted-foreground hover:text-foreground cursor-help" />
                        </TooltipTrigger>
                        <TooltipContent side="bottom" className="max-w-[260px] p-3">
                          <div className="space-y-2 text-xs">
                            <p className="font-semibold">How the score is calculated:</p>
                            <div className="space-y-1">
                              <p>When AI Score &ge; 80 (high conviction):</p>
                              <p className="text-muted-foreground pl-2">AI: 60% + Momentum: 40%</p>
                              <p className="pt-1">Otherwise:</p>
                              <p className="text-muted-foreground pl-2">AI: 50% + Momentum: 50%</p>
                            </div>
                            <div className="pt-1 border-t border-border">
                              <p><strong>BUY</strong> when score &ge; 70 or AI &ge; 80 with momentum &ge; 40</p>
                              <p><strong>HOLD</strong> when score &ge; 60 or AI &ge; 75</p>
                            </div>
                          </div>
                        </TooltipContent>
                      </Tooltip>
                    </div>
                    <span className="font-bold">{decision.combinedScore || Math.round(decision.confidence * 100)}/100</span>
                  </div>
                  {decision.strategy && (
                    <div className="text-[10px] text-muted-foreground text-center">
                      Strategy: {decision.strategy}
                    </div>
                  )}
                </div>
              </TooltipProvider>
            )}

            <Separator />

            {/* Trade Details */}
            {(decision.action === "BUY" || decision.action === "SELL") && (
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <div className="text-sm text-muted-foreground">Symbol</div>
                  <div className="text-lg font-bold">{decision.symbol}</div>
                </div>
                <div className="space-y-1">
                  <div className="text-sm text-muted-foreground">Quantity</div>
                  <div className="text-lg font-bold">
                    {decision.quantity} shares
                  </div>
                </div>
                <div className="space-y-1">
                  <div className="text-sm text-muted-foreground">Entry</div>
                  <div className="font-medium">
                    {formatCurrency(decision.entryPrice)}
                  </div>
                </div>
                <div className="space-y-1">
                  <div className="text-sm text-muted-foreground">Stop Loss</div>
                  <div className="font-medium text-red-500">
                    {formatCurrency(decision.stopLoss)}
                  </div>
                </div>
                <div className="space-y-1">
                  <div className="text-sm text-muted-foreground">
                    Take Profit
                  </div>
                  <div className="font-medium text-green-500">
                    {formatCurrency(decision.takeProfit)}
                  </div>
                </div>
                <div className="space-y-1">
                  <div className="text-sm text-muted-foreground">R:R Ratio</div>
                  <div className="font-medium">
                    1:
                    {(
                      (decision.takeProfit - decision.entryPrice) /
                      (decision.entryPrice - decision.stopLoss)
                    ).toFixed(1)}
                  </div>
                </div>
              </div>
            )}

            {/* Reasoning */}
            <div className="space-y-2">
              <div className="text-sm text-muted-foreground">Reasoning</div>
              <p className="text-sm">{decision.reasoning}</p>
            </div>

            {/* Contributing Agents */}
            <div className="flex flex-wrap gap-2">
              {decision.contributingAgents.map((agent) => (
                <Badge key={agent} variant="outline" className="text-xs">
                  {agent}
                </Badge>
              ))}
            </div>

            <Separator />

            {/* Execute Button */}
            <Dialog open={confirmDialogOpen} onOpenChange={setConfirmDialogOpen}>
              <DialogTrigger asChild>
                <Button
                  className="w-full"
                  variant={decision.action === "BUY" ? "success" : "destructive"}
                  disabled={!canTrade() || isExecuting}
                  size="lg"
                >
                  {isExecuting ? (
                    "Executing..."
                  ) : !canTrade() ? (
                    <>
                      <Ban className="h-4 w-4 mr-2" />
                      {getDisabledReason()}
                    </>
                  ) : (
                    <>
                      <CheckCircle2 className="h-4 w-4 mr-2" />
                      Execute Trade
                    </>
                  )}
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle className="flex items-center gap-2">
                    {tradingMode === "live" && (
                      <AlertTriangle className="h-5 w-5 text-red-500" />
                    )}
                    Confirm Trade Execution
                  </DialogTitle>
                  <DialogDescription>
                    {tradingMode === "live" ? (
                      <span className="text-red-500 font-medium">
                        WARNING: You are about to execute a LIVE trade with real
                        money!
                      </span>
                    ) : (
                      "You are about to execute a paper trade."
                    )}
                  </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 py-4">
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <span className="text-muted-foreground">Action:</span>{" "}
                      <span className="font-medium">{decision.action}</span>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Symbol:</span>{" "}
                      <span className="font-medium">{decision.symbol}</span>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Quantity:</span>{" "}
                      <span className="font-medium">{decision.quantity}</span>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Entry:</span>{" "}
                      <span className="font-medium">
                        {formatCurrency(decision.entryPrice)}
                      </span>
                    </div>
                  </div>
                </div>

                <DialogFooter>
                  <Button
                    variant="outline"
                    onClick={() => setConfirmDialogOpen(false)}
                  >
                    Cancel
                  </Button>
                  <Button
                    variant={tradingMode === "live" ? "destructive" : "default"}
                    onClick={handleConfirmTrade}
                  >
                    {tradingMode === "live" ? "Execute LIVE Trade" : "Execute Paper Trade"}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </>
        ) : (
          <div className="flex flex-col items-center justify-center py-4 text-muted-foreground">
            <Target className="h-8 w-8 mb-2 opacity-50" />
            <p className="text-xs">Run analysis to get trade recommendation</p>
          </div>
        )}
      </CardContent>
      </Card>
    </TooltipProvider>
  );
}
