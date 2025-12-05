"use client";

import {
  Brain,
  Newspaper,
  DollarSign,
  TrendingUp,
  ChevronRight,
  Info,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn, getDirectionBgColor } from "@/lib/utils";
import type { AgentSignal, Direction } from "@/types";

interface AIAgentsPanelProps {
  ticker?: string;
  newsAgent: AgentSignal | undefined;
  earningsAgent: AgentSignal | undefined;
  technicalAgent: AgentSignal | undefined;
  isLoading: boolean;
}

function AgentCard({
  agent,
  icon: Icon,
  title,
}: {
  agent: AgentSignal | undefined;
  icon: React.ElementType;
  title: string;
}) {
  if (!agent) {
    return (
      <div className="p-3 rounded-lg bg-secondary/30 space-y-1">
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-muted-foreground" />
          <span className="font-medium text-sm">{title}</span>
        </div>
        <p className="text-xs text-muted-foreground">Awaiting analysis...</p>
      </div>
    );
  }

  const getDirectionIcon = (direction: Direction) => {
    switch (direction) {
      case "bullish":
        return <TrendingUp className="h-4 w-4" />;
      case "bearish":
        return <TrendingUp className="h-4 w-4 rotate-180" />;
      default:
        return <ChevronRight className="h-4 w-4" />;
    }
  };

  return (
    <div className="p-3 rounded-lg bg-secondary/30 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-primary" />
          <span className="font-medium text-sm">{title}</span>
        </div>
        <Badge className={cn("capitalize text-xs", getDirectionBgColor(agent.direction))}>
          {getDirectionIcon(agent.direction)}
          <span className="ml-1">{agent.direction}</span>
        </Badge>
      </div>

      <div className="flex items-center gap-2">
        <Progress
          value={agent.confidence * 100}
          className={cn(
            "h-1.5 flex-1",
            agent.direction === "bullish" && "[&>div]:bg-green-500",
            agent.direction === "bearish" && "[&>div]:bg-red-500",
            agent.direction === "neutral" && "[&>div]:bg-yellow-500"
          )}
        />
        <span className="text-xs font-medium w-8">
          {Math.round(agent.confidence * 100)}%
        </span>
      </div>

      <p className="text-xs text-muted-foreground line-clamp-2">
        {agent.reasoning}
      </p>
    </div>
  );
}

export function AIAgentsPanel({
  ticker,
  newsAgent,
  earningsAgent,
  technicalAgent,
  isLoading,
}: AIAgentsPanelProps) {
  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Brain className="h-5 w-5" />
            AI Agents
            {ticker && <Badge variant="outline" className="text-[10px] font-bold">{ticker}</Badge>}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="animate-pulse">
                <div className="h-32 bg-secondary rounded-lg" />
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
            <Brain className="h-5 w-5 text-primary" />
            AI Agents Analysis
            {ticker && <Badge variant="outline" className="text-[10px] font-bold">{ticker}</Badge>}
            <Tooltip>
              <TooltipTrigger asChild>
                <Info className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground cursor-help" />
              </TooltipTrigger>
              <TooltipContent side="bottom" className="max-w-[300px] p-3">
                <div className="space-y-2 text-xs">
                  <p className="font-semibold">AI Agents Explained</p>
                  <div className="space-y-1.5">
                    <p><strong>News Agent:</strong> Analyzes recent headlines and sentiment from financial news sources.</p>
                    <p><strong>Earnings Agent:</strong> Evaluates earnings reports, surprises, and forward guidance.</p>
                    <p><strong>Technical Agent:</strong> Uses RSI, MACD, and moving averages to assess momentum.</p>
                  </div>
                  <div className="pt-1 border-t border-border">
                    <p className="text-muted-foreground">Each agent votes bullish, bearish, or neutral. Confidence shows how certain the agent is.</p>
                  </div>
                </div>
              </TooltipContent>
            </Tooltip>
          </CardTitle>
          <CardDescription>
            Multi-agent consensus for trading decisions
          </CardDescription>
        </CardHeader>
      <CardContent className="space-y-2 pt-0">
        <AgentCard
          agent={newsAgent}
          icon={Newspaper}
          title="News Agent"
        />
        <AgentCard
          agent={earningsAgent}
          icon={DollarSign}
          title="Earnings Agent"
        />
        <AgentCard
          agent={technicalAgent}
          icon={TrendingUp}
          title="Technical Agent"
        />
      </CardContent>
      </Card>
    </TooltipProvider>
  );
}
