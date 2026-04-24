"""Tests for the RAG engine modules."""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document


# ── chains tests ──────────────────────────────────────────────────────────────

class TestFormatContext:
    def test_empty_list_returns_empty_string(self):
        from src.rag.chains import format_context
        assert format_context([]) == ""

    def test_single_doc_has_header(self):
        from src.rag.chains import format_context
        doc = Document(
            page_content="Some content",
            metadata={"source": "paper.pdf", "page": 3},
        )
        result = format_context([doc])
        assert "[paper.pdf, p.3]" in result
        assert "Some content" in result

    def test_multiple_docs_separated_by_divider(self):
        from src.rag.chains import format_context
        docs = [
            Document(page_content="A", metadata={"source": "a.pdf", "page": 1}),
            Document(page_content="B", metadata={"source": "b.pdf", "page": 2}),
        ]
        result = format_context(docs)
        assert "---" in result
        assert "[a.pdf, p.1]" in result
        assert "[b.pdf, p.2]" in result

    def test_missing_metadata_uses_defaults(self):
        from src.rag.chains import format_context
        doc = Document(page_content="text", metadata={})
        result = format_context([doc])
        assert "알 수 없음" in result
        assert "?" in result


class TestBuildChains:
    def test_condense_template_has_required_variables(self):
        from src.rag.chains import CONDENSE_QUESTION_TEMPLATE
        assert "{chat_history}" in CONDENSE_QUESTION_TEMPLATE
        assert "{question}" in CONDENSE_QUESTION_TEMPLATE

    def test_qa_template_has_required_variables(self):
        from src.rag.chains import QA_SYSTEM_TEMPLATE
        assert "{context}" in QA_SYSTEM_TEMPLATE
        assert "{question}" in QA_SYSTEM_TEMPLATE

    def test_qa_template_allows_partial_answer(self):
        """QA 프롬프트가 부분 관련 컨텍스트에도 답변하도록 지시하는지 확인."""
        from src.rag.chains import QA_SYSTEM_TEMPLATE
        # 부분 관련 시 답변 허용 규칙이 있어야 함
        assert "일부에만 관련" in QA_SYSTEM_TEMPLATE or "관련된 내용에 대해서는" in QA_SYSTEM_TEMPLATE
        # 완전 무관 시에만 찾을 수 없습니다 반환
        assert "완전히 무관" in QA_SYSTEM_TEMPLATE

    def test_condense_chain_builds_without_error(self):
        from langchain_openai import ChatOpenAI
        from unittest.mock import create_autospec
        from src.rag.chains import build_condense_chain
        mock_llm = create_autospec(ChatOpenAI, instance=True)
        chain = build_condense_chain(mock_llm)
        assert chain is not None

    def test_qa_chain_builds_without_error(self):
        from langchain_openai import ChatOpenAI
        from unittest.mock import create_autospec
        from src.rag.chains import build_qa_chain
        mock_llm = create_autospec(ChatOpenAI, instance=True)
        chain = build_qa_chain(mock_llm)
        assert chain is not None


# ── reranker tests ────────────────────────────────────────────────────────────

class TestReranker:
    def _make_docs(self, n: int) -> list:
        return [
            Document(page_content=f"content {i}", metadata={"source": f"{i}.pdf", "page": i})
            for i in range(n)
        ]

    def test_returns_top_k_when_model_unavailable(self):
        """Reranker 없을 때 원본 순서 상위 top_k 반환."""
        from src.rag import reranker as rr
        original = rr._reranker
        rr._reranker = None
        try:
            with patch("src.rag.reranker._get_reranker", return_value=None):
                from src.rag.reranker import rerank
                docs = self._make_docs(10)
                result = rerank("query", docs, top_k=3)
            assert len(result) == 3
            assert result[0].page_content == "content 0"
        finally:
            rr._reranker = original

    def test_returns_all_when_fewer_than_top_k(self):
        """후보가 top_k보다 적으면 모두 반환."""
        from src.rag.reranker import rerank
        docs = self._make_docs(2)
        result = rerank("query", docs, top_k=5)
        assert len(result) == 2

    def test_returns_empty_for_empty_input(self):
        from src.rag.reranker import rerank
        assert rerank("query", [], top_k=5) == []

    def test_reranks_with_mock_model(self):
        """Mock cross-encoder가 점수를 역순으로 줄 때 순서가 바뀌는지 확인."""
        from src.rag.reranker import rerank
        docs = self._make_docs(3)
        mock_model = MagicMock()
        # 역순 점수: doc2=0.9, doc1=0.5, doc0=0.1
        mock_model.predict.return_value = [0.1, 0.5, 0.9]
        with patch("src.rag.reranker._get_reranker", return_value=mock_model):
            result = rerank("query", docs, top_k=2)
        assert len(result) == 2
        assert result[0].page_content == "content 2"  # 가장 높은 점수
        assert result[1].page_content == "content 1"


