# 아키텍처

## 디렉토리 구조

```
llm.rag.for.resercher/
├── app.py                  # Streamlit 진입점
├── ingest.py               # 인제스트 CLI (python ingest.py [--dir rag_data])
├── config.py               # 환경변수 로딩 + 전역 상수 (DATA_SCHEMA.md 참조)
├── requirements.txt
├── logs/                   # 런타임 로그 (.gitignore에 포함)
│   └── app.log
├── src/
│   ├── __init__.py
│   ├── ingest/
│   │   ├── __init__.py
│   │   ├── loader.py       # PDF 파싱 (pdfplumber 기반)
│   │   ├── splitter.py     # 청킹 + 최소 길이 검증
│   │   └── pipeline.py     # 전체 인제스트 파이프라인 오케스트레이션
│   ├── rag/
│   │   ├── __init__.py
│   │   ├── retriever.py    # Pinecone 리트리버 (유사도 임계값 필터링)
│   │   ├── chains.py       # Chain-1(질문 응축) + Chain-2(전문 QA) 빌더
│   │   └── engine.py       # RAGEngine: ask(), reset()
│   └── ui/
│       ├── __init__.py
│       ├── components.py   # Streamlit 컴포넌트 함수
│       └── session.py      # SessionManager: 로컬 세션 영속화
├── data/
│   └── sessions/           # 세션 JSON 파일 (.gitignore에 추가)
├── tests/
│   ├── __init__.py
│   ├── test_ingest.py
│   └── test_rag.py
└── rag_data/
    └── *.pdf
```

---

## 핵심 모듈 함수 시그니처

이 인터페이스를 변경하면 안 된다. 내부 구현은 에이전트 재량이나, 아래 계약을 벗어나지 마라.

### src/ingest/loader.py

```python
def compute_file_hash(path: str) -> str:
    """파일 전체 MD5 해시 반환 (32자 16진수 문자열). 블록 단위 스트리밍."""

def is_scanned_pdf(pages: list) -> bool:
    """전체 페이지 추출 텍스트 합계가 SCANNED_PDF_MIN_CHARS(50) 미만이면 True."""

def load_pdf(path: str) -> list[Document]:
    """
    pdfplumber로 PDF 로딩.
    - 각 페이지: page.extract_text(x_tolerance=3, y_tolerance=3)
    - is_scanned_pdf() True이면 빈 리스트 반환 (호출자가 E-I-05 처리)
    - 페이지별 Document: metadata={source(파일명만), file_hash, page(1-indexed)}
    - pdfplumber 예외 시 예외 전파 (호출자 E-I-04 처리)
    - 개별 페이지 추출 실패는 스킵 (경고 로그), 나머지 계속
    반환: list[Document] (빈 리스트 가능)
    """

def load_all_pdfs(dir_path: str) -> tuple[list[Document], list[str]]:
    """
    dir_path/*.pdf 전체 로딩. 대소문자 무관 (*.pdf, *.PDF 모두 처리).
    반환: (all_docs: list[Document], failed_files: list[str])
    실패 파일은 로그 + failed_files 추가. 전체 중단 없음.
    """
```

### src/ingest/splitter.py

```python
def split_documents(documents: list[Document]) -> list[Document]:
    """
    RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,        # 1000
        chunk_overlap=CHUNK_OVERLAP,  # 200
        separators=["\n\n", "\n", ".", " ", ""],
    )
    - 각 청크에 chunk_index(0-indexed, 파일별 리셋), char_count 메타데이터 추가
    - len(chunk.page_content.strip()) < MIN_CHUNK_SIZE(100) 청크 제외
    - 빈 page_content 청크 제외
    - 원본 Document metadata(source, file_hash, page) 유지
    반환: list[Document] (빈 리스트 가능)
    """
```

### src/ingest/pipeline.py

