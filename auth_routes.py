from fastapi import APIRouter, Depends, HTTPException, Request, Response, Cookie
from pydantic import EmailStr
from schemas import LoginRequest, RegisterRequest
from typing import Optional
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address
from auth import (
    authenticate_user, create_access_token, create_refresh_token,
    decode_refresh_token, get_current_user, register_user
)
# FIX: Import get_db from main.py, NOT database.py
from dependencies import get_db
from models import Invite

# FIX: Add parentheses () to correctly create an INSTANCE of the APIRouter.
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.post("/register")
@limiter.limit("5/minute")
async def register(
    request: Request,
    payload: RegisterRequest,
    db: Session = Depends(get_db)
):
    # password check
    if payload.password != payload.password_confirm:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    # get invite from query params
    invite_code = request.query_params.get("invite")
    role = "owner"

    if invite_code:
        invite = db.query(Invite).filter_by(
            code=invite_code, used=False).first()
        if invite:
            role = "employee"
            invite.used = True
            db.commit()
        else:
            raise HTTPException(
                status_code=400, detail="Invalid or expired invite code")

    # register user
    register_user(db, payload.email, payload.password,
                  name=payload.name, role=role)

    return {"message": f"User registered successfully with role {role}"}


@router.post("/login")
async def login(request: Request, response: Response, payload: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, payload.email, payload.password)
    access_token = create_access_token(data={"sub": user.email})
    refresh_token = create_refresh_token(data={"sub": user.email})

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=7 * 24 * 60 * 60  # 7 days
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        # <-- ADD THIS LINE
        "display_name": user.name or user.email.split('@')[0]
    }


@router.post("/refresh-token")
def refresh_token(response: Response, refresh_token: Optional[str] = Cookie(None)):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token")

    try:
        payload = decode_refresh_token(refresh_token)
        user_email = payload.get("sub")
        if not user_email:
            raise HTTPException(
                status_code=401, detail="Invalid refresh payload")

        access_token = create_access_token(data={"sub": user_email})
        return {
            "access_token": access_token,
            "user_email": user_email,
            "display_name": user_email.split("@")[0]
        }
    except HTTPException:
        raise


@router.post("/invite")
def create_invite(
    user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if user.role != "owner":
        raise HTTPException(
            status_code=403, detail="Only owners can invite employees.")

    import secrets
    code = secrets.token_urlsafe(8)

    invite = Invite(code=code, owner_id=user.id)
    db.add(invite)
    db.commit()

    invite_link = f"https://myapp.com/register?invite={code}"
    return {"invite_link": invite_link}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key="refresh_token")
    return {"message": "Logout successful"}
