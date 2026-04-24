# 에러 처리 카탈로그

모든 에러는 이 문서에 명시된 동작을 따른다. 에러 코드를 변경하거나 임의로 처리 방식을 바꾸지 마라.
새 에러 케이스가 발생하면 이 문서에 먼저 추가하고 구현하라.

---

## 에러 코드 체계

| 접두어 | 범위 |
|--------|------|
| E-C | 시작 시 에러 (config.py) |
| E-I | 인제스트 에러 (ingest.py, src/ingest/) |
| E-R | RAG 에러 (src/rag/) |
| E-U | UI 에러 (app.py, src/ui/) |

---

## 1. 시작 시 에러 (config.py)

### E-C-01: 필수 환경변수 없음
- **감지**: `os.getenv("OPENAI_API_KEY") is None` 또는 `os.getenv("PINECONE_API_KEY") is None`
- **위치**: config.py 모듈 임포트 시점
- **동작**: `raise EnvironmentError("환경변수 {VAR}가 설정되지 않았습니다. .env 파일을 확인하세요.")`
- **로그 레벨**: CRITICAL

---

## 2. 인제스트 에러 (ingest.py, src/ingest/)

### E-I-01: rag_data/ 디렉토리 없음
- **감지**: `os.path.isdir(dir_path) == False`
- **동작**: `sys.exit(1)`
- **출력**: `"에러: '{dir_path}' 디렉토리가 존재하지 않습니다."`
- **로그 레벨**: CRITICAL

### E-I-02: PDF 파일 없음 (빈 디렉토리)
- **감지**: glob(`*.pdf`, `*.PDF`) 결과 빈 리스트
- **동작**: 경고 출력 후 정상 종료 (exit code 0)
- **출력**: `"경고: '{dir_path}'에 PDF 파일이 없습니다."`
- **로그 레벨**: WARNING

### E-I-03: PDF 파일 접근 권한 없음
- **감지**: `open(path)` 시 `PermissionError`
- **동작**: 해당 파일 스킵, `IngestReport.failed`에 파일명 추가
- **출력**: `"에러: 파일 접근 권한 없음: {filename}"`
- **로그 레벨**: ERROR

### E-I-04: PDF 파일 손상 / 파싱 실패
- **감지**: `pdfplumber.open(path)` 또는 페이지 접근 시 예외 (PDFSyntaxError 등)
- **동작**: 해당 파일 스킵, `IngestReport.failed`에 추가
- **출력**: `"에러: PDF 파싱 실패: {filename} — {에러 메시지}"`
- **로그 레벨**: ERROR

### E-I-05: 스캔본 PDF (텍스트 레이어 없음)
- **감지**: `is_scanned_pdf(pages) == True` (총 텍스트 < `SCANNED_PDF_MIN_CHARS`=50자)
- **동작**: 해당 파일 스킵, `IngestReport.failed`에 추가
- **출력**: `"경고: 스캔본으로 판단됨 (텍스트 추출 불가): {filename}"`
- **로그 레벨**: WARNING

### E-I-06: 비어있는 PDF (0 페이지)
- **감지**: `len(pdf.pages) == 0`
- **동작**: 해당 파일 스킵, `IngestReport.failed`에 추가
- **출력**: `"경고: 페이지가 없는 PDF: {filename}"`
- **로그 레벨**: WARNING

### E-I-07: 청킹 후 유효 청크 없음
- **감지**: `split_documents()` 결과 빈 리스트 (모두 MIN_CHUNK_SIZE 미만)
- **동작**: 해당 파일 스킵, `IngestReport.failed`에 추가
- **출력**: `"경고: 유효한 청크 없음 (모두 {MIN_CHUNK_SIZE}자 미만): {filename}"`
- **로그 레벨**: WARNING

### E-I-08: OpenAI 임베딩 오류 (재시도 가능)
- **감지**: `openai.RateLimitError`, `openai.APITimeoutError`, `openai.InternalServerError`
- **동작**: `retry_with_backoff()` — 1s, 2s, 4s 대기 후 최대 `MAX_RETRIES`(3)회 재시도
- **재시도 소진**: `RetryExhaustedError` → 인제스트 전체 중단
- **출력 (재시도 중)**: `"경고: OpenAI API 오류. {n}회 재시도 중 ({delay}s 대기)..."`
- **출력 (소진)**: `"에러: OpenAI API 재시도 {MAX_RETRIES}회 소진. 잠시 후 다시 실행하세요."`
- **로그 레벨**: WARNING (재시도), ERROR (소진)

### E-I-09: OpenAI 임베딩 오류 (즉시 실패)
- **감지**: `openai.AuthenticationError`, `openai.PermissionDeniedError`
- **동작**: `sys.exit(1)`
- **출력**: `"에러: OpenAI API 키가 유효하지 않습니다. .env를 확인하세요."`
- **로그 레벨**: CRITICAL