# ── retriever tests ───────────────────────────────────────────────────────────

class TestThresholdRetriever:
    def _make_retriever(self, results):
        from src.rag.retriever import ThresholdRetriever
        mock_vs = MagicMock()
        mock_vs.similarity_search_with_score.return_value = results
        return ThresholdRetriever(vectorstore=mock_vs, k=5, threshold=0.7)

    def test_filters_below_threshold(self):
        doc_high = Document(page_content="high", metadata={"source": "a.pdf", "page": 1})
        doc_low = Document(page_content="low", metadata={"source": "b.pdf", "page": 1})
        retriever = self._make_retriever([(doc_high, 0.9), (doc_low, 0.5)])
        result = retriever._get_relevant_documents("test query")
        assert len(result) == 1
        assert result[0].page_content == "high"

    def test_returns_empty_list_when_no_results_above_threshold(self):
        doc = Document(page_content="low", metadata={})
        retriever = self._make_retriever([(doc, 0.3)])
        result = retriever._get_relevant_documents("test query")
        assert result == []

    def test_raises_runtime_error_on_query_failure(self):
        from src.rag.retriever import ThresholdRetriever
        mock_vs = MagicMock()
        mock_vs.similarity_search_with_score.side_effect = Exception("connection error")
        retriever = ThresholdRetriever(vectorstore=mock_vs)
        with pytest.raises(RuntimeError, match="벡터 검색 실패"):
            retriever._get_relevant_documents("query")


# ── engine tests ──────────────────────────────────────────────────────────────

class TestRAGEngine:
    def _make_engine(self, retriever_docs=None, condense_text=None, qa_text=None):
        """Return a RAGEngine with all external dependencies mocked."""
        with patch("src.rag.engine.validate_env"), \
             patch("src.rag.engine.ChatOpenAI") as mock_llm_cls, \
             patch("src.rag.engine.get_retriever") as mock_get_retriever, \
             patch("src.rag.engine.rerank", side_effect=lambda q, docs, top_k: docs[:top_k] if docs else []), \
             patch("src.rag.engine.build_condense_chain") as mock_condense, \
             patch("src.rag.engine.build_qa_chain") as mock_qa:

            mock_llm = MagicMock()
            mock_llm_cls.return_value = mock_llm

            mock_retriever = MagicMock()
            mock_retriever.invoke.return_value = retriever_docs or []
            mock_get_retriever.return_value = mock_retriever

            mock_condense_chain = MagicMock()
            mock_condense_chain.invoke.return_value = condense_text or "standalone question"
            mock_condense.return_value = mock_condense_chain

            mock_qa_chain = MagicMock()
            mock_qa_chain.invoke.return_value = qa_text or "답변입니다."
            mock_qa.return_value = mock_qa_chain

            from src.rag.engine import RAGEngine
            engine = RAGEngine()
            return engine

    def test_ask_returns_required_keys(self):
        engine = self._make_engine(
            retriever_docs=[Document(page_content="context", metadata={"source": "a.pdf", "page": 1})],
            qa_text="테스트 답변",
        )
        result = engine.ask("질문은?")
        assert "answer" in result
        assert "source_documents" in result
        assert "standalone_question" in result

    def test_ask_empty_question_returns_prompt(self):
        engine = self._make_engine()
        result = engine.ask("   ")
        assert "질문을 입력해 주세요" in result["answer"]

    def test_ask_no_docs_returns_not_found_message(self):
        engine = self._make_engine(retriever_docs=[])
        result = engine.ask("관련 없는 질문")
        assert "찾을 수 없습니다" in result["answer"]
        assert result["source_documents"] == []

    def test_ask_chain1_failure_falls_back_to_original(self):
        with patch("src.rag.engine.validate_env"), \
             patch("src.rag.engine.ChatOpenAI"), \
             patch("src.rag.engine.get_retriever") as mock_get_retriever, \
             patch("src.rag.engine.rerank", side_effect=lambda q, docs, top_k: docs[:top_k] if docs else []), \
             patch("src.rag.engine.build_condense_chain") as mock_condense, \
             patch("src.rag.engine.build_qa_chain") as mock_qa:

            mock_retriever = MagicMock()
            mock_retriever.invoke.return_value = []
            mock_get_retriever.return_value = mock_retriever

            mock_condense_chain = MagicMock()
            mock_condense_chain.invoke.side_effect = Exception("API error")
            mock_condense.return_value = mock_condense_chain

            mock_qa_chain = MagicMock()
            mock_qa.return_value = mock_qa_chain

            from src.rag.engine import RAGEngine
            engine = RAGEngine()
            result = engine.ask("원본 질문")

        assert result["standalone_question"] == "원본 질문"

    def test_reset_clears_memory(self):
        engine = self._make_engine(
            retriever_docs=[Document(page_content="ctx", metadata={"source": "x.pdf", "page": 1})],
            qa_text="답변",
        )
        engine.ask("첫 번째 질문")
        engine.reset()
        msgs = engine.get_memory_messages()
        assert msgs == []

    def test_get_memory_messages_returns_list(self):
        engine = self._make_engine(
            retriever_docs=[Document(page_content="ctx", metadata={"source": "x.pdf", "page": 1})],
            qa_text="답변",
        )
        engine.ask("질문")
        msgs = engine.get_memory_messages()
        assert isinstance(msgs, list)


