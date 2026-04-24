"""PDF loading with OCR fallback for scanned documents."""

import glob
import hashlib
import logging
import os
import re
from typing import Optional

import pdfplumber
import pypdfium2 as pdfium
from langchain_core.documents import Document

from config import CID_OCR_THRESHOLD, SCANNED_PDF_MIN_CHARS

logger = logging.getLogger(__name__)

# EasyOCR reader — lazy singleton (초기화 비용이 크므로 최초 1회만)
_ocr_reader = None


def _get_ocr_reader():
    """Return a cached EasyOCR Reader (Korean + English), initialised once."""
    global _ocr_reader
    if _ocr_reader is None:
        try:
            import easyocr
            logger.info("EasyOCR Reader 초기화 중 (최초 1회)...")
            _ocr_reader = easyocr.Reader(["ko", "en"], gpu=False, verbose=False)
            logger.info("EasyOCR Reader 준비 완료")
        except ImportError:
            logger.warning("easyocr 미설치 — 스캔 PDF OCR 불가. pip install easyocr 실행 필요")
    return _ocr_reader


def compute_file_hash(path: str) -> str:
    """Return MD5 hex digest of the file at path."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def is_scanned_pdf(pages: list) -> bool:
    """Return True if PDF needs OCR.

    Triggers OCR when:
    - Total extractable text < SCANNED_PDF_MIN_CHARS (image-based scan), or
    - CID font codes comprise >= CID_OCR_THRESHOLD of extracted text
      (broken ToUnicode CMap — common in older Korean PDFs)
    """
    texts = [p.extract_text() or "" for p in pages]
    all_text = "".join(texts)
    total = len(all_text)

    if total < SCANNED_PDF_MIN_CHARS:
        return True

    # Each (cid:X) token occupies ~7 chars but represents one character
    cid_count = len(re.findall(r'\(cid:\d+\)', all_text))
    cid_ratio = (cid_count * 7) / total
    if cid_ratio >= CID_OCR_THRESHOLD:
        logger.debug("CID 폰트 인코딩 감지 (비율=%.1f%%) → OCR 경로로 전환", cid_ratio * 100)
        return True

    return False


def _ocr_pdf(path: str) -> list[tuple[int, str]]:
    """
    Run OCR on every page of a PDF.

    Uses pypdfium2 to render pages at 2x scale (better OCR accuracy),
    then EasyOCR for text extraction.

    Returns list of (page_number_1indexed, text) tuples for pages with content.
    Raises RuntimeError if EasyOCR is not installed.
    """
    import numpy as np

    reader = _get_ocr_reader()
    if reader is None:
        raise RuntimeError(
            "EasyOCR가 설치되지 않아 스캔 PDF를 처리할 수 없습니다. "
            "'pip install easyocr' 를 실행하세요."
        )

    results = []
    try:
        pdf = pdfium.PdfDocument(path)
    except Exception as e:
        raise RuntimeError(f"pypdfium2 PDF 열기 실패: {e}") from e

    for page_num, page in enumerate(pdf, start=1):
        try:
            bitmap = page.render(scale=2.0)
            img_np = np.array(bitmap.to_pil())
            texts = reader.readtext(img_np, detail=0)
            text = "\n".join(t.strip() for t in texts if t.strip())
            if text:
                results.append((page_num, text))
        except Exception as e:
            logger.warning("OCR 페이지 %d 실패: %s", page_num, e)

    return results


def load_pdf(path: str) -> list[Document]:
    """
    Parse a PDF with pdfplumber; fall back to OCR for scanned/image PDFs.

    Each Document has metadata: source (basename), file_hash, page (1-indexed).

    - Text PDF: extracted via pdfplumber (x_tolerance=3, y_tolerance=3)
    - Scanned PDF: rendered via pypdfium2 + EasyOCR (ko+en)
    - Empty pages are skipped in both paths

    Raises RuntimeError if the file cannot be opened or all OCR pages fail.
    """
    file_hash = compute_file_hash(path)
    basename = os.path.basename(path)
    docs: list[Document] = []

    # ── Path 1: text-based PDF via pdfplumber ─────────────────────────────
    try:
        with pdfplumber.open(path) as pdf:
            if not is_scanned_pdf(pdf.pages):
                for page_num, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
                    text = text.strip()
                    if not text:
                        continue
                    docs.append(
                        Document(
                            page_content=text,
                            metadata={
                                "source": basename,
                                "file_hash": file_hash,
                                "page": page_num,
                            },
                        )
                    )
                if docs:
                    logger.info("텍스트 PDF: %d페이지 로드 ← %s", len(docs), basename)
                    return docs
                # 텍스트가 있다고 판단했지만 실제 내용이 없는 경우 → OCR 폴백
                logger.warning("텍스트 PDF이나 내용 없음, OCR 시도: %s", basename)
    except Exception as e:
        raise RuntimeError(f"PDF 파싱 실패: {basename} — {e}") from e

    # ── Path 2: scanned / image-based PDF → OCR ───────────────────────────
    logger.info("스캔 PDF 감지, OCR 시작: %s", basename)
    try:
        ocr_pages = _ocr_pdf(path)
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"OCR 처리 실패: {basename} — {e}") from e

    if not ocr_pages:
        raise RuntimeError(
            f"OCR 결과 없음 — 모든 페이지가 빈 텍스트: {basename}"
        )

    for page_num, text in ocr_pages:
        docs.append(
            Document(
                page_content=text,
                metadata={
                    "source": basename,
                    "file_hash": file_hash,
                    "page": page_num,
                    "ocr": True,
                },
            )
        )

    logger.info("OCR PDF: %d페이지 추출 ← %s", len(docs), basename)
    return docs


def load_all_pdfs(dir_path: str) -> tuple[list[Document], list[str]]:
    """
    Recursively load all PDF files under dir_path (text + OCR fallback).

    Returns:
        (documents, failed_paths) where failed_paths lists files that could not be loaded.
    """
    pattern = os.path.join(dir_path, "**", "*.pdf")
    pdf_paths = glob.glob(pattern, recursive=True)

    # Case-insensitive: also catch .PDF uppercase
    pattern_upper = os.path.join(dir_path, "**", "*.PDF")
    pdf_paths += [p for p in glob.glob(pattern_upper, recursive=True) if p not in pdf_paths]

    if not pdf_paths:
        logger.warning("PDF 파일을 찾을 수 없습니다: %s", dir_path)
        return [], []

    all_docs: list[Document] = []
    failed: list[str] = []

    for path in sorted(pdf_paths):
        try:
            docs = load_pdf(path)
            if not docs:
                logger.warning("빈 PDF (텍스트/OCR 모두 없음): %s", path)
                failed.append(path)
                continue
            all_docs.extend(docs)
        except (ValueError, RuntimeError) as e:
            logger.error("PDF 로드 실패: %s — %s", path, e)
            failed.append(path)

    logger.info(
        "Total: %d documents from %d PDFs (%d failed)",
        len(all_docs),
        len(pdf_paths) - len(failed),
        len(failed),
    )
    return all_docs, failed
