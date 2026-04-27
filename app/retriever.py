from typing import List, Optional

from app.config import get_settings
from app.db import get_pool
from app.embeddings import embed_query


async def retrieve(
    question: str,
    spaces: Optional[List[str]] = None,
) -> List[dict]:
    settings = get_settings()
    query_vec = await embed_query(question)

    pool = await get_pool()
    async with pool.acquire() as conn:
        if spaces:
            rows = await conn.fetch(
                """
                SELECT c.content,
                       p.page_id,
                       p.title,
                       p.url,
                       1 - (c.embedding <=> $1) AS score
                FROM chunks c
                JOIN pages  p ON p.page_id = c.page_id
                WHERE p.space_key = ANY($2::text[])
                ORDER BY c.embedding <=> $1
                LIMIT $3
                """,
                query_vec,
                spaces,
                settings.top_k,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT c.content,
                       p.page_id,
                       p.title,
                       p.url,
                       1 - (c.embedding <=> $1) AS score
                FROM chunks c
                JOIN pages  p ON p.page_id = c.page_id
                ORDER BY c.embedding <=> $1
                LIMIT $2
                """,
                query_vec,
                settings.top_k,
            )

    return [dict(r) for r in rows]
