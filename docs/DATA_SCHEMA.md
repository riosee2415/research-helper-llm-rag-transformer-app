# 데이터 스키마

모든 모듈은 이 파일에 정의된 스키마를 정확히 따라야 한다. 필드명, 타입, 인덱스 기준을 임의로 변경하지 마라.

---

## 1. Pinecone 벡터

### Vector ID 형식
```
{file_hash}_{chunk_index:06d}
```
- `file_hash`: 파일 전체의 MD5 해시 (32자 16진수)
- `chunk_index`: 해당 파일 내 청크 순서 (0부터 시작, 6자리 0-패딩)

**예시**: `d41d8cd98f00b204e9800998ecf8427e_000042`

### 메타데이터 필드 (Pinecone upsert 시 metadata dict)

| 필드 | 타입 | 설명 | 예시 |
|------|------|------|------|
| `source` | str | PDF 파일명 (경로 제외, 확장자 포함) | `"KR101742708B1_천연물.pdf"` |
| `file_hash` | str | 파일 전체 MD5 해시 (32자) | `"d41d8cd98f00b204e980..."` |
| `page` | int | PDF 페이지 번호 **(1-indexed)** | `3` |
| `chunk_index` | int | 파일 내 청크 순서 **(0-indexed)** | `42` |
| `text` | str | 청크 원문 텍스트 (strip() 처리됨) | `"코팅 조성물은..."` |
| `char_count` | int | 청크 실제 글자 수 | `987` |

### 벡터 차원 및 유사도
- 모델: `text-embedding-3-large`
- 차원: `3072` (float32)
- 유사도 방식: cosine similarity (Pinecone 인덱스 metric 설정과 일치해야 함)

### 유사도 임계값 적용
```
score >= SIMILARITY_THRESHOLD(0.7) → 결과 사용
score <  SIMILARITY_THRESHOLD(0.7) → 해당 청크 제외
```
임계값 미달 결과만 있으면 빈 리스트 반환 → "관련 내용 없음" 처리.

---

## 2. LangChain Document 구조

`loader.py`와 `splitter.py`에서 생성·유지해야 하는 Document 형식:

```python
from langchain.schema import Document

Document(
    page_content="청크 텍스트 (strip()된 상태, char_count >= MIN_CHUNK_SIZE)",
    metadata={
        "source": "filename.pdf",       # str, 파일명만 (경로 제외)
        "file_hash": "md5hexstring",    # str, 32자
        "page": 3,                      # int, 1-indexed
        "chunk_index": 42,              # int, 0-indexed (splitter에서 추가)
        "char_count": 987,              # int (splitter에서 추가)
    }
)
```

**주의사항**:
- `source`는 파일명만 포함 (예: `os.path.basename(path)`)
- `page_content`는 반드시 `strip()` 처리된 상태
- `char_count`는 `len(page_content)` (strip 후)
- `page`: loader.py에서 pdfplumber 페이지 인덱스+1로 설정 (0-indexed → 1-indexed)
- `chunk_index`: splitter.py에서 파일별로 0부터 재할당

---

## 3. RAGEngine.ask() 반환 타입

```python
def ask(self, question: str) -> dict:
    """
    반환 형식:
    {
        "answer": str,                      # 한국어 답변 텍스트
        "source_documents": list[Document], # 검색에 사용된 청크 (0~5개)
        "standalone_question": str,         # Chain-1 응축 결과 (디버깅용)
    }
    """
```

- `source_documents`가 빈 리스트이면 UI에서 출처 expander 표시 안 함
- `answer`가 "제공된 문서에서 관련 내용을 찾을 수 없습니다." 이면 `source_documents`는 반드시 `[]`

---

## 4. IngestReport 구조

`ingest.py` 실행 결과로 반환되는 dict:

```python
{
    "processed": int,       # 성공적으로 인제스트된 파일 수
    "skipped": int,         # 해시 일치로 건너뛴 파일 수
    "failed": list[str],    # 실패·경고 파일명 목록 (스캔본, 손상, 빈 파일 등)
    "total_chunks": int,    # 이번 실행에서 업로드된 총 벡터 수
}
```

---

## 5. Streamlit session_state

```python
st.session_state.messages: list[dict]
# 형식: [{"role": "user" | "assistant", "content": str}, ...]
# assistant content는 순수 텍스트 답변 (출처 별도 표시)

st.session_state.last_sources: list[Document]
# 마지막 ask() 호출의 source_documents
# 빈 리스트 가능 (검색 결과 없을 때)
# 초기값: []

st.session_state.engine_ready: bool
# RAGEngine 초기화 완료 여부
# False이면 st.chat_input 표시 안 함
# 초기값: False
```

---

