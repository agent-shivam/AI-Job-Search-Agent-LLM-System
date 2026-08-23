from typing import TypedDict, Annotated, List, Optional
from langgraph.graph import add_messages
import json
import os


def load_preferences() -> dict:
    """Load preferences.json — resolves path whether run from project root or agent/."""
    candidates = [
        "agent/preferences.json",
        os.path.join(os.path.dirname(__file__), "preferences.json"),
        "preferences.json",
    ]
    for path in candidates:
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
    print("⚠️ preferences.json not found — using empty defaults")
    return {}


class AgentState(TypedDict):
    preferences:       Optional[dict]
    skipped_jobs:      Optional[List[str]]
    jobs_found:        List[dict]
    jobs_scored:       List[dict]
    current_job:       Optional[dict]
    jd_parsed:         Optional[dict]
    tailored_resume:   Optional[dict]
    cold_email:        Optional[str]
    applied:           List[dict]
    messages:          Annotated[list, add_messages]
    query:             Optional[str]
    location:          Optional[str]
    base_resume:       Optional[dict]
    # Scoring
    job_score:         Optional[float]
    score_explanation: Optional[str]
    # Approval
    approved:          Optional[bool]
    approval_action:   Optional[str]
    # Misc
    apply_result:      Optional[dict]
    resume_pdf_path:   Optional[str]
    stop:              Optional[bool]
