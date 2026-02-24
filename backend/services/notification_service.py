"""
Notification Service
─────────────────────
- Hot lead SMS alert via Twilio
- Instant agent-lead call connect (Twilio Programmable Voice)
- SendGrid transactional emails
- Daily digest scheduling
"""

from twilio.rest import Client as TwilioClient
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from typing import Optional
import os
import logging

logger = logging.getLogger(__name__)

twilio_client = TwilioClient(
    os.getenv("TWILIO_ACCOUNT_SID"),
    os.getenv("TWILIO_AUTH_TOKEN"),
)
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "+18435550100")
TWILIO_CONNECT_NUMBER = os.getenv("TWILIO_CONNECT_NUMBER", "+18435550101")

sg_client = SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))
FROM_EMAIL = os.getenv("FROM_EMAIL", "alerts@realboost.ai")
FROM_NAME = "RealBoost AI"


async def send_hot_lead_alert(agent, lead, key_findings: list[str] = None):
    """
    Fire all hot lead alerts simultaneously:
    1. SMS to agent
    2. Email to agent
    3. Optional: initiate call connect (Twilio)
    """
    lead_name = f"{lead.first_name} {lead.last_name or ''}".strip()
    budget = f"${lead.budget_max:,}" if lead.budget_max else "Unknown"
    findings_text = " · ".join(key_findings or []) or "High engagement, motivated buyer"

    # SMS Alert
    if agent.notify_hot_lead_sms and agent.phone:
        await send_hot_lead_sms(
            to=agent.phone,
            agent_name=agent.full_name,
            lead_name=lead_name,
            lead_phone=lead.phone,
            lead_email=lead.email,
            budget=budget,
            score=lead.ai_score,
            findings=findings_text,
        )

    # Email Alert
    if agent.notify_hot_lead_email and agent.email:
        await send_hot_lead_email(
            to=agent.email,
            agent_name=agent.full_name,
            lead_name=lead_name,
            lead_phone=lead.phone,
            lead_email=lead.email,
            budget=budget,
            score=lead.ai_score,
            findings=findings_text,
            lead_id=str(lead.id),
        )

    logger.info(f"Hot lead alerts sent for {lead_name} → {agent.email}")


async def send_hot_lead_sms(
    to: str,
    agent_name: str,
    lead_name: str,
    lead_phone: Optional[str],
    lead_email: Optional[str],
    budget: str,
    score: int,
    findings: str,
):
    """Send SMS hot lead alert to agent via Twilio"""
    message = (
        f"🔥 HOT LEAD — RealBoost AI\n\n"
        f"Name: {lead_name}\n"
        f"📞 {lead_phone or 'No phone'}\n"
        f"✉️ {lead_email or 'No email'}\n"
        f"💰 Budget: {budget}\n"
        f"🎯 Score: {score}/100\n"
        f"💡 {findings}\n\n"
        f"Reply CALL to connect now or log in to view full conversation."
    )

    try:
        twilio_client.messages.create(
            body=message,
            from_=TWILIO_FROM_NUMBER,
            to=to,
        )
        logger.info(f"Hot lead SMS sent to {to}")
    except Exception as e:
        logger.error(f"Twilio SMS failed: {e}")


async def send_hot_lead_email(
    to: str,
    agent_name: str,
    lead_name: str,
    lead_phone: Optional[str],
    lead_email: Optional[str],
    budget: str,
    score: int,
    findings: str,
    lead_id: str,
):
    """Send HTML hot lead email to agent via SendGrid"""
    html_content = f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f9fafb; margin: 0; padding: 20px;">
  <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.08);">

    <!-- Header -->
    <div style="background: linear-gradient(135deg, #ef4444, #dc2626); padding: 30px; text-align: center;">
      <div style="font-size: 40px; margin-bottom: 8px;">🔥</div>
      <h1 style="color: white; margin: 0; font-size: 24px; font-weight: 800;">HOT LEAD ALERT</h1>
      <p style="color: rgba(255,255,255,0.85); margin: 8px 0 0; font-size: 14px;">AI Lead Score: {score}/100 — Call within 5 minutes for best results</p>
    </div>

    <!-- Lead Info -->
    <div style="padding: 30px;">
      <div style="background: #fef2f2; border: 1px solid #fecaca; border-radius: 12px; padding: 20px; margin-bottom: 24px;">
        <h2 style="margin: 0 0 16px; font-size: 20px; color: #111;">{lead_name}</h2>
        <table style="width: 100%; border-collapse: collapse;">
          <tr><td style="padding: 6px 0; color: #6b7280; font-size: 14px; width: 120px;">📞 Phone</td><td style="padding: 6px 0; font-weight: 600; font-size: 14px;">{lead_phone or 'Not provided'}</td></tr>
          <tr><td style="padding: 6px 0; color: #6b7280; font-size: 14px;">✉️ Email</td><td style="padding: 6px 0; font-weight: 600; font-size: 14px;">{lead_email or 'Not provided'}</td></tr>
          <tr><td style="padding: 6px 0; color: #6b7280; font-size: 14px;">💰 Budget</td><td style="padding: 6px 0; font-weight: 600; font-size: 14px;">{budget}</td></tr>
          <tr><td style="padding: 6px 0; color: #6b7280; font-size: 14px;">🎯 Score</td><td style="padding: 6px 0; font-weight: 600; font-size: 14px; color: #ef4444;">{score}/100</td></tr>
        </table>
      </div>

      <!-- AI Findings -->
      <div style="background: #f5f3ff; border: 1px solid #ddd6fe; border-radius: 12px; padding: 16px; margin-bottom: 24px;">
        <p style="margin: 0 0 6px; font-size: 12px; color: #7c3aed; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">🤖 AI Key Findings</p>
        <p style="margin: 0; color: #4c1d95; font-size: 14px;">{findings}</p>
      </div>

      <!-- CTA Buttons -->
      <div style="display: flex; gap: 12px; flex-wrap: wrap;">
        <a href="tel:{lead_phone or ''}" style="display: inline-block; background: #16a34a; color: white; padding: 14px 24px; border-radius: 10px; text-decoration: none; font-weight: 700; font-size: 15px;">📞 Call Now</a>
        <a href="https://app.realboost.ai/chat/{lead_id}" style="display: inline-block; background: #2563eb; color: white; padding: 14px 24px; border-radius: 10px; text-decoration: none; font-weight: 700; font-size: 15px;">💬 View Conversation</a>
        <a href="sms:{lead_phone or ''}" style="display: inline-block; background: #7c3aed; color: white; padding: 14px 24px; border-radius: 10px; text-decoration: none; font-weight: 700; font-size: 15px;">✉️ Text Lead</a>
      </div>
    </div>

    <!-- Footer -->
    <div style="background: #f9fafb; padding: 16px 30px; border-top: 1px solid #e5e7eb; text-align: center;">
      <p style="margin: 0; color: #9ca3af; font-size: 12px;">RealBoost AI · Hot leads go cold fast — call within 5 minutes · <a href="https://app.realboost.ai/settings" style="color: #6b7280;">Manage alerts</a></p>
    </div>
  </div>
