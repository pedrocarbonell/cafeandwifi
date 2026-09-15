"""Per-session CSRF tokens for the admin forms."""

import hmac
import secrets

from flask import abort, request, session

SESSION_KEY = "csrf_token"


def token() -> str:
    if SESSION_KEY not in session:
        session[SESSION_KEY] = secrets.token_urlsafe(32)
    return session[SESSION_KEY]


def protect() -> None:
    """Reject any state-changing request that doesn't carry this session's token."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    expected = session.get(SESSION_KEY)
    sent = request.form.get(SESSION_KEY, "")
    if not expected or not hmac.compare_digest(expected, sent):
        abort(400, "The form expired. Go back, reload the page and try again.")
