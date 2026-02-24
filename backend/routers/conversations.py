"""Conversations Router"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from models.database import Lead, Message, Agent, LeadStatus, get_db
from middleware.auth import get_current_agent

router = APIRouter()


@router.get("/")
async def list_conversations(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Get all leads that have at least one message, sorted by most recent activity"""
    result = await db.execute(
        select(Lead).where(Lead.agent_id == agent.id).order_by(desc(Lead.updated_at))
    )
    leads = result.scalars().all()
    conversations = []
    for lead in leads:
        last_msg_result = await db.execute(
            select(Message).where(Message.lead_id == lead.id).order_by(desc(Message.created_at)).limit(1)
        )
        last_msg = last_msg_result.scalar_one_or_none()
        if last_msg:
            conversations.append({
                "lead_id": str(lead.id),
                "lead_name": f"{lead.first_name} {lead.last_name or ''}".strip(),
                "lead_status": lead.status.value,
                "ai_score": lead.ai_score,
                "last_message": last_msg.content[:100],
                "last_message_role": last_msg.role.value,
                "last_message_at": last_msg.created_at.isoformat(),
            })
    return conversations
