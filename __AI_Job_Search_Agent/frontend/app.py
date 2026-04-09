

"""
app.py
------
Streamlit frontend for the AI Job Search Agent.

Workflow displayed:
  Search → Fetch JD → Parse JD → Match Score → [>75%: Tailored Resume → Cold Email → Approval]

Approval card shows:
  - Job title, company, match score, score explanation
  - Two buttons: "⏭ Skip" (search next job) | "📄 Details" (full details)

Details view shows:
  - Job link, full JD, tailored resume, cold email, HR email
"""
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from streamlit_autorefresh import st_autorefresh

import streamlit as st   # 🔥 MUST BE FIRST

# from streamlit_autorefresh import st_autorefresh

# 🔥 Only refresh if NO job is expanded
# if not st.session_state.get("expanded_jobs"):
#     st_autorefresh(interval=2000, key="refresh")

from agent.approval_store import get_all_pending, resolve_approval
# import streamlit as st
import json
import threading
import time
import os
import sys

import streamlit as st
from typing import cast

# ── Path setup ───────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from agent.orchestrator import app as graph_app, _load_base_resume
from agent.state import AgentState, load_preferences
from agent.approval_store import get_all_pending, resolve_approval, get_all_requests

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="🤖 AI Job Agent", layout="wide", initial_sidebar_state="collapsed")

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.job-card {
    background: #1e1e2e;
    border: 1px solid #313244;
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 16px;
}
.score-high  { color: #a6e3a1; font-weight: bold; font-size: 1.2em; }
.score-med   { color: #f9e2af; font-weight: bold; font-size: 1.2em; }
.score-low   { color: #f38ba8; font-weight: bold; font-size: 1.2em; }
.tag {
    display: inline-block;
    background: #313244;
    border-radius: 6px;
    padding: 2px 10px;
    margin: 2px;
    font-size: 0.8em;
    color: #cdd6f4;
}
.status-pending  { color: #f9e2af; }
.status-skip     { color: #f38ba8; }
.status-details  { color: #a6e3a1; }
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────
for key, default in [
    ("agent_thread",  None),
    ("agent_running", False),
    ("log_messages",  []),
    ("expanded_jobs", []),
]:
    if key not in st.session_state:
        st.session_state[key] = default


viewing_details = len(st.session_state.expanded_jobs) > 0
# AFTER session_state initialization
pending = get_all_pending()


thread_alive = (
    st.session_state.agent_thread is not None and
    st.session_state.agent_thread.is_alive()
)

if thread_alive or pending:
    st_autorefresh(interval=1000, key="refresh")
    

# ── Graph runner ──────────────────────────────────────────────────────────────
def run_graph(initial_state: dict):
    try:
        graph_app.invoke(cast(AgentState, initial_state))
    except Exception as e:
        st.session_state.log_messages.append(f"❌ Agent error: {e}")
    


# ── Header ────────────────────────────────────────────────────────────────────
st.title("🤖 AI Job Search Agent")
st.caption("Automated: Search → Fetch JD → Parse → Match Score → Tailor Resume → Cold Email → Your Approval")

st.divider()

# ── Controls ──────────────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns([3, 2, 1, 1])

with col1:
    query = st.text_input("🔍 Job Role", "AI Engineer", label_visibility="collapsed",
                          placeholder="Job Role (e.g. AI Engineer)")

with col2:
    location = st.text_input("📍 Location", "India", label_visibility="collapsed",
                              placeholder="Location (e.g. India)")

with col3:
    search_clicked = st.button("🚀 Start", use_container_width=True,
                                disabled=st.session_state.agent_running)

with col4:
    stop_clicked = st.button("🛑 Stop", use_container_width=True,
                              disabled=not st.session_state.agent_running)

# ── Start agent ───────────────────────────────────────────────────────────────
if search_clicked and not st.session_state.agent_running:

    st.session_state.agent_running = True   # ✅ SET HERE ONLY

    store_path = os.path.join(ROOT, "data", "approval_state.json")
    if os.path.exists(store_path):
        os.remove(store_path)

    try:
        prefs = load_preferences()
    except Exception:
        prefs = {}

    initial_state = {
        "query":    query,
        "location": location,
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
        "score_explanation": "",
        "stop": False,
    }

    def run_and_reset():
        try:
            graph_app.invoke(cast(AgentState, initial_state))
        finally:
            st.session_state.agent_running = False   # ✅ SAFE RESET

    t = threading.Thread(target=run_and_reset, daemon=True)
    t.start()

    st.session_state.agent_thread = t
    st.rerun()


if stop_clicked:
    st.session_state.agent_running = False
    st.warning("🛑 Stop requested — agent will halt after the current job.")

# ── Live Loader / Processing UI ───────────────────────────────────────────────
# ── Live Loader / Processing UI (Stable Version) ──────────────────────────────
pending = get_all_pending()

loader_box = st.empty()

thread_alive = (
    st.session_state.agent_thread is not None and
    st.session_state.agent_thread.is_alive()
)

if thread_alive:

    steps = [
        "🔍 Searching jobs...",
        "📄 Fetching job description...",
        "🧠 Parsing & understanding JD...",
        "📊 Calculating match score...",
        "📎 Generating tailored resume...",
        "✉️ Writing cold email...",
    ]

    step_index = int(time.time() / 2) % len(steps)

    loader_box.markdown("### ⚡ AI Agent Working...")
    loader_box.info(steps[step_index])

elif pending:
    loader_box.success("📬 Approval request ready! Check left panel 👈")

else:
    loader_box.warning("😴 Agent idle. Click Start to begin.")

# ── Running indicator ─────────────────────────────────────────────────────────
if st.session_state.agent_running:
    st.info("🔄 Agent is running… page auto-refreshes every 3 seconds")

# ── Main area: two columns ────────────────────────────────────────────────────
left, right = st.columns([1, 1], gap="large")

# ── LEFT: Pending approvals ───────────────────────────────────────────────────
with left:
    st.subheader("📬 Pending Approvals")

    pending = get_all_pending()

    if not pending:
        if st.session_state.agent_running:
            st.caption("⏳ Waiting for agent to find a qualifying job (score ≥ 75%)…")
        else:
            st.caption("No pending approvals. Start the agent to begin.")
    else:
        for job in pending:
            job_id  = job.get("id", "")
            company = job.get("company", "Unknown")
            role    = job.get("role", "Unknown")
            score   = float(job.get("score", 0))
            score_pct = f"{score*100:.0f}%"
            explanation = job.get("score_explanation", "")

            score_class = "score-high" if score >= 0.85 else ("score-med" if score >= 0.75 else "score-low")

            st.markdown(f"""
<div class="job-card">
  <div style="display:flex; justify-content:space-between; align-items:center;">
    <div>
      <h3 style="margin:0; color:#cdd6f4;">💼 {role}</h3>
      <p style="margin:4px 0; color:#89b4fa;">🏢 {company}</p>
    </div>
    <div class="{score_class}">⭐ {score_pct}</div>
  </div>
  <p style="color:#a6adc8; font-size:0.85em; margin-top:8px;">{explanation[:200]}</p>
</div>
""", unsafe_allow_html=True)

            c1, c2 = st.columns(2)

            with c1:
                if st.button(f"⏭ Skip", key=f"skip_{job_id}", use_container_width=True):
                    resolve_approval(job_id, "skip")
                    st.success("Skipped → agent will pick next job")
                    time.sleep(0.5)
                    st.rerun()

            with c2:
                if st.button(f"📄 Details", key=f"details_{job_id}", use_container_width=True):
                    resolve_approval(job_id, "details")
                    st.session_state.expanded_jobs = [job_id]   # 🔥 replace append
                    st.rerun()

# ── RIGHT: History / Details ───────────────────────────────────────────────────
with right:
    st.subheader("📋 Job History")

    all_requests = get_all_requests()
    history = [j for j in all_requests if j.get("status") != "pending"]

    if not history:
        st.caption("Resolved jobs will appear here.")
    else:
        for job in reversed(history):
            job_id  = job.get("id", "")
            company = job.get("company", "Unknown")
            role    = job.get("role", "Unknown")
            score   = float(job.get("score", 0))
            status  = job.get("status", "")

            status_icon = {"skip": "⏭", "details": "📄", "timeout": "⏰"}.get(status, "❓")
            status_label = {"skip": "Skipped", "details": "Viewed Details", "timeout": "Timed Out"}.get(status, status)


            expanded = (status == "details") or (job_id in st.session_state.expanded_jobs)

            # 🔥 Keep expansion stable across reruns
            if expanded and job_id not in st.session_state.expanded_jobs:
                st.session_state.expanded_jobs = [job_id]

            with st.expander(
                f"{status_icon} {role} @ {company}  ({score*100:.0f}%)  — {status_label}",
                expanded=expanded
            ):
                
                # 🚀 Apply Button
                job_url = job.get("job_url", "")
                if job_url:
                    st.link_button("🚀 Apply Now", job_url)
                if status == "details" or job_id in st.session_state.expanded_jobs:
                    # Show full details
                    st.markdown(f"**🔗 Job Link:** [{job.get('job_url', 'N/A')}]({job.get('job_url', '#')})")
                    st.markdown(f"**📧 HR Email:** {job.get('hr_email', 'Not available')}")
                    st.markdown(f"**👤 Recruiter:** {job.get('recruiter_name', 'N/A')}")

                    tab_jd, tab_resume, tab_email = st.tabs(["📝 Job Description", "📎 Tailored Resume", "✉️ Cold Email"])

                    with tab_jd:
                        jd_text = job.get("jd", "Not available")
                        st.text_area("Full JD", jd_text, height=300, key=f"jd_{job_id}")

                    with tab_resume:
                        resume = job.get("tailored_resume", {})
                        if isinstance(resume, dict):
                            st.json(resume)
                        else:
                            st.text(str(resume))

                    with tab_email:
                        email = job.get("cold_email", "Not generated")
                        st.text_area("Cold Email", email, height=250, key=f"email_{job_id}")
                        if st.button("📋 Copy Email", key=f"copy_{job_id}"):
                            st.code(email)

                else:
                    st.markdown(f"**Score:** {score*100:.0f}%")
                    st.markdown(f"**Status:** {status_label}")

# ── Workflow diagram ──────────────────────────────────────────────────────────
st.divider()
with st.expander("🗺️ Agent Workflow"):
    st.markdown("""
```
Search Jobs
    ↓
Pick Job (skip already-seen)
    ↓
Fetch & Parse JD
    ↓
Score Match (LLM)
    ↓
Score < 75% → Skip → Pick Next Job
Score ≥ 75% → Tailor Resume (LLM)
                    ↓
               Generate Cold Email (LLM)
                    ↓
               📬 Approval Card (shown above)
                    ↓
        ⏭ Skip → Pick Next Job
        📄 Details → Show Full Details → Done
```
""")


