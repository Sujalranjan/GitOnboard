# Quick Reference — Validation Gates Manual Verification

## 🔑 Critical Queries (Copy-Paste Ready)

Replace `7` with your **Analysis ID**

### ✅ GATE 1 — The Most Important Query (ZERO ORPHANED RELATIONSHIPS)

```sql
-- THE CRITICAL TEST — Must return 0
SELECT 
  COUNT(*) as orphaned_from_symbol_id,
  (SELECT COUNT(*) FROM relationships WHERE analysis_id = 7 
    AND NOT EXISTS (SELECT 1 FROM symbols s WHERE s.id = from_symbol_id)) as from_orphaned,
  (SELECT COUNT(*) FROM relationships WHERE analysis_id = 7 
    AND NOT EXISTS (SELECT 1 FROM symbols s WHERE s.id = to_symbol_id)) as to_orphaned,
  COUNT(DISTINCT r.from_symbol_id) as unique_from_symbols,
  COUNT(DISTINCT r.to_symbol_id) as unique_to_symbols
FROM relationships r
WHERE r.analysis_id = 7;
```

**✅ PASS if**: `from_orphaned = 0` AND `to_orphaned = 0`

---

### Analysis Status

```sql
SELECT id, status, repository_id FROM analyses WHERE id = 7;
```

**✅ PASS if**: `status = 'Completed'`

---

### File & Symbol Counts

```sql
SELECT 
  (SELECT COUNT(*) FROM files WHERE analysis_id = 7) as files,
  (SELECT COUNT(*) FROM symbols WHERE analysis_id = 7) as symbols,
  (SELECT COUNT(*) FROM symbols WHERE analysis_id = 7 AND symbol_type = 'file') as file_symbols,
  (SELECT COUNT(*) FROM relationships WHERE analysis_id = 7) as relationships;
```

**✅ PASS if**: `files > 0`, `symbols > files`, `relationships > 0`

---

### Path Validation (Must be canonical)

```sql
SELECT COUNT(*) as invalid_paths
FROM files
WHERE analysis_id = 7
AND (path LIKE '%\\%' OR path LIKE '/%' OR path LIKE '%/');
```

**✅ PASS if**: Returns `0`

---

### Blob Consistency

```sql
SELECT 
  COUNT(*) as total_blobs,
  COUNT(CASE WHEN blob_name IS NOT NULL THEN 1 END) as with_names,
  COUNT(CASE WHEN size > 0 THEN 1 END) as with_size
FROM files
WHERE analysis_id = 7;
```

**✅ PASS if**: `with_names ≈ total_blobs`, `with_size ≈ total_blobs`

---

## 📋 Manual Verification Checklist

### Database Verification
- [ ] Run "GATE 1 — The Most Important Query" → `from_orphaned = 0` ✓
- [ ] Run "Analysis Status" → `status = 'Completed'` ✓
- [ ] Run "File & Symbol Counts" → All > 0 ✓
- [ ] Run "Path Validation" → `invalid_paths = 0` ✓
- [ ] Run "Blob Consistency" → Names and sizes present ✓

### Azure Storage Verification
- [ ] Open Azure Storage Explorer
- [ ] Navigate to: `repositories/1/snapshots/local_clone/`
- [ ] Verify code files exist (backend/*.py, etc)
- [ ] Spot-check file sizes match PostgreSQL

### Tools Testing
- [ ] Run: `python -m backend.validation.gate3_tools_harness 7 find_files 'backend'` → Returns files ✓
- [ ] Run: `python -m backend.validation.gate3_tools_harness 7 find_symbols 'process'` → Returns symbols ✓
- [ ] Run: `python -m backend.validation.gate3_tools_harness 7 retrieval_search 'repository'` → Returns results ✓

---

## 🚀 Success Criteria

### MUST ALL BE TRUE:

```
✅ Orphaned relationships = 0
✅ Analysis status = "Completed"
✅ Files > 100
✅ Symbols > 10,000
✅ Relationships > 20,000
✅ Invalid paths = 0
✅ Blobs exist in Azure
✅ find_files works
✅ find_symbols works
✅ retrieval_search works
```

If all above ✅: **READY FOR PHASE 2M**

---

## 🔧 Access Points

### PostgreSQL (pgAdmin)
```
URL: http://localhost:5050
Email: admin@admin.com
Password: admin
DB: repository_intelligence
User: myuser
```

### Azure Storage Explorer
```
Download: https://azure.microsoft.com/en-us/products/storage/storage-explorer/
Connect to: Azurite (Local Emulator)
Container: gitonboard-repos
```

### Tools Harness
```bash
cd /home/dheeraj/repository_intelligence_platform
python -m backend.validation.gate3_tools_harness 7 [test_case] [args]
```

---

## ⚡ Common Commands

### Quick Status Check
```sql
SELECT 
  a.status,
  COUNT(f.id) as files,
  COUNT(s.id) as symbols,
  COUNT(r.id) as relationships,
  (SELECT COUNT(*) FROM relationships WHERE analysis_id = a.id 
    AND NOT EXISTS (SELECT 1 FROM symbols WHERE id = from_symbol_id)) as orphaned
FROM analyses a
LEFT JOIN files f ON a.id = f.analysis_id
LEFT JOIN symbols s ON a.id = s.analysis_id
LEFT JOIN relationships r ON a.id = r.analysis_id
WHERE a.id = 7
GROUP BY a.id, a.status;
```

### Find Orphaned (If any)
```sql
SELECT DISTINCT from_symbol_id
FROM relationships
WHERE analysis_id = 7
AND NOT EXISTS (SELECT 1 FROM symbols WHERE id = from_symbol_id)
LIMIT 20;
```

### Symbol Details
```sql
SELECT 
  name,
  qualified_name,
  symbol_type,
  line_start,
  line_end,
  file_id
FROM symbols
WHERE analysis_id = 7
LIMIT 20;
```

---

## 📝 Report Template

When verification complete, document results:

```
VALIDATION REPORT
=================
Date: [Today]
Analysis ID: 7
Repository: [Your repo name]

GATE 1 Results:
- Orphaned relationships: 0 ✓
- Invalid paths: 0 ✓
- Blob consistency: OK ✓
- File count: [X]
- Symbol count: [Y]
- Relationship count: [Z]

GATE 2 Results:
- Symbol extraction: [Sample symbols match source?]

GATE 3 Results:
- find_files: ✓
- find_symbols: ✓
- retrieval_search: ✓

Overall Status: [PASS / FAIL]
Ready for Phase 2M: [YES / NO]
```

---

## 🎯 Expected Numbers (for reference)

For a typical repository like GitOnboard:
- Files: 100-200 code files
- Symbols: 9,000-12,000 (functions, classes, methods)
- Relationships: 20,000-25,000
- FILE-type symbols: 1,500-2,000

Your numbers will vary based on repository size.

---

For detailed instructions, see: `MANUAL_VERIFICATION_GUIDE.md`
