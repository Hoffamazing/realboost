"""
Leads Router
CRUD + AI qualification endpoint
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from pydantic import BaseModel, EmailStr
from typing import Optional
from uuid import UUID
from datetime import datetime

from models.database import Lead, Message, Agent, LeadStatus, LeadSource, MessageRole, get_db
from middleware.auth import get_current_agent, require_active_subscription
from services.ai_service import qualify_lead, score_lead_from_profile
from services.notification_service import send_hot_lead_alert

router = APIRouter()


# ── SCHEMAS ───────────────────────────────────────────────────────────────────

class LeadCreate(BaseModel):
    first_name: str
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    source: LeadSource = LeadSource.manual
    budget_min: Optional[int] = None
    budget_max: Optional[int] = None
    timeline: Optional[str] = None
    intent: Optional[str] = None
    location_interest: Optional[str] = None
    notes: Optional[str] = None
    is_pre_approved: Optional[bool] = None
    is_cash_buyer: bool = False
    birthday: Optional[datetime] = None
    ad_campaign_id: Optional[str] = None
    utm_source: Optional[str] = None
    utm_campaign: Optional[str] = None


class LeadUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    status: Optional[LeadStatus] = None
    budget_min: Optional[int] = None
    budget_max: Optional[int] = None
    timeline: Optional[str] = None
    intent: Optional[str] = None
    notes: Optional[str] = None
    is_pre_approved: Optional[bool] = None
    is_cash_buyer: Optional[bool] = None
    current_situation: Optional[str] = None
    urgency_level: Optional[str] = None
    birthday: Optional[datetime] = None


class IncomingMessage(BaseModel):
    content: str
    channel: str = "chat"  # chat, sms, email


class LeadResponse(BaseModel):
    id: UUID
    first_name: str
    last_name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    status: str
    source: str
    ai_score: int
    budget_min: Optional[int]
    budget_max: Optional[int]
    timeline: Optional[str]
    intent: Optional[str]
    location_interest: Optional[str]
    notes: Optional[str]
    is_pre_approved: Optional[bool]
    is_cash_buyer: bool
    unread_count: int = 0
    last_message_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


# ── ENDPOINTS ─────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[LeadResponse])
async def list_leads(
    status: Optional[LeadStatus] = None,
    source: Optional[LeadSource] = None,
    search: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    sort_by: str = "created_at",
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """List all leads for the authenticated agent with filtering"""
    query = select(Lead).where(Lead.agent_id == agent.id)

    if status:
        query = query.where(Lead.status == status)
    if source:
        query = query.where(Lead.source == source)
    if search:
        query = query.where(
            (Lead.first_name.ilike(f"%{search}%")) |
            (Lead.last_name.ilike(f"%{search}%")) |
            (Lead.email.ilike(f"%{search}%")) |
            (Lead.phone.ilike(f"%{search}%"))
        )

    query = query.order_by(desc(Lead.created_at)).limit(limit).offset(offset)
    result = await db.execute(query)
    leads = result.scalars().all()

    # Enrich with unread count and last message time
    enriched = []
    for lead in leads:
        unread_result = await db.execute(
            select(func.count(Message.id)).where(
                Message.lead_id == lead.id,
                Message.role == MessageRole.lead,
                Message.is_read == False
            )
        )
        unread_count = unread_result.scalar() or 0

        last_msg_result = await db.execute(
            select(Message.created_at).where(Message.lead_id == lead.id).order_by(desc(Message.created_at)).limit(1)
        )
        last_msg = last_msg_result.scalar_one_or_none()

        lead_dict = {c.name: getattr(lead, c.name) for c in lead.__table__.columns}
        lead_dict["unread_count"] = unread_count
        lead_dict["last_message_at"] = last_msg
        enriched.append(lead_dict)

    return enriched


@router.post("/", response_model=LeadResponse, status_code=201)
async def create_lead(
    data: LeadCreate,
    background_tasks: BackgroundTasks,
    agent: Agent = Depends(require_active_subscription),
    db: AsyncSession = Depends(get_db),
):
    """Create a new lead and run AI initial scoring"""
    lead = Lead(agent_id=agent.id, **data.dict(exclude_none=True))
    db.add(lead)
    await db.flush()

    # AI score based on profile
    background_tasks.add_task(_score_lead_background, lead.id, db)

    lead_dict = {c.name: getattr(lead, c.name) for c in lead.__table__.columns}
    lead_dict["unread_count"] = 0
    lead_dict["last_message_at"] = None
    return lead_dict


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: UUID,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    lead = await _get_lead_or_404(lead_id, agent.id, db)
    lead_dict = {c.name: getattr(lead, c.name) for c in lead.__table__.columns}
    lead_dict["unread_count"] = 0
    lead_dict["last_message_at"] = None
    return lead_dict


@router.patch("/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: UUID,
    data: LeadUpdate,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    lead = await _get_lead_or_404(lead_id, agent.id, db)
    for field, value in data.dict(exclude_none=True).items():
        setattr(lead, field, value)
    lead_dict = {c.name: getattr(lead, c.name) for c in lead.__table__.columns}
    lead_dict["unread_count"] = 0
    lead_dict["last_message_at"] = None
    return lead_dict


@router.delete("/{lead_id}", status_code=204)
async def delete_lead(
    lead_id: UUID,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    lead = await _get_lead_or_404(lead_id, agent.id, db)
    await db.delete(lead)


@router.post("/{lead_id}/qualify")
async def qualify_lead_message(
    lead_id: UUID,
    message: IncomingMessage,
    background_tasks: BackgroundTasks,
    agent: Agent = Depends(require_active_subscription),
    db: AsyncSession = Depends(get_db),
):
    """
    STEP 1 CORE ENDPOINT: 
    Receives an incoming lead message, runs it through GPT-4o qualification,
    saves both messages, updates lead score, triggers hot lead alert if needed.
    """
    lead = await _get_lead_or_404(lead_id, agent.id, db)

    # Load conversation history
    history_result = await db.execute(
        select(Message).where(Message.lead_id == lead_id).order_by(Message.created_at).limit(50)
    )
    history = [
        {"role": msg.role.value, "content": msg.content}
        for msg in history_result.scalars().all()
    ]

    # Save the incoming lead message
    lead_msg = Message(
        lead_id=lead_id,
        role=MessageRole.lead,
        content=message.content,
        is_read=False,
    )
    db.add(lead_msg)
    await db.flush()

    # Run AI qualification
    result = await qualify_lead(lead, agent, message.content, history, db)

    # Save AI response
    ai_msg = Message(
        lead_id=lead_id,
        role=MessageRole.ai,
        content=result["ai_response"],
        ai_model="gpt-4o",
        ai_prompt_tokens=result["prompt_tokens"],
        ai_completion_tokens=result["completion_tokens"],
        triggered_hot_lead_alert=result["alert_agent"],
        score_at_time=result["score"],
        is_read=True,
    )
    db.add(ai_msg)
    lead.last_contacted_at = datetime.utcnow()

    # Trigger hot lead alert in background
    if result["alert_agent"]:
        background_tasks.add_task(
            send_hot_lead_alert,
            agent=agent,
            lead=lead,
            key_findings=result["key_findings"],
        )

    return {
        "ai_response": result["ai_response"],
        "lead_score": result["score"],
        "lead_status": result["status"],
        "is_hot_lead": result["alert_agent"],
        "key_findings": result["key_findings"],
    }


@router.get("/{lead_id}/messages")
async def get_conversation(
    lead_id: UUID,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get full conversation history for a lead"""
    await _get_lead_or_404(lead_id, agent.id, db)

    result = await db.execute(
        select(Message).where(Message.lead_id == lead_id).order_by(Message.created_at)
    )
    messages = result.scalars().all()

    # Mark all lead messages as read
    for msg in messages:
        if msg.role == MessageRole.lead:
            msg.is_read = True

    return [
        {
            "id": str(msg.id),
            "role": msg.role.value,
            "content": msg.content,
            "created_at": msg.created_at.isoformat(),
            "score_at_time": msg.score_at_time,
        }
        for msg in messages
    ]


