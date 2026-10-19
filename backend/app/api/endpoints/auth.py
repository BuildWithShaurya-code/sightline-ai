"""
SightLine AI - Authentication Endpoints
Provides authenticated operator profile lookup (GET /api/v1/auth/me)
Supabase alone issues access tokens; no local password login is exposed.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...core.auth import AuthenticatedUser, get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


class UserProfileResponse(BaseModel):
    id: str
    email: Optional[str] = None
    role: str = "authenticated"
    operatorId: str


@router.post('/login', include_in_schema=False)
async def removed_local_login():
    # Explicit tombstone also prevents the static frontend mount returning 405.
    raise HTTPException(status_code=404, detail='Not found')


@router.get(
    "/me",
    response_model=UserProfileResponse,
    summary="Retrieve current verified operator profile",
)
async def get_me(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> UserProfileResponse:
    """
    Returns profile for currently verified user token.
    Excludes secret hashes, credentials, and tokens.
    """
    return UserProfileResponse(
        id=current_user.id,
        email=current_user.email,
        role=current_user.role,
        operatorId=current_user.email.split("@")[0] if current_user.email else current_user.id[:8],
    )
