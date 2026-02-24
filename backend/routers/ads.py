"""
STEP 4: Ads Router
──────────────────
- Meta (Facebook) Ads API — full integration
- Google Ads API — structured stub (ready for credentials)
- TikTok Ads API — structured stub
- Waze Ads — structured stub
- AI budget optimization endpoint
- Platform performance aggregation
- Webhook receiver for lead events from Meta
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
from uuid import UUID
import httpx
import os
import logging
import hmac
import hashlib

from models.database import Agent, AdAccount, AdOptimizationLog, Lead, LeadSource, get_db
from middleware.auth import get_current_agent, require_active_subscription
from services.ai_service import optimize_ad_budget

logger = logging.getLogger(__name__)
router = APIRouter()

META_APP_ID = os.getenv("META_APP_ID")
META_APP_SECRET = os.getenv("META_APP_SECRET")
META_API_VERSION = "v19.0"
META_BASE_URL = f"https://graph.facebook.com/{META_API_VERSION}"


# ── SCHEMAS ───────────────────────────────────────────────────────────────────

class AdAccountConnect(BaseModel):
    platform: str            # meta, google, tiktok, waze
    access_token: str
    account_id: str

class BudgetUpdate(BaseModel):
    platform: str
    monthly_budget: float

class CampaignCreate(BaseModel):
    platform: str
    name: str
    objective: str = "LEAD_GENERATION"
    daily_budget: float       # in dollars
    target_location: Optional[str] = None
    target_radius_miles: int = 25
    age_min: int = 25
    age_max: int = 65
    ad_creative_headline: Optional[str] = None
    ad_creative_body: Optional[str] = None


# ── PERFORMANCE AGGREGATION ───────────────────────────────────────────────────

@router.get("/performance")
async def get_ad_performance(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate performance across all connected platforms"""
    result = await db.execute(select(AdAccount).where(AdAccount.agent_id == agent.id))
    accounts = result.scalars().all()

    platforms = []
    for account in accounts:
        # Refresh cache if stale (> 1 hour)
        needs_refresh = (
            not account.cache_updated_at or
            datetime.utcnow() - account.cache_updated_at > timedelta(hours=1)
        )
        if needs_refresh and account.is_connected:
            await _refresh_platform_cache(account, db)

        platforms.append({
            "platform": account.platform,
            "is_connected": account.is_connected,
            "monthly_budget": account.monthly_budget,
            "spend": account.cached_spend,
            "leads": account.cached_leads,
            "cpl": account.cached_cpl,
            "roas": account.cached_roas,
            "cache_updated_at": account.cache_updated_at.isoformat() if account.cache_updated_at else None,
        })

    # Total stats
    total_spend = sum(p["spend"] for p in platforms)
    total_leads = sum(p["leads"] for p in platforms)

    return {
        "platforms": platforms,
        "totals": {
            "spend": total_spend,
            "leads": total_leads,
            "avg_cpl": round(total_spend / total_leads, 2) if total_leads > 0 else 0,
        },
    }


@router.post("/optimize")
async def run_ai_optimization(
    agent: Agent = Depends(require_active_subscription),
    db: AsyncSession = Depends(get_db),
):
    """
    Run AI analysis on all platform data and get budget reallocation recommendation.
    Optionally auto-applies the recommendation.
    """
    result = await db.execute(select(AdAccount).where(AdAccount.agent_id == agent.id))
    accounts = result.scalars().all()

    if not accounts:
        raise HTTPException(status_code=400, detail="No ad accounts connected")

    platforms_data = [
        {
            "platform": a.platform,
            "monthly_budget": a.monthly_budget,
            "spend": a.cached_spend,
            "leads": a.cached_leads,
            "cpl": a.cached_cpl,
            "roas": a.cached_roas,
        }
        for a in accounts if a.is_connected
    ]

    recommendation = await optimize_ad_budget(platforms_data)

    # Log the recommendation
    log = AdOptimizationLog(
        agent_id=agent.id,
        recommendation=recommendation.get("recommendation"),
        from_platform=recommendation.get("from_platform"),
        to_platform=recommendation.get("to_platform"),
        amount_shifted=recommendation.get("amount_to_shift"),
        projected_additional_leads=recommendation.get("projected_additional_leads"),
    )
    db.add(log)

    return {**recommendation, "log_id": str(log.id)}


