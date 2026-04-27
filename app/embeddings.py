from typing import List

from openai import AsyncOpenAI

from app.config import get_settings


def _client() -> AsyncOpenAI:
    settings = get_settings()
    return AsyncOpenAI(
        base_url=settings.github_models_base_url,
        api_key=settings.github_token,
    )


async def embed_texts(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    settings = get_settings()
    client = _client()
    # Batch in modest chunks to stay within request limits.
    out: List[List[float]] = []
    batch_size = 64
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        resp = await client.embeddings.create(
            model=settings.embedding_model,
            input=batch,
        )
        out.extend([d.embedding for d in resp.data])
    return out


async def embed_query(text: str) -> List[float]:
    vectors = await embed_texts([text])
    return vectors[0]
