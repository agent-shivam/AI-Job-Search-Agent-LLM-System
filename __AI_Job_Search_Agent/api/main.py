

"""
api/main.py — FastAPI Backend for Job AI Agent
Run: uvicorn api.main:app --reload --port 8000
"""

import asyncio
import json
import os
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

app = FastAPI(
    title="Job AI Agent API",
    description="REST + WebSocket API for the autonomous job application agent",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory run state ───────────────────────────────────────────────────────
# Keyed by run_id → {status, logs, result, process}
_runs: Dict[str, Dict[str, Any]] = {}

# ── WebSocket manager ─────────────────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self._connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, run_id: str, ws: WebSocket):
        await ws.accept()
        self._connections.setdefault(run_id, []).append(ws)

    def disconnect(self, run_id: str, ws: WebSocket):
        if run_id in self._connections:
            # Replace `discard` with a safe removal method for lists
            try:
                self._connections[run_id].remove(ws)
            except ValueError:
                pass

    async def broadcast(self, run_id: str, data: dict):
        for ws in list(self._connections.get(run_id, [])):
            try:
                await ws.send_json(data)
            except Exception:
                pass


manager = ConnectionManager()


# ── Pydantic models ───────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    query: str = "AI Engineer"
    location: str = "India"
    dry_run: bool = True
    max_jobs: int = 5
    require_approval: bool = True
    sources: List[str] = ["LinkedIn", "Internshala"]


class PreferencesModel(BaseModel):
    target_roles: List[str] = []
    locations: List[str] = []
    industries: List[str] = []
    company_sizes: List[str] = []
    work_preferences: Dict[str, Any] = {}
    min_match_score: float = 0.7
    apply_limit_per_day: int = 15
    email_recruiters: bool = True
    resume_path: str = "data/base_resume.json"
    require_approval: bool = True
    Working_Experience: str = ""


class EnvConfig(BaseModel):
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    DRY_RUN: str = "true"
    SHOW_BROWSER: str = ""
    APPROVAL_TIMEOUT_SECONDS: str = "1800"
    DB_PATH: str = "db/tracker.db"
    PDF_OUTPUT_DIR: str = "data/resumes"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _db_path() -> str:
    return os.getenv("DB_PATH", str(ROOT / "db" / "tracker.db"))


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except Exception:
        return {}


def _save_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def _read_env() -> dict:
    env_file = ROOT / ".env"
    env: dict = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


def _write_env(data: dict):
    env_file = ROOT / ".env"
    lines = [f"{k}={v}" for k, v in data.items()]
    env_file.write_text("\n".join(lines) + "\n")


def _get_applications() -> List[dict]:
    db = _db_path()
    if not os.path.exists(db):
        return []
    try:
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM applications ORDER BY applied_at DESC LIMIT 500"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _get_stats() -> dict:
    apps = _get_applications()
    total   = len(apps)
    applied = sum(1 for a in apps if a.get("status") == "applied")
    dry_run = sum(1 for a in apps if a.get("status") == "dry_run")
    failed  = sum(1 for a in apps if a.get("status") == "failed")
    scores  = [a.get("match_score", 0) or 0 for a in apps]
    avg     = sum(scores) / max(len(scores), 1)
    return {
        "total": total,
        "applied": applied,
        "dry_run": dry_run,
        "failed": failed,
        "avg_score": round(avg, 3),
    }


# ── Background task: run agent subprocess ────────────────────────────────────

async def _stream_agent(run_id: str, req: RunRequest):
    run = _runs[run_id]
    run["status"] = "running"
    run["started_at"] = datetime.now().isoformat()

    env = {
        **os.environ,
        "DRY_RUN": "true" if req.dry_run else "false",
    }

    cmd = [sys.executable, str(ROOT / "agent" / "orchestrator.py")]

    # Pass params via env
    env["AGENT_QUERY"]    = req.query
    env["AGENT_LOCATION"] = req.location
    env["AGENT_MAX_JOBS"] = str(req.max_jobs)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=str(ROOT),
            env=env,
        )
        run["pid"] = proc.pid

        if proc.stdout:  # Ensure stdout is not None before iterating
            async for raw in proc.stdout:
                line = raw.decode("utf-8", errors="replace").rstrip()
                if line:
                    entry = {"ts": datetime.now().isoformat(), "line": line}
                    run["logs"].append(entry)
                    await manager.broadcast(run_id, {"type": "log", "data": entry})

        await proc.wait()
        run["exit_code"] = proc.returncode
        run["status"]    = "completed" if proc.returncode == 0 else "failed"

    except Exception as e:
        run["status"] = "error"
        entry = {"ts": datetime.now().isoformat(), "line": f"❌ Internal error: {e}"}
        run["logs"].append(entry)
        await manager.broadcast(run_id, {"type": "log", "data": entry})

    run["finished_at"] = datetime.now().isoformat()
    await manager.broadcast(run_id, {"type": "done", "status": run["status"]})


# ══════════════════════════════════════════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/", tags=["Health"])
async def root():
    return {"message": "Job AI Agent API", "version": "1.0.0", "status": "ok"}


@app.get("/health", tags=["Health"])
async def health():
    return {
        "status": "ok",
        "db_exists": os.path.exists(_db_path()),
        "resume_exists": (ROOT / "data" / "base_resume.json").exists(),
        "prefs_exists": (ROOT / "agent" / "preferences.json").exists(),
        "telegram_configured": bool(os.getenv("TELEGRAM_BOT_TOKEN")),
    }


# ── Agent Runs ────────────────────────────────────────────────────────────────

