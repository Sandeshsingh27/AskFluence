# AskFluence — Minimal Secure Confluence Q&A (FastAPI + pgvector + GitHub Models)

A minimal RAG service that answers questions over your Confluence pages.

- **LLM & embeddings**: [GitHub Models](https://github.com/marketplace/models) (`openai/gpt-4o-mini`, `openai/text-embedding-3-small`)
- **Vector store**: PostgreSQL + `pgvector` (via Docker Compose)
- **Admin UI**: pgAdmin (via Docker Compose, pre-registered server)
- **API**: FastAPI with bearer-token auth, CORS allow-list, audit logging
- **Ingestion**: Pulls pages from Confluence Cloud **or** Server / Data Center (PAT or basic auth), sanitizes HTML, chunks, embeds, upserts

> This is an MVP. It is intentionally small so it is easy to read and harden. See [USAGE.md](USAGE.md) for day-to-day commands.

So basically, AskFluence is a minimal, security-conscious Retrieval-Augmented Generation (RAG) 
service that answers natural-language questions over your Confluence pages.

Built with FastAPI, PostgreSQL + pgvector, and GitHub Models (GPT-4o-mini + 
text-embedding-3-small). Supports both Confluence Cloud (API token) and 
Confluence Server/Data Center (PAT). Includes Docker Compose for Postgres, 
pgvector, and pgAdmin. Features bearer-token auth, CORS allow-list, 
parameterized SQL, HTML sanitization, prompt hardening, and audit logging.

Intentionally minimal — easy to read, easy to harden, easy to extend.

## Project layout

```
.
├── app/
│   ├── main.py              # FastAPI app, /ask endpoint
│   ├── config.py            # Pydantic settings (CSV env parsing)
│   ├── security.py          # Bearer-token auth (constant-time compare)
│   ├── schemas.py           # Request / response models
│   ├── db.py                # asyncpg pool + pgvector codec
│   ├── embeddings.py        # GitHub Models embeddings
│   ├── llm.py               # GitHub Models chat completion (grounded prompt)
│   ├── retriever.py         # pgvector cosine search
│   └── ingestion/
│       ├── chunking.py      # HTML sanitization + character-window chunker
│       └── run.py           # Confluence -> chunks -> embeddings -> Postgres
├── pgadmin/
│   └── servers.json         # pgAdmin server pre-registration
├── docker-compose.yml       # postgres + pgadmin
├── init.sql                 # Schema + vector index (runs on first DB start)
├── Dockerfile               # API container (non-root)
├── requirements.txt
├── .env.example
├── README.md
└── USAGE.md
```

## Prerequisites

- **Python 3.11+** (tested on 3.13)
- **Docker Desktop**
- A **GitHub fine-grained PAT with `Models: read`** scope → `GITHUB_TOKEN`
- Confluence access:
  - Cloud → Atlassian account email + API token, **or**
  - Server / Data Center → Personal Access Token (PAT)

## Setup

### 1. Clone & configure env

```powershell
copy .env.example .env
```

Generate a strong API key for the `/ask` endpoint and put it in `API_KEYS`:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Edit [.env](.env) and fill in at minimum:

```env
# DB (defaults are fine for local dev)
POSTGRES_USER=askfluence
POSTGRES_PASSWORD=changeme
POSTGRES_DB=askfluence
DATABASE_URL=postgresql://askfluence:changeme@localhost:5432/askfluence

# API
API_KEYS=<paste the secrets.token_urlsafe value>
CORS_ORIGINS=http://localhost:3000

# GitHub Models
GITHUB_TOKEN=<your PAT with Models:read>
LLM_MODEL=openai/gpt-4o-mini
EMBEDDING_MODEL=openai/text-embedding-3-small
EMBEDDING_DIM=1536

# Confluence
CONFLUENCE_BASE_URL=https://your-org.atlassian.net/wiki   # Cloud
# CONFLUENCE_BASE_URL=https://confluence.your-org.com     # Server / DC
CONFLUENCE_EMAIL=you@your-org.com    # leave EMPTY to use a PAT (Server/DC)
CONFLUENCE_API_TOKEN=<api token or PAT>
CONFLUENCE_SPACES=ENG,PRODUCT        # space KEYS, comma-separated
```

> **Confluence Server / Data Center**: leave `CONFLUENCE_EMAIL` empty and put your **Personal Access Token** in `CONFLUENCE_API_TOKEN`. The ingester then uses Bearer auth.

### 2. Start infra (Postgres + pgvector + pgAdmin)

```powershell
docker compose up -d
```

- Postgres: `localhost:5432` (DB/user `askfluence`)
- pgAdmin: <http://localhost:5050> (login `admin@admin.com` / `admin`; the AskFluence server is pre-registered)

### 3. Install Python deps

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

`pip-system-certs` is included so HTTPS calls to GitHub Models work behind corporate TLS-intercepting proxies (Zscaler, BlueCoat, etc.). If you still hit `CERTIFICATE_VERIFY_FAILED`, see the **Corporate proxy / TLS** note in [USAGE.md](USAGE.md).

### 4. Ingest your Confluence space(s)

```powershell
python -m app.ingestion.run
```

You should see lines like `INFO:askfluence.ingest:Indexed page <id> (N chunks)`. For large spaces (1000+ pages) this takes a while and consumes embedding quota; start with one small space.

### 5. Start the API

```powershell
uvicorn app.main:app --reload --port 8000
```

Verify:

```powershell
curl.exe http://localhost:8000/health
# {"status":"ok"}
```

### 6. Ask a question

```powershell
$apiKey = "<your API_KEYS value>"
curl.exe -X POST http://localhost:8000/ask `
  -H "Authorization: Bearer $apiKey" `
  -H "Content-Type: application/json" `
  -d '{\"question\":\"What does the team do?\",\"filters\":{\"spaces\":[\"CRS\"]}}'
```

See [USAGE.md](USAGE.md) for more examples (PowerShell, troubleshooting, DB inspection, re-ingest).

## Security notes (MVP)

- **Auth**: All `/ask` calls require `Authorization: Bearer <token>` matching one of `API_KEYS`. Tokens are compared with `hmac.compare_digest` (constant-time).
- **CORS**: `CORS_ORIGINS` is an allow-list of exact origins; no wildcard.
- **Input validation**: Pydantic models enforce types, length, and a strict character set on `space` filters.
- **SQL**: All queries use parameterized `asyncpg` calls — no string interpolation.
- **HTML sanitization**: Confluence storage HTML is stripped with `bleach` before parsing.
- **Prompt hardening**: System prompt instructs the model to treat retrieved text as untrusted data and to refuse when context is insufficient. Per-chunk content is truncated to bound prompt size.
- **Secrets**: Loaded from environment / `.env`; `.env` is git-ignored. For production, mount secrets from your secret manager (Vault / AWS SM / Azure KV).
- **Container**: API container runs as a non-root user.
- **Audit log**: Each question + returned citations is recorded in `audit_log`. The token itself is never stored — only a short prefix identifier.

### Not included (deliberately, for the MVP)

Permission-aware Confluence retrieval, OAuth 3LO, rate limiting, PII redaction, hybrid BM25, reranker, incremental sync via webhooks, evaluation harness, frontend, Slack/Teams bots. The architecture in the original spec describes how to add these.

## Configuration reference

See [.env.example](.env.example). Key knobs:

- `LLM_MODEL` (default `openai/gpt-4o-mini`)
- `EMBEDDING_MODEL` / `EMBEDDING_DIM` — must match the `vector(N)` size in [init.sql](init.sql)
- `TOP_K`, `MAX_QUESTION_CHARS`

If you change `EMBEDDING_DIM`, drop the `chunks` table and re-run [init.sql](init.sql), then re-ingest.

## License

MIT

---

## Appendix — Full vision & target architecture

The sections below describe the **target product** this MVP is a stepping-stone toward. Anything not covered earlier in this README is **not yet implemented**.

### Features

#### Core
- 🔎 **Natural-language Q&A** over one or many Confluence spaces
- 📚 **Cited answers** — every response links back to the source Confluence page(s)
- 🧠 **Hybrid retrieval** (semantic vector search + BM25 keyword search) with a re-ranker for high-precision context
- 🔄 **Incremental sync** — new and updated pages are indexed automatically (webhooks + scheduled jobs)
- 🗂️ **Space, label & page-level filtering** at query time

#### User Experience
- 💬 **Multi-channel access**:
  - Confluence Forge macro (in-page chat widget)
  - Standalone web UI (React / Next.js)
  - Slack & Microsoft Teams bots
- 🧵 **Conversational memory** — supports follow-up questions in the same thread
- 👍 **Feedback loop** — thumbs up/down on answers to continuously improve retrieval quality
- 🌐 **Multi-language** support (model-dependent)

#### Security & Governance
- 🔐 **Permission-aware retrieval** — respects Confluence space and page restrictions per user
- 🪪 **Atlassian OAuth 2.0 / SSO** authentication
- 🛡️ **PII redaction** in logs and prompts
- 🗝️ **Secrets management** via AWS Secrets Manager / Azure Key Vault / HashiCorp Vault
- 📊 **Audit logs** of all queries and returned sources

#### Operations
- 📈 **Observability** with LangSmith / Langfuse / OpenTelemetry
- 🧪 **Evaluation harness** for retrieval & answer quality (RAGAS / TruLens)
- ⚙️ **Configurable** chunking, embedding model, LLM, and vector store via environment variables
- 🐳 **Docker & Kubernetes** ready

### Architecture

```
┌──────────────────┐      ┌────────────────────┐      ┌─────────────────────┐
│  Confluence      │      │  Ingestion Worker  │      │  Vector Store       │
│  (Cloud / DC)    │─API─▶│  - Fetch pages     │─────▶│  (Pinecone/Qdrant/  │
│                  │  &   │  - Clean HTML      │      │   pgvector/Weaviate)│
│                  │ Webhk│  - Chunk           │      │                     │
└──────────────────┘      │  - Embed           │      └──────────┬──────────┘
                          └────────────────────┘                 │
                                                                 │
┌──────────────────┐      ┌────────────────────┐                 │
│  User Interfaces │      │   Backend API      │                 │
│  - Forge macro   │─────▶│   (FastAPI/Node)   │─── retrieve ───┘
│  - Web UI        │      │   /ask endpoint    │
│  - Slack/Teams   │◀─────│                    │◀── rerank ──── Reranker
└──────────────────┘      │                    │
                          │                    │──── prompt ──▶ ┌──────────┐
                          │                    │                │   LLM    │
                          │                    │◀── answer ─────│ (GPT-4o, │
                          │                    │                │ Claude…) │
                          └─────────┬──────────┘                └──────────┘
                                    │
                          ┌─────────▼──────────┐
                          │  Redis (memory)    │
                          │  Postgres (audit)  │
                          │  Langfuse (traces) │
                          └────────────────────┘
```

### Request flow (target)

1. **User** asks a question via Forge macro / web UI / Slack.
2. **Backend** authenticates the user (Atlassian OAuth) and resolves their accessible spaces/pages.
3. **Retriever** runs hybrid search against the vector DB, filtered by the user's permissions.
4. **Re-ranker** reorders the top-K chunks for relevance.
5. **LLM** receives the question + top chunks in a grounded prompt and produces an answer with citations.
6. **Response** is returned with source links; the interaction is logged for evaluation.

### Tech stack (suggested)

| Layer              | Technology |
|--------------------|------------|
| Source system      | Atlassian Confluence (Cloud or Data Center) |
| Ingestion          | Python + `atlassian-python-api`, Celery / Airflow |
| Chunking           | LangChain / LlamaIndex text splitters |
| Embeddings         | OpenAI `text-embedding-3-large`, Azure OpenAI, or `bge-large-en-v1.5` |
| Vector store       | Pinecone / Qdrant / Weaviate / pgvector / Azure AI Search |
| Keyword search     | OpenSearch / Elasticsearch (for hybrid) |
| Re-ranker          | Cohere Rerank / BGE Reranker |
| LLM                | GPT-4o / Claude 3.5 Sonnet / Llama 3.1 / Mistral Large |
| Orchestration      | LangChain / LlamaIndex / Haystack |
| Backend API        | FastAPI (Python) or Express (Node.js) |
| Frontend           | Next.js + React + Tailwind |
| Confluence app     | Atlassian Forge (UI Kit / Custom UI) |
| Chat platforms     | Slack Bolt SDK, Microsoft Bot Framework |
| Auth               | Atlassian OAuth 2.0 (3LO), JWT |
| Memory & cache     | Redis |
| Audit / metadata   | PostgreSQL |
| Observability      | Langfuse / LangSmith, OpenTelemetry, Grafana |
| Evaluation         | RAGAS, TruLens |
| Deployment         | Docker, Kubernetes (EKS/AKS/GKE), Terraform |
| Secrets            | AWS Secrets Manager / Azure Key Vault / Vault |

### Target API

**POST `/ask`**

```json
{
  "question": "What is our incident response process?",
  "conversation_id": "optional-uuid",
  "filters": { "spaces": ["ENG"], "labels": ["runbook"] }
}
```

**Response**

```json
{
  "answer": "Our incident response process has 4 phases…",
  "citations": [
    { "title": "Incident Response Runbook", "url": "https://your-org.atlassian.net/wiki/spaces/ENG/pages/12345" }
  ],
  "conversation_id": "…"
}
```

> The MVP currently supports `question` and `filters.spaces` only. `conversation_id` and `filters.labels` are part of the target schema.

### Evaluation (target)

Run an eval suite against a curated golden set of Q&A pairs:

```bash
python -m eval.run --dataset eval/golden_set.jsonl
```

Tracks: faithfulness, answer relevancy, context precision/recall (via RAGAS).

### Roadmap

- [ ] Hybrid BM25 + semantic retrieval with reranker
- [ ] Permission-aware retrieval (Atlassian OAuth 3LO)
- [ ] Conversational memory (Redis) and follow-up questions
- [ ] Incremental sync via Confluence webhooks
- [ ] Web UI (Next.js + Tailwind)
- [ ] Slack / Microsoft Teams bots
- [ ] Confluence Forge macro
- [ ] Observability (OpenTelemetry / Langfuse)
- [ ] Eval harness (RAGAS golden set)
- [ ] Multimodal support (diagrams, screenshots) via vision LLMs
- [ ] Auto-generated FAQ pages from frequent questions
- [ ] Inline answer suggestions while editing Confluence pages
- [ ] Jira ticket grounding alongside Confluence
- [ ] Fine-tuned domain reranker

### Contributing

PRs welcome. Please open an issue to discuss major changes first.
