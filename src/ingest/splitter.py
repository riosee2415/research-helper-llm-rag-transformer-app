"""Text splitting for ingest pipeline."""

import logging

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import CHUNK_OVERLAP, CHUNK_SIZE, MIN_CHUNK_SIZE

logger = logging.getLogger(__name__)


def split_documents(documents: list[Document]) -> list[Document]:
    """
    Split documents into chunks.

    - Uses RecursiveCharacterTextSplitter (chunk_size=1000, overlap=200).
    - Assigns chunk_index (0-indexed, per source file) and char_count to metadata.
    - Drops chunks shorter than MIN_CHUNK_SIZE.
    - Preserves all existing metadata (source, file_hash, page) from parent document.

    Returns list of chunk Documents with metadata:
        source, file_hash, page, chunk_index, char_count, text (copy of page_content)
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        add_start_index=False,
    )

    chunks = splitter.split_documents(documents)

    # Count per-file chunk indices
    file_chunk_counters: dict[str, int] = {}
    result: list[Document] = []

    for chunk in chunks:
        content = chunk.page_content.strip()
        if len(content) < MIN_CHUNK_SIZE:
            continue

        source = chunk.metadata.get("source", "")
        idx = file_chunk_counters.get(source, 0)
        file_chunk_counters[source] = idx + 1

        new_metadata = dict(chunk.metadata)
        new_metadata["chunk_index"] = idx
        new_metadata["char_count"] = len(content)
        new_metadata["text"] = content

        result.append(Document(page_content=content, metadata=new_metadata))

    logger.info(
        "Split %d documents → %d chunks (dropped %d short)",
        len(documents),
        len(result),
        len(chunks) - len(result),
    )
    return result
