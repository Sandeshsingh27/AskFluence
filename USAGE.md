# AskFluence — Usage Guide

Day-to-day commands for running, querying, inspecting, and troubleshooting the service.
For first-time setup see [README.md](README.md).

---

## 1. Start / stop everything

```powershell
# Start Postgres + pgAdmin
docker compose up -d

# Stop them (keeps data)
docker compose stop

# Stop and remove containers (keeps the pgdata volume)
docker compose down

# Wipe all DB data (destroys pages/chunks/audit_log)
docker compose down -v
```

Activate the Python venv before running ingestion or the API:

```powershell
.\.venv\Scripts\Activate.ps1
```

Start the API:

```powershell
uvicorn app.main:app --reload --port 8000
```

Stop a running uvicorn: focus its terminal and press **Ctrl+C**. To free port 8000 if something is stuck:

```powershell
netstat -ano | findstr :8000
taskkill /PID <pid> /F
```

---

## 2. Ingest Confluence content

Make sure [.env](.env) has the right values, then:

```powershell
python -m app.ingestion.run
```

You'll see lines like:

```
INFO:askfluence.ingest:Space CRS: fetched 1435 pages
INFO:askfluence.ingest:Indexed page 1146929 (12 chunks)
...
INFO:askfluence.ingest:Done. Indexed 1428 pages total.
```

The ingester is **idempotent**: re-running it deletes a page's previous chunks and inserts the latest version. Safe to run again.

### Tips for large spaces

- Start with **one small space** in `CONFLUENCE_SPACES` for a smoke test.
- Embedding calls cost quota on GitHub Models; full re-ingest of thousands of pages is not free.
- The current run is **full re-ingest** every time. An incremental version (compare `version` per page) is on the roadmap.

---

## 3. Call the `/ask` API

### 3a. Quick health check

```powershell
curl.exe http://localhost:8000/health
# {"status":"ok"}
```

### 3b. PowerShell (cleanest)

```powershell
$apiKey = "<your API_KEYS value from .env>"

Invoke-RestMethod -Method Post -Uri http://localhost:8000/ask `
  -Headers @{ Authorization = "Bearer $apiKey" } `
  -ContentType "application/json" `
  -Body (@{
      question = "What does the Indirect Distribution team do?"
      filters  = @{ spaces = @("CRS") }
  } | ConvertTo-Json) `
  | ConvertTo-Json -Depth 6
```

### 3c. curl.exe (Windows-bundled)

```powershell
$apiKey = "<your API_KEYS value from .env>"

curl.exe -X POST http://localhost:8000/ask `
  -H "Authorization: Bearer $apiKey" `
  -H "Content-Type: application/json" `
  -d '{\"question\":\"What does the team do?\",\"filters\":{\"spaces\":[\"CRS\"]}}'
```

### 3d. bash / git-bash / WSL

```bash
API_KEY="<your API_KEYS value from .env>"

curl -s -X POST http://localhost:8000/ask \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question":"What does the team do?","filters":{"spaces":["CRS"]}}' \
  | jq
```

### Request schema

```json
{
  "question": "string (3..MAX_QUESTION_CHARS)",
  "filters": {
    "spaces": ["CRS", "IMN"]   // optional; alphanumeric / -/_ only
  }
}
```

### Response schema

```json
{
  "answer": "Grounded answer with inline [1], [2] citations.",
  "citations": [
    {
      "title": "Page title",
      "url":   "https://confluence.your-org.com/display/CRS/...",
      "page_id": "1146929",
      "score": 0.81
    }
  ]
}
```

If retrieval returns nothing the answer falls back to:
> "I don't have enough information in the indexed Confluence pages to answer that."

### HTTP errors

| Status | Meaning | Fix |
|---|---|---|
| `401 Missing bearer token` | header missing | add `Authorization: Bearer <key>` |
| `401 Invalid token` | wrong key | check `API_KEYS` in [.env](.env), restart uvicorn after edits |
| `413 Question too long` | exceeds `MAX_QUESTION_CHARS` | shorten or raise the limit |
| `422` | request body failed validation | check JSON shape and `spaces` characters |
| `503 API keys not configured` | `API_KEYS` empty | set it, restart uvicorn |

---

## 4. Inspect the database

### Via pgAdmin (browser)

Open <http://localhost:5050> → log in `admin@admin.com` / `admin` → server **AskFluence** is pre-registered. Drill into:

```
Databases → askfluence → Schemas → public → Tables
```

### Via psql in the container

```powershell
docker exec -it askfluence-postgres psql -U askfluence -d askfluence
```

Useful one-liners:

```powershell
# Count
docker exec askfluence-postgres psql -U askfluence -d askfluence -c `
  "SELECT count(*) AS pages FROM pages; SELECT count(*) AS chunks FROM chunks;"

# Latest indexed pages
docker exec askfluence-postgres psql -U askfluence -d askfluence -c `
  "SELECT page_id, space_key, title, updated_at FROM pages ORDER BY updated_at DESC LIMIT 10;"

