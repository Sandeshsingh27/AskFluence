# AskFluence — Minimal Secure Confluence Q&A (FastAPI + pgvector + GitHub Models)

A minimal RAG service that answers questions over your Confluence pages.
- **LLM & embeddings**: [GitHub Models](https://github.com/marketplace/models) (`gpt-4o-mini`, `text-embedding-3-small`)
- **Vector store**: PostgreSQL + `pgvector` (via Docker Compose)
- **API**: FastAPI with bearer-token auth, CORS allow-list, audit logging
- **Ingestion**: Pulls pages from Confluence Cloud, sanitizes HTML, chunks, embeds, upserts

> This is an MVP. It is intentionally small so it is easy to read and harden.

## Project layout

```
.
├── app/
│   ├── main.py              # FastAPI app, /ask endpoint
│   ├── config.py            # Pydantic settings
│   ├── security.py          # Bearer-token auth (constant-time compare)
│   ├── schemas.py           # Request / response models
│   ├── db.py                # asyncpg pool + pgvector codec
│   ├── embeddings.py        # GitHub Models embeddings
│   ├── llm.py               # GitHub Models chat completion (grounded prompt)
│   ├── retriever.py         # pgvector cosine search
│   └── ingestion/
│       ├── chunking.py      # HTML sanitization + character-window chunker
│       └── run.py           # Confluence -> chunks -> embeddings -> Postgres
├── docker-compose.yml       # pgvector/postgres
├── init.sql                 # Schema + vector index
├── Dockerfile               # API container (non-root)
├── requirements.txt
└── .env.example
```

## Prerequisites
- Python 3.11+
- Docker Desktop
- A GitHub fine-grained PAT with **Models: read** access (set as `GITHUB_TOKEN`)
- A Confluence Cloud API token

## Setup

```powershell
copy .env.example .env
# Edit .env and fill in GITHUB_TOKEN, CONFLUENCE_*, API_KEYS
```

Generate a strong API key for the `/ask` endpoint:
```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```
Put it in `API_KEYS` (comma-separated if you want multiple).

## Run

```powershell
# 1) Start Postgres + pgvector
docker compose up -d

# 2) Install Python deps
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 3) Ingest your spaces (reads CONFLUENCE_SPACES from .env)
python -m app.ingestion.run

# 4) Start the API
uvicorn app.main:app --reload --port 8000
```

## Use

```powershell
$token = "<your API_KEYS value>"
curl -Method POST http://localhost:8000/ask `
  -Headers @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" } `
  -Body '{"question":"What is our incident response process?","filters":{"spaces":["ENG"]}}'
```

Response:
```json
{
  "answer": "…grounded answer with [1] inline citations…",
  "citations": [
    { "title": "Incident Response Runbook",
      "url": "https://your-org.atlassian.net/wiki/...",
      "page_id": "12345",
      "score": 0.81 }
  ]
}
```

## Security notes (MVP)

- **Auth**: All `/ask` calls require `Authorization: Bearer <token>` matching one of `API_KEYS`. Tokens are compared with `hmac.compare_digest` (constant-time).
- **CORS**: `CORS_ORIGINS` is an allow-list of exact origins; no wildcard.
- **Input validation**: Pydantic models enforce types, length, and a strict character set on `space` filters.
- **SQL**: All queries use parameterized `asyncpg` calls — no string interpolation.
- **HTML sanitization**: Confluence storage HTML is stripped with `bleach` before parsing.
- **Prompt hardening**: System prompt instructs the model to treat retrieved text as untrusted data and to refuse when context is insufficient. Per-chunk content is truncated to bound prompt size.
- **Secrets**: Loaded from environment / `.env`; `.env` is git-ignored. For production, mount secrets from your secret manager (Vault / AWS SM / Azure KV).
- **Container**: Runs as a non-root user.
- **Audit log**: Each question + returned citations is recorded in `audit_log`. The token itself is never stored — only a short prefix identifier.

### Not included (deliberately, for the MVP)
Permission-aware Confluence retrieval, OAuth 3LO, rate limiting, PII redaction, hybrid BM25, reranker, webhooks, evaluation harness. The architecture in the original spec describes how to add these.

## Configuration reference
See [.env.example](.env.example). Key knobs:
- `LLM_MODEL` (default `openai/gpt-4o-mini`)
- `EMBEDDING_MODEL` / `EMBEDDING_DIM` (must match the `vector(N)` size in [init.sql](init.sql))
- `TOP_K`, `MAX_QUESTION_CHARS`

If you change `EMBEDDING_DIM`, drop the `chunks` table and re-run `init.sql`, then re-ingest.

## License
MIT
