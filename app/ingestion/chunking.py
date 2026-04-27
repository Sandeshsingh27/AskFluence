from typing import List

import bleach
from bs4 import BeautifulSoup


def html_to_text(html: str) -> str:
    # Strip all tags/attrs (defense-in-depth) then extract clean text.
    cleaned = bleach.clean(html or "", tags=[], attributes={}, strip=True)
    text = BeautifulSoup(cleaned, "html.parser").get_text(" ")
    return " ".join(text.split())


def chunk_text(text: str, chunk_chars: int = 1200, overlap: int = 150) -> List[str]:
    if not text:
        return []
    if chunk_chars <= 0:
        raise ValueError("chunk_chars must be positive")
    if overlap < 0 or overlap >= chunk_chars:
        raise ValueError("overlap must be in [0, chunk_chars)")

    chunks: List[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_chars, n)
        chunks.append(text[start:end])
        if end == n:
            break
        start = end - overlap
    return chunks
