#!/usr/bin/env python3
"""Ingest VASS regulatory corpus into ChromaDB (AUT-3631).

Loads Australian Design Rules (ADR), VSI bulletins, VSB6 clauses,
and VicRoads guidelines from the corpus directory and indexes them
into the ChromaDB vector store for semantic search.

Usage:
    python -m app.ingest_docs [--corpus-dir PATH] [--collection NAME]
                              [--host HOST] [--port PORT] [--reset]

Environment variables:
    CHROMA_HOST   ChromaDB server host (default: localhost)
    CHROMA_PORT   ChromaDB server port (default: 8000)
"""

import argparse
import hashlib
import os
import sys
from pathlib import Path

import chromadb

# Corpus directory structure:
# corpus/
#   adr/           # Australian Design Rules
#   vsi/           # Vehicle Standards Instructions bulletins
#   vsb6/          # Vehicle Standards Bulletin 6 clauses
#   vicroads/      # VicRoads guidelines

CORPUS_DIR = Path(__file__).parent.parent / "corpus"
COLLECTION_NAME = "vass_regulatory"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150


def _chroma_url() -> str:
    host = os.getenv("CHROMA_HOST", "localhost")
    port = os.getenv("CHROMA_PORT", "8000")
    return f"http://{host}:{port}"


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks."""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        # Try to break at sentence boundary
        if end < len(text):
            last_period = text.rfind(". ", start, end)
            if last_period > start:
                end = last_period + 1
        chunks.append(text[start:end].strip())
        start = end - overlap
        if start >= len(text):
            break
    return [c for c in chunks if c]


def _extract_doc_type(filepath: Path) -> str:
    """Determine document type from path."""
    parts = filepath.relative_to(CORPUS_DIR).parts
    if parts:
        return parts[0].lower()
    return "unknown"


def _generate_id(filepath: Path, chunk_index: int) -> str:
    """Generate deterministic ID for a chunk."""
    key = f"{filepath.relative_to(CORPUS_DIR)}::{chunk_index}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def ingest_corpus(
    corpus_dir: Path,
    collection_name: str = COLLECTION_NAME,
    host: str = "localhost",
    port: int = 8000,
    reset: bool = False,
) -> tuple[int, int]:
    """Ingest all documents in corpus_dir into ChromaDB.

    Returns:
        (num_documents, num_chunks) indexed
    """
    client = chromadb.HttpClient(host=host, port=port)

    if reset:
        try:
            client.delete_collection(collection_name)
            print(f"Deleted existing collection: {collection_name}")
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"description": "VASS regulatory corpus for modification legality checks"},
    )

    total_docs = 0
    total_chunks = 0

    for filepath in sorted(corpus_dir.rglob("*")):
        if not filepath.is_file():
            continue
        if filepath.suffix.lower() not in (".txt", ".md", ".pdf"):
            continue

        try:
            if filepath.suffix.lower() == ".pdf":
                import pypdf

                text = ""
                with filepath.open("rb") as f:
                    reader = pypdf.PdfReader(f)
                    for page in reader.pages:
                        text += page.extract_text() or ""
            else:
                text = filepath.read_text(encoding="utf-8", errors="ignore")

            if not text.strip():
                print(f"  Skipping empty file: {filepath}")
                continue

            doc_type = _extract_doc_type(filepath)
            chunks = _chunk_text(text)

            for i, chunk in enumerate(chunks):
                chunk_id = _generate_id(filepath, i)
                collection.add(
                    documents=[chunk],
                    metadatas=[
                        {
                            "source": str(filepath.relative_to(CORPUS_DIR)),
                            "doc_type": doc_type,
                            "section": filepath.stem,
                            "chunk_index": i,
                        }
                    ],
                    ids=[chunk_id],
                )
                total_chunks += 1

            total_docs += 1
            print(f"  Indexed: {filepath.relative_to(CORPUS_DIR)} ({len(chunks)} chunks)")

        except Exception as exc:
            print(f"  Error indexing {filepath}: {exc}", file=sys.stderr)

    print(f"\nDone. Indexed {total_docs} documents, {total_chunks} chunks into '{collection_name}'.")
    return total_docs, total_chunks


def main():
    parser = argparse.ArgumentParser(description="Ingest VASS regulatory corpus into ChromaDB")
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=CORPUS_DIR,
        help=f"Path to corpus directory (default: {CORPUS_DIR})",
    )
    parser.add_argument(
        "--collection",
        default=COLLECTION_NAME,
        help=f"ChromaDB collection name (default: {COLLECTION_NAME})",
    )
    parser.add_argument("--host", default=os.getenv("CHROMA_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.getenv("CHROMA_PORT", "8000")))
    parser.add_argument("--reset", action="store_true", help="Delete and recreate collection")
    args = parser.parse_args()

    if not args.corpus_dir.exists():
        print(f"Error: Corpus directory not found: {args.corpus_dir}", file=sys.stderr)
        print("Create it and add .txt/.md/.pdf files under adr/, vsi/, vsb6/, vicroads/ subdirectories.")
        sys.exit(1)

    print(f"Connecting to ChromaDB at {args.host}:{args.port}...")
    print(f"Corpus directory: {args.corpus_dir}")
    print(f"Collection: {args.collection}")
    if args.reset:
        print("Reset mode: will delete existing collection")

    ingest_corpus(
        corpus_dir=args.corpus_dir,
        collection_name=args.collection,
        host=args.host,
        port=args.port,
        reset=args.reset,
    )


if __name__ == "__main__":
    main()