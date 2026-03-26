"""Shared API contract loader used by backend and frontend."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict


CONTRACT_PATH = Path(__file__).resolve().parents[3] / "shared" / "api-contract.json"


@lru_cache(maxsize=1)
def load_api_contract() -> Dict[str, Any]:
    """Load the shared JSON API contract once per process."""
    if not CONTRACT_PATH.exists():
        return {"version": "missing", "routes": {}}
    with CONTRACT_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)

