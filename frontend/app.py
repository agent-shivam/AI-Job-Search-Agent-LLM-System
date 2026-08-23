"""
app.py
------
Interactive, user-friendly Streamlit frontend for the AI Job Search Agent.
Allows dynamic inputs, custom resume uploading, multi-portal job searching (10 results),
and on-demand tailored resume PDF generation + cold email drafting.
"""

import sys
import os

if sys.platform.startswith('win'):
    try:
        import io
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import json
import time
import streamlit as st

# Setup path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Import backend tools
from tools.job_search_parser import search_jobs, parse_jd
from tools.resume_tailor import tailor_resume
from tools.email_sender import generate_cold_email
from tools.pdf_generator import generate_resume_pdf
from agent.orchestrator import llm, _load_base_resume, parse_jd_node, score_job_node
from agent.state import load_preferences

# Page layout & styling
st.set_page_config(
    page_title="🤖 AI Job Agent Pro",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for rich aesthetics and modern typography
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Outfit', sans-serif;
    color: #cdd6f4;
}

/* Background gradient styling */
.stApp {
    background: radial-gradient(circle at 10% 20%, #11111b 0%, #181825 90%);
}

/* Custom job card styling */
.job-card {
    background: rgba(30, 30, 46, 0.6);
    border: 1px solid rgba(180, 190, 254, 0.15);
    border-radius: 16px;
    padding: 24px;
    margin-bottom: 20px;
    transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
    box-shadow: 0 4px 30px rgba(0, 0, 0, 0.2);
    backdrop-filter: blur(10px);
}

.job-card:hover {
    border-color: rgba(180, 190, 254, 0.4);
    box-shadow: 0 8px 30px rgba(180, 190, 254, 0.1);
    transform: translateY(-2px);
}

/* Match Score badges */
.score-badge {
    background: linear-gradient(135deg, #a6e3a1 0%, #89b4fa 100%);
    color: #11111b !important;
    font-weight: 700;
    padding: 6px 14px;
    border-radius: 30px;
    font-size: 1.1em;
    box-shadow: 0 4px 10px rgba(166, 227, 161, 0.3);
}

.score-badge-low {
    background: linear-gradient(135deg, #f38ba8 0%, #fab387 100%);
    color: #11111b !important;
    font-weight: 700;
    padding: 6px 14px;
    border-radius: 30px;
    font-size: 1.1em;
    box-shadow: 0 4px 10px rgba(243, 139, 168, 0.3);
}

/* Badges for filters */
.tag {
    display: inline-block;
    background: rgba(49, 50, 68, 0.5);
    border: 1px solid rgba(137, 180, 250, 0.2);
    border-radius: 20px;
    padding: 4px 12px;
    margin: 4px;
    font-size: 0.85em;
    font-weight: 500;
    color: #bac2de;
}

.sidebar-title {
    font-weight: 700;
    color: #b4befe;
    font-size: 1.4em;
    margin-bottom: 20px;
}
</style>
""", unsafe_allow_html=True)

# ── PDF Parser Helpers ───────────────────────────────────────────────────────
def extract_text_from_pdf(file_bytes) -> str:
    import io
    import pypdf
    try:
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        text = ""
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
        return text.strip()
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return ""

def parse_resume_text_to_json(resume_text: str) -> dict:
    from tools.resume_tailor import _extract_json
    prompt = f"""You are a professional resume parser. Parse the following raw text from a candidate's resume and convert it into a structured JSON matching the exact schema shown below.
    
    Target Schema:
    {{
      "name": "Candidate's full name",
      "title": "Professional title/headline",
      "contact": {{
        "location": "City, State, Country",
        "phone": "Phone number",
        "email": "Email address",
        "linkedin": "LinkedIn profile link",
        "github": "GitHub link"
      }},
      "summary": "Professional summary statement",
      "skills": {{
        "programming": ["Python", "SQL", etc.],
        "ml_ai": ["Machine Learning", "NLP", etc.],
        "llm_systems": ["LangChain", "RAG", etc.],
        "frameworks": ["FastAPI", "Streamlit", etc.],
        "vector_dbs": ["Pinecone", "ChromaDB", etc.],
        "data": ["Pandas", "PostgreSQL", etc.],
        "tools": ["Git", "Docker", "Linux", etc.]
      }},
      "projects": [
        {{
          "name": "Project Name",
          "tech": ["Python", "Docker", etc.],
          "bullets": [
            "Action-oriented bullet points describing achievements and engineering contribution",
            "Quantify impact where possible"
          ],
          "highlights": ["Keywords/highlights of the project"]
        }}
      ],
      "education": [
        {{
          "degree": "Degree and Major",
          "institution": "University / College name",
          "location": "City, State",
          "graduation": "Year or Expected Year",
          "coursework": ["Relevant coursework 1", "Relevant coursework 2"]
        }}
      ],
      "strengths": ["Strength 1", "Strength 2"],
      "target_roles": ["Role 1", "Role 2"],
      "work_preferences": {{
        "modes": ["Remote", "Hybrid", "On-site"],
        "open_to_internships": true,
        "open_to_full_time": true
      }}
    }}
    
    Ensure all skills are categorized correctly. If certain fields are not present in the text, leave them blank (empty strings, lists, or default values). Do NOT invent any facts or fake projects. Keep all details truthful to the text.
    
    RAW RESUME TEXT:
    {resume_text}
    
    Return ONLY valid JSON. No markdown formatting, no preambles, no trailing text.
    """
    try:
        raw = llm.invoke(prompt)
        raw_text = raw.content if hasattr(raw, "content") else str(raw)
        parsed = _extract_json(raw_text)
        return parsed
    except Exception as e:
        print(f"Error parsing resume via LLM: {e}")
        return {}

# ── Session State Setup ───────────────────────────────────────────────────────
if "search_results" not in st.session_state:
    st.session_state.search_results = []
if "tailored_data" not in st.session_state:
    st.session_state.tailored_data = {}  # job_id -> {tailored_resume, cold_email, score, explanation, pdf_path}
if "base_resume_text" not in st.session_state:
    # Load default base resume
    default_resume = _load_base_resume()
    st.session_state.base_resume_text = json.dumps(default_resume, indent=2)

# ── Sidebar Inputs ────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="sidebar-title">💼 Candidate Settings</div>', unsafe_allow_html=True)
    
    # Base Resume Section
    with st.expander("📝 Base Resume (JSON / PDF)", expanded=False):
        uploaded_file = st.file_uploader("Upload Resume (JSON or PDF)", type=["json", "pdf"])
        if uploaded_file is not None:
            file_name = uploaded_file.name.lower()
            if file_name.endswith(".json"):
                try:
                    uploaded_data = json.load(uploaded_file)
                    st.session_state.base_resume_text = json.dumps(uploaded_data, indent=2)
                    st.success("Resume updated from JSON file!")
                except Exception as e:
                    st.error(f"Invalid JSON: {e}")
            elif file_name.endswith(".pdf"):
                # We need a spinner for the extraction + LLM call
                with st.spinner("⏳ Extracting text and parsing PDF into structured JSON using AI..."):
                    pdf_bytes = uploaded_file.read()
                    extracted_text = extract_text_from_pdf(pdf_bytes)
                    if extracted_text:
                        parsed_json = parse_resume_text_to_json(extracted_text)
                        if parsed_json:
                            st.session_state.base_resume_text = json.dumps(parsed_json, indent=2)
                            st.success("Resume parsed from PDF successfully!")
                        else:
                            st.error("❌ Failed to parse PDF text using LLM. (This is typically due to API key errors, rate limits, or insufficient balance like OpenRouter 402 Payment Required. Please check your terminal logs and .env file.)")
                    else:
                        st.error("Failed to extract readable text from the uploaded PDF.")
                
        resume_input = st.text_area(
            "Edit Base Resume JSON",
            st.session_state.base_resume_text,
            height=250,
            key="edited_resume_json"
        )
        # Keep internal state updated
        st.session_state.base_resume_text = resume_input

    st.markdown("---")
    st.markdown('<div class="sidebar-title">🔍 Search Filters</div>', unsafe_allow_html=True)
    
    # Filter Controls
    role = st.text_input("Target Role", "AI Engineer", placeholder="e.g. LLM Engineer, Data Scientist")
    location = st.text_input("Location", "India", placeholder="e.g. Bangalore, Remote, USA")
    
    experience = st.selectbox(
        "Experience Level",
        [
            "Any",
            "Fresher/Entry Level (0-1 years)",
            "Mid Level (1-3 years)",
            "Senior Level (3-5 years)",
            "Lead/Director (5+ years)"
        ],
        index=0
    )
    
    date_posted = st.selectbox(
        "Date Posted",
        [
            "Anytime",
            "Past 24 Hours",
            "Past 3 Days",
            "Past Week",
            "Past Month"
        ],
        index=4
    )
    
    work_modes = st.multiselect(
        "Work Mode",
        ["Remote", "Hybrid", "On-site"],
        default=["Remote", "Hybrid", "On-site"]
    )
    
    max_jobs = st.slider("Max Search Results", min_value=5, max_value=20, value=10)

# ── Main Content Area ──────────────────────────────────────────────────────────
st.markdown('<h1 style="background: linear-gradient(135deg, #b4befe, #89b4fa); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 2.8em; font-weight: 700;">🤖 AI Job Search Agent Pro</h1>', unsafe_allow_html=True)
st.markdown('<p style="color: #a6adc8; font-size: 1.2em; font-weight: 300;">Search top job portals, score candidate fit with LLMs, and tailors professional PDF resumes on-demand.</p>', unsafe_allow_html=True)

st.divider()

# Validation before search
try:
    current_resume_dict = json.loads(st.session_state.base_resume_text)
    is_resume_valid = True
except Exception:
    is_resume_valid = False
    st.error("⚠️ The Base Resume JSON is currently invalid. Please fix it in the sidebar before searching.")

# Search trigger
col_search, col_spacer = st.columns([1, 3])
with col_search:
    search_clicked = st.button(
        "🔍 Search Matching Jobs",
        use_container_width=True,
        type="primary",
        disabled=not is_resume_valid
    )

if search_clicked and is_resume_valid:
    with st.spinner("⚡ Fetching jobs across LinkedIn, Naukri, Indeed, Apna, Internshala, and Glassdoor..."):
        # Map Date Posted filter to API compatible terms
        date_map = {
            "Anytime": "all",
            "Past 24 Hours": "today",
            "Past 3 Days": "3days",
            "Past Week": "week",
            "Past Month": "month"
        }
        api_date_posted = date_map.get(date_posted, "all")
        
        # Build preferences dict dynamically
        prefs = load_preferences()
        prefs["target_roles"] = [role]
        
        search_state = {
            "query": role,
            "location": location,
            "date_posted": api_date_posted,
            "work_modes": work_modes if work_modes else ["Remote", "Hybrid", "On-site"],
            "experience_level": experience,
            "apply_limit": max_jobs,
            "preferences": prefs,
            "applied": []
        }
        
        try:
            results = search_jobs(search_state)
            st.session_state.search_results = results.get("jobs_scored", [])
            st.session_state.tailored_data = {}  # Clear previous tailorings
            if st.session_state.search_results:
                st.success(f"🎯 Found {len(st.session_state.search_results)} matching job listings!")
            else:
                st.warning("No jobs found matching your criteria. Try adjusting the filters.")
        except Exception as e:
            st.error(f"Search failed: {e}")

# ── Render Search Results ──────────────────────────────────────────────────────
if st.session_state.search_results:
    st.markdown("### 📋 Top Job Openings Matching Your Profile")
    
    for idx, job in enumerate(st.session_state.search_results):
        job_id = job.get("id", f"job_{idx}")
        company = job.get("company", "Unknown Company")
        title = job.get("title", "Unknown Role")
        loc = job.get("location", "Unknown Location")
        score = job.get("score", 0.0)
        mode = job.get("work_mode", "On-site")
        exp_req = job.get("experience_required", "Not specified")
        url = job.get("url", "")
        description = job.get("description", "")
        
        # Display Job Card
        score_class = "score-badge" if score >= 0.7 else "score-badge-low"
        
        st.markdown(f"""
        <div class="job-card">
          <div style="display:flex; justify-content:space-between; align-items:flex-start;">
            <div>
              <h3 style="margin:0; font-size:1.4em; font-weight:600; color:#cdd6f4;">💼 {title}</h3>
              <p style="margin:6px 0 12px 0; font-size:1.1em; font-weight:600; color:#89b4fa;">🏢 {company}</p>
              <div>
                <span class="tag">📍 {loc}</span>
                <span class="tag">💻 {mode}</span>
                <span class="tag">⏳ {exp_req}</span>
              </div>
            </div>
            <div style="text-align:right;">
              <span class="{score_class}">⭐ Match Fit: {score * 100:.0f}%</span>
              <p style="margin-top:10px; font-size:0.85em; color:#a6adc8;">Source: {job.get('source', 'Web')}</p>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Action columns inside job layout
        c_apply, c_action = st.columns([1, 2])
        with c_apply:
            if url:
                st.link_button("🚀 Direct Apply", url, use_container_width=True)
            else:
                st.button("No Apply URL Available", disabled=True, use_container_width=True)
                
        with c_action:
            tailor_clicked = st.button(
                f"🧠 Tailor Resume & Draft Cold Email",
                key=f"tailor_btn_{job_id}",
                use_container_width=True
            )
            
        # Job Description Expander
        with st.expander("📝 View Full Job Description", expanded=False):
            st.markdown(description)
            
        # On-Demand Generation logic
        if tailor_clicked:
            with st.spinner("⏳ LLM is analyzing requirements, tailoring experience points, and writing cold email..."):
                # 1. Parse JD using orchestrator model logic
                jd_state = {"current_job": job, "jd_parsed": {}}
                parsed_res = parse_jd_node(jd_state)
                parsed_jd_data = parsed_res.get("jd_parsed", {})
                
                # 2. Get LLM fit evaluation
                fit_state = {
                    "jd_parsed": parsed_jd_data,
                    "base_resume": current_resume_dict,
                    "current_job": job,
                    "job_score": None,
                    "score_explanation": ""
                }
                fit_res = score_job_node(fit_state)
                llm_score = fit_res.get("job_score", score)
                llm_explanation = fit_res.get("score_explanation", "Fit evaluation complete.")
                
                # 3. Tailor resume JSON
                tailored_res = tailor_resume(current_resume_dict, parsed_jd_data, llm)
                tailored_resume_dict = tailored_res.get("tailored_resume", current_resume_dict)
                
                # 4. Generate cold outreach email
                email_res = generate_cold_email(parsed_jd_data, tailored_resume_dict, llm)
                cold_email = email_res.get("cold_email", "Email drafting failed.")
                
                # 5. Compile to PDF using ReportLab
                pdf_output_name = f"tailored_resume_{job_id}.pdf"
                pdf_output_path = os.path.join(ROOT, "data", "resumes", pdf_output_name)
                
                try:
                    pdf_path = generate_resume_pdf(tailored_resume_dict, pdf_output_path)
                    pdf_success = True
                except Exception as e:
                    pdf_path = ""
                    pdf_success = False
                    st.error(f"PDF generation failed: {e}")
                    
                # Save generated details to state
                st.session_state.tailored_data[job_id] = {
                    "tailored_resume": tailored_resume_dict,
                    "cold_email": cold_email,
                    "score": llm_score,
                    "explanation": llm_explanation,
                    "pdf_path": pdf_path if pdf_success else None
                }
                
        # If tailored data is present for this job, render it under the card
        if job_id in st.session_state.tailored_data:
            data = st.session_state.tailored_data[job_id]
            
            st.markdown("---")
            st.markdown(f"#### 🎯 Precise AI Match Score: **{data['score']*100:.0f}%**")
            st.info(f"💡 **AI Justification:** {data['explanation']}")
            
            tab_resume, tab_email = st.tabs(["📎 Tailored Resume PDF", "✉️ Cold Outreach Email"])
            
            with tab_resume:
                # PDF Download button
                pdf_path = data.get("pdf_path")
                if pdf_path and os.path.exists(pdf_path):
                    with open(pdf_path, "rb") as f:
                        pdf_bytes = f.read()
                    st.download_button(
                        label="📥 Download Tailored Resume PDF",
                        data=pdf_bytes,
                        file_name=f"{company.replace(' ', '_')}_{title.replace(' ', '_')}_Resume.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                else:
                    st.warning("PDF download unavailable.")
                    
                # Show JSON structure
                with st.expander("Inspect Tailored Resume Structure (JSON)"):
                    st.json(data["tailored_resume"])
                    
            with tab_email:
                st.text_area(
                    "Cold Email Draft",
                    data["cold_email"],
                    height=250,
                    key=f"email_txt_area_{job_id}"
                )
                st.code(data["cold_email"], language="markdown")
                st.caption("📋 Copy code snippet above to copy full cold email text.")
                
        st.markdown("<div style='height:30px;'></div>", unsafe_allow_html=True)
        st.divider()
else:
    # Landing state
    st.info("👋 Welcome! Set your preferences in the sidebar and click **Search Matching Jobs** to discover matching job opportunities.")
