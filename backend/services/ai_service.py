"""
STEP 1: OpenAI AI Service
─────────────────────────
- Lead qualification chatbot (GPT-4o)
- Hot lead scoring and detection
- AI email and newsletter generation
- Ad spend optimization recommendations
- Drip campaign content generation
"""

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
import json
import os
import logging

from models.database import Lead, Message, Agent, AdAccount, MessageRole, LeadStatus

logger = logging.getLogger(__name__)

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = "gpt-4o"


# ── SYSTEM PROMPTS ────────────────────────────────────────────────────────────

def build_qualification_system_prompt(agent: Agent, lead: Lead) -> str:
    return f"""You are an expert real estate lead qualification assistant working for {agent.full_name} at {agent.brokerage or 'their real estate brokerage'} in {agent.location or 'the local area'}.

Your job is to have a natural, friendly conversation with potential buyers and sellers to:
1. Understand their real estate needs
2. Qualify their readiness (timeline, budget, financing status)
3. Identify hot leads (pre-approved buyers, motivated sellers, cash buyers, short timelines)
4. Collect contact information
5. Schedule the agent when the lead is ready

LEAD INFO SO FAR:
- Name: {lead.first_name} {lead.last_name or ''}
- Source: {lead.source}
- Budget: {f'${lead.budget_min:,} - ${lead.budget_max:,}' if lead.budget_max else 'Unknown'}
- Status: {lead.status}

QUALIFICATION GOALS (gather these naturally, not all at once):
- Are they buying, selling, or both?
- What's their timeline? (1 month = HOT, 6+ months = COLD)
- Are they pre-approved or a cash buyer? (CRITICAL for hot lead)
- What's their budget range?
- What areas are they interested in?
- What are their must-haves (beds, baths, school districts)?
- Are they currently renting or do they own?

HOT LEAD TRIGGERS — if any of these are true, end the conversation naturally and alert the agent:
- Pre-approved with a lender AND looking in < 3 months
- Cash buyer
- Already working with a lender, motivated timeline
- Currently selling and needs to buy simultaneously
- Relocating with a firm start date

STYLE:
- Be warm, conversational, and helpful — never robotic
- Ask ONE question at a time
- Use local knowledge about {agent.location or 'the area'} when relevant
- Keep messages short (2-4 sentences max)
- Don't sound like a script — sound like a knowledgeable friend

When you determine this is a HOT LEAD, tell them: "This sounds like a great match — let me get {agent.full_name} on the phone with you right away! They're available today and would love to chat."

IMPORTANT: After every response, include a JSON block at the very end (invisible to user) in this exact format:
[SCORE_UPDATE: {{"score": 0-100, "status": "cold/warm/hot", "key_findings": ["finding1"], "is_hot": false, "alert_agent": false}}]"""


def build_email_generation_prompt(context: str, agent: Agent, email_type: str) -> str:
    return f"""You are an expert real estate email copywriter for {agent.full_name}, a real estate agent in {agent.location or 'the local area'}.

Write a professional, engaging {email_type} email based on this request:
{context}

Requirements:
- Subject line that gets opened (curiosity, urgency, or personal)
- Conversational but professional tone
- Local market relevance for {agent.location or 'the area'}
- Clear call-to-action
- 150-300 words for newsletters, 50-150 words for personal emails
- Use [First Name] as placeholder for personalization
- Include [Agent Name], [Agent Phone], [Agent Website] in signature

Format your response EXACTLY as:
SUBJECT: <subject line here>
---
<email body here>"""


def build_ad_optimization_prompt(platforms_data: list) -> str:
    return f"""You are a digital marketing expert specializing in real estate advertising optimization.

Analyze this ad platform performance data and provide a specific budget reallocation recommendation:

{json.dumps(platforms_data, indent=2)}

Provide:
1. Which platform has the best ROI (lowest CPL + highest lead quality)
2. Specific dollar amount to shift and from/to which platforms
3. Projected impact (estimated additional leads per month)
4. One sentence explanation

Respond in JSON:
{{
  "recommendation": "Clear one-sentence action",
  "from_platform": "platform name",
  "to_platform": "platform name", 
  "amount_to_shift": 200,
  "projected_additional_leads": 7,
  "reasoning": "Brief explanation"
}}"""


