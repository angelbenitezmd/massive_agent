"use client";

import { memo } from "react";
import { Coins, Zap, ArrowUpRight, ArrowDownRight } from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useTokenUsage } from "@/hooks/use-trading-data";
import { cn } from "@/lib/utils";

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toString();
}

function TokenMonitorInner() {
  const { data, isLoading } = useTokenUsage();

  if (isLoading || !data) {
    return (
      <Card className="border-border/50">
        <CardHeader className="pb-2 pt-3 px-4">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Coins className="h-4 w-4 text-yellow-500" />
            LLM Tokens
          </CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-3">
          <p className="text-xs text-muted-foreground">Loading...</p>
        </CardContent>
      </Card>
    );
  }

  const models = Object.entries(data.by_model);
  const agents = Object.entries(data.by_agent);
  const maxHourTokens = data.by_hour.length > 0
    ? Math.max(...data.by_hour.map(h => h.input + h.output))
    : 0;

  return (
    <Card className="border-border/50">
      <CardHeader className="pb-2 pt-3 px-4">
        <CardTitle className="text-sm font-medium flex items-center justify-between">
          <span className="flex items-center gap-2">
            <Coins className="h-4 w-4 text-yellow-500" />
            LLM Tokens
          </span>
          <Badge
            variant="outline"
            className={cn(
              "text-xs font-mono",
              data.total_cost_estimate > 1
                ? "border-red-500/50 text-red-400"
                : data.total_cost_estimate > 0.25
                  ? "border-yellow-500/50 text-yellow-400"
                  : "border-green-500/50 text-green-400"
            )}
          >
            ${data.total_cost_estimate.toFixed(3)}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-3 space-y-3">
        {/* Stats row */}
        <div className="grid grid-cols-3 gap-2 text-center">
          <div>
            <div className="text-xs text-muted-foreground flex items-center justify-center gap-1">
              <ArrowUpRight className="h-3 w-3" /> In
            </div>
            <div className="text-sm font-mono font-medium">
              {formatTokens(data.total_input_tokens)}
            </div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground flex items-center justify-center gap-1">
              <ArrowDownRight className="h-3 w-3" /> Out
            </div>
            <div className="text-sm font-mono font-medium">
              {formatTokens(data.total_output_tokens)}
            </div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground flex items-center justify-center gap-1">
              <Zap className="h-3 w-3" /> Calls
            </div>
            <div className="text-sm font-mono font-medium">
              {data.call_count}
            </div>
          </div>
        </div>

        {/* Model breakdown */}
        {models.length > 0 && (
          <div className="space-y-1.5">
            <div className="text-xs text-muted-foreground font-medium">By Model</div>
            {models.map(([model, usage]) => {
              const shortName = model.includes("haiku") ? "Haiku" :
                model.includes("sonnet") ? "Sonnet" :
                model.includes("gpt-4.1-mini") ? "GPT-4.1m" : model.slice(0, 12);
              const totalTokens = usage.input + usage.output;
              const maxTokens = Math.max(...models.map(([, u]) => u.input + u.output));
              const pct = maxTokens > 0 ? (totalTokens / maxTokens) * 100 : 0;
              return (
                <div key={model} className="space-y-0.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground">{shortName}</span>
                    <span className="font-mono">
                      {formatTokens(totalTokens)} · ${usage.cost.toFixed(3)} · {usage.calls}x
                    </span>
                  </div>
                  <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                    <div
                      className="h-full rounded-full bg-yellow-500/70"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Agent breakdown */}
        {agents.length > 0 && (
          <div className="space-y-1">
            <div className="text-xs text-muted-foreground font-medium">By Agent</div>
            <div className="flex flex-wrap gap-1.5">
              {agents.map(([agent, usage]) => (
                <Badge key={agent} variant="secondary" className="text-xs font-mono">
                  {agent}: {usage.calls}x
                </Badge>
              ))}
            </div>
          </div>
        )}

        {/* Hourly sparkline */}
        {data.by_hour.length > 0 && (
          <div className="space-y-1">
            <div className="text-xs text-muted-foreground font-medium">Hourly</div>
            <div className="flex items-end gap-px h-8">
              {data.by_hour.map((h) => {
                const total = h.input + h.output;
                const pct = maxHourTokens > 0 ? (total / maxHourTokens) * 100 : 0;
                return (
                  <div
                    key={h.hour}
                    className="flex-1 bg-yellow-500/50 rounded-t-sm min-w-[3px] hover:bg-yellow-500/80 transition-colors"
                    style={{ height: `${Math.max(pct, 4)}%` }}
                    title={`${h.hour}:00 - ${formatTokens(total)} tokens, ${h.calls} calls`}
                  />
                );
              })}
            </div>
            <div className="flex justify-between text-[10px] text-muted-foreground">
              <span>{data.by_hour[0]?.hour}:00</span>
              <span>{data.by_hour[data.by_hour.length - 1]?.hour}:00</span>
            </div>
          </div>
        )}

        {data.call_count === 0 && (
          <p className="text-xs text-muted-foreground text-center py-2">
            No LLM calls today
          </p>
        )}
      </CardContent>
    </Card>
  );
}

export const TokenMonitor = memo(TokenMonitorInner);
