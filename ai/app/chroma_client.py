"""ChromaDB client for VASS regulatory vector store (AUT-3631).

Provides semantic search over Australian Design Rules (ADR), VSI bulletins,
VSB6 clauses, and VicRoads guidelines for modification legality checks.

The client is lazy-initialized and fails closed: if ChromaDB is unreachable,
all queries return empty results so the fallback path runs cleanly.

Environment variables:
  CHROMA_HOST  ChromaDB server host (default: localhost)
  CHROMA_PORT  ChromaDB server port (default: 8000)
"""

import os

from app.logging import get_logger

logger = get_logger(__name__)

# Collection name for the VASS regulatory corpus
COLLECTION_NAME = "vass_regulatory"

_client = None


def _chroma_url() -> str:
    host = os.getenv("CHROMA_HOST", "localhost")
    port = os.getenv("CHROMA_PORT", "8000")
    return f"http://{host}:{port}"


def _get_client():
    """Lazy-initialize the ChromaDB HTTP client. Returns None if unreachable."""
    global _client
    if _client is not None:
        return _client
    try:
        import chromadb

        _client = chromadb.HttpClient(host=_chroma_url())
        logger.info("chromadb_connected", url=_chroma_url())
        return _client
    except Exception as exc:
        logger.warning("chromadb_unavailable", error=str(exc))
        _client = None
        return None


def query_regulatory_context(
    text: str,
    n_results: int = 5,
    doc_type: str | None = None,
) -> list[dict]:
    """Query the VASS regulatory corpus for relevant passages.

    Args:
        text: Natural language query (e.g. "aftermarket exhaust noise limits")
        n_results: Maximum number of results to return
        doc_type: Optional filter by document type (adr, vsi, vsb6, vicroads)

    Returns:
        List of dicts with keys: text, source, section, doc_type, distance.
        Empty list if ChromaDB is unavailable or collection is empty.
    """
    client = _get_client()
    if client is None:
        return []

    try:
        collection = client.get_collection(COLLECTION_NAME)
    except Exception:
        # Collection doesn't exist yet or ChromaDB error
        return []

    where_filter = {"doc_type": doc_type} if doc_type else None

    try:
        results = collection.query(
            query_texts=[text],
            n_results=n_results,
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:
        logger.warning("chromadb_query_failed", error=str(exc))
        return []

    if not results or not results.get("documents"):
        return []

    docs = results["documents"][0] if results["documents"] else []
    metas = results["metadatas"][0] if results.get("metadatas") else []
    distances = results["distances"][0] if results.get("distances") else []

    out = []
    for i, doc in enumerate(docs):
        meta = metas[i] if i < len(metas) else {}
        out.append(
            {
                "text": doc,
                "source": meta.get("source", ""),
                "section": meta.get("section", ""),
                "doc_type": meta.get("doc_type", ""),
                "distance": distances[i] if i < len(distances) else None,
            }
        )
    return out


def is_available() -> bool:
    """Check if ChromaDB is reachable and the collection exists."""
    client = _get_client()
    if client is None:
        return False
    try:
        client.get_collection(COLLECTION_NAME)
        return True
    except Exception:
        return False
