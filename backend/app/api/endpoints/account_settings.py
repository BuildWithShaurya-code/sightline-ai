"""Verified account username management; no admin key or password storage."""
from typing import Optional
from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, Field, SecretStr
from ...config import Settings, get_settings
from ...core.errors import AuthenticationError
from ...services import account_aliases as accounts

router = APIRouter(prefix='/auth', tags=['Account settings'])


class UsernameRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)


class UsernameLoginRequest(UsernameRequest):
    password: SecretStr


def private_response(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Pragma'] = 'no-cache'


@router.get('/username')
async def own_username(response: Response, authorization: Optional[str] = Header(default=None), settings: Settings = Depends(get_settings)):
    private_response(response)
    account = await accounts.verified_account(settings, authorization)
    return {'username': accounts.alias_store(settings).own(account)}


@router.put('/username')
async def save_username(payload: UsernameRequest, response: Response, authorization: Optional[str] = Header(default=None), settings: Settings = Depends(get_settings)):
    private_response(response)
    account = await accounts.verified_account(settings, authorization)
    return {'username': accounts.alias_store(settings).save(account, payload.username)}


@router.post('/username-login')
async def username_login(payload: UsernameLoginRequest, request: Request, response: Response, settings: Settings = Depends(get_settings)):
    private_response(response)
    name = accounts.username_value(payload.username)
    accounts.limit_attempts(request.client.host if request.client else 'unknown', name)
    password = payload.password.get_secret_value()
    if not password or len(password) > 4096:
        raise AuthenticationError('Username or password is incorrect, or your session has ended.')
    stored = accounts.alias_store(settings).lookup(name)
    if not stored:
        raise AuthenticationError('Username or password is incorrect, or your session has ended.')
    return await accounts.password_session(settings,stored,password)


@router.post('/register',status_code=201)
async def register_username(payload: UsernameLoginRequest, request: Request, response: Response, settings: Settings=Depends(get_settings)):
    """Create a unique private account without collecting or sending email."""
    import uuid
    from starlette.concurrency import run_in_threadpool
    from ...core.errors import ConflictError,ServiceUnavailableError
    private_response(response)
    name=accounts.username_value(payload.username)
    accounts.limit_attempts(request.client.host if request.client else 'unknown','signup:'+name)
    password=accounts.registration_password(payload.password.get_secret_value())
    if settings.storage_backend!='supabase':
        raise ServiceUnavailableError('Private username registration requires configured account persistence.')
    store=accounts.alias_store(settings)
    if await run_in_threadpool(store.lookup,name):
        raise ConflictError('This username is already taken. Choose another, or sign in.')
    # Supabase's password provider needs an internal identifier. It is random,
    # non-deliverable and never presented as the user's contact email.
    try:
        user=await accounts.admin_request(settings,'POST','users',{
            'email':'u-'+uuid.uuid4().hex+'@accounts.sightline.invalid',
            'password':password,'email_confirm':True,
            'user_metadata':{'username':name},'app_metadata':{'account_kind':'username_only'},
        })
    except ServiceUnavailableError:
        # The provider's unique alias trigger decides concurrent registrations.
        if await run_in_threadpool(store.lookup,name):
            raise ConflictError('This username is already taken. Choose another, or sign in.') from None
        raise
    stored=await run_in_threadpool(store.lookup,name)
    if not stored or stored['user_id']!=user.get('id'):
        raise ServiceUnavailableError('The account could not be verified. Try signing in before creating another.')
    return await accounts.password_session(settings,stored,password)
