# UI 디자인 가이드 (Streamlit)

## 디자인 원칙
1. **도구처럼 보여야 한다.** 전문 연구자가 매일 쓰는 연구 도구다. 마케팅 UI가 아니다.
2. **정보 우선.** 답변과 출처가 즉시 눈에 들어와야 한다. 장식은 방해다.
3. **예측 가능하게.** 질문 → 로딩 → 답변 → 출처의 흐름이 항상 일관되어야 한다.
4. **상태를 명확히.** 로딩, 에러, 빈 상태, 정상 상태를 시각적으로 구분한다.

---

## Streamlit 컴포넌트 사용 규칙

### 페이지 설정
```python
st.set_page_config(
    page_title="Research RAG",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)
```

### 채팅 인터페이스
```python
# 메시지 렌더링 (session_state.messages 순서대로)
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 질문 입력 (engine_ready일 때만 표시)
if st.session_state.engine_ready:
    prompt = st.chat_input("질문을 입력하세요...")

# 로딩 표시
with st.spinner("문서 검색 중..."):
    result = engine.ask(prompt)
```

### 출처 표시 (답변 바로 아래)
```python
if st.session_state.last_sources:
    for i, doc in enumerate(st.session_state.last_sources, 1):
        filename = doc.metadata.get("source", "알 수 없음")
        page = doc.metadata.get("page", "?")
        char_count = doc.metadata.get("char_count", "?")
        with st.expander(f"📄 출처 {i}: {filename}  ·  p.{page}"):
            st.caption(doc.page_content)
```

### 사이드바
```python
with st.sidebar:
    st.title("Research RAG")
    st.caption("전문 연구자용 논문 Q&A")
    st.divider()

    # 현재 세션 초기화
    if st.button("🗑️ 대화 초기화", use_container_width=True):
        try:
            engine.reset()
            session_manager.delete_session(st.session_state.session_id)
        except Exception:
            pass  # E-U-03: 수동 초기화
        st.session_state.messages = []
        st.session_state.last_sources = []
        st.session_state.session_id = session_manager.create_session()
        st.rerun()

    st.divider()

    # 과거 세션 목록 (읽기 전용)
    st.caption("📋 과거 대화 기록")
    past_sessions = session_manager.list_sessions()
    if past_sessions:
        for s in past_sessions[:10]:  # 최근 10개만 표시
            label = f"{s['created_at'][:16]}  ({s['message_count']}개)"
            if st.button(label, key=s["session_id"], use_container_width=True):
                st.session_state.viewing_session = s["session_id"]
    else:
        st.caption("저장된 대화가 없습니다.")

    st.divider()
    st.caption(f"인덱스: resercher-helper")
    st.caption(f"모델: gpt-4o")
```

### 과거 세션 열람 UI (읽기 전용)
```python
# viewing_session이 설정된 경우 해당 세션 내용 표시
if "viewing_session" in st.session_state and st.session_state.viewing_session:
    session_data = session_manager.load_session(st.session_state.viewing_session)
    if session_data:
        st.subheader(f"📖 과거 대화 — {session_data['created_at'][:16]}")
        for msg in session_data["messages"]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
        if st.button("← 현재 대화로 돌아가기"):
            del st.session_state.viewing_session
            st.rerun()
        st.stop()  # 과거 세션 열람 중에는 현재 대화 렌더링 안 함
```

---

## 상태별 UI 처리

### 1. 엔진 초기화 실패 (E-U-01)
```python
# get_engine() 실패 시 engine_ready = False
if not st.session_state.get("engine_ready", False):
    st.error(
        "🔴 RAG 엔진을 시작할 수 없습니다.\n\n"
        "**확인 사항:**\n"
        "- `.env` 파일에 `OPENAI_API_KEY`, `PINECONE_API_KEY` 설정\n"
        "- Pinecone 인덱스 `resercher-helper` 존재 여부\n"
        "- 네트워크 연결 상태"
    )
    st.stop()  # 이후 렌더링 중단 (입력창 표시 안 함)
```