@router.post("/optimize/{log_id}/apply")
async def apply_optimization(
    log_id: UUID,
    agent: Agent = Depends(require_active_subscription),
    db: AsyncSession = Depends(get_db),
):
    """Apply an AI optimization recommendation to actual ad budgets"""
    result = await db.execute(
        select(AdOptimizationLog).where(
            AdOptimizationLog.id == log_id,
            AdOptimizationLog.agent_id == agent.id
        )
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Optimization log not found")

    # Update budgets
    from_acct_result = await db.execute(
        select(AdAccount).where(AdAccount.agent_id == agent.id, AdAccount.platform == log.from_platform)
    )
    to_acct_result = await db.execute(
        select(AdAccount).where(AdAccount.agent_id == agent.id, AdAccount.platform == log.to_platform)
    )

    from_acct = from_acct_result.scalar_one_or_none()
    to_acct = to_acct_result.scalar_one_or_none()

    if from_acct and log.amount_shifted:
        from_acct.monthly_budget = max(0, from_acct.monthly_budget - log.amount_shifted)
    if to_acct and log.amount_shifted:
        to_acct.monthly_budget = to_acct.monthly_budget + log.amount_shifted

    log.was_applied = True
    log.applied_at = datetime.utcnow()

    return {"status": "applied", "message": f"Shifted ${log.amount_shifted} from {log.from_platform} to {log.to_platform}"}


# ── ACCOUNT MANAGEMENT ────────────────────────────────────────────────────────

@router.get("/accounts")
async def list_ad_accounts(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AdAccount).where(AdAccount.agent_id == agent.id))
    return result.scalars().all()


@router.post("/accounts/connect")
async def connect_ad_account(
    data: AdAccountConnect,
    agent: Agent = Depends(require_active_subscription),
    db: AsyncSession = Depends(get_db),
):
    """Connect an ad platform account via OAuth token"""
    valid_platforms = ["meta", "google", "tiktok", "waze"]
    if data.platform not in valid_platforms:
        raise HTTPException(status_code=400, detail=f"Platform must be one of: {valid_platforms}")

    result = await db.execute(
        select(AdAccount).where(AdAccount.agent_id == agent.id, AdAccount.platform == data.platform)
    )
    account = result.scalar_one_or_none()

    if not account:
        account = AdAccount(agent_id=agent.id, platform=data.platform)
        db.add(account)

    account.access_token = data.access_token  # In prod: encrypt with Fernet
    account.account_id = data.account_id
    account.is_connected = True

    # Verify the token works by fetching initial data
    if data.platform == "meta":
        verified = await _verify_meta_token(data.access_token, data.account_id)
        if not verified:
            raise HTTPException(status_code=400, detail="Meta access token verification failed")

    await db.flush()
    return {"status": "connected", "platform": data.platform}


@router.patch("/accounts/{platform}/budget")
async def update_platform_budget(
    platform: str,
    data: BudgetUpdate,
    agent: Agent = Depends(require_active_subscription),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AdAccount).where(AdAccount.agent_id == agent.id, AdAccount.platform == platform)
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Ad account not found")

    account.monthly_budget = data.monthly_budget
    return {"status": "updated", "platform": platform, "monthly_budget": data.monthly_budget}


# ── META ADS API ──────────────────────────────────────────────────────────────

@router.post("/meta/campaigns")
async def create_meta_campaign(
    data: CampaignCreate,
    agent: Agent = Depends(require_active_subscription),
    db: AsyncSession = Depends(get_db),
):
    """Create a lead generation campaign on Meta (Facebook/Instagram)"""
    acct_result = await db.execute(
        select(AdAccount).where(AdAccount.agent_id == agent.id, AdAccount.platform == "meta")
    )
    account = acct_result.scalar_one_or_none()
    if not account or not account.is_connected:
        raise HTTPException(status_code=400, detail="Meta Ads account not connected")

    try:
        async with httpx.AsyncClient() as client:
            # Step 1: Create campaign
            campaign_resp = await client.post(
                f"{META_BASE_URL}/act_{account.account_id}/campaigns",
                params={
                    "access_token": account.access_token,
                    "name": data.name,
                    "objective": data.objective,
                    "status": "PAUSED",  # Start paused for review
                    "special_ad_categories": ["HOUSING"],  # Required for real estate
                },
            )
            campaign_resp.raise_for_status()
            campaign_id = campaign_resp.json()["id"]

            # Step 2: Create ad set with targeting
            daily_budget_cents = int(data.daily_budget * 100)
            location_targeting = await _build_meta_location_targeting(
                data.target_location or agent.location or "United States",
                data.target_radius_miles,
            )

            adset_resp = await client.post(
                f"{META_BASE_URL}/act_{account.account_id}/adsets",
                params={
                    "access_token": account.access_token,
                    "campaign_id": campaign_id,
                    "name": f"{data.name} - Ad Set",
                    "daily_budget": daily_budget_cents,
                    "billing_event": "IMPRESSIONS",
                    "optimization_goal": "LEAD_GENERATION",
                    "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
                    "targeting": {
                        "geo_locations": location_targeting,
                        "age_min": data.age_min,
                        "age_max": data.age_max,
                        "interests": [
                            {"id": "6003020834693", "name": "Real estate"},
                            {"id": "6003255229069", "name": "Home ownership"},
                            {"id": "6003195624287", "name": "Property"},
                        ],
                    },
                    "status": "PAUSED",
                },
            )
            adset_resp.raise_for_status()
            adset_id = adset_resp.json()["id"]

            logger.info(f"Created Meta campaign {campaign_id} for agent {agent.email}")
            return {
                "status": "created",
                "campaign_id": campaign_id,
                "adset_id": adset_id,
                "note": "Campaign created in PAUSED state — activate in Meta Ads Manager after review",
            }

    except httpx.HTTPStatusError as e:
        logger.error(f"Meta API error: {e.response.text}")
        raise HTTPException(status_code=400, detail=f"Meta API error: {e.response.text}")
    except Exception as e:
        logger.error(f"Campaign creation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to create campaign")


