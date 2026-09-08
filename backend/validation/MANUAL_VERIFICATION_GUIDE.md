# Manual Verification Guide

Independent verification of validation gates using PostgreSQL Admin Panel and Azure Blob Storage Explorer.

---

## Part 1: Access PostgreSQL Admin Panel (pgAdmin)

### Step 1: Open pgAdmin

```
URL: http://localhost:5050
Email: admin@admin.com
Password: admin
```

### Step 2: Connect to Database

1. Click **"Add New Server"** (top left, lightning bolt icon)
2. General tab:
   - Name: `repository_intelligence`
3. Connection tab:
   - Host: `repository_intelligence-postgres-1` (or `postgres` in docker compose)
   - Port: `5432`
   - Username: `myuser`
   - Password: `mypassword`
   - Database: `repository_intelligence`
4. Click **"Save"**

### Step 3: Navigate to Database

1. Expand **"Servers"** → **"repository_intelligence"** → **"Databases"** → **"repository_intelligence"**
2. Expand **"Schemas"** → **"public"** → **"Tables"**

---

## Part 2: Verification Queries (GATE 1)

Copy and paste these queries into pgAdmin Query Tool (**Tools** → **Query Tool** or press Alt+Shift+Q)

### Query 1: Verify Analysis Exists and is Completed

```sql
SELECT 
  id, 
  status, 
  repository_id, 
  indexed_at, 
  indexing_status
FROM analyses
WHERE id = 7  -- Replace 7 with your analysis ID
ORDER BY id DESC
LIMIT 1;
```

**Expected Result**:
```
id | status    | repository_id | indexed_at          | indexing_status
7  | Completed | 1             | 2026-09-07 21:20:00 | partial
```

---

### Query 2: Verify File Counts

```sql
-- Count files in PostgreSQL
SELECT 
  COUNT(*) as total_files,
  COUNT(DISTINCT path) as unique_paths
FROM files
WHERE analysis_id = 7;
```

**Expected Result**:
```
total_files | unique_paths
156         | 156
```

---

### Query 3: Verify File Paths are Canonical

```sql
-- Check for backslashes or invalid paths
SELECT 
  path,
  CASE 
    WHEN path LIKE '%\\%' THEN 'BACKSLASH'
    WHEN path LIKE '/%' THEN 'LEADING_SLASH'
    WHEN path LIKE '%/' THEN 'TRAILING_SLASH'
    ELSE 'OK'
  END as issue
FROM files
WHERE analysis_id = 7
AND (path LIKE '%\\%' OR path LIKE '/%' OR path LIKE '%/');

-- If query returns 0 rows, all paths are canonical ✓
```

**Expected Result**: Empty (0 rows) = All paths canonical ✓

---

### Query 4: Verify Symbols Link to Valid Files

```sql
-- Find orphaned symbols (file_id not in files table)
SELECT 
  COUNT(*) as orphaned_symbols
FROM symbols s
WHERE s.analysis_id = 7
AND s.file_id IS NOT NULL
AND NOT EXISTS (
  SELECT 1 FROM files f 
  WHERE f.id = s.file_id 
  AND f.analysis_id = 7
);
```

**Expected Result**:
```
orphaned_symbols
0
```

---

### Query 5: THE CRITICAL TEST — Verify ZERO Orphaned Relationships

```sql
-- Find orphaned from_symbol_id references
SELECT 
  COUNT(*) as orphaned_from_symbol_id
FROM relationships r
WHERE r.analysis_id = 7
AND NOT EXISTS (
  SELECT 1 FROM symbols s 
  WHERE s.id = r.from_symbol_id 
  AND s.analysis_id = 7
);
```

**Expected Result**:
```
orphaned_from_symbol_id
0
```

---

### Query 6: Verify Relationships' to_symbol_id

```sql
-- Find orphaned to_symbol_id references
SELECT 
  COUNT(*) as orphaned_to_symbol_id
FROM relationships r
WHERE r.analysis_id = 7
AND NOT EXISTS (
  SELECT 1 FROM symbols s 
  WHERE s.id = r.to_symbol_id 
  AND s.analysis_id = 7
);
```

**Expected Result**:
```
orphaned_to_symbol_id
0
```

