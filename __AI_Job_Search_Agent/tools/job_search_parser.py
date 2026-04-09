"""
job_search_parser.py
--------------------
Job search via real APIs (no scraping — job sites block server-side requests).

Priority order:
  1. JSearch API via RapidAPI  (set RAPIDAPI_KEY in .env)  — free 200 req/month
  2. SerpAPI Google Jobs        (set SERPAPI_KEY in .env)   — free 100 req/month
  3. Mock data fallback         (always works, for testing)

Get free keys:
  JSearch:  https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch  (free tier)
  SerpAPI:  https://serpapi.com  (100 free searches/month)
"""

import os
import json
import time
import hashlib
import httpx
from typing import Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _job_id(job: dict) -> str:
    base = f"{job.get('title','')}{job.get('company','')}{job.get('url','')}"
    return hashlib.md5(base.encode()).hexdigest()[:12]


def _score_job(job: dict, prefs: dict) -> float:
    title = job.get("title", "").lower()
    desc  = job.get("description", "").lower()

    score = 0.3  # base score (IMPORTANT)

    # 🎯 Title-based boost (VERY IMPORTANT)
    if any(k in title for k in ["ai", "ml", "llm", "data"]):
        score += 0.3

    # 🎯 Role match
    for role in prefs.get("target_roles", []):
        if role.lower() in title:
            score += 0.2
            break

    # 🎯 Keywords
    for kw in prefs.get("keywords_boost", ["python", "llm", "langchain"]):
        if kw in title:
            score += 0.1
        if kw in desc:
            score += 0.05

    # 🎯 AI relevance
    if any(k in desc for k in ["machine learning", "llm", "generative ai"]):
        score += 0.1

    return round(min(score, 1.0), 2)


# ── Strategy 1: JSearch via RapidAPI ─────────────────────────────────────────

def search_jsearch(query: str, location: str, num_pages: int = 2) -> List[dict]:
    """
    JSearch API — https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch
    Free tier: 200 requests/month. Returns full job descriptions.
    """
    api_key = os.getenv("RAPIDAPI_KEY", "")
    if not api_key:
        return []

    jobs = []
    headers = {
        "X-RapidAPI-Key":  api_key,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
    }

    for page in range(1, num_pages + 1):
        try:
            r = httpx.get(
                "https://jsearch.p.rapidapi.com/search",
                params={
                    "query":      f"{query} in {location}",
                    "page":       str(page),
                    "num_pages":  "1",
                    "date_posted": "month",
                },
                headers=headers,
                timeout=20,
            )
            r.raise_for_status()
            data = r.json().get("data", [])

            for item in data:
                desc = item.get("job_description", "") or ""
                jobs.append({
                    "title":       item.get("job_title", ""),
                    "company":     item.get("employer_name", ""),
                    "url":         item.get("job_apply_link") or item.get("job_url", ""),
                    "source":      "jsearch",
                    "description": desc,
                    "location":    item.get("job_city", "") + ", " + item.get("job_country", ""),
                    "score":       0.0,
                    "id":          item.get("job_id", ""),
                })

        except Exception as e:
            print(f"⚠️ JSearch page {page} error: {e}")
            break

        time.sleep(0.5)

    print(f"📦 JSearch: {len(jobs)} jobs")
    return jobs


# ── Strategy 2: SerpAPI Google Jobs ──────────────────────────────────────────

def search_serpapi(query: str, location: str) -> List[dict]:
    """
    SerpAPI Google Jobs — https://serpapi.com/google-jobs-api
    Free tier: 100 searches/month.
    """
    api_key = os.getenv("SERPAPI_KEY", "")
    if not api_key:
        return []

    jobs = []
    try:
        r = httpx.get(
            "https://serpapi.com/search",
            params={
                "engine":   "google_jobs",
                "q":        f"{query} {location}",
                "api_key":  api_key,
                "hl":       "en",
                "gl":       "in",
                "chips":    "date_posted:month",
            },
            timeout=20,
        )
        r.raise_for_status()
        items = r.json().get("jobs_results", [])

        for item in items:
            desc_parts = []
            for ext in item.get("job_highlights", []):
                title_str = ext.get("title", "")
                items_str = "\n".join(ext.get("items", []))
                desc_parts.append(f"{title_str}:\n{items_str}")
            desc = "\n\n".join(desc_parts) or item.get("description", "")

            apply_options = item.get("apply_options", [])
            url = apply_options[0].get("link", "") if apply_options else ""

            jobs.append({
                "title":       item.get("title", ""),
                "company":     item.get("company_name", ""),
                "url":         url,
                "source":      "serpapi",
                "description": desc,
                "location":    item.get("location", ""),
                "score":       0.0,
                "id":          "",
            })

    except Exception as e:
        print(f"⚠️ SerpAPI error: {e}")

    print(f"📦 SerpAPI: {len(jobs)} jobs")
    return jobs


