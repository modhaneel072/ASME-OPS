"""Private file storage behind a small adapter interface.

* ``LocalStorage`` keeps files under ``instance/uploads/<organization>/...``
  (never inside ``static/``), so nothing is web-reachable without a signed URL.
* Downloads are authorised per request and served through a short-lived token
  produced by ``sign_download``; the token is bound to the attachment id.
* An S3 adapter is a documented follow-up (``ASME_STORAGE_BACKEND=s3``); until
  it exists, selecting it fails loudly at boot instead of silently writing to disk.
"""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from pathlib import Path
from typing import BinaryIO, Protocol

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from asme.config import settings

SAFE_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/\-]{0,380}$")


class StorageAdapter(Protocol):
    def put(self, key: str, stream: BinaryIO, content_type: str) -> tuple[int, str]: ...

    def open(self, key: str) -> BinaryIO: ...

    def delete(self, key: str) -> None: ...

    def exists(self, key: str) -> bool: ...


def _check_key(key: str) -> str:
    if not key or not SAFE_KEY_RE.match(key) or ".." in key.split("/"):
        raise ValueError(f"unsafe storage key {key!r}")
    return key


class LocalStorage:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / _check_key(key)).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError("storage key escapes the upload root")
        return path

    def put(self, key: str, stream: BinaryIO, content_type: str) -> tuple[int, str]:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        with open(path, "wb") as handle:
            while True:
                chunk = stream.read(1024 * 256)
                if not chunk:
                    break
                handle.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        return size, digest.hexdigest()

    def open(self, key: str) -> BinaryIO:
        return open(self._path(key), "rb")

    def delete(self, key: str) -> None:
        path = self._path(key)
        try:
            os.remove(path)
        except FileNotFoundError:
            pass

    def exists(self, key: str) -> bool:
        return self._path(key).exists()


def build_storage(cfg=None, instance_path: str | None = None):
    cfg = cfg or settings()
    backend = (cfg.storage_backend or "local").lower()
    if backend == "local":
        root = Path(cfg.upload_root) if cfg.upload_root else Path(instance_path or current_app.instance_path) / "uploads"
        return LocalStorage(root)
    if backend == "s3":
        raise RuntimeError(
            "ASME_STORAGE_BACKEND=s3 is not implemented yet. Use 'local' (default) or add an S3 adapter in asme/ops/storage.py; see docs/deployment.md."
        )
    raise RuntimeError(f"unknown ASME_STORAGE_BACKEND {backend!r}")


def get_storage():
    store = current_app.extensions.get("asme_ops_storage")
    if store is None:
        store = build_storage()
        current_app.extensions["asme_ops_storage"] = store
    return store


def new_storage_key(org_id, entity_type: str, original_name: str) -> str:
    ext = Path(original_name or "").suffix.lower()
    ext = ext if re.match(r"^\.[a-z0-9]{1,8}$", ext) else ""
    return f"{org_id}/{entity_type}/{uuid.uuid4().hex}{ext}"


# --------------------------------------------------------------------------- signed downloads


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="asme-ops-download")


def sign_download(attachment_id, user_id: int | None = None) -> str:
    return _serializer().dumps({"a": str(attachment_id), "u": user_id})


def verify_download(token: str, max_age: int | None = None) -> str | None:
    if max_age is None:
        max_age = settings().ops_download_ttl_seconds
    try:
        data = _serializer().loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    return str(data.get("a")) if isinstance(data, dict) else None
