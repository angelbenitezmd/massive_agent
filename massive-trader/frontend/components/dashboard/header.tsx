"use client";

import { useState } from "react";
import {
  Search,
  Activity,
  RefreshCw,
  Settings,
  AlertTriangle,
  Circle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useSystemStatus } from "@/hooks/use-trading-data";
import { cn } from "@/lib/utils";

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
}: HeaderProps) {
  const [searchValue, setSearchValue] = useState(selectedTicker);
  const [showWatchlist, setShowWatchlist] = useState(false);
  const { data: status } = useSystemStatus();

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchValue.trim()) {
      onTickerChange(searchValue.trim().toUpperCase());
    }
  };

  const isLive = status?.tradingMode === "live";

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
        <div className="flex items-center gap-4 flex-1 max-w-md mx-8">
          <form onSubmit={handleSearch} className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              value={searchValue}
              onChange={(e) => setSearchValue(e.target.value.toUpperCase())}
              onFocus={() => setShowWatchlist(true)}
              onBlur={() => setTimeout(() => setShowWatchlist(false), 200)}
              placeholder="Search ticker..."
              className="pl-10 bg-secondary/50"
            />
            {showWatchlist && watchlist.length > 0 && (
              <div className="absolute top-full left-0 right-0 mt-1 bg-popover border rounded-md shadow-lg z-50">
                {watchlist.map((ticker) => (
                  <button
                    key={ticker}
                    type="button"
                    onClick={() => {
                      onTickerChange(ticker);
                      setSearchValue(ticker);
                    }}
                    className="w-full px-4 py-2 text-left hover:bg-accent transition-colors first:rounded-t-md last:rounded-b-md"
                  >
                    {ticker}
                  </button>
                ))}
              </div>
            )}
          </form>

          <Button onClick={onAnalyze} disabled={isAnalyzing} className="gap-2">
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
        <div className="flex items-center gap-6">
          {/* Auto-Refresh Toggle */}
          <div className="flex items-center gap-2">
            <label
              htmlFor="auto-refresh"
              className="text-sm text-muted-foreground"
            >
              Auto-refresh
            </label>
            <Switch
              id="auto-refresh"
              checked={autoRefresh}
              onCheckedChange={onAutoRefreshChange}
            />
          </div>

          {/* Auto-Trade Toggle */}
          <div className="flex items-center gap-2">
            <label
              htmlFor="auto-trade"
              className="text-sm text-muted-foreground"
            >
              Auto-trade
            </label>
            <Tooltip>
              <TooltipTrigger asChild>
                <div>
                  <Switch
                    id="auto-trade"
                    checked={autoTrade}
                    onCheckedChange={onAutoTradeChange}
                    className={cn(
                      autoTrade && "data-[state=checked]:bg-yellow-600"
                    )}
                  />
                </div>
              </TooltipTrigger>
              <TooltipContent>
                {autoTrade
                  ? "Auto-trade enabled - trades will execute automatically"
                  : "Auto-trade disabled"}
              </TooltipContent>
            </Tooltip>
          </div>

          <Button variant="ghost" size="icon">
            <Settings className="h-5 w-5" />
          </Button>
        </div>
      </div>
    </header>
  );
}