</body>
</html>"""

    try:
        message = Mail(
            from_email=(FROM_EMAIL, FROM_NAME),
            to_emails=to,
            subject=f"🔥 HOT LEAD: {lead_name} — {budget} budget — Call Now",
            html_content=html_content,
        )
        sg_client.send(message)
        logger.info(f"Hot lead email sent to {to}")
    except Exception as e:
        logger.error(f"SendGrid email failed: {e}")


async def initiate_call_connect(agent_phone: str, lead_phone: str, lead_name: str):
    """
    Twilio call connect: calls the agent first, then bridges to the lead.
    Agent hears: "You have a hot lead — {name} — connecting now"
    """
    try:
        # TwiML for the call bridge
        twiml_url = f"{os.getenv('API_BASE_URL', 'https://api.realboost.ai')}/api/webhooks/twiml/connect?lead_phone={lead_phone}&lead_name={lead_name}"

        call = twilio_client.calls.create(
            url=twiml_url,
            to=agent_phone,
            from_=TWILIO_CONNECT_NUMBER,
        )
        logger.info(f"Call connect initiated: agent={agent_phone}, lead={lead_phone}, call_sid={call.sid}")
        return {"call_sid": call.sid, "status": "initiated"}
    except Exception as e:
        logger.error(f"Call connect failed: {e}")
        raise


async def send_drip_email(
    to_email: str,
    to_name: str,
    subject: str,
    html_body: str,
    from_agent_name: str,
    from_agent_email: str,
):
    """Send a drip campaign email via SendGrid"""
    # Personalize the body
    personalized_body = html_body.replace("[First Name]", to_name.split()[0])

    try:
        message = Mail(
            from_email=(FROM_EMAIL, from_agent_name),
            to_emails=to_email,
            subject=subject,
            html_content=personalized_body,
        )
        message.reply_to = from_agent_email
        sg_client.send(message)
        return True
    except Exception as e:
        logger.error(f"Drip email send failed to {to_email}: {e}")
        return False


async def send_daily_digest(agent, leads_summary: dict):
    """Send daily lead digest to agent"""
    html = f"""
<div style="font-family: sans-serif; max-width: 600px; margin: 0 auto;">
  <h2>📊 Your Daily Lead Report</h2>
  <p>Hi {agent.full_name.split()[0]}, here's your summary for today:</p>
  <table style="width:100%; border-collapse: collapse;">
    <tr style="background:#f3f4f6;"><td style="padding:12px;">Total Leads</td><td style="padding:12px;font-weight:bold;">{leads_summary.get('total', 0)}</td></tr>
    <tr><td style="padding:12px;">Hot Leads 🔥</td><td style="padding:12px;font-weight:bold;color:#ef4444;">{leads_summary.get('hot', 0)}</td></tr>
    <tr style="background:#f3f4f6;"><td style="padding:12px;">New Today</td><td style="padding:12px;font-weight:bold;">{leads_summary.get('new_today', 0)}</td></tr>
    <tr><td style="padding:12px;">Ad Spend Today</td><td style="padding:12px;font-weight:bold;">${leads_summary.get('spend_today', 0):.2f}</td></tr>
  </table>
  <br>
  <a href="https://app.realboost.ai" style="background:#2563eb;color:white;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:bold;">View Dashboard →</a>
</div>"""

    try:
        message = Mail(
            from_email=(FROM_EMAIL, FROM_NAME),
            to_emails=agent.email,
            subject=f"📊 Daily Report — {leads_summary.get('hot', 0)} hot leads today",
            html_content=html,
        )
        sg_client.send(message)
    except Exception as e:
        logger.error(f"Daily digest failed for {agent.email}: {e}")
