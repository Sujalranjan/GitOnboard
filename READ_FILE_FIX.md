# Fix: read_file Tool - Search All Snapshot Directories

**Date:** 2026-09-12  
**Issue:** `read_file` tool failed to find files that exist in Azure Blob Storage because it only looked in the hardcoded `snapshots/local_clone/` directory  
**Root Cause:** Repository snapshots are stored under different directories (e.g., `snapshots/0c68a0e46fec4f3beecf9b314d7a80f53e50ee1d/`), not just `snapshots/local_clone/`  
**Status:** ✅ FIXED

---

## Problem

When calling `read_file("backend/intelligence/capabilities/detectors/auth_detector.py")`, the tool returned:
```
File not found: 'backend/intelligence/capabilities/detectors/auth_detector.py'. 
Check that the path is correct.
```

However, the file **actually exists in Azure Blob Storage** at:
```
repositories/d3dd11a8-c483-49e0-9072-37351954a6e1/snapshots/0c68a0e46fec4f3beecf9b314d7a80f53e50ee1d/
  backend/intelligence/capabilities/detectors/auth_detector.py
```

The tool was looking for it at:
```
repositories/d3dd11a8-c483-49e0-9072-37351954a6e1/snapshots/local_clone/
  backend/intelligence/capabilities/detectors/auth_detector.py
```

---

## Root Cause

Repository snapshots can be stored under:
- `snapshots/local_clone/` (default, for initial indexing)
- `snapshots/{commit_hash}/` (for specific commits or analyses)

The `read_file()` method hardcoded the path to `snapshots/local_clone/`, causing it to miss files in other snapshot directories.

---

## Solution

Modified two methods in `backend/repository_tools/tools.py`:

### 1. `read_file()` Method (Lines 126-138)

**Before:**
```python
# Construct blob name directly
blob_name = f"repositories/{repo.repository_hash}/snapshots/local_clone/{clean_path}"
raw_text = storage.get_object_text(blob_name)  # Throws FileNotFoundError if not found
```

**After:**
```python
# Try to find the file by searching across all snapshot directories for this repo
repo_prefix = f"repositories/{repo.repository_hash}/snapshots/"
all_blobs = storage.list_objects(prefix=repo_prefix)

# Look for the file in any snapshot directory
matching_blob = None
for blob in all_blobs:
    if blob.endswith(f"/{clean_path}"):
        matching_blob = blob
        break

if not matching_blob:
    raise FileNotFoundError(f"File not found in any snapshot: {clean_path}")

raw_text = storage.get_object_text(matching_blob)
```

### 2. `get_tree()` Method (Lines 237-265)

**Before:**
```python
blob_prefix = f"repositories/{repo.repository_hash}/snapshots/local_clone/"
# Add path filter if specified
if clean_path:
    blob_prefix += clean_path + "/"
blob_names = storage.list_objects(blob_prefix)
```

**After:**
```python
repo_prefix = f"repositories/{repo.repository_hash}/snapshots/"
all_blobs = storage.list_objects(repo_prefix)

# Filter to only blobs under the requested path (or all if no path specified)
matching_files = []

for blob_name in all_blobs:
    # Extract the relative path from the blob
    # blob_name format: repositories/{hash}/snapshots/{snapshot_id}/{file_path}
    parts = blob_name.split("/")
    if len(parts) >= 5:  # repo/hash/snapshots/snapshot_id/file_path...
        # Everything after snapshots/{snapshot_id}/ is the file path
        file_path = "/".join(parts[4:])

        # Filter by clean_path if specified
        if clean_path:
            if file_path.startswith(clean_path + "/"):
                relative = file_path[len(clean_path) + 1:]
                if relative:
                    matching_files.append(relative)
        else:
            # Include all files
            matching_files.append(file_path)

# Remove duplicates (same file in multiple snapshots)
matching_files = sorted(set(matching_files))
```

---

## How It Works Now

1. **List all snapshots** for the repository using the prefix `repositories/{hash}/snapshots/`
2. **Search across all snapshot directories** for the requested file
3. **Extract the file path** from each blob name by skipping the first 4 path segments (`repositories/{hash}/snapshots/{snapshot_id}/`)
4. **Return the first matching blob** (or first unique file path for `get_tree`)
5. **Handle duplicates** (same file in multiple snapshots) by deduplicating

**Result:** Files are found regardless of which snapshot directory they're stored in.

---

## Benefits

✅ **Works with all snapshot types** — both `snapshots/local_clone/` and `snapshots/{commit_hash}/`  
✅ **Backward compatible** — still works with existing `local_clone` snapshots  
✅ **Deduplicates** — returns unique files even if they appear in multiple snapshots  
✅ **No database changes** — purely a blob storage search optimization  
✅ **Minimal code change** — only affects the blob path construction logic  

---

## Testing

The fix was verified by:
1. Checking that files exist in blob storage under non-`local_clone` paths
2. Verifying the new search logic correctly extracts file paths from blob names
3. Testing that deduplication removes duplicate files across snapshot directories
4. Confirming the backend starts without errors

**Test File:** `backend/intelligence/capabilities/detectors/auth_detector.py`
- **Before Fix:** Not found ❌
- **After Fix:** Found in `snapshots/0c68a0e46fec4f3beecf9b314d7a80f53e50ee1d/` ✅

---

## Files Modified

| File | Change | Lines |
|------|--------|-------|
| `backend/repository_tools/tools.py` | `read_file()`: Search all snapshots instead of hardcoding `local_clone` | 126-138 |
| | `get_tree()`: List all snapshots, extract paths dynamically | 237-265 |

**Total changes:** ~50 lines modified/replaced (net ~20 lines added for robustness)

---

## Rollback

If issues arise, the original hardcoded path approach can be restored by reverting to the git history.
