"use client";

import { memo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Users, TrendingUp, TrendingDown, Minus, Target, Info } from "lucide-react";

interface RatingItem {
  benzinga_id?: string;
  ticker: string;
  company_name?: string;
  firm: string;
  analyst?: string;
  rating?: string;
  previous_rating?: string;
  rating_action?: string;
  price_target?: number;
  previous_price_target?: number;
  price_target_action?: string;
  date: string;
}

interface AnalystRatingsProps {
  ratings?: RatingItem[];
  selectedTicker?: string;
  isLoading?: boolean;
}

function formatDate(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function getRatingActionIcon(action?: string) {
  if (!action) return <Minus className="h-3 w-3 text-muted-foreground" />;
  const a = action.toLowerCase();
  if (a.includes("upgrade")) return <TrendingUp className="h-3 w-3 text-green-500" />;
  if (a.includes("downgrade")) return <TrendingDown className="h-3 w-3 text-red-500" />;
  if (a.includes("initiate")) return <Target className="h-3 w-3 text-blue-500" />;
  return <Minus className="h-3 w-3 text-muted-foreground" />;
}

function getRatingActionBadge(action?: string) {
  if (!action) return null;
  const a = action.toLowerCase();
  let variant: "default" | "destructive" | "secondary" = "secondary";
  let text = action.replace(/_/g, " ");

  if (a.includes("upgrade")) {
    variant = "default";
    text = "Upgrade";
  } else if (a.includes("downgrade")) {
    variant = "destructive";
    text = "Downgrade";
  } else if (a.includes("initiate")) {
    text = "New Coverage";
  } else if (a.includes("reiterate") || a.includes("maintain")) {
    text = "Reiterate";
  }

  return (
    <Badge variant={variant} className="text-[10px] px-1.5 py-0">
      {text}
    </Badge>
  );
}

function getPriceTargetChange(current?: number, previous?: number): JSX.Element | null {
  if (!current) return null;

  if (previous && previous !== current) {
    const change = current - previous;
    const pctChange = ((change / previous) * 100).toFixed(0);
    const isUp = change > 0;

    return (
      <div className="flex items-center gap-1">
        <Target className="h-3 w-3 text-muted-foreground" />
        <span className="text-xs">${current}</span>
        <span className={`text-[10px] ${isUp ? "text-green-500" : "text-red-500"}`}>
          ({isUp ? "+" : ""}{pctChange}%)
        </span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1">
      <Target className="h-3 w-3 text-muted-foreground" />
      <span className="text-xs">${current}</span>
    </div>
  );
}

export const AnalystRatings = memo(function AnalystRatings({
  ratings = [],
  selectedTicker,
  isLoading,
}: AnalystRatingsProps) {
  // Filter and limit ratings
  const displayRatings = selectedTicker
    ? ratings.filter((r) => r.ticker === selectedTicker).slice(0, 8)
    : ratings.slice(0, 8);

  // Count upgrades vs downgrades
  const upgrades = displayRatings.filter((r) =>
    r.rating_action?.toLowerCase().includes("upgrade")
  ).length;
  const downgrades = displayRatings.filter((r) =>
    r.rating_action?.toLowerCase().includes("downgrade")
  ).length;

  return (
    <TooltipProvider>
      <Card className="bg-card border-border">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Users className="h-4 w-4 text-primary" />
            Analyst Ratings
            <Tooltip>
              <TooltipTrigger asChild>
                <Info className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground cursor-help transition-colors" />
              </TooltipTrigger>
              <TooltipContent side="bottom" className="max-w-[280px] p-3">
                <div className="space-y-2 text-xs">
                  <p className="font-semibold text-sm">Rating Actions Explained</p>
                  <div className="space-y-1.5">
                    <div className="flex items-center gap-2">
                      <Badge variant="default" className="text-[10px] px-1.5 py-0">Upgrade</Badge>
                      <span>Analyst raised their rating (e.g., Hold → Buy)</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="destructive" className="text-[10px] px-1.5 py-0">Downgrade</Badge>
                      <span>Analyst lowered their rating (e.g., Buy → Hold)</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="secondary" className="text-[10px] px-1.5 py-0">Reiterate</Badge>
                      <span>Analyst reaffirmed their existing rating</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="secondary" className="text-[10px] px-1.5 py-0">New Coverage</Badge>
                      <span>Analyst started covering this stock</span>
                    </div>
                  </div>
                  <div className="pt-1 border-t border-border mt-2">
                    <p className="text-muted-foreground">
                      <Target className="h-3 w-3 inline mr-1" />
                      <strong>Price Target:</strong> Analyst&apos;s expected stock price. % shows change from previous target.
                    </p>
                  </div>
                </div>
              </TooltipContent>
            </Tooltip>
            {displayRatings.length > 0 && (
              <div className="ml-auto flex items-center gap-2">
                {upgrades > 0 && (
                  <Badge variant="default" className="text-[10px] px-1.5 py-0">
                    {upgrades} Up
                  </Badge>
                )}
                {downgrades > 0 && (
                  <Badge variant="destructive" className="text-[10px] px-1.5 py-0">
                    {downgrades} Down
                  </Badge>
                )}
              </div>
            )}
          </CardTitle>
        </CardHeader>
      <CardContent className="pt-0">
        <ScrollArea className="h-[130px]">
          {isLoading ? (
            <div className="flex items-center justify-center h-full text-muted-foreground">
              Loading ratings...
            </div>
          ) : displayRatings.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
              <Users className="h-8 w-8 mb-2 opacity-50" />
              <p className="text-sm">No recent analyst ratings</p>
              <p className="text-xs mt-1">Ratings require a Benzinga subscription</p>
            </div>
          ) : (
            <div className="space-y-2">
              {displayRatings.map((rating, idx) => (
                <div
                  key={rating.benzinga_id || idx}
                  className="p-2 rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        {getRatingActionIcon(rating.rating_action)}
                        <span className="font-medium text-sm">{rating.ticker}</span>
                        {getRatingActionBadge(rating.rating_action)}
                      </div>
                      <div className="text-xs text-muted-foreground mt-1 truncate">
                        {rating.firm}
                        {rating.analyst && ` - ${rating.analyst}`}
                      </div>
                      {rating.rating && (
                        <div className="text-xs mt-1">
                          <span className="text-muted-foreground">Rating: </span>
                          <span className="font-medium">{rating.rating}</span>
                          {rating.previous_rating && rating.previous_rating !== rating.rating && (
                            <span className="text-muted-foreground">
                              {" "}
                              (was {rating.previous_rating})
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                    <div className="text-right shrink-0">
                      {getPriceTargetChange(rating.price_target, rating.previous_price_target)}
                      <div className="text-[10px] text-muted-foreground mt-1">
                        {formatDate(rating.date)}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
      </CardContent>
      </Card>
    </TooltipProvider>
  );
});
