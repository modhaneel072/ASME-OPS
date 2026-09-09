"""Attachments: validated uploads, signed downloads, delete rules, visibility and tenancy."""

from __future__ import annotations

import dataclasses
import hashlib
import io
import struct
import time
import uuid
import zlib

import pytest

from asme.extensions import db as _db
from asme.ops import storage
from asme.ops.models import Asset, Attachment, AuditEvent, OpsProject, Organization, ProjectMember, WorkOrder
from asme.ops.services import attachments as attachments_service
from asme.ops.validation import ValidationErrors
from tests.ops.conftest import make_user

UPLOAD_HEADERS = {"X-Requested-With": "ASME-Ops"}
_counter = {"n": 0}


def _next_number() -> int:
    _counter["n"] += 1
    return _counter["n"]


def make_png(width: int = 1, height: int = 1, padding: int = 0) -> bytes:
    """A real, decodable RGB PNG; ``padding`` bytes go into a tEXt chunk to control size."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\xff\x00\x00" * width for _ in range(height))
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw))
    if padding:
        png += chunk(b"tEXt", b"pad\x00" + b"x" * padding)
    return png + chunk(b"IEND", b"")


def _upload(client, url, content: bytes, filename: str, content_type: str, headers=UPLOAD_HEADERS):
    return client.post(url, data={"file": (io.BytesIO(content), filename, content_type)}, headers=headers, content_type="multipart/form-data")


def _project(org, name="Rover", visibility="chapter", **kw):
    row = OpsProject(organization_id=org.id, name=name, code=name[:3].upper() + str(_next_number()), visibility=visibility, **kw)
    _db.session.add(row)
    _db.session.commit()
    return row


def _work_order(org, creator, **kw):
    row = WorkOrder(organization_id=org.id, number=_next_number(), title=kw.pop("title", "Replace wheel hub"), created_by_user_id=creator.id, **kw)
    _db.session.add(row)
    _db.session.commit()
    return row


def _asset(org, name="3D Printer 01", **kw):
    row = Asset(organization_id=org.id, name=name, **kw)
    _db.session.add(row)
    _db.session.commit()
    return row


def _stored_files(store) -> list:
    return sorted(p for p in store.root.rglob("*") if p.is_file())


@pytest.fixture(autouse=True)
def store(app, tmp_path):
    """Keep uploaded bytes inside the test's temp dir instead of instance/uploads."""
    local = storage.LocalStorage(tmp_path / "uploads")
    app.extensions["asme_ops_storage"] = local
    yield local
    app.extensions.pop("asme_ops_storage", None)


@pytest.fixture
def patch_settings(app):
    original = app.config["SETTINGS"]

    def _patch(**overrides):
        app.config["SETTINGS"] = dataclasses.replace(original, **overrides)
        return app.config["SETTINGS"]

    yield _patch
    app.config["SETTINGS"] = original


# --------------------------------------------------------------------------- happy path


