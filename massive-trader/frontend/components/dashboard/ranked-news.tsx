"use client";

import React, { useState, useMemo } from "react";
import { ExternalLink, Newspaper, ArrowUpDown, ArrowDown, ArrowUp } from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { NewsItem } from "@/types";

interface RankedNewsProps {
  articles: NewsItem[] | undefined;
  isLoading: boolean;
  onTickerClick?: (ticker: string) => void;
}

type SortField = "score" | "time";
type SortDir = "desc" | "asc";

function scoreColor(score: number): string {
  if (score >= 80) return "bg-green-600 text-white";
  if (score >= 65) return "bg-green-500/80 text-white";
  if (score >= 55) return "bg-yellow-500 text-black";
  if (score >= 40) return "bg-orange-500 text-white";
  return "bg-red-500 text-white";
}

function timeAgo(dateStr: string): string {
  if (!dateStr) return "";
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export function RankedNews({ articles, isLoading, onTickerClick }: RankedNewsProps) {
  const [sortField, setSortField] = useState<SortField>("score");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortField(field);
      setSortDir("desc");
    }
  };

  const sorted = useMemo(() => {
    if (!articles) return [];
    const copy = [...articles];
    copy.sort((a, b) => {
      let cmp: number;
      if (sortField === "score") {
        cmp = a.keywordScore - b.keywordScore;
      } else {
        const ta = new Date(a.publishedAt).getTime() || 0;
        const tb = new Date(b.publishedAt).getTime() || 0;
        cmp = ta - tb;
      }
      return sortDir === "desc" ? -cmp : cmp;
    });
    return copy;
  }, [articles, sortField, sortDir]);

  const count = sorted.length;

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return <ArrowUpDown className="h-3 w-3 opacity-40" />;
    return sortDir === "desc"
      ? <ArrowDown className="h-3 w-3" />
      : <ArrowUp className="h-3 w-3" />;
  };

  return (
    <Card className="h-full">
      <CardHeader className="pb-2 pt-3 px-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-semibold flex items-center gap-1.5">
            <Newspaper className="h-4 w-4" />
            Top News Today
          </CardTitle>
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => toggleSort("score")}
              className={`flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded border transition-colors ${sortField === "score" ? "bg-primary/10 border-primary/30 text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}
            >
              Score <SortIcon field="score" />
            </button>
            <button
              onClick={() => toggleSort("time")}
              className={`flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded border transition-colors ${sortField === "time" ? "bg-primary/10 border-primary/30 text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}
            >
              Time <SortIcon field="time" />
            </button>
            <Badge variant="outline" className="text-xs ml-1">
              {count}
            </Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="px-3 pb-3 pt-0">
        {isLoading && !articles ? (
          <div className="text-xs text-muted-foreground py-4 text-center">Loading news...</div>
        ) : !count ? (
          <div className="text-xs text-muted-foreground py-4 text-center">No articles found</div>
        ) : (
          <ScrollArea className="h-[420px]">
            <div className="space-y-1">
              {sorted.map((article, idx) => (
                <div
                  key={`${article.url || idx}`}
                  className="flex items-start gap-2 py-1.5 px-1 rounded hover:bg-muted/50 transition-colors"
                >
                  {/* Rank */}
                  <span className="text-xs text-muted-foreground w-5 shrink-0 pt-0.5 text-right font-mono">
                    {idx + 1}
                  </span>

                  {/* Score badge */}
                  <span
                    className={`text-xs font-bold rounded px-1.5 py-0.5 shrink-0 ${scoreColor(article.keywordScore)}`}
                  >
                    {article.keywordScore}
                  </span>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start gap-1">
                      {article.url ? (
                        <a
                          href={article.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs font-medium leading-tight hover:underline line-clamp-2"
                        >
                          {article.headline}
                          <ExternalLink className="inline h-3 w-3 ml-0.5 opacity-40" />
                        </a>
                      ) : (
                        <span className="text-xs font-medium leading-tight line-clamp-2">
                          {article.headline}
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                      {/* Tickers */}
                      {article.symbols.slice(0, 4).map((t) => (
                        <Badge
                          key={t}
                          variant="secondary"
                          className="text-[10px] px-1 py-0 cursor-pointer hover:bg-primary/20"
                          onClick={() => onTickerClick?.(t)}
                        >
                          {t}
                        </Badge>
                      ))}
                      {article.symbols.length > 4 && (
                        <span className="text-[10px] text-muted-foreground">
                          +{article.symbols.length - 4}
                        </span>
                      )}

                      {/* Time + Source */}
                      <span className="text-[10px] text-muted-foreground ml-auto whitespace-nowrap">
                        {timeAgo(article.publishedAt)} · {article.source}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  );
}
