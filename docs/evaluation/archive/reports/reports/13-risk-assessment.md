# Risk Assessment

**Confidence:** Verified  
**Cross-reference:** All reports

---

## Risk Register

Risks are scored by **Likelihood × Impact** (1-5 scale each).

| ID | Risk | Likelihood | Impact | Score | Category |
|----|------|-----------|--------|-------|---------|
| R-01 | Committed real GitHub OAuth credentials rotated | 5 | 5 | 25 | Security |
| R-02 | Docker Compose env var mismatch — backend can't connect to DB in Docker | 5 | 5 | 25 | Availability |
| R-03 | Hard-coded login URL breaks authentication in non-local environments | 5 | 5 | 25 | Functionality |
| R-04 | JWT tokens have no expiration — stolen tokens valid forever | 3 | 5 | 15 | Security |
| R-05 | `get_or_build_model()` deserializes full RIM on every request — performance collapse at scale | 4 | 4 | 16 | Performance |
| R-06 | Multi-user ChromaDB collection name collision | 3 | 4 | 12 | Data Isolation |
| R-07 | `allow_origins=["*"]` + `allow_credentials=True` invalid CORS config | 3 | 4 | 12 | Security |
| R-08 | Semantic search SSE task name mismatch → stuck spinner UX | 5 | 2 | 10 | UX Bug |
| R-09 | `main.py.orig` confusion leads developer to edit wrong file | 3 | 3 | 9 | Maintainability |
| R-10 | Root `tests/` tests dead `src/analysis/` code → false test coverage | 5 | 3 | 15 | Quality |
| R-11 | LLM requests (Ollama) have no timeout → hung requests | 3 | 3 | 9 | Reliability |
| R-12 | Dashboard repo card renders `undefined` for repository path field | 5 | 2 | 10 | UX Bug |
| R-13 | Health score formula is heuristic, not real static analysis | 5 | 2 | 10 | Quality |
| R-14 | Call graph edges reference callee IDs that may not exist in model | 4 | 2 | 8 | Data Quality |
| R-15 | Cookie missing `Secure` and `SameSite` flags | 3 | 4 | 12 | Security |
| R-16 | Analysis artifacts stored as `blob_data` — large JSON bloats DB | 3 | 3 | 9 | Scalability |
| R-17 | Analysis jobs queue is in-memory — lost on server restart | 4 | 3 | 12 | Reliability |
| R-18 | `asyncio.create_task()` in dead function — cargo-cult risk | 1 | 4 | 4 | Code Quality |
| R-19 | ChromaDB 500 error if semantic search called before indexing | 3 | 2 | 6 | Reliability |
| R-20 | `src/analysis/` and `tests/` tests create false security — passing tests on dead code | 5 | 3 | 15 | Quality |

---

## P0 Risks (Score ≥ 20 or Critical Category)

### R-01: Real OAuth Secrets Committed to Git
**Evidence:** `.env` file contains `GITHUB_CLIENT_ID=Ov23linDXTm2BnTp1U7e` and `GITHUB_CLIENT_SECRET=772bdf168ec3b6c112ae086b0101b25b6734af16`. Git history likely also contains these.  
**Mitigation:**
1. Immediately revoke the GitHub OAuth app credentials in GitHub settings
2. Generate new credentials
3. Add `.env` to `.gitignore`
4. `git filter-repo` or BFG to remove `.env` from git history

### R-02: Docker Compose Database Connection Failure
**Evidence:** `docker-compose.yml` sets `DATABASE_URL` but backend reads `LOCAL_DATABASE_URL`.  
**Fix:** Change `docker-compose.yml` environment block:
```yaml
environment:
  - LOCAL_DATABASE_URL=postgresql+psycopg://myuser:mypassword@postgres:5432/repository_intelligence
```

### R-03: Hard-Coded Login URL
**Evidence:** `Header.jsx:58`: `window.location.href = "http://localhost:8000/api/auth/github/login"`  
**Fix:** Change to `/api/auth/github/login` (relative URL → goes through proxy)

---

## P1 Risks (Score 10-19)

### R-04: JWT Token Expiration
**Fix:** Add `exp` claim in `create_jwt()`:
```python
payload = {"user_id": user.id, "exp": datetime.utcnow() + timedelta(days=7)}
```

### R-05: `get_or_build_model()` Performance
**Fix:** Implement in-memory LRU cache keyed by `(repo_name, analysis_id)`. Invalidate on reanalysis.

### R-06: ChromaDB Multi-User Collision
**Fix:** Use `f"{current_user.id}_{repo_name}_index"` as collection name.

### R-07: CORS Configuration
**Fix:** `allow_origins=[settings.frontend_url]`

### R-10 & R-20: Root Tests Test Dead Code
**Fix:** Delete `src/analysis/` and root `tests/`, or move them to an explicit `archive/` directory.

### R-17: In-Memory Job Queue Lost on Restart
The job recovery loop in `lifespan()` re-enqueues unfinished jobs — this mitigates the issue. However, jobs that are in-flight when the server crashes (status="Analyzing") may be re-started correctly but the tmp directory may be missing.

---

## P2 Risks (Score 5-9)

### R-09, R-11, R-13, R-14, R-16 — See individual reports

---

## Risk Summary Chart

```
Score
 25 |  R-01  R-02  R-03
    |
 15 |  R-04        R-05       R-10  R-20
    |
 12 |  R-06  R-07        R-15  R-17
    |
 10 |  R-08  R-12  R-13
    |
  9 |  R-09  R-11  R-16
    |
  8 |  R-14
    |
  6 |  R-19
    |
  4 |  R-18
```
