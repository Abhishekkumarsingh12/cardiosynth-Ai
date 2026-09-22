"""Password reset token lifecycle (no email — token logged for development)."""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import PasswordResetToken, User
from app.services.auth_service import get_user_by_email

log = logging.getLogger(__name__)

RESET_TOKEN_TTL_MINUTES = 15


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.strip().encode("utf-8")).hexdigest()


def issue_password_reset_token(db: Session, email: str) -> None:
    """
    If user exists: revoke pending tokens, create new token, log plain token once (dev email).
    If user does not exist: no-op (caller returns generic message).
    """
    user = get_user_by_email(db, email)
    if not user:
        return
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used_at.is_(None),
    ).delete(synchronize_session=False)
    raw = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw)
    expires_at = datetime.utcnow() + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)
    row = PasswordResetToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at)
    db.add(row)
    db.commit()
    log.info(
        "Password reset token (dev — no email; use this once) | user_id=%s email=%s expires_utc=%s token=%s",
        user.id,
        user.email,
        expires_at.isoformat(),
        raw,
    )


def apply_password_reset(db: Session, email: str, token: str, new_password: str) -> Optional[str]:
    """
    Returns None on success, or a generic error message (safe to show) on failure.
    """
    if len(new_password) < 8:
        return "Password must be at least 8 characters."
    user = get_user_by_email(db, email)
    if not user:
        return "Invalid or expired reset link."
    th = _hash_token(token)
    row = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.token_hash == th,
            PasswordResetToken.user_id == user.id,
        )
        .first()
    )
    if row is None or row.used_at is not None:
        return "Invalid or expired reset link."
    if row.expires_at < datetime.utcnow():
        return "Invalid or expired reset link."
    user.hashed_password = hash_password(new_password)
    row.used_at = datetime.utcnow()
    db.add(user)
    db.add(row)
    db.commit()
    return None
