import json
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import close_pool, get_pool
from app.embeddings import EmbeddingsQuotaExceededError
from app.llm import generate_answer
from app.retriever import retrieve
from app.schemas import AskRequest, AskResponse, Citation
from app.security import require_api_key

logger = logging.getLogger("askfluence")
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await get_pool()
    yield
    await close_pool()


settings = get_settings()
app = FastAPI(title="AskFluence", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins or [],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
async def ask(
    payload: AskRequest,
    user_id: str = Depends(require_api_key),
) -> AskResponse:
    if len(payload.question) > settings.max_question_chars:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Question too long",
        )

    spaces = payload.filters.spaces if payload.filters else None
    try:
        chunks = await retrieve(payload.question, spaces=spaces)
        answer = await generate_answer(payload.question, chunks)
    except EmbeddingsQuotaExceededError as err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(err),
        ) from err

    # Deduplicate citations by page_id, preserve order, keep best score.
    seen: dict[str, Citation] = {}
    for c in chunks:
        if c["page_id"] in seen:
            continue
        seen[c["page_id"]] = Citation(
            title=c["title"],
            url=c["url"],
            page_id=c["page_id"],
            score=float(c["score"]),
        )
    citations = list(seen.values())

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO audit_log (user_identifier, question, citations)
            VALUES ($1, $2, $3::jsonb)
            """,
            user_id,
            payload.question,
            json.dumps([c.model_dump() for c in citations]),
        )

    return AskResponse(answer=answer, citations=citations)
