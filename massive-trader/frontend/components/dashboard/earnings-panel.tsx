"use client";

import { DollarSign, TrendingUp, TrendingDown, Calendar } from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { formatCurrency, formatPercent, cn } from "@/lib/utils";
import type { Earnings } from "@/types";

interface EarningsPanelProps {
  earnings: Earnings[] | undefined;
  isLoading: boolean;
}

export function EarningsPanel({ earnings, isLoading }: EarningsPanelProps) {
  const getImportanceBadge = (importance: number) => {
    if (importance >= 4) return <Badge variant="destructive">High</Badge>;
    if (importance >= 2) return <Badge variant="warning">Medium</Badge>;
    return <Badge variant="secondary">Low</Badge>;
  };

  const getSurpriseColor = (surprise: number | null) => {
    if (surprise === null) return "text-muted-foreground";
    if (surprise > 0) return "text-green-500";
    if (surprise < 0) return "text-red-500";
    return "text-yellow-500";
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <DollarSign className="h-5 w-5" />
            Earnings
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="animate-pulse space-y-4">
            <div className="h-20 bg-secondary rounded" />
            <div className="h-20 bg-secondary rounded" />
          </div>
        </CardContent>
      </Card>
    );
  }

  const recentEarnings = earnings?.slice(0, 2) || [];

  return (
    <Card className="card-hover">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2">
          <DollarSign className="h-5 w-5 text-primary" />
          Earnings
        </CardTitle>
        <CardDescription>Recent earnings reports</CardDescription>
      </CardHeader>
      <CardContent>
        {recentEarnings.length > 0 ? (
          <div className="space-y-4">
            {recentEarnings.map((earning, index) => (
              <div
                key={`${earning.fiscalQuarter}-${earning.fiscalYear}`}
                className="p-4 rounded-lg bg-secondary/30 space-y-3"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Calendar className="h-4 w-4 text-muted-foreground" />
                    <span className="font-medium">
                      {earning.fiscalQuarter} {earning.fiscalYear}
                    </span>
                  </div>
                  {getImportanceBadge(earning.importance)}
                </div>

                {/* EPS */}
                <div className="space-y-1">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">EPS</span>
                    <div className="flex items-center gap-2">
                      {earning.epsActual !== null ? (
                        <>
                          <span className="font-medium">
                            ${earning.epsActual?.toFixed(2)}
                          </span>
                          <span className="text-muted-foreground">
                            vs ${earning.epsEstimate?.toFixed(2)} est
                          </span>
                          {earning.epsSurprisePercent !== null && (
                            <span
                              className={cn(
                                "flex items-center gap-1 font-medium",
                                getSurpriseColor(earning.epsSurprisePercent)
                              )}
                            >
                              {earning.epsSurprisePercent > 0 ? (
                                <TrendingUp className="h-3 w-3" />
                              ) : (
                                <TrendingDown className="h-3 w-3" />
                              )}
                              {formatPercent(earning.epsSurprisePercent)}
                            </span>
                          )}
                        </>
                      ) : (
                        <span className="text-muted-foreground">
                          Est: ${earning.epsEstimate?.toFixed(2) || "N/A"}
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                {/* Revenue */}
                <div className="space-y-1">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Revenue</span>
                    <div className="flex items-center gap-2">
                      {earning.revenueActual !== null ? (
                        <>
                          <span className="font-medium">
                            {formatCurrency(earning.revenueActual / 1_000_000)}M
                          </span>
                          <span className="text-muted-foreground">
                            vs{" "}
                            {formatCurrency(
                              (earning.revenueEstimate || 0) / 1_000_000
                            )}
                            M est
                          </span>
                          {earning.revenueSurprisePercent !== null && (
                            <span
                              className={cn(
                                "flex items-center gap-1 font-medium",
                                getSurpriseColor(earning.revenueSurprisePercent)
                              )}
                            >
                              {earning.revenueSurprisePercent > 0 ? (
                                <TrendingUp className="h-3 w-3" />
                              ) : (
                                <TrendingDown className="h-3 w-3" />
                              )}
                              {formatPercent(earning.revenueSurprisePercent)}
                            </span>
                          )}
                        </>
                      ) : (
                        <span className="text-muted-foreground">
                          Est:{" "}
                          {earning.revenueEstimate
                            ? formatCurrency(earning.revenueEstimate / 1_000_000) +
                              "M"
                            : "N/A"}
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                {/* Report Date */}
                <div className="flex items-center justify-between text-xs text-muted-foreground pt-1 border-t border-border/50">
                  <span>Report Date</span>
                  <span>
                    {new Date(earning.reportDate).toLocaleDateString()} (
                    {earning.reportTime})
                  </span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
            <DollarSign className="h-12 w-12 mb-4 opacity-50" />
            <p>No earnings data available</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
