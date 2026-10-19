"""Private Supabase objects; scratch files are caches, never the durable store."""
from functools import lru_cache
import hashlib
import os
from pathlib import Path
from urllib.parse import urlsplit
import uuid

import httpx
from supabase import create_client
from supabase.lib.client_options import SyncClientOptions

from ..core.errors import ServiceUnavailableError, PayloadTooLargeError

MODEL_SHA256 = '0b17d4a5f108447e277dce5688ecd1d3924a43792f2d751c018858d9539dc0f8'


@lru_cache(maxsize=1)
def _client(url, key):
    return create_client(url, key, options=SyncClientOptions(auto_refresh_token=False, persist_session=False, storage_client_timeout=60))


class CloudStorage:
    def __init__(self, settings):
        self.settings = settings
        self.client = _client(settings.supabase_url, settings.supabase_secret_key)

    def bucket(self, name):
        if name not in ('source-videos', 'evidence-frames', self.settings.cloud_model_bucket):
            raise ValueError('Unknown private storage bucket')
        return self.client.storage.from_(name)

    def upload(self, bucket, key, data, content_type):
        return self.bucket(bucket).upload(key, data, {'content-type': content_type, 'upsert': 'false'})

    def signed_upload(self, key):
        result = self.bucket('source-videos').create_signed_upload_url(key)
        return result['signed_url']

    def signed_urls(self, bucket, keys):
        if not keys:
            return {}
        items = self.bucket(bucket).create_signed_urls(keys, 300)
        if any(item.get('error') for item in items):
            raise ServiceUnavailableError('Private evidence is temporarily unavailable.')
        return {item['path']: item['signedURL'] for item in items}

    def download(self, bucket, key, target, maximum):
        url = self.signed_urls(bucket, [key])[key]
        expected = urlsplit(self.settings.supabase_url)
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.hostname != expected.hostname:
            raise ServiceUnavailableError('Private storage returned an unexpected address.')
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + '.' + uuid.uuid4().hex + '.partial')
        total = 0
        try:
            with httpx.Client(timeout=60, follow_redirects=False, trust_env=False) as client:
                with client.stream('GET', url) as response:
                    response.raise_for_status()
                    if int(response.headers.get('content-length', 0)) > maximum:
                        raise PayloadTooLargeError('Stored media exceeds the permitted size.', max_bytes=maximum)
                    with partial.open('xb') as output:
                        os.chmod(partial, 0o600)
                        for chunk in response.iter_bytes(1024*1024):
                            total += len(chunk)
                            if total > maximum:
                                raise PayloadTooLargeError('Stored media exceeds the permitted size.', max_bytes=maximum)
                            output.write(chunk)
            partial.replace(target)
            return total
        except httpx.HTTPError:
            raise ServiceUnavailableError('Private media could not be downloaded. Please retry.') from None
        finally:
            partial.unlink(missing_ok=True)

    def ready(self):
        # Reading bucket configuration verifies the real remote store and server permission.
        try:
            for name in ('source-videos', 'evidence-frames', self.settings.cloud_model_bucket):
                bucket = self.client.storage.get_bucket(name)
                if bucket.public:
                    return False
            return True
        except Exception:
            return False


def hydrate_model(settings):
    target = settings.model_path
    if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == MODEL_SHA256:
        return
    CloudStorage(settings).download(settings.cloud_model_bucket, settings.cloud_model_key, target, 100*1024*1024)
    if hashlib.sha256(target.read_bytes()).hexdigest() != MODEL_SHA256:
        target.unlink(missing_ok=True)
        raise RuntimeError('The private model checkpoint failed its integrity check.')
