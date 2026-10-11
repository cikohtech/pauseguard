"""Create (or refresh) the demo analyst in Firebase Auth and set the custom claim role=analyst.

The API lets `/cases*` and `/metrics` through only with that claim (SECURITY_PRIVACY.md §3). The
demo login is public on purpose (landing page + README): judges sign in with it, and all the data
behind it is synthetic.

    make analyst                                    # the cloud project from .env (ADC)
    make analyst ARGS=--emulator                    # the local Auth emulator (127.0.0.1:9099)
    make analyst ARGS="--email a@b.example --password ..."   # another account

Idempotent: an existing user keeps its UID; the password is reset to the demo one and the claim is
set again. Needs the Email/Password provider enabled in Firebase Authentication.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import firebase_admin
from firebase_admin import auth

REPO_ROOT = Path(__file__).resolve().parents[1]
EMULATOR_PROJECT = "demo-pauseguard"  # same as backend/app/config.py
DEMO_EMAIL = "analyst@harbourbank.example"
DEMO_PASSWORD = "HarbourDemo2026"  # public demo login, not a secret
CLAIMS = {"role": "analyst"}


def project_from_env() -> str | None:
    if os.environ.get("GOOGLE_CLOUD_PROJECT"):
        return os.environ["GOOGLE_CLOUD_PROJECT"]
    env = REPO_ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("GOOGLE_CLOUD_PROJECT="):
                return line.split("=", 1)[1].split("#", 1)[0].strip() or None
    return None


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--email", default=DEMO_EMAIL)
    ap.add_argument("--password", default=DEMO_PASSWORD)
    ap.add_argument("--project", default=None, help="default: GOOGLE_CLOUD_PROJECT (env or .env)")
    ap.add_argument("--emulator", action="store_true", help="use the local Auth emulator")
    args = ap.parse_args(argv)

    if args.emulator:
        os.environ.setdefault("FIREBASE_AUTH_EMULATOR_HOST", "127.0.0.1:9099")
        project = EMULATOR_PROJECT
    else:
        os.environ.pop("FIREBASE_AUTH_EMULATOR_HOST", None)
        project = args.project or project_from_env()
    if not project or project == "your-project-id":
        sys.exit("Set GOOGLE_CLOUD_PROJECT in .env (or pass --project).")

    app = firebase_admin.initialize_app(options={"projectId": project})
    try:
        user = auth.get_user_by_email(args.email, app=app)
        user = auth.update_user(user.uid, password=args.password, email_verified=True, app=app)
        action = "updated"
    except auth.UserNotFoundError:
        user = auth.create_user(
            email=args.email,
            password=args.password,
            email_verified=True,
            display_name="Harbour Bank analyst (demo)",
            app=app,
        )
        action = "created"
    auth.set_custom_user_claims(user.uid, CLAIMS, app=app)
    claims = auth.get_user(user.uid, app=app).custom_claims
    where = "Auth emulator" if args.emulator else f"project {project}"
    print(f"✔ {action} {args.email} (uid {user.uid}) in {where}; custom claims: {claims}")


if __name__ == "__main__":
    main()
