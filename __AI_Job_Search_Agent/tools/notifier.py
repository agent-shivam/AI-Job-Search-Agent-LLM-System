"""
notifier.py
-----------
All Telegram communication for the Job AI Agent:
  - Approval request cards with inline buttons
  - Long-poll callback waiting (approve / skip / edit)
  - Result notifications
  - Follow-up reminders

Bug fixes:
  - notify_user() signature mismatch with orchestrator call — fixed arg order
  - BOT_TOKEN / CHAT_ID loaded at call time (not import time) so .env works
"""

import os
import time
import logging
import httpx
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)


def _tokens():
    """Fetch tokens at call time so dotenv is respected."""
    return os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")


def _base_url():
    token, _ = _tokens()
    return f"https://api.telegram.org/bot{token}"


# ── Raw API call ──────────────────────────────────────────────────────────────

def _api(endpoint: str, payload: dict = {}, method: str = "POST") -> dict:
    url = f"{_base_url()}/{endpoint}"
    try:
        if method == "GET":
            r = httpx.get(url, params=payload, timeout=35)
        else:
            r = httpx.post(url, json=payload, timeout=10)
        data = r.json()
        if not data.get("ok"):
            log.warning(f"Telegram API not OK ({endpoint}): {data.get('description')}")
        return data
    except httpx.TimeoutException:
        log.warning(f"Telegram timeout on {endpoint}")
        return {}
    except Exception as e:
        log.error(f"Telegram error ({endpoint}): {e}")
        return {}


# ── Offset store ──────────────────────────────────────────────────────────────

_last_offset: Optional[int] = None


def _get_updates(timeout: int = 30) -> list:
    global _last_offset
    _, chat_id = _tokens()
    params: dict = {
        "timeout":         timeout,
        "allowed_updates": ["callback_query"],
    }
    if _last_offset is not None:
        params["offset"] = _last_offset

    data = _api("getUpdates", params, method="GET")
    updates = data.get("result", [])

    if updates:
        _last_offset = updates[-1]["update_id"] + 1

    return updates


def _ack_callback(callback_id: str, text: str = "") -> None:
    _api("answerCallbackQuery", {
        "callback_query_id": callback_id,
        "text":              text,
        "show_alert":        False
    })


def _edit_message_text(message_id: int, new_text: str) -> None:
    _, chat_id = _tokens()
    _api("editMessageText", {
        "chat_id":    chat_id,
        "message_id": message_id,
        "text":       new_text
    })


def _score_bar(score: float) -> str:
    filled = round(score * 10)
    return "[" + "#" * filled + "-" * (10 - filled) + "]"


# ── notify_user — called from send_msg_to_telegram_node ──────────────────────
# Fixed: orchestrator passes (company, Job_Title, score, base_resume, job_url, email_preview)

def notify_user(
    company_name:  str,
    job_title:     str,
    score:         float,
    base_resume:   dict,
    job_url:       str,
    email_preview: str
) -> None:
    _, chat_id = _tokens()
    bar = _score_bar(score)
    text = (
        f"Job Find!\n\n"
        f"Company       : {company_name}\n"
        f"Role          : {job_title}\n"
        f"Match Score   : {bar} {score:.0%}\n"
        f"URL           : {job_url}\n\n"
        f"Email Preview :\n{email_preview[:400]}"
    )
    _api("sendMessage", {"chat_id": chat_id, "text": text})


# ── Send approval request card ────────────────────────────────────────────────

def send_approval_request(
    company:        str,
    role:           str,
    score:          float,
    job_url:        str,
    email_preview:  str,
    resume_summary: str,
    job_id:         str
) -> Optional[int]:
    _, chat_id = _tokens()
    bar  = _score_bar(score)
    text = (
        f"Application ready\n\n"
        f"Company : {company}\n"
        f"Role    : {role}\n"
        f"Score   : {bar} {score:.0%}\n"
        f"URL     : {job_url}\n\n"
        f"Resume summary:\n{resume_summary[:200]}\n\n"
        f"Email draft:\n{email_preview[:300]}\n\n"
        f"job_id: {job_id}"
    )
    payload = {
        "chat_id": chat_id,
        "text":    text,
        "reply_markup": {
            "inline_keyboard": [[
            {"text": "⏭️ Skip",    "callback_data": f"skip:{job_id}"},
            {"text": "📄 Details", "callback_data": f"details:{job_id}"}
        ]]
        }
    }
    resp   = _api("sendMessage", payload)
    msg_id = resp.get("result", {}).get("message_id")
    log.info(f"Approval card sent — job_id={job_id}, message_id={msg_id}")
    return msg_id

