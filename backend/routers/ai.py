"""
AI Router — exposes all AI generation endpoints to the frontend
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from models.database import Agent, get_db
from middleware.auth import require_active_subscription
from services.ai_service import (
    generate_email, generate_drip_campaign,
    generate_market_newsletter, generate_birthday_email, optimize_ad_budget
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


class EmailGenRequest(BaseModel):
    prompt: str
    email_type: str = "newsletter"  # newsletter, birthday, market_update, follow_up, reengagement


class CampaignGenRequest(BaseModel):
    name: str
    campaign_type: str
    target_audience: str
    num_emails: int = 5


class NewsletterRequest(BaseModel):
    location: Optional[str] = None
    market_data: Optional[dict] = None


@router.post("/generate-email")
async def generate_email_endpoint(
    data: EmailGenRequest,
    agent: Agent = Depends(require_active_subscription),
):
    """Generate a single marketing email"""
    result = await generate_email(data.prompt, data.email_type, agent)
    return result


@router.post("/generate-campaign")
async def generate_campaign_endpoint(
    data: CampaignGenRequest,
    agent: Agent = Depends(require_active_subscription),
):
    """Generate a full multi-step drip campaign"""
    emails = await generate_drip_campaign(
        data.name, data.campaign_type, data.target_audience, data.num_emails, agent
    )
    return {"campaign_name": data.name, "emails": emails}


@router.post("/generate-newsletter")
async def generate_newsletter_endpoint(
    data: NewsletterRequest,
    agent: Agent = Depends(require_active_subscription),
):
    """Generate a monthly market newsletter"""
    location = data.location or agent.location or "your local area"
    result = await generate_market_newsletter(location, agent, data.market_data)
    return result