### E-I-10: OpenAI API 연결 실패
- **감지**: `openai.APIConnectionError`
- **동작**: 인제스트 전체 중단 (재시도 없음)
- **출력**: `"에러: OpenAI API에 연결할 수 없습니다. 네트워크를 확인하세요."`
- **로그 레벨**: ERROR

### E-I-11: Pinecone API 키 무효
- **감지**: Pinecone 초기화 시 401/403 오류
- **동작**: `sys.exit(1)`
- **출력**: `"에러: Pinecone API 키가 유효하지 않습니다. .env를 확인하세요."`
- **로그 레벨**: CRITICAL

### E-I-12: Pinecone 인덱스 없음
- **감지**: 인덱스 접근 시 404 오류
- **동작**: `sys.exit(1)`
- **출력**: `"에러: Pinecone 인덱스 '{PINECONE_INDEX_NAME}'가 존재하지 않습니다."`
- **로그 레벨**: CRITICAL

### E-I-13: Pinecone upsert 실패 (배치)
- **감지**: `index.upsert()` 시 예외
- **동작**: 해당 배치 1회 재시도 → 실패 시 해당 배치 스킵, 경고 출력, 계속 진행
- **출력**: `"경고: Pinecone 업로드 실패 (배치 {i}~{i+BATCH_SIZE}). 건너뜁니다."`
- **로그 레벨**: WARNING

### E-I-14: 해시 조회 실패 (중복 확인 불가)
- **감지**: `get_existing_hashes()` 시 Pinecone 예외
- **동작**: 빈 set 반환 + 경고 출력. 모든 파일 재인제스트 진행 (중복 벡터 가능)
- **출력**: `"경고: 기존 해시 조회 실패. 중복 체크 없이 진행합니다."`
- **로그 레벨**: WARNING

---

## 3. RAG 에러 (src/rag/)

### E-R-01: RAGEngine 초기화 실패
- **감지**: `RAGEngine.__init__()` 내 예외 (Pinecone 연결, OpenAI 초기화 등)
- **동작**: 예외 전파 → `get_engine()` 실패 → `engine_ready = False`
- **UI 동작**: `st.error("RAG 엔진 초기화 실패. Pinecone/OpenAI 연결을 확인하세요.")` + 입력창 미표시
- **로그 레벨**: ERROR

### E-R-02: Chain-1 OpenAI 오류 (질문 응축 실패)
- **감지**: Chain-1 (`build_condense_chain`) 실행 시 OpenAI 예외
- **동작**: `retry_with_backoff(3회)` → 소진 시 **fallback: 원본 question을 standalone_question으로 사용**
- **fallback 로그**: `"경고: Chain-1 실패, 원본 질문으로 fallback: {question}"`
- **사용자에게 표시 안 함** (자동 처리)
- **로그 레벨**: WARNING

### E-R-03: Chain-2 OpenAI 오류 (답변 생성 실패)
- **감지**: Chain-2 (`build_qa_chain`) 실행 시 OpenAI 예외
- **동작**: `retry_with_backoff(3회)` → 소진 시 `RetryExhaustedError` 전파
- **UI 메시지**: `"AI 서비스 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."`
- **로그 레벨**: ERROR

### E-R-04: 검색 결과 없음 (유사도 임계값 미달)
- **감지**: 유사도 필터 후 `filtered_docs == []`
- **동작**: Chain-2 호출 없이 즉시 반환
- **answer**: `"제공된 문서에서 해당 질문과 관련된 내용을 찾을 수 없습니다. 질문을 더 구체적으로 바꾸거나 관련 문서가 인제스트되었는지 확인하세요."`
- **source_documents**: `[]`
- **메모리 저장**: 정상 저장 (히스토리 유지)
- **로그 레벨**: INFO

### E-R-05: 빈 LLM 응답 (Chain-2)
- **감지**: `response.strip() == ""`
- **동작**: 동일 입력으로 1회 재시도 → 여전히 빈 응답 → 에러 메시지
- **answer**: `"답변을 생성할 수 없습니다. 다시 시도해 주세요."`
- **로그 레벨**: WARNING

### E-R-06: 메모리 토큰 초과 (자동 처리)
- **감지**: 히스토리 토큰 수 > `MAX_MEMORY_TOKENS`(4000)
- **동작**: tiktoken으로 계산 후 오래된 메시지 쌍(사용자+AI)부터 제거. 한도 이하가 될 때까지 반복.
- **사용자에게 표시 안 함**
- **로그 레벨**: DEBUG

### E-R-07: ConversationBufferMemory 접근 오류
- **감지**: `memory.load_memory_variables()` 또는 `memory.save_context()` 예외
- **동작**: 메모리 완전 초기화 후 현재 질문 재처리 (히스토리 소실 감수)
- **UI 메시지**: `"대화 기록에 오류가 발생해 초기화되었습니다."`
- **로그 레벨**: WARNING

### E-R-08: Pinecone 쿼리 실패
- **감지**: `similarity_search_with_score()` 시 Pinecone 예외
- **동작**: 예외 전파 → engine.ask() 에러 처리
- **UI 메시지**: `"문서 검색 중 오류가 발생했습니다. 다시 시도해 주세요."`
- **로그 레벨**: ERROR

