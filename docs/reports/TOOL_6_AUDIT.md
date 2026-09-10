# Tool #6 (Feature Query) - Audit & Verification

**Date:** 2026-09-08  
**Status:** 🔍 AUDIT IN PROGRESS  

---

## Overview

**Tool #6: Feature Query**
- **Location:** `/backend/routers/repo/intelligence.py:65-103`
- **Endpoint:** `GET /{repo_name}/features`
- **Purpose:** List all discovered features and their members with relationships
- **Input:** repo_name (URL parameter)
- **Output:** List of features with members, relationships, and metadata

---

## Current Implementation Analysis

The tool retrieves features from the repository model, extracts members and relationships, then returns them as a JSON response. However, there are several critical issues:

### Issues Identified

#### 1. ❌ Silent Exception Handling (CRITICAL)
**Line:** 102-103  
**Issue:** Catch-all exception returns empty data instead of error  
**Impact:**
- Cannot distinguish between "no features" and "error occurred"
- Makes debugging impossible
- LLM cannot tell if request succeeded or failed

#### 2. ❌ No Input Validation (HIGH)
**Line:** 66  
**Issue:** No validation of repo_name parameter  
**Impact:**
- Could silently fail for invalid repository names
- No 400 error for malformed requests

#### 3. ❌ No Logging (HIGH)
**Issue:** No logging of errors or success  
**Impact:**
- Cannot debug failures
- No visibility into what went wrong
- Cannot track usage patterns

#### 4. ⚠️ Potential AttributeError Risks (MEDIUM)
**Lines:** 83, 91-92, 98  
**Risk Areas:**
- `feature.members` - might not exist or be None
- `feature.evidence` - might not exist or be None
- `feature.metadata` - might not exist or be None
- `rel.model_dump()` - might fail for certain relationship types

#### 5. ⚠️ No Explicit HTTP Error Codes (MEDIUM)
**Issue:** Unlike Tools #2 and #3 (after fixes), always returns 200  
**Impact:**
- Client cannot distinguish error from success
- LLM integration cannot handle errors properly

#### 6. ⚠️ Data Structure Assumptions (MEDIUM)
**Issue:** Assumes all objects have expected attributes  
**Impact:** Could crash silently on schema changes

---

## Comparison with Fixed Tools

| Aspect | Tool #2 (Fixed) | Tool #3 (Fixed) | Tool #6 (Current) |
|--------|-----------------|-----------------|-------------------|
| Error Distinction | ✅ 400/404/500 | ✅ 400/404/500 | ❌ Always 200 |
| Logging | ✅ Explicit | ✅ Explicit | ❌ None |
| Input Validation | ✅ Yes | ✅ Yes | ❌ No |
| Exception Handling | ✅ Specific | ✅ Specific | ❌ Silent |
| LLM Safety | ✅ Safe | ✅ Safe | ❌ Unsafe |

---

## Recommended Fixes

### Fix #1: Replace Silent Exception with Explicit Errors
- Add try-except blocks for specific error types
- Return appropriate HTTP status codes (400/404/500)
- Add logging for debugging

### Fix #2: Input Validation
- Validate repo_name is not empty
- Return 400 for invalid input

### Fix #3: Safe Attribute Access
- Check for attribute existence before accessing
- Use getattr() with defaults
- Handle None values gracefully

### Fix #4: Add Comprehensive Logging
- Log all operations
- Log errors with stack traces
- Track successful retrievals

---

## All Tools Status

| Tool | Name | Status | Priority |
|------|------|--------|----------|
| #1 | Symbol Inspection | ⚠️ Not Reviewed | LOW |
| #2 | File Retrieval | ✅ FIXED | DONE |
| #3 | Graph Query | ✅ FIXED | DONE |
| #4 | Entity Search | ⚠️ Not Reviewed | MEDIUM |
| #5 | Symbol Search | ⚠️ Not Reviewed | MEDIUM |
| #6 | Feature Query | ❌ NEEDS FIX | HIGH |
| #7 | Context/Trace | ⚠️ Not Reviewed | LOW |

---

## Test Plan for Tool #6

### Valid Cases
1. Valid repo with features → 200 with list
2. Valid repo no features → 200 empty list
3. Features with members → 200 members included
4. Features with relationships → 200 relationships included

### Error Cases
1. Missing analysis → 404
2. Empty repo_name → 400
3. Data structure error → 500
4. Database error → 500

---

## Implementation Status

- [ ] Fix silent exception handling
- [ ] Add input validation
- [ ] Add logging
- [ ] Safe attribute access
- [ ] Write tests
- [ ] Verify all error cases

