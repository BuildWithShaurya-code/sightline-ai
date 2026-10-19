"""Request identity is established only after server-side token verification."""
from contextvars import ContextVar

owner_id: ContextVar[str | None] = ContextVar('sightline_owner', default=None)
