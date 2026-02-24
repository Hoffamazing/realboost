"""
RealBoost AI — FastAPI Backend
Multi-tenant Real Estate Marketing SaaS
"""

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from contextlib import asynccontextmanager
import logging

from routers import agents, leads, conversations, campaigns, ads, billing, webhooks, ai
from models.database import init_db
from middleware.auth import verify_token

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting RealBoost AI backend...")
    await init_db()
    yield
    logger.info("Shutting down...")


app = FastAPI(
    title="RealBoost AI API",
    description="AI-powered real estate marketing automation platform",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "https://app.realboost.ai",
        "https://www.realboost.ai",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── ROUTERS ───────────────────────────────────────────────────────────────────
app.include_router(agents.router,        prefix="/api/agents",        tags=["Agents"])
app.include_router(leads.router,         prefix="/api/leads",         tags=["Leads"])
app.include_router(conversations.router, prefix="/api/conversations",  tags=["Conversations"])
app.include_router(campaigns.router,     prefix="/api/campaigns",      tags=["Campaigns"])
app.include_router(ads.router,           prefix="/api/ads",            tags=["Ads"])
app.include_router(billing.router,       prefix="/api/billing",        tags=["Billing"])
app.include_router(webhooks.router,      prefix="/api/webhooks",       tags=["Webhooks"])
app.include_router(ai.router,            prefix="/api/ai",             tags=["AI"])


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "realboost-api", "version": "1.0.0"}


@app.get("/")
async def root():
    return {"message": "RealBoost AI API", "docs": "/docs"}
