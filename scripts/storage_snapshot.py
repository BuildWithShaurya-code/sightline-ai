#!/usr/bin/env python3
"""Offline private storage backup/restore. Never includes environment files or weights."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import tempfile

DATABASES = ('data/sightline.db', 'data/account_aliases.sqlite3')


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def private_copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with source.open('rb') as incoming, target.open('xb') as outgoing:
        os.chmod(target, 0o600)
        shutil.copyfileobj(incoming, outgoing)


def valid_name(name):
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or '\\' in name or any(part.startswith('.') for part in p.parts):
        return False
    return name in DATABASES or (len(p.parts) >= 3 and p.parts[:2] in [('media','videos'), ('media','keyframes')] and p.suffix.lower() in ('.mp4','.mov','.avi','.mkv','.webm','.jpg','.jpeg','.png'))


def plain_file(root, name):
    path = root / name
    current = path
    while current != root:
        if current.is_symlink():
            raise ValueError('Symbolic links are not supported in private snapshots.')
        current = current.parent
    if not path.is_file():
        raise ValueError('Snapshot file is missing or not a regular file.')
    return path


def check_sqlite(path):
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Database integrity check failed.')
        if db.execute('PRAGMA foreign_key_check').fetchone() is not None:
            raise ValueError('Database foreign key check failed.')


@contextmanager
def worker_lock(root):
    lock = root / 'data' / '.analysis-worker.lock'
    if lock.is_symlink():
        raise ValueError('Unsafe storage lock path.')
    with os.fdopen(os.open(lock, os.O_CREAT | os.O_RDWR, 0o600), 'r+') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Stop the backend before taking a storage snapshot.') from None
        yield


def build_atomically(output, action):
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError('Output must be a new directory; existing storage is never overwritten.')
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.sightline-snapshot-', dir=output.parent))
    try:
        action(stage)
        if output.exists() or output.is_symlink():
            raise ValueError('Output appeared while preparing snapshot; refusing overwrite.')
        stage.rename(output)
    except Exception:
        shutil.rmtree(stage)
        raise
    return output


def backup(storage_root, output):
    root = Path(storage_root).absolute()
    if root.is_symlink() or not (root/'data/sightline.db').is_file():
        raise ValueError('Select the stopped backend storage directory containing data/sightline.db.')
    if Path(output).absolute().is_relative_to(root):
        raise ValueError('Keep backups outside the active storage directory.')
    with worker_lock(root):
        def copy(stage):
            records = []
            for name in DATABASES:
                if not (root / name).exists():
                    continue
                source = plain_file(root, name)
                target = stage / name
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with sqlite3.connect(source.as_uri()+'?mode=ro', uri=True) as incoming, sqlite3.connect(target) as outgoing:
                    os.chmod(target, 0o600)
                    incoming.backup(outgoing)
                check_sqlite(target)
                records.append({'path':name, 'sha256':digest(target), 'bytes':target.stat().st_size})
            for folder in ('media/videos','media/keyframes'):
                base = root / folder
                if base.is_symlink():
                    raise ValueError('Symbolic media directories are not supported.')
                if not base.exists():
                    continue
                for source in sorted(base.rglob('*')):
                    if source.is_symlink():
                        raise ValueError('Symbolic media files are not supported.')
                    if not source.is_file():
                        continue
                    name = source.relative_to(root).as_posix()
                    if not valid_name(name):
                        raise ValueError('Unexpected file in private media directory; inspect it before backup.')
                    target = stage / name
                    private_copy(source, target)
                    records.append({'path':name, 'sha256':digest(target), 'bytes':target.stat().st_size})
            manifest = stage / 'manifest.json'
            manifest.write_text(json.dumps({'version':1, 'created_at':datetime.now(timezone.utc).isoformat(), 'files':records}, indent=2))
            manifest.chmod(0o600)
        return build_atomically(output, copy)


def restore(snapshot, output):
    root = Path(snapshot).absolute()
    if root.is_symlink():
        raise ValueError('Snapshot must be a regular directory.')
    manifest = json.loads(plain_file(root, 'manifest.json').read_text())
    if manifest.get('version') != 1 or not isinstance(manifest.get('files'), list):
        raise ValueError('Unsupported snapshot format.')
    seen = set()
    for record in manifest['files']:
        name = record['path']
        if not valid_name(name) or name in seen:
            raise ValueError('Invalid or duplicate snapshot path.')
        seen.add(name)
        source = plain_file(root, name)
        if source.stat().st_size != record['bytes'] or digest(source) != record['sha256']:
            raise ValueError('Snapshot checksum mismatch; restore was not started.')
        if name in DATABASES:
            check_sqlite(source)
    if 'data/sightline.db' not in seen:
        raise ValueError('Snapshot does not contain the application database.')
    def copy(stage):
        for record in manifest['files']:
            private_copy(root / record['path'], stage / record['path'])
    return build_atomically(output, copy)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('backup', help='Stop the server first. Creates a private snapshot.')
    create.add_argument('--storage-root', required=True)
    create.add_argument('--server-stopped', required=True, action='store_true')
    create.add_argument('--output', required=True)
    recover = commands.add_parser('restore', help='Verify and restore into a NEW storage directory.')
    recover.add_argument('--snapshot', required=True)
    recover.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'backup':
            backup(args.storage_root, args.output)
        else:
            restore(args.snapshot, args.output)
    except (ValueError, OSError, sqlite3.Error, KeyError, TypeError) as error:
        parser.exit(1, f'Snapshot operation failed: {error}\n')
    print('Private storage snapshot operation completed and verified.')


if __name__ == '__main__':
    main()
