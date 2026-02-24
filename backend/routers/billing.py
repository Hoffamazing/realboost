"""
STEP 3: Stripe Billing Router
─────────────────────────────
- Subscription tiers: Starter ($99), Pro ($249), Team ($499)
- Checkout session creation
- Customer portal (self-serve billing)
- Webhook handler for subscription events
- Trial to paid conversion
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
import stripe
import os
import logging

from models.database import Agent, SubscriptionPlan, SubscriptionStatus, get_db
from middleware.auth import get_current_agent

logger = logging.getLogger(__name__)
router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

# ── PRICING TIERS ─────────────────────────────────────────────────────────────
PLANS = {
    "starter": {
        "name": "Starter",
        "price_id": os.getenv("STRIPE_STARTER_PRICE_ID", "price_starter"),
        "amount": 9900,       # $99/mo in cents
        "description": "1 agent · 2 ad platforms · AI chat · Basic drip",
        "features": [
            "Up to 200 leads/month",
            "Meta + Google Ads",
            "AI lead qualification",
            "3 drip campaigns",
            "Hot lead SMS alerts",
        ],
    },
    "pro": {
        "name": "Pro",
        "price_id": os.getenv("STRIPE_PRO_PRICE_ID", "price_pro"),
        "amount": 24900,      # $249/mo in cents
        "description": "1 agent · All 4 platforms · Full AI suite · Unlimited campaigns",
        "features": [
            "Unlimited leads",
            "Meta + Google + TikTok + Waze",
            "AI lead qualification",
            "Unlimited drip campaigns",
            "AI email generator",
            "Hot lead call connect",
            "Monthly newsletter AI",
            "Birthday automation",
            "Ad budget optimization",
        ],
    },
    "team": {
        "name": "Team",
        "price_id": os.getenv("STRIPE_TEAM_PRICE_ID", "price_team"),
        "amount": 49900,      # $499/mo in cents
        "description": "Up to 5 agents · All features · Team dashboard + reporting",
        "features": [
            "Everything in Pro",
            "Up to 5 agents",
            "Team lead routing",
            "Shared campaign library",
            "Team performance dashboard",
            "Priority support",
            "Custom AI persona",
        ],
    },
}


# ── SCHEMAS ───────────────────────────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    plan: str  # starter, pro, team
    success_url: str = "https://app.realboost.ai/billing/success"
    cancel_url: str = "https://app.realboost.ai/billing"


class PortalRequest(BaseModel):
    return_url: str = "https://app.realboost.ai/settings"


# ── ENDPOINTS ─────────────────────────────────────────────────────────────────

@router.get("/plans")
async def get_plans():
    """Return all available subscription plans (public endpoint)"""
    return PLANS


@router.get("/status")
async def get_billing_status(agent: Agent = Depends(get_current_agent)):
    """Get current agent's billing status"""
    return {
        "plan": agent.subscription_plan.value if agent.subscription_plan else None,
        "status": agent.subscription_status.value if agent.subscription_status else None,
        "trial_ends_at": agent.trial_ends_at.isoformat() if agent.trial_ends_at else None,
        "subscription_ends_at": agent.subscription_ends_at.isoformat() if agent.subscription_ends_at else None,
        "stripe_customer_id": agent.stripe_customer_id,
        "has_active_subscription": agent.subscription_status in (
            SubscriptionStatus.active, SubscriptionStatus.trialing
        ),
    }


