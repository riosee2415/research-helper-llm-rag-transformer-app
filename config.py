"""Project-wide configuration constants and logging setup."""

import logging
import logging.handlers
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- API keys (validated at import) ---
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
PINECONE_API_KEY: str = os.environ.get("PINECONE_API_KEY", "")

# --- Model identifiers ---
LLM_MODEL = "gpt-4o"
EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIM = 3072

# --- Pinecone ---
PINECONE_INDEX_NAME = "resercher-helper"

# --- Ingest ---
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
MIN_CHUNK_SIZE = 100
EMBEDDING_BATCH_SIZE = 100
SCANNED_PDF_MIN_CHARS = 50
CID_OCR_THRESHOLD = 0.3  # (cid:X) 패턴이 추출 텍스트의 30% 이상이면 OCR 경로로 전환

# --- RAG ---
RETRIEVER_TOP_K = 30            # 임베딩 1차 후보 수 — cross-encoder가 최종 품질을 보장하므로 넓게 수집
RETRIEVER_FINAL_K = 7           # cross-encoder 재순위화 후 QA에 전달하는 최종 청크 수
SIMILARITY_THRESHOLD = 0.15     # 의미 유사 문서를 폭넓게 통과시킴 (cross-encoder가 관련성 판별)
LLM_TEMPERATURE = 0.0
MAX_MEMORY_TOKENS = 4000
RERANKER_MODEL = "BAAI/bge-reranker-base"  # 한국어·다국어 cross-encoder (CJK 특화)

# --- Retry ---
RETRY_MAX_ATTEMPTS = 3
RETRY_BASE_DELAY = 1.0

# --- Session ---
SESSION_DIR = Path(__file__).parent / "data" / "sessions"

# --- Directories ---
RAG_DATA_DIR = Path(__file__).parent / "rag_data"
LOG_DIR = Path(__file__).parent / "logs"


def setup_logging(name: str = "rag") -> logging.Logger:
    """Configure console (INFO+) and rotating file (DEBUG+) handlers."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    fh = logging.handlers.RotatingFileHandler(
        LOG_DIR / "app.log", maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


def validate_env() -> None:
    """Raise EnvironmentError if required API keys are missing."""
    missing = []
    if not OPENAI_API_KEY:
        missing.append("OPENAI_API_KEY")
    if not PINECONE_API_KEY:
        missing.append("PINECONE_API_KEY")
    if missing:
        raise EnvironmentError(
            f"필수 환경 변수가 설정되지 않았습니다: {', '.join(missing)}. "
            ".env 파일을 확인하세요."
        )
