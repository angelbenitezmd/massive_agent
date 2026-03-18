"use client";

import { useState, useMemo } from "react";
import { ExternalLink, Newspaper, Clock, TrendingUp, TrendingDown, Info, Filter, ArrowUpDown, ArrowDown, ArrowUp } from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { formatNewsTime, cn } from "@/lib/utils";
import type { NewsItem } from "@/types";

const TIME_FILTERS = [
  { label: "30m", hours: 0.5 },
  { label: "1h", hours: 1 },
  { label: "4h", hours: 4 },
  { label: "All", hours: 0 },
] as const;

const SCORE_FILTERS = [
  { label: "All", min: 0, max: 100 },
  { label: "Bullish 70+", min: 70, max: 100 },
  { label: "Bearish <30", min: 0, max: 30 },
] as const;

interface NewsFeedProps {
  news: NewsItem[] | undefined;
  isLoading: boolean;
  onTickerClick?: (ticker: string) => void;
  selectedTicker?: string;
  watchlist?: string[];
}

export function NewsFeed({ news, isLoading, onTickerClick, selectedTicker, watchlist }: NewsFeedProps) {
  const [timeFilter, setTimeFilter] = useState(3); // index into TIME_FILTERS, default "All"
  const [scoreFilter, setScoreFilter] = useState(0); // index into SCORE_FILTERS, default "All"
  const [scoreSort, setScoreSort] = useState<"none" | "desc" | "asc">("none");

  const watchlistSet = useMemo(() => new Set(watchlist || []), [watchlist]);

  const filteredNews = useMemo(() => {
    if (!news) return [];
    const filtered = news.filter((item) => {
      // Time filter
      const tf = TIME_FILTERS[timeFilter];
      if (tf.hours > 0 && item.publishedAt) {
        const published = new Date(item.publishedAt).getTime();
        const cutoff = Date.now() - tf.hours * 60 * 60 * 1000;
        if (published < cutoff) return false;
      }
      // Score filter
      const sf = SCORE_FILTERS[scoreFilter];
      const kw = item.keywordScore ?? 50;
      if (sf.min === 0 && sf.max === 30) {
        if (kw >= 30) return false;
      } else if (sf.min > 0) {
        if (kw < sf.min) return false;
      }
      return true;
    });
    // Sort by score
    if (scoreSort !== "none") {
      filtered.sort((a, b) => {
        const diff = (a.keywordScore ?? 50) - (b.keywordScore ?? 50);
        return scoreSort === "desc" ? -diff : diff;
      });
    }
    return filtered;
  }, [news, timeFilter, scoreFilter, scoreSort]);

  // Display invariant requested by user:
  // Always show KW score. <30 red gradient, >70 green gradient.
  const getKeywordScoreStyle = (score: number) => {
    const safe = Math.max(0, Math.min(100, Number.isFinite(score) ? score : 50));

    if (safe < 30) {
      // Lower score => deeper red
      const lightness = 45 - ((30 - safe) / 30) * 20; // 45% -> 25%
      return { backgroundColor: `hsl(0 78% ${lightness}%)`, color: "white" };
    }

    if (safe > 70) {
      // Higher score => darker green
      const lightness = 42 - ((safe - 70) / 30) * 20; // 42% -> 22%
      return { backgroundColor: `hsl(140 65% ${lightness}%)`, color: "white" };
    }

    return { backgroundColor: "hsl(42 90% 45%)", color: "black" };
  };

  const getSentimentBadge = (sentiment?: string) => {
    switch (sentiment?.toLowerCase()) {
      case "bullish":
        return (
          <Badge variant="success" className="gap-1">
            <TrendingUp className="h-3 w-3" />
            Bullish
          </Badge>
        );
      case "bearish":
        return (
          <Badge variant="danger" className="gap-1">
            <TrendingDown className="h-3 w-3" />
            Bearish
          </Badge>
        );
      default:
        return null;
    }
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Newspaper className="h-5 w-5" />
            {selectedTicker ? `${selectedTicker} News` : "Live News Feed"}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="animate-pulse space-y-2">
                <div className="h-4 bg-secondary rounded w-3/4" />
                <div className="h-3 bg-secondary rounded w-1/2" />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  const hasActiveFilters = timeFilter !== 3 || scoreFilter !== 0 || scoreSort !== "none";

  return (
    <TooltipProvider>
    <Card className="card-hover">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2">
          <Newspaper className="h-5 w-5 text-primary" />
          {selectedTicker ? `${selectedTicker} News` : "Live News Feed"}
          <Tooltip>
            <TooltipTrigger asChild>
              <Info className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground cursor-help" />
            </TooltipTrigger>
            <TooltipContent side="bottom" className="max-w-[280px] p-3">
              <div className="space-y-2 text-xs">
                <p className="font-semibold">News Feed</p>
                <p>Real-time financial news from Benzinga. Click ticker badges to switch stocks.</p>
                <p className="text-muted-foreground">Watchlist tickers are highlighted with a yellow border.</p>
              </div>
            </TooltipContent>
          </Tooltip>
          {hasActiveFilters && (
            <Badge variant="secondary" className="text-xs ml-auto">
              {filteredNews.length}/{news?.length || 0}
            </Badge>
          )}
        </CardTitle>

        {/* Filter bar */}
        <div className="flex flex-col gap-1.5 pt-1">
          {/* Time filters */}
          <div className="flex items-center gap-1">
            <Clock className="h-3 w-3 text-muted-foreground shrink-0" />
            {TIME_FILTERS.map((tf, i) => (
              <Button
                key={tf.label}
                variant={timeFilter === i ? "default" : "ghost"}
                size="sm"
                className={cn(
                  "h-5 px-2 text-xs",
                  timeFilter === i && "bg-primary text-primary-foreground"
                )}
                onClick={() => setTimeFilter(i)}
              >
                {tf.label}
              </Button>
            ))}
          </div>
          {/* Score filters + sort */}
          <div className="flex items-center gap-1">
            <Filter className="h-3 w-3 text-muted-foreground shrink-0" />
            {SCORE_FILTERS.map((sf, i) => (
              <Button
                key={sf.label}
                variant={scoreFilter === i ? "default" : "ghost"}
                size="sm"
                className={cn(
                  "h-5 px-2 text-xs",
                  scoreFilter === i && "bg-primary text-primary-foreground"
                )}
                onClick={() => setScoreFilter(i)}
              >
                {sf.label}
              </Button>
            ))}
            <Separator orientation="vertical" className="h-4 mx-0.5" />
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant={scoreSort !== "none" ? "default" : "ghost"}
                  size="sm"
                  className={cn(
                    "h-5 px-1.5 text-xs gap-1",
                    scoreSort !== "none" && "bg-primary text-primary-foreground"
                  )}
                  onClick={() =>
                    setScoreSort((prev) =>
                      prev === "none" ? "desc" : prev === "desc" ? "asc" : "none"
                    )
                  }
                >
                  {scoreSort === "desc" ? (
                    <ArrowDown className="h-3 w-3" />
                  ) : scoreSort === "asc" ? (
                    <ArrowUp className="h-3 w-3" />
                  ) : (
                    <ArrowUpDown className="h-3 w-3" />
                  )}
                  KW
                </Button>
              </TooltipTrigger>
              <TooltipContent side="bottom" className="text-xs">
                {scoreSort === "none" ? "Sort by score" : scoreSort === "desc" ? "Highest first" : "Lowest first"}
              </TooltipContent>
            </Tooltip>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-[200px] pr-4">
          {filteredNews.length > 0 ? (
            <div className="space-y-3">
              {filteredNews.map((item, index) => (
                <div key={`${item.id || 'news'}-${index}`}>
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group block space-y-2 hover:bg-accent/50 rounded-lg p-3 -mx-3 transition-colors"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <h4 className="font-medium leading-tight group-hover:text-primary transition-colors line-clamp-2 text-sm">
                        {item.headline}
                      </h4>
                      <ExternalLink className="h-4 w-4 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground" />
                    </div>

                    <div className="flex items-center gap-2 flex-wrap">
                      <div className="flex items-center gap-1 text-xs text-muted-foreground">
                        <Clock className="h-3 w-3" />
                        {formatNewsTime(item.publishedAt)}
                      </div>
                      <Badge
                        className="text-xs font-semibold border-0"
                        style={getKeywordScoreStyle(item.keywordScore)}
                      >
                        KW {item.keywordScore}
                      </Badge>
                      {item.source && (
                        <span className="text-xs text-muted-foreground">
                          {item.source}
                        </span>
                      )}
                      {getSentimentBadge(item.sentiment)}
                    </div>

                    {/* Ticker badges — watchlist tickers highlighted */}
                    {item.symbols && item.symbols.length > 0 && (
                      <div className="flex items-center gap-1 flex-wrap">
                        {item.symbols.slice(0, 5).map((symbol, symbolIndex) => {
                          const isWatchlist = watchlistSet.has(symbol);
                          return (
                            <Badge
                              key={`${item.id || index}-symbol-${symbolIndex}`}
                              variant="secondary"
                              className={cn(
                                "text-xs cursor-pointer transition-colors",
                                isWatchlist
                                  ? "border-yellow-500 border bg-yellow-500/15 text-yellow-200 hover:bg-yellow-500/30 font-semibold"
                                  : "hover:bg-primary hover:text-primary-foreground"
                              )}
                              onClick={(e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                onTickerClick?.(symbol);
                              }}
                            >
                              ${symbol}
                            </Badge>
                          );
                        })}
                        {item.symbols.length > 5 && (
                          <span className="text-xs text-muted-foreground">
                            +{item.symbols.length - 5} more
                          </span>
                        )}
                      </div>
                    )}

                    {/* Tags/channels */}
                    {item.tags && item.tags.length > 0 && (
                      <div className="flex items-center gap-1 flex-wrap">
                        {item.tags.slice(0, 3).map((tag, tagIndex) => (
                          <Badge
                            key={`${item.id || index}-tag-${tagIndex}`}
                            variant="outline"
                            className="text-xs"
                          >
                            {typeof tag === "string" ? tag : (tag as any).name || String(tag)}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </a>
                  {index < filteredNews.length - 1 && <Separator className="mt-3" />}
                </div>
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground py-8">
              <Newspaper className="h-12 w-12 mb-4 opacity-50" />
              {hasActiveFilters ? (
                <div className="text-center">
                  <p>No news matching filters</p>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="mt-2 text-xs"
                    onClick={() => { setTimeFilter(3); setScoreFilter(0); setScoreSort("none"); }}
                  >
                    Clear filters
                  </Button>
                </div>
              ) : (
                <p>No news available</p>
              )}
            </div>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
    </TooltipProvider>
  );
}
