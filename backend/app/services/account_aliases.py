"""Private username aliases. Passwords and provider sessions are never persisted here."""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
import uuid
from urllib.parse import urlsplit

import httpx
from ..core.errors import AuthenticationError, ConflictError, ServiceUnavailableError, SightLineError, ValidationError

USERNAME = re.compile(r'^[a-z0-9][a-z0-9_. -]{2,31}$')
_attempts = {}
_attempt_lock = threading.Lock()


def username_value(value):
    value = value.strip().lower()
    if not USERNAME.fullmatch(value):
        raise ValidationError('Use 3–32 letters or numbers. Spaces, dots, underscores and hyphens are also allowed.')
    return value


def limit_attempts(ip, username):
    now = time.monotonic()
    keys = [('ip', ip), ('name', hashlib.sha256(username.encode()).hexdigest())]
    with _attempt_lock:
        for key in list(_attempts):
            _attempts[key] = [t for t in _attempts[key] if now-t < 60]
            if not _attempts[key]:
                del _attempts[key]
        if len(_attempts) > 10000:
            raise SightLineError('RATE_LIMITED', 'Too many sign-in attempts. Please wait a minute.', 429)
        for key, maximum in zip(keys, (30, 10)):
            if len(_attempts.get(key, [])) >= maximum:
                raise SightLineError('RATE_LIMITED', 'Too many sign-in attempts. Please wait a minute.', 429)
        for key in keys:
            _attempts.setdefault(key, []).append(now)


def provider_config(settings):
    url = (settings.supabase_url or '').rstrip('/')
    key = settings.supabase_publishable_key
    parsed = urlsplit(url)
    if not key or parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path:
        raise ServiceUnavailableError('Account sign-in is not connected on this server.')
    return url, key


async def provider_request(settings, method, path, *, bearer=None, payload=None):
    url, key = provider_config(settings)
    headers = {'apikey': key}
    if bearer:
        headers['Authorization'] = 'Bearer ' + bearer
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False, trust_env=False) as client:
            response = await client.request(method, url + '/auth/v1/' + path, headers=headers, json=payload)
        if response.status_code == 429:
            raise SightLineError('RATE_LIMITED', 'Too many sign-in attempts. Please wait a minute.', 429)
        if response.status_code in (400, 401, 403, 422):
            if response.json().get('error_code') == 'email_not_confirmed':
                raise SightLineError('EMAIL_NOT_CONFIRMED','The account is waiting for activation.',401)
            raise AuthenticationError('Username or password is incorrect. New here? Choose Create account first.')
        if not response.is_success:
            raise ServiceUnavailableError('Account service is temporarily unavailable. Please retry.')
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError('Unexpected account response')
        return data
    except (httpx.HTTPError, ValueError):
        raise ServiceUnavailableError('Could not reach account sign-in. Please retry.') from None


async def verified_account(settings, authorization):
    if not authorization or not authorization.startswith('Bearer '):
        raise AuthenticationError()
    token = authorization[7:]
    if not token or len(token) > 16384:
        raise AuthenticationError()
    data = await provider_request(settings, 'GET', 'user', bearer=token)
    try:
        uuid.UUID(data.get('id', ''))
    except (ValueError, TypeError, AttributeError):
        raise AuthenticationError() from None
    if not isinstance(data.get('email'), str) or not data['email'] or data.get('is_anonymous'):
        raise AuthenticationError()
    from ..core.identity import owner_id
    owner_id.set(data['id'])
    return {'id': data['id'], 'email': data['email']}


class AliasStore:
    def __init__(self, path: Path, project: str):
        self.path, self.project = path, project

    @contextmanager
    def connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('CREATE TABLE IF NOT EXISTS aliases(project TEXT NOT NULL,user_id TEXT NOT NULL,username TEXT NOT NULL,email TEXT NOT NULL,PRIMARY KEY(project,user_id),UNIQUE(project,username))')
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def own(self, account):
        with self.connection() as conn:
            row = conn.execute('SELECT username FROM aliases WHERE project=? AND user_id=?', (self.project, account['id'])).fetchone()
            conn.execute('UPDATE aliases SET email=? WHERE project=? AND user_id=?', (account['email'], self.project, account['id']))
            return row['username'] if row else None

    def save(self, account, username):
        username = username_value(username)
        try:
            with self.connection() as conn:
                conn.execute('INSERT INTO aliases(project,user_id,username,email) VALUES(?,?,?,?) ON CONFLICT(project,user_id) DO UPDATE SET username=excluded.username,email=excluded.email', (self.project, account['id'], username, account['email']))
        except sqlite3.IntegrityError:
            raise ConflictError('This username is unavailable. Please choose another.') from None
        return username

    def lookup(self, username):
        with self.connection() as conn:
            row = conn.execute('SELECT user_id,email FROM aliases WHERE project=? AND username=?', (self.project, username)).fetchone()
            return dict(row) if row else None


