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
  XCircle,
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

  // Execute button uses the master AI verdict (score-based), but still respects
  // the execution gate as a safety filter — the AI says BUY, but if any gate
  // check fails we won't let the user execute without acknowledging it.
  const canTrade = () => {
    if (!decision || !riskStatus) return false;
    if (riskStatus.circuitBreaker === "RED") return false;
    if (riskStatus.circuitBreaker === "ORANGE") return false;
    if (masterAction !== "BUY") return false;
    if (decision.buyGate && decision.buyGate.passed === false) return false;
    return true;
  };

  const getDisabledReason = () => {
    if (!decision) return "No analysis available";
    if (!riskStatus) return "Risk status unavailable";
    if (riskStatus.circuitBreaker === "RED") return "Circuit breaker: RED";
    if (riskStatus.circuitBreaker === "ORANGE")
      return "Circuit breaker: ORANGE - No new positions";
    if (masterAction !== "BUY") return `AI score ${masterScore} below BUY threshold`;
    if (decision.buyGate && decision.buyGate.passed === false) {
      const r = (decision.buyGate.reasons || [])[0] || "gate_failed";
      return `Gate blocking: ${r}`;
    }
    return null;
  };

  const handleConfirmTrade = () => {
    setConfirmDialogOpen(false);
    onExecuteTrade();
  };

  // Master verdict = the backend's action. BUY only when the trade will
  // actually execute (gate passes + score qualifies). Anything else = HOLD.
  // Score is shown alongside for context but does NOT override the action.
  const masterScore = decision?.combinedScore ?? (decision ? Math.round(decision.confidence * 100) : 0);
  const rawAction = decision?.action;
  const masterAction: TradeAction =
    rawAction === "BUY" ? "BUY" : rawAction === "SELL" ? "SELL" : "HOLD";

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
            {/* === MASTER AI TRADE DECISION === */}
            {/* This is the ultimate verdict, derived from the combined AI score.
                Score >= 70 = BUY, 50-69 = HOLD, < 50 = NO BUY. */}
            <div className="rounded-lg border-2 border-primary/30 bg-primary/5 p-4 space-y-3">
              <div className="flex items-center justify-between">
                {getActionBadge(masterAction)}
                <div className="text-right">
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
                    AI Trade Score
                  </div>
                  <div className="text-3xl font-bold leading-none">
                    {masterScore}
                    <span className="text-base text-muted-foreground font-normal">/100</span>
                  </div>
                </div>
              </div>
              <Progress
                value={masterScore}
                className={cn(
                  "h-2",
                  masterAction === "BUY" && "[&>div]:bg-green-500",
                  masterAction === "HOLD" && "[&>div]:bg-yellow-500",
                  masterAction === "SELL" && "[&>div]:bg-red-500"
                )}
              />
              <div className="flex justify-between text-[10px] text-muted-foreground">
                <span>SELL 0–29</span>
                <span>HOLD 30–69</span>
                <span>BUY 70–100</span>
              </div>
            </div>

            {/* === INDEPENDENT COMPONENT SCORES === */}
            {/* Each score is independent; the master AI score above is derived
                from these but the AI's final verdict is the master control. */}
            <div className="space-y-2">
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
                Component Scores
              </div>
              <div className="grid grid-cols-2 gap-2">
                <ComponentScore
                  icon={<Brain className="h-3.5 w-3.5 text-purple-500" />}
                  label="Sentiment"
                  value={decision.sentimentScore}
                  tooltip="Raw news sentiment from headlines and analyst ratings"
                />
                <ComponentScore
                  icon={<Brain className="h-3.5 w-3.5 text-pink-500" />}
                  label="AI (LLM)"
                  value={decision.aiScore}
                  tooltip="LLM-enhanced news intelligence — reads actual article bodies"
                />
                <ComponentScore
                  icon={<Activity className="h-3.5 w-3.5 text-blue-500" />}
                  label="Momentum"
                  value={decision.momentumScore}
                  tooltip="Price and volume momentum"
                />
                <ComponentScore
                  icon={<Activity className="h-3.5 w-3.5 text-cyan-500" />}
                  label="Technical"
                  value={decision.technicalScore}
                  tooltip="RSI, MACD, regime, and trend composite"
                />
              </div>
              {decision.strategy && (
                <div className="text-[10px] text-muted-foreground text-center pt-1">
                  Strategy: {decision.strategy}
                </div>
              )}
            </div>

            {decision.buyGate && (
              <BuyGateChecklist gate={decision.buyGate} />
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

function ComponentScore({
  icon,
  label,
  value,
  tooltip,
}: {
  icon: React.ReactNode;
  label: string;
  value: number | undefined;
  tooltip: string;
}) {
  const hasValue = typeof value === "number";
  const v = hasValue ? Math.round(value!) : null;
  const color =
    v === null
      ? "text-muted-foreground"
      : v >= 75
      ? "text-green-500"
      : v >= 50
      ? "text-yellow-500"
      : "text-red-500";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div className="flex items-center justify-between bg-muted/30 rounded-md px-2 py-1.5">
          <div className="flex items-center gap-1.5 min-w-0">
            {icon}
            <span className="text-xs text-muted-foreground truncate">
              {label}
            </span>
          </div>
          <span className={cn("text-sm font-semibold", color)}>
            {v === null ? "—" : v}
          </span>
        </div>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="max-w-[220px] p-2 text-xs">
        {tooltip}
      </TooltipContent>
    </Tooltip>
  );
}

type BuyGate = NonNullable<TradeDecision["buyGate"]>;

function BuyGateChecklist({ gate }: { gate: BuyGate }) {
  // Collapse the 15 raw flags into 6 user-facing checks. A group passes only
  // if every underlying flag is true (or undefined — treated as not blocking).
  const ok = (v?: boolean) => v !== false;
  const checks: Array<{ label: string; passed: boolean; tooltip: string }> = [
    {
      label: "Sentiment",
      passed: ok(gate.score_ok) && ok(gate.ai_ok) && ok(gate.llm_ok),
      tooltip: "Combined score, AI score, and LLM confirmation all clear",
    },
    {
      label: "Momentum",
      passed: ok(gate.momentum_ok),
      tooltip: "Momentum score above threshold",
    },
    {
      label: "Timing",
      passed:
        ok(gate.timing_ok) &&
        ok(gate.vwap_extension_ok) &&
        ok(gate.session_position_ok),
      tooltip: "Fresh entry, not extended above VWAP, not near session high",
    },
    {
      label: "Technical",
      passed: ok(gate.technical_ok) && ok(gate.regime_ok) && ok(gate.rsi_ok),
      tooltip: "Technical score, regime not bearish, RSI not overbought",
    },
    {
      label: "Volume",
      passed: ok(gate.volume_ok),
      tooltip: "Relative volume above minimum",
    },
    {
      label: "R:R",
      passed: ok(gate.risk_reward_ok) && ok(gate.resistance_ok),
      tooltip: "Risk/reward ratio and resistance headroom both acceptable",
    },
  ];

  const passedCount = checks.filter((c) => c.passed).length;

  return (
    <div className="bg-muted/30 rounded-lg p-3 space-y-2">
      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-1.5">
          <span className="text-muted-foreground font-medium">
            Execution Filter
          </span>
          <Tooltip>
            <TooltipTrigger asChild>
              <Info className="h-3 w-3 text-muted-foreground hover:text-foreground cursor-help" />
            </TooltipTrigger>
            <TooltipContent side="bottom" className="max-w-[260px] p-2 text-xs">
              Secondary safety filter applied AFTER the AI decision. The AI
              decision above is the master — these checks just determine if
              the order can be executed right now.
            </TooltipContent>
          </Tooltip>
        </div>
        <span
          className={cn(
            "font-medium",
            gate.passed
              ? "text-green-500"
              : passedCount >= 4
              ? "text-yellow-500"
              : "text-red-500"
          )}
        >
          {passedCount}/{checks.length} {gate.passed ? "PASS" : "BLOCKED"}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-1.5">
        {checks.map((c) => (
          <Tooltip key={c.label}>
            <TooltipTrigger asChild>
              <div className="flex items-center gap-1 text-[11px]">
                {c.passed ? (
                  <CheckCircle2 className="h-3.5 w-3.5 text-green-500 shrink-0" />
                ) : (
                  <XCircle className="h-3.5 w-3.5 text-red-500 shrink-0" />
                )}
                <span
                  className={cn(
                    "truncate",
                    c.passed ? "text-foreground" : "text-muted-foreground"
                  )}
                >
                  {c.label}
                </span>
              </div>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="max-w-[220px] p-2 text-xs">
              {c.tooltip}
            </TooltipContent>
          </Tooltip>
        ))}
      </div>
      {!gate.passed && gate.reasons && gate.reasons.length > 0 && (
        <div className="text-[10px] text-muted-foreground pt-1 border-t border-border">
          Blocked: {gate.reasons.slice(0, 3).join(", ")}
        </div>
      )}
    </div>
  );
}