@app.post("/runs", tags=["Agent"])
async def start_run(req: RunRequest, background_tasks: BackgroundTasks):
    """Start a new agent pipeline run."""
    run_id = uuid.uuid4().hex[:10]
    _runs[run_id] = {
        "run_id":    run_id,
        "status":    "queued",
        "logs":      [],
        "request":   req.model_dump(),
        "started_at": None,
        "finished_at": None,
        "exit_code": None,
        "pid":       None,
    }
    background_tasks.add_task(_stream_agent, run_id, req)
    return {"run_id": run_id, "status": "queued"}


@app.get("/runs", tags=["Agent"])
async def list_runs():
    """List all runs this session."""
    return [
        {k: v for k, v in r.items() if k != "logs"}
        for r in _runs.values()
    ]


@app.get("/runs/{run_id}", tags=["Agent"])
async def get_run(run_id: str):
    if run_id not in _runs:
        raise HTTPException(404, "Run not found")
    return _runs[run_id]


@app.get("/runs/{run_id}/logs", tags=["Agent"])
async def get_run_logs(run_id: str):
    if run_id not in _runs:
        raise HTTPException(404, "Run not found")
    return {"run_id": run_id, "logs": _runs[run_id]["logs"]}


@app.delete("/runs/{run_id}", tags=["Agent"])
async def cancel_run(run_id: str):
    if run_id not in _runs:
        raise HTTPException(404, "Run not found")
    run = _runs[run_id]
    if run.get("pid") and run["status"] == "running":
        try:
            import signal
            os.kill(run["pid"], signal.SIGTERM)
            run["status"] = "cancelled"
        except Exception as e:
            raise HTTPException(500, f"Could not kill process: {e}")
    return {"run_id": run_id, "status": run["status"]}


# ── WebSocket: live logs ──────────────────────────────────────────────────────

@app.websocket("/ws/runs/{run_id}")
async def ws_run_logs(websocket: WebSocket, run_id: str):
    """Stream live logs for a run."""
    await manager.connect(run_id, websocket)

    # Send backlog immediately
    if run_id in _runs:
        for entry in _runs[run_id]["logs"]:
            await websocket.send_json({"type": "log", "data": entry})
        if _runs[run_id]["status"] in ("completed", "failed", "cancelled", "error"):
            await websocket.send_json({"type": "done", "status": _runs[run_id]["status"]})

    try:
        while True:
            await websocket.receive_text()  # keep alive
    except WebSocketDisconnect:
        manager.disconnect(run_id, websocket)


# ── Applications (DB) ─────────────────────────────────────────────────────────

@app.get("/applications", tags=["Applications"])
async def get_applications(
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    apps = _get_applications()
    if status:
        apps = [a for a in apps if a.get("status","").lower() == status.lower()]
    return {
        "total": len(apps),
        "items": apps[offset: offset + limit],
    }


@app.get("/applications/stats", tags=["Applications"])
async def get_stats():
    return _get_stats()


@app.delete("/applications/{app_id}", tags=["Applications"])
async def delete_application(app_id: int):
    db = _db_path()
    if not os.path.exists(db):
        raise HTTPException(404, "Database not found")
    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM applications WHERE id=?", (app_id,))
    conn.commit()
    conn.close()
    return {"deleted": app_id}


# ── Resume ────────────────────────────────────────────────────────────────────

@app.get("/resume", tags=["Resume"])
async def get_resume():
    path = ROOT / "data" / "base_resume.json"
    if not path.exists():
        raise HTTPException(404, "Resume not found")
    return _load_json(path)


@app.put("/resume", tags=["Resume"])
async def update_resume(resume: Dict[str, Any]):
    path = ROOT / "data" / "base_resume.json"
    _save_json(path, resume)
    return {"saved": True, "path": str(path)}


# ── Preferences ───────────────────────────────────────────────────────────────

@app.get("/preferences", tags=["Preferences"])
async def get_preferences():
    path = ROOT / "agent" / "preferences.json"
    if not path.exists():
        raise HTTPException(404, "preferences.json not found")
    return _load_json(path)


@app.put("/preferences", tags=["Preferences"])
async def update_preferences(prefs: Dict[str, Any]):
    path = ROOT / "agent" / "preferences.json"
    _save_json(path, prefs)
    return {"saved": True}


# ── Environment config ────────────────────────────────────────────────────────

@app.get("/config", tags=["Config"])
async def get_config():
    env = _read_env()
    # Mask token
    if env.get("TELEGRAM_BOT_TOKEN"):
        tok = env["TELEGRAM_BOT_TOKEN"]
        env["TELEGRAM_BOT_TOKEN"] = tok[:6] + "***" + tok[-4:] if len(tok) > 10 else "***"
    return env


@app.put("/config", tags=["Config"])
async def update_config(config: Dict[str, Any]):
    existing = _read_env()
    existing.update(config)
    _write_env(existing)
    # Apply to current process
    for k, v in config.items():
        os.environ[k] = str(v)
    return {"saved": True}


# ── System info ───────────────────────────────────────────────────────────────

@app.get("/system", tags=["System"])
async def system_info():
    def cmd_exists(name):
        import shutil
        return shutil.which(name) is not None

    return {
        "python":       sys.version,
        "ollama":       cmd_exists("ollama"),
        "playwright":   cmd_exists("playwright"),
        "root":         str(ROOT),
        "db_path":      _db_path(),
        "active_runs":  sum(1 for r in _runs.values() if r["status"] == "running"),
        "total_runs":   len(_runs),
    }



