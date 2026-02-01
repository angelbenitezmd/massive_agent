"use client";

import { useState, useEffect, useCallback } from "react";
import type { LayoutItem } from "@/components/dashboard/layout-editor";

const DEFAULT_LAYOUT: LayoutItem[] = [
  { id: "market-status", component: "Market Status", visible: true, order: 0 },
  { id: "todays-summary", component: "Today's Summary", visible: true, order: 1 },
  { id: "trade-signals", component: "AI Trade Decisions", visible: true, order: 2 },
  { id: "news-feed-global", component: "Global News Feed", visible: true, order: 3 },
  { id: "news-feed-ticker", component: "Ticker News Feed", visible: true, order: 4 },
  { id: "scanner", component: "Scanner Panel", visible: true, order: 5 },
  { id: "ai-agents", component: "AI Agents Panel", visible: true, order: 6 },
  { id: "market-snapshot", component: "Market Snapshot", visible: true, order: 7, colSpan: 2 },
  { id: "deep-analysis", component: "Deep Analysis", visible: true, order: 8 },
  { id: "trade-decision", component: "Trade Decision", visible: true, order: 9 },
  { id: "manual-trade", component: "Manual Trade", visible: true, order: 10 },
  { id: "portfolio-heatmap", component: "Portfolio Heatmap", visible: true, order: 11 },
  { id: "portfolio-chart", component: "Portfolio Chart", visible: true, order: 12 },
  { id: "trade-journal", component: "Trade Journal", visible: true, order: 13 },
  { id: "analyst-ratings", component: "Analyst Ratings", visible: true, order: 14 },
  { id: "activity-log", component: "Activity Log", visible: true, order: 15 },
  { id: "earnings", component: "Earnings Panel", visible: true, order: 16 },
  { id: "performance", component: "Performance Stats", visible: true, order: 17 },
  { id: "market-movers", component: "Market Movers", visible: true, order: 18 },
  { id: "risk-panel", component: "Risk Panel", visible: true, order: 19 },
];

const STORAGE_KEY = "dashboard-layout";

export function useDashboardLayout() {
  const [layout, setLayout] = useState<LayoutItem[]>(DEFAULT_LAYOUT);
  const [isLoaded, setIsLoaded] = useState(false);

  // Load layout from localStorage on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        // Merge with defaults to handle new components
        const merged = [...DEFAULT_LAYOUT];
        parsed.forEach((savedItem: LayoutItem) => {
          const index = merged.findIndex((item) => item.id === savedItem.id);
          if (index >= 0) {
            merged[index] = { ...merged[index], ...savedItem };
          }
        });
        setLayout(merged);
      }
    } catch (error) {
      console.error("Failed to load layout:", error);
    } finally {
      setIsLoaded(true);
    }
  }, []);

  // Save layout to localStorage
  const saveLayout = useCallback((newLayout: LayoutItem[]) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(newLayout));
      setLayout(newLayout);
    } catch (error) {
      console.error("Failed to save layout:", error);
    }
  }, []);

  // Reset to default layout
  const resetLayout = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setLayout(DEFAULT_LAYOUT);
  }, []);

  // Get visible components in order
  const getVisibleComponents = useCallback(() => {
    return layout
      .filter((item) => item.visible)
      .sort((a, b) => a.order - b.order);
  }, [layout]);

  // Check if component is visible
  const isComponentVisible = useCallback(
    (componentId: string) => {
      const item = layout.find((item) => item.id === componentId);
      return item?.visible ?? true;
    },
    [layout]
  );

  return {
    layout,
    isLoaded,
    saveLayout,
    resetLayout,
    getVisibleComponents,
    isComponentVisible,
  };
}

