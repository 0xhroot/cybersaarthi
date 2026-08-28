"""Aggregates all v1 API routes."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import health_router

api_router = APIRouter()
api_router.include_router(health_router, prefix="/api/v1")
