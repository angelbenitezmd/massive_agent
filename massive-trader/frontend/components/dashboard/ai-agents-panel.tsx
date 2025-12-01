"use client";

import {
  Brain,
  Newspaper,
  DollarSign,
  TrendingUp,
  ChevronRight,
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
import { cn, getDirectionBgColor } from "@/lib/utils";
import type { AgentSignal, Direction } from "@/types";

interface AIAgentsPanelProps {
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
      <div className="p-4 rounded-lg bg-secondary/30 space-y-3">
        <div className="flex items-center gap-2">
          <Icon className="h-5 w-5 text-muted-foreground" />
          <span className="font-medium">{title}</span>
        </div>
        <p className="text-sm text-muted-foreground">Awaiting analysis...</p>
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
    <div className="p-4 rounded-lg bg-secondary/30 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Icon className="h-5 w-5 text-primary" />
          <span className="font-medium">{title}</span>
        </div>
        <Badge className={cn("capitalize", getDirectionBgColor(agent.direction))}>
          {getDirectionIcon(agent.direction)}
          <span className="ml-1">{agent.direction}</span>
        </Badge>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">Confidence</span>
          <span className="font-medium">
            {Math.round(agent.confidence * 100)}%
          </span>
        </div>
        <Progress
          value={agent.confidence * 100}
          className={cn(
            "h-2",
            agent.direction === "bullish" && "[&>div]:bg-green-500",
            agent.direction === "bearish" && "[&>div]:bg-red-500",
            agent.direction === "neutral" && "[&>div]:bg-yellow-500"
          )}
        />
      </div>

      <p className="text-sm text-muted-foreground line-clamp-3">
        {agent.reasoning}
      </p>
    </div>
  );
}

export function AIAgentsPanel({
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
    <Card className="card-hover">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2">
          <Brain className="h-5 w-5 text-primary" />
          AI Agents Analysis
        </CardTitle>
        <CardDescription>
          Multi-agent consensus for trading decisions
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <AgentCard
          agent={newsAgent}
          icon={Newspaper}
          title="News/Sentiment Agent"
        />
        <AgentCard
          agent={earningsAgent}
          icon={DollarSign}
          title="Earnings Agent"
        />
        <AgentCard
          agent={technicalAgent}
          icon={TrendingUp}
          title="Technical Momentum Agent"
        />
      </CardContent>
    </Card>
  );
}
