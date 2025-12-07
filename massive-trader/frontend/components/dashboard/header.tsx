"use client";

import { useState } from "react";
import {
  Activity,
  Circle,
  RefreshCw,
  Settings,
  XOctagon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { useSystemStatus, usePanicClose } from "@/hooks/use-trading-data";
import { cn } from "@/lib/utils";
import { TickerSelector } from "./ticker-selector";

interface HeaderProps {
  selectedTicker: string;
  onTickerChange: (ticker: string) => void;
  autoRefresh: boolean;
  onAutoRefreshChange: (value: boolean) => void;
  autoTrade: boolean;
  onAutoTradeChange: (value: boolean) => void;
  onAnalyze: () => void;
  isAnalyzing: boolean;
  watchlist: string[];
  activeSignal?: {
    ticker: string;
    action: string;
    confidence: number;
  };
}

export function Header({
  selectedTicker,
  onTickerChange,
  autoRefresh,
  onAutoRefreshChange,
  autoTrade,
  onAutoTradeChange,
  onAnalyze,
  isAnalyzing,
  watchlist,
  activeSignal,
}: HeaderProps) {
  const { data: status } = useSystemStatus();
  const panicMutation = usePanicClose();
  const [panicDialogOpen, setPanicDialogOpen] = useState(false);

  const isLive = status?.tradingMode === "live";

  const handlePanicClose = async () => {
    try {
      await panicMutation.mutateAsync();
      setPanicDialogOpen(false);
    } catch (error) {
      console.error("Panic close failed:", error);
    }
  };

  return (
    <header className="sticky top-0 z-50 w-full border-b border-border/40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container flex h-16 items-center justify-between px-4">
        {/* Logo & Title */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Activity className="h-6 w-6 text-primary" />
            <h1 className="text-xl font-bold">Signalist AI Trader</h1>
          </div>

          {/* Environment Badge */}
          <Badge
            variant={isLive ? "destructive" : "secondary"}
            className={cn(
              "uppercase font-bold",
              isLive && "animate-pulse bg-red-600"
            )}
          >
            {isLive ? (
              <>
                <AlertTriangle className="h-3 w-3 mr-1" />
                LIVE
              </>
            ) : (
              "PAPER"
            )}
          </Badge>

          {/* Connection Status */}
          <div className="flex items-center gap-2">
            <Tooltip>
              <TooltipTrigger>
                <div className="flex items-center gap-1">
                  <Circle
                    className={cn(
                      "h-2 w-2 fill-current",
                      status?.backendConnected
                        ? "text-green-500"
                        : "text-red-500"
                    )}
                  />
                  <span className="text-xs text-muted-foreground">Backend</span>
                </div>
              </TooltipTrigger>
              <TooltipContent>
                {status?.backendConnected ? "Connected" : "Disconnected"}
              </TooltipContent>
            </Tooltip>
          </div>
        </div>

        {/* Ticker Search */}
        <div className="flex items-center gap-3 flex-1 max-w-xl mx-8">
          <TickerSelector
            selectedTicker={selectedTicker}
            onTickerChange={onTickerChange}
            watchlist={watchlist}
            activeSignal={activeSignal}
            className="flex-1"
          />

          <Button onClick={onAnalyze} disabled={isAnalyzing} className="gap-2 shrink-0">
            {isAnalyzing ? (
              <>
                <RefreshCw className="h-4 w-4 animate-spin" />
                Analyzing...
              </>
            ) : (
              <>
                <Activity className="h-4 w-4" />
                Run Analysis
              </>
            )}
          </Button>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-3">
          {/* Auto-Refresh Toggle */}
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="flex items-center gap-1.5">
                <label
                  htmlFor="auto-refresh"
                  className="text-xs text-muted-foreground cursor-pointer"
                >
                  Refresh
                </label>
                <Switch
                  id="auto-refresh"
                  checked={autoRefresh}
                  onCheckedChange={onAutoRefreshChange}
                  className="scale-75"
                />
              </div>
            </TooltipTrigger>
            <TooltipContent>Auto-refresh data every 30s</TooltipContent>
          </Tooltip>

          {/* Auto-Trade Toggle */}
          <Tooltip>
            <TooltipTrigger asChild>
              <div className="flex items-center gap-1.5">
                <label
                  htmlFor="auto-trade"
                  className="text-xs text-muted-foreground cursor-pointer"
                >
                  Auto
                </label>
                <Switch
                  id="auto-trade"
                  checked={autoTrade}
                  onCheckedChange={onAutoTradeChange}
                  className={cn(
                    "scale-75",
                    autoTrade && "data-[state=checked]:bg-yellow-600"
                  )}
                />
              </div>
            </TooltipTrigger>
            <TooltipContent>
              {autoTrade
                ? "Auto-trade ON - trades execute automatically"
                : "Auto-trade OFF"}
            </TooltipContent>
          </Tooltip>

          <div className="h-4 w-px bg-border" />

          {/* Emergency Stop - Close all positions & cancel orders */}
          <AlertDialog open={panicDialogOpen} onOpenChange={setPanicDialogOpen}>
            <Tooltip>
              <TooltipTrigger asChild>
                <AlertDialogTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 text-red-600 hover:text-red-700 hover:bg-red-600/10"
                  >
                    <XOctagon className="h-4 w-4" />
                  </Button>
                </AlertDialogTrigger>
              </TooltipTrigger>
              <TooltipContent>Emergency stop</TooltipContent>
            </Tooltip>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle className="flex items-center gap-2 text-red-600">
                  <XOctagon className="h-5 w-5" />
                  EMERGENCY STOP
                </AlertDialogTitle>
                <AlertDialogDescription asChild>
                  <div className="space-y-2 text-sm text-muted-foreground">
                    <span>This will immediately:</span>
                    <ul className="list-disc list-inside space-y-1">
                      <li>Close ALL open positions at market price</li>
                      <li>Cancel ALL pending orders</li>
                    </ul>
                    <span className="block font-semibold text-red-500">
                      This action cannot be undone.
                    </span>
                  </div>
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Back</AlertDialogCancel>
                <AlertDialogAction
                  onClick={handlePanicClose}
                  disabled={panicMutation.isPending}
                  className="bg-red-600 hover:bg-red-700"
                >
                  {panicMutation.isPending ? "Stopping..." : "STOP EVERYTHING"}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>

          <Button variant="ghost" size="icon">
            <Settings className="h-5 w-5" />
          </Button>
        </div>
      </div>
    </header>
  );
}
