# =========================
# ENV LOADER
# =========================
from dotenv import load_dotenv
load_dotenv()

# =========================
# IMPORTS
# =========================
import os
from datetime import datetime, timedelta
from jose import jwt, JWTError
from jose.exceptions import ExpiredSignatureError
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer


# =========================
# CONFIG
# =========================

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ISSUER = os.getenv("JWT_ISSUER", "UseersAuthService")

if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY no está configurada")

ACCESS_TOKEN_EXPIRE_MINUTES = 60

# OAuth opcional (para /ask)
oauth2_optional = OAuth2PasswordBearer(
    tokenUrl="/auth/login",
    auto_error=False
)

# OAuth obligatorio (para admin protegido)
oauth2_required = OAuth2PasswordBearer(
    tokenUrl="/auth/login"
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# =========================
# PASSWORDS
# =========================

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# =========================
# JWT LOCAL (si aún lo usas)
# =========================

def create_access_token(data: dict, expires_minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# =========================
# ROLE NORMALIZATION
# =========================

def normalize_role(dotnet_role: str | None) -> str | None:
    if not dotnet_role:
        return None

    role_clean = dotnet_role.strip().lower()

    mapping = {
        "estudiante": "student",
        "alumno": "student",
        "administrador": "admin",
        "administrativo": "admin",
        "admin": "admin"
    }

    return mapping.get(role_clean, role_clean)

# =========================
# JWT DECODER (.NET compatible)
# =========================

def decode_dotnet_token(token: str):
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            issuer=ISSUER,
            options={"verify_aud": False}
        )

        user_id = payload.get(
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"
        )

        email = payload.get(
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress"
        )

        username = payload.get(
            "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name"
        )

        role = payload.get(
            "http://schemas.microsoft.com/ws/2008/06/identity/claims/role"
        )

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido: sin identificador"
            )

        return {
            "user_id": int(user_id),
            "email": email,
            "username": username,
            "role": normalize_role(role)
        }

    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")


# =========================
# DEPENDENCIES
# =========================

def get_current_user(token: str | None = Depends(oauth2_optional)):
    if not token:
        return None
    return decode_dotnet_token(token)


def get_current_admin(token: str = Depends(oauth2_required)):
    user = decode_dotnet_token(token)

    if user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )

    return user