# ── session manager tests ──────────────────────────────────────────────────────

class TestSessionManager:
    def test_create_session_returns_valid_id(self, tmp_path):
        from src.ui.session import SessionManager
        sm = SessionManager(session_dir=tmp_path)
        sid = sm.create_session()
        assert len(sid) == 36  # UUID format
        assert (tmp_path / f"{sid}.json").exists()

    def test_save_and_load_message(self, tmp_path):
        from src.ui.session import SessionManager
        sm = SessionManager(session_dir=tmp_path)
        sid = sm.create_session()
        sm.save_message(sid, "user", "안녕하세요")
        data = sm.load_session(sid)
        assert data["messages"][0]["role"] == "user"
        assert data["messages"][0]["content"] == "안녕하세요"

    def test_list_sessions_sorted_by_updated_at(self, tmp_path):
        import json
        from src.ui.session import SessionManager
        sm = SessionManager(session_dir=tmp_path)
        sid1 = sm.create_session()
        sid2 = sm.create_session()
        # Manually set sid2 to a later timestamp to guarantee ordering
        p = tmp_path / f"{sid2}.json"
        data = json.loads(p.read_text())
        data["updated_at"] = "2099-01-01T00:00:00+0900"
        p.write_text(json.dumps(data))
        sessions = sm.list_sessions()
        assert sessions[0]["session_id"] == sid2

    def test_load_session_returns_none_for_missing(self, tmp_path):
        from src.ui.session import SessionManager
        sm = SessionManager(session_dir=tmp_path)
        assert sm.load_session("nonexistent-id") is None

    def test_delete_session_removes_file(self, tmp_path):
        from src.ui.session import SessionManager
        sm = SessionManager(session_dir=tmp_path)
        sid = sm.create_session()
        sm.delete_session(sid)
        assert not (tmp_path / f"{sid}.json").exists()

    def test_rebuild_memory_returns_empty_for_missing_session(self, tmp_path):
        from src.ui.session import SessionManager
        sm = SessionManager(session_dir=tmp_path)
        result = sm.rebuild_memory("missing-id")
        assert result == []

    def test_load_latest_session_returns_none_when_empty(self, tmp_path):
        from src.ui.session import SessionManager
        sm = SessionManager(session_dir=tmp_path)
        assert sm.load_latest_session() is None

    def test_memory_messages_saved_and_rebuilt(self, tmp_path):
        from src.ui.session import SessionManager
        sm = SessionManager(session_dir=tmp_path)
        sid = sm.create_session()
        memory = [{"type": "human", "content": "Q"}, {"type": "ai", "content": "A"}]
        sm.save_message(sid, "user", "Q", memory_messages=memory)
        result = sm.rebuild_memory(sid)
        assert result == memory
