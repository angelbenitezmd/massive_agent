"use client";

import { useState } from "react";
import {
  Activity,
  AlertTriangle,
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
import { useSystemStatus, usePanicClose, useAutoTradeStatus, useEnableAutoTrade, useDisableAutoTrade } from "@/hooks/use-trading-data";
import { cn } from "@/lib/utils";
import { TickerSelector } from "./ticker-selector";
import { LayoutEditor, type LayoutItem } from "./layout-editor";
import { useDashboardLayout } from "@/hooks/use-dashboard-layout";

interface HeaderProps {
  selectedTicker: string;
  onTickerChange: (ticker: string) => void;
  autoRefresh: boolean;
  onAutoRefreshChange: (value: boolean) => void;
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
  onAnalyze,
  isAnalyzing,
  watchlist,
  activeSignal,
}: HeaderProps) {
  const { data: status } = useSystemStatus();
  const { data: autoTradeStatus } = useAutoTradeStatus();
  const enableAutoTrade = useEnableAutoTrade();
  const disableAutoTrade = useDisableAutoTrade();
  const panicMutation = usePanicClose();
  const [panicDialogOpen, setPanicDialogOpen] = useState(false);
  const { layout, saveLayout } = useDashboardLayout();

  const isLive = status?.tradingMode === "live";
  const autoTrade = autoTradeStatus?.enabled ?? false;

  const handleAutoTradeChange = (checked: boolean) => {
    if (checked) {
      enableAutoTrade.mutate(60); // 60 second interval
    } else {
      disableAutoTrade.mutate();
    }
  };

  const handlePanicClose = async () => {
    try {
      const result = await panicMutation.mutateAsync();
      // Check if market was closed
      if (result.positions?.status === "market_closed") {
        alert(`⚠️ Market is CLOSED!\n\n${result.positions.message}\n\nPositions will remain open until market opens.`);
      } else if (result.positions?.status === "all_closed") {
        setPanicDialogOpen(false);
      } else {
        setPanicDialogOpen(false);
      }
    } catch (error) {
      console.error("Panic close failed:", error);
      alert("Failed to close positions. Check console for details.");
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

          {/* Auto-Trade Toggle (Backend-controlled 24/7) */}
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
                  onCheckedChange={handleAutoTradeChange}
                  disabled={enableAutoTrade.isPending || disableAutoTrade.isPending}
                  className={cn(
                    "scale-75",
                    autoTrade && "data-[state=checked]:bg-yellow-600"
                  )}
                />
              </div>
            </TooltipTrigger>
            <TooltipContent>
              {autoTrade
                ? "Auto-trade ON (24/7) - server executes trades automatically"
                : "Auto-trade OFF - enable for 24/7 automated trading"}
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

          {/* Layout Editor */}
          <LayoutEditor
            items={layout}
            onLayoutChange={saveLayout}
            availableComponents={[
              { id: "market-status", name: "Market Status", description: "Market open/close status" },
              { id: "todays-summary", name: "Today's Summary", description: "Daily trading summary" },
              { id: "trade-signals", name: "AI Trade Decisions", description: "AI-generated trade signals" },
              { id: "news-feed-global", name: "Global News Feed", description: "Market-wide news" },
              { id: "news-feed-ticker", name: "Ticker News Feed", description: "Ticker-specific news" },
              { id: "scanner", name: "Scanner Panel", description: "Stock scanner" },
              { id: "ai-agents", name: "AI Agents Panel", description: "AI agent analysis" },
              { id: "market-snapshot", name: "Market Snapshot", description: "Price chart and technicals" },
              { id: "deep-analysis", name: "Deep Analysis", description: "Deep AI analysis" },
              { id: "trade-decision", name: "Trade Decision", description: "Trade decision panel" },
              { id: "manual-trade", name: "Manual Trade", description: "Manual trade execution" },
              { id: "portfolio-heatmap", name: "Portfolio Heatmap", description: "Portfolio visualization" },
              { id: "portfolio-chart", name: "Portfolio Chart", description: "Portfolio performance chart" },
              { id: "trade-journal", name: "Trade Journal", description: "Trade history" },
              { id: "analyst-ratings", name: "Analyst Ratings", description: "Analyst rating changes" },
              { id: "activity-log", name: "Activity Log", description: "System activity log" },
              { id: "earnings", name: "Earnings Panel", description: "Earnings calendar" },
              { id: "performance", name: "Performance Stats", description: "Performance metrics" },
              { id: "market-movers", name: "Market Movers", description: "Top movers" },
              { id: "risk-panel", name: "Risk Panel", description: "Risk management" },
            ]}
          />

          <Button variant="ghost" size="icon">
            <Settings className="h-5 w-5" />
          </Button>
        </div>
      </div>
    </header>
  );
}
