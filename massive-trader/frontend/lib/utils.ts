import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatPercent(value: number): string {
  const sign = value >= 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

export function formatNumber(value: number, decimals: number = 2): string {
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

export function formatVolume(value: number): string {
  if (value >= 1_000_000_000) {
    return `${(value / 1_000_000_000).toFixed(2)}B`;
  }
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(2)}M`;
  }
  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(2)}K`;
  }
  return value.toString();
}

export function formatRelativeTime(date: Date | string | undefined | null): string {
  if (!date) return "Unknown";

  const now = new Date();
  const then = new Date(date);

  // Check for invalid date
  if (isNaN(then.getTime())) return "Unknown";

  const seconds = Math.floor((now.getTime() - then.getTime()) / 1000);

  if (seconds < 0) return "just now"; // Future dates
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;

  return then.toLocaleDateString();
}

export function getDirectionColor(direction: string): string {
  switch (direction.toLowerCase()) {
    case "bullish":
    case "buy":
      return "text-green-500";
    case "bearish":
    case "sell":
      return "text-red-500";
    default:
      return "text-yellow-500";
  }
}

export function getDirectionBgColor(direction: string): string {
  switch (direction.toLowerCase()) {
    case "bullish":
    case "buy":
      return "bg-green-500/10 text-green-500 border-green-500/20";
    case "bearish":
    case "sell":
      return "bg-red-500/10 text-red-500 border-red-500/20";
    default:
      return "bg-yellow-500/10 text-yellow-500 border-yellow-500/20";
  }
}

export function getCircuitBreakerColor(level: string): string {
  switch (level.toUpperCase()) {
    case "GREEN":
      return "bg-green-500";
    case "YELLOW":
      return "bg-yellow-500";
    case "ORANGE":
      return "bg-orange-500";
    case "RED":
      return "bg-red-500";
    default:
      return "bg-gray-500";
  }
}
