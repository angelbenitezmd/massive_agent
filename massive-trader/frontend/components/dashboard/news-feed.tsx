"use client";

import { ExternalLink, Newspaper, Clock, TrendingUp, TrendingDown, Info } from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
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

interface NewsFeedProps {
  news: NewsItem[] | undefined;
  isLoading: boolean;
  onTickerClick?: (ticker: string) => void;
  selectedTicker?: string;
}

export function NewsFeed({ news, isLoading, onTickerClick, selectedTicker }: NewsFeedProps) {
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

  return (
    <TooltipProvider>
    <Card className="card-hover">
      <CardHeader className="pb-3">
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
                <p className="text-muted-foreground">Bullish/Bearish sentiment is AI-analyzed from headlines and content.</p>
              </div>
            </TooltipContent>
          </Tooltip>
        </CardTitle>
        <CardDescription>
          {selectedTicker ? `Latest news for ${selectedTicker}` : "Real-time market news from Benzinga"}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-[200px] pr-4">
          {news && news.length > 0 ? (
            <div className="space-y-3">
              {news.map((item, index) => (
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
                      {item.source && (
                        <span className="text-xs text-muted-foreground">
                          {item.source}
                        </span>
                      )}
                      {getSentimentBadge(item.sentiment)}
                    </div>

                    {/* Ticker badges */}
                    {item.symbols && item.symbols.length > 0 && (
                      <div className="flex items-center gap-1 flex-wrap">
                        {item.symbols.slice(0, 5).map((symbol, symbolIndex) => (
                          <Badge
                            key={`${item.id || index}-symbol-${symbolIndex}`}
                            variant="secondary"
                            className="text-xs cursor-pointer hover:bg-primary hover:text-primary-foreground transition-colors"
                            onClick={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                              onTickerClick?.(symbol);
                            }}
                          >
                            ${symbol}
                          </Badge>
                        ))}
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
                  {index < news.length - 1 && <Separator className="mt-3" />}
                </div>
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground py-8">
              <Newspaper className="h-12 w-12 mb-4 opacity-50" />
              <p>No news available</p>
            </div>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
    </TooltipProvider>
  );
}