---

## 4. UI 에러 (app.py, src/ui/)

### E-U-01: RAGEngine 초기화 실패 (UI 진입 시)
- **감지**: `get_engine()` 예외
- **동작**: `st.session_state.engine_ready = False`
- **UI 동작**:
  - `st.error("RAG 엔진을 시작할 수 없습니다. Pinecone/OpenAI 연결을 확인하세요.")`
  - `st.chat_input()` 표시 안 함 (`engine_ready` 조건 분기)
  - `st.stop()` 호출하여 이후 렌더링 중단

### E-U-02: 질문 처리 중 예외
- **감지**: `engine.ask()` 에서 예외 전파 (RetryExhaustedError 등)
- **동작**: try/except 내 포착
- **UI 동작**:
  - `st.session_state.messages`에 assistant 에러 메시지 추가: `"⚠️ 오류가 발생했습니다: 잠시 후 다시 시도해 주세요."`
  - 세션 유지 (대화 히스토리 보존, 재질문 가능)
- **로그 레벨**: ERROR

### E-U-03: 대화 초기화 중 예외
- **감지**: `engine.reset()` 예외
- **동작**: `st.session_state.messages = []`, `st.session_state.last_sources = []` 수동 초기화
- **UI 동작**: `st.warning("대화 기록 초기화 중 오류가 발생했습니다. 수동으로 초기화했습니다.")`
- **로그 레벨**: WARNING

---

## 5. 세션 에러 (src/ui/session.py)

### E-S-01: 세션 파일 읽기 실패
- **감지**: `load_latest_session()` 시 JSON 파싱 오류, 파일 손상, 권한 없음
- **동작**: `None` 반환 → 빈 세션으로 시작
- **UI 동작**: `st.warning("이전 세션을 불러올 수 없어 새 세션으로 시작합니다.")`
- **로그 레벨**: WARNING

### E-S-02: 세션 파일 저장 실패
- **감지**: `save_message()` 시 파일 쓰기 오류 (권한, 디스크 풀 등)
- **동작**: 경고 로그만 출력, 대화 계속 진행 (저장 실패가 대화를 중단하면 안 됨)
- **사용자에게 표시 안 함**
- **로그 레벨**: WARNING

### E-S-03: data/sessions/ 디렉토리 없음
- **감지**: `data/sessions/` 폴더 없음
- **동작**: 자동 생성 (`os.makedirs(sessions_dir, exist_ok=True)`)
- **로그 레벨**: INFO

### E-S-04: 세션 메모리 재구성 실패
- **감지**: `rebuild_memory()` 또는 `engine.memory`에 메시지 주입 시 예외
- **동작**: 빈 메모리로 시작, 저장된 messages는 UI에 표시 (맥락 없이 새 대화 시작)
- **UI 동작**: `st.warning("이전 대화 맥락을 복원할 수 없습니다. 새 대화로 시작합니다.")`
- **로그 레벨**: WARNING

---

## 에러 우선순위 및 격리 원칙

| 우선순위 | 코드 | 처리 방식 |
|---------|------|---------|
| CRITICAL | E-C-01, E-I-01, E-I-09, E-I-11, E-I-12 | 즉시 종료 / UI 비활성화 |
| HIGH | E-I-08, E-R-01, E-R-03, E-R-08 | 재시도 후 에러 메시지 |
| MEDIUM | E-I-03~E-I-07, E-I-13, E-R-04, E-R-05, E-R-07 | 해당 단위 스킵, 계속 진행 |
| LOW | E-I-02, E-I-14, E-R-02, E-R-06 | 경고 + 자동 처리 |

**격리 원칙**:
- 인제스트: 파일 단위 격리. 한 파일 실패가 전체 인제스트를 중단하지 않는다.
- RAG: 질문 단위 격리. 한 질문 실패가 세션을 파괴하지 않는다.

---

## retry_with_backoff() 스펙

모든 OpenAI API 호출에 공통 적용:

```python
RETRYABLE_EXCEPTIONS = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.InternalServerError,
)

NON_RETRYABLE_EXCEPTIONS = (
    openai.AuthenticationError,
    openai.PermissionDeniedError,
    openai.APIConnectionError,
)

def retry_with_backoff(func, *args, **kwargs):
    for attempt in range(MAX_RETRIES):
        try:
            return func(*args, **kwargs)
        except NON_RETRYABLE_EXCEPTIONS:
            raise  # 즉시 실패
        except RETRYABLE_EXCEPTIONS as e:
            if attempt == MAX_RETRIES - 1:
                raise RetryExhaustedError(f"재시도 {MAX_RETRIES}회 소진") from e
            delay = RETRY_BASE_DELAY * (2 ** attempt)
            logger.warning(f"API 오류, {delay}s 후 재시도 ({attempt+1}/{MAX_RETRIES}): {e}")
            time.sleep(delay)
```
