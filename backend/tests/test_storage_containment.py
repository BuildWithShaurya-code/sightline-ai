from pathlib import Path

import pytest

from app.services.storage import LocalMediaStorage


def test_sibling_prefix_read_and_delete_cannot_escape(tmp_path: Path):
    storage = LocalMediaStorage(tmp_path / 'media')
    sibling = tmp_path / 'media-private'
    sibling.mkdir()
    private_file = sibling / 'private.mp4'
    private_file.write_bytes(b'private')
    with pytest.raises(ValueError):
        storage.get_media_path('../media-private/private.mp4')
    assert storage.delete_media('../media-private/private.mp4') is False
    assert private_file.read_bytes() == b'private'


def test_save_validates_before_creating_outside_directory(tmp_path: Path):
    storage = LocalMediaStorage(tmp_path / 'media')
    with pytest.raises(ValueError):
        storage.save_media(b'private', 'video.mp4', '../media-private/new')
    assert not (tmp_path / 'media-private').exists()


def test_symlink_cannot_escape_media_root(tmp_path: Path):
    storage = LocalMediaStorage(tmp_path / 'media')
    outside = tmp_path / 'outside'
    outside.mkdir()
    (storage.base_dir / 'alias').symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        storage.save_media(b'private', 'video.mp4', 'alias')
    assert list(outside.iterdir()) == []


def test_regular_media_round_trip(tmp_path: Path):
    storage = LocalMediaStorage(tmp_path / 'media')
    key = storage.save_media(b'video-bytes', 'recording.mp4')
    assert storage.get_media_path(key).read_bytes() == b'video-bytes'
    assert storage.delete_media(key)