# ── CORE AI FUNCTIONS ─────────────────────────────────────────────────────────

async def qualify_lead(
    lead: Lead,
    agent: Agent,
    incoming_message: str,
    conversation_history: list[dict],
    db: AsyncSession,
) -> dict:
    """
    Main qualification engine. Takes a lead's message, runs it through GPT-4o,
    returns AI response + updated lead score/status.
    """
    system_prompt = build_qualification_system_prompt(agent, lead)

    messages = [{"role": "system", "content": system_prompt}]
    for msg in conversation_history[-20:]:  # Last 20 messages for context
        role = "user" if msg["role"] == "lead" else "assistant"
        messages.append({"role": role, "content": msg["content"]})
    messages.append({"role": "user", "content": incoming_message})

    try:
        response = await client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=400,
            temperature=0.7,
        )

        full_response = response.choices[0].message.content
        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens

        # Parse the hidden score update block
        score_data = None
        display_response = full_response

        if "[SCORE_UPDATE:" in full_response:
            parts = full_response.split("[SCORE_UPDATE:")
            display_response = parts[0].strip()
            try:
                score_json = parts[1].rstrip("]").strip()
                score_data = json.loads(score_json)
            except (json.JSONDecodeError, IndexError) as e:
                logger.warning(f"Failed to parse score update: {e}")

        # Update lead in DB
        new_score = score_data.get("score", lead.ai_score) if score_data else lead.ai_score
        new_status = score_data.get("status", lead.status) if score_data else lead.status
        alert_agent = score_data.get("alert_agent", False) if score_data else False

        lead.ai_score = new_score
        if new_status:
            lead.status = LeadStatus(new_status)

        # Check hot lead threshold
        if new_score >= agent.ai_hot_lead_score_threshold and lead.status != LeadStatus.hot:
            lead.status = LeadStatus.hot
            alert_agent = True
            logger.info(f"HOT LEAD DETECTED: {lead.first_name} {lead.last_name} (score: {new_score})")

        return {
            "ai_response": display_response,
            "score": new_score,
            "status": new_status,
            "alert_agent": alert_agent,
            "key_findings": score_data.get("key_findings", []) if score_data else [],
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        }

    except Exception as e:
        logger.error(f"OpenAI API error in qualify_lead: {e}")
        raise


async def generate_email(
    prompt: str,
    email_type: str,
    agent: Agent,
) -> dict:
    """
    Generate a marketing email using GPT-4o.
    Types: newsletter, birthday, market_update, new_listing, reengagement, follow_up
    """
    system_prompt = build_email_generation_prompt(prompt, agent, email_type)

    try:
        response = await client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            max_tokens=800,
            temperature=0.75,
        )

        content = response.choices[0].message.content

        # Parse subject and body
        subject = ""
        body = content
        if "SUBJECT:" in content and "---" in content:
            lines = content.split("---", 1)
            subject = lines[0].replace("SUBJECT:", "").strip()
            body = lines[1].strip()

        return {
            "subject": subject,
            "body": body,
            "full_content": content,
            "tokens_used": response.usage.total_tokens,
        }

    except Exception as e:
        logger.error(f"OpenAI email generation error: {e}")
        raise


