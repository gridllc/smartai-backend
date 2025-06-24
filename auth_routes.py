import sqlite3
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi import Response, Cookie
from sqlalchemy.orm import Session
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from auth import authenticate_user, register_user, create_access_token, get_current_user
from auth import create_refresh_token
from database import get_db
from models import Base
from pydantic import BaseModel

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str


@router.post("/register")
@limiter.limit("5/minute")
async def register(request: Request, payload: RegisterRequest, db: Session = Depends(get_db)):
    try:
        register_user(db, payload.email, payload.password)
        return {"message": "User registered successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login")
async def login(request: Request, payload: LoginRequest, db: Session = Depends(get_db), response: Response):
    try:
        user = authenticate_user(db, payload.email, payload.password)
        access_token = create_access_token(data={"sub": user.email})
        refresh_token = create_refresh_token(
            data={"sub": user.email})  # this must exist already

        # Set refresh token in HTTP-only secure cookie
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
            "token_type": "bearer"
        }

    except Exception:
        raise HTTPException(status_code=401, detail="Invalid credentials")

# Create a refresh token with a 7-day expiration.


@router.post("/refresh-token")
def refresh_token(
    response: Response,
    refresh_token: str = Cookie(None)
):
    if not refresh_token:
        raise HTTPException(
            status_code=401, detail="No refresh token provided")

    try:
        # Decode and validate token
        # Your helper should do jwt.decode + expiry check
        payload = decode_refresh_token(refresh_token)
        email = payload.get("sub")
        if not email:
            raise HTTPException(
                status_code=401, detail="Invalid refresh token payload")

        # Generate new tokens
        new_access_token = create_access_token({"sub": email})
        new_refresh_token = create_refresh_token({"sub": email})

        # Set refreshed token in cookie
        response.set_cookie(
            key="refresh_token",
            value=new_refresh_token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=7 * 24 * 60 * 60  # 7 days
        )

        return {"access_token": new_access_token}

    except Exception as e:
        raise HTTPException(
            status_code=401, detail=f"Refresh failed: {str(e)}")