## 6. 세션 파일 스키마 (로컬 영속화)

세션 파일은 `data/sessions/` 폴더에 저장된다.

### 파일명 형식
```
{YYYYMMDD_HHMMSS}_{session_id[:8]}.json
```
예: `20260424_153022_a1b2c3d4.json`

### 세션 파일 구조
```python
{
    "session_id": "uuid4 문자열",          # 세션 고유 ID
    "created_at": "ISO8601 문자열",         # 세션 생성 시각
    "updated_at": "ISO8601 문자열",         # 마지막 업데이트 시각
    "messages": [                           # UI 렌더링용 메시지 목록
        {
            "role": "user" | "assistant",
            "content": "str",
            "timestamp": "ISO8601 문자열",  # 메시지 시각
        },
        ...
    ],
    "memory_messages": [                    # RAGEngine 메모리 재구성용
        {
            "type": "human" | "ai",
            "content": "str",
        },
        ...
    ],
}
```

### 저장 위치 및 관리
- `data/sessions/`: 세션 파일 저장 폴더 (.gitignore에 추가)
- 세션은 삭제하지 않으면 영구 보존
- 앱 시작 시 가장 최근 `updated_at` 세션을 자동 로드
- "대화 초기화" 버튼: 현재 세션 파일 삭제 + 새 세션 ID 생성

### SessionManager 인터페이스 (src/ui/session.py)
```python
class SessionManager:
    def __init__(self, sessions_dir: str = "data/sessions") -> None: ...

    def create_session(self) -> str:
        """새 세션 ID(uuid4) 생성 및 파일 초기화. 세션 ID 반환."""

    def save_message(self, session_id: str, role: str, content: str) -> None:
        """메시지 1개를 세션 파일에 추가. 실패 시 경고 로그만 (E-S-02)."""

    def load_latest_session(self) -> dict | None:
        """가장 최근 세션 파일 로드. 없거나 실패 시 None 반환 (E-S-01)."""

    def list_sessions(self) -> list[dict]:
        """모든 세션 메타정보 목록. [{session_id, created_at, message_count}, ...]"""

    def delete_session(self, session_id: str) -> None:
        """세션 파일 삭제."""

    def rebuild_memory(self, session_data: dict) -> list[dict]:
        """
        저장된 session_data에서 RAGEngine 메모리 재구성용 메시지 추출.
        반환: memory_messages 리스트
        """
```

---

## 7. config.py 상수 전체 목록

```python
import os
from dotenv import load_dotenv

load_dotenv()

# [API Keys] — .env에서 로딩, 없으면 즉시 에러
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY") or _raise("OPENAI_API_KEY")
PINECONE_API_KEY: str = os.getenv("PINECONE_API_KEY") or _raise("PINECONE_API_KEY")

# [Pinecone]
PINECONE_INDEX_NAME: str = "resercher-helper"
PINECONE_NAMESPACE: str = ""                    # default namespace

# [Embedding]
EMBEDDING_MODEL: str = "text-embedding-3-large"
EMBEDDING_DIM: int = 3072
EMBEDDING_BATCH_SIZE: int = 100                 # API 호출당 최대 청크 수

# [LLM]
LLM_MODEL: str = "gpt-4o"
LLM_TEMPERATURE: float = 0.0                    # 결정론적 응답
LLM_MAX_TOKENS: int = 2048                      # 최대 응답 토큰

# [Chunking]
CHUNK_SIZE: int = 1000                          # 최대 청크 글자 수
CHUNK_OVERLAP: int = 200                        # 오버랩 글자 수
MIN_CHUNK_SIZE: int = 100                       # 최소 청크 글자 수 (미달 시 제외)

# [Retrieval]
RETRIEVER_K: int = 5                            # 검색 청크 수
SIMILARITY_THRESHOLD: float = 0.7              # 유사도 임계값

# [Retry]
MAX_RETRIES: int = 3                            # 최대 재시도 횟수
RETRY_BASE_DELAY: float = 1.0                   # 초기 대기(초), 2^n 지수 증가
RETRYABLE_STATUS_CODES: set = {429, 500, 502, 503}

# [Memory]
MAX_MEMORY_TOKENS: int = 4000                   # 대화 히스토리 최대 토큰

# [PDF]
SCANNED_PDF_MIN_CHARS: int = 50                 # 스캔본 감지: 총 텍스트 < 이 값

# [Logging]
LOG_DIR: str = "logs"
LOG_FILE: str = "logs/app.log"
LOG_MAX_BYTES: int = 10 * 1024 * 1024           # 10MB
LOG_BACKUP_COUNT: int = 3
```

`_raise` 헬퍼: 환경변수 없을 때 `EnvironmentError` 발생 (E-C-01 참조).
