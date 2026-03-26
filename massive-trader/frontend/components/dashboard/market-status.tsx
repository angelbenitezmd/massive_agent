"use client";

import { memo, useEffect, useState } from "react";
import { Clock, Sun, Moon, Sunrise, Sunset } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type MarketSession = "pre-market" | "market-open" | "after-hours" | "market-closed";

function getMarketSession(): { session: MarketSession; nextEvent: string; timeUntil: string } {
  const now = new Date();
  const nyTime = new Date(now.toLocaleString("en-US", { timeZone: "America/New_York" }));
  const hours = nyTime.getHours();
  const minutes = nyTime.getMinutes();
  const day = nyTime.getDay();
  const currentMinutes = hours * 60 + minutes;

  // Weekend check
  if (day === 0 || day === 6) {
    return {
      session: "market-closed",
      nextEvent: "Market opens Monday",
      timeUntil: day === 0 ? "~1 day" : "~2 days",
    };
  }

  // Pre-market: 4:00 AM - 9:30 AM ET
  const preMarketStart = 4 * 60; // 4:00 AM
  const marketOpen = 9 * 60 + 30; // 9:30 AM
  const marketClose = 16 * 60; // 4:00 PM
  const afterHoursEnd = 20 * 60; // 8:00 PM

  if (currentMinutes >= preMarketStart && currentMinutes < marketOpen) {
    const minsUntil = marketOpen - currentMinutes;
    return {
      session: "pre-market",
      nextEvent: "Market opens",
      timeUntil: `${Math.floor(minsUntil / 60)}h ${minsUntil % 60}m`,
    };
  }

  if (currentMinutes >= marketOpen && currentMinutes < marketClose) {
    const minsUntil = marketClose - currentMinutes;
    return {
      session: "market-open",
      nextEvent: "Market closes",
      timeUntil: `${Math.floor(minsUntil / 60)}h ${minsUntil % 60}m`,
    };
  }

  if (currentMinutes >= marketClose && currentMinutes < afterHoursEnd) {
    const minsUntil = afterHoursEnd - currentMinutes;
    return {
      session: "after-hours",
      nextEvent: "After-hours ends",
      timeUntil: `${Math.floor(minsUntil / 60)}h ${minsUntil % 60}m`,
    };
  }

  // Market closed (before pre-market or after after-hours)
  if (currentMinutes < preMarketStart) {
    const minsUntil = preMarketStart - currentMinutes;
    return {
      session: "market-closed",
      nextEvent: "Pre-market opens",
      timeUntil: `${Math.floor(minsUntil / 60)}h ${minsUntil % 60}m`,
    };
  }

  return {
    session: "market-closed",
    nextEvent: "Pre-market tomorrow",
    timeUntil: "~8h",
  };
}

const sessionConfig: Record<MarketSession, { icon: typeof Sun; color: string; bg: string; label: string }> = {
  "pre-market": {
    icon: Sunrise,
    color: "text-orange-500",
    bg: "bg-orange-500/20",
    label: "Pre-Market",
  },
  "market-open": {
    icon: Sun,
    color: "text-green-500",
    bg: "bg-green-500/20",
    label: "Market Open",
  },
  "after-hours": {
    icon: Sunset,
    color: "text-purple-500",
    bg: "bg-purple-500/20",
    label: "After-Hours",
  },
  "market-closed": {
    icon: Moon,
    color: "text-gray-500",
    bg: "bg-gray-500/20",
    label: "Market Closed",
  },
};

export const MarketStatus = memo(function MarketStatus() {
  const [status, setStatus] = useState(getMarketSession());
  const [currentTime, setCurrentTime] = useState<string>("");

  useEffect(() => {
    const updateStatus = () => {
      setStatus(getMarketSession());
      const now = new Date();
      setCurrentTime(
        now.toLocaleTimeString("en-US", {
          timeZone: "America/New_York",
          hour: "2-digit",
          minute: "2-digit",
        })
      );
    };

    updateStatus();
    const interval = setInterval(updateStatus, 10000);
    return () => clearInterval(interval);
  }, []);

  const config = sessionConfig[status.session];
  const Icon = config.icon;

  return (
    <div className={cn("flex items-center gap-3 px-3 py-2 rounded-lg", config.bg)}>
      <div className="flex items-center gap-2">
        <Icon className={cn("h-4 w-4", config.color)} />
        <span className={cn("font-semibold text-sm", config.color)}>{config.label}</span>
      </div>
      <div className="h-4 w-px bg-border" />
      <div className="flex items-center gap-1 text-xs text-muted-foreground">
        <Clock className="h-3 w-3" />
        <span>{currentTime} ET</span>
      </div>
      <div className="h-4 w-px bg-border" />
      <div className="text-xs">
        <span className="text-muted-foreground">{status.nextEvent}: </span>
        <span className="font-medium">{status.timeUntil}</span>
      </div>
    </div>
  );
});
