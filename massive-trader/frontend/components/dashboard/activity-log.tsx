"use client";

import { memo } from "react";
import { Activity, ArrowUpCircle, ArrowDownCircle, AlertCircle, CheckCircle, XCircle, Clock, Info } from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { formatRelativeTime, formatCurrency, formatPercent } from "@/lib/utils";
import type { ActivityLogEntry } from "@/lib/api";

interface ActivityLogProps {
  logs: ActivityLogEntry[] | undefined;
  isLoading: boolean;
}

export const ActivityLog = memo(function ActivityLog({ logs, isLoading }: ActivityLogProps) {
  const getTypeIcon = (type: string) => {
    switch (type) {
      case "ENTRY_SUCCESS":
        return <ArrowUpCircle className="h-4 w-4 text-green-500" />;
      case "EXIT_SUCCESS":
        return <CheckCircle className="h-4 w-4 text-blue-500" />;
      case "EXIT_SIGNAL":
        return <ArrowDownCircle className="h-4 w-4 text-yellow-500" />;
      case "ENTRY_ERROR":
      case "EXIT_ERROR":
        return <XCircle className="h-4 w-4 text-red-500" />;
      case "EXIT_WARNING":
        return <AlertCircle className="h-4 w-4 text-orange-500" />;
      default:
        return <Activity className="h-4 w-4 text-muted-foreground" />;
    }
  };

  const getTypeBadge = (type: string) => {
    switch (type) {
      case "ENTRY_SUCCESS":
        return <Badge variant="success" className="text-xs">ENTRY</Badge>;
      case "EXIT_SUCCESS":
        return <Badge variant="default" className="text-xs bg-blue-500">EXIT OK</Badge>;
      case "EXIT_SIGNAL":
        return <Badge variant="warning" className="text-xs">EXIT SIGNAL</Badge>;
      case "ENTRY_ERROR":
        return <Badge variant="danger" className="text-xs">ENTRY FAIL</Badge>;
      case "EXIT_ERROR":
        return <Badge variant="danger" className="text-xs">EXIT FAIL</Badge>;
      case "EXIT_WARNING":
        return <Badge variant="warning" className="text-xs">WARNING</Badge>;
      case "AUTO_EXIT":
        return <Badge variant="default" className="text-xs bg-blue-500">AUTO_EXIT</Badge>;
      case "TRADE":
        return <Badge variant="success" className="text-xs">TRADE</Badge>;
      default:
        return <Badge variant="outline" className="text-xs">{type}</Badge>;
    }
  };

  const getStatusBadge = (status: string | undefined) => {
    if (!status) return null;
    switch (status.toLowerCase()) {
      case "executed":
      case "filled":
        return <Badge variant="outline" className="text-[10px] text-green-500 border-green-500/50">FILLED</Badge>;
      case "pending":
      case "new":
      case "held":
        return <Badge variant="outline" className="text-[10px] text-yellow-500 border-yellow-500/50">PENDING</Badge>;
      case "closed":
        return <Badge variant="outline" className="text-[10px] text-blue-500 border-blue-500/50">CLOSED</Badge>;
      case "canceled":
      case "cancelled":
        return <Badge variant="outline" className="text-[10px] text-muted-foreground">CANCELED</Badge>;
      case "rejected":
      case "failed":
        return <Badge variant="outline" className="text-[10px] text-red-500 border-red-500/50">FAILED</Badge>;
      default:
        return <Badge variant="outline" className="text-[10px]">{status.toUpperCase()}</Badge>;
    }
  };

  const formatDetails = (log: ActivityLogEntry) => {
    const details = log.details;
    const parts: string[] = [];

    if (details.reason) {
      parts.push(details.reason);
    }
    if (details.error) {
      parts.push(`Error: ${details.error}`);
    }
    if (details.pnl !== undefined && details.pnl !== null) {
      const pnlStr = details.pnl >= 0 ? `+${formatCurrency(details.pnl)}` : formatCurrency(details.pnl);
      parts.push(`P&L: ${pnlStr}`);
    }
    if (details.pnl_pct !== undefined && details.pnl_pct !== null) {
      parts.push(`(${formatPercent(details.pnl_pct)})`);
    }
    if (details.quantity) {
      parts.push(`Qty: ${details.quantity}`);
    }
    if (details.entry_price) {
      parts.push(`Entry: ${formatCurrency(details.entry_price)}`);
    }
    if (details.current_price) {
      parts.push(`Current: ${formatCurrency(details.current_price)}`);
    }

    return parts.join(" | ");
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Activity className="h-5 w-5" />
            Activity Log
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
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
    <TooltipProvider>
    <Card className="card-hover">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Activity className="h-5 w-5 text-primary" />
          Activity Log
          <Tooltip>
            <TooltipTrigger asChild>
              <Info className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground cursor-help" />
            </TooltipTrigger>
            <TooltipContent side="bottom" className="max-w-[280px] p-3">
              <div className="space-y-2 text-xs">
                <p className="font-semibold">Activity Log</p>
                <p>Real-time log of trading system actions and events.</p>
                <div className="space-y-1 pt-1">
                  <p><strong>ENTRY:</strong> New position opened</p>
                  <p><strong>EXIT:</strong> Position closed (with P&L)</p>
                  <p><strong>SIGNAL:</strong> Exit condition triggered</p>
                </div>
                <p className="text-muted-foreground">Includes error messages and warnings if trades fail.</p>
              </div>
            </TooltipContent>
          </Tooltip>
        </CardTitle>
        <CardDescription>
          Trade entries, exits, and signals
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-[130px] pr-4">
          {logs && logs.length > 0 ? (
            <div className="space-y-2">
              {logs.map((log) => (
                <div
                  key={log.id}
                  className="flex items-start gap-2 p-2 rounded-lg bg-accent/30 hover:bg-accent/50 transition-colors"
                >
                  <div className="mt-0.5">
                    {getTypeIcon(log.type)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-sm">{log.ticker}</span>
                      {getTypeBadge(log.type)}
                      <span className="text-xs text-muted-foreground">
                        {log.action}
                      </span>
                      {getStatusBadge(log.details?.status || log.details?.result)}
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">
                      {formatDetails(log)}
                    </p>
                    <div className="flex items-center gap-1 text-[10px] text-muted-foreground/70">
                      <Clock className="h-2.5 w-2.5" />
                      {log.timestamp ? new Date(log.timestamp).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true, timeZone: "America/New_York" }) + " " + new Date(log.timestamp).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "America/New_York" }) : "Unknown"}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground py-4">
              <Activity className="h-8 w-8 mb-2 opacity-50" />
              <p className="text-xs">No activity yet</p>
            </div>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
    </TooltipProvider>
  );
});