### 2. 초기 상태 (대화 없음, 인제스트 전)
```python
if not st.session_state.messages:
    st.info(
        "📂 **PDF 인제스트 후 질문을 시작하세요.**\n\n"
        "```bash\npython ingest.py --dir rag_data\n```"
    )
```

### 3. 검색 결과 없음
- Chain-2 answer에 "제공된 문서에서 관련 내용을 찾을 수 없습니다." 자동 포함
- 별도 UI 처리 없음 (assistant 메시지로 자연스럽게 표시)
- `last_sources`가 빈 리스트 → 출처 expander 미표시

### 4. 질문 처리 중 API 오류 (E-U-02)
```python
# engine.ask() try/except 내
except Exception as e:
    error_msg = "⚠️ 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
    st.session_state.messages.append({"role": "assistant", "content": error_msg})
    # 세션 유지 (재질문 가능)
```

### 5. 로딩 상태
- `st.spinner("문서 검색 중...")` 내에서 `engine.ask()` 호출
- spinner 표시 중 입력창 비활성화 (Streamlit 자동 처리)
- 30초 초과 응답이 드물지 않음 → spinner 텍스트로 사용자 안내

### 6. 대화 초기화 확인 없음
- 초기화 버튼 클릭 시 즉시 초기화 (확인 다이얼로그 없음)
- 석사·박사 사용자 대상: 불필요한 UX 단계 제거

---

## 금지 사항

| 금지 | 이유 |
|------|------|
| `st.balloons()`, `st.snow()` | 전문 도구에 어울리지 않는 시각 효과 |
| `st.markdown("<style>...", unsafe_allow_html=True)` 과도한 사용 | 유지보수 불가, Streamlit 업그레이드 시 깨짐 |
| 배경 이미지, 그라디언트 배경, glass morphism | 가독성 저하 |
| `st.rerun()` 남발 (로직 흐름 외) | UX 예측 불가, 무한 루프 위험 |
| `time.sleep()` | UI 블로킹 |
| `st.stop()` (정상 상태에서) | 엔진 실패 등 예외 상황에만 허용 |
| `@st.cache_data` (RAGEngine에) | `@st.cache_resource`만 사용. 상태가 있는 객체에 cache_data 금지 |
| 동일 session_state 키에 다른 타입 혼용 | 타입 불일치로 런타임 에러 발생 |

---

## 레이아웃

- `layout="wide"` — 채팅 영역 확보
- 채팅 영역: 메인 컬럼 (전체 너비)
- 출처 + 설정: 사이드바 + 채팅 메시지 하단 expander
- 컬럼 분할 금지 (채팅 UI에서 `st.columns` 사용 자제)

---

## 상태 관리 요약

| 키 | 타입 | 초기값 | 설명 |
|----|------|--------|------|
| `messages` | `list[dict]` | `[]` | `{role: "user"\|"assistant", content: str}` |
| `last_sources` | `list[Document]` | `[]` | 마지막 응답 출처 문서 |
| `engine_ready` | `bool` | `False` | 엔진 초기화 완료 여부 |

**주의**: `engine_ready`는 `get_engine()` 성공 시만 `True`로 설정. 이 값이 `False`이면 `st.chat_input` 렌더링하지 않는다.

---

## RAGEngine 캐싱

```python
@st.cache_resource
def get_engine() -> RAGEngine:
    """
    Streamlit 프로세스 수명 동안 싱글톤 유지.
    앱 재시작 시만 재초기화.
    초기화 실패 시 예외 전파 (E-U-01 처리).
    """
    try:
        engine = RAGEngine()
        # engine_ready 설정은 호출 코드에서
        return engine
    except Exception as e:
        logger.critical(f"RAGEngine 초기화 실패: {e}")
        raise
```
