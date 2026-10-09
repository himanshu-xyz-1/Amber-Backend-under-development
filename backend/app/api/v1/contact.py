import asyncio
import html
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, field_validator

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/contact", tags=["Contact"])


class ContactRequest(BaseModel):
    name: str | None = None
    email: str
    phone: str | None = None
    selectedPlan: str | None = None
    selectedInfra: str | None = None
    clusterScale: str | None = None
    message: str | None = None

    @field_validator("email", "name", "phone", mode="after")
    @classmethod
    def prevent_header_injection(cls, v: str | None) -> str | None:
        if v and ("\r" in v or "\n" in v):
            raise ValueError("Input cannot contain newline characters (CRLF injection prevention).")
        return v


def _send_smtp_sync(gmail_user: str, gmail_pass: str, msg: MIMEMultipart) -> None:
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as server:
        server.starttls()
        server.login(gmail_user, gmail_pass)
        server.send_message(msg)


@router.post("", status_code=status.HTTP_200_OK)
async def submit_contact(req: ContactRequest):
    gmail_user = settings.GMAIL_USER or "amber.incident@gmail.com"
    gmail_pass = settings.GMAIL_APP_PASSWORD

    if not gmail_pass:
        logger.warning("GMAIL_APP_PASSWORD is not set. Simulating contact dispatch.")
        return {
            "success": True,
            "simulated": True,
            "message": "Lead received (email delivery simulated in dev mode)"
        }

    clean_name = req.name.strip() if req.name else ""
    clean_email = req.email.strip()

    msg = MIMEMultipart("alternative")
    msg["From"] = formataddr(("Amber Intake", gmail_user))
    msg["To"] = gmail_user
    msg["Reply-To"] = clean_email
    subject_lead = f"{clean_name} · {clean_email}" if clean_name else clean_email
    msg["Subject"] = f"🚨 New Amber Lead: {subject_lead} ({req.selectedPlan or 'Inquiry'})"

    plain_text = f"""
New Amber Lead Received
===============================================
Name:           {clean_name or 'Not provided'}
Work Email:     {clean_email}
Phone:          {req.phone or 'Not provided'}
Selected Tier:  {req.selectedPlan or 'General Inquiry'}
Infrastructure: {req.selectedInfra or 'AWS'} ({req.clusterScale or 'Not specified'})

Message:
-----------------------------------------------
{req.message or 'No additional message provided.'}
===============================================
Hit 'Reply' in your email client to directly reply to {clean_email}.
    """.strip()

    esc_name = html.escape(clean_name or "Not provided")
    esc_email = html.escape(clean_email)
    esc_phone = html.escape(req.phone or "Not provided")
    esc_plan = html.escape(req.selectedPlan or "General")
    esc_infra = html.escape(req.selectedInfra or "AWS")
    esc_scale = html.escape(req.clusterScale or "N/A")
    esc_message = html.escape(req.message or "No message provided")

    html_content = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 580px; margin: 0 auto; background: #ffffff; border: 1px solid #e7e5e4; border-radius: 14px; padding: 24px;">
      <h2 style="color: #0c0a09; margin-top: 0;">New Client Inquiry Received</h2>
      <p><strong>Name:</strong> {esc_name}</p>
      <p><strong>Work Email:</strong> <a href="mailto:{esc_email}">{esc_email}</a></p>
      <p><strong>Phone:</strong> {esc_phone}</p>
      <p><strong>Selected Tier:</strong> {esc_plan}</p>
      <p><strong>Infrastructure:</strong> {esc_infra} ({esc_scale})</p>
      <hr style="border: 0; border-top: 1px solid #e7e5e4; margin: 20px 0;" />
      <p><strong>Message:</strong><br/>{esc_message}</p>
      <p style="color: #78716c; font-size: 12px; margin-top: 24px;">Click Reply in Gmail to respond directly to {esc_email}.</p>
    </div>
    """

    msg.attach(MIMEText(plain_text, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    try:
        # Offload blocking SMTP call to thread pool to keep async event loop responsive
        await asyncio.to_thread(_send_smtp_sync, gmail_user, gmail_pass, msg)
        return {"success": True, "message": "Lead dispatched successfully"}
    except Exception as e:
        logger.error(f"Failed to send email via SMTP: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to dispatch email: {e}"
        )
