import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.services.auth_service import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_user_by_id,
    register_user,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    username: str
    status: str

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


@router.post("/register", response_model=LoginResponse, status_code=201)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="密码至少6个字符")
    if len(req.username) < 2:
        raise HTTPException(status_code=400, detail="用户名至少2个字符")

    try:
        user = register_user(db, req.email, req.username, req.password)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    user_id = str(user.id)
    return LoginResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
        user=UserResponse.model_validate(user),
    )


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, req.email, req.password)
    if user is None:
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    user_id = str(user.id)
    return LoginResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
        user=UserResponse.model_validate(user),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(req: RefreshRequest, db: Session = Depends(get_db)):
    payload = decode_token(req.refresh_token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Refresh token 无效或已过期")
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Token 类型错误")

    user = get_user_by_id(db, payload["sub"])
    if user is None or user.status != "active":
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")

    user_id = str(user.id)
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
    )


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user
