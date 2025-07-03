from fastapi import APIRouter, Depends, HTTPException, status, Response, Request, Cookie
from sqlalchemy.orm import Session
from typing import Optional
from jose import JWTError

# --- Local Imports ---
from database import get_db
from models import User, Invite
from schemas import RegisterRequest, LoginRequest, UserResponse
from auth import (
    create_access_token,
    create_refresh_token,
    authenticate_user,
    get_current_user,
    decode_refresh_token,
    register_user,
)

# --- Rate Limiter Imports ---
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


# --- REGISTER ---
@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register_new_user(
    request: Request,
    payload: RegisterRequest,
    db: Session = Depends(get_db)
):
    if payload.password != payload.password_confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match"
        )

    invite_code = request.query_params.get("invite")
    role = "owner"  # default role

    if invite_code:
        invite = db.query(Invite).filter(
            Invite.code == invite_code, Invite.used == False).first()
        if invite:
            role = "employee"
            invite.used = True
            # we’ll commit after registering user so it’s atomic
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired invite code"
            )

    new_user = register_user(
        db,
        email=payload.email,
        password=payload.password,
        name=payload.name,
        role=role
    )

    if invite_code:
        db.commit()  # finalize the invite mark-used

    return {"message": f"User '{new_user.email}' registered successfully as {role}."}


# --- LOGIN ---
@router.post("/login")
@limiter.limit("10/minute")
async def login_for_token(
    request: Request,             # <-- add this
    response: Response,
    payload: LoginRequest,
    db: Session = Depends(get_db)
):
    user = authenticate_user(db, payload.email, payload.password)

    access_token = create_access_token(data={"sub": user.email})
    refresh_token = create_refresh_token(data={"sub": user.email})

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,     # best practice
        samesite="lax",
        max_age=7 * 24 * 60 * 60  # 7 days
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "email": user.email,
        "display_name": user.name,
        "role": user.role,
    }


# --- GET CURRENT USER ---
@router.get("/me", response_model=UserResponse)
async def get_my_info(current_user: User = Depends(get_current_user)):
    # response_model filters fields automatically
    return current_user


# --- REFRESH TOKEN ---
@router.post("/refresh-token")
@limiter.limit("10/minute")
async def refresh_access_token(
    request: Request,           # <--- ADD THIS
    response: Response,
    refresh_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db)
):
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token missing")

    try:
        payload = decode_refresh_token(refresh_token)
        user_email = payload.get("sub")
        if not user_email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh payload")

        user = db.query(User).filter(User.email == user_email).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

        new_access_token = create_access_token(data={"sub": user.email})
        return {
            "access_token": new_access_token,
            "token_type": "bearer",
            "email": user.email,
            "display_name": user.name,
            "role": user.role,
        }
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid or expired refresh token")


# --- INVITE ---
@router.post("/invite", status_code=status.HTTP_201_CREATED)
async def create_new_invite(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "owner":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owners can create invite links."
        )

    import secrets
    code = secrets.token_urlsafe(16)

    new_invite = Invite(code=code, owner_id=current_user.id)
    db.add(new_invite)
    db.commit()

    invite_link = f"https://your-frontend-url.com/register?invite={code}"

    return {"invite_link": invite_link}


# --- LOGOUT ---
@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key="refresh_token")
    return {"message": "Logout successful"}
