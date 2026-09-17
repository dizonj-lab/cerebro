"""Request/response contracts for the authentication API."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

PASSWORD_MIN_LENGTH = 10


class SignupRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    email: EmailStr = Field(max_length=320)
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=128)

    @field_validator("display_name")
    @classmethod
    def _strip_display_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Display name is required")
        return v

    @field_validator("password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        # Deliberately modest: length carries most of the strength, with a
        # letter+digit floor to reject "aaaaaaaaaa" style inputs.
        if not any(c.isalpha() for c in v):
            raise ValueError("Password must contain at least one letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        return v


class LoginRequest(BaseModel):
    email: EmailStr = Field(max_length=320)
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    """The public projection of a user. Never includes the password hash."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_name: str
    email: EmailStr
    created_at: datetime


class MessageResponse(BaseModel):
    message: str
