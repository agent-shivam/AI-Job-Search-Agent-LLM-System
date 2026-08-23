"""
resume_tailor.py
----------------
Tailors the base resume dict to the parsed job description.

Fixes:
  - llm.invoke() returns AIMessage; extract .content before JSON parsing
  - Safe key access for mixed-case JD fields
  - Returns {"tailored_resume": <dict>} for LangGraph state merge
"""

import json
import re


from typing import Union
from langchain_core.messages import AIMessage

def _extract_json(text: Union[str, AIMessage]) -> dict:
    """Try to extract a JSON object from an LLM response string."""

    # ✅ Safely normalize input
    if not isinstance(text, str):
        text = getattr(text, "content", str(text))

    cleaned = re.sub(r"```(?:json)?", "", str(text)).strip().rstrip("`").strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except:
                pass

    return {}


def tailor_resume(base_resume: dict, jd_data: dict, llm) -> dict:
    """
    Returns {"tailored_resume": <dict>} for LangGraph state merge.
    """
    job_title    = jd_data.get("Job_Title") or jd_data.get("job_title", "the role")
    company      = jd_data.get("company_name", "the company")
    ats_keywords = jd_data.get("ats_keywords", [])

    required_skills = (
        jd_data.get("required_skills")
        or jd_data.get("Required Skills")
        or jd_data.get("skills")
        or []
    )
    if isinstance(required_skills, str):
        required_skills = [required_skills]

    prompt = f"""You are an expert resume writer. Tailor the following resume JSON to better match the job description.

Rules:
- Inject these ATS keywords naturally where relevant: {ats_keywords}
- Reorder bullet points to prioritize the most relevant experience and skills for the job.
- Rewrite the "summary" field to better reflect the candidate's fit for this specific role.
- Keep it truthful — only rephrase and reorder existing information, do NOT invent new facts.
- Return ONLY a valid JSON object that matches the exact schema of the BASE RESUME below.
- Do NOT wrap in markdown code fences.

BASE RESUME:
{json.dumps(base_resume, indent=2)}

TARGET ROLE: {job_title} at {company}
REQUIRED SKILLS: {', '.join(required_skills)}
"""

    result = llm.invoke(prompt)

    # Extract string content from AIMessage
    raw = result.content if hasattr(result, "content") else str(result)

    tailored = _extract_json(raw)

    if not tailored:
        print("⚠️ resume_tailor: LLM returned invalid JSON — using base_resume as fallback")
        tailored = base_resume

    return {"tailored_resume": tailored}