# ── Strategy 3: Mock fallback ─────────────────────────────────────────────────

MOCK_JOBS = [
    {
        "title": "AI/ML Engineer",
        "company": "TechCorp India",
        "url": "https://example.com/jobs/ai-ml-engineer-techcorp",
        "source": "mock",
        "location": "Bangalore, India",
        "description": """We are looking for an AI/ML Engineer to join our team.

Responsibilities:
- Design and implement machine learning models and LLM-based pipelines
- Work with Python, PyTorch, TensorFlow, LangChain
- Deploy models using FastAPI and Docker
- Collaborate with data engineers on ETL pipelines

Requirements:
- 2+ years experience in ML/AI engineering
- Strong Python skills
- Experience with LLMs, RAG, vector databases
- Knowledge of MLOps practices (MLflow, Kubeflow)
- Familiarity with AWS/GCP

Nice to have:
- Experience with LangChain, LlamaIndex
- Published research or open-source contributions

Salary: 12-20 LPA
Location: Bangalore (Hybrid)

To apply, contact hr@techcorp.example.com""",
    },
    {
        "title": "Senior Machine Learning Engineer",
        "company": "DataDriven Solutions",
        "url": "https://example.com/jobs/senior-ml-engineer-datadriven",
        "source": "mock",
        "location": "Hyderabad, India",
        "description": """DataDriven Solutions is hiring a Senior ML Engineer.

About the role:
You'll lead the development of our AI products, working on NLP, computer vision, and generative AI systems.

Key Skills Required:
- Python, PyTorch, Hugging Face Transformers
- LLM fine-tuning (LoRA, QLoRA, PEFT)
- Retrieval-Augmented Generation (RAG) systems
- Vector databases (Pinecone, Weaviate, FAISS)
- MLflow / experiment tracking
- REST API development (FastAPI)

Experience: 4+ years in ML/AI
Education: B.Tech/M.Tech in CS, EE, or related

Recruiter: Priya Sharma
Email: priya.sharma@datadriven.example.com
Salary: 25-35 LPA""",
    },
    {
        "title": "Generative AI Engineer",
        "company": "InnovateTech",
        "url": "https://example.com/jobs/genai-engineer-innovatetech",
        "source": "mock",
        "location": "Mumbai, India (Remote OK)",
        "description": """InnovateTech is looking for a Generative AI Engineer.

Responsibilities:
- Build LLM-powered applications and agents (LangChain, LangGraph)
- Implement prompt engineering and chain-of-thought techniques
- Develop RAG pipelines with vector search
- Fine-tune open-source LLMs (Llama, Mistral)
- API integration and deployment

Must Have:
- Python expertise
- LangChain / LlamaIndex / LangGraph
- OpenAI / Anthropic / Gemini API experience
- Prompt engineering skills
- Git and CI/CD

Preferred:
- Experience with Streamlit, Gradio for demos
- Knowledge of Kubernetes
- Prior startup experience

CTC: 15-28 LPA
Contact: careers@innovatetech.example.com""",
    },
    {
        "title": "NLP Research Engineer",
        "company": "AI Research Labs",
        "url": "https://example.com/jobs/nlp-engineer-airesearch",
        "source": "mock",
        "location": "Delhi NCR, India",
        "description": """AI Research Labs — NLP Research Engineer

We're building next-generation conversational AI.

Requirements:
- Masters or PhD in Computer Science, NLP, or related field
- Experience with transformer architectures (BERT, GPT, T5)
- Strong Python + PyTorch skills
- Publication record is a plus
- Experience with text classification, NER, summarization

Responsibilities:
- Research and implement state-of-the-art NLP models
- Build training pipelines for LLM fine-tuning
- Evaluate models on benchmark datasets
- Write technical reports and documentation

ATS Keywords: NLP, transformer, BERT, GPT, PyTorch, Python, fine-tuning, NER

Salary: 20-40 LPA (depending on experience)""",
    },
    {
        "title": "Full Stack Developer (AI Products)",
        "company": "StartupXYZ",
        "url": "https://example.com/jobs/fullstack-ai-startupxyz",
        "source": "mock",
        "location": "Pune, India",
        "description": """Join StartupXYZ as a Full Stack Developer for AI Products.

Tech Stack:
- Frontend: React, Next.js, TypeScript
- Backend: Python, FastAPI, Node.js
- AI: OpenAI API, LangChain integrations
- DB: PostgreSQL, Redis, Pinecone
- Cloud: AWS (EC2, S3, Lambda)

You'll build:
- AI-powered SaaS features
- Real-time chat interfaces with LLM backends
- Dashboard analytics

Requirements:
- 3+ years full stack experience
- Python + JavaScript/TypeScript proficiency
- Prior work with AI/LLM APIs a strong plus

Salary: 18-28 LPA""",
    },
]


