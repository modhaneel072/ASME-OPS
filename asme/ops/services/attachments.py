"""Private attachments on work orders, projects, assets, parts and purchase
requests (``ops_attachments``).

Uploads are validated three ways before anything is written: the extension
must be on the allow-list, the declared content type must match the
extension's family, and for binary formats the magic bytes must match. Size is
checked from ``Content-Length`` before the body is parsed and again from the
bytes actually streamed to storage (over-size objects are deleted). Files live
behind the storage adapter, never under ``static/``; downloads are served with
a short-lived token bound to the attachment id.

Audit events are recorded against the parent entity with the attachment id,
entity type and entity id in the metadata.
"""

from __future__ import annotations

import posixpath
from pathlib import PurePosixPath

from asme.config import settings
from asme.extensions import db
from asme.ops import policy, storage
from asme.ops.models import Attachment
from asme.ops.services import audit_events, entities
from asme.ops.types import parse_uuid
from asme.ops.validation import ValidationErrors
from asme.services.errors import Forbidden, NotFound

ATTACHMENT_FIELDS = ("id", "entity_type", "entity_id", "original_name", "content_type", "size_bytes", "checksum_sha256", "is_image", "uploaded_by_user_id")
# One key covers every entity type, so the route gate and the service gate are
# the same check: a caller the route lets through is never refused here for a
# different reason. Read access to the parent is the other half and is decided
# per entity type by ``entities.resolve``.
UPLOAD_KEY = "work_order.attach"
MAX_NAME_LENGTH = 260
# Multipart framing (boundaries, part headers, other form fields) that may
# legitimately push Content-Length past the file limit.
MULTIPART_OVERHEAD = 64 * 1024

EXTENSION_FAMILIES = {
    "png": "image",
    "jpg": "image",
    "jpeg": "image",
    "gif": "image",
    "webp": "image",
    "pdf": "pdf",
    "txt": "text",
    "csv": "text",
    "md": "text",
    "stl": "model",
    "step": "model",
    "stp": "model",
    "gcode": "model",
    "3mf": "zip",
    "zip": "zip",
    "xlsx": "zip",
    "docx": "zip",
}
ALLOWED_EXTENSIONS = frozenset(EXTENSION_FAMILIES)

_ZIP_TYPES = ("application/zip", "application/x-zip-compressed")
_OOXML_PREFIX = "application/vnd.openxmlformats"
_3MF_TYPES = ("model/3mf", "application/vnd.ms-package.3dmanufacturing-3dmodel+xml")

