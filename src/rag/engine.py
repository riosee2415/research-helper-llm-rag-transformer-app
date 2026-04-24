"""RAGEngine: coordinates Chain-1 (condense) + retrieval + Chain-2 (QA)."""

import logging
from typing import Optional

import tiktoken
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI

import config
from config import (
    LLM_MODEL,
    LLM_TEMPERATURE,
    MAX_MEMORY_TOKENS,
    OPENAI_API_KEY,
    validate_env,
)
from src.rag.chains import build_condense_chain, build_qa_chain, format_context
from src.rag.reranker import rerank
from src.rag.retriever import get_retriever

logger = logging.getLogger(__name__)


def _count_tokens(text: str, model: str = LLM_MODEL) -> int:
    """Estimate token count using tiktoken."""
    try:
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


class RAGEngine:
    """
    Stateful RAG engine for a single conversation session.

    Chain-1 condenses follow-up questions; Chain-2 generates expert Korean answers.
    Conversation history is stored as a list of HumanMessage/AIMessage pairs
    and trimmed to MAX_MEMORY_TOKENS on each turn.
    """

    def __init__(self):
        validate_env()
        self._llm = ChatOpenAI(
            model=LLM_MODEL,
            temperature=LLM_TEMPERATURE,
            openai_api_key=OPENAI_API_KEY,
        )
        self._retriever = get_retriever()
        self._condense_chain = build_condense_chain(self._llm)
        self._qa_chain = build_qa_chain(self._llm)
        self._history: list[dict] = []  # [{role: "human"|"ai", content: str}]
        logger.info("RAGEngine initialised")

    def _get_chat_history_str(self) -> str:
        """Return chat history as a plain text string for the condense prompt."""
        if not self._history:
            return ""
        lines = []
        for msg in self._history:
            role = "사용자" if msg["role"] == "human" else "AI"
            lines.append(f"{role}: {msg['content']}")
        return "\n".join(lines)

    def _trim_history(self) -> None:
        """Remove oldest message pairs until history fits within MAX_MEMORY_TOKENS."""
        while len(self._history) >= 2:
            history_str = self._get_chat_history_str()
            if _count_tokens(history_str) <= MAX_MEMORY_TOKENS:
                break
            self._history = self._history[2:]

    def ask(self, question: str) -> dict:
        """
        Process a question through the 2-chain RAG pipeline.

        Returns:
            {
                "answer": str,
                "source_documents": list[Document],
                "standalone_question": str,
            }

        Chain-1 failure falls back to the original question (logs WARNING).
        Empty retrieval returns "제공된 문서에서 해당 내용을 찾을 수 없습니다." without Chain-2 call.
        Raises RuntimeError on Chain-2 failure after retry exhaustion.
        """
        question = question.strip()
        if not question:
            return {
                "answer": "질문을 입력해 주세요.",
                "source_documents": [],
                "standalone_question": question,
            }

        # Chain-1: Condense follow-up into standalone question
        chat_history = self._get_chat_history_str()
        try:
            standalone_question = self._condense_chain.invoke(
                {"chat_history": chat_history, "question": question}
            )
            if isinstance(standalone_question, str):
                standalone_question = standalone_question.strip()
            if not standalone_question:
                standalone_question = question
        except Exception as e:
            logger.warning("Chain-1 실패, 원본 질문 사용: %s — %s", question, e)
            standalone_question = question

        # Retrieval
        try:
            source_docs = self._retriever.invoke(standalone_question)
        except Exception as e:
            logger.error("Retrieval 실패 (E-R-07): %s", e)
            raise RuntimeError(f"벡터 검색 중 오류가 발생했습니다: {e}") from e

        # Cross-encoder reranking: 트랜스포머로 (쿼리, 문서) 쌍 관련성 재평가
        if source_docs:
            source_docs = rerank(
                standalone_question,
                source_docs,
                top_k=config.RETRIEVER_FINAL_K,
            )

        if not source_docs:
            answer = "제공된 문서에서 해당 내용을 찾을 수 없습니다."
            self._history.append({"role": "human", "content": question})
            self._history.append({"role": "ai", "content": answer})
            self._trim_history()
            return {
                "answer": answer,
                "source_documents": [],
                "standalone_question": standalone_question,
            }

        # Chain-2: QA with context
        context = format_context(source_docs)
        try:
            answer = self._qa_chain.invoke(
                {"context": context, "question": standalone_question}
            )
            if isinstance(answer, str):
                answer = answer.strip()
            if not answer:
                answer = "제공된 문서에서 해당 내용을 찾을 수 없습니다."
        except Exception as e:
            logger.error("Chain-2 QA 실패 (E-R-03): %s", e)
            raise RuntimeError(f"답변 생성 중 오류가 발생했습니다: {e}") from e

        # Save to history and trim
        self._history.append({"role": "human", "content": question})
        self._history.append({"role": "ai", "content": answer})
        self._trim_history()

        return {
            "answer": answer,
            "source_documents": source_docs,
            "standalone_question": standalone_question,
        }

    # ── Streaming-friendly split API ─────────────────────────────────────────

    def prepare(self, question: str) -> tuple[list[Document], str]:
        """Phase 1: condense → retrieve → rerank. 히스토리 업데이트 없음.

        Returns (source_docs, standalone_question).
        Empty source_docs means nothing passed the threshold.
        """
        question = question.strip()
        if not question:
            return [], question

        chat_history = self._get_chat_history_str()
        try:
            standalone_question = self._condense_chain.invoke(
                {"chat_history": chat_history, "question": question}
            )
            if isinstance(standalone_question, str):
                standalone_question = standalone_question.strip()
            if not standalone_question:
                standalone_question = question
        except Exception as e:
            logger.warning("Chain-1 실패, 원본 질문 사용: %s — %s", question, e)
            standalone_question = question

        try:
            source_docs = self._retriever.invoke(standalone_question)
        except Exception as e:
            logger.error("Retrieval 실패 (E-R-07): %s", e)
            raise RuntimeError(f"벡터 검색 중 오류가 발생했습니다: {e}") from e

        if source_docs:
            source_docs = rerank(standalone_question, source_docs, top_k=config.RETRIEVER_FINAL_K)

        return source_docs, standalone_question

    def generate_stream(self, standalone_question: str, source_docs: list[Document]):
        """Phase 2: Chain-2 QA 답변을 토큰 단위로 스트리밍.

        Yields str chunks. Errors yield an error message chunk.
        """
        context = format_context(source_docs)
        try:
            for chunk in self._qa_chain.stream({"context": context, "question": standalone_question}):
                yield chunk
        except Exception as e:
            logger.error("Chain-2 QA 스트림 실패 (E-R-03): %s", e)
            yield "\n\n⚠️ 답변 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."

    def update_history(self, question: str, answer: str) -> None:
        """대화 히스토리에 한 턴을 추가하고 토큰 한도 내로 트리밍."""
        self._history.append({"role": "human", "content": question})
        self._history.append({"role": "ai", "content": answer})
        self._trim_history()

    def reset(self) -> None:
        """Clear conversation history for this session."""
        self._history = []
        logger.info("RAGEngine memory reset")

    def get_memory_messages(self) -> list[dict]:
        """Return history as a serialisable list for session persistence."""
        return list(self._history)

    def load_memory_messages(self, messages: list[dict]) -> None:
        """Restore history from a previously serialised message list."""
        self._history = []
        for msg in messages:
            if isinstance(msg, dict) and "role" in msg and "content" in msg:
                if msg["role"] in ("human", "ai"):
                    self._history.append({"role": msg["role"], "content": msg["content"]})
        logger.debug("Loaded %d memory messages", len(self._history))