# Recent audit log
docker exec askfluence-postgres psql -U askfluence -d askfluence -c `
  "SELECT created_at, user_identifier, left(question,80) FROM audit_log ORDER BY id DESC LIMIT 10;"
```

---

## 5. Reset and re-ingest

### Re-index a single space

Just edit `CONFLUENCE_SPACES` in [.env](.env) and re-run:

```powershell
python -m app.ingestion.run
```

### Wipe everything and start fresh

```powershell
docker compose down -v
docker compose up -d
python -m app.ingestion.run
```

### Change embedding model / dimension

If you change `EMBEDDING_MODEL` or `EMBEDDING_DIM`:

1. Update [.env](.env).
2. Update the `vector(N)` size in [init.sql](init.sql) so it matches.
3. `docker compose down -v && docker compose up -d`
4. Re-ingest.

(Mismatched dimensions will throw `expected N dimensions, got M` from pgvector.)

---

## 6. Troubleshooting

### `openai.APIConnectionError: ... CERTIFICATE_VERIFY_FAILED`

You're behind a TLS-intercepting proxy (Zscaler, BlueCoat, internal CA).

1. Make sure `pip-system-certs` is installed (it's in [requirements.txt](requirements.txt)). It teaches OpenSSL to use the Windows certificate store, where IT typically installs the corporate root CA.
2. If still failing, get the corporate root CA (`.pem`) from IT and:

   ```powershell
   $env:SSL_CERT_FILE      = "C:\certs\corp-root.pem"
   $env:REQUESTS_CA_BUNDLE = "C:\certs\corp-root.pem"
   python -m app.ingestion.run
   ```

3. If you're behind an HTTP proxy, also set:

   ```powershell
   $env:HTTPS_PROXY = "http://proxy.your-org.com:8080"
   $env:HTTP_PROXY  = "http://proxy.your-org.com:8080"
   ```

### Confluence `Unauthorized (401)`

- **Cloud**: `CONFLUENCE_EMAIL` is your Atlassian account email; `CONFLUENCE_API_TOKEN` is an API token from <https://id.atlassian.com/manage-profile/security/api-tokens>.
- **Server / DC**: leave `CONFLUENCE_EMAIL` empty and put a **Personal Access Token** in `CONFLUENCE_API_TOKEN` (from `<base>/plugins/personalaccesstokens/usertokens.action`). The ingester then sends `Authorization: Bearer <PAT>`.
- Verify with:

  ```powershell
  $h = @{ Authorization = "Bearer <PAT>"; Accept = "application/json" }
  curl.exe -Headers $h "https://confluence.your-org.com/rest/api/user/current"
  ```

### Confluence `404` on a space

`CONFLUENCE_SPACES` takes the **space key** (the short code in the URL like `CRS`), **not the display name**. List keys:

```powershell
$h = @{ Authorization = "Bearer <PAT>"; Accept = "application/json" }
curl.exe -Headers $h "https://confluence.your-org.com/rest/api/space?limit=200" |
  ConvertFrom-Json | Select-Object -ExpandProperty results | Select-Object key,name
```

### Postgres port already in use

Something else (often another project's Postgres) is on `5432`. Either stop it:

```powershell
docker ps --format "{{.Names}}\t{{.Ports}}"
docker stop <other-postgres-container>
```

…or remap AskFluence to another host port in [docker-compose.yml](docker-compose.yml) (e.g. `"5433:5432"`) and update `DATABASE_URL` accordingly.

### `/ask` returns "I don't have enough information…" for everything

- `chunks` table is empty → re-run ingest.
- Your `filters.spaces` doesn't match the keys you actually ingested → drop the filter or fix the keys.
- Question is unrelated to indexed content → expected.

### Settings field parsing error

`pydantic_settings` complains it can't JSON-decode a comma-separated string. The CSV fields (`API_KEYS`, `CORS_ORIGINS`, `CONFLUENCE_SPACES`) use `NoDecode` annotations to bypass JSON decoding. If you fork [app/config.py](app/config.py), keep that pattern for any list field you read from `.env`.

---

## 7. Common one-liners

```powershell
# Generate an API key
python -c "import secrets; print(secrets.token_urlsafe(48))"

# Show containers
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Tail the API (when run in a terminal, just use the terminal)
# When dockerized later: docker compose logs -f api

# Re-ingest just one space without editing .env
$env:CONFLUENCE_SPACES = "CRS"; python -m app.ingestion.run

# Open pgAdmin
Start-Process http://localhost:5050
```