@router.get("/meta/performance")
async def get_meta_performance(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Fetch real performance data from Meta Ads API"""
    acct_result = await db.execute(
        select(AdAccount).where(AdAccount.agent_id == agent.id, AdAccount.platform == "meta")
    )
    account = acct_result.scalar_one_or_none()
    if not account or not account.is_connected:
        return {"error": "Meta not connected", "data": None}

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{META_BASE_URL}/act_{account.account_id}/insights",
                params={
                    "access_token": account.access_token,
                    "fields": "spend,impressions,clicks,leads,actions,cost_per_action_type",
                    "date_preset": "this_month",
                    "level": "account",
                },
            )
            resp.raise_for_status()
            data = resp.json().get("data", [{}])[0]

            spend = float(data.get("spend", 0))
            leads = int(data.get("leads", 0))
            cpl = round(spend / leads, 2) if leads > 0 else 0

            # Update cache
            account.cached_spend = spend
            account.cached_leads = leads
            account.cached_cpl = cpl
            account.cache_updated_at = datetime.utcnow()

            return {"platform": "meta", "spend": spend, "leads": leads, "cpl": cpl, "raw": data}

    except Exception as e:
        logger.error(f"Meta performance fetch failed: {e}")
        return {"error": str(e), "data": None}


# ── META LEAD WEBHOOK ─────────────────────────────────────────────────────────

@router.post("/meta/webhook/leads", include_in_schema=False)
async def meta_lead_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Receives real-time lead notifications from Meta Lead Ads.
    When someone fills out a Facebook/Instagram lead form, this fires.
    Creates a new Lead record and starts AI qualification.
    """
    # Verify Meta signature
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(
        META_APP_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=403, detail="Invalid Meta webhook signature")

    payload = await request.json()

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") == "leadgen":
                lead_data = change.get("value", {})
                background_tasks.add_task(_process_meta_lead, lead_data, db)

    return {"status": "ok"}


@router.get("/meta/webhook/leads", include_in_schema=False)
async def verify_meta_webhook(request: Request):
    """Meta webhook verification challenge"""
    params = request.query_params
    if (
        params.get("hub.mode") == "subscribe" and
        params.get("hub.verify_token") == os.getenv("META_WEBHOOK_VERIFY_TOKEN")
    ):
        return int(params.get("hub.challenge", 0))
    raise HTTPException(status_code=403, detail="Verification failed")


# ── GOOGLE ADS STUB ───────────────────────────────────────────────────────────

@router.get("/google/performance")
async def get_google_performance(
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """
    Google Ads performance data.
    Full implementation: install google-ads library, authenticate via OAuth2,
    use CustomerService + CampaignService + GoogleAdsService queries.
    Docs: https://developers.google.com/google-ads/api/docs/start
    """
    return {
        "platform": "google",
        "status": "stub — connect Google Ads API credentials to activate",
        "implementation_guide": {
            "library": "google-ads-python",
            "auth": "OAuth2 with refresh token",
            "key_service": "GoogleAdsService for GAQL queries",
            "lead_tracking": "Conversion tracking via Google Tag Manager",
        },
        "mock_data": {"spend": 980, "leads": 31, "cpl": 31.61, "roas": 3.8},
    }


# ── TIKTOK ADS STUB ───────────────────────────────────────────────────────────

@router.get("/tiktok/performance")
async def get_tiktok_performance(
    agent: Agent = Depends(get_current_agent),
):
    """
    TikTok Ads performance.
    Full implementation: TikTok Marketing API v1.3
    POST to https://business-api.tiktok.com/open_api/v1.3/report/integrated/get/
    Auth: App access token + advertiser_id
    Lead Gen: TikTok Instant Lead Forms
    """
    return {
        "platform": "tiktok",
        "status": "stub — connect TikTok Marketing API credentials",
        "implementation_guide": {
            "base_url": "https://business-api.tiktok.com/open_api/v1.3/",
            "auth": "App access token in Authorization header",
            "lead_forms": "Lead Generation objective with Instant Form",
            "webhook": "Real-time lead notifications via TikTok webhook",
        },
        "mock_data": {"spend": 520, "leads": 22, "cpl": 23.64, "roas": 2.9},
    }


# ── WAZE ADS STUB ─────────────────────────────────────────────────────────────

@router.get("/waze/performance")
async def get_waze_performance(
    agent: Agent = Depends(get_current_agent),
):
    """
    Waze Ads (Branded Pins) performance.
    Waze uses a managed API — contact Waze Ads support for API access.
    Best for: local brand awareness when buyers are near listings/offices.
    """
    return {
        "platform": "waze",
        "status": "stub — Waze Ads requires managed API access",
        "implementation_guide": {
            "contact": "advertise@waze.com for API access",
            "ad_types": ["Branded Pin", "Nearby Arrow", "Zero-Speed Takeover"],
            "best_use": "Drive traffic to open houses and office locations",
            "reporting": "Available via Waze Ads Manager dashboard export",
        },
        "mock_data": {"spend": 380, "leads": 14, "cpl": 27.14, "roas": 2.1},
    }


# ── INTERNAL HELPERS ──────────────────────────────────────────────────────────

async def _verify_meta_token(access_token: str, account_id: str) -> bool:
    """Verify Meta access token is valid"""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{META_BASE_URL}/me",
                params={"access_token": access_token, "fields": "id,name"},
            )
            return resp.status_code == 200
    except Exception:
        return False


async def _refresh_platform_cache(account: AdAccount, db: AsyncSession):
    """Refresh cached performance data for a platform"""
    if account.platform == "meta":
        try:
            async with httpx.AsyncClient() as http:
                resp = await http.get(
                    f"{META_BASE_URL}/act_{account.account_id}/insights",
                    params={
                        "access_token": account.access_token,
                        "fields": "spend,leads",
                        "date_preset": "this_month",
                    },
                )
                data = resp.json().get("data", [{}])[0]
                spend = float(data.get("spend", 0))
                leads = int(data.get("leads", 0))
                account.cached_spend = spend
                account.cached_leads = leads
                account.cached_cpl = round(spend / leads, 2) if leads > 0 else 0
                account.cache_updated_at = datetime.utcnow()
        except Exception as e:
            logger.warning(f"Failed to refresh Meta cache: {e}")


async def _build_meta_location_targeting(location: str, radius_miles: int) -> dict:
    """Build Meta geo-targeting object for a location string"""
    # In production: geocode the location string to lat/lng using Google Geocoding API
    # For now, return a US city targeting structure
    return {
        "custom_locations": [{
            "address_string": location,
            "radius": radius_miles,
            "distance_unit": "mile",
        }]
    }


async def _process_meta_lead(lead_data: dict, db: AsyncSession):
    """
    Background task: parse Meta lead form submission and create Lead record.
    Meta sends field data as a list of {name, values} pairs.
    """
    try:
        ad_id = lead_data.get("ad_id")
        campaign_id = lead_data.get("campaign_id")
        form_data = {f["name"]: f["values"][0] for f in lead_data.get("field_data", [])}

        # Find agent by their Meta ad account
        agent_result = await db.execute(
            select(AdAccount).where(AdAccount.platform == "meta")
        )
        # In production: match by campaign_id -> agent. For now use first account
        ad_account = agent_result.scalars().first()
        if not ad_account:
            return

        lead = Lead(
            agent_id=ad_account.agent_id,
            first_name=form_data.get("first_name", ""),
            last_name=form_data.get("last_name"),
            email=form_data.get("email"),
            phone=form_data.get("phone_number"),
            source=LeadSource.meta,
            ad_campaign_id=str(campaign_id),
            ad_id=str(ad_id),
        )
        db.add(lead)
        await db.commit()
        logger.info(f"Created Meta lead: {lead.first_name} {lead.last_name}")

    except Exception as e:
        logger.error(f"Failed to process Meta lead: {e}")
