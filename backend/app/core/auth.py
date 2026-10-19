"""Fail-closed verification of Supabase user access tokens via project public JWKS."""
from dataclasses import dataclass
import math
import threading
import time
from typing import Optional
from urllib.parse import urlsplit
from uuid import UUID

import httpx
import jwt
from fastapi import Depends, Header

from ..config import Settings, get_settings
from .errors import AuthenticationError, AuthorizationError, ServiceUnavailableError

@dataclass
class AuthenticatedUser:
    id: str
    email: Optional[str] = None
    role: str = 'authenticated'

# Only configured project URLs are cache keys. No token, password or private key is cached.
_jwks_cache = {}
_cache_lock = threading.Lock()
_CACHE_SECONDS = 600
_REFRESH_SECONDS = 30


def project_issuer(settings):
    url = (settings.supabase_url or '').rstrip('/')
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise AuthenticationError('Account token verification is not configured.')
    return url + '/auth/v1'


async def _fetch_jwks(issuer):
    try:
        async with httpx.AsyncClient(timeout=5, follow_redirects=False, trust_env=False) as client:
            response = await client.get(issuer + '/.well-known/jwks.json')
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or not isinstance(data.get('keys'), list) or len(data['keys']) > 20:
            raise ValueError('Invalid signing-key response')
        return data
    except (httpx.HTTPError, ValueError):
        raise ServiceUnavailableError('Account verification is temporarily unavailable. Please retry.') from None


async def _signing_key(issuer, kid, algorithm):
    now = time.monotonic()
    with _cache_lock:
        cached = _jwks_cache.get(issuer)
        needs_fetch = not cached or now >= cached[0] or (kid not in cached[2] and now >= cached[1])
    if needs_fetch:
        data = await _fetch_jwks(issuer)
        keys = {}
        try:
            for value in data['keys']:
                if not isinstance(value, dict) or value.get('alg') not in ('ES256', 'RS256') or value.get('use', 'sig') != 'sig':
                    continue
                if any(name in value for name in ('d', 'p', 'q', 'k')):
                    continue
                if not isinstance(value.get('kid'), str) or value.get('key_ops', ['verify']) != ['verify']:
                    continue
                parsed = jwt.PyJWK.from_dict(value)
                keys[value['kid']] = parsed
        except (jwt.PyJWTError, ValueError, TypeError):
            raise ServiceUnavailableError('Account signing keys are unavailable.') from None
        now = time.monotonic()
        cached = (now + _CACHE_SECONDS, now + _REFRESH_SECONDS, keys)
        with _cache_lock:
            if len(_jwks_cache) >= 8 and issuer not in _jwks_cache:
                _jwks_cache.clear()
            _jwks_cache[issuer] = cached
    key = cached[2].get(kid)
    if not key or key.algorithm_name != algorithm:
        raise AuthenticationError('Unknown account signing key. Please refresh your session.')
    return key.key


async def get_current_user(authorization: Optional[str] = Header(None, alias='Authorization'), settings: Settings = Depends(get_settings)) -> AuthenticatedUser:
    if not authorization:
        raise AuthenticationError('Authorization header is required.')
    parts = authorization.strip().split()
    if len(parts) != 2 or parts[0].lower() != 'bearer' or len(parts[1]) > 16384:
        raise AuthenticationError('Invalid bearer access token.')
    token = parts[1]
    if token in (settings.supabase_secret_key, settings.supabase_publishable_key):
        raise AuthorizationError('An API key cannot be used as an operator credential.')
    issuer = project_issuer(settings)
    try:
        header = jwt.get_unverified_header(token)  # Only routing metadata; never establishes identity.
        algorithm, kid = header.get('alg'), header.get('kid')
        if algorithm not in ('ES256', 'RS256') or not isinstance(kid, str) or not kid or len(kid) > 128 or header.get('crit'):
            raise AuthenticationError('Unsupported account access token.')
        key = await _signing_key(issuer, kid, algorithm)
        payload = jwt.decode(token, key, algorithms=[algorithm], audience='authenticated', issuer=issuer,
            options={'require':['exp','iat','iss','sub','aud','role'], 'strict_aud':True})
        if any(isinstance(payload[k], bool) or not isinstance(payload[k], (int,float)) or not math.isfinite(payload[k]) for k in ('exp','iat')) or payload['exp'] <= payload['iat']:
            raise AuthenticationError('Invalid account token lifetime.')
        user_id = str(UUID(payload['sub']))
    except jwt.ExpiredSignatureError:
        raise AuthenticationError('Access token has expired. Please refresh your session.') from None
    except (jwt.PyJWTError, ValueError, TypeError, KeyError, AttributeError):
        raise AuthenticationError('Invalid account access token.') from None
    if payload['role'] != 'authenticated' or payload.get('is_anonymous') is True:
        raise AuthorizationError('A signed-in owner account is required.')
    email = payload.get('email')
    from .identity import owner_id
    owner_id.set(user_id)
    return AuthenticatedUser(id=user_id, email=email if isinstance(email,str) else None)
