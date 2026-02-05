"use client";

import { useState } from "react";
import {
  Activity,
  AlertTriangle,
  Circle,
  HelpCircle,
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
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
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
  const [helpDialogOpen, setHelpDialogOpen] = useState(false);
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

          {/* Help Guide */}
          <Dialog open={helpDialogOpen} onOpenChange={setHelpDialogOpen}>
            <Tooltip>
              <TooltipTrigger asChild>
                <DialogTrigger asChild>
                  <Button variant="ghost" size="icon" className="h-7 w-7">
                    <HelpCircle className="h-4 w-4" />
                  </Button>
                </DialogTrigger>
              </TooltipTrigger>
              <TooltipContent>User Guide</TooltipContent>
            </Tooltip>
            <DialogContent className="max-w-2xl max-h-[85vh]">
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  <HelpCircle className="h-5 w-5" />
                  Massive Trader - Quick Guide
                </DialogTitle>
              </DialogHeader>
              <ScrollArea className="h-[70vh] pr-4">
                <div className="space-y-6 text-sm">
                  {/* Quick Start */}
                  <section>
                    <h3 className="font-semibold text-base mb-2">Quick Start</h3>
                    <ul className="space-y-1 text-muted-foreground">
                      <li><strong>Trading Mode:</strong> Check badge (Paper = safe, Live = real money)</li>
                      <li><strong>Auto-Trade:</strong> Toggle in header - when ON, trades automatically</li>
                      <li><strong>Market Hours:</strong> Only trades 9:30 AM - 4:00 PM ET weekdays</li>
                    </ul>
                  </section>

                  {/* Auto-Trading */}
                  <section>
                    <h3 className="font-semibold text-base mb-2">Auto-Trading Behavior</h3>
                    <p className="text-muted-foreground mb-2">When enabled, the system scans every 60 seconds:</p>
                    <ul className="space-y-1 text-muted-foreground list-disc list-inside">
                      <li>Finds best signal from watchlist</li>
                      <li>Only trades when score &ge; 70 (strong signal)</li>
                      <li>Won&apos;t buy if you already own the ticker</li>
                      <li>Executes market orders automatically</li>
                    </ul>
                  </section>

                  {/* Understanding Scores */}
                  <section>
                    <h3 className="font-semibold text-base mb-2">Understanding Scores</h3>
                    <div className="grid grid-cols-2 gap-2 text-muted-foreground">
                      <div className="flex items-center gap-2">
                        <span className="w-16 text-green-500 font-mono">70-100</span>
                        <span>BUY signal (auto-trades here)</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="w-16 text-yellow-500 font-mono">60-69</span>
                        <span>HOLD / Watch</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="w-16 text-red-500 font-mono">&lt;60</span>
                        <span>Avoid</span>
                      </div>
                    </div>
                  </section>

                  {/* Exit Rules */}
                  <section>
                    <h3 className="font-semibold text-base mb-2">Automatic Exit Rules</h3>
                    <div className="space-y-1 text-muted-foreground">
                      <div className="flex justify-between"><span>Take Profit</span><span className="text-green-500">+5%</span></div>
                      <div className="flex justify-between"><span>Stop Loss</span><span className="text-red-500">-5%</span></div>
                      <div className="flex justify-between"><span>Quick Stop (bad trade)</span><span className="text-red-500">-3% in 30 min</span></div>
                      <div className="flex justify-between"><span>Trailing Stop</span><span>After +2%, trails 2%</span></div>
                      <div className="flex justify-between"><span>Time Exit</span><span>4 hours if not profitable</span></div>
                      <div className="flex justify-between"><span>Day Limit</span><span>24 hours max hold</span></div>
                    </div>
                  </section>

                  {/* Key Panels */}
                  <section>
                    <h3 className="font-semibold text-base mb-2">Key Panels</h3>
                    <ul className="space-y-1 text-muted-foreground">
                      <li><strong>Scanner:</strong> All watchlist stocks ranked by score</li>
                      <li><strong>Trade Signal Card:</strong> Best current opportunity</li>
                      <li><strong>AI Agents:</strong> Individual agent analysis breakdown</li>
                      <li><strong>Positions:</strong> Your current holdings with P&amp;L</li>
                      <li><strong>Activity Log:</strong> Every system action</li>
                      <li><strong>Trade Journal:</strong> Completed trades history</li>
                    </ul>
                  </section>

                  {/* Safety */}
                  <section>
                    <h3 className="font-semibold text-base mb-2">Safety Features</h3>
                    <ul className="space-y-1 text-muted-foreground list-disc list-inside">
                      <li>Paper trading by default (fake money)</li>
                      <li>Dynamic position limits based on signal score:</li>
                    </ul>
                    <div className="ml-4 mt-1 space-y-0.5 text-muted-foreground text-xs">
                      <div className="flex justify-between"><span>Score 70-79</span><span>Max 12%</span></div>
                      <div className="flex justify-between"><span>Score 80-89</span><span>Max 15%</span></div>
                      <div className="flex justify-between"><span>Score 90+</span><span className="text-green-500">Max 20%</span></div>
                    </div>
                    <ul className="space-y-1 text-muted-foreground list-disc list-inside mt-2">
                      <li>Daily drawdown limit: 5%</li>
                      <li>Max 500 shares per trade</li>
                      <li>Emergency stop button (red X) closes everything</li>
                    </ul>
                  </section>

                  {/* Common Questions */}
                  <section>
                    <h3 className="font-semibold text-base mb-2">Common Questions</h3>
                    <div className="space-y-2 text-muted-foreground">
                      <div>
                        <p className="font-medium text-foreground">Why isn&apos;t it trading?</p>
                        <p>Market closed, no signal &ge;70, already own position, or auto-trade off</p>
                      </div>
                      <div>
                        <p className="font-medium text-foreground">How do I stop auto-trading?</p>
                        <p>Toggle the &quot;Auto&quot; switch OFF in the header</p>
                      </div>
                      <div>
                        <p className="font-medium text-foreground">Where do I see trades?</p>
                        <p>Activity Log (real-time) or Trade Journal (history)</p>
                      </div>
                    </div>
                  </section>

                  {/* API Endpoints */}
                  <section>
                    <h3 className="font-semibold text-base mb-2">API Quick Reference</h3>
                    <div className="bg-muted rounded p-2 font-mono text-xs space-y-1">
                      <div>GET /api/auto-trade/status</div>
                      <div>POST /api/auto-trade/disable</div>
                      <div>GET /api/trading/positions</div>
                      <div>POST /api/trading/close-all</div>
                    </div>
                  </section>
                </div>
              </ScrollArea>
            </DialogContent>
          </Dialog>

          <Button variant="ghost" size="icon">
            <Settings className="h-5 w-5" />
          </Button>
        </div>
      </div>
    </header>
  );
}
