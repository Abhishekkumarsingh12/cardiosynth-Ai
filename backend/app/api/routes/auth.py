from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import create_access_token
from app.database import get_db
from app.models import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    MessageOut,
    ResetPasswordRequest,
    Token,
    UserCreate,
    UserLogin,
    UserOut,
)
from app.services import auth_service
from app.services import password_reset_service

router = APIRouter()

_FORGOT_PASSWORD_ACK = (
    "If an account exists for that email, you will receive reset instructions shortly."
)


@router.post("/signup", response_model=Token)
def signup(body: UserCreate, db: Session = Depends(get_db)):
    if auth_service.get_user_by_email(db, body.email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    user = auth_service.create_user(db, body.email, body.password, body.full_name)
    token = create_access_token(str(user.id))
    return Token(access_token=token)


@router.post("/login", response_model=Token)
def login(body: UserLogin, db: Session = Depends(get_db)):
    user = auth_service.authenticate(db, body.email, body.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(str(user.id))
    return Token(access_token=token)


@router.get("/me", response_model=UserOut)
def me(current: User = Depends(get_current_user)):
    return current


@router.post("/forgot-password", response_model=MessageOut)
def forgot_password(body: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Always same response — token is logged server-side in development (no email integration)."""
    password_reset_service.issue_password_reset_token(db, body.email)
    return MessageOut(message=_FORGOT_PASSWORD_ACK)


@router.post("/reset-password", response_model=MessageOut)
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)):
    err = password_reset_service.apply_password_reset(db, body.email, body.token, body.new_password)
    if err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err)
    return MessageOut(message="Password updated. You can sign in with your new password.")
