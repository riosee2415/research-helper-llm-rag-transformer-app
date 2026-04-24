"""Ingest pipeline: load → split → embed → upload to Pinecone."""

import logging
import os
import time
from pathlib import Path

from langchain_openai import OpenAIEmbeddings
from pinecone import Pinecone

import config
from config import (
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_MODEL,
    OPENAI_API_KEY,
    PINECONE_API_KEY,
    PINECONE_INDEX_NAME,
    RETRY_BASE_DELAY,
    RETRY_MAX_ATTEMPTS,
)
from src.ingest.loader import load_all_pdfs
from src.ingest.splitter import split_documents

logger = logging.getLogger(__name__)


class RetryExhaustedError(Exception):
    """Raised when all retry attempts are exhausted."""


def retry_with_backoff(fn, *args, **kwargs):
    """
    Call fn(*args, **kwargs) with exponential backoff on transient errors.

    Retryable: openai.RateLimitError, openai.APITimeoutError, openai.InternalServerError
    Non-retryable: openai.AuthenticationError, openai.PermissionDeniedError,
                   openai.APIConnectionError, all other exceptions

    Raises RetryExhaustedError after RETRY_MAX_ATTEMPTS failures on retryable errors.
    Re-raises immediately for non-retryable errors.
    """
    import openai

    retryable = (openai.RateLimitError, openai.APITimeoutError, openai.InternalServerError)
    non_retryable = (openai.AuthenticationError, openai.PermissionDeniedError, openai.APIConnectionError)

    last_exc = None
    for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
        try:
            return fn(*args, **kwargs)
        except non_retryable as e:
            logger.error("Non-retryable OpenAI error: %s", e)
            raise
        except retryable as e:
            delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
            logger.warning(
                "Retryable error (attempt %d/%d): %s — retrying in %.0fs",
                attempt,
                RETRY_MAX_ATTEMPTS,
                e,
                delay,
            )
            last_exc = e
            if attempt < RETRY_MAX_ATTEMPTS:
                time.sleep(delay)
    raise RetryExhaustedError(
        f"OpenAI API {RETRY_MAX_ATTEMPTS}회 재시도 후 실패: {last_exc}"
    ) from last_exc


def get_pinecone_index():
    """Return an initialised Pinecone Index object."""
    pc = Pinecone(api_key=PINECONE_API_KEY)
    return pc.Index(PINECONE_INDEX_NAME)


def get_existing_hashes(index) -> set[str]:
    """
    Query Pinecone to get all file_hash values already stored in the index.

    Returns a set of hash strings. Returns empty set on query failure (logs error).
    """
    try:
        stats = index.describe_index_stats()
        total = stats.get("total_vector_count", 0)
        if total == 0:
            return set()

        # Fetch a sample to discover hashes — Pinecone doesn't support list-all-metadata
        # We query with a zero vector and large top_k to collect known hashes
        # Use namespace="" (default) and filter-free query
        dummy = [0.0] * config.EMBEDDING_DIM
        result = index.query(vector=dummy, top_k=min(total, 10000), include_metadata=True)
        hashes = {
            match["metadata"]["file_hash"]
            for match in result.get("matches", [])
            if "file_hash" in match.get("metadata", {})
        }
        logger.debug("Found %d existing hashes in Pinecone", len(hashes))
        return hashes
    except Exception as e:
        logger.error("Pinecone 해시 조회 실패 (E-I-14): %s", e)
        return set()


def embed_and_upload(chunks: list, index, embeddings: OpenAIEmbeddings) -> int:
    """
    Embed chunks and upsert into Pinecone in batches.

    Vector ID format: {file_hash}_{chunk_index:06d}
    Returns number of vectors successfully upserted.
    """
    total_upserted = 0

    for batch_start in range(0, len(chunks), EMBEDDING_BATCH_SIZE):
        batch = chunks[batch_start : batch_start + EMBEDDING_BATCH_SIZE]
        texts = [c.page_content for c in batch]

        try:
            vectors_emb = retry_with_backoff(embeddings.embed_documents, texts)
        except RetryExhaustedError:
            logger.error(
                "임베딩 실패 (E-I-08): batch %d-%d",
                batch_start,
                batch_start + len(batch),
            )
            raise

        records = []
        for chunk, emb in zip(batch, vectors_emb):
            meta = chunk.metadata
            file_hash = meta["file_hash"]
            chunk_idx = meta["chunk_index"]
            vector_id = f"{file_hash}_{chunk_idx:06d}"
            records.append(
                {
                    "id": vector_id,
                    "values": emb,
                    "metadata": {
                        "source": meta.get("source", ""),
                        "file_hash": file_hash,
                        "page": meta.get("page", 0),
                        "chunk_index": chunk_idx,
                        "text": chunk.page_content,
                        "char_count": meta.get("char_count", len(chunk.page_content)),
                    },
                }
            )

        try:
            index.upsert(vectors=records)
            total_upserted += len(records)
            logger.debug("Upserted batch %d-%d", batch_start, batch_start + len(batch))
        except Exception as e:
            logger.error("Pinecone upsert 실패 (E-I-12): %s", e)
            raise RuntimeError(f"Pinecone upsert 실패: {e}") from e

    return total_upserted


def run_pipeline(dir_path: str) -> dict:
    """
    Full ingest pipeline.

    Returns IngestReport:
        {processed: int, skipped: int, failed: list[str], total_chunks: int}
    """
    config.validate_env()
    report = {"processed": 0, "skipped": 0, "failed": [], "total_chunks": 0}

    dir_path = str(Path(dir_path).resolve())
    if not os.path.isdir(dir_path):
        raise FileNotFoundError(f"인제스트 디렉토리를 찾을 수 없습니다 (E-I-01): {dir_path}")

    # Load PDFs
    docs, failed = load_all_pdfs(dir_path)
    report["failed"] = failed

    if not docs and not failed:
        logger.warning("PDF 파일 없음 (E-I-02): %s", dir_path)
        return report

    if not docs:
        logger.error("로드 가능한 PDF 없음 — 모두 실패: %s", failed)
        return report

    # Split
    chunks = split_documents(docs)
    if not chunks:
        logger.warning("청크 생성 결과 없음 (E-I-07)")
        return report

    # Pinecone setup
    index = get_pinecone_index()
    existing_hashes = get_existing_hashes(index)

    # Group chunks by file_hash
    from collections import defaultdict

    by_hash: dict[str, list] = defaultdict(list)
    for chunk in chunks:
        by_hash[chunk.metadata["file_hash"]].append(chunk)

    embeddings = OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        openai_api_key=OPENAI_API_KEY,
    )

    for file_hash, file_chunks in by_hash.items():
        source = file_chunks[0].metadata.get("source", file_hash)
        if file_hash in existing_hashes:
            logger.info("Skip (already indexed): %s", source)
            report["skipped"] += 1
            continue

        try:
            n = embed_and_upload(file_chunks, index, embeddings)
            report["processed"] += 1
            report["total_chunks"] += n
            logger.info("Ingested %s → %d chunks", source, n)
        except Exception as e:
            logger.error("파일 인제스트 실패: %s — %s", source, e)
            report["failed"].append(source)

    return report
