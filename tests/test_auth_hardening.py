import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import jwt

from backend.config import settings
from backend.main import app
from backend.routers import auth as auth_router
from backend.services.github_oauth import create_jwt


def test_create_jwt_includes_expiration_and_subject():
    user = SimpleNamespace(id=42, email="user@example.com", username="alice")

    token = create_jwt(user)
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])

    assert payload["sub"] == "42"
    assert payload["email"] == "user@example.com"
    assert payload["username"] == "alice"
    assert datetime.fromtimestamp(payload["exp"], tz=timezone.utc) > datetime.now(timezone.utc)


def test_github_callback_sets_secure_cookie_in_production(monkeypatch):
    monkeypatch.setattr(auth_router.settings, "environment", "production")
    monkeypatch.setattr(auth_router.settings, "deployment_type", "PROD")
    monkeypatch.setattr(auth_router.settings, "prod_frontend_url", "https://app.example.com")

    monkeypatch.setattr(auth_router, "exchange_code_for_token", lambda code: "github-access-token")
    monkeypatch.setattr(auth_router, "fetch_user_profile", lambda access_token: {"id": 7, "login": "alice", "email": "alice@example.com", "avatar_url": "https://example.com/avatar.png"})
    monkeypatch.setattr(auth_router, "get_or_create_user", lambda db, github_data, access_token: SimpleNamespace(id=7, email="alice@example.com", username="alice", avatar="https://example.com/avatar.png"))
    monkeypatch.setattr(auth_router, "create_jwt", lambda user: "jwt-token")

    db = MagicMock()
    response = auth_router.github_callback(code="oauth-code", db=db)

    assert response.status_code == 302
    assert response.headers["location"] == "https://app.example.com/dashboard"
    cookie_header = response.headers.get("set-cookie", "")
    assert "access_token=jwt-token" in cookie_header
    assert "httponly" in cookie_header.lower()
    assert "secure" in cookie_header.lower()
    assert "samesite=lax" in cookie_header.lower()
    assert "path=/" in cookie_header.lower()


def test_cors_is_scoped_to_configured_frontend_origin():
    cors_middleware = next(m for m in app.user_middleware if m.cls.__name__ == "CORSMiddleware")

    assert cors_middleware.kwargs["allow_origins"] == [settings.frontend_url]
    assert cors_middleware.kwargs["allow_credentials"] is True