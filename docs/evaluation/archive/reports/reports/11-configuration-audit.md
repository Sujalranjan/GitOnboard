# Configuration Audit

**Confidence:** Verified  
**Cross-reference:** [00-executive-summary.md](./00-executive-summary.md)

---

## 1. Environment Variables

### Backend (`backend/config.py` — Pydantic Settings)

| Variable | Read As | Default | Required | Source | Notes |
|----------|---------|---------|----------|--------|-------|
| `LOCAL_DATABASE_URL` | `local_database_url` | None | Yes (local) | `.env` | Pydantic Settings reads this |
| `PROD_DATABASE_URL` | `prod_database_url` | `None` | No | `.env` | |
| `GITHUB_CLIENT_ID` | `github_client_id` | None | Yes | `.env` | OAuth app credential |
| `GITHUB_CLIENT_SECRET` | `github_client_secret` | None | Yes | `.env` | OAuth app credential |
| `JWT_SECRET` | `jwt_secret` | None | Yes | `.env` | Used for signing access tokens |
| `LOCAL_FRONTEND_URL` | `local_frontend_url` | None | Yes (local) | `.env` | Used in OAuth callback redirect |
| `PROD_FRONTEND_URL` | `prod_frontend_url` | `None` | No | `.env` | |
| `DEPLOYMENT_TYPE` | `deployment_type` | `"LOCAL"` | No | `.env` | Controls which DB/frontend URL is used |
| `OLLAMA_MODEL` | `ollama_model` | `"qwen2.5-coder:7b"` | No | `.env` | LLM model name |

### `Settings.database_url` Property Logic

```python
@property
def database_url(self) -> str:
    if self.deployment_type == "PROD":
        return self.prod_database_url
    return self.local_database_url
```

**Status:** ✅ Correct.

### `Settings.frontend_url` Property Logic

```python
@property
def frontend_url(self) -> str:
    if self.deployment_type == "PROD":
        return self.prod_frontend_url
    return self.local_frontend_url
```

**Status:** ✅ Correct.

---

## 2. Docker Compose Configuration

**File:** `docker-compose.yml`

```yaml
backend:
  environment:
    - DATABASE_URL=postgresql://myuser:mypassword@postgres:5432/repository_intelligence
```

**⚠️ Critical Bug (C-01):** Docker Compose sets `DATABASE_URL` but Pydantic Settings reads `LOCAL_DATABASE_URL` (or `PROD_DATABASE_URL`). The `DATABASE_URL` variable is **never consumed** by `backend/config.py`. The backend running in Docker will have `local_database_url = None` (unless `.env` is mounted), which will cause a Pydantic validation error at startup.

**Fix:** Change docker-compose.yml to:
```yaml
environment:
  - LOCAL_DATABASE_URL=postgresql+psycopg://myuser:mypassword@postgres:5432/repository_intelligence
```

---

## 3. `.env` File Security

**⚠️ Critical Security Issue (C-02):** The `.env` file is **committed to the repository** and contains:
- Real GitHub OAuth credentials (`GITHUB_CLIENT_ID=Ov23linDXTm2BnTp1U7e`, `GITHUB_CLIENT_SECRET=772bdf168ec3b6c112ae086b0101b25b6734af16`)
- A real JWT signing secret

These credentials should be considered **compromised** and must be rotated immediately.

**`.env.example`** exists and is correctly formatted, but it does not prevent `.env` from being committed.

**Fix:**
1. Add `.env` to `.gitignore`
2. Rotate all secrets immediately
3. Use environment variable injection in CI/CD

---

## 4. Next.js Configuration

**File:** `frontend/next.config.ts`

```typescript
async rewrites() {
  return [
    { source: "/api/:path*", destination: "http://127.0.0.1:8000/api/*" }
  ];
}
```

**Status:** ✅ Correct for local development. Hard-codes backend address — expected for a dev config.  
**Note:** Production deployment would require a different configuration (e.g., env-based destination URL).

---

## 5. CORS Configuration

**File:** `backend/main.py`

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**⚠️ Bug (C-03):** `allow_origins=["*"]` combined with `allow_credentials=True` is invalid per the CORS specification. Browsers will reject credentialed cross-origin requests when the origin is `*`. The current setup works in local dev because the proxy hides the origin, but this configuration is incorrect.

**Fix:** Use explicit origin:
```python
allow_origins=[settings.frontend_url],
allow_credentials=True,
```

---

## 6. JWT Configuration

| Setting | Value | Notes |
|---------|-------|-------|
| Algorithm | `HS256` (inferred from PyJWT default) | Standard |
| Expiry | None set (no `exp` claim) | ⚠️ Tokens never expire |
| Secret source | `settings.jwt_secret` | Reads from `JWT_SECRET` env var |
| Cookie | `httponly=True`, no `samesite`, no `secure` | ⚠️ Missing `Secure` and `SameSite` |

**⚠️ Bug (C-04):** JWT tokens have no expiration. A stolen token is valid forever.

**⚠️ Bug (C-05):** Cookie is missing `Secure` flag (required for HTTPS in production) and explicit `SameSite` policy.

---

## 7. Database Driver Configuration

**File:** `.env`
```
LOCAL_DATABASE_URL=postgresql+psycopg://myuser:mypassword@postgres:5432/repository_intelligence
```

Uses `psycopg` (psycopg3), which is correct for modern SQLAlchemy. The `docker-compose.yml` value uses the old `postgresql://` URL without the driver specifier — further confirming the Docker Compose bug.

---

## 8. Ollama Configuration

| Setting | Value | Notes |
|---------|-------|-------|
| Base URL | Hard-coded `http://localhost:11434` | ⚠️ Not configurable via env var |
| Model | `settings.ollama_model` (from env) | ✅ Configurable |
| Timeout | Not set | ⚠️ LLM requests could hang indefinitely |

**File:** `backend/llm_service.py` — the `requests.post()` call has no `timeout` parameter.

---

## 9. Data Storage Paths

| Data Type | Path | Configurable? |
|-----------|------|--------------|
| Cloned repos (temp) | `/tmp/repo-analysis/job_{id}_{repo}/` | ❌ Hard-coded |
| Analysis artifacts | PostgreSQL `AnalysisArtifact.blob_data` | N/A |
| ChromaDB vector store | `{DATA_REPOS_PATH}/chroma` | Via `DATA_REPOS_PATH` constant in repo.py |

**Note:** `DATA_REPOS_PATH` in `repo.py` appears to be a path constant. Verify whether it is configurable via env.

---

## Configuration Health Summary

| Issue | Severity | Status |
|-------|---------|--------|
| Real secrets in `.env` committed to git | **P0** | ⚠️ Must rotate + add to .gitignore |
| Docker Compose env var name mismatch | **P0** | ⚠️ Backend can't connect to DB via Docker |
| JWT tokens never expire | **P1** | ⚠️ Security risk |
| Cookie missing `Secure` and `SameSite` | **P1** | ⚠️ Security risk |
| CORS `allow_origins=["*"]` + credentials | **P1** | ⚠️ Invalid combination |
| Ollama URL hard-coded | **P2** | Low risk for MVP |
| LLM request no timeout | **P2** | Risk of hung requests |