@router.get("/stats/overview")
async def get_lead_stats(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Dashboard stats for the agent"""
    total = await db.execute(select(func.count(Lead.id)).where(Lead.agent_id == agent.id))
    hot = await db.execute(select(func.count(Lead.id)).where(Lead.agent_id == agent.id, Lead.status == LeadStatus.hot))
    warm = await db.execute(select(func.count(Lead.id)).where(Lead.agent_id == agent.id, Lead.status == LeadStatus.warm))
    converted = await db.execute(select(func.count(Lead.id)).where(Lead.agent_id == agent.id, Lead.status == LeadStatus.converted))

    return {
        "total_leads": total.scalar(),
        "hot_leads": hot.scalar(),
        "warm_leads": warm.scalar(),
        "converted_leads": converted.scalar(),
    }


# ── HELPERS ───────────────────────────────────────────────────────────────────

async def _get_lead_or_404(lead_id: UUID, agent_id: UUID, db: AsyncSession) -> Lead:
    result = await db.execute(
        select(Lead).where(Lead.id == lead_id, Lead.agent_id == agent_id)
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


async def _score_lead_background(lead_id: UUID, db: AsyncSession):
    """Background task to score a lead from profile data"""
    result = await db.execute(select(Lead).where(Lead.id == lead_id))
    lead = result.scalar_one_or_none()
    if lead:
        score = await score_lead_from_profile(lead)
        lead.ai_score = score
        await db.commit()