async def generate_drip_campaign(
    campaign_name: str,
    campaign_type: str,
    target_audience: str,
    num_emails: int,
    agent: Agent,
) -> list[dict]:
    """
    Generate a full multi-step drip campaign sequence.
    Returns list of {subject, body, delay_days} dicts.
    """
    prompt = f"""Create a {num_emails}-email drip campaign called "{campaign_name}" for {campaign_type} targeting: {target_audience}.

Agent: {agent.full_name} in {agent.location or 'local area'}.

For each email provide:
- Email number (1 to {num_emails})
- Days after previous email to send (first email = 0)
- Subject line
- Email body (100-250 words)

Format as JSON array:
[{{"email_num": 1, "delay_days": 0, "subject": "...", "body": "..."}}]

Make each email feel personal, valuable, and build trust. Use [First Name] placeholder."""

    try:
        response = await client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=3000,
            temperature=0.7,
            response_format={"type": "json_object"},
        )

        data = json.loads(response.choices[0].message.content)
        emails = data.get("emails", data) if isinstance(data, dict) else data
        return emails if isinstance(emails, list) else []

    except Exception as e:
        logger.error(f"OpenAI campaign generation error: {e}")
        raise


async def generate_market_newsletter(
    location: str,
    agent: Agent,
    market_data: Optional[dict] = None,
) -> dict:
    """Generate a monthly market update newsletter with local data"""
    market_context = json.dumps(market_data) if market_data else "Use realistic current market trends for the area."

    prompt = f"""Write a monthly real estate market newsletter for {location}.
Agent: {agent.full_name}
Market data context: {market_context}

Include:
- Market summary (price trends, inventory, days on market)
- 3 hot neighborhoods with brief insight
- Buyer tip and seller tip
- Local lifestyle/event mention
- Clear CTA to schedule a consultation

Tone: Knowledgeable neighbor, not corporate broker.
Length: 300-400 words."""

    return await generate_email(prompt, "monthly market newsletter", agent)


async def optimize_ad_budget(platforms_data: list[dict]) -> dict:
    """
    AI analyzes all platform performance and recommends budget reallocation.
    """
    prompt = build_ad_optimization_prompt(platforms_data)

    try:
        response = await client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.3,
            response_format={"type": "json_object"},
        )

        return json.loads(response.choices[0].message.content)

    except Exception as e:
        logger.error(f"OpenAI ad optimization error: {e}")
        raise


async def score_lead_from_profile(lead: Lead) -> int:
    """
    Score a lead 0-100 based on their profile data alone (no conversation).
    Used for leads imported manually or from ad platforms.
    """
    prompt = f"""Score this real estate lead from 0-100 based on buying readiness.

Lead profile:
- Timeline: {lead.timeline or 'Unknown'}
- Budget: {f'${lead.budget_min:,}-${lead.budget_max:,}' if lead.budget_max else 'Unknown'}
- Pre-approved: {lead.is_pre_approved}
- Cash buyer: {lead.is_cash_buyer}
- Intent: {lead.intent or 'Unknown'}
- Current situation: {lead.current_situation or 'Unknown'}
- Urgency: {lead.urgency_level or 'Unknown'}

Scoring guide:
- 80-100: Pre-approved/cash, short timeline (< 2 months), clear intent
- 60-79: Has financing discussion, 2-5 month timeline
- 40-59: Exploring options, 6-12 month timeline  
- 0-39: Early research, no financing, long timeline

Respond with just the number."""

    try:
        response = await client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10,
            temperature=0.1,
        )
        score_text = response.choices[0].message.content.strip()
        return min(100, max(0, int(''.join(filter(str.isdigit, score_text)))))
    except Exception:
        return 25  # Default score if AI fails


async def generate_birthday_email(lead: Lead, agent: Agent) -> dict:
    """Generate a personalized birthday email for a lead"""
    prompt = f"""Write a warm, personal birthday email from real estate agent {agent.full_name} to their client/lead {lead.first_name}.

Keep it:
- Genuine and warm (not salesy AT ALL)
- Short (50-80 words max)
- Include a subtle, soft mention of being available if they ever need real estate help
- Personal, as if from a friend who happens to be in real estate

This is relationship-building, not selling."""

    return await generate_email(prompt, "birthday message", agent)
