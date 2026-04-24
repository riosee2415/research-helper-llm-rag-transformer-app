"""Tests for the ingest pipeline modules."""

import hashlib
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document


# ── loader tests ──────────────────────────────────────────────────────────────

class TestComputeFileHash:
    def test_returns_md5_hex(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"hello world")
        from src.ingest.loader import compute_file_hash
        result = compute_file_hash(str(f))
        expected = hashlib.md5(b"hello world").hexdigest()
        assert result == expected

    def test_different_files_different_hashes(self, tmp_path):
        f1 = tmp_path / "a.bin"
        f2 = tmp_path / "b.bin"
        f1.write_bytes(b"content_a")
        f2.write_bytes(b"content_b")
        from src.ingest.loader import compute_file_hash
        assert compute_file_hash(str(f1)) != compute_file_hash(str(f2))


class TestIsScannedPdf:
    def test_scanned_when_total_chars_below_threshold(self):
        from src.ingest.loader import is_scanned_pdf
        page = MagicMock()
        page.extract_text.return_value = "ab"  # 2 chars
        assert is_scanned_pdf([page]) is True

    def test_not_scanned_when_text_above_threshold(self):
        from src.ingest.loader import is_scanned_pdf
        page = MagicMock()
        page.extract_text.return_value = "a" * 100
        assert is_scanned_pdf([page]) is False

    def test_none_text_treated_as_empty(self):
        from src.ingest.loader import is_scanned_pdf
        page = MagicMock()
        page.extract_text.return_value = None
        assert is_scanned_pdf([page]) is True

    def test_cid_encoded_text_triggers_ocr(self):
        """CID 코드 비율 >= 30%이면 OCR 필요로 판정해야 한다."""
        from src.ingest.loader import is_scanned_pdf
        page = MagicMock()
        # "normal text " * 5 = 60자, "(cid:1234) " * 10 = 110자 → cid_count=10, ratio=70/170=41%
        page.extract_text.return_value = "normal text " * 5 + "(cid:1234) " * 10
        assert is_scanned_pdf([page]) is True

    def test_low_cid_ratio_not_treated_as_scanned(self):
        """CID 코드 비율이 낮으면 정상 텍스트 PDF로 판정해야 한다."""
        from src.ingest.loader import is_scanned_pdf
        page = MagicMock()
        # 200자 정상 텍스트 + "(cid:1)" 1개 → ratio = 7/207 ≈ 3%
        page.extract_text.return_value = "a" * 200 + "(cid:1)"
        assert is_scanned_pdf([page]) is False


class TestLoadPdf:
    def test_scanned_pdf_falls_back_to_ocr_and_returns_documents(self, tmp_path):
        """Scanned PDF should go through OCR and return Documents."""
        fake_pdf = tmp_path / "scanned.pdf"
        fake_pdf.write_bytes(b"fake pdf content")

        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = lambda s: s
        mock_pdf.__exit__ = MagicMock(return_value=False)

        with patch("pdfplumber.open", return_value=mock_pdf), \
             patch("src.ingest.loader._ocr_pdf", return_value=[(1, "OCR extracted text content for page one")]):
            from src.ingest.loader import load_pdf
            docs = load_pdf(str(fake_pdf))
        assert len(docs) == 1
        assert docs[0].metadata.get("ocr") is True
        assert "OCR extracted text" in docs[0].page_content

    def test_scanned_pdf_raises_runtime_error_when_ocr_returns_empty(self, tmp_path):
        """Scanned PDF with no OCR output should raise RuntimeError."""
        fake_pdf = tmp_path / "scanned_empty.pdf"
        fake_pdf.write_bytes(b"fake pdf content")

        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = lambda s: s
        mock_pdf.__exit__ = MagicMock(return_value=False)

        with patch("pdfplumber.open", return_value=mock_pdf), \
             patch("src.ingest.loader._ocr_pdf", return_value=[]):
            from src.ingest.loader import load_pdf
            with pytest.raises(RuntimeError, match="OCR 결과 없음"):
                load_pdf(str(fake_pdf))

    def test_returns_documents_with_correct_metadata(self, tmp_path):
        fake_pdf = tmp_path / "paper.pdf"
        fake_pdf.write_bytes(b"fake")

        mock_page = MagicMock()
        mock_page.extract_text.return_value = "This is page text with enough characters to pass threshold " * 2

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = lambda s: s
        mock_pdf.__exit__ = MagicMock(return_value=False)

        with patch("pdfplumber.open", return_value=mock_pdf):
            from src.ingest.loader import load_pdf
            docs = load_pdf(str(fake_pdf))

        assert len(docs) == 1
        assert docs[0].metadata["source"] == "paper.pdf"
        assert docs[0].metadata["page"] == 1
        assert "file_hash" in docs[0].metadata

    def test_raises_runtime_error_on_parse_failure(self, tmp_path):
        fake_pdf = tmp_path / "corrupt.pdf"
        fake_pdf.write_bytes(b"corrupt")

        with patch("pdfplumber.open", side_effect=Exception("parse error")):
            from src.ingest.loader import load_pdf
            with pytest.raises(RuntimeError, match="PDF 파싱 실패"):
                load_pdf(str(fake_pdf))


