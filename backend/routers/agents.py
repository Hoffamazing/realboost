"""
Agents Router
Registration, login, profile management (multi-tenant auth)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime, timedelta
from uuid import UUID

from models.database import Agent, SubscriptionPlan, SubscriptionStatus, get_db
from middleware.auth import hash_password, verify_password, create_access_token, get_current_agent

router = APIRouter()


# ── SCHEMAS ───────────────────────────────────────────────────────────────────

class AgentRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    phone: Optional[str] = None
    brokerage: Optional[str] = None
    location: Optional[str] = None

class AgentLogin(BaseModel):
    email: EmailStr
    password: str

class AgentUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    brokerage: Optional[str] = None
    license_number: Optional[str] = None
    location: Optional[str] = None
    timezone: Optional[str] = None
    ai_greeting_style: Optional[str] = None
    ai_auto_reply_enabled: Optional[bool] = None
    ai_hot_lead_score_threshold: Optional[int] = None
    notify_hot_lead_sms: Optional[bool] = None
    notify_hot_lead_email: Optional[bool] = None
    notify_daily_summary: Optional[bool] = None
    notify_summary_time: Optional[str] = None

class AgentResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    phone: Optional[str]
    brokerage: Optional[str]
    location: Optional[str]
    subscription_plan: str
    subscription_status: str
    ai_hot_lead_score_threshold: int
    ai_auto_reply_enabled: bool
    notify_hot_lead_sms: bool
    notify_hot_lead_email: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ── ENDPOINTS ─────────────────────────────────────────────────────────────────

@router.post("/register", status_code=201)
async def register(data: AgentRegister, db: AsyncSession = Depends(get_db)):
    """Register a new agent (creates tenant). Starts 14-day free trial."""
    existing = await db.execute(select(Agent).where(Agent.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    agent = Agent(
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        phone=data.phone,
        brokerage=data.brokerage,
        location=data.location,
        subscription_plan=SubscriptionPlan.starter,
        subscription_status=SubscriptionStatus.trialing,
        trial_ends_at=datetime.utcnow() + timedelta(days=14),
    )
    db.add(agent)
    await db.flush()

    token = create_access_token(str(agent.id), agent.email)
    return {
        "access_token": token,
        "token_type": "bearer",
        "agent": {
            "id": str(agent.id),
            "email": agent.email,
            "full_name": agent.full_name,
            "subscription_status": agent.subscription_status.value,
            "trial_ends_at": agent.trial_ends_at.isoformat(),
        },
    }


@router.post("/login")
async def login(data: AgentLogin, db: AsyncSession = Depends(get_db)):
    """Authenticate agent and return JWT"""
    result = await db.execute(select(Agent).where(Agent.email == data.email, Agent.is_active == True))
    agent = result.scalar_one_or_none()

    if not agent or not verify_password(data.password, agent.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token(str(agent.id), agent.email)
    return {
        "access_token": token,
        "token_type": "bearer",
        "agent": {
            "id": str(agent.id),
            "email": agent.email,
            "full_name": agent.full_name,
            "subscription_plan": agent.subscription_plan.value,
            "subscription_status": agent.subscription_status.value,
            "trial_ends_at": agent.trial_ends_at.isoformat() if agent.trial_ends_at else None,
        },
    }


@router.get("/me", response_model=AgentResponse)
async def get_profile(agent: Agent = Depends(get_current_agent)):
    """Get current agent's profile"""
    return agent


@router.patch("/me", response_model=AgentResponse)
async def update_profile(
    data: AgentUpdate,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Update agent profile and settings"""
    for field, value in data.dict(exclude_none=True).items():
        setattr(agent, field, value)
    return agent
