"""Account API without inference imports or model startup.

Vercel routes /api/v1/auth/* here so username login never waits for PyTorch.
Supabase remains the sole password/token authority; this service stores no password.
"""
import logging
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from .config import get_settings
from .core.identity import owner_id
from .core.errors import SightLineError, sightline_error_handler, validation_error_handler, starlette_http_exception_handler, unhandled_exception_handler
from .api.endpoints.auth import router as auth_router
from .api.endpoints.account_settings import router as account_router

app = FastAPI(title='SightLine account API', docs_url=None, redoc_url=None, openapi_url=None)
logging.getLogger('httpx').setLevel(logging.WARNING)
app.add_exception_handler(SightLineError,sightline_error_handler)
app.add_exception_handler(RequestValidationError,validation_error_handler)
app.add_exception_handler(HTTPException,starlette_http_exception_handler)
app.add_exception_handler(Exception,unhandled_exception_handler)

@app.middleware('http')
async def private_account_response(request: Request, call_next):
    token=owner_id.set(None)
    try:
        response=await call_next(request)
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        return response
    finally:
        owner_id.reset(token)

app.include_router(auth_router,prefix=get_settings().api_prefix)
app.include_router(account_router,prefix=get_settings().api_prefix)
