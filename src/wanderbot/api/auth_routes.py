"""Email/password auth: register + login -> JWT."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from wanderbot.api.deps import get_principal
from wanderbot.security.audit import audit
from wanderbot.security.auth import Principal, create_access_token
from wanderbot.storage import users

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    email: str
    password: str
    home_city: str | None = None


class TokenResponse(BaseModel):
    token: str
    email: str


class Profile(BaseModel):
    email: str | None = None
    home_city: str | None = None


@router.post("/register", response_model=TokenResponse)
async def register(creds: Credentials) -> TokenResponse:
    try:
        user_id = await users.create_user(creds.email, creds.password, creds.home_city)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    email = creds.email.strip().lower()
    audit("user_register", user_id, email=email)
    token = create_access_token(user_id, ["plan", "reserve"], email=email)
    return TokenResponse(token=token, email=email)


@router.get("/me", response_model=Profile)
async def me(principal: Principal = Depends(get_principal)) -> Profile:
    user = await users.get_user(principal.user_id)
    if user is None:
        return Profile(email=principal.email)
    return Profile(email=user["email"], home_city=user.get("home_city"))


@router.post("/me", response_model=Profile)
async def update_me(body: Profile, principal: Principal = Depends(get_principal)) -> Profile:
    await users.set_home_city(principal.user_id, body.home_city)
    user = await users.get_user(principal.user_id)
    return Profile(email=user["email"] if user else principal.email, home_city=body.home_city)


@router.post("/login", response_model=TokenResponse)
async def login(creds: Credentials) -> TokenResponse:
    user_id = await users.authenticate(creds.email, creds.password)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid email or password")
    email = creds.email.strip().lower()
    token = create_access_token(user_id, ["plan", "reserve"], email=email)
    return TokenResponse(token=token, email=email)
