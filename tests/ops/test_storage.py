import io
import time

import pytest

from asme.ops import storage


def test_local_storage_put_open_delete(tmp_path):
    store = storage.LocalStorage(tmp_path / "uploads")
    key = storage.new_storage_key("org-1", "work_order", "photo.PNG")
    assert key.startswith("org-1/work_order/") and key.endswith(".png")
    size, digest = store.put(key, io.BytesIO(b"hello world"), "text/plain")
    assert size == 11 and len(digest) == 64
    assert store.exists(key)
    with store.open(key) as handle:
        assert handle.read() == b"hello world"
    store.delete(key)
    assert not store.exists(key)
    store.delete(key)  # idempotent


@pytest.mark.parametrize("bad", ["../etc/passwd", "/abs/path", "a/../../b", "", "space in key"])
def test_local_storage_rejects_unsafe_keys(tmp_path, bad):
    store = storage.LocalStorage(tmp_path / "uploads")
    with pytest.raises(ValueError):
        store.put(bad, io.BytesIO(b"x"), "text/plain")


def test_signed_download_tokens(app):
    token = storage.sign_download("abc-123", user_id=7)
    assert storage.verify_download(token) == "abc-123"
    assert storage.verify_download(token + "x") is None
    assert storage.verify_download("garbage") is None
    assert storage.verify_download(token, max_age=60) == "abc-123"
    time.sleep(1.1)  # itsdangerous timestamps have one-second resolution
    assert storage.verify_download(token, max_age=0) is None


def test_get_storage_uses_instance_uploads(app):
    store = storage.get_storage()
    assert isinstance(store, storage.LocalStorage)
    assert store.root.name == "uploads"
    assert storage.get_storage() is store
