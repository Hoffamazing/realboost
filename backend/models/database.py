"""
Database configuration and models
Uses async SQLAlchemy with PostgreSQL (Supabase)
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text,
    ForeignKey, Enum, JSON, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid
import enum
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:password@localhost/realboost")

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True, pool_size=10, max_overflow=20)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# ── ENUMS ─────────────────────────────────────────────────────────────────────

class LeadStatus(str, enum.Enum):
    new = "new"
    cold = "cold"
    warm = "warm"
    hot = "hot"
    converted = "converted"
    lost = "lost"

class LeadSource(str, enum.Enum):
    meta = "meta"
    google = "google"
    tiktok = "tiktok"
    waze = "waze"
    referral = "referral"
    manual = "manual"
    organic = "organic"

class CampaignType(str, enum.Enum):
    nurture = "nurture"
    newsletter = "newsletter"
    relationship = "relationship"
    reactivation = "reactivation"
    announcement = "announcement"

class MessageRole(str, enum.Enum):
    ai = "ai"
    lead = "lead"
    agent = "agent"
    system = "system"

class SubscriptionPlan(str, enum.Enum):
    starter = "starter"      # $99/mo — 1 agent, 2 platforms
    pro = "pro"              # $249/mo — 1 agent, all platforms
    team = "team"            # $499/mo — 5 agents, all platforms + team features

class SubscriptionStatus(str, enum.Enum):
    active = "active"
    past_due = "past_due"
    canceled = "canceled"
    trialing = "trialing"


# ── MODELS ────────────────────────────────────────────────────────────────────

class Agent(Base):
    """Represents a real estate agent (tenant)"""
    __tablename__ = "agents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    phone = Column(String(50))
    brokerage = Column(String(255))
    license_number = Column(String(100))
    location = Column(String(255))  # e.g. "Charleston, SC"
    timezone = Column(String(50), default="America/New_York")
    avatar_url = Column(String(500))

    # Stripe
    stripe_customer_id = Column(String(255), unique=True)
    stripe_subscription_id = Column(String(255), unique=True)
    subscription_plan = Column(Enum(SubscriptionPlan), default=SubscriptionPlan.starter)
    subscription_status = Column(Enum(SubscriptionStatus), default=SubscriptionStatus.trialing)
    trial_ends_at = Column(DateTime)
    subscription_ends_at = Column(DateTime)

    # AI config
    ai_greeting_style = Column(String(50), default="conversational")
    ai_auto_reply_enabled = Column(Boolean, default=True)
    ai_auto_reply_hours = Column(JSON, default={"start": 0, "end": 24})  # 24/7 by default
    ai_hot_lead_score_threshold = Column(Integer, default=75)
    ai_qualification_questions = Column(JSON, default=[])

    # Notification preferences
    notify_hot_lead_sms = Column(Boolean, default=True)
    notify_hot_lead_email = Column(Boolean, default=True)
    notify_daily_summary = Column(Boolean, default=True)
    notify_summary_time = Column(String(10), default="07:00")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    # Relationships
    leads = relationship("Lead", back_populates="agent", cascade="all, delete-orphan")
    campaigns = relationship("Campaign", back_populates="agent", cascade="all, delete-orphan")
    ad_accounts = relationship("AdAccount", back_populates="agent", cascade="all, delete-orphan")


class Lead(Base):
    """A potential buyer/seller captured from any ad platform"""
    __tablename__ = "leads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False, index=True)

    # Contact info
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100))
    email = Column(String(255), index=True)
    phone = Column(String(50))

    # Lead details
    status = Column(Enum(LeadStatus), default=LeadStatus.new, index=True)
    source = Column(Enum(LeadSource), default=LeadSource.manual)
    ai_score = Column(Integer, default=0)          # 0-100, calculated by AI
    budget_min = Column(Integer)
    budget_max = Column(Integer)
    timeline = Column(String(100))                  # e.g. "1-2 months"
    intent = Column(String(20))                     # "buy", "sell", "both"
    location_interest = Column(String(255))         # Area they want to buy in
    bedrooms = Column(Integer)
    bathrooms = Column(Float)
    must_haves = Column(JSON, default=[])
    notes = Column(Text)

    # Qualification
    is_pre_approved = Column(Boolean)
    is_cash_buyer = Column(Boolean, default=False)
    current_situation = Column(String(50))          # "renting", "owns", "selling first"
    urgency_level = Column(String(20))              # "low", "medium", "high"

    # Tracking
    birthday = Column(DateTime)
    last_contacted_at = Column(DateTime)
    converted_at = Column(DateTime)
    ad_campaign_id = Column(String(255))            # Platform-specific campaign ID
    ad_set_id = Column(String(255))
    ad_id = Column(String(255))
    utm_source = Column(String(100))
    utm_medium = Column(String(100))
    utm_campaign = Column(String(255))

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    agent = relationship("Agent", back_populates="leads")
    messages = relationship("Message", back_populates="lead", cascade="all, delete-orphan", order_by="Message.created_at")
    campaign_enrollments = relationship("CampaignEnrollment", back_populates="lead", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_leads_agent_status", "agent_id", "status"),
        Index("ix_leads_agent_created", "agent_id", "created_at"),
    )


class Message(Base):
    """Individual chat message in a lead conversation"""
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False, index=True)

    role = Column(Enum(MessageRole), nullable=False)
    content = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)

    # AI metadata
    ai_model = Column(String(50))                   # e.g. "gpt-4o"
    ai_prompt_tokens = Column(Integer)
    ai_completion_tokens = Column(Integer)
    triggered_hot_lead_alert = Column(Boolean, default=False)
    score_at_time = Column(Integer)                 # Lead score when message was sent

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationship
    lead = relationship("Lead", back_populates="messages")


class Campaign(Base):
    """An email drip campaign"""
    __tablename__ = "campaigns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False, index=True)

    name = Column(String(255), nullable=False)
    description = Column(Text)
    campaign_type = Column(Enum(CampaignType), default=CampaignType.nurture)
    is_active = Column(Boolean, default=True)
    ai_generated = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    agent = relationship("Agent", back_populates="campaigns")
    steps = relationship("CampaignStep", back_populates="campaign", cascade="all, delete-orphan", order_by="CampaignStep.step_order")
    enrollments = relationship("CampaignEnrollment", back_populates="campaign", cascade="all, delete-orphan")


class CampaignStep(Base):
    """A single email in a drip campaign sequence"""
    __tablename__ = "campaign_steps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False, index=True)

    step_order = Column(Integer, nullable=False)
    delay_days = Column(Integer, default=0)         # Days after previous step
    subject = Column(String(500), nullable=False)
    body_html = Column(Text, nullable=False)
    body_text = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    campaign = relationship("Campaign", back_populates="steps")


class CampaignEnrollment(Base):
    """Tracks which leads are enrolled in which campaigns"""
    __tablename__ = "campaign_enrollments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False)

    current_step = Column(Integer, default=0)
    next_send_at = Column(DateTime)
    is_active = Column(Boolean, default=True)
    enrolled_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)

    # Relationships
    lead = relationship("Lead", back_populates="campaign_enrollments")
    campaign = relationship("Campaign", back_populates="enrollments")

    __table_args__ = (
        UniqueConstraint("lead_id", "campaign_id", name="uq_lead_campaign"),
    )


class AdAccount(Base):
    """Ad platform account connected to an agent"""
    __tablename__ = "ad_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False, index=True)

    platform = Column(String(50), nullable=False)   # meta, google, tiktok, waze
    account_id = Column(String(255))                # Platform's account ID
    access_token = Column(Text)                     # Encrypted OAuth token
    refresh_token = Column(Text)
    token_expires_at = Column(DateTime)
    is_connected = Column(Boolean, default=False)
    monthly_budget = Column(Float, default=0)

    # Cached performance (refreshed hourly)
    cached_spend = Column(Float, default=0)
    cached_leads = Column(Integer, default=0)
    cached_cpl = Column(Float, default=0)
    cached_roas = Column(Float, default=0)
    cache_updated_at = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    agent = relationship("Agent", back_populates="ad_accounts")

    __table_args__ = (
        UniqueConstraint("agent_id", "platform", name="uq_agent_platform"),
    )


class AdOptimizationLog(Base):
    """Tracks AI budget optimization decisions"""
    __tablename__ = "ad_optimization_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False, index=True)

    recommendation = Column(Text)
    from_platform = Column(String(50))
    to_platform = Column(String(50))
    amount_shifted = Column(Float)
    projected_additional_leads = Column(Integer)
    was_applied = Column(Boolean, default=False)
    applied_at = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow)


# ── DB INIT ───────────────────────────────────────────────────────────────────

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
