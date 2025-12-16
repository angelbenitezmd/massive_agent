# Visual Layout Editor Guide

## Overview

The Visual Layout Editor allows you to customize your dashboard layout by:
- **Dragging and dropping** components to rearrange them
- **Showing/hiding** components
- **Adding new** components from a palette
- **Saving** your custom layout to localStorage

## How to Access

1. Look for the **Layout** icon (📐) in the header, next to the Settings button
2. Click it to open the Layout Editor dialog

## Features

### Drag and Drop
- Click and hold the **grip icon** (⋮⋮) on any component
- Drag it up or down to reorder
- Release to drop in the new position

### Toggle Visibility
- Click the **eye icon** (👁️) to show/hide a component
- Hidden components appear in a separate "Hidden Components" section
- Click the eye icon again to make them visible

### Add Components
- Use the "Add Components" section at the top
- Click any available component to add it to your dashboard
- Components already in use won't appear in this list

### Remove Components
- Click the **X icon** on any component to remove it
- You can always add it back later from the component palette

### Save Layout
- Click **"Save Layout"** to persist your changes
- Your layout is saved to browser localStorage
- It will be restored when you reload the page

### Reset to Default
- Click **"Reset to Default"** to restore the original layout
- This removes your custom layout from localStorage

## Available Components

- **Market Status** - Market open/close status
- **Today's Summary** - Daily trading summary
- **AI Trade Decisions** - AI-generated trade signals
- **Global News Feed** - Market-wide news
- **Ticker News Feed** - Ticker-specific news
- **Scanner Panel** - Stock scanner
- **AI Agents Panel** - AI agent analysis
- **Market Snapshot** - Price chart and technicals
- **Deep Analysis** - Deep AI analysis
- **Trade Decision** - Trade decision panel
- **Manual Trade** - Manual trade execution
- **Portfolio Heatmap** - Portfolio visualization
- **Portfolio Chart** - Portfolio performance chart
- **Trade Journal** - Trade history
- **Analyst Ratings** - Analyst rating changes
- **Activity Log** - System activity log
- **Earnings Panel** - Earnings calendar
- **Performance Stats** - Performance metrics
- **Market Movers** - Top movers
- **Risk Panel** - Risk management

## Tips

1. **Start Simple**: Hide components you don't use often
2. **Group Related**: Arrange related components together
3. **Save Often**: Save your layout after making changes
4. **Experiment**: Try different arrangements to find what works best

## Technical Details

- Layouts are stored in `localStorage` under the key `dashboard-layout`
- The layout persists across browser sessions
- Each component has an `id`, `component` name, `visible` flag, and `order` number
- The editor uses `@dnd-kit` for drag-and-drop functionality