def test_upload_png_to_work_order_then_list_and_get(client, org, users, api_login, store):
    wo = _work_order(org, users["lead"])
    png = make_png(4, 4)
    api_login(users["member"])

    response = _upload(client, f"/api/v1/work-orders/{wo.id}/attachments", png, "hub photo.PNG", "image/png")
    assert response.status_code == 201, response.get_json()
    body = response.get_json()["payload"]["attachment"]
    assert body["entity_type"] == "work_order" and body["entity_id"] == str(wo.id)
    assert body["original_name"] == "hub photo.PNG"
    assert body["content_type"] == "image/png" and body["size_bytes"] == len(png) and body["is_image"] is True
    assert body["uploaded_by"]["id"] == users["member"].id
    assert body["download_url"].startswith(f"/api/v1/attachments/{body['id']}/download?token=")
    assert body["created_at"].endswith("Z")
    assert set(body) == {"id", "entity_type", "entity_id", "original_name", "content_type", "size_bytes", "is_image", "uploaded_by", "download_url", "created_at"}

    row = _db.session.get(Attachment, uuid.UUID(body["id"]))
    assert row.checksum_sha256 == hashlib.sha256(png).hexdigest()
    assert row.storage_key.startswith(f"{org.id}/work_order/") and row.storage_key.endswith(".png")
    assert store.exists(row.storage_key)
    with store.open(row.storage_key) as handle:
        assert handle.read() == png
    assert [p.name for p in _stored_files(store)] == [row.storage_key.rsplit("/", 1)[1]]

    event = AuditEvent.query.filter_by(event_type="attachment.uploaded").one()
    assert event.entity_type == "work_order" and event.entity_id == str(wo.id) and event.actor_user_id == users["member"].id
    assert event.metadata_json["attachment_id"] == body["id"]
    assert event.metadata_json["entity_type"] == "work_order" and event.metadata_json["entity_id"] == str(wo.id)
    assert event.after_json["original_name"] == "hub photo.PNG" and event.after_json["size_bytes"] == len(png)

    listed = client.get(f"/api/v1/work-orders/{wo.id}/attachments")
    assert listed.status_code == 200
    payload = listed.get_json()["payload"]
    assert payload["total"] == 1 and [a["id"] for a in payload["items"]] == [body["id"]]

    single = client.get(f"/api/v1/attachments/{body['id']}")
    assert single.status_code == 200
    fresh = single.get_json()["payload"]["attachment"]
    token = fresh["download_url"].split("token=", 1)[1]
    assert storage.verify_download(token) == body["id"]


