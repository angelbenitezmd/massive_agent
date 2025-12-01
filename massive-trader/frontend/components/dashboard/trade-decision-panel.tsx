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
    if (decision.confidence < 0.6) return "Confidence too low (<60%)";
    return null;
  };

  const handleConfirmTrade = () => {
    setConfirmDialogOpen(false);
    onExecuteTrade();
  };

  return (
    <Card className="card-hover border-primary/20">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2">
          <Target className="h-5 w-5 text-primary" />
          Trade Decision
        </CardTitle>
        <CardDescription>AI consensus recommendation</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {decision ? (
          <>
            {/* Action & Confidence */}
            <div className="flex items-center justify-between">
              {getActionBadge(decision.action)}
              <div className="text-right">
                <div className="text-sm text-muted-foreground">Confidence</div>
                <div className="text-2xl font-bold">
                  {Math.round(decision.confidence * 100)}%
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
          <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
            <Target className="h-12 w-12 mb-4 opacity-50" />
            <p>Run analysis to get trade recommendation</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