def search_mock(query: str, location: str) -> List[dict]:
    """Always-available fallback with realistic AI job data for testing."""
    print("📦 Using mock job data (add RAPIDAPI_KEY or SERPAPI_KEY to .env for real jobs)")
    results = []
    q_lower = query.lower()
    for job in MOCK_JOBS:
        # Simple relevance filter
        title_low = job["title"].lower()
        desc_low  = job["description"].lower()
        if any(w in title_low or w in desc_low for w in q_lower.split()):
            results.append({**job, "score": 0.0})
    return results if results else [{**j, "score": 0.0} for j in MOCK_JOBS]


# ── Main search function ───────────────────────────────────────────────────────

def search_jobs(state) -> Dict:
    query    = state.get("query", "AI Engineer")
    location = state.get("location", "India")
    prefs    = state.get("preferences", {})
    apply_limit = prefs.get("apply_limit_per_day", 10)
    applied_urls = {j.get("url") for j in state.get("applied", [])}

    print(f"\n🔍 Searching: '{query}' in '{location}'")

    # ── Try APIs in priority order ──────────────────────────────────────────
    raw_jobs: List[dict] = []

    # 1. JSearch
    jsearch_jobs = search_jsearch(query, location)
    if jsearch_jobs:
        raw_jobs.extend(jsearch_jobs)
        print(f"✅ JSearch returned {len(jsearch_jobs)} jobs")

    # 2. SerpAPI (complement or fallback)
    if len(raw_jobs) < 5:
        serp_jobs = search_serpapi(query, location)
        if serp_jobs:
            raw_jobs.extend(serp_jobs)
            print(f"✅ SerpAPI returned {len(serp_jobs)} jobs")

    # 3. Mock fallback
    if not raw_jobs:
        raw_jobs = search_mock(query, location)

    # ── Normalize and score ─────────────────────────────────────────────────
    seen_urls = set()
    scored    = []

    for job in raw_jobs:
        url = job.get("url", "")
        if url and url in applied_urls:
            continue
        if url in seen_urls:
            continue
        if url:
            seen_urls.add(url)

        # Ensure ID
        if not job.get("id"):
            job["id"] = _job_id(job)

        job["score"] = _score_job(job, prefs)
        scored.append(job)

    scored.sort(key=lambda x: x["score"], reverse=True)

    print(f"✅ Total unique jobs: {len(scored)}")
    for j in scored[:apply_limit]:
        has_jd = "✅ JD" if len(j.get("description","")) > 100 else "⚠️ no JD"
        print(f"   ⭐ {j['score']:.2f} | {j['title']} @ {j['company']} [{has_jd}]")

    return {
        "jobs_found":  scored,
        "jobs_scored": scored[:apply_limit],
    }


# ── Standalone JD fetch (kept for parse_jd node belt-and-suspenders) ─────────

def fetch_job_description(url: str, retries: int = 2) -> str:
    """
    Best-effort HTTP fetch. Works for some job boards.
    Many block server requests — that's why we use APIs above.
    """
    if not url or not url.startswith("http") or "example.com" in url:
        return ""

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    for attempt in range(retries):
        try:
            r = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
            if r.status_code == 200 and len(r.text) > 500:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(r.text, "html.parser")
                for tag in soup(["script", "style", "noscript"]):
                    tag.extract()
                for sel in [".job-description", "#job-description", "article", "main", ".description"]:
                    el = soup.select_one(sel)
                    if el:
                        text = el.get_text(separator="\n").strip()
                        if len(text) > 200:
                            return text
                text = soup.get_text(separator="\n").strip()
                return text if len(text) > 200 else ""
        except Exception:
            pass
        time.sleep(1)

    return ""


# ── Standalone parse_jd ───────────────────────────────────────────────────────
def parse_jd(url: str, llm) -> dict:
    jd_text = (fetch_job_description(url) or "")[:1200]

    if not jd_text:
        return {
            "jd_parsed": {},
            "parse_failed": True
        }

    import re
    prompt = f"""Extract from this job description and return ONLY valid JSON:

{{"Job_Title":"","company_name":"","required_skills":[],"experience_level":"",
"ats_keywords":[],"nice_to_have":[],"recruiter_name":"","recruiter_email":"","tools":[]}}

JD:
{jd_text[:2000]}
"""

    try:
        raw = llm.invoke(prompt)
        content = getattr(raw, "content", str(raw)).strip()
        if not content:
            raise ValueError("Empty LLM response")

        cleaned = re.sub(r"```(?:json)?", "", content).strip().rstrip("`").strip()
        match   = re.search(r"\{.*\}", cleaned, re.DOTALL)

        parsed = json.loads(match.group(0) if match else cleaned)

        return {
            "jd_parsed": parsed,
            "parse_failed": False
        }

    except Exception as e:
        print(f"❌ parse_jd LLM failed: {e}")
        return {
            "jd_parsed": {},
            "parse_failed": True
        }