MAGIC = {
    "png": (b"\x89PNG",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    "gif": (b"GIF8",),
    "pdf": (b"%PDF",),
    "zip": (b"PK\x03\x04",),
    "xlsx": (b"PK\x03\x04",),
    "docx": (b"PK\x03\x04",),
    "3mf": (b"PK\x03\x04",),
}
HEAD_BYTES = 16


def max_upload_bytes() -> int:
    return int(settings().upload_max_bytes)


def _limit_label(limit: int) -> str:
    if limit >= 1024 * 1024 and limit % (1024 * 1024) == 0:
        return f"{limit // (1024 * 1024)} MB"
    if limit >= 1024 and limit % 1024 == 0:
        return f"{limit // 1024} KB"
    return f"{limit} bytes"


def _too_large_message() -> str:
    return f"Files must be {_limit_label(max_upload_bytes())} or smaller."


def ensure_request_size(content_length: int | None) -> None:
    """Cheap pre-parse check on the request's declared size."""
    if content_length is not None and content_length > max_upload_bytes() + MULTIPART_OVERHEAD:
        raise ValidationErrors({"file": _too_large_message()})


# --------------------------------------------------------------------------- validation


def clean_filename(raw: str | None) -> str:
    name = (raw or "").replace("\\", "/")
    name = posixpath.basename(name).strip().strip(".")
    return name[:MAX_NAME_LENGTH]


def extension_of(name: str) -> str:
    return PurePosixPath(name).suffix.lower().lstrip(".")


def content_type_matches(extension: str, content_type: str) -> bool:
    family = EXTENSION_FAMILIES.get(extension)
    if not content_type or family is None:
        return False
    if family == "image":
        return content_type.startswith("image/")
    if family == "pdf":
        return content_type == "application/pdf"
    if family == "text":
        return content_type.startswith("text/")
    if family == "model":
        return content_type.startswith("model/") or content_type == "application/octet-stream"
    if family == "zip":
        if content_type in _ZIP_TYPES or content_type.startswith(_OOXML_PREFIX):
            return True
        return extension == "3mf" and content_type in _3MF_TYPES
    return False


def magic_matches(extension: str, head: bytes) -> bool:
    if extension == "webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    signatures = MAGIC.get(extension)
    if not signatures:
        return True
    return any(head.startswith(signature) for signature in signatures)


def validate_upload(upload) -> tuple[str, str, str]:
    """Return ``(original_name, extension, content_type)`` or raise ``ValidationErrors``."""
    if upload is None or not getattr(upload, "filename", None):
        raise ValidationErrors({"file": "Choose a file to upload."})
    original_name = clean_filename(upload.filename)
    if not original_name:
        raise ValidationErrors({"file": "The file needs a name."})
    extension = extension_of(original_name)
    if extension not in ALLOWED_EXTENSIONS:
        shown = f".{extension}" if extension else "without an extension"
        raise ValidationErrors({"file": f"Files {shown} are not allowed. Allowed: " + ", ".join(sorted(ALLOWED_EXTENSIONS)) + "."})
    content_type = (getattr(upload, "mimetype", None) or getattr(upload, "content_type", None) or "").split(";")[0].strip().lower()
    if not content_type_matches(extension, content_type):
        raise ValidationErrors({"file": f"The content type {content_type or '(missing)'} does not match a .{extension} file."})
    stream = upload.stream
    head = stream.read(HEAD_BYTES)
    stream.seek(0)
    if not head:
        raise ValidationErrors({"file": "The file is empty."})
    if not magic_matches(extension, head):
        raise ValidationErrors({"file": f"The file contents do not look like a .{extension} file."})
    return original_name, extension, content_type


# --------------------------------------------------------------------------- reads


def _load(ctx, attachment_id) -> tuple[Attachment, object]:
    parsed = parse_uuid(attachment_id)
    if parsed is None:
        raise NotFound()
    row = policy.get_or_404(ctx, Attachment, parsed)
    parent = entities.load(ctx, row.entity_type, row.entity_id)
    return row, parent


def list_for(ctx, entity_segment: str, entity_id) -> tuple[str, object, list[Attachment]]:
    entity_type, obj = entities.resolve(ctx, entity_segment, entity_id)
    rows = (
        Attachment.query.filter_by(organization_id=ctx.org.id, entity_type=entity_type, entity_id=obj.id)
        .order_by(Attachment.created_at.asc(), Attachment.id.asc())
        .all()
    )
    return entity_type, obj, rows


def get(ctx, attachment_id) -> Attachment:
    row, _parent = _load(ctx, attachment_id)
    return row


def for_download(attachment_id) -> Attachment | None:
    """Token-authorised lookup: the signed token, not a session, is the credential."""
    parsed = parse_uuid(attachment_id)
    if parsed is None:
        return None
    return db.session.get(Attachment, parsed)


# --------------------------------------------------------------------------- writes


def _audit(ctx, event_type: str, row: Attachment, parent, *, before=None, after=None, summary=None):
    # ``record`` reserves the ``entity_id`` keyword for the audit row itself, so the
    # parent's id is added to the metadata after the row is built.
    event = audit_events.record(
        ctx,
        event_type,
        parent,
        before=before,
        after=after,
        summary=summary,
        attachment_id=str(row.id),
        entity_type=row.entity_type,
        original_name=row.original_name,
    )
    event.metadata_json = {**(event.metadata_json or {}), "entity_id": str(row.entity_id)}
    return event


def upload(ctx, entity_segment: str, entity_id, file_storage) -> Attachment:
    entity_type, obj = entities.resolve(ctx, entity_segment, entity_id)
    policy.authorize(ctx, UPLOAD_KEY, obj)
    original_name, extension, content_type = validate_upload(file_storage)

    store = storage.get_storage()
    key = storage.new_storage_key(ctx.org.id, entity_type, original_name)
    size, digest = store.put(key, file_storage.stream, content_type)
    if size > max_upload_bytes():
        store.delete(key)
        raise ValidationErrors({"file": _too_large_message()})
    if size == 0:
        store.delete(key)
        raise ValidationErrors({"file": "The file is empty."})

    row = Attachment(
        organization_id=ctx.org.id,
        entity_type=entity_type,
        entity_id=obj.id,
        storage_key=key,
        original_name=original_name,
        content_type=content_type,
        size_bytes=size,
        checksum_sha256=digest,
        uploaded_by_user_id=ctx.user.id,
        is_image=EXTENSION_FAMILIES[extension] == "image",
        created_by_user_id=ctx.user.id,
        updated_by_user_id=ctx.user.id,
    )
    db.session.add(row)
    db.session.flush()
    _audit(
        ctx,
        "attachment.uploaded",
        row,
        obj,
        after=audit_events.snapshot(row, ATTACHMENT_FIELDS),
        summary=f"Uploaded {original_name} to {entities.label(entity_type, obj)}",
    )
    db.session.commit()
    return row


def delete(ctx, attachment_id) -> Attachment:
    row, parent = _load(ctx, attachment_id)
    if row.uploaded_by_user_id != ctx.user.id and not entities.can_manage(ctx, row.entity_type, parent):
        raise Forbidden("Only the uploader or someone who manages this item can remove this file.", permission=entities.MANAGE_KEYS[row.entity_type])
    before = audit_events.snapshot(row, ATTACHMENT_FIELDS)
    storage.get_storage().delete(row.storage_key)
    db.session.delete(row)
    _audit(
        ctx,
        "attachment.deleted",
        row,
        parent,
        before=before,
        summary=f"Removed {row.original_name} from {entities.label(row.entity_type, parent)}",
    )
    db.session.commit()
    return row
