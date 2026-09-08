# Repository Ambiguity: How Duplicate Names Are Handled

## Quick Answer

✅ **Different Users:** Same repo name is fine (isolated by `user_id`)  
❌ **Same User, Multiple Repos:** Ambiguity error, must use repo ID  
✅ **Workaround:** Always use repo ID to avoid ambiguity

---

## The Ambiguity Detection Logic

**File:** `/backend/routers/repo/services/analysis.py:7-57`

**Function:** `resolve_repository(repo_name, db, current_user)`

```python
# Line 13: CRITICAL - Filter by current_user FIRST
repos = db.query(Repository).filter(Repository.user_id == current_user.id).all()
#      ↑ Only repos belonging to this user are searched

# Then try to match by name with ambiguity detection
```

---

## Three Resolution Strategies (In Priority Order)

### **Strategy 1: Direct Integer ID Match** ✅ (No ambiguity possible)
```
Input: repo_name="1"
Query: Repository.id = 1 AND Repository.user_id = current_user.id
Result: Returns exactly 1 repo (ID is unique)
```

### **Strategy 2: Exact URL Match** ⚠️ (Ambiguity possible)
```
Input: repo_name="https://github.com/user/repo"
Query: Repository.url = "https://github.com/user/repo" 
       AND Repository.user_id = current_user.id

# Line 39-40: Ambiguity detection
if len(exact_matches) > 1:
    raise HTTPException(
        status_code=400, 
        detail="Ambiguous repository. Please specify repository ID."
    )
```

### **Strategy 3: Slug Suffix Match** ⚠️ (Ambiguity possible)
```
Input: repo_name="GitOnboard"
Query: Repository.url ENDS WITH "/GitOnboard"
       AND Repository.user_id = current_user.id

# Line 51-52: Ambiguity detection
if len(slug_matches) > 1:
    raise HTTPException(
        status_code=400,
        detail="Ambiguous repository slug. Found N repositories. 
                Please specify repository ID."
    )
```

---

## Scenarios & Behaviors

### Scenario A: Same Repo Name, Different Users ✅

```
User Alice:
  - Repository ID=1, URL="https://github.com/alice/GitOnboard"
  
User Bob:
  - Repository ID=2, URL="https://github.com/bob/GitOnboard"

Query by User Alice: repo_name="GitOnboard"
  ↓
resolve_repository("GitOnboard", db, alice)
  ↓ Line 13: Filter by alice.id
db.query(Repository).filter(Repository.user_id == alice.id)
  ↓
Returns: [Repository(id=1, url=...alice/GitOnboard)]
  ↓
✅ Success: Returns Alice's repo (ID=1)

Query by User Bob: repo_name="GitOnboard"
  ↓
resolve_repository("GitOnboard", db, bob)
  ↓ Line 13: Filter by bob.id
db.query(Repository).filter(Repository.user_id == bob.id)
  ↓
Returns: [Repository(id=2, url=...bob/GitOnboard)]
  ↓
✅ Success: Returns Bob's repo (ID=2)
```

**Result:** ✅ NO AMBIGUITY - User isolation works perfectly

---

### Scenario B: Same User, Multiple Repos with Same Slug ❌

```
User Alice has:
  - Repository ID=1, URL="https://github.com/alice/GitOnboard"
  - Repository ID=2, URL="https://github.com/alice/GitOnboard-v2"
  
Both end with "onboard" pattern
Or Alice accidentally has two repos with same name

Query: repo_name="GitOnboard"
  ↓
resolve_repository("GitOnboard", db, alice)
  ↓ Line 13: Filter by alice.id
repos = [Repository(id=1, ...alice/GitOnboard),
         Repository(id=2, ...alice/GitOnboard-v2)]
  
Step 1: Try Integer Match
  - "GitOnboard" is not a digit → skip
  
Step 2: Try Exact URL Match
  - "GitOnboard" != full URL → 0 matches → skip
  
Step 3: Try Slug Suffix Match
  - Repository 1: url.endswith("/GitOnboard") → ✓ matches
  - Repository 2: url.endswith("/GitOnboard-v2") → doesn't match
  - slug_matches = [Repository(id=1)]
  
Result: ✅ Returns Repository ID=1
```

**Result:** ✅ Works (lucky - only 1 match)

---

### Scenario C: Same User, Two Identical Repo Names (True Ambiguity) ❌