def test_upload_other_types_to_projects_and_assets(client, org, users, api_login):
    project = _project(org, "Showcase")
    asset = _asset(org)
    api_login(users["member"])
    pdf = _upload(client, f"/api/v1/projects/{project.id}/attachments", b"%PDF-1.4\n%fake\n", "layout.pdf", "application/pdf")
    assert pdf.status_code == 201
    assert pdf.get_json()["payload"]["attachment"]["entity_type"] == "project"
    assert pdf.get_json()["payload"]["attachment"]["is_image"] is False
    csv = _upload(client, f"/api/v1/assets/{asset.id}/attachments", b"date,reading\n2026-09-01,12\n", "log.csv", "text/csv")
    assert csv.status_code == 201
    stl = _upload(client, f"/api/v1/assets/{asset.id}/attachments", b"solid part\nendsolid part\n", "bracket.stl", "application/octet-stream")
    assert stl.status_code == 201
    xlsx = _upload(
        client,
        f"/api/v1/projects/{project.id}/attachments",
        b"PK\x03\x04" + b"\x00" * 30,
        "budget.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    assert xlsx.status_code == 201
    stripped = _upload(client, f"/api/v1/projects/{project.id}/attachments", b"# notes\n", "C:\\Users\\me\\..\\notes.md", "text/markdown")
    assert stripped.status_code == 201
    assert stripped.get_json()["payload"]["attachment"]["original_name"] == "notes.md"
    assert client.get(f"/api/v1/projects/{project.id}/attachments").get_json()["payload"]["total"] == 3
    assert client.get(f"/api/v1/assets/{asset.id}/attachments").get_json()["payload"]["total"] == 2


# --------------------------------------------------------------------------- validation


@pytest.mark.parametrize(
    "content, filename, content_type, fragment",
    [
        (b"MZ\x90\x00" + b"\x00" * 20, "setup.exe", "application/octet-stream", "not allowed"),
        (make_png(), "photo.png", "application/pdf", "does not match"),
        (b"definitely not a png but long enough", "photo.png", "image/png", "do not look like"),
        (b"", "empty.png", "image/png", "empty"),
        (b"%PDF-1.4", "noext", "application/pdf", "not allowed"),
        (b"PK\x03\x04" + b"\x00" * 10, "archive.zip", "application/octet-stream", "does not match"),
        (b"\x89PNG\r\n\x1a\n" + b"\x00" * 8, "photo.jpg", "image/jpeg", "do not look like"),
        (b"RIFF\x00\x00\x00\x00WAVE", "clip.webp", "image/webp", "do not look like"),
        (b"hello", "readme.txt", "application/pdf", "does not match"),
    ],
)
def test_rejected_uploads(client, org, users, api_login, store, content, filename, content_type, fragment):
    wo = _work_order(org, users["lead"])
    api_login(users["member"])
    response = _upload(client, f"/api/v1/work-orders/{wo.id}/attachments", content, filename, content_type)
    assert response.status_code == 400, response.get_json()
    body = response.get_json()
    assert body["code"] == "validation" and set(body["errors"]) == {"file"}
    assert fragment in body["errors"]["file"]
    assert Attachment.query.count() == 0 and _stored_files(store) == []


def test_missing_file_field(client, org, users, api_login):
    wo = _work_order(org, users["lead"])
    api_login(users["member"])
    response = client.post(f"/api/v1/work-orders/{wo.id}/attachments", data={"note": "no file"}, headers=UPLOAD_HEADERS, content_type="multipart/form-data")
    assert response.status_code == 400 and response.get_json()["errors"] == {"file": "Choose a file to upload."}


def test_multipart_requires_ops_header(client, org, users, api_login):
    wo = _work_order(org, users["lead"])
    api_login(users["member"])
    response = _upload(client, f"/api/v1/work-orders/{wo.id}/attachments", make_png(), "photo.png", "image/png", headers={})
    assert response.status_code == 415 and response.get_json()["code"] == "upload_header_required"


def test_oversized_uploads_are_rejected_and_not_kept(client, org, users, api_login, store, patch_settings, ctx_member):
    wo = _work_order(org, users["lead"])
    patch_settings(upload_max_bytes=1024)
    api_login(users["member"])

    # Slightly over the limit: Content-Length passes the cheap check, the streamed size does not.
    streamed = _upload(client, f"/api/v1/work-orders/{wo.id}/attachments", make_png(padding=1500), "big.png", "image/png")
    assert streamed.status_code == 400, streamed.get_json()
    assert streamed.get_json()["errors"] == {"file": "Files must be 1 KB or smaller."}
    assert _stored_files(store) == [] and Attachment.query.count() == 0

    # Far over the limit: rejected from Content-Length before the body is parsed.
    huge = _upload(client, f"/api/v1/work-orders/{wo.id}/attachments", make_png(padding=200 * 1024), "huge.png", "image/png")
    assert huge.status_code == 400 and set(huge.get_json()["errors"]) == {"file"}
    assert _stored_files(store) == []

    with pytest.raises(ValidationErrors) as excinfo:
        attachments_service.ensure_request_size(1024 + attachments_service.MULTIPART_OVERHEAD + 1)
    assert set(excinfo.value.errors) == {"file"}
    attachments_service.ensure_request_size(1024 + attachments_service.MULTIPART_OVERHEAD)
    attachments_service.ensure_request_size(None)

    exactly = _upload(client, f"/api/v1/work-orders/{wo.id}/attachments", make_png(padding=1024 - len(make_png()) - 12 - 4), "fits.png", "image/png")
    assert exactly.status_code == 201, exactly.get_json()
    assert exactly.get_json()["payload"]["attachment"]["size_bytes"] <= 1024


def test_validation_helpers():
    assert attachments_service.content_type_matches("png", "image/png")
    assert attachments_service.content_type_matches("jpg", "image/jpeg")
    assert not attachments_service.content_type_matches("png", "application/pdf")
    assert attachments_service.content_type_matches("pdf", "application/pdf")
    assert attachments_service.content_type_matches("md", "text/markdown")
    assert not attachments_service.content_type_matches("csv", "application/octet-stream")
    assert attachments_service.content_type_matches("stl", "model/stl")
    assert attachments_service.content_type_matches("gcode", "application/octet-stream")
    assert attachments_service.content_type_matches("zip", "application/x-zip-compressed")
    assert attachments_service.content_type_matches("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    assert attachments_service.content_type_matches("3mf", "model/3mf")
    assert not attachments_service.content_type_matches("xlsx", "model/3mf")
    assert not attachments_service.content_type_matches("png", "")
    assert not attachments_service.content_type_matches("exe", "application/octet-stream")

    assert attachments_service.magic_matches("png", b"\x89PNG\r\n\x1a\n")
    assert attachments_service.magic_matches("jpeg", b"\xff\xd8\xff\xe0")
    assert attachments_service.magic_matches("gif", b"GIF89a")
    assert attachments_service.magic_matches("webp", b"RIFF\x00\x00\x00\x00WEBPVP8 ")
    assert not attachments_service.magic_matches("webp", b"RIFF\x00\x00\x00\x00WAVE")
    assert attachments_service.magic_matches("pdf", b"%PDF-1.7")
    assert attachments_service.magic_matches("3mf", b"PK\x03\x04")
    assert not attachments_service.magic_matches("docx", b"PK\x05\x06")
    assert attachments_service.magic_matches("txt", b"anything")
    assert attachments_service.magic_matches("stl", b"\x00binary stl")

    assert attachments_service.clean_filename("C:\\Users\\me\\report.pdf") == "report.pdf"
    assert attachments_service.clean_filename("../../etc/passwd") == "passwd"
    assert attachments_service.clean_filename("  .hidden.png ") == "hidden.png"
    assert attachments_service.extension_of("archive.tar.ZIP") == "zip"
    assert attachments_service.extension_of("README") == ""


# --------------------------------------------------------------------------- downloads


def test_download_requires_a_valid_token(app, client, org, users, api_login, patch_settings):
    wo = _work_order(org, users["lead"])
    png = make_png(2, 2)
    api_login(users["member"])
    body = _upload(client, f"/api/v1/work-orders/{wo.id}/attachments", png, "photo.png", "image/png").get_json()["payload"]["attachment"]
    download_url = body["download_url"]
    token = download_url.split("token=", 1)[1]

    anonymous = app.test_client()  # no session at all: the token is the credential
    good = anonymous.get(download_url)
    assert good.status_code == 200
    assert good.data == png
    assert good.mimetype == "image/png"
    assert good.headers["Content-Disposition"].startswith("attachment;") and "photo.png" in good.headers["Content-Disposition"]
    assert good.headers["Cache-Control"] == "private, no-store"
    assert good.headers["X-Content-Type-Options"] == "nosniff"
    good.close()  # the test client keeps the streamed file open until the response is closed

    logged_in = client.get(download_url)
    assert logged_in.status_code == 200 and logged_in.data == png
    assert "no-store" in logged_in.headers["Cache-Control"] and "private" in logged_in.headers["Cache-Control"]
    logged_in.close()

    missing = anonymous.get(f"/api/v1/attachments/{body['id']}/download")
    assert missing.status_code == 403 and missing.get_json()["code"] == "invalid_token"

    tampered = anonymous.get(f"/api/v1/attachments/{body['id']}/download?token={token}x")
    assert tampered.status_code == 403 and tampered.get_json()["code"] == "invalid_token"

    garbage = anonymous.get(f"/api/v1/attachments/{body['id']}/download?token=garbage")
    assert garbage.status_code == 403 and garbage.get_json()["code"] == "invalid_token"

    other_id = uuid.uuid4()
    wrong_attachment = anonymous.get(f"/api/v1/attachments/{other_id}/download?token={token}")
    assert wrong_attachment.status_code == 403 and wrong_attachment.get_json()["code"] == "invalid_token"

    unknown_but_signed = anonymous.get(f"/api/v1/attachments/{other_id}/download?token={storage.sign_download(other_id, users['member'].id)}")
    assert unknown_but_signed.status_code == 404 and unknown_but_signed.get_json()["code"] == "not_found"

    store = storage.get_storage()
    store.delete(_db.session.get(Attachment, uuid.UUID(body["id"])).storage_key)
    gone = anonymous.get(download_url)
    assert gone.status_code == 404 and gone.get_json()["code"] == "file_missing"

    patch_settings(ops_download_ttl_seconds=0)
    time.sleep(1.1)  # itsdangerous timestamps have one-second resolution
    expired = anonymous.get(download_url)
    assert expired.status_code == 403 and expired.get_json()["code"] == "invalid_token"


# --------------------------------------------------------------------------- delete


def test_delete_by_uploader_or_manager_only(client, org, users, api_login, store):
    admin, member = users["admin"], users["member"]
    creator = make_user("Cal Creator", "cal@uiowa.edu", org=org)  # full member: work_order.edit@own on own work orders
    stranger = make_user("Ola Other", "ola@uiowa.edu", org=org)
    wo = _work_order(org, creator)

    api_login(member)
    first = _upload(client, f"/api/v1/work-orders/{wo.id}/attachments", make_png(), "one.png", "image/png").get_json()["payload"]["attachment"]
    second = _upload(client, f"/api/v1/work-orders/{wo.id}/attachments", make_png(), "two.png", "image/png").get_json()["payload"]["attachment"]
    third = _upload(client, f"/api/v1/work-orders/{wo.id}/attachments", make_png(), "three.png", "image/png").get_json()["payload"]["attachment"]
    assert len(_stored_files(store)) == 3

    api_login(stranger)
    denied = client.delete(f"/api/v1/attachments/{first['id']}")
    assert denied.status_code == 403 and denied.get_json()["permission"] == "work_order.edit"

    api_login(member)
    mine = client.delete(f"/api/v1/attachments/{first['id']}")
    assert mine.status_code == 200 and mine.get_json()["payload"] == {"deleted": True, "id": first["id"]}
    assert _db.session.get(Attachment, uuid.UUID(first["id"])) is None
    assert len(_stored_files(store)) == 2
    assert client.get(f"/api/v1/attachments/{first['id']}").status_code == 404
    event = AuditEvent.query.filter_by(event_type="attachment.deleted").one()
    assert event.entity_type == "work_order" and event.metadata_json["attachment_id"] == first["id"]
    assert event.before_json["original_name"] == "one.png"

    api_login(creator)
    assert client.delete(f"/api/v1/attachments/{second['id']}").status_code == 200

    api_login(admin)
    assert client.delete(f"/api/v1/attachments/{third['id']}").status_code == 200
    assert _stored_files(store) == [] and Attachment.query.count() == 0
    assert client.get(f"/api/v1/work-orders/{wo.id}/attachments").get_json()["payload"]["total"] == 0


def test_project_lead_manages_files_on_own_project(client, org, users, api_login):
    pl = make_user("Pat Lead", "pat@uiowa.edu", ops_role="project_lead", org=org)
    mine = _project(org, "Rover", lead_user_id=pl.id)
    mine.members.append(ProjectMember(user_id=pl.id, project_role="lead"))
    theirs = _project(org, "Showcase")
    _db.session.commit()

    api_login(users["member"])
    on_mine = _upload(client, f"/api/v1/projects/{mine.id}/attachments", make_png(), "a.png", "image/png").get_json()["payload"]["attachment"]
    on_theirs = _upload(client, f"/api/v1/projects/{theirs.id}/attachments", make_png(), "b.png", "image/png").get_json()["payload"]["attachment"]

    api_login(pl)
    assert client.delete(f"/api/v1/attachments/{on_mine['id']}").status_code == 200
    assert client.delete(f"/api/v1/attachments/{on_theirs['id']}").status_code == 403


# --------------------------------------------------------------------------- permissions, visibility, tenancy


def test_upload_requires_attach_permission(client, org, users, requester, api_login):
    advisor = make_user("Dr. Advisor", "advisor@uiowa.edu", ops_role="faculty_advisor", org=org)
    wo = _work_order(org, users["lead"])
    project = _project(org, "Showcase")

    api_login(requester)
    denied = _upload(client, f"/api/v1/projects/{project.id}/attachments", make_png(), "a.png", "image/png")
    assert denied.status_code == 403 and denied.get_json()["permission"] == ["work_order.attach"]
    assert client.get(f"/api/v1/projects/{project.id}/attachments").status_code == 200  # any reader may list

    api_login(advisor)
    assert client.get(f"/api/v1/work-orders/{wo.id}/attachments").status_code == 200
    denied = _upload(client, f"/api/v1/work-orders/{wo.id}/attachments", make_png(), "a.png", "image/png")
    assert denied.status_code == 403 and denied.get_json()["permission"] == ["work_order.attach"]
    assert Attachment.query.count() == 0


def test_private_project_work_order_is_hidden_from_non_members(client, org, users, api_login):
    secret = _project(org, "Sponsor Bid", visibility="private")
    wo = _work_order(org, users["lead"], project_id=secret.id)
    asset = _asset(org, project_id=secret.id)
    api_login(users["admin"])
    seeded = _upload(client, f"/api/v1/work-orders/{wo.id}/attachments", make_png(), "secret.png", "image/png").get_json()["payload"]["attachment"]

    api_login(users["member"])
    assert client.get(f"/api/v1/work-orders/{wo.id}/attachments").status_code == 404
    assert _upload(client, f"/api/v1/work-orders/{wo.id}/attachments", make_png(), "peek.png", "image/png").status_code == 404
    assert client.get(f"/api/v1/projects/{secret.id}/attachments").status_code == 404
    assert client.get(f"/api/v1/assets/{asset.id}/attachments").status_code == 404
    assert client.get(f"/api/v1/attachments/{seeded['id']}").status_code == 404
    assert client.delete(f"/api/v1/attachments/{seeded['id']}").status_code == 404
    assert Attachment.query.count() == 1

    secret.members.append(ProjectMember(user_id=users["member"].id))
    _db.session.commit()
    assert client.get(f"/api/v1/work-orders/{wo.id}/attachments").get_json()["payload"]["total"] == 1
    assert client.get(f"/api/v1/attachments/{seeded['id']}").status_code == 200


def test_cross_organization_ids_are_not_found(client, org, users, api_login):
    other = Organization(name="Other Chapter", slug=f"other-{uuid.uuid4().hex[:6]}")
    _db.session.add(other)
    _db.session.flush()
    foreign_wo = WorkOrder(organization_id=other.id, number=1, title="Foreign", created_by_user_id=users["admin"].id)
    _db.session.add(foreign_wo)
    _db.session.flush()
    foreign_file = Attachment(
        organization_id=other.id,
        entity_type="work_order",
        entity_id=foreign_wo.id,
        storage_key=f"{other.id}/work_order/{uuid.uuid4().hex}.png",
        original_name="foreign.png",
        content_type="image/png",
        size_bytes=3,
        uploaded_by_user_id=users["admin"].id,
    )
    _db.session.add(foreign_file)
    _db.session.commit()

    api_login(users["admin"])
    assert client.get(f"/api/v1/work-orders/{foreign_wo.id}/attachments").status_code == 404
    assert _upload(client, f"/api/v1/work-orders/{foreign_wo.id}/attachments", make_png(), "a.png", "image/png").status_code == 404
    assert client.get(f"/api/v1/attachments/{foreign_file.id}").status_code == 404
    assert client.delete(f"/api/v1/attachments/{foreign_file.id}").status_code == 404
    assert _db.session.get(Attachment, foreign_file.id) is not None
    assert client.get("/api/v1/attachments/not-a-uuid").status_code == 404
    assert client.get(f"/api/v1/attachments/{uuid.uuid4()}").status_code == 404
    assert client.get("/api/v1/teams/abc/attachments").status_code == 404


def test_anonymous_requests_are_rejected(client, org, users):
    wo = _work_order(org, users["lead"])
    assert client.get(f"/api/v1/work-orders/{wo.id}/attachments").status_code == 401
    assert _upload(client, f"/api/v1/work-orders/{wo.id}/attachments", make_png(), "a.png", "image/png").status_code == 401
