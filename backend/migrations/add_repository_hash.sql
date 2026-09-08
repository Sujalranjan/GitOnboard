-- Migration: Add repository_hash (UUID) column for unambiguous identification
-- Date: 2026-09-08
-- Purpose: Replace name-based repo identification with immutable UUID hash

BEGIN;

-- Step 1: Add repository_hash column (nullable initially)
ALTER TABLE repositories
ADD COLUMN repository_hash VARCHAR(36);

-- Step 2: Generate UUID for all existing repositories
UPDATE repositories
SET repository_hash = gen_random_uuid()::text
WHERE repository_hash IS NULL;

-- Step 3: Make column NOT NULL and UNIQUE
ALTER TABLE repositories
ALTER COLUMN repository_hash SET NOT NULL;

ALTER TABLE repositories
ADD CONSTRAINT uq_repository_hash UNIQUE (repository_hash);

-- Step 4: Create index for fast lookup
CREATE INDEX idx_repository_hash ON repositories(repository_hash);

-- Step 5: Verify data integrity
-- Count repos with and without hash
SELECT
    COUNT(*) as total_repos,
    SUM(CASE WHEN repository_hash IS NOT NULL THEN 1 ELSE 0 END) as repos_with_hash,
    SUM(CASE WHEN repository_hash IS NULL THEN 1 ELSE 0 END) as repos_without_hash
FROM repositories;

COMMIT;