class TestLoadAllPdfs:
    def test_returns_empty_for_missing_dir(self, tmp_path):
        from src.ingest.loader import load_all_pdfs
        docs, failed = load_all_pdfs(str(tmp_path / "nonexistent"))
        assert docs == []
        assert failed == []

    def test_failed_list_contains_errored_files(self, tmp_path):
        fake_pdf = tmp_path / "bad.pdf"
        fake_pdf.write_bytes(b"fake")

        with patch("src.ingest.loader.load_pdf", side_effect=RuntimeError("err")):
            from src.ingest.loader import load_all_pdfs
            docs, failed = load_all_pdfs(str(tmp_path))

        assert str(fake_pdf) in failed
        assert docs == []


# ── splitter tests ─────────────────────────────────────────────────────────────

class TestSplitDocuments:
    def _make_doc(self, text: str, source: str = "paper.pdf", page: int = 1) -> Document:
        return Document(
            page_content=text,
            metadata={"source": source, "file_hash": "abc123", "page": page},
        )

    def test_chunk_index_is_per_file(self):
        from src.ingest.splitter import split_documents
        long_text = "word " * 300  # ~1500 chars, will produce multiple chunks
        docs = [self._make_doc(long_text, source="a.pdf")]
        chunks = split_documents(docs)
        indices = [c.metadata["chunk_index"] for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_drops_short_chunks(self):
        from src.ingest.splitter import split_documents
        docs = [self._make_doc("x" * 50, source="tiny.pdf")]  # below MIN_CHUNK_SIZE
        chunks = split_documents(docs)
        assert all(len(c.page_content) >= 100 for c in chunks)

    def test_metadata_preserved(self):
        from src.ingest.splitter import split_documents
        docs = [self._make_doc("A " * 200, source="test.pdf", page=3)]
        chunks = split_documents(docs)
        if chunks:
            assert chunks[0].metadata["source"] == "test.pdf"
            assert chunks[0].metadata["file_hash"] == "abc123"
            assert "char_count" in chunks[0].metadata
            assert "text" in chunks[0].metadata

    def test_separate_chunk_counters_per_file(self):
        from src.ingest.splitter import split_documents
        long_text = "word " * 300
        docs = [
            self._make_doc(long_text, source="a.pdf"),
            self._make_doc(long_text, source="b.pdf"),
        ]
        chunks = split_documents(docs)
        a_chunks = [c for c in chunks if c.metadata["source"] == "a.pdf"]
        b_chunks = [c for c in chunks if c.metadata["source"] == "b.pdf"]
        # Each file's chunks start from 0
        assert a_chunks[0].metadata["chunk_index"] == 0
        assert b_chunks[0].metadata["chunk_index"] == 0


# ── pipeline tests (unit — mock external APIs) ────────────────────────────────

class TestRetryWithBackoff:
    def test_returns_on_first_success(self):
        from src.ingest.pipeline import retry_with_backoff
        fn = MagicMock(return_value="ok")
        result = retry_with_backoff(fn)
        assert result == "ok"
        fn.assert_called_once()

    def test_retries_on_rate_limit(self):
        import openai
        from src.ingest.pipeline import retry_with_backoff, RetryExhaustedError
        fn = MagicMock(side_effect=openai.RateLimitError("rate", response=MagicMock(), body={}))
        with patch("time.sleep"):
            with pytest.raises(RetryExhaustedError):
                retry_with_backoff(fn)
        assert fn.call_count == 3

    def test_does_not_retry_auth_error(self):
        import openai
        from src.ingest.pipeline import retry_with_backoff
        fn = MagicMock(side_effect=openai.AuthenticationError("auth", response=MagicMock(), body={}))
        with pytest.raises(openai.AuthenticationError):
            retry_with_backoff(fn)
        fn.assert_called_once()


class TestGetExistingHashes:
    def test_returns_empty_set_when_no_vectors(self):
        from src.ingest.pipeline import get_existing_hashes
        mock_index = MagicMock()
        mock_index.describe_index_stats.return_value = {"total_vector_count": 0}
        result = get_existing_hashes(mock_index)
        assert result == set()

    def test_returns_hashes_from_metadata(self):
        from src.ingest.pipeline import get_existing_hashes
        mock_index = MagicMock()
        mock_index.describe_index_stats.return_value = {"total_vector_count": 2}
        mock_index.query.return_value = {
            "matches": [
                {"id": "hash1_000000", "metadata": {"file_hash": "hash1"}},
                {"id": "hash2_000000", "metadata": {"file_hash": "hash2"}},
            ]
        }
        result = get_existing_hashes(mock_index)
        assert result == {"hash1", "hash2"}

    def test_returns_empty_set_on_query_failure(self):
        from src.ingest.pipeline import get_existing_hashes
        mock_index = MagicMock()
        mock_index.describe_index_stats.side_effect = Exception("connection error")
        result = get_existing_hashes(mock_index)
        assert result == set()
