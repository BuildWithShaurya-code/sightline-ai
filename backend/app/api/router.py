"""
SightLine AI - Main API Router
Mounts active endpoints under the configured API prefix.
"""

from fastapi import APIRouter
from .endpoints import account_settings, analysis, auth, capabilities, dispatches, health, incidents, inference, videos

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(capabilities.router)
api_router.include_router(auth.router)
api_router.include_router(account_settings.router)
api_router.include_router(inference.router)
api_router.include_router(videos.router)
api_router.include_router(analysis.router)
api_router.include_router(incidents.router)
api_router.include_router(dispatches.router)