def alias_store(settings):
    project, _ = provider_config(settings)
    if settings.storage_backend == 'supabase':
        return CloudAliasStore(project)
    return AliasStore(settings.media_dir.parent / 'data' / 'account_aliases.sqlite3', project)


class CloudAliasStore(AliasStore):
    def __init__(self, project):
        self.project = project

    @contextmanager
    def connection(self):
        from ..db.database import DatabaseManager
        conn = DatabaseManager.get_instance().get_connection()
        conn.execute('BEGIN')
        try:
            yield conn
            conn.execute('COMMIT')
        except Exception:
            conn.execute('ROLLBACK')
            raise

    def lookup(self, username):
        with self.connection() as conn:
            row = conn.execute('SELECT * FROM sightline.alias_lookup(?,?)', (self.project, username)).fetchone()
            return dict(row) if row else None


async def admin_request(settings, method, path, payload):
    """Narrow provider administration for username accounts; never a browser key."""
    url, _ = provider_config(settings)
    secret = settings.supabase_secret_key
    if not secret:
        raise ServiceUnavailableError('Account creation is not connected on this server.')
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=False, trust_env=False) as client:
            response = await client.request(method, url+'/auth/v1/admin/'+path,
                headers={'apikey':secret,'Authorization':'Bearer '+secret},json=payload)
        if response.status_code == 429:
            raise SightLineError('RATE_LIMITED','Too many account requests. Please wait a minute.',429)
        if not response.is_success:
            # Never expose provider diagnostics, email addresses, keys or passwords.
            raise ServiceUnavailableError('The account could not be saved. Try signing in, or choose a different username.')
        data=response.json()
        if not isinstance(data,dict):raise ValueError('Invalid account response')
        return data
    except (httpx.HTTPError,ValueError):
        raise ServiceUnavailableError('Could not reach account creation. Please retry.') from None


def registration_password(value):
    if len(value)<8 or len(value.encode('utf-8'))>72:
        raise ValidationError('Use at least 8 characters. The password must fit within 72 bytes.')
    return value


def verify_pending_password(settings, account_id, password):
    """Compatibility for accounts left pending by the retired email signup flow.

    This isolated privileged read compares the provider's existing password hash.
    It never trusts a client owner ID, exports a hash, or modifies a password.
    Ordinary application queries continue through their owner-scoped API role.
    """
    if settings.storage_backend != 'supabase' or len(password.encode('utf-8'))>72:
        return False
    import bcrypt
    from ..db.database import DatabaseManager
    db=DatabaseManager.get_instance()
    with db.pool.connection() as conn:
        row=conn.execute('SELECT encrypted_password,email_confirmed_at FROM auth.users WHERE id=%s',(account_id,)).fetchone()
    if not row or row[1] is not None or not row[0]:return False
    try:return bcrypt.checkpw(password.encode('utf-8'),row[0].encode('utf-8'))
    except (ValueError,TypeError):return False


async def password_session(settings, stored, password):
    payload={'email':stored['email'],'password':password}
    try:
        session=await provider_request(settings,'POST','token?grant_type=password',payload=payload)
    except SightLineError as exc:
        if exc.error_code != 'EMAIL_NOT_CONFIRMED':raise
        from starlette.concurrency import run_in_threadpool
        if not await run_in_threadpool(verify_pending_password,settings,stored['user_id'],password):
            raise AuthenticationError('Username or password is incorrect.') from None
        # Owner explicitly chose username/password-only accounts. Activate an old
        # pending account only after verifying its existing password and alias.
        # Do not label the old, unverified real email as verified. Replace it
        # with an internal identifier; the verified UUID, username and data stay.
        internal_email='u-'+uuid.uuid4().hex+'@accounts.sightline.invalid'
        activated=await admin_request(settings,'PUT','users/'+stored['user_id'],{'email':internal_email,'email_confirm':True})
        if activated.get('id')!=stored['user_id'] or activated.get('email')!=internal_email:
            raise AuthenticationError('Account activation could not be verified. Please retry using your username.')
        payload['email']=internal_email
        session=await provider_request(settings,'POST','token?grant_type=password',payload=payload)
    if session.get('user',{}).get('id') != stored['user_id'] or not isinstance(session.get('access_token'),str) or not isinstance(session.get('refresh_token'),str):
        raise AuthenticationError('Could not verify account sign-in. Please retry.')
    return {'access_token':session['access_token'],'refresh_token':session['refresh_token']}