```python
def get_existing_hashes(index) -> set[str]:
    """
    Pinecone index에서 기존 file_hash 목록 조회 (중복 방지용).
    실패 시 빈 set 반환 + 경고 로그 (E-I-14: 중복 체크 없이 진행).
    """

def embed_and_upload(chunks: list[Document]) -> int:
    """
    OpenAIEmbeddings(EMBEDDING_MODEL)로 배치 임베딩(EMBEDDING_BATCH_SIZE=100) 후 Pinecone upsert.
    - Vector ID: {file_hash}_{chunk_index:06d}
    - metadata: DATA_SCHEMA.md Pinecone 메타데이터 필드 전체 (text 필드 포함)
    - OpenAI 오류 시 retry_with_backoff() 사용 (E-I-08, E-I-09)
    - 배치 upsert 실패 시 해당 배치 1회 재시도 (E-I-13)
    반환: 업로드된 벡터 수 (int)
    """

def run_pipeline(dir_path: str) -> dict:
    """
    전체 인제스트 파이프라인.
    1. 디렉토리 존재 확인 (E-I-01)
    2. PDF 파일 glob (E-I-02)
    3. get_existing_hashes() → 새 파일만 필터링
    4. load_all_pdfs() → 로딩 (E-I-03 ~ E-I-07)
    5. split_documents() → 청킹
    6. embed_and_upload() → 임베딩 + 업로드
    반환: IngestReport dict (DATA_SCHEMA.md 참조)
    """
```

### src/rag/retriever.py

```python
def get_vectorstore() -> PineconeVectorStore:
    """
    PineconeVectorStore(index_name=PINECONE_INDEX_NAME, embedding=OpenAIEmbeddings(...)).
    초기화 실패 시 예외 전파 (E-R-01 처리는 engine.py에서).
    """

def get_retriever() -> VectorStoreRetriever:
    """
    similarity_search_with_score(k=RETRIEVER_K) 기반.
    score < SIMILARITY_THRESHOLD(0.7) 결과 제외 후 Document만 반환.
    반환: VectorStoreRetriever (커스텀 또는 LangChain BaseRetriever 구현체)
    """
```

### src/rag/chains.py

```python
def format_context(docs: list[Document]) -> str:
    """PROMPTS.md의 컨텍스트 조립 형식 정확히 따름."""

def build_condense_chain(llm: ChatOpenAI) -> LLMChain:
    """PROMPTS.md CONDENSE_QUESTION_TEMPLATE 사용. Chain-1."""

def build_qa_chain(llm: ChatOpenAI) -> StuffDocumentsChain:
    """
    PROMPTS.md QA_SYSTEM_TEMPLATE 사용.
    document_variable_name="context", 문서 → format_context() 적용.
    Chain-2.
    """
```

### src/rag/engine.py

```python
class RAGEngine:
    def __init__(self) -> None:
        """
        retriever, condense_chain, qa_chain, memory 초기화.
        ConversationBufferMemory(memory_key="chat_history", return_messages=True, output_key="answer")
        초기화 실패 시 예외 전파 (E-R-01).
        """

    def ask(self, question: str) -> dict:
        """
        DATA_SCHEMA.md ask() 반환 타입 준수.
        1. Chain-1: 질문 응축 (실패 시 E-R-02 fallback: 원본 질문 사용)
        2. retriever: 검색 (빈 결과 → E-R-04: "관련 내용 없음" 즉시 반환)
        3. Chain-2: QA 생성 (실패 시 E-R-03 재시도)
        4. 빈 응답 시 E-R-05 처리
        5. 메모리 저장
        """

    def reset(self) -> None:
        """ConversationBufferMemory 완전 초기화 (chat_history 삭제)."""
```

---

## 2-Chain 데이터 흐름 (정상 경로 + 에러 경로)

