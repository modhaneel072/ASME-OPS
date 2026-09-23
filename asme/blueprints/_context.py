"""Template context builders shared by the HTML blueprints.

These read; they never write. Anything that mutates lives in ``asme.services``.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from flask import current_app, render_template
from sqlalchemy import func

from asme.auth.session import current_auth_user, current_user_member, get_active_member, is_admin_member, role_allows
from asme.config import settings
from asme.constants import ITEM_TYPES, PRINT_REQUEST_PRINTERS, PRINT_REQUEST_STATUSES, PRINTER_TYPES
from asme.content_data import FRONT_CLUB_HIGHLIGHTS, FRONT_CLUB_MISSION, FRONT_PROJECT_SHOWCASE
from asme.extensions import db
from asme.models import (
    AttendanceRecord,
    ContactMessage,
    Event,
    Item,
    Member,
    NFCTag,
    PrintRequest,
    Project,
    Transaction,
    User,
)
from asme.services import attendance, audit, content, fabrication, inventory, scheduling
from asme.utils import default_due_date

# --------------------------------------------------------------------------- public / portal contexts


def public_site_context(page_title):
    user = current_auth_user()
    projects = Project.query.order_by(Project.created_at.desc(), Project.id.desc()).all()
    project_filters = sorted({(project.project_type or "General").strip() for project in projects if project}) or ["General"]
    return {
        "page_title": page_title,
        "current_user": user,
        "projects": projects,
        "project_filters": project_filters,
        "announcements": content.public_announcements(limit=5),
    }


def member_dashboard_context():
    from asme.services.onboarding import engine

    user = current_auth_user()
    member = current_user_member(user)
    open_checkouts = inventory.open_loans_for(user=user, member=member)
    items = Item.query.filter(Item.active.is_(True)).order_by(Item.name.asc(), Item.id.asc()).all()
    print_requests = (
        PrintRequest.query.filter_by(user_id=user.id).order_by(PrintRequest.created_at.desc(), PrintRequest.id.desc()).all()
    )
    my_help_messages = (
        ContactMessage.query.filter_by(user_id=user.id, kind="help")
        .order_by(ContactMessage.created_at.desc(), ContactMessage.id.desc())
        .limit(40)
        .all()
    )
    return {
        "current_user": user,
        "member_profile": member,
        "items": items,
        "open_checkouts": open_checkouts,
        "print_requests": print_requests,
        "portal_print_printers": PRINT_REQUEST_PRINTERS,
        "upcoming_events": scheduling.upcoming_events(limit=25),
        "calendar_embed_url": scheduling.calendar_embed_url(),
        "announcements": content.member_announcements(limit=8),
        "my_help_messages": my_help_messages,
        "launchpad": engine.summary_for_user(user),
        "onboarding_enforced": settings().onboarding_enforce,
    }


def admin_dashboard_context():
    user = current_auth_user()
    now = datetime.now()
    active_members_count = User.query.filter(User.is_active.is_(True), User.role.in_(["member", "team_leader", "admin"])).count()
    checked_out_now_count = (
        db.session.query(func.coalesce(func.sum(Transaction.qty), 0)).filter(Transaction.status == "OUT").scalar() or 0
    )
    cfg = settings()
    return {
        "current_user": user,
        "members": Member.query.order_by(Member.name.asc()).all(),
        "users": User.query.order_by(User.created_at.desc(), User.id.desc()).all(),
        "tags": NFCTag.query.order_by(NFCTag.assigned_at.desc(), NFCTag.id.desc()).all(),
        "items": Item.query.order_by(Item.name.asc()).all(),
        "item_primary_tags": inventory.get_item_primary_tag_map(),
        "transactions": Transaction.query.order_by(Transaction.timestamp.desc(), Transaction.id.desc()).limit(120).all(),
        "print_requests": PrintRequest.query.order_by(PrintRequest.created_at.desc(), PrintRequest.id.desc()).limit(120).all(),
        "events": Event.query.order_by(Event.start_time.desc(), Event.id.desc()).limit(120).all(),
        "attendance_records": AttendanceRecord.query.order_by(AttendanceRecord.checkin_time.desc(), AttendanceRecord.id.desc()).limit(200).all(),
        "projects": Project.query.order_by(Project.created_at.desc(), Project.id.desc()).all(),
        "contact_messages": ContactMessage.query.order_by(ContactMessage.created_at.desc(), ContactMessage.id.desc()).limit(60).all(),
        "audit_logs": audit.recent(150),
        "roles": ["member", "team_leader", "admin"],
        "print_request_statuses": PRINT_REQUEST_STATUSES,
        "portal_print_printers": PRINT_REQUEST_PRINTERS,
        "item_types": ITEM_TYPES,
        "active_members_count": active_members_count,
        "checked_out_now_count": int(checked_out_now_count),
        "attendance_today_count": attendance.today_count(),
        "overdue_items_count": len(inventory.overdue_loans()),
        "low_stock_items_count": len(inventory.low_stock_items()),
        "upcoming_meetings_count": Event.query.filter(Event.start_time >= now).count(),
        "pending_print_count": fabrication.pending_count(),
        "calendar_provider": cfg.calendar_provider,
        "google_embed_set": bool(cfg.google_calendar_embed_url),
        "outlook_embed_set": bool(cfg.outlook_calendar_embed_url),
    }


# --------------------------------------------------------------------------- legacy ops contexts


def legacy_dashboard_context(transaction_limit=15):
    members = Member.query.order_by(Member.name.asc()).all()
    items = Item.query.order_by(Item.name.asc()).all()
    recent_transactions = Transaction.query.order_by(Transaction.timestamp.desc()).limit(transaction_limit).all()
    today_attendance = attendance.today_unique_scans()
    queues = fabrication.queue_snapshot()
    return {
        "members": members,
        "items": items,
        "recent_transactions": recent_transactions,
        "today_attendance": today_attendance,
        "attendance_count": len(today_attendance),
        "queues": queues,
        "default_due": str(default_due_date()),
        "today": str(date.today()),
        "low_stock_count": len([item for item in items if item.available_qty <= 2]),
        "active_prints_count": len([printer for printer in PRINTER_TYPES if queues[printer]["active"]]),
        "h2s_waiting_count": len(queues["H2S"]["queued"]),
        "p1s_waiting_count": len(queues["P1S"]["queued"]),
    }


def render_ops_page(template_name, active_page, page_title, page_subtitle, transaction_limit=15):
    cfg = settings()
    active_member = get_active_member()
    context = legacy_dashboard_context(transaction_limit=transaction_limit)
    context.update(
        {
            "active_page": active_page,
            "page_title": page_title,
            "page_subtitle": page_subtitle,
            "active_member": active_member,
            "active_member_is_admin": is_admin_member(active_member),
            "h2s_print_cmd_configured": bool(cfg.h2s_print_cmd),
            "p1s_print_cmd_configured": bool(cfg.p1s_print_cmd),
            "h2s_print_cmd_value": cfg.h2s_print_cmd,
            "p1s_print_cmd_value": cfg.p1s_print_cmd,
            "print_commands_env_file": str(Path(current_app.instance_path) / "print_commands.env"),
        }
    )
    return render_template(template_name, **context)


def frontend_portal_context():
    active_member = get_active_member()
    my_open_count = Transaction.query.filter_by(member_id=active_member.id, status="OUT").count() if active_member else 0
    return {
        "active_member": active_member,
        "active_member_is_admin": is_admin_member(active_member),
        "members": Member.query.order_by(Member.name.asc()).all(),
        "item_count": Item.query.count(),
        "available_total": int(db.session.query(func.coalesce(func.sum(Item.available_qty), 0)).scalar() or 0),
        "my_open_count": my_open_count,
        "club_mission": FRONT_CLUB_MISSION,
        "club_highlights": FRONT_CLUB_HIGHLIGHTS,
        "project_showcase": FRONT_PROJECT_SHOWCASE,
    }


def can_switch_to_team(user):
    return bool(user) and role_allows(user.role, "team_leader")
