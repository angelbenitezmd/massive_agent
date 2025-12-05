"use client";

import { ExternalLink, Newspaper, Clock } from "lucide-react";
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
import { formatNewsTime, cn } from "@/lib/utils";
import type { NewsItem } from "@/types";

interface NewsPanelProps {
  news: NewsItem[] | undefined;
  isLoading: boolean;
}

export function NewsPanel({ news, isLoading }: NewsPanelProps) {
  const getSentimentBadge = (sentiment?: string) => {
    switch (sentiment?.toLowerCase()) {
      case "bullish":
        return <Badge variant="success">Bullish</Badge>;
      case "bearish":
        return <Badge variant="danger">Bearish</Badge>;
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
            Market News
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
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
    <Card className="card-hover">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2">
          <Newspaper className="h-5 w-5 text-primary" />
          Market News
        </CardTitle>
        <CardDescription>
          Latest Benzinga headlines across all tickers
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-[500px] pr-4">
          {news && news.length > 0 ? (
            <div className="space-y-4">
              {news.map((item, index) => (
                <div key={item.id || index}>
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group block space-y-2 hover:bg-accent/50 rounded-lg p-3 -mx-3 transition-colors"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <h4 className="font-medium leading-tight group-hover:text-primary transition-colors line-clamp-2">
                        {item.headline}
                      </h4>
                      <ExternalLink className="h-4 w-4 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground" />
                    </div>

                    <div className="flex items-center gap-2 flex-wrap">
                      <div className="flex items-center gap-1 text-xs text-muted-foreground">
                        <Clock className="h-3 w-3" />
                        {formatNewsTime(item.publishedAt)}
                      </div>
                      <span className="text-xs text-muted-foreground">
                        {item.source}
                      </span>
                      {getSentimentBadge(item.sentiment)}
                      {item.tags?.slice(0, 2).map((tag, tagIndex) => (
                        <Badge
                          key={`${item.id || index}-tag-${tagIndex}`}
                          variant="outline"
                          className="text-xs"
                        >
                          {tag}
                        </Badge>
                      ))}
                    </div>

                    {item.summary && (
                      <p className="text-sm text-muted-foreground line-clamp-2">
                        {item.summary}
                      </p>
                    )}
                  </a>
                  {index < news.length - 1 && <Separator className="mt-4" />}
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
  );
}
