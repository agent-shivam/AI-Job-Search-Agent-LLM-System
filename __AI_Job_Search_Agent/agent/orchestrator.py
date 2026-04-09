"""
orchestrator.py
---------------
LangGraph pipeline for the Job AI Agent.

Workflow:
  search → pick_job → fetch_jd → parse_jd → score_job
       → [score < 0.75: skip_low_score → pick_job]
       → [score >= 0.75: tailor_resume → generate_email → approval_gate]
       → [approval: skip → pick_job | details → END]

Approval is communicated via a shared file/dict (approval_store.py),
so Streamlit frontend can display and resolve approvals without Telegram.
"""

import json
import os
import hashlib
import re
import time
from typing import cast
from llm import GroqLLM
from langgraph.graph import StateGraph, START, END

from tools.job_search_parser import search_jobs
from tools.resume_tailor import tailor_resume
from tools.email_sender import generate_cold_email
from agent.state import AgentState, load_preferences
from agent.approval_store import (
    post_approval_request,
    get_approval_decision,
    clear_approval,
)
# from llm import OllamaLLM


from dotenv import load_dotenv
import os
# from langchain_ollama import OllamaLLM
load_dotenv()

# ── LLM ───────────────────────────────────────────────────────────────────────

# llm = GroqLLM()


from llm import OpenRouterLLM
llm = OpenRouterLLM()


# # llm = GeminiLLM()
# llm = OllamaLLM(
#     model="tinyllama:latest",
    
# )

# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_content(result) -> str:
    """Extract string from AIMessage or plain string."""
    if hasattr(result, "content"):
        return result.content
    return str(result)


def generate_job_id(job: dict) -> str:
    base = f"{job.get('title', '')}_{job.get('company', '')}_{job.get('url', '')}"
    return hashlib.md5(base.encode()).hexdigest()[:12]


# ── Nodes ──────────────────────────────────────────────────────────────────────

def search_jobs_node(state: AgentState) -> dict:
    query    = state.get("query")
    location = state.get("location")

    if not query or not location:
        print("⚠️ Missing query/location — skipping search")
        return {"jobs_found": [], "jobs_scored": []}

    try:
        result = search_jobs(state)
        print(f"🔍 Found {len(result.get('jobs_scored', []))} scored jobs")
        return result
    except Exception as e:
        print(f"❌ search_jobs failed: {e}")
        return {"jobs_found": [], "jobs_scored": []}


def pick_job_node(state: AgentState) -> dict:
    jobs    = state.get("jobs_scored") or state.get("jobs_found", [])
    skipped = set(state.get("skipped_jobs") or [])

    if not jobs:
        print("⚠️ No jobs found — ending pipeline")
        return {"current_job": None}

    for job in jobs:
        job_id = job.get("id") or generate_job_id(job)
        job["id"] = job_id
        if job_id not in skipped:
            print(f"📌 Picked: {job.get('title')} @ {job.get('company')} (id={job_id})")
            return {"current_job": job}

    print("⚠️ All jobs exhausted (all skipped)")
    return {"current_job": None}


def parse_jd_node(state: AgentState) -> dict:
    job     = state.get("current_job") or {}
    jd_text = (job.get("description") or "").strip()

# 🔥 FILTER BAD JD
    jd_text = (job.get("description") or "").strip()

# 🚨 BLOCK BAD JD
    if len(jd_text) < 300 or jd_text.count(" ") < 80:
        print("⛔ Bad JD detected → skipping LLM call")

        return {
            "jd_parsed": {},
            "parse_failed": True
        }
    prompt = f"""You are a strict JSON extractor.

Extract structured data from the job description.

Return ONLY valid JSON. No explanation.

{{
  "Job_Title": "",
  "company_name": "",
  "required_skills": [],
  "experience_level": "",
  "ats_keywords": [],
  "nice_to_have": [],
  "recruiter_name": "",
  "recruiter_email": "",
  "skills": [],
  "tools": []
}}

Job Description:
{jd_text[:800]}
"""
    try:
        raw     = _safe_content(llm.invoke(prompt))
        print("📦 RAW LLM (parse_jd):", raw[:200])
        jd_text = re.sub(r"\s+", " ", jd_text)  # remove weird spacing
        cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
        match   = re.search(r"\{.*\}", cleaned, re.DOTALL)
        parsed  = json.loads(match.group(0) if match else cleaned)
    except Exception as e:
        print(f"⚠️ JD parse failed: {e} → fallback")
        parsed = {
            "Job_Title": job.get("title", ""),
            "company_name": job.get("company", ""),
            "required_skills": [],
            "ats_keywords": [],
            "skills": [],
            "tools": [],
        }

    return {"jd_parsed": parsed}

