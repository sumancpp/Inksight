from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import UserRole


class UserBase(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255, description="Full name of the user")
    email: EmailStr = Field(..., description="Unique email address")
    role: UserRole = Field(default=UserRole.STUDENT, description="System role: student, teacher, or admin")
    is_active: bool = Field(default=True, description="Account active status")


class UserCreate(UserBase):
    password: Optional[str] = Field(None, min_length=6, max_length=128, description="Plaintext password")


class UserRegister(UserBase):
    password: str = Field(..., min_length=6, max_length=128, description="Plaintext password for registration")


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class UserRead(UserBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class TokenData(BaseModel):
    sub: Optional[str] = None
    role: Optional[str] = None
    exp: Optional[int] = None


class LoginRequest(BaseModel):
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=1, description="Account password")
