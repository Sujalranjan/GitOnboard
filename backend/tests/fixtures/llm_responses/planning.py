"""Deterministic mock LLM fixtures for planning pipeline tests."""
import json

MOCK_REQUIREMENT_ANALYSIS = {
    "title": "Add Google OAuth Login",
    "goals": ["Allow users to log in with Google", "Store OAuth tokens securely"],
    "acceptance_criteria": [
        {"id": "AC-01", "description": "User can click 'Login with Google' and be redirected to Google OAuth."},
        {"id": "AC-02", "description": "After OAuth callback, a JWT session token is created and stored."},
        {"id": "AC-03", "description": "Invalid or expired OAuth codes return a 400 error response."},
    ],
    "security_considerations": [
        "OAuth state parameter must be validated to prevent CSRF attacks.",
        "Google client secret must never be exposed in client-side code.",
    ],
    "tests_required": [
        "Test that GET /auth/google redirects to Google OAuth URL.",
        "Test that POST /auth/google/callback with valid code returns JWT token.",
        "Test that POST /auth/google/callback with invalid code returns 400.",
    ],
}

MOCK_CONTRACT_OUTPUT = {
    "affected_components": [
        {
            "file": "backend/routers/auth.py",
            "symbol": "google_login",
            "component_type": "EXISTING",
            "evidence_ids": ["EVID-001"],
        },
        {
            "file": "backend/services/google_oauth.py",
            "symbol": "GoogleOAuthService",
            "component_type": "EXISTING",
            "evidence_ids": ["EVID-002"],
        },
    ],
    "tests_required": [
        "Test AC-01: GET /auth/google returns 302 redirect to accounts.google.com.",
        "Test AC-02: POST /auth/google/callback returns JWT in body.",
        "Test AC-03: POST /auth/google/callback with invalid code returns 400.",
    ],
    "security_considerations": ["Validate state param for CSRF", "Mask client secret"],
}

MOCK_PLAN_STEPS = json.dumps([
    {
        "step_number": 1,
        "title": "Add Google OAuth redirect endpoint",
        "description": "Create GET /auth/google endpoint that generates state and redirects to Google.",
        "target_files": ["backend/routers/auth.py"],
        "affected_symbols": ["google_login"],
        "component_type": "EXISTING",
        "acceptance_criteria": ["AC-01"],
        "evidence_ids": ["EVID-001"],
        "expected_changes": "Add google_login route and state generation logic.",
        "dependencies": [],
    },
    {
        "step_number": 2,
        "title": "Implement OAuth callback handler",
        "description": "Handle Google callback, exchange code for token, create JWT session.",
        "target_files": ["backend/routers/auth.py", "backend/services/google_oauth.py"],
        "affected_symbols": ["google_callback", "GoogleOAuthService"],
        "component_type": "EXISTING",
        "acceptance_criteria": ["AC-02", "AC-03"],
        "evidence_ids": ["EVID-001", "EVID-002"],
        "expected_changes": "Add callback route and GoogleOAuthService.exchange_code method.",
        "dependencies": [1],
    },
    {
        "step_number": 3,
        "title": "Write unit tests for OAuth endpoints",
        "description": "Write pytest tests covering all three acceptance criteria.",
        "target_files": ["backend/tests/test_auth.py"],
        "affected_symbols": ["test_google_login", "test_google_callback"],
        "component_type": "NEW",
        "acceptance_criteria": ["AC-01", "AC-02", "AC-03"],
        "evidence_ids": [],
        "expected_changes": "Create test_auth.py with 3 test functions.",
        "dependencies": [1, 2],
    },
])
