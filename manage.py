"""Operational commands.

    python manage.py upgrade      # migrate to head (stamps legacy DBs) + seed defaults
    python manage.py seed         # seed defaults only
    python manage.py evaluate     # re-run the Launchpad engine for everyone
    python manage.py reconcile    # file stock discrepancies
    python manage.py reconcile-ops-inventory  # report ops ledger/balance mismatches (exit 1 if any)
    python manage.py worker       # dedicated outbox worker loop
    python manage.py serve        # upgrade, then run the dev server
    python manage.py routes       # list URL rules
"""

from __future__ import annotations

import sys
import time

from asme import create_app


def reconcile_ops_inventory(write=print) -> int:
    """Compare every organization's inventory balances with its ledger. Prints
    the mismatches and returns 1 when there are any, else 0. Never corrects."""
    from asme.ops.models import Organization
    from asme.ops.services import inventory_ledger

    total = 0
    for org in Organization.query.order_by(Organization.slug.asc()).all():
        mismatches = inventory_ledger.reconcile(org.id)
        total += len(mismatches)
        write(f"{org.slug}: {len(mismatches)} mismatch(es)")
        for row in mismatches:
            write(
                f"  part {row['part_id']} at location {row['location_id']}: "
                f"on_hand balance={row['balance_on_hand']} ledger={row['ledger_on_hand']}; "
                f"reserved balance={row['balance_reserved']} ledger={row['ledger_reserved']}"
            )
    return 1 if total else 0


def seed_guard(app) -> str | None:
    """Why seeding would publish a known password, or ``None`` when it is safe.

    ``create_app`` already refuses this configuration on a hosting platform. This
    is the other doorway into the same accounts: a checkout on somebody's own
    computer running the documented recovery command against the chapter's real
    database (docs/deploy-render.md section 9), where production is assumed
    rather than declared and the app is therefore lenient about settings a
    migration never uses. Creating the accounts is not one of those settings, so
    it is checked here, and only when this run would actually create one.
    """
    from sqlalchemy import func

    from asme.config import bootstrap_password_problem
    from asme.models import User

    cfg = app.config["SETTINGS"]
    if cfg.database_url.startswith("sqlite"):
        return None  # a throwaway local file, not the chapter's data
    try:
        first_run = User.query.count() == 0
        admin_missing = User.query.filter(func.lower(User.email) == cfg.default_admin_email).first() is None
    except Exception:
        # No users table yet (the migration has not run): sync_schema comes first,
        # so this is re-checked with the real answer before anything is seeded.
        return None
    if not (first_run or admin_missing):
        return None
    candidates = [("ASME_DEFAULT_ADMIN_PASSWORD", cfg.default_admin_password)]
    if first_run:
        candidates.append(("ASME_DEFAULT_USER_PASSWORD", cfg.default_user_password))
    problems = [problem for problem in (bootstrap_password_problem(name, value) for name, value in candidates) if problem]
    if not problems:
        return None
    return (
        "Refusing to create the first accounts in this database:\n- "
        + "\n- ".join(problems)
        + "\n\nSet that variable in this shell and run the command again, for example:\n"
        '  Windows PowerShell:  $env:ASME_DEFAULT_ADMIN_PASSWORD="the password you typed into the hosting dashboard"\n'
        '  macOS / Linux:       export ASME_DEFAULT_ADMIN_PASSWORD="the password you typed into the hosting dashboard"'
    )


def main(argv):
    command = (argv[1] if len(argv) > 1 else "help").strip().lower()
    if command in {"help", "-h", "--help"}:
        print(__doc__)
        return 0

    # Never spin up the background worker for one-shot commands.
    app = create_app(outbox_worker_enabled=(command in {"serve"}), auto_migrate=False)
    with app.app_context():
        from asme.services import bootstrap

        if command == "upgrade":
            print("schema:", bootstrap.sync_schema())
            blocked = seed_guard(app)
            if blocked:
                print(blocked)
                return 2
            print("seed:", bootstrap.seed_defaults())
            return 0
        if command == "seed":
            blocked = seed_guard(app)
            if blocked:
                print(blocked)
                return 2
            print("seed:", bootstrap.seed_defaults())
            return 0
        if command == "evaluate":
            from asme.models import User
            from asme.services.onboarding import engine

            users = User.query.filter(User.is_active.is_(True)).all()
            for user in users:
                engine.evaluate_user(user)
            engine.evaluate_chapter()
            print(f"evaluated {len(users)} users + chapter")
            return 0
        if command == "reconcile":
            from asme.services import inventory

            print("discrepancies filed:", len(inventory.reconcile_stock()))
            return 0
        if command == "reconcile-ops-inventory":
            return reconcile_ops_inventory()
        if command == "worker":
            from asme.jobs import process_pending, schedule_recurring

            poll = app.config["SETTINGS"].outbox_poll_seconds
            print(f"outbox worker running (poll {poll}s); Ctrl+C to stop")
            while True:
                # The recurring schedule lives here as well as in the in-process
                # worker thread, so running this command with ASME_OUTBOX_WORKER=0
                # on the web service keeps the nightly stock reconciliation and the
                # hourly work-order scan running. Both are idempotent per window.
                scheduled = schedule_recurring()
                if scheduled:
                    print("scheduled", scheduled)
                done = process_pending()
                if done:
                    print("processed", done)
                time.sleep(poll)
        if command == "routes":
            for rule in sorted(app.url_map.iter_rules(), key=lambda r: (r.rule, r.endpoint)):
                methods = ",".join(sorted(m for m in rule.methods if m not in {"HEAD", "OPTIONS"}))
                print(f"{methods:12} {rule.rule:55} {rule.endpoint}")
            return 0
        if command == "serve":
            print("schema:", bootstrap.sync_schema())
            blocked = seed_guard(app)
            if blocked:
                print(blocked)
                return 2
            print("seed:", bootstrap.seed_defaults())
    if command == "serve":
        settings = app.config["SETTINGS"]
        app.run(host="0.0.0.0", port=settings.port, debug=settings.env == "development")
        return 0

    print(f"unknown command: {command}")
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
