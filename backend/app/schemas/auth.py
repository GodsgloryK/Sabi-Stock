from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class CredentialsBase(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Full name cannot be blank.")
        return value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class OwnerRegistration(CredentialsBase):
    business_name: str = Field(min_length=1, max_length=160)

    @field_validator("business_name")
    @classmethod
    def normalize_business_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Business name cannot be blank.")
        return value


class ManagerRegistration(CredentialsBase):
    invitation_code: str = Field(min_length=32, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class UserResponse(BaseModel):
    id: UUID
    full_name: str
    email: EmailStr
    business_id: UUID
    business_name: str
    role: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class InvitationResponse(BaseModel):
    invitation_code: str
    expires_at: datetime


class TeamMemberResponse(BaseModel):
    id: UUID
    full_name: str
    email: EmailStr
    role: str
    joined_at: datetime


class InvitationStatusResponse(BaseModel):
    id: UUID
    status: str
    expires_at: datetime
    used_at: datetime | None
    created_at: datetime


class CurrentUserResponse(UserResponse):
    pass
