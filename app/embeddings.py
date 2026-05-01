import asyncio
import logging
import random
from typing import List

from openai import APIError, AsyncOpenAI, RateLimitError

from app.config import get_settings

logger = logging.getLogger(__name__)


class EmbeddingsQuotaExceededError(RuntimeError):
    """Raised when the embeddings provider indicates quota is exhausted."""

# GitHub Models has tight per-minute and per-day rate limits.
# Keep batches small and pace requests; back off aggressively on 429.
_BATCH_SIZE = 16
_INTER_BATCH_DELAY_SEC = 10.0
_MAX_RETRIES = 6


def _client() -> AsyncOpenAI:
    settings = get_settings()
    return AsyncOpenAI(
        base_url=settings.github_models_base_url,
        api_key=settings.github_token,
        timeout=60.0,
    )


def _retry_after_seconds(err: Exception) -> float | None:
    resp = getattr(err, "response", None)
    if resp is None:
        return None
    headers = getattr(resp, "headers", {}) or {}
    for key in ("retry-after", "Retry-After", "x-ratelimit-reset", "x-ratelimit-timeremaining"):
        val = headers.get(key)
        if val:
            try:
                # Cap retry-after to 60 seconds max
                return min(float(val), 60.0)
            except ValueError:
                continue
    return None


def _raw_retry_after_seconds(err: Exception) -> float | None:
    """Read Retry-After without caps to detect day-level quota exhaustion."""
    resp = getattr(err, "response", None)
    if resp is None:
        return None
    headers = getattr(resp, "headers", {}) or {}
    for key in ("retry-after", "Retry-After"):
        val = headers.get(key)
        if val:
            try:
                return float(val)
            except ValueError:
                continue
    return None


async def _embed_batch(client: AsyncOpenAI, model: str, batch: List[str]) -> List[List[float]]:
    delay = 2.0
    MAX_WAIT = 60.0
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = await client.embeddings.create(model=model, input=batch)
            return [d.embedding for d in resp.data]
        except RateLimitError as err:
            raw_retry_after = _raw_retry_after_seconds(err)
            if raw_retry_after and raw_retry_after >= 900:
                hours = raw_retry_after / 3600
                msg = (
                    f"Embeddings quota exhausted (Retry-After={raw_retry_after:.0f}s, ~{hours:.1f}h). "
                    "Wait for quota reset or use another embedding provider/token."
                )
                logger.error(msg)
                raise EmbeddingsQuotaExceededError(msg) from err

            wait = _retry_after_seconds(err) or delay
            wait += random.uniform(0, 1.0)
            wait = min(wait, MAX_WAIT)
            logger.warning(
                "429 from embeddings API (attempt %d/%d); sleeping %.1fs (capped)",
                attempt, _MAX_RETRIES, wait,
            )
            if attempt == _MAX_RETRIES:
                raise
            await asyncio.sleep(wait)
            delay = min(delay * 2, MAX_WAIT)
        except APIError as err:
            status = getattr(err, "status_code", None)
            if status and 500 <= status < 600 and attempt < _MAX_RETRIES:
                logger.warning("Server error %s from embeddings (attempt %d); retrying in %.1fs",
                               status, attempt, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, MAX_WAIT)
                continue
            raise
    raise RuntimeError("unreachable")


async def embed_texts(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    settings = get_settings()
    client = _client()
    out: List[List[float]] = []
    for i in range(0, len(texts), _BATCH_SIZE):
        batch = texts[i : i + _BATCH_SIZE]
        vectors = await _embed_batch(client, settings.embedding_model, batch)
        out.extend(vectors)
        if i + _BATCH_SIZE < len(texts):
            await asyncio.sleep(_INTER_BATCH_DELAY_SEC)
    return out


async def embed_query(text: str) -> List[float]:
    vectors = await embed_texts([text])
    return vectors[0]
