from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends, Request
from fastapi.security import OAuth2PasswordBearer
from fastapi.security.utils import get_authorization_scheme_param
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import os
from dotenv import load_dotenv

from app.infrastructure.database.database import get_read_db
from app.infrastructure.models import models

load_dotenv()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

SECRET_KEY = os.getenv("JWT_SECRET", "a_sane_default_secret_key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def extract_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization")
    if authorization:
        scheme, param = get_authorization_scheme_param(authorization)
        if scheme.lower() == "bearer":
            return param

    token = request.cookies.get("access_token")
    if token:
        return token

    return None

async def get_current_user(request: Request, db: AsyncSession = Depends(get_read_db)) -> models.User:
    token = await extract_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Session expired or missing.", "code": "L101"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        subject = payload.get("sub")
        if not isinstance(subject, str):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"message": "Invalid authentication token.", "code": "L102"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        email: str = subject
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Session expired.", "code": "L101"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Could not validate credentials.", "code": "L102"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    result = await db.execute(select(models.User).filter(models.User.email == email))
    user = result.scalars().first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "User not found.", "code": "L102"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Inactive user. Please verify your email.", "code": "USER_INACTIVE"}
        )

    return user

def require_role(required_role: str):
    async def role_checker(current_user: models.User = Depends(get_current_user)):
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated"
            )
        if current_user.role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted. Requires '{required_role}' role."
            )
        return current_user
    return role_checker

async def get_current_admin(request: Request, db: AsyncSession = Depends(get_read_db)) -> models.AdminUser:
    token = await extract_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Session expired or missing.", "code": "L101"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        subject = payload.get("sub")
        if not isinstance(subject, str):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"message": "Invalid authentication token.", "code": "L102"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        email: str = subject
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Session expired.", "code": "L101"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Could not validate credentials.", "code": "L102"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    result = await db.execute(select(models.AdminUser).filter(models.AdminUser.email == email))
    admin = result.scalars().first()
    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"message": "Admin user not found.", "code": "L102"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    return admin

def require_admin_role(required_roles: list[str]):
    async def role_checker(current_admin: models.AdminUser = Depends(get_current_admin)):
        if current_admin.role.value not in required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted. Requires one of these roles: {required_roles}."
            )
        return current_admin
    return role_checker