def score_job_node(state: AgentState) -> dict:
    jd_data     = state.get("jd_parsed") or {}
    base_resume = state.get("base_resume") or {}
    job         = state.get("current_job") or {}

    if not jd_data:
        print("⚠️ No parsed JD → using raw job data")

    prompt = f"""
You are an AI job matching system.

Evaluate how well the candidate matches the job.

ONLY return valid JSON. No explanation outside JSON.

Job Title: {job.get("title")}
Company: {job.get("company")}

Job Description:
{(job.get("description") or "")[:500]}

Parsed JD:
{json.dumps(jd_data)[:500]}

Candidate Resume:
{json.dumps(base_resume)[:500]}

Rules:
- 0.9–1.0 → very strong match
- 0.7–0.89 → good match
- 0.5–0.69 → average
- below 0.5 → poor match

Return ONLY:
{{"score": 0.75, "explanation": "short reason"}}
"""

    try:
        raw     = _safe_content(llm.invoke(prompt))
        cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
        match   = re.search(r"\{.*\}", cleaned, re.DOTALL)
        data    = json.loads(match.group(0) if match else cleaned)
    except Exception:
        data = {
            "score": 0.65,
            "explanation": "fallback using job context"
        }

    try:
        score = float(data.get("score", 0.65))
    except:
        score = 0.65

    # 🔥 clamp score
    if score < 0 or score > 1:
        score = 0.65

    # 🔥 avoid useless constant scores
    if score <= 0.5:
        score = 0.6
    print(f"✅ score_job_node: {score:.2f} for {job.get('title', '?')} @ {job.get('company', '?')}")

    return {
        "job_score":         score,
        "score_explanation": data.get("explanation", ""),
    }

def skip_low_score_node(state: AgentState) -> dict:
    """Mark current job as skipped (score < 0.75) and loop back."""
    job      = state.get("current_job") or {}
    skipped  = list(state.get("skipped_jobs") or [])
    job_id   = job.get("id") or generate_job_id(job)
    score    = state.get("job_score", 0)

    print(f"⏭ Skipping low-score job (score={score:.2f}): {job.get('title')} @ {job.get('company')}")
    if job_id not in skipped:
        skipped.append(job_id)

    return {"skipped_jobs": skipped, "current_job": None}


def tailor_resume_node(state: AgentState) -> dict:
    base_resume = state.get("base_resume")
    jd_data     = state.get("jd_parsed")
    if not base_resume or not jd_data:
        raise ValueError("Missing 'base_resume' or 'jd_parsed' in AgentState")
    return tailor_resume(base_resume, jd_data, llm)


def generate_email_node(state: AgentState) -> dict:
    jd_data = state.get("jd_parsed") or {}
    resume  = state.get("tailored_resume") or state.get("base_resume", {}) or {}
    if not jd_data:
        raise ValueError("Missing 'jd_parsed' in AgentState")
    return generate_cold_email(jd_data, resume, llm)


def approval_gate_node(state: AgentState) -> dict:
    """
    Post approval request to the shared store and POLL until Streamlit
    resolves it (skip or details). Timeout after APPROVAL_TIMEOUT_SECONDS.
    Does NOT use Telegram — Streamlit frontend reads/writes the store.
    """
    jd     = state.get("jd_parsed", {}) or {}
    job    = state.get("current_job", {}) or {}
    resume = state.get("tailored_resume") or state.get("base_resume", {}) or {}

    job_id  = job.get("id") or generate_job_id(job)
    company = jd.get("company_name", "Unknown")
    role    = jd.get("Job_Title", "Unknown")
    score   = float(state.get("job_score") or 0)

    payload = {
        "id": job_id,
        "job_id": job_id,
        "company":         company,
        "title": role,
        "role": role,
        "score":           score,
        "score_pct":       f"{score * 100:.0f}%",
        "score_explanation": state.get("score_explanation", ""),
        "job_url":         job.get("url", ""),
        "jd":              job.get("description", ""),
        "cold_email":      state.get("cold_email", ""),
        "tailored_resume": resume,
        "hr_email":        jd.get("recruiter_email", "Not available"),
        "recruiter_name":  jd.get("recruiter_name", "Hiring Manager"),
        "status":          "pending",   # Streamlit will set "skip" or "details"
    }

    print(f"📬 Posting approval request for {role} @ {company} (score={score:.0%})")
    post_approval_request(job_id, payload)

    # Poll the shared store until Streamlit resolves it
    timeout = int(os.getenv("APPROVAL_TIMEOUT_SECONDS", "1800"))
    deadline = time.time() + timeout

    while time.time() < deadline:
        decision = get_approval_decision(job_id)
        if decision and decision != "pending":
            print(f"✅ Approval resolved: {decision}")
            # Only clear if skip
            if decision == "skip":
                clear_approval(job_id)
            return {"approval_action": decision}
        time.sleep(2)

    print(f"⏰ Approval timeout for {role} @ {company}")
    clear_approval(job_id)
    return {"approval_action": "timeout"}


