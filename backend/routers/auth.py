from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
import logging

from backend.database import get_db
from backend.config import settings
from backend.dependencies.auth import get_current_user
from backend.models.user import User
from backend.services.github_oauth import (
    get_github_login_url,
    exchange_code_for_token,
    fetch_user_profile,
    get_or_create_user,
    create_jwt
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/github", tags=["auth"])

@router.get("/login")
def github_login(prompt: str = "consent"):
    """
    Redirects the user to the GitHub OAuth authorization page.
    Forces consent prompt by appending prompt=consent parameter.
    """
    login_url = get_github_login_url()
    
    # Append prompt parameter to URL to force GitHub login/consent screen
    separator = "&" if "?" in login_url else "?"
    full_url = f"{login_url}{separator}prompt={prompt}"
    
    return RedirectResponse(url=full_url)

@router.get("/callback")
def github_callback(code: str, db: Session = Depends(get_db)):
    """
    Handles the callback from GitHub after user authorizes the app.
    Exchanges the code for a token, fetches profile, creates user,
    sets JWT cookie and redirects to frontend.
    """
    try:
        # 1. Exchange code for access token
        access_token = exchange_code_for_token(code)
        
        # 2. Fetch user profile from GitHub
        github_data = fetch_user_profile(access_token)
        
        # 3. Create or update user in database
        user = get_or_create_user(db, github_data, access_token)
        
        # 4. Create JWT session token
        jwt_token = create_jwt(user)
        
        # 5. Redirect to frontend dashboard and set HttpOnly cookie
        redirect_url = f"{settings.frontend_url}/dashboard"
        response = RedirectResponse(url=redirect_url, status_code=302)
        
        is_secure = settings.environment.lower() == "production"
        same_site = "none" if is_secure else "lax"
        
        response.set_cookie(
            key="access_token",
            value=jwt_token,
            httponly=True,
            secure=is_secure,
            samesite=same_site,
            path="/",
            max_age=settings.jwt_expire_minutes * 60
        )
        
        return response

    except Exception as e:
        logger.error(f"Error during GitHub OAuth callback: {e}")
        # Redirect to frontend with an error
        error_url = f"{settings.frontend_url}/login?error=oauth_failed"
        return RedirectResponse(url=error_url, status_code=302)

@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    """Returns the currently authenticated user."""
    return {
        "id": current_user.id,
        "github_id": current_user.github_id,
        "username": current_user.username,
        "email": current_user.email,
        "avatar": current_user.avatar
    }

@router.post("/logout")
def logout():
    """Clears the access_token session cookie and logs out user."""
    response = JSONResponse({"message": "Logged out successfully"})

    is_secure = settings.environment.lower() == "production"
    same_site = "none" if is_secure else "lax"

    response.delete_cookie(
        key="access_token",
        path="/",
        httponly=True,
        samesite=same_site,
        secure=is_secure
    )

    return response