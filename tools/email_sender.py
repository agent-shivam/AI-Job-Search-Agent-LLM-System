"""
email_sender.py
---------------
Generates a cold outreach email using the LLM.

Fixes:
  - llm.invoke() returns AIMessage; extract .content before returning
  - Safe key access for mixed-case JD fields
  - Returns {"cold_email": <str>} for LangGraph state merge
"""


def generate_cold_email(jd_data: dict, resume: dict, llm) -> dict:
    """
    Returns {"cold_email": <str>} for LangGraph state merge.
    """
    job_title = jd_data.get("Job_Title") or jd_data.get("job_title", "the role")
    company   = jd_data.get("company_name", "the company")
    exp_level = jd_data.get("Experience Level") or jd_data.get("experience_level", "")

    required_skills = (
        jd_data.get("required_skills")
        or jd_data.get("Required Skills")
        or jd_data.get("skills")
        or []
    )
    if isinstance(required_skills, str):
        required_skills = [required_skills]

    recruiter_name = jd_data.get("recruiter_name", "Hiring Manager")
    candidate_name = resume.get("name", "")
    summary        = resume.get("summary", "")

    prompt = f"""You are a professional career coach and email copywriter.

Write a concise cold email from {candidate_name} to {recruiter_name} at {company}.

Guidelines:
- No more than 150 words, 3 short paragraphs.
- Paragraph 1: Express genuine interest in the {job_title} role at {company}.
- Paragraph 2: Highlight 2-3 key qualifications from the resume that match the job.
- Paragraph 3: Clear Call to Action — request a 15-min call.
- Naturally weave in these ATS keywords: {jd_data.get('ats_keywords', [])[:5]}
- Tone: Professional, enthusiastic, confident — NOT arrogant.

CANDIDATE SUMMARY: {summary}
REQUIRED SKILLS:   {', '.join(required_skills)}
EXPERIENCE LEVEL:  {exp_level}

Return ONLY the email body — no subject line, no preamble.
"""

    result = llm.invoke(prompt)

    # llm.invoke returns AIMessage; extract .content
    if hasattr(result, "content"):
        email_body = result.content
    elif isinstance(result, dict):
        email_body = str(result)
    else:
        email_body = str(result)

    email_text = email_body.strip()
    if not email_text:
        # Local template fallback if API has insufficient balance or rate-limited
        email_text = f"""Dear {recruiter_name},

I hope this email finds you well. I am writing to express my strong interest in the {job_title} position at {company}.

Based on my background, I have hands-on experience in software engineering and AI projects, particularly in LLM systems, RAG pipelines, and machine learning models. I am confident that my skills in these areas will allow me to contribute effectively to your team.

I would welcome the opportunity to discuss how my qualifications align with your requirements. I have attached my tailored resume for your review and would love to schedule a brief 15-minute call.

Best regards,
{candidate_name}"""
        print("⚠️ email_sender: LLM returned empty response — using fallback template email")

    return {"cold_email": email_text}
