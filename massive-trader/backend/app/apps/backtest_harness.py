"""CSV-based backtest harness for baseline vs strict gating policies.

Input CSV columns expected:
- timestamp (ISO8601 or YYYY-MM-DD HH:MM:SS)
- price
- ai_score
- momentum_score
- combined_score
- price_change_pct
- momentum_warning (optional, true/false)
"""
from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Tuple

from app.services.trade_policy import evaluate_buy_gate


@dataclass
class SignalRow:
    ts: datetime
    price: float
    ai_score: float
    momentum_score: float
    combined_score: float
    price_change_pct: float
    momentum_warning: bool = False


@dataclass
class Trade:
    entry_ts: datetime
    exit_ts: datetime
    entry_price: float
    exit_price: float
    pnl_pct: float


def parse_csv(path: str) -> List[SignalRow]:
    rows: List[SignalRow] = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            rows.append(
                SignalRow(
                    ts=datetime.fromisoformat(raw["timestamp"].replace("Z", "+00:00")),
                    price=float(raw["price"]),
                    ai_score=float(raw["ai_score"]),
                    momentum_score=float(raw["momentum_score"]),
                    combined_score=float(raw["combined_score"]),
                    price_change_pct=float(raw.get("price_change_pct", 0) or 0),
                    momentum_warning=str(raw.get("momentum_warning", "false")).lower() == "true",
                )
            )
    return sorted(rows, key=lambda r: r.ts)


def should_buy_baseline(row: SignalRow) -> bool:
    return row.combined_score >= 70


def should_buy_strict(row: SignalRow) -> bool:
    gate = evaluate_buy_gate(
        combined_score=row.combined_score,
        ai_score=row.ai_score,
        momentum_score=row.momentum_score,
        price_change_pct=row.price_change_pct,
        momentum_warning=row.momentum_warning,
    )
    return gate["passed"]


def run_policy_backtest(
    rows: List[SignalRow],
    policy_name: str,
    decision_fn,
    hold_bars: int = 12,
    stop_loss_pct: float = 0.015,
    take_profit_pct: float = 0.03,
) -> Dict[str, float]:
    trades: List[Trade] = []
    i = 0
    while i < len(rows) - 1:
        row = rows[i]
        if not decision_fn(row):
            i += 1
            continue

        entry = row.price
        entry_ts = row.ts
        exit_price = entry
        exit_ts = entry_ts

        max_idx = min(i + hold_bars, len(rows) - 1)
        for j in range(i + 1, max_idx + 1):
            px = rows[j].price
            pnl_pct = (px - entry) / entry
            if pnl_pct <= -stop_loss_pct or pnl_pct >= take_profit_pct or j == max_idx:
                exit_price = px
                exit_ts = rows[j].ts
                break

        pnl_pct = (exit_price - entry) / entry
        trades.append(
            Trade(
                entry_ts=entry_ts,
                exit_ts=exit_ts,
                entry_price=entry,
                exit_price=exit_price,
                pnl_pct=pnl_pct,
            )
        )
        i = min(i + hold_bars, len(rows) - 1)

    return compute_metrics(trades, rows, policy_name)


def compute_metrics(trades: List[Trade], rows: List[SignalRow], policy_name: str) -> Dict[str, float]:
    if not rows:
        raise ValueError("No rows available for metrics")
    if not trades:
        return {
            "policy": policy_name,
            "trade_count": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 0.0,
            "sharpe": 0.0,
            "trade_frequency_per_day": 0.0,
            "net_return_pct": 0.0,
        }

    returns = [t.pnl_pct for t in trades]
    wins = [r for r in returns if r > 0]
    losses = [abs(r) for r in returns if r < 0]

    win_rate = len(wins) / len(trades)
    profit_factor = (sum(wins) / sum(losses)) if losses else float("inf")

    # Equity curve for max drawdown
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in returns:
        equity *= (1 + r)
        peak = max(peak, equity)
        dd = (peak - equity) / peak
        max_dd = max(max_dd, dd)

    mean_ret = sum(returns) / len(returns)
    variance = sum((r - mean_ret) ** 2 for r in returns) / max(len(returns) - 1, 1)
    std_ret = math.sqrt(variance)
    sharpe = (mean_ret / std_ret) * math.sqrt(252) if std_ret > 0 else 0.0

    days = max((rows[-1].ts - rows[0].ts).days, 1)
    trade_frequency = len(trades) / days

    return {
        "policy": policy_name,
        "trade_count": len(trades),
        "win_rate": round(win_rate * 100, 2),
        "profit_factor": round(profit_factor, 3) if math.isfinite(profit_factor) else 999.0,
        "max_drawdown": round(max_dd * 100, 2),
        "sharpe": round(sharpe, 3),
        "trade_frequency_per_day": round(trade_frequency, 2),
        "net_return_pct": round((equity - 1.0) * 100, 2),
    }


def run_comparison(csv_path: str) -> Tuple[Dict[str, float], Dict[str, float]]:
    rows = parse_csv(csv_path)
    before = run_policy_backtest(rows, "before_baseline", should_buy_baseline)
    after = run_policy_backtest(rows, "after_strict_gate", should_buy_strict)
    return before, after


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest baseline vs strict trade gates.")
    parser.add_argument("--csv", required=True, help="Path to signal CSV")
    args = parser.parse_args()

    before, after = run_comparison(args.csv)
    print("=== BEFORE (baseline) ===")
    print(before)
    print("=== AFTER (strict gate) ===")
    print(after)


if __name__ == "__main__":
    main()

