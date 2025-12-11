"use client";

import { useState, useEffect } from "react";
import {
  ShoppingCart,
  TrendingUp,
  TrendingDown,
  DollarSign,
  Shield,
  Target,
  AlertTriangle,
  Loader2,
  Calculator,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn, formatCurrency } from "@/lib/utils";

interface ManualTradePanelProps {
  ticker: string;
  currentPrice: number;
  buyingPower: number;
  onTrade: (trade: ManualTradeRequest) => Promise<any>;
  isExecuting: boolean;
  tradingMode: "paper" | "live";
}

export interface ManualTradeRequest {
  ticker: string;
  side: "buy" | "sell";
  quantity: number;
  order_type: "market" | "limit" | "stop" | "bracket";
  limit_price?: number;
  stop_loss?: number;
  take_profit?: number;
  time_in_force: "day" | "gtc";
}

export function ManualTradePanel({
  ticker,
  currentPrice,
  buyingPower,
  onTrade,
  isExecuting,
  tradingMode,
}: ManualTradePanelProps) {
  // Trade parameters
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [quantity, setQuantity] = useState<string>("10");
  const [orderType, setOrderType] = useState<"market" | "limit" | "bracket">("market");
  const [limitPrice, setLimitPrice] = useState<string>("");
  const [stopLoss, setStopLoss] = useState<string>("");
  const [takeProfit, setTakeProfit] = useState<string>("");
  const [timeInForce, setTimeInForce] = useState<"day" | "gtc">("day");

  // Risk calculation
  const [riskPercent, setRiskPercent] = useState<string>("1");
  const [useRiskCalc, setUseRiskCalc] = useState(false);

  // Confirmation dialog
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [tradeResult, setTradeResult] = useState<any>(null);

  // Update limit price when ticker changes
  useEffect(() => {
    if (currentPrice > 0) {
      setLimitPrice(currentPrice.toFixed(2));
      // Set default stop loss at 2% below and take profit at 4% above
      setStopLoss((currentPrice * 0.98).toFixed(2));
      setTakeProfit((currentPrice * 1.04).toFixed(2));
    }
  }, [currentPrice, ticker]);

  // Calculate position size based on risk
  useEffect(() => {
    if (useRiskCalc && stopLoss && currentPrice > 0) {
      const riskAmount = buyingPower * (parseFloat(riskPercent) / 100);
      const stopLossPrice = parseFloat(stopLoss);
      const riskPerShare = Math.abs(currentPrice - stopLossPrice);
      if (riskPerShare > 0) {
        const calculatedQty = Math.floor(riskAmount / riskPerShare);
        setQuantity(Math.max(1, calculatedQty).toString());
      }
    }
  }, [useRiskCalc, riskPercent, stopLoss, currentPrice, buyingPower]);

  const qty = parseFloat(quantity) || 0;
  const price = orderType === "limit" ? parseFloat(limitPrice) || currentPrice : currentPrice;
  const estimatedCost = qty * price;
  const stopLossPrice = parseFloat(stopLoss) || 0;
  const takeProfitPrice = parseFloat(takeProfit) || 0;

  // Calculate risk/reward
  const riskPerShare = side === "buy"
    ? price - stopLossPrice
    : stopLossPrice - price;
  const rewardPerShare = side === "buy"
    ? takeProfitPrice - price
    : price - takeProfitPrice;
  const riskRewardRatio = riskPerShare > 0 ? (rewardPerShare / riskPerShare).toFixed(2) : "N/A";
  const totalRisk = qty * riskPerShare;
  const totalReward = qty * rewardPerShare;

  const canTrade = () => {
    if (qty <= 0) return false;
    if (side === "buy" && estimatedCost > buyingPower) return false;
    if (orderType === "limit" && (!limitPrice || parseFloat(limitPrice) <= 0)) return false;
    if (orderType === "bracket" && (!stopLoss || !takeProfit)) return false;
    return true;
  };

  const handleSubmit = async () => {
    const trade: ManualTradeRequest = {
      ticker,
      side,
      quantity: qty,
      order_type: orderType,
      time_in_force: timeInForce,
    };

    if (orderType === "limit") {
      trade.limit_price = parseFloat(limitPrice);
    }

    if (orderType === "bracket" || stopLoss) {
      trade.stop_loss = parseFloat(stopLoss);
    }

    if (orderType === "bracket" || takeProfit) {
      trade.take_profit = parseFloat(takeProfit);
    }

    try {
      const result = await onTrade(trade);
      setTradeResult(result);
      if (result?.status === "executed") {
        setConfirmOpen(false);
      }
    } catch (error: any) {
      setTradeResult({ status: "error", message: error.message });
    }
  };

  return (
    <Card className="card-hover border-primary/20">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2">
          <ShoppingCart className="h-5 w-5 text-primary" />
          Manual Trade
          <Badge variant="outline" className="text-[10px] font-bold">
            {ticker}
          </Badge>
        </CardTitle>
        <CardDescription>
          Override AI - trade with full control
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Buy/Sell Toggle */}
        <div className="grid grid-cols-2 gap-2">
          <Button
            variant={side === "buy" ? "default" : "outline"}
            className={cn(
              "w-full",
              side === "buy" && "bg-green-600 hover:bg-green-700"
            )}
            onClick={() => setSide("buy")}
          >
            <TrendingUp className="h-4 w-4 mr-2" />
            BUY
          </Button>
          <Button
            variant={side === "sell" ? "default" : "outline"}
            className={cn(
              "w-full",
              side === "sell" && "bg-red-600 hover:bg-red-700"
            )}
            onClick={() => setSide("sell")}
          >
            <TrendingDown className="h-4 w-4 mr-2" />
            SELL
          </Button>
        </div>

        {/* Order Type */}
        <div className="space-y-2">
          <label className="text-sm text-muted-foreground">Order Type</label>
          <div className="grid grid-cols-3 gap-2">
            {(["market", "limit", "bracket"] as const).map((type) => (
              <Button
                key={type}
                variant={orderType === type ? "default" : "outline"}
                size="sm"
                onClick={() => setOrderType(type)}
                className="capitalize"
              >
                {type}
              </Button>
            ))}
          </div>
        </div>

        {/* Quantity */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-sm text-muted-foreground">Shares</label>
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">Risk Calc</span>
              <Switch
                checked={useRiskCalc}
                onCheckedChange={setUseRiskCalc}
              />
            </div>
          </div>
          <div className="flex gap-2">
            <Input
              type="number"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              min="1"
              className="flex-1"
            />
            <Button
              variant="outline"
              size="sm"
              onClick={() => setQuantity("10")}
            >
              10
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setQuantity("50")}
            >
              50
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setQuantity("100")}
            >
              100
            </Button>
          </div>
        </div>

        {/* Risk Calculator */}
        {useRiskCalc && (
          <div className="bg-muted/30 rounded-lg p-3 space-y-2">
            <div className="flex items-center gap-2 text-xs">
              <Calculator className="h-3.5 w-3.5" />
              <span className="text-muted-foreground">Risk-Based Position Sizing</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm">Risk</span>
              <Input
                type="number"
                value={riskPercent}
                onChange={(e) => setRiskPercent(e.target.value)}
                className="w-20 h-8"
                min="0.1"
                max="5"
                step="0.1"
              />
              <span className="text-sm">% of portfolio</span>
            </div>
            <p className="text-xs text-muted-foreground">
              Max risk: {formatCurrency(buyingPower * (parseFloat(riskPercent) / 100))}
            </p>
          </div>
        )}

        {/* Limit Price (for limit orders) */}
        {orderType === "limit" && (
          <div className="space-y-2">
            <label className="text-sm text-muted-foreground flex items-center gap-2">
              <DollarSign className="h-3.5 w-3.5" />
              Limit Price
            </label>
            <Input
              type="number"
              value={limitPrice}
              onChange={(e) => setLimitPrice(e.target.value)}
              step="0.01"
              placeholder={currentPrice.toFixed(2)}
            />
          </div>
        )}

        {/* Stop Loss & Take Profit (for bracket or optional) */}
        {(orderType === "bracket" || orderType === "market") && (
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <label className="text-sm text-muted-foreground flex items-center gap-2">
                <Shield className="h-3.5 w-3.5 text-red-500" />
                Stop Loss
              </label>
              <Input
                type="number"
                value={stopLoss}
                onChange={(e) => setStopLoss(e.target.value)}
                step="0.01"
                className="border-red-500/30"
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm text-muted-foreground flex items-center gap-2">
                <Target className="h-3.5 w-3.5 text-green-500" />
                Take Profit
              </label>
              <Input
                type="number"
                value={takeProfit}
                onChange={(e) => setTakeProfit(e.target.value)}
                step="0.01"
                className="border-green-500/30"
              />
            </div>
          </div>
        )}

        {/* Time in Force */}
        <div className="space-y-2">
          <label className="text-sm text-muted-foreground">Time in Force</label>
          <div className="grid grid-cols-2 gap-2">
            <Button
              variant={timeInForce === "day" ? "default" : "outline"}
              size="sm"
              onClick={() => setTimeInForce("day")}
            >
              Day
            </Button>
            <Button
              variant={timeInForce === "gtc" ? "default" : "outline"}
              size="sm"
              onClick={() => setTimeInForce("gtc")}
            >
              GTC
            </Button>
          </div>
        </div>

        <Separator />

        {/* Order Summary */}
        <div className="bg-muted/30 rounded-lg p-3 space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Current Price</span>
            <span className="font-medium">{formatCurrency(currentPrice)}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Estimated Cost</span>
            <span className={cn(
              "font-medium",
              estimatedCost > buyingPower && "text-red-500"
            )}>
              {formatCurrency(estimatedCost)}
            </span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">Buying Power</span>
            <span className="font-medium">{formatCurrency(buyingPower)}</span>
          </div>
          {stopLossPrice > 0 && takeProfitPrice > 0 && (
            <>
              <Separator className="my-2" />
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Risk</span>
                <span className="font-medium text-red-500">
                  {formatCurrency(Math.abs(totalRisk))}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Reward</span>
                <span className="font-medium text-green-500">
                  {formatCurrency(totalReward)}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">R:R Ratio</span>
                <span className="font-bold">1:{riskRewardRatio}</span>
              </div>
            </>
          )}
        </div>

        {/* Submit Button */}
        <Button
          className={cn(
            "w-full",
            side === "buy" ? "bg-green-600 hover:bg-green-700" : "bg-red-600 hover:bg-red-700"
          )}
          size="lg"
          disabled={!canTrade() || isExecuting}
          onClick={() => setConfirmOpen(true)}
        >
          {isExecuting ? (
            <>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              Executing...
            </>
          ) : (
            <>
              {side === "buy" ? <TrendingUp className="h-4 w-4 mr-2" /> : <TrendingDown className="h-4 w-4 mr-2" />}
              {side.toUpperCase()} {qty} {ticker}
            </>
          )}
        </Button>

        {estimatedCost > buyingPower && (
          <p className="text-xs text-red-500 text-center">
            Insufficient buying power
          </p>
        )}

        {/* Confirmation Dialog */}
        <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                {tradingMode === "live" && (
                  <AlertTriangle className="h-5 w-5 text-red-500" />
                )}
                Confirm {side.toUpperCase()} Order
              </DialogTitle>
              <DialogDescription>
                {tradingMode === "live" ? (
                  <span className="text-red-500 font-medium">
                    WARNING: This is a LIVE trade with real money!
                  </span>
                ) : (
                  "You are about to place a paper trade."
                )}
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-3 py-4">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <span className="text-muted-foreground">Symbol:</span>{" "}
                  <span className="font-bold">{ticker}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">Side:</span>{" "}
                  <span className={cn(
                    "font-bold",
                    side === "buy" ? "text-green-500" : "text-red-500"
                  )}>
                    {side.toUpperCase()}
                  </span>
                </div>
                <div>
                  <span className="text-muted-foreground">Quantity:</span>{" "}
                  <span className="font-bold">{qty}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">Type:</span>{" "}
                  <span className="font-bold capitalize">{orderType}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">Est. Cost:</span>{" "}
                  <span className="font-bold">{formatCurrency(estimatedCost)}</span>
                </div>
                {stopLossPrice > 0 && (
                  <div>
                    <span className="text-muted-foreground">Stop Loss:</span>{" "}
                    <span className="font-bold text-red-500">{formatCurrency(stopLossPrice)}</span>
                  </div>
                )}
              </div>

              {tradeResult && (
                <div className={cn(
                  "p-3 rounded-lg text-sm",
                  tradeResult.status === "executed" ? "bg-green-500/10 text-green-500" :
                  tradeResult.status === "error" ? "bg-red-500/10 text-red-500" :
                  "bg-yellow-500/10 text-yellow-500"
                )}>
                  {tradeResult.message}
                </div>
              )}
            </div>

            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => {
                  setConfirmOpen(false);
                  setTradeResult(null);
                }}
              >
                Cancel
              </Button>
              <Button
                variant={tradingMode === "live" ? "destructive" : "default"}
                onClick={handleSubmit}
                disabled={isExecuting}
                className={side === "buy" ? "bg-green-600 hover:bg-green-700" : ""}
              >
                {isExecuting ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Executing...
                  </>
                ) : (
                  `Confirm ${side.toUpperCase()}`
                )}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </CardContent>
    </Card>
  );
}