---

### Query 7: Summary Statistics

```sql
-- Get complete summary
SELECT 
  'Files' as metric, COUNT(*) as count FROM files WHERE analysis_id = 7
UNION ALL
SELECT 'Symbols', COUNT(*) FROM symbols WHERE analysis_id = 7
UNION ALL
SELECT 'Relationships', COUNT(*) FROM relationships WHERE analysis_id = 7
UNION ALL
SELECT 'FILE type symbols', COUNT(*) FROM symbols 
  WHERE analysis_id = 7 AND symbol_type = 'file'
UNION ALL
SELECT 'Orphaned relationships', COUNT(*) FROM relationships r
  WHERE r.analysis_id = 7
  AND (NOT EXISTS (SELECT 1 FROM symbols s WHERE s.id = r.from_symbol_id)
    OR NOT EXISTS (SELECT 1 FROM symbols s WHERE s.id = r.to_symbol_id));
```

**Expected Result**:
```
metric                    | count
Files                     | 156
Symbols                   | 11072
Relationships             | 22133
FILE type symbols         | 1620
Orphaned relationships    | 0
```

---

## Part 3: Verify Blob Storage (GATE 1)

### Access Azure Storage Explorer

#### Option A: Local Azurite (Docker)

1. **Azure Storage Explorer** (Download: https://azure.microsoft.com/en-us/products/storage/storage-explorer/)
2. Click **"Connect to Azure Storage"** (plug icon, left sidebar)
3. Select **"Emulator or Local"** (Azurite)
4. Click **"Connect"**

#### Option B: Direct URL (if exposed)

```
Azurite Blob Storage: http://localhost:10000
```

### Browse Blob Files

1. Expand **"Blob Containers"**
2. Select **"gitonboard-repos"** (or your container name)
3. Navigate: `repositories/1/snapshots/local_clone/`
4. You should see code files:
   - `backend/intelligence/engine/orchestration/pipeline.py`
   - `backend/intelligence/rim/entity.py`
   - `backend/intelligence/builder.py`
   - etc.

### Verify Blobs Match PostgreSQL

```sql
-- Get sample blob_name values
SELECT 
  path,
  blob_name,
  size
FROM files
WHERE analysis_id = 7
LIMIT 10;
```

**Then in Azure Storage Explorer**:
1. Copy a `blob_name` from query result
2. Navigate to that blob in explorer
3. Verify it exists and size matches

---

## Part 4: Verification Queries (GATE 2)

### Query 8: Verify Symbol Line Boundaries

```sql
-- Check symbols have valid line boundaries
SELECT 
  id,
  name,
  symbol_type,
  line_start,
  line_end,
  CASE 
    WHEN line_start IS NULL THEN 'MISSING_START'
    WHEN line_end IS NULL THEN 'MISSING_END'
    WHEN line_start >= line_end THEN 'INVALID_RANGE'
    ELSE 'OK'
  END as status
FROM symbols
WHERE analysis_id = 7
AND symbol_type != 'file'
LIMIT 20;
```

**Expected Result**: All have `status = 'OK'`

---

### Query 9: Sample Symbols by Type

```sql
-- View distribution of symbol types
SELECT 
  symbol_type,
  COUNT(*) as count
FROM symbols
WHERE analysis_id = 7
GROUP BY symbol_type
ORDER BY count DESC;
```

**Expected Result**:
```
symbol_type | count
function    | 5234
class       | 2145
method      | 3012
file        | 1620
module      | 61
```

---

## Part 5: Verification Queries (GATE 3)

### Query 10: Test Symbol Lookup

```sql
-- Find a specific symbol
SELECT 
  id,
  name,
  qualified_name,
  symbol_type,
  file_id,
  line_start,
  line_end
FROM symbols
WHERE analysis_id = 7
AND symbol_type = 'class'
LIMIT 1;
```

**Copy the `id` value for next query**

---

### Query 11: Test Relationship Lookup

```sql
-- Find relationships FROM a symbol
SELECT 
  r.from_symbol_id,
  r.to_symbol_id,
  r.rel_type,
  s.qualified_name as target_name
FROM relationships r
LEFT JOIN symbols s ON s.id = r.to_symbol_id
WHERE r.analysis_id = 7
AND r.from_symbol_id = '7:urn:class:YOUR_SYMBOL_ID'  -- Replace with ID from Query 10
LIMIT 10;
```

**Expected Result**: List of related symbols with relationship types

---

### Query 12: Test Retrieval Search

```sql
-- Full-text search for keywords
SELECT 
  'symbol' as type,
  qualified_name as name,
  symbol_type,
  id
FROM symbols
WHERE analysis_id = 7
AND qualified_name ILIKE '%process%'
LIMIT 10;
```

**Expected Result**: Symbols matching the search term

---

## Part 6: Manual Checklist

Use this checklist to track your verification:

```
GATE 1: Storage/Persistence
[ ] Query 1: Analysis exists and status = "Completed"
[ ] Query 2: File count > 0 and unique paths match total
[ ] Query 3: No invalid paths (0 rows returned)
[ ] Query 4: No orphaned symbols (0 rows)
[ ] Query 5: No orphaned from_symbol_id (0 rows) ← CRITICAL
[ ] Query 6: No orphaned to_symbol_id (0 rows) ← CRITICAL
[ ] Query 7: Summary shows expected counts
[ ] Azure: Blob files exist and sizes match PostgreSQL

GATE 2: Symbol Extraction
[ ] Query 8: All symbols have valid line boundaries
[ ] Query 9: Symbol types distributed correctly
[ ] Manual check: Open source file and verify symbol at lines

GATE 3: Tools Working
[ ] Query 10: Can find specific symbol
[ ] Query 11: Can find relationships from symbol
[ ] Query 12: Can search for keywords

OVERALL
[ ] All checks passed
[ ] ZERO orphaned relationships
[ ] Blob storage consistent with PostgreSQL
[ ] Ready for Phase 2M
```

---

## Troubleshooting

### Issue: Connection to PostgreSQL Failed

**Solution**:
```bash
# Check if postgres container is running
docker ps | grep postgres

# Check connection details
docker logs repository_intelligence-postgres-1

# Try connecting with psql
psql -h localhost -U myuser -d repository_intelligence -c "SELECT 1"
# Password: mypassword
```

---

### Issue: Orphaned Relationships Found

**This indicates a problem. Investigate**:
```sql
-- Find WHICH symbols are orphaned
SELECT DISTINCT 
  r.from_symbol_id,
  r.analysis_id,
  COUNT(*) as count
FROM relationships r
WHERE r.analysis_id = 7
AND NOT EXISTS (
  SELECT 1 FROM symbols s 
  WHERE s.id = r.from_symbol_id
)
GROUP BY r.from_symbol_id, r.analysis_id;

-- Then check if those symbols exist elsewhere
SELECT * FROM symbols WHERE id = 'YOUR_SYMBOL_ID';
```

---

### Issue: Azure Blobs Not Found

**Check blob path**:
```sql
-- Get exact blob_name value
SELECT blob_name, size FROM files 
WHERE analysis_id = 7 LIMIT 5;

-- Try accessing it
-- In Azure Storage Explorer, navigate to: repositories/1/snapshots/local_clone/...
```

---

## Success Criteria

✅ **ALL of the following must be true**:

1. **Query 1**: Analysis status = "Completed"
2. **Query 2**: Files > 100, unique paths = total files
3. **Query 3**: Zero invalid paths
4. **Query 4**: Zero orphaned symbols
5. **Query 5**: **Zero orphaned from_symbol_id** ← CRITICAL
6. **Query 6**: **Zero orphaned to_symbol_id** ← CRITICAL
7. **Query 7**: Symbols > Files (more symbols than files due to functions/classes in each file)
8. **Azure**: Blobs exist and match PostgreSQL paths
9. **Query 8**: All symbols have valid line boundaries
10. **Query 9**: Symbol types distributed across function/class/method/file
11. **Query 10-12**: Lookups and searches work

If all above pass: **✅ GATE 1 & 2 VERIFIED**

---

## Next Steps

Once you've verified with this manual checklist:

1. Run GATE 3 tools harness for automated testing
2. Document results with screenshot/timestamp
3. If all gates pass: Ready for Phase 2M approval
