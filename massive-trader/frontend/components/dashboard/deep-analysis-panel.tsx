"use client";

import { memo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Brain,
  Sparkles,
  TrendingUp,
  TrendingDown,
  Target,
  AlertTriangle,
  Loader2,
  ChevronDown,
  ChevronUp,
  Newspaper,
  BarChart3,
  Lightbulb,
  Info,
} from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface DeepAnalysisResult {
  ticker: string;
  timestamp: string;
  current_price: number;
  final_action: string;
  final_score: number;
  confidence: number;
  agents: {
    news: {
      sentiment: string;
      score: number;
      confidence: number;
      summary?: string;
      catalysts?: string[];
      risks?: string[];
      provider?: string;
    };
    technical: {
      trend: string;
      score: number;
      confidence: number;
      support_levels?: number[];
      resistance_levels?: number[];
      stop_loss?: number;
      target_1?: number;
      target_2?: number;
      summary?: string;
      provider?: string;
    };
  };
  synthesis: {
    action: string;
    conviction: number;
    score: number;
    thesis?: string;
    bull_case?: string;
    bear_case?: string;
    key_risks?: string[];
    catalysts?: string[];
    position_recommendation?: {
      size_percent: number;
      shares: number;
    };
    risk_management?: {
      stop_loss: number;
      take_profit_1: number;
      take_profit_2: number;
      risk_reward_ratio: number;
    };
    provider?: string;
  };
  error?: string;
}

interface DeepAnalysisPanelProps {
  ticker: string;
  result?: DeepAnalysisResult | null;
  isLoading?: boolean;
  onRunAnalysis?: () => void;
}

function getActionColor(action: string): string {
  const a = action?.toUpperCase() || "";
  if (a.includes("STRONG_BUY")) return "text-green-400 bg-green-500/20";
  if (a.includes("BUY")) return "text-green-500 bg-green-500/10";
  if (a.includes("STRONG_SELL")) return "text-red-400 bg-red-500/20";
  if (a.includes("SELL")) return "text-red-500 bg-red-500/10";
  if (a.includes("AVOID")) return "text-orange-500 bg-orange-500/10";
  return "text-yellow-500 bg-yellow-500/10";
}

function getScoreColor(score: number): string {
  if (score >= 70) return "text-green-500";
  if (score >= 60) return "text-green-400";
  if (score <= 30) return "text-red-500";
  if (score <= 40) return "text-red-400";
  return "text-yellow-500";
}

