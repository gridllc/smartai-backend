from pydantic import BaseModel, EmailStr
from typing import Optional


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    password_confirm: str
    name: Optional[str] = None  # Make name optional for more flexibility

# ADD THIS NEW CLASS


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    name: Optional[str]
    role: str

    class Config:
        orm_mode = True  # This tells Pydantic to read data from ORM models