def _format_details(
    company: str,
    role: str,
    job_url: str,
    email_preview: str,
    resume_summary: str,
    hr_email: str = "Not available",
    jd: str = "Not available"
) -> str:
    return (
        f"📄 FULL JOB DETAILS\n\n"
        f"Company : {company}\n"
        f"Role    : {role}\n\n"
        f"🔗 Apply Link:\n{job_url}\n\n"
        f"📧 HR Email:\n{hr_email}\n\n"
        f"📝 Job Description:\n{jd[:500]}\n\n"
        f"✉️ Cold Mail:\n{email_preview[:500]}\n\n"
        f"📎 Resume:\n{resume_summary[:300]}"
    )



# ── Wait for approval ─────────────────────────────────────────────────────────
SKIPPED_JOBS = set()  # 🔥 global memory (replace with DB later)




def wait_for_approval(
    job: dict,
    message_id: Optional[int] = None,
    timeout_seconds: int = 1800
) -> tuple:

    job_id = job.get("id", "")

    company = job.get("company") or "Unknown Company"
    role = job.get("role") or "Unknown Role"
    job_url = job.get("url") or "No URL"
    email_preview = job.get("email") or "No email generated"
    resume_summary = job.get("resume") or "No resume summary"
    hr_email = job.get("hr_email") or "Not available"
    jd = job.get("jd") or "Not available"

    deadline = time.time() + timeout_seconds
    log.info(f"Waiting for approval: job_id={job_id}, timeout={timeout_seconds}s")

    while time.time() < deadline:
        remaining    = deadline - time.time()
        poll_timeout = min(30, int(remaining))
        if poll_timeout <= 0:
            break

        updates = _get_updates(timeout=poll_timeout)

        for update in updates:
            cb = update.get("callback_query")
            if not cb:
                continue

            data        = cb.get("data", "")
            callback_id = cb.get("id", "")
            from_user   = cb.get("from", {}).get("first_name", "User")

            if not data.endswith(f":{job_id}"):
                _ack_callback(callback_id)
                continue

            action = data.split(":")[0]

            # ✅ ACK
            ack_text = {
                "skip": "⏭ Skipped. Finding better job...",
                "details": "📄 Opening full details..."
            }.get(action, "Got it.")
            _ack_callback(callback_id, text=ack_text)

            # ───────────── DETAILS FLOW ─────────────
            if action == "details":
                details_text = _format_details(
                    company=company,
                    role=role,
                    job_url=job_url,
                    email_preview=email_preview,
                    resume_summary=resume_summary,
                    hr_email=hr_email,
                    jd=jd
                )

                # ✅ Send NEW message (don’t kill buttons)
                _api("sendMessage", {
                    "chat_id": _tokens()[1],
                    "text": details_text
                })

                log.info(f"Details viewed: job_id={job_id}")
                continue  # 🔥 keep loop alive

            # ───────────── SKIP FLOW ─────────────
            
            if action == "skip":

                # ✅ ONLY store locally if you want (optional)
                SKIPPED_JOBS.add(job_id)

                if message_id:
                    _edit_message_text(
                        message_id,
                        f"[SKIPPED] Skipped by {from_user}."
                    )

                log.info(f"Job skipped: job_id={job_id}")

                # 🔥 IMPORTANT: JUST RETURN
                return False, "skip"
                    

                

    # ───────────── TIMEOUT ─────────────
    log.warning(f"Approval timeout after {timeout_seconds}s for job_id={job_id}")

    if message_id:
        _edit_message_text(message_id, "[TIMEOUT] No response — job skipped.")

    return False, "timeout"

# ── Post-apply notification ───────────────────────────────────────────────────

def notify(
    company:       str,
    role:          str,
    score:         float,
    base_resume:   dict,
    job_url:       str,
    email_preview: str,
    success:       bool = True,
    method:        str  = "",
    error:         Optional[str] = None,
    dry_run:       bool = False
) -> None:
    _, chat_id = _tokens()
    prefix = "[DRY RUN] " if dry_run else ""
    status = "Applied ✅" if success else "Failed ❌"
    bar    = _score_bar(score)
    text   = (
        f"{prefix}{status}: {company}\n"
        f"Role   : {role}\n"
        f"Score  : {bar} {score:.0%}\n"
        f"Method : {method}\n"
        f"URL    : {job_url}\n\n"
        f"Email sent:\n{email_preview[:300]}"
    )
    if error:
        text += f"\n\nError: {error}"
    _api("sendMessage", {"chat_id": chat_id, "text": text})


# ── Follow-up reminder ────────────────────────────────────────────────────────

def notify_followup(company: str, role: str, applied_at: str, job_url: str) -> None:
    _, chat_id = _tokens()
    text = (
        f"Follow-up reminder\n\n"
        f"Company  : {company}\n"
        f"Role     : {role}\n"
        f"Applied  : {applied_at}\n"
        f"URL      : {job_url}\n\n"
        f"Consider sending a follow-up email today."
    )
    _api("sendMessage", {"chat_id": chat_id, "text": text})
