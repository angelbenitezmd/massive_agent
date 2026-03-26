"""LLM Token Usage Tracker.

In-memory tracker that accumulates token usage per LLM call,
grouped by model and agent type, with hourly breakdowns and cost estimates.
"""
import threading
from datetime import datetime, date
from typing import Dict, Any, List

# Pricing per 1M tokens (input, output)
MODEL_PRICING = {
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-sonnet-4-5-20241022": {"input": 3.00, "output": 15.00},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
}

# Fallback pricing for unknown models
DEFAULT_PRICING = {"input": 1.00, "output": 5.00}


class TokenTracker:
    def __init__(self):
        self._lock = threading.Lock()
        self._calls: List[Dict[str, Any]] = []

    def record(self, model: str, input_tokens: int, output_tokens: int, agent_type: str = "unknown"):
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "date": date.today().isoformat(),
            "hour": datetime.utcnow().hour,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "agent_type": agent_type,
        }
        with self._lock:
            self._calls.append(entry)

    def _estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        pricing = MODEL_PRICING.get(model, DEFAULT_PRICING)
        return (input_tokens / 1_000_000) * pricing["input"] + (output_tokens / 1_000_000) * pricing["output"]

    def get_today_summary(self) -> Dict[str, Any]:
        today = date.today().isoformat()
        with self._lock:
            today_calls = [c for c in self._calls if c["date"] == today]

        total_input = 0
        total_output = 0
        total_cost = 0.0
        by_model: Dict[str, Dict] = {}
        by_agent: Dict[str, Dict] = {}
        by_hour: Dict[int, Dict] = {}

        for c in today_calls:
            inp = c["input_tokens"]
            out = c["output_tokens"]
            model = c["model"]
            agent = c["agent_type"]
            hour = c["hour"]
            cost = self._estimate_cost(model, inp, out)

            total_input += inp
            total_output += out
            total_cost += cost

            # By model
            if model not in by_model:
                by_model[model] = {"input": 0, "output": 0, "cost": 0.0, "calls": 0}
            by_model[model]["input"] += inp
            by_model[model]["output"] += out
            by_model[model]["cost"] += cost
            by_model[model]["calls"] += 1

            # By agent
            if agent not in by_agent:
                by_agent[agent] = {"input": 0, "output": 0, "calls": 0}
            by_agent[agent]["input"] += inp
            by_agent[agent]["output"] += out
            by_agent[agent]["calls"] += 1

            # By hour
            if hour not in by_hour:
                by_hour[hour] = {"hour": hour, "input": 0, "output": 0, "calls": 0}
            by_hour[hour]["input"] += inp
            by_hour[hour]["output"] += out
            by_hour[hour]["calls"] += 1

        # Round costs
        total_cost = round(total_cost, 4)
        for m in by_model.values():
            m["cost"] = round(m["cost"], 4)

        return {
            "date": today,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_cost_estimate": total_cost,
            "call_count": len(today_calls),
            "by_model": by_model,
            "by_agent": by_agent,
            "by_hour": sorted(by_hour.values(), key=lambda x: x["hour"]),
        }


token_tracker = TokenTracker()