export const DeepAnalysisPanel = memo(function DeepAnalysisPanel({
  ticker,
  result,
  isLoading,
  onRunAnalysis,
}: DeepAnalysisPanelProps) {
  const [expanded, setExpanded] = useState(false);

  const hasResult = result && !result.error;
  const isStaleResult = hasResult && result.ticker && result.ticker !== ticker;

  return (
    <TooltipProvider>
    <Card className="bg-card border-border">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-base">
            <Brain className="h-4 w-4 text-purple-500" />
            Deep AI Analysis
            <Tooltip>
              <TooltipTrigger asChild>
                <Info className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground cursor-help" />
              </TooltipTrigger>
              <TooltipContent side="bottom" className="max-w-[280px] p-3">
                <div className="space-y-2 text-xs">
                  <p className="font-semibold">Deep AI Analysis</p>
                  <p>Advanced multi-model analysis using Claude + GPT for comprehensive stock evaluation.</p>
                  <p className="text-muted-foreground">Includes news sentiment, technical analysis, trade setup with targets and stop loss.</p>
                </div>
              </TooltipContent>
            </Tooltip>
            <Badge variant="outline" className="text-[10px] font-bold">
              {ticker}
            </Badge>
            <Badge variant="secondary" className="text-[10px] bg-purple-500/20 text-purple-400">
              Claude + GPT
            </Badge>
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={onRunAnalysis}
            disabled={isLoading}
            className="h-7 text-xs"
          >
            {isLoading ? (
              <>
                <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                Analyzing {ticker}...
              </>
            ) : (
              <>
                <Sparkles className="h-3 w-3 mr-1" />
                Analyze {ticker}
              </>
            )}
          </Button>
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        {isStaleResult && (
          <div className="mb-3 p-2 bg-yellow-500/10 border border-yellow-500/30 rounded-lg text-xs text-yellow-600 flex items-center gap-2">
            <AlertTriangle className="h-3 w-3" />
            Result is for {result.ticker}, not {ticker}. Run analysis again for updated data.
          </div>
        )}
        {(!hasResult || isStaleResult) && !isLoading ? (
          <div className="flex flex-col items-center justify-center py-4 text-muted-foreground">
            <Brain className="h-8 w-8 mb-2 opacity-30" />
            <p className="text-xs">Click &quot;Analyze {ticker}&quot; to get AI insights</p>
            <p className="text-[10px] mt-0.5 text-muted-foreground/70">Uses Claude for news & OpenAI for technicals</p>
          </div>
        ) : isLoading ? (
          <div className="flex flex-col items-center justify-center py-4">
            <Loader2 className="h-6 w-6 animate-spin text-purple-500 mb-2" />
            <p className="text-xs text-muted-foreground">Running multi-agent analysis...</p>
            <p className="text-[10px] text-muted-foreground/70 mt-0.5">This may take 10-20 seconds</p>
          </div>
        ) : hasResult ? (
          <div className="space-y-4">
            {/* Final Decision */}
            <div className={`rounded-lg p-4 ${getActionColor(result.final_action)}`}>
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-xs uppercase tracking-wide opacity-70">AI Recommendation</div>
                  <div className="text-2xl font-bold">{result.final_action}</div>
                </div>
                <div className="text-right">
                  <div className="text-xs opacity-70">Score</div>
                  <div className={`text-3xl font-bold ${getScoreColor(result.final_score)}`}>
                    {result.final_score}
                  </div>
                </div>
              </div>
              {result.synthesis?.thesis && (
                <p className="text-sm mt-3 opacity-90">{result.synthesis.thesis}</p>
              )}
            </div>

            {/* Agent Summaries */}
            <div className="grid grid-cols-2 gap-3">
              {/* News Agent */}
              <div className="bg-muted/30 rounded-lg p-3">
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-2">
                  <Newspaper className="h-3 w-3" />
                  News Analysis
                  {result.agents?.news?.provider && (
                    <Badge variant="outline" className="text-[9px] px-1 py-0">
                      {result.agents.news.provider}
                    </Badge>
                  )}
                </div>
                <div className="flex items-center justify-between">
                  <span className={`font-medium capitalize ${
                    result.agents?.news?.sentiment === "bullish" ? "text-green-500" :
                    result.agents?.news?.sentiment === "bearish" ? "text-red-500" :
                    "text-yellow-500"
                  }`}>
                    {result.agents?.news?.sentiment || "neutral"}
                  </span>
                  <span className={`font-bold ${getScoreColor(result.agents?.news?.score || 50)}`}>
                    {result.agents?.news?.score || 50}
                  </span>
                </div>
              </div>

              {/* Technical Agent */}
              <div className="bg-muted/30 rounded-lg p-3">
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-2">
                  <BarChart3 className="h-3 w-3" />
                  Technical Analysis
                  {result.agents?.technical?.provider && (
                    <Badge variant="outline" className="text-[9px] px-1 py-0">
                      {result.agents.technical.provider}
                    </Badge>
                  )}
                </div>
                <div className="flex items-center justify-between">
                  <span className={`font-medium capitalize ${
                    result.agents?.technical?.trend === "bullish" ? "text-green-500" :
                    result.agents?.technical?.trend === "bearish" ? "text-red-500" :
                    "text-yellow-500"
                  }`}>
                    {result.agents?.technical?.trend || "neutral"}
                  </span>
                  <span className={`font-bold ${getScoreColor(result.agents?.technical?.score || 50)}`}>
                    {result.agents?.technical?.score || 50}
                  </span>
                </div>
              </div>
            </div>

            {/* Expand/Collapse for Details */}
            <Button
              variant="ghost"
              size="sm"
              className="w-full text-xs"
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? (
                <>
                  <ChevronUp className="h-3 w-3 mr-1" />
                  Hide Details
                </>
              ) : (
                <>
                  <ChevronDown className="h-3 w-3 mr-1" />
                  Show Details
                </>
              )}
            </Button>

            {expanded && (
              <ScrollArea className="h-[150px]">
                <div className="space-y-4 pr-3">
                  {/* Risk Management */}
                  {result.synthesis?.risk_management && (
                    <div className="bg-muted/20 rounded-lg p-3">
                      <div className="flex items-center gap-1.5 text-xs font-medium mb-2">
                        <Target className="h-3 w-3 text-blue-500" />
                        Trade Setup
                      </div>
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        <div>
                          <span className="text-muted-foreground">Stop Loss:</span>
                          <span className="ml-1 text-red-500 font-medium">
                            ${result.synthesis.risk_management.stop_loss?.toFixed(2)}
                          </span>
                        </div>
                        <div>
                          <span className="text-muted-foreground">Target 1:</span>
                          <span className="ml-1 text-green-500 font-medium">
                            ${result.synthesis.risk_management.take_profit_1?.toFixed(2)}
                          </span>
                        </div>
                        <div>
                          <span className="text-muted-foreground">Target 2:</span>
                          <span className="ml-1 text-green-500 font-medium">
                            ${result.synthesis.risk_management.take_profit_2?.toFixed(2)}
                          </span>
                        </div>
                        <div>
                          <span className="text-muted-foreground">R:R Ratio:</span>
                          <span className="ml-1 font-medium">
                            {result.synthesis.risk_management.risk_reward_ratio?.toFixed(1)}:1
                          </span>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Bull/Bear Case */}
                  {(result.synthesis?.bull_case || result.synthesis?.bear_case) && (
                    <div className="space-y-2">
                      {result.synthesis.bull_case && (
                        <div className="bg-green-500/10 rounded-lg p-3">
                          <div className="flex items-center gap-1.5 text-xs font-medium text-green-500 mb-1">
                            <TrendingUp className="h-3 w-3" />
                            Bull Case
                          </div>
                          <p className="text-xs text-muted-foreground">{result.synthesis.bull_case}</p>
                        </div>
                      )}
                      {result.synthesis.bear_case && (
                        <div className="bg-red-500/10 rounded-lg p-3">
                          <div className="flex items-center gap-1.5 text-xs font-medium text-red-500 mb-1">
                            <TrendingDown className="h-3 w-3" />
                            Bear Case
                          </div>
                          <p className="text-xs text-muted-foreground">{result.synthesis.bear_case}</p>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Catalysts */}
                  {result.synthesis?.catalysts && result.synthesis.catalysts.length > 0 && (
                    <div className="bg-muted/20 rounded-lg p-3">
                      <div className="flex items-center gap-1.5 text-xs font-medium mb-2">
                        <Lightbulb className="h-3 w-3 text-yellow-500" />
                        Catalysts
                      </div>
                      <ul className="text-xs text-muted-foreground space-y-1">
                        {result.synthesis.catalysts.slice(0, 4).map((catalyst, i) => (
                          <li key={i} className="flex items-start gap-1">
                            <span className="text-yellow-500">•</span>
                            {catalyst}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Key Risks */}
                  {result.synthesis?.key_risks && result.synthesis.key_risks.length > 0 && (
                    <div className="bg-muted/20 rounded-lg p-3">
                      <div className="flex items-center gap-1.5 text-xs font-medium mb-2">
                        <AlertTriangle className="h-3 w-3 text-orange-500" />
                        Key Risks
                      </div>
                      <ul className="text-xs text-muted-foreground space-y-1">
                        {result.synthesis.key_risks.slice(0, 4).map((risk, i) => (
                          <li key={i} className="flex items-start gap-1">
                            <span className="text-orange-500">•</span>
                            {risk}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* News Summary */}
                  {result.agents?.news?.summary && (
                    <div className="bg-muted/20 rounded-lg p-3">
                      <div className="flex items-center gap-1.5 text-xs font-medium mb-2">
                        <Newspaper className="h-3 w-3" />
                        News Summary
                      </div>
                      <p className="text-xs text-muted-foreground">{result.agents.news.summary}</p>
                    </div>
                  )}

                  {/* Technical Summary */}
                  {result.agents?.technical?.summary && (
                    <div className="bg-muted/20 rounded-lg p-3">
                      <div className="flex items-center gap-1.5 text-xs font-medium mb-2">
                        <BarChart3 className="h-3 w-3" />
                        Technical Summary
                      </div>
                      <p className="text-xs text-muted-foreground">{result.agents.technical.summary}</p>
                    </div>
                  )}
                </div>
              </ScrollArea>
            )}
          </div>
        ) : result?.error ? (
          <div className="flex flex-col items-center justify-center py-6 text-red-500">
            <AlertTriangle className="h-8 w-8 mb-2" />
            <p className="text-sm">Analysis failed</p>
            <p className="text-xs text-muted-foreground mt-1">{result.error}</p>
          </div>
        ) : null}
      </CardContent>
    </Card>
    </TooltipProvider>
  );
});