```
사용자 질문 (str)
        │
        ▼
[Chain-1: Question Condenser]
ChatOpenAI(model=LLM_MODEL, temperature=0.0)
PromptTemplate(CONDENSE_QUESTION_TEMPLATE) + chat_history
        │
        ├─ OpenAI 오류 → retry_with_backoff(3회)
        │  └─ 소진 → fallback: 원본 question 사용 (경고 로그)
        │
        ▼ standalone_question (str)
[PineconeVectorStore.similarity_search_with_score(k=5)]
score >= 0.7 필터링
        │
        ├─ 빈 결과 → answer="제공된 문서에서 관련 내용을 찾을 수 없습니다."
        │            source_documents=[] → 즉시 반환 (Chain-2 미실행)
        │
        ▼ filtered_docs (list[Document], 1~5개)
[format_context(filtered_docs)]
        │
        ▼ formatted_context (str)
[Chain-2: Expert QA]
ChatOpenAI(model=LLM_MODEL, temperature=0.0)
ChatPromptTemplate(QA_SYSTEM_TEMPLATE)
        │
        ├─ 빈 응답 → 1회 재시도 → 여전히 빈 응답 → "답변 생성 실패"
        ├─ OpenAI 오류 → retry_with_backoff(3회)
        │  └─ 소진 → RetryExhaustedError → UI 에러 메시지
        │
        ▼
{answer: str, source_documents: list[Document], standalone_question: str}
        │
        ▼
ConversationBufferMemory에 저장
(MAX_MEMORY_TOKENS 초과 시 오래된 메시지 트리밍)
```

---

## PDF 파싱 전략 (pdfplumber)

### 선택 이유 (ADR-006 참조)
특허·학술 논문의 다단 레이아웃(2-column IEEE, 특허 청구항)에서 pypdf 대비 컬럼 순서를 더 정확히 복원. MIT 라이선스.

### 스캔본 감지
```python
def is_scanned_pdf(pages) -> bool:
    total = "".join(p.extract_text() or "" for p in pages)
    return len(total.strip()) < SCANNED_PDF_MIN_CHARS  # 50
```

### 페이지별 텍스트 추출
```python
text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
```
- 개별 페이지 추출 실패: 해당 페이지 스킵 (WARNING 로그), 나머지 계속

### 알려진 한계 (MVP 내 허용)
- 복잡한 표: 셀 구조 손실, 텍스트로 평탄화
- 수식: 플레인텍스트 변환 시 수식 의미 일부 손실
- 이미지 내 텍스트: OCR 없음 (MVP 제외)

---

## 청킹 전략

```python
RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,       # 1000자
    chunk_overlap=CHUNK_OVERLAP,  # 200자
    separators=["\n\n", "\n", ".", " ", ""],
)
```

### 청크 유효성 검증
```python
valid = [c for c in raw_chunks if len(c.page_content.strip()) >= MIN_CHUNK_SIZE]  # 100
```
- 100자 미만 청크(머리글, 번호, 짧은 설명 등): 임베딩 품질 저하 → 제외

### chunk_index 할당
- 파일별로 0부터 재시작 (전역 인덱스 아님)
- Vector ID `{file_hash}_{chunk_index:06d}` 고유성은 file_hash + chunk_index 조합으로 보장

---

## 임베딩 배치 처리

레이트 리밋 방지를 위한 배치 처리:

```python
for i in range(0, len(chunks), EMBEDDING_BATCH_SIZE):  # 100
    batch = chunks[i:i + EMBEDDING_BATCH_SIZE]
    # 배치 임베딩 → upsert
```

---

## 에러 처리 원칙

### retry_with_backoff() 유틸리티
`src/ingest/pipeline.py` 또는 공통 util 모듈에 구현:

```python
def retry_with_backoff(func, *args, **kwargs):
    """
    재시도 대상: openai.RateLimitError, openai.APITimeoutError, openai.InternalServerError
    즉시 실패: openai.AuthenticationError, openai.PermissionDeniedError, openai.APIConnectionError
    대기: RETRY_BASE_DELAY * (2 ** attempt) → 1s, 2s, 4s
    소진 시: RetryExhaustedError (커스텀 예외) 발생
    """
```

