# Repository Storage Architecture & Azurite Local Emulation Guide

This guide explains how repository source code files are stored and how to verify, inspect, and test the **Azure Blob Storage / Azurite** local development setup.

---

## 1. Storage Architecture

```text
                    GitHub / Git Provider
                              │
                              ▼
                Temporary Worktree / Clone (/tmp)
                              │
                         scan / parse
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
       Azure Blob Storage                 PostgreSQL
       (Azurite locally)               (metadata only)
              │                               │
              │                       ┌───────┴─────────┐
              │                       │ files (metadata)│
              │                       │ symbols (AST)   │
              │                       │ relationships   │
              │                       │ contracts       │
              │                       │ capabilities    │
              │                       └─────────────────┘
              │
              ▼
       Raw repository files
       (streamed, no size limit)
```

### Key Principles
1. **Never Persist Code on Server Filesystem**: Raw code is only temporarily cloned to `/tmp` during scanning/ingestion and deleted immediately in `try ... finally`.
2. **Never Store Full Source Code in PostgreSQL**: PostgreSQL stores file metadata (`path`, `hash`, `size`, `blob_name`, `snapshot_id`), AST symbols, relationships, and code intelligence facts.
3. **Azure Blob Storage in Production & Azurite in Docker for Local Dev**: All raw repository snapshots are stored as blobs under deterministic paths:
   `repositories/{repository_id}/snapshots/{snapshot_id}/{relative_path}`

---

## 2. Docker Compose Configuration & Port Mapping

In `docker-compose.yml`, Azurite runs with Blob, Queue, and Table services enabled:

```yaml
  azurite:
    image: mcr.microsoft.com/azure-storage/azurite
    command: azurite --blobHost 0.0.0.0 --queueHost 0.0.0.0 --tableHost 0.0.0.0 --location /data --skipApiVersionCheck
    ports:
      - "10100:10000"
      - "10101:10001"
      - "10102:10002"
    volumes:
      - azurite_data:/data
```

> [!NOTE]
> **Why host port `10100` instead of `10000`?**
> On Windows machines, host port `10000` is frequently occupied by background system processes (e.g. `kpm.exe`), causing silent connection drops. Azurite host ports are mapped to `10100` (Blob), `10101` (Queue), and `10102` (Table).
>
> Inside the Docker network, the backend container connects directly to `http://azurite:10000/devstoreaccount1`.

---

## 3. How to Test & Verify Local Azurite

### Method 1: Automated Unit & Integration Tests (Recommended)
Run the full test suite using `uv`:

```bash
uv run pytest backend/tests/ -v
```

---

### Method 2: Instant Python Script (Zero Installs Needed)
Verify container creation, uploading, downloading, and listing from WSL / PowerShell:

```bash
uv run python -c "
from backend.storage import get_storage
storage = get_storage()
storage.ensure_container_exists()

# Upload a test file
storage.put_object('test.txt', 'hello from azurite')
print('Uploaded test.txt successfully!')

# Read back content
content = storage.get_object_text('test.txt')
print('Verified Content:', content)

# List all stored blobs
print('\nBlobs in gitonboard-repos:')
for b in storage.list_objects():
    print(' -', b)
"
```

---

### Method 3: Windows PowerShell with Azure CLI (`az`)
If you have Azure CLI installed on Windows:

```powershell
# 1. Set the Azurite connection string in PowerShell
$env:AZURE_STORAGE_CONNECTION_STRING = "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10100/devstoreaccount1;QueueEndpoint=http://127.0.0.1:10101/devstoreaccount1;TableEndpoint=http://127.0.0.1:10102/devstoreaccount1;"

# 2. List containers
az storage container list --output table

# 3. List all files in the container
az storage blob list --container-name gitonboard-repos --output table

# 4. View content of a stored file
az storage blob download --container-name gitonboard-repos --name test.txt --file -
```

---

### Method 4: WSL / Ubuntu Terminal with Azure CLI
From inside WSL:

```bash
export AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10100/devstoreaccount1;QueueEndpoint=http://127.0.0.1:10101/devstoreaccount1;TableEndpoint=http://127.0.0.1:10102/devstoreaccount1;"

az storage container list --output table
az storage blob list --container-name gitonboard-repos --output table
```

---

### Method 5: Azure Storage Explorer (GUI)
Connect [Azure Storage Explorer](https://azure.microsoft.com/en-us/products/storage/storage-explorer/) to inspect files visually:
1. Open Azure Storage Explorer.
2. Select **Add an Account** -> **Storage account or service** -> **Connection String**.
3. Paste the connection string:
   ```text
   DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10100/devstoreaccount1;QueueEndpoint=http://127.0.0.1:10101/devstoreaccount1;TableEndpoint=http://127.0.0.1:10102/devstoreaccount1;
   ```
4. Click **Connect** and navigate to `Blob Containers` -> `gitonboard-repos`.

---

## 4. Troubleshooting & FAQ

| Symptom | Cause | Solution |
| :--- | :--- | :--- |
| `RemoteDisconnected('Remote end closed connection without response')` | Port 10000 collision on Windows or missing Queue/Table endpoints in connection string. | Use port `10100` and ensure the connection string includes `QueueEndpoint` and `TableEndpoint`. |
| `The API version 2026-xx-xx is not supported by Azurite` | Modern Azure SDK sending newer API headers than Azurite's default expectation. | Azurite container uses `--skipApiVersionCheck` and `backend/storage/azure.py` specifies `api_version="2023-11-03"`. |
| Data missing after `docker compose down` | Missing volume mount flag. | Ensure `command` in `docker-compose.yml` includes `--location /data`. |
| `Failed to resolve 'azurite'` when running outside Docker | Running local test scripts outside the container network. | `AzureBlobStorage` automatically detects host execution and maps `azurite:10000` to `127.0.0.1:10100`. |
