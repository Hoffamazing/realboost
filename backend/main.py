"""
RealBoost AI — FastAPI Backend
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import will happen after DB init
async def init_routers(app):
    try:
        from routers import agents, leads, conversations, campaigns, ads, billing, webhooks, ai
        app.include_router(agents.router, prefix="/api/agents", tags=["Agents"])
        app.include_router(leads.router, prefix="/api/leads", tags=["Leads"])
        app.include_router(conversations.router, prefix="/api/conversations", tags=["Conversations"])
        app.include_router(campaigns.router, prefix="/api/campaigns", tags=["Campaigns"])
        app.include_router(ads.router, prefix="/api/ads", tags=["Ads"])
        app.include_router(billing.router, prefix="/api/billing", tags=["Billing"])
        app.include_router(webhooks.router, prefix="/api/webhooks", tags=["Webhooks"])
        app.include_router(ai.router, prefix="/api/ai", tags=["AI"])
        logger.info("All routers loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load routers: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting RealBoost AI backend...")
    try:
        from models.database import init_db
        await init_db()
        await init_routers(app)
    except Exception as e:
        logger.error(f"Startup error: {e}")
    yield
    logger.info("Shutting down...")

app = FastAPI(
    title="RealBoost AI API",
    description="AI-powered real estate marketing automation platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "https://app.realboost.ai",
        "https://www.realboost.ai",
        "*"  # Allow all for now during setup
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "realboost-api", "version": "1.0.0"}

@app.get("/")
async def root():
    return {"message": "RealBoost AI API", "docs": "/docs"}
