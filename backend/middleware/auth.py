"""
Authentication middleware
JWT-based auth for multi-tenant agent sessions
"""

from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import JWTError, jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta
from typing import Optional
import os

from models.database import Agent, get_db

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-this-in-production-use-256-bit-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(agent_id: str, email: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": str(agent_id), "email": email, "exp": expire},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_agent(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Agent:
    payload = decode_token(credentials.credentials)
    agent_id = payload.get("sub")
    if not agent_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.is_active == True))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=401, detail="Agent not found or inactive")

    return agent


async def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    return decode_token(credentials.credentials)


def require_active_subscription(agent: Agent = Depends(get_current_agent)) -> Agent:
    if agent.subscription_status not in ("active", "trialing"):
        raise HTTPException(
            status_code=402,
            detail="Active subscription required. Please update your billing at /billing.",
        )
    return agent
