# 🚀 Autonomous Job AI Agent Pro
### *Smart Job Discovery, AI Fit Evaluation, PDF Resume Tailoring, & Cold Outreach Automation*

An intelligent, multi-agent career assistant that automates the job application lifecycle. The agent dynamically parses your base resume (JSON or PDF), aggregates live listings from top portals (LinkedIn, Naukri, Indeed, Apna, Internshala, and Glassdoor), scores matches using LLMs, and generates tailored resumes (downloadable as PDF) and custom cold emails on-demand.

---

## 🗺️ System Workflow

The agent operates through an interactive web-based dashboard:

```
[ Upload JSON/PDF Resume ] 
           │
           ▼
[ Configure Search Filters ] (Role, Location, Experience, Date Posted, Work Mode)
           │
           ▼
[ Query Job Aggregators ] (JSearch API / SerpAPI Google Jobs / Mock Fallback)
           │
           ▼
[ Render Top 10 Scored Jobs ] (Collapsible Job Descriptions & Basic Company Info)
           │
           ▼
[ Select Job & Tailor ] (On-Demand LLM Fit Analysis, Custom Resume Bullets, & PDF Compile)
           │
     ┌─────┴──────────┐
     ▼                ▼
[ Download Tailored ]  [ Copy Custom Cold ]
[ Resume PDF ]         [ Email Draft ]
```

---

## ✨ Key Features

- 🔍 **Dynamic Job Discovery**: Queries major portals via RapidAPI (JSearch) and SerpAPI (Google Jobs).
- ⚙️ **Advanced Search Constraints**: Filters live results by Job Title, Location, Date Posted (24h, 3d, week, month), Experience Level (Entry to Lead), and Work Mode (Remote, Hybrid, On-site).
- 📎 **AI PDF Resume Ingestion**: Upload an existing PDF resume. The system extracts text via `pypdf` and uses LLM structuring to populate the settings editor automatically.
- 🎯 **LLM Match Scoring**: Evaluates candidate fit, providing a precise percentage match score and clear semantic justification.
- 📄 **On-Demand PDF Tailoring**: Dynamically re-ranks experience bullets, rewrites the summary with targeted ATS keywords, and compiles the result into a clean, professional PDF using **ReportLab**.
- ✉️ **Recruiter Outreach Drafts**: Writes concise, customized cold outreach emails matching the recruiter name and required qualifications.
- 🛡️ **Resilient Fallback Modes**:
  - Automatically activates rule-based email templates if LLM APIs time out or return billing limits (e.g. 402 Client Error).
  - Handles stdout/stderr UTF-8 reconfigurations on Windows to prevent Unicode CP1252 exceptions.

---

## 🏗️ Architecture & Tech Stack

- **Frontend**: Streamlit (Modern dark theme, responsive sidebars, interactive tabs)
- **Backend API**: FastAPI (REST endpoints & WebSocket live log streamer)
- **Orchestration**: LangGraph (Agentic state machine)
- **Language Models**: OpenRouter API (`deepseek/deepseek-chat` default) & Groq
- **PDF Compiler**: ReportLab (Flowable document rendering)
- **Scrapers/APIs**: RapidAPI JSearch, SerpAPI Google Jobs
- **Database**: SQLite (Tracker for historical applications)

---

## ⚙️ Environment Variables (`.env`)

Create a `.env` file in the root directory:

```env
# Search Portals API Keys
SERPAPI_KEY=your_serp_api_key
RAPIDAPI_KEY=your_rapidapi_jsearch_key

# Language Model Configurations
OPENROUTER_API_KEY=your_openrouter_api_key
OPENROUTER_MODEL=deepseek/deepseek-chat

# System Variables
DB_PATH=db/tracker.db
APPROVAL_TIMEOUT_SECONDS=1800
```

---

## 🚀 Getting Started

Follow these steps to clean and recreate your environment and run the application locally.

### 1. Recreate the Environment (Recommended on Windows)
If your virtual environment points to an obsolete Python interpreter path, recreate it:

```powershell
# Deactivate current shell
deactivate

# Remove the broken directory
Remove-Item -Recurse -Force .\venv

# Create a new environment using system python (3.11+)
python -m venv venv

# Activate the new environment
.\venv\Scripts\Activate.ps1
```

### 2. Install Project Dependencies
Install standard requirements along with PDF processing and formatting modules:
```powershell
pip install -r requirements.txt
pip install reportlab pypdf groq
```

### 3. Launch the Streamlit Dashboard
Start the front-end server from the project directory:
```powershell
streamlit run frontend/app.py
```
Open [http://localhost:8501](http://localhost:8501) in your browser.

### 4. Run the FastAPI Backend (Optional)
To run the REST interface alongside Streamlit:
```powershell
uvicorn api.main:app --port 8000 --reload
```

---

## 📂 Project Structure

```
├── agent/
│   ├── orchestrator.py    # LangGraph definition & pipeline nodes
│   ├── state.py           # TypedDict schema representing AgentState
│   ├── approval_store.py  # File-backed JSON approval manager
│   └── preferences.json   # Base user search preferences
├── api/
│   └── main.py            # FastAPI endpoints & websocket stream logs
├── data/
│   ├── base_resume.json   # Default candidate profile JSON
│   └── resumes/           # Storage folder for compiled tailored PDFs
├── frontend/
│   └── app.py             # Main Streamlit web dashboard
└── tools/
    ├── pdf_generator.py   # ReportLab PDF compiler
    ├── email_sender.py    # Cold outreach draft generator (LLM & template)
    ├── resume_tailor.py   # ATS keyword optimization node
    └── job_search_parser.py # JSearch, SerpAPI, and Mock aggregators
```

---

## 📜 License

MIT License. Feel free to use, modify, and distribute this software.

---

## 👨‍💻 Author
**Shivam Sharma**
- GitHub: [@agent-shivam](https://github.com/agent-shivam)
- LinkedIn: [Shivam Sharma](https://www.linkedin.com/in/shivam-sharma-8467a7358)
