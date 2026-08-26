from fastapi import Depends, HTTPException, Request
import jwt
from sqlalchemy.orm import Session
import logging

from backend.config import settings
from backend.database import get_db
from backend.models.user import User

logger = logging.getLogger(__name__)


def get_or_create_local_dev_user(db: Session) -> User:
    """
    Retrieves or creates a default local developer user entity for LOCAL mode bypass.
    """
    user = db.query(User).first()
    if not user:
        user = User(
            github_id="local_developer",
            username="local_developer",
            email="developer@local.host",
            avatar=None,
            github_access_token="mock_local_token",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """
    Dependency to get the current authenticated user from the JWT cookie.
    If DEPLOYMENT_TYPE is LOCAL and no token is provided or invalid, bypasses authentication
    and returns the local development user.
    """
    is_local_mode = str(settings.deployment_type).upper() == "LOCAL"
    token = request.cookies.get("access_token")

    if not token:
        if is_local_mode:
            return get_or_create_local_dev_user(db)
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = payload.get("sub")
        if not user_id:
            if is_local_mode:
                return get_or_create_local_dev_user(db)
            raise HTTPException(status_code=401, detail="Invalid token payload")

        user = db.query(User).filter(User.id == int(user_id)).first()
        if not user:
            if is_local_mode:
                return get_or_create_local_dev_user(db)
            raise HTTPException(status_code=401, detail="User not found")

        return user

    except (jwt.ExpiredSignatureError, jwt.PyJWTError) as err:
        if is_local_mode:
            return get_or_create_local_dev_user(db)
        raise HTTPException(status_code=401, detail=f"Authentication token invalid: {err}")