@router.post("/checkout")
async def create_checkout_session(
    data: CheckoutRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a Stripe Checkout session for the selected plan.
    Agent is redirected to Stripe's hosted checkout page.
    """
    if data.plan not in PLANS:
        raise HTTPException(status_code=400, detail=f"Invalid plan. Choose: {list(PLANS.keys())}")

    plan = PLANS[data.plan]

    # Create or retrieve Stripe customer
    if not agent.stripe_customer_id:
        customer = stripe.Customer.create(
            email=agent.email,
            name=agent.full_name,
            metadata={"agent_id": str(agent.id), "brokerage": agent.brokerage or ""},
        )
        agent.stripe_customer_id = customer.id

    # If agent already has an active subscription, redirect to portal
    if agent.stripe_subscription_id and agent.subscription_status == SubscriptionStatus.active:
        portal = stripe.billing_portal.Session.create(
            customer=agent.stripe_customer_id,
            return_url=data.cancel_url,
        )
        return {"url": portal.url, "type": "portal"}

    # Create checkout session
    session = stripe.checkout.Session.create(
        customer=agent.stripe_customer_id,
        payment_method_types=["card"],
        line_items=[{"price": plan["price_id"], "quantity": 1}],
        mode="subscription",
        success_url=f"{data.success_url}?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=data.cancel_url,
        subscription_data={
            "trial_period_days": 14 if not agent.stripe_subscription_id else 0,
            "metadata": {"agent_id": str(agent.id), "plan": data.plan},
        },
        metadata={"agent_id": str(agent.id), "plan": data.plan},
        allow_promotion_codes=True,
    )

    return {"url": session.url, "type": "checkout", "session_id": session.id}


@router.post("/portal")
async def create_customer_portal(
    data: PortalRequest,
    agent: Agent = Depends(get_current_agent),
):
    """
    Create a Stripe Customer Portal session.
    Agents manage their subscription, update payment method, view invoices.
    """
    if not agent.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No billing account found. Please subscribe first.")

    session = stripe.billing_portal.Session.create(
        customer=agent.stripe_customer_id,
        return_url=data.return_url,
    )
    return {"url": session.url}


@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="stripe-signature"),
    db: AsyncSession = Depends(get_db),
):
    """
    Stripe webhook handler.
    Processes subscription lifecycle events to update agent access.
    """
    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(payload, stripe_signature, STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    event_type = event["type"]
    data = event["data"]["object"]

    logger.info(f"Stripe webhook received: {event_type}")

    # ── SUBSCRIPTION CREATED / UPDATED ────────────────────────────────────────
    if event_type in ("customer.subscription.created", "customer.subscription.updated"):
        await _handle_subscription_updated(data, db)

    # ── SUBSCRIPTION DELETED (canceled) ───────────────────────────────────────
    elif event_type == "customer.subscription.deleted":
        await _handle_subscription_deleted(data, db)

    # ── PAYMENT SUCCEEDED ─────────────────────────────────────────────────────
    elif event_type == "invoice.payment_succeeded":
        customer_id = data.get("customer")
        result = await db.execute(select(Agent).where(Agent.stripe_customer_id == customer_id))
        agent = result.scalar_one_or_none()
        if agent:
            agent.subscription_status = SubscriptionStatus.active
            logger.info(f"Payment succeeded for agent {agent.email}")

    # ── PAYMENT FAILED ────────────────────────────────────────────────────────
    elif event_type == "invoice.payment_failed":
        customer_id = data.get("customer")
        result = await db.execute(select(Agent).where(Agent.stripe_customer_id == customer_id))
        agent = result.scalar_one_or_none()
        if agent:
            agent.subscription_status = SubscriptionStatus.past_due
            logger.warning(f"Payment failed for agent {agent.email}")
            # TODO: Send payment failed email to agent

    # ── TRIAL ENDING SOON ─────────────────────────────────────────────────────
    elif event_type == "customer.subscription.trial_will_end":
        customer_id = data.get("customer")
        result = await db.execute(select(Agent).where(Agent.stripe_customer_id == customer_id))
        agent = result.scalar_one_or_none()
        if agent:
            logger.info(f"Trial ending soon for {agent.email}")
            # TODO: Send trial ending email

    await db.commit()
    return {"status": "ok"}


# ── WEBHOOK HELPERS ───────────────────────────────────────────────────────────

async def _handle_subscription_updated(subscription: dict, db: AsyncSession):
    customer_id = subscription.get("customer")
    result = await db.execute(select(Agent).where(Agent.stripe_customer_id == customer_id))
    agent = result.scalar_one_or_none()

    if not agent:
        logger.warning(f"No agent found for Stripe customer {customer_id}")
        return

    # Map Stripe status to our enum
    stripe_status = subscription.get("status")
    status_map = {
        "active": SubscriptionStatus.active,
        "trialing": SubscriptionStatus.trialing,
        "past_due": SubscriptionStatus.past_due,
        "canceled": SubscriptionStatus.canceled,
        "unpaid": SubscriptionStatus.past_due,
    }
    agent.subscription_status = status_map.get(stripe_status, SubscriptionStatus.active)
    agent.stripe_subscription_id = subscription.get("id")

    # Determine plan from metadata or price ID
    metadata = subscription.get("metadata", {})
    plan_name = metadata.get("plan", "pro")
    plan_map = {"starter": SubscriptionPlan.starter, "pro": SubscriptionPlan.pro, "team": SubscriptionPlan.team}
    agent.subscription_plan = plan_map.get(plan_name, SubscriptionPlan.pro)

    # Set subscription end date
    current_period_end = subscription.get("current_period_end")
    if current_period_end:
        from datetime import timezone
        agent.subscription_ends_at = datetime.fromtimestamp(current_period_end, tz=timezone.utc).replace(tzinfo=None)

    logger.info(f"Updated subscription for {agent.email}: {agent.subscription_plan.value} / {agent.subscription_status.value}")


async def _handle_subscription_deleted(subscription: dict, db: AsyncSession):
    customer_id = subscription.get("customer")
    result = await db.execute(select(Agent).where(Agent.stripe_customer_id == customer_id))
    agent = result.scalar_one_or_none()

    if agent:
        agent.subscription_status = SubscriptionStatus.canceled
        logger.info(f"Subscription canceled for {agent.email}")
