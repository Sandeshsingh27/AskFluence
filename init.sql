CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS pages (
    id           BIGSERIAL PRIMARY KEY,
    page_id      TEXT UNIQUE NOT NULL,
    space_key    TEXT NOT NULL,
    title        TEXT NOT NULL,
    url          TEXT NOT NULL,
    version      INTEGER NOT NULL,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chunks (
    id           BIGSERIAL PRIMARY KEY,
    page_id      TEXT NOT NULL REFERENCES pages(page_id) ON DELETE CASCADE,
    chunk_index  INTEGER NOT NULL,
    content      TEXT NOT NULL,
    embedding    vector(1536) NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (page_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE INDEX IF NOT EXISTS chunks_page_id_idx ON chunks (page_id);

CREATE TABLE IF NOT EXISTS audit_log (
    id              BIGSERIAL PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_identifier TEXT,
    question        TEXT NOT NULL,
    citations       JSONB NOT NULL DEFAULT '[]'::jsonb
);
