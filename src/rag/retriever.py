"""Pinecone vector store and threshold-filtered retriever."""

import logging
from typing import Any

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone

import config
from config import (
    EMBEDDING_MODEL,
    OPENAI_API_KEY,
    PINECONE_API_KEY,
    PINECONE_INDEX_NAME,
    RETRIEVER_TOP_K,
    SIMILARITY_THRESHOLD,
)

import config

logger = logging.getLogger(__name__)


def get_vectorstore() -> PineconeVectorStore:
    """Return an initialised PineconeVectorStore using text-embedding-3-large."""
    pc = Pinecone(api_key=PINECONE_API_KEY)
    index = pc.Index(PINECONE_INDEX_NAME)
    embeddings = OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        openai_api_key=OPENAI_API_KEY,
    )
    return PineconeVectorStore(index=index, embedding=embeddings, text_key="text")


class ThresholdRetriever(BaseRetriever):
    """
    Retriever that filters out results below SIMILARITY_THRESHOLD.

    Wraps PineconeVectorStore.similarity_search_with_score() and returns
    only Documents whose cosine similarity score >= SIMILARITY_THRESHOLD.
    Returns an empty list (not an error) when no documents pass the threshold.
    """

    model_config = {"arbitrary_types_allowed": True}

    vectorstore: Any
    k: int = RETRIEVER_TOP_K
    threshold: float = SIMILARITY_THRESHOLD

    def _get_relevant_documents(self, query: str) -> list[Document]:
        try:
            results = self.vectorstore.similarity_search_with_score(query, k=self.k)
        except Exception as e:
            logger.error("Pinecone 쿼리 실패 (E-R-07): %s", e)
            raise RuntimeError(f"벡터 검색 실패: {e}") from e

        passed = [(doc, score) for doc, score in results if score >= self.threshold]

        if not passed:
            logger.info(
                "No documents above threshold %.2f for query: %.80s",
                self.threshold,
                query,
            )
            return []

        # 검색 점수를 메타데이터에 저장 (디버깅 및 재순위화 참고용)
        result_docs = []
        for doc, score in passed:
            doc.metadata["_retrieval_score"] = round(float(score), 4)
            result_docs.append(doc)

        logger.debug(
            "Retrieved %d/%d docs above threshold %.2f | scores: %s",
            len(result_docs),
            len(results),
            self.threshold,
            [f"{s:.3f}" for _, s in passed[:5]],
        )
        return result_docs

    async def _aget_relevant_documents(self, query: str) -> list[Document]:
        return self._get_relevant_documents(query)


def get_retriever() -> ThresholdRetriever:
    """Return a ThresholdRetriever backed by the Pinecone vector store."""
    vs = get_vectorstore()
    return ThresholdRetriever(vectorstore=vs, k=RETRIEVER_TOP_K, threshold=SIMILARITY_THRESHOLD)