def handle_skip_node(state: AgentState) -> dict:
    """Add current job to skipped list and reset for next pick."""
    job     = state.get("current_job") or {}
    skipped = list(state.get("skipped_jobs") or [])
    job_id  = job.get("id") or generate_job_id(job)

    if job_id not in skipped:
        skipped.append(job_id)
        print(f"⏭ Skipped (user decision): {job.get('title')} @ {job.get('company')}")

    return {"skipped_jobs": skipped, "current_job": None}


# ── Routing functions ─────────────────────────────────────────────────────────

def after_pick_job(state: AgentState) -> str:
    if state.get("current_job") is None:
        return END
    return "parse_jd"


def after_score_job(state: AgentState) -> str:
    score = float(state.get("job_score") or 0)
    if score >= 0.75:
        return "tailor_resume"
    return "skip_low_score"


def after_approval_gate(state: AgentState) -> str:
    action = state.get("approval_action", "")
    if action == "skip" or action == "timeout":
        return "handle_skip"
    if action == "details":
        # User wants details → mark as approved/done and end this cycle
        return END
    return "handle_skip"


# ── Build graph ────────────────────────────────────────────────────────────────

graph = StateGraph(AgentState)

graph.add_node("search",          search_jobs_node)
graph.add_node("pick_job",        pick_job_node)
graph.add_node("parse_jd",        parse_jd_node)
graph.add_node("score_job",       score_job_node)
graph.add_node("skip_low_score",  skip_low_score_node)
graph.add_node("tailor_resume",   tailor_resume_node)
graph.add_node("generate_email",  generate_email_node)
graph.add_node("approval_gate",   approval_gate_node)
graph.add_node("handle_skip",     handle_skip_node)

# ── Edges ──────────────────────────────────────────────────────────────────────

graph.add_edge(START, "search")
graph.add_edge("search", "pick_job")

graph.add_conditional_edges("pick_job",       after_pick_job,    {"parse_jd": "parse_jd", END: END})
graph.add_edge("parse_jd", "score_job")
graph.add_conditional_edges("score_job",      after_score_job,   {"tailor_resume": "tailor_resume", "skip_low_score": "skip_low_score"})
graph.add_edge("skip_low_score", "pick_job")   # loop back to try next job
graph.add_edge("tailor_resume", "generate_email")
graph.add_edge("generate_email", "approval_gate")
graph.add_conditional_edges("approval_gate",  after_approval_gate, {"handle_skip": "handle_skip", END: END})
graph.add_edge("handle_skip", "pick_job")      # loop back to try next job

# ── Compile ────────────────────────────────────────────────────────────────────

app = graph.compile()


# ── Helpers for external use ──────────────────────────────────────────────────

def _load_base_resume() -> dict:
    prefs       = load_preferences()
    resume_path = prefs.get("resume_path", "data/base_resume.json")
    if os.path.exists(resume_path):
        with open(resume_path, "r") as f:
            return json.load(f)
    print(f"⚠️ base_resume not found at {resume_path}")
    return {}


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    prefs = load_preferences()

    initial_state: dict = {
        "query":    "AI Engineer",
        "location": "India",
        "preferences": prefs,
        "base_resume":  _load_base_resume(),
        "jobs_found":   [],
        "jobs_scored":  [],
        "skipped_jobs": [],
        "applied":      [],
        "messages":     [],
        "current_job":     None,
        "jd_parsed":       None,
        "tailored_resume": None,
        "cold_email":      None,
        "job_score":       None,
        "approved":        None,
        "approval_action": None,
    }

    result = app.invoke(cast(AgentState, initial_state))
    print("\n✅ Agent Finished")
    print(json.dumps({k: v for k, v in result.items() if k != "messages"}, indent=2, default=str))