```
User Alice somehow has:
  - Repository ID=1, URL="https://github.com/alice/GitOnboard"
  - Repository ID=3, URL="https://github.com/alice/GitOnboard"
  
(Technically shouldn't happen due to unique constraints, but theoretically...)

Query: repo_name="GitOnboard"
  ↓
resolve_repository("GitOnboard", db, alice)
  ↓ Line 13: Filter by alice.id
repos = [Repository(id=1, ...alice/GitOnboard),
         Repository(id=3, ...alice/GitOnboard)]

Step 1: Try Integer Match
  - "GitOnboard" is not a digit → skip

Step 2: Try Exact URL Match
  - "GitOnboard" != full URL → 0 matches → skip

Step 3: Try Slug Suffix Match
  - Repository 1: url.endswith("/GitOnboard") → ✓ matches
  - Repository 3: url.endswith("/GitOnboard") → ✓ matches
  - slug_matches = [Repository(id=1), Repository(id=3)]
  
Line 51: len(slug_matches) > 1 → True
Line 52: Raise HTTPException(400)
  
Result: ❌ HTTP 400 - "Ambiguous repository slug 'GitOnboard'. 
         Found 2 repositories for this user. 
         Please specify repository ID."
```

**Result:** ❌ AMBIGUITY ERROR

---

### Scenario D: Using Repository ID (Always Unambiguous) ✅

```
User Alice has multiple repos (ambiguous by slug)

Query: repo_name="1"
  ↓
resolve_repository("1", db, alice)
  ↓ Line 23: "1" is a digit
target_int_id = 1
id_match = next((r for r in repos if r.id == 1), None)
  ↓
Returns: Repository(id=1)
  
Result: ✅ Always works (ID is globally unique)
```

**Result:** ✅ ALWAYS WORKS - No ambiguity with ID

---

## Error Messages

### Ambiguous URL Match (Line 40)
```
HTTP 400
"Ambiguous repository 'https://github.com/alice/GitOnboard'. 
 2 repositories match. Please specify repository ID."
```

### Ambiguous Slug Match (Line 52)
```
HTTP 400
"Ambiguous repository slug 'GitOnboard'. 
 Found 2 repositories for this user. 
 Please specify repository ID."
```

### Not Found (Line 55)
```
HTTP 404
"Repository 'GitOnboard' not found"
```

---

## Resolution Priority (Why Order Matters)

```
Integer ID Match (priority 1)
  ↓ if not found
Exact URL Match (priority 2)
  ↓ if not found or ambiguous
Slug Suffix Match (priority 3)
  ↓ if not found or ambiguous
Not Found Error (priority 4)
```

This ordering means:
- ✅ ID is always most specific (no ambiguity)
- ✅ Exact URL catches full GitHub URLs
- ✅ Slug suffix is most flexible but can be ambiguous
- ✅ Friendly error messages guide users to use ID

---

## Best Practices

### For LLM Agents (To Avoid Ambiguity)

**Option 1: Use Repository ID** ✅ (Always works)
```
repo_name="1"
```

**Option 2: Use Full URL** ✅ (Works if exact match)
```
repo_name="https://github.com/user/GitOnboard"
```

**Option 3: Use Slug** ⚠️ (Works if only 1 match)
```
repo_name="GitOnboard"  # Risk: fails if user has multiple repos with similar names
```

### Recommendation for LLM Tools
- **When you know the ID:** Use `repo_name="1"`
- **When you know the URL:** Use full URL
- **When you only have name:** Try slug, but be prepared for 400 ambiguity error

---

## Unique Constraint Protection

**Database Level** (prevents duplicate URLs per user):
```sql
CONSTRAINT uq_user_repo_url UNIQUE (user_id, url)
```

This means:
- Same URL cannot exist twice for same user (database prevents it)
- But theoretically could have `repo/GitOnboard` and `repo/GitOnboard-v2` 

**Result:** True ambiguity (two repos with exact same name) is extremely rare in practice

---

## Summary Table

| Scenario | Input | Result | Recommendation |
|----------|-------|--------|-----------------|
| Different users, same name | `repo_name="GitOnboard"` | ✅ Works (user_id filters) | Use slug if user_id isolated |
| Same user, unique slug | `repo_name="GitOnboard"` | ✅ Works (1 match) | Safe |
| Same user, ambiguous slug | `repo_name="GitOnboard"` | ❌ 400 error (2+ matches) | **Use ID: `repo_name="1"`** |
| Using repository ID | `repo_name="1"` | ✅ Always works | **Most reliable** |
| Using full URL | `repo_name="https://..."` | ✅ Works if exact | **Very specific** |

---

## Conclusion

✅ **The system is designed correctly:**
- User isolation prevents cross-user conflicts
- Ambiguity detection prevents silent mistakes
- Clear error messages guide users to use ID
- Repository ID is always unambiguous workaround

❌ **Potential issues:**
- LLM agents should handle 400 ambiguity errors
- Users need to specify ID when ambiguity occurs
- Slug-based queries are not guaranteed unambiguous

✅ **For LLM-friendly tools:**
- Always prefer Repository ID when available
- Fall back to slug only if ID unknown
- Handle 400 ambiguity errors gracefully
- Suggest to user: "Multiple repos match. Please use repository ID."
