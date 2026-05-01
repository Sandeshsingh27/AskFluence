"""Confluence ingestion: fetch pages, chunk, embed, upsert into pgvector."""
import asyncio
import logging
from typing import Iterable

from atlassian import Confluence

from app.config import get_settings
from app.db import get_pool, close_pool
from app.embeddings import EmbeddingsQuotaExceededError, embed_texts
from app.ingestion.chunking import chunk_text, html_to_text

logger = logging.getLogger("askfluence.ingest")
logging.basicConfig(level=logging.INFO)


def _client() -> Confluence:
    settings = get_settings()
    if not settings.confluence_base_url:
        raise RuntimeError("CONFLUENCE_BASE_URL is not configured")

    is_cloud = ".atlassian.net" in settings.confluence_base_url

    # Server/DC + Personal Access Token: pass token=...
    if not is_cloud and settings.confluence_api_token and not settings.confluence_email:
        return Confluence(
            url=settings.confluence_base_url,
            token=settings.confluence_api_token,
            cloud=False,
        )

    # Cloud (email + API token) or Server with username + password.
    if not (settings.confluence_email and settings.confluence_api_token):
        raise RuntimeError("Confluence credentials are not configured")
    return Confluence(
        url=settings.confluence_base_url,
        username=settings.confluence_email,
        password=settings.confluence_api_token,
        cloud=is_cloud,
    )


def _iter_space_pages(client: Confluence, space_key: str) -> Iterable[dict]:
    start = 0
    limit = 50
    while True:
        batch = client.get_all_pages_from_space(
            space=space_key,
            start=start,
            limit=limit,
            expand="body.storage,version",
            status="current",
        )
        if not batch:
            return
        for page in batch:
            yield page
        if len(batch) < limit:
            return
        start += limit


async def _upsert_page(conn, page: dict, base_url: str, chunks_with_vectors):
    page_id = str(page["id"])
    title = page.get("title") or "(untitled)"
    version = int(page.get("version", {}).get("number", 1))
    webui = page.get("_links", {}).get("webui", "")
    url = f"{base_url.rstrip('/')}{webui}" if webui else base_url
    space_key = page.get("space", {}).get("key") or page.get("_expandable", {}).get("space", "").split("/")[-1]

    async with conn.transaction():
        await conn.execute(
            """
            INSERT INTO pages (page_id, space_key, title, url, version, updated_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            ON CONFLICT (page_id) DO UPDATE
              SET space_key = EXCLUDED.space_key,
                  title     = EXCLUDED.title,
                  url       = EXCLUDED.url,
                  version   = EXCLUDED.version,
                  updated_at= NOW()
            """,
            page_id, space_key, title, url, version,
        )
        # Replace chunks atomically.
        await conn.execute("DELETE FROM chunks WHERE page_id = $1", page_id)
        if chunks_with_vectors:
            await conn.executemany(
                """
                INSERT INTO chunks (page_id, chunk_index, content, embedding)
                VALUES ($1, $2, $3, $4)
                """,
                [
                    (page_id, i, content, vector)
                    for i, (content, vector) in enumerate(chunks_with_vectors)
                ],
            )


async def ingest_space(space_key: str) -> int:
    settings = get_settings()
    client = _client()
    pool = await get_pool()

    indexed = 0
    pages = list(_iter_space_pages(client, space_key))
    logger.info("Space %s: fetched %d pages", space_key, len(pages))

    for page in pages:
        page_id = str(page["id"])
        version = int(page.get("version", {}).get("number", 1))

        # Skip pages already indexed at this version (resumable after 429s).
        async with pool.acquire() as conn:
            existing = await conn.fetchval(
                "SELECT version FROM pages WHERE page_id = $1", page_id
            )
            has_chunks = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM chunks WHERE page_id = $1)", page_id
            )
        if existing == version and has_chunks:
            logger.info("Skipping unchanged page %s (v%d)", page_id, version)
            continue

        html = (page.get("body", {}).get("storage", {}) or {}).get("value", "")
        text = html_to_text(html)
        chunks = chunk_text(text)
        if not chunks:
            logger.info("Skipping empty page %s (%s)", page.get("id"), page.get("title"))
            continue

        vectors = await embed_texts(chunks)
        async with pool.acquire() as conn:
            await _upsert_page(
                conn,
                page,
                settings.confluence_base_url,
                list(zip(chunks, vectors)),
            )
        indexed += 1
        logger.info("Indexed page %s (%d chunks)", page.get("id"), len(chunks))

    return indexed


async def main() -> None:
    settings = get_settings()
    if not settings.confluence_spaces:
        raise SystemExit("CONFLUENCE_SPACES is empty")
    try:
        total = 0
        for space in settings.confluence_spaces:
            total += await ingest_space(space)
        logger.info("Done. Indexed %d pages total.", total)
    except EmbeddingsQuotaExceededError as err:
        raise SystemExit(
            f"Ingestion paused due to embeddings quota exhaustion. {err}"
        ) from err
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
