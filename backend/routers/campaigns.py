"""Campaigns Router"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime

from models.database import Campaign, CampaignStep, CampaignEnrollment, Lead, Agent, CampaignType, get_db
from middleware.auth import get_current_agent, require_active_subscription
from services.notification_service import send_drip_email

router = APIRouter()


class CampaignCreate(BaseModel):
    name: str
    description: Optional[str] = None
    campaign_type: CampaignType = CampaignType.nurture
    ai_generated: bool = False


class StepCreate(BaseModel):
    step_order: int
    delay_days: int = 0
    subject: str
    body_html: str


class EnrollRequest(BaseModel):
    lead_ids: list[UUID]


@router.get("/")
async def list_campaigns(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Campaign).where(Campaign.agent_id == agent.id))
    campaigns = result.scalars().all()
    output = []
    for c in campaigns:
        enrolled = await db.execute(
            select(func.count(CampaignEnrollment.id)).where(
                CampaignEnrollment.campaign_id == c.id,
                CampaignEnrollment.is_active == True,
            )
        )
        steps_count = await db.execute(
            select(func.count(CampaignStep.id)).where(CampaignStep.campaign_id == c.id)
        )
        output.append({
            "id": str(c.id), "name": c.name, "campaign_type": c.campaign_type.value,
            "is_active": c.is_active, "ai_generated": c.ai_generated,
            "enrolled_leads": enrolled.scalar(), "steps": steps_count.scalar(),
            "created_at": c.created_at.isoformat(),
        })
    return output


@router.post("/", status_code=201)
async def create_campaign(
    data: CampaignCreate,
    agent: Agent = Depends(require_active_subscription),
    db: AsyncSession = Depends(get_db),
):
    campaign = Campaign(agent_id=agent.id, **data.dict())
    db.add(campaign)
    await db.flush()
    return {"id": str(campaign.id), "name": campaign.name}


@router.post("/{campaign_id}/steps", status_code=201)
async def add_campaign_step(
    campaign_id: UUID,
    data: StepCreate,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    campaign_result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.agent_id == agent.id)
    )
    campaign = campaign_result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    step = CampaignStep(campaign_id=campaign_id, **data.dict())
    db.add(step)
    await db.flush()
    return {"id": str(step.id), "step_order": step.step_order}


@router.post("/{campaign_id}/enroll")
async def enroll_leads(
    campaign_id: UUID,
    data: EnrollRequest,
    agent: Agent = Depends(require_active_subscription),
    db: AsyncSession = Depends(get_db),
):
    campaign_result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.agent_id == agent.id)
    )
    campaign = campaign_result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    enrolled = 0
    for lead_id in data.lead_ids:
        existing = await db.execute(
            select(CampaignEnrollment).where(
                CampaignEnrollment.lead_id == lead_id,
                CampaignEnrollment.campaign_id == campaign_id,
            )
        )
        if not existing.scalar_one_or_none():
            enrollment = CampaignEnrollment(
                lead_id=lead_id,
                campaign_id=campaign_id,
                next_send_at=datetime.utcnow(),
            )
            db.add(enrollment)
            enrolled += 1

    return {"enrolled": enrolled, "campaign": campaign.name}
