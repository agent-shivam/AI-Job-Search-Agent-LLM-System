"""
approval_store.py
-----------------
Shared in-memory + file-backed store for approval requests.

The orchestrator (background thread) writes a "pending" request here.
The Streamlit frontend reads it and writes back "skip" or "details".
The orchestrator polls until resolved.

Uses a JSON file (approval_state.json) so it survives thread boundaries
and works even if Streamlit rerenders the page.
"""

import json
import os
import threading

_STORE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "approval_state.json")
_lock = threading.Lock()


def _read() -> dict:
    try:
        with open(_STORE_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write(data: dict) -> None:
    os.makedirs(os.path.dirname(_STORE_PATH), exist_ok=True)
    with open(_STORE_PATH, "w") as f:
        json.dump(data, f, indent=2, default=str)


def post_approval_request(job_id: str, payload: dict) -> None:
    """Orchestrator calls this to post a new pending approval."""
    with _lock:
        data = _read()
        data[job_id] = {**payload, "status": "pending"}
        _write(data)


def get_approval_decision(job_id: str) -> str | None:
    """Orchestrator polls this. Returns 'skip', 'details', 'pending', or None."""
    with _lock:
        data = _read()
        entry = data.get(job_id)
        if entry is None:
            return None
        return entry.get("status", "pending")


def resolve_approval(job_id: str, decision: str) -> None:
    """Streamlit frontend calls this when user clicks Skip or Details."""
    with _lock:
        data = _read()
        if job_id in data:
            data[job_id]["status"] = decision
            _write(data)


def clear_approval(job_id: str) -> None:
    """Orchestrator calls this after consuming the decision."""
    with _lock:
        data = _read()
        data.pop(job_id, None)
        _write(data)


def get_all_pending() -> list[dict]:
    """Streamlit frontend calls this to display pending approvals."""
    with _lock:
        data = _read()
        return [v for v in data.values() if v.get("status") == "pending"]


def get_all_requests() -> list[dict]:
    """Streamlit frontend calls this to show all requests (any status)."""
    with _lock:
        data = _read()
        return list(data.values())