### 에러 격리 원칙
- **인제스트**: 파일 단위 격리. 파일 실패 → 로그 + failed_files 추가, 다음 파일로.
- **RAG**: 질문 단위 격리. 질문 실패 → UI 에러 메시지, 세션 유지.
- **치명적 오류** (API 키 무효, 인덱스 없음): 즉시 종료 또는 UI 입력 비활성화.

모든 에러 케이스의 정확한 동작은 **ERROR_HANDLING.md**를 참조하라.

---

## 로깅 전략

### 모든 모듈에서 동일한 패턴 사용
```python
import logging
logger = logging.getLogger(__name__)
```
루트 로거 설정은 `config.py`에서 한 번만 수행.

### 로그 레벨 기준
| 레벨 | 사용 예 |
|------|--------|
| DEBUG | 청크 단위 처리, 유사도 점수, 배치 인덱스 |
| INFO | 파일별 인제스트 시작/완료, 질문 처리, Chain-1 결과 |
| WARNING | 스캔본 PDF, 짧은 청크 스킵, 빈 LLM 응답, 재시도 발생 |
| ERROR | 파일 인제스트 실패, API 재시도 소진 |
| CRITICAL | API 키 무효, Pinecone 인덱스 없음 |

### 출력 대상
- 콘솔 (StreamHandler): INFO 이상
- 파일 logs/app.log (RotatingFileHandler): DEBUG 이상, 10MB × 3 백업

---

## 메모리 관리

```python
ConversationBufferMemory(
    memory_key="chat_history",
    return_messages=True,
    output_key="answer",
)
```

### 토큰 한도 트리밍
- `tiktoken`으로 히스토리 토큰 수 계산
- MAX_MEMORY_TOKENS(4000) 초과 시: 오래된 메시지 쌍(사용자+AI)부터 제거
- 트리밍은 사용자에게 표시 안 함 (자동 처리)

---

## 세션 영속화 (로컬 파일 기반)

로그인 없이 PC 로컬 파일로 대화 히스토리를 영속화한다.

### 디렉토리 구조 추가
```
data/
└── sessions/              # 세션 파일 저장 (.gitignore에 추가)
    └── {datetime}_{id}.json
src/ui/
└── session.py             # SessionManager 클래스
```

### 동작 흐름
```
앱 시작
  │
  ▼
SessionManager.load_latest_session()
  ├── 세션 없음 → create_session() → 빈 대화로 시작
  └── 세션 있음 → st.session_state.messages 복원
                → engine.memory에 memory_messages 재주입
                   (ConversationBufferMemory.chat_memory.add_messages)

질문/답변 발생
  └── SessionManager.save_message() → 즉시 파일에 추가

대화 초기화
  └── 현재 세션 파일 삭제 + create_session() → 새 빈 세션
```

### 세션 파일 스키마
DATA_SCHEMA.md "세션 파일 스키마" 참조.

### 사이드바 세션 히스토리 UI
- 과거 세션 목록: 날짜·메시지 수 표시
- 선택 시 해당 세션 messages 열람 (읽기 전용, 현재 세션 교체 없음)
- 과거 세션에서는 질문 불가 (이어서 대화 기능 MVP 제외)

---

## Streamlit 상태 관리

```python
# app.py 초기화 블록
if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_sources" not in st.session_state:
    st.session_state.last_sources = []
if "engine_ready" not in st.session_state:
    st.session_state.engine_ready = False

@st.cache_resource
def get_engine() -> RAGEngine:
    """RAGEngine 싱글톤. Streamlit 프로세스 수명 동안 유지."""
    try:
        engine = RAGEngine()
        st.session_state.engine_ready = True
        return engine
    except Exception as e:
        st.session_state.engine_ready = False
        raise
```
