<div align="center">

# 🧬 리서처헬퍼

**전문 연구자를 위한 논문·특허 PDF 대화형 Q&A 시스템**

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.x-FF4B4B?style=flat-square&logo=streamlit&logoColor=white)](https://streamlit.io)
[![LangChain](https://img.shields.io/badge/LangChain-0.3-1C3C3C?style=flat-square&logo=langchain&logoColor=white)](https://langchain.com)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-412991?style=flat-square&logo=openai&logoColor=white)](https://openai.com)
[![Pinecone](https://img.shields.io/badge/Pinecone-VectorDB-13AA52?style=flat-square)](https://pinecone.io)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)

<br/>

> 석·박사 연구자가 수십 편의 논문·특허 PDF를 업로드하면,  
> GPT-4o 기반 2-Chain RAG가 **출처 명시**와 함께 정확한 전문 답변을 스트리밍으로 제공합니다.

<br/>

![리서처헬퍼 스크린샷 자리](https://via.placeholder.com/900x480/0d1520/4a8fcd?text=리서처헬퍼+%F0%9F%A7%AC)

</div>

---

## ✨ 주요 기능

| 기능                     | 설명                                                                          |
| ------------------------ | ----------------------------------------------------------------------------- |
| 📄 **PDF 배치 인제스트** | `rag_data/` 폴더의 모든 PDF를 파싱·청킹·임베딩 후 Pinecone에 업로드           |
| 💬 **대화형 전문 QA**    | 2-Chain RAG(질문 응축 → 벡터 검색 → 전문 답변)로 맥락을 유지한 연속 질문 지원 |
| 📌 **출처 자동 표시**    | 모든 답변에 `(출처: 파일명.pdf, p.N)` 형식으로 근거 청크 명시                 |
| 🔄 **세션 영속화**       | 대화 히스토리를 로컬에 자동 저장, 앱 재시작 후 이전 대화 즉시 복원            |
| 🎨 **다크/라이트 모드**  | 미드나잇 블루 다크 테마 기본 제공, 햄버거 메뉴로 테마 전환                    |
| ⚡ **스트리밍 답변**     | 답변을 실시간으로 타이핑하듯 스트리밍 출력                                    |
| 🛡️ **할루시네이션 방지** | 컨텍스트 외부 지식으로 보완하지 않음. 근거 없으면 "찾을 수 없습니다" 반환     |

---

## 🏗️ 아키텍처

```
사용자 질문
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  Chain-1: Question Condenser                            │
│  대화 히스토리의 지시어를 구체적 내용으로 대체             │
│  → 독립형 standalone question 생성                      │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│  Pinecone Vector Search                                 │
│  text-embedding-3-large (dim 3072)                     │
│  Top-K=30 후보 → Cross-Encoder 재순위화 → Final-K=7    │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│  Chain-2: Expert QA                                     │
│  GPT-4o + 컨텍스트 기반 전문 한국어 답변 생성            │
│  출처: (파일명, p.페이지) 인라인 표기                    │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
                     스트리밍 답변 출력
```

### 레이어 구조

```
llm.rag.for.resercher/
├── app.py                    # Streamlit 진입점 (UI only)
├── ingest.py                 # PDF 인제스트 CLI
├── config.py                 # 환경변수 로딩 & 전역 상수
├── requirements.txt
│
├── src/
│   ├── ingest/
│   │   ├── loader.py         # PDF 파싱 (pdfplumber — 다단 레이아웃 지원)
│   │   ├── splitter.py       # 청킹 & 최소 길이 검증
│   │   └── pipeline.py       # 인제스트 파이프라인 오케스트레이션
│   ├── rag/
│   │   ├── retriever.py      # Pinecone 리트리버 + 유사도 필터
│   │   ├── chains.py         # Chain-1 & Chain-2 빌더
│   │   └── engine.py         # RAGEngine (prepare / generate_stream / update_history)
│   └── ui/
│       ├── components.py     # Streamlit 컴포넌트
│       └── session.py        # 로컬 세션 영속화
│
├── tests/
│   ├── test_ingest.py
│   └── test_rag.py
│
└── docs/
    ├── ARCHITECTURE.md
    ├── PRD.md
    ├── DATA_SCHEMA.md
    ├── ERROR_HANDLING.md
    └── PROMPTS.md
```

---

## 🛠️ 기술 스택

<table>
  <thead>
    <tr>
      <th>레이어</th>
      <th>기술</th>
      <th>역할</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><b>UI</b></td>
      <td>Streamlit</td>
      <td>웹 프론트엔드 (다크/라이트 테마, 스트리밍 채팅)</td>
    </tr>
    <tr>
      <td><b>LLM</b></td>
      <td>OpenAI GPT-4o</td>
      <td>질문 응축 & 전문 QA 생성</td>
    </tr>
    <tr>
      <td><b>임베딩</b></td>
      <td>text-embedding-3-large (dim 3072)</td>
      <td>문서 & 쿼리 벡터화</td>
    </tr>
    <tr>
      <td><b>벡터 DB</b></td>
      <td>Pinecone</td>
      <td>고속 유사도 검색 (index: resercher-helper)</td>
    </tr>
    <tr>
      <td><b>Re-ranker</b></td>
      <td>BAAI/bge-reranker-base</td>
      <td>Cross-Encoder 기반 재순위화 (한국어 특화)</td>
    </tr>
    <tr>
      <td><b>PDF 파싱</b></td>
      <td>pdfplumber</td>
      <td>다단 레이아웃·특허 문서 컬럼 순서 정확 복원</td>
    </tr>
    <tr>
      <td><b>RAG 오케스트레이션</b></td>
      <td>LangChain</td>
      <td>2-Chain 파이프라인, 메모리 관리</td>
    </tr>
  </tbody>
</table>

---

## 🚀 빠른 시작

### 1. 요구사항

- Python **3.11**
- OpenAI API 키
- Pinecone API 키 (인덱스명: `resercher-helper`, dimension: `3072`, metric: `cosine`)

### 2. 설치

```bash
# 저장소 클론
git clone https://github.com/YOUR_USERNAME/llm.rag.for.resercher.git
cd llm.rag.for.resercher

# 가상환경 생성 & 활성화
python -m venv venv
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate         # Windows

# 의존성 설치
pip install -r requirements.txt
```

### 3. 환경변수 설정

`.env.example`을 복사하여 `.env`를 생성하고 API 키를 입력합니다.

```bash
cp .env.example .env
```

```ini
# .env
OPENAI_API_KEY=sk-...
PINECONE_API_KEY=pcsk_...
```

> ⚠️ `.env` 파일은 절대 커밋하지 마세요. `.gitignore`에 이미 등록되어 있습니다.

### 4. PDF 인제스트

분석할 PDF 파일을 `rag_data/` 폴더에 넣고 인제스트를 실행합니다.

```bash
python ingest.py --dir rag_data
```

```
✅ 처리 완료: 논문A.pdf (청크 132개 업로드)
✅ 처리 완료: 특허B.pdf (청크 87개 업로드)
⏭️  스킵 (이미 인덱싱됨): 논문C.pdf
────────────────────────────────
총 파일: 3  |  성공: 2  |  스킵: 1  |  실패: 0
업로드된 벡터: 219개
```

> 동일 파일을 다시 실행해도 MD5 해시 기반 멱등성으로 중복 업로드되지 않습니다.

### 5. 앱 실행

```bash
streamlit run app.py
```

브라우저에서 `http://localhost:8501` 접속 후 질문을 시작하세요.

---

## ☁️ Streamlit Cloud 배포

### 1. GitHub에 푸시

```bash
git add .
git commit -m "feat: initial commit"
git push origin main
```

> `rag_data/`, `.env`, `venv/`, `data/sessions/`는 `.gitignore`에 의해 자동 제외됩니다.  
> PDF 원본은 Git에 포함되지 않으며, 벡터는 Pinecone 클라우드에 저장됩니다.

### 2. share.streamlit.io 설정

1. [share.streamlit.io](https://share.streamlit.io) 접속 → **New app**
2. Repository 선택 → Main file: `app.py`
3. **Advanced settings → Secrets**에 API 키 입력:

```toml
OPENAI_API_KEY = "sk-..."
PINECONE_API_KEY = "pcsk_..."
```

4. **Deploy** 클릭

---

## 💬 사용 예시

```
사용자: 코팅 조성물에서 셀룰로오스의 역할이 뭔가요?

리서처헬퍼: 코팅 조성물에서 셀룰로오스는 **필름 형성 기제**로 사용됩니다.
            구체적으로 **5~10 중량%** 농도로 배합되며, 피막의 기계적 강도를
            높이는 핵심 성분입니다.
            (출처: KR101742708B1_천연물.pdf, p.3)

사용자: 그게 몇 도에서 만들어지나요?

리서처헬퍼: 해당 조성물은 **60~80°C**에서 **15분간 교반**하여 제조됩니다.
            (출처: KR101742708B1_천연물.pdf, p.5)
```

> Chain-1이 "그게 몇 도에서"를 "셀룰로오스 코팅 조성물의 제조 온도는 몇 도인가요?"로 자동 변환하여 검색합니다.

---

## 🧪 테스트

```bash
# 전체 테스트 실행
pytest tests/ -v

# 특정 모듈 테스트
pytest tests/test_ingest.py -v
pytest tests/test_rag.py -v
```

---

## ⚙️ 주요 파라미터

| 파라미터               | 기본값                   | 설명                                    |
| ---------------------- | ------------------------ | --------------------------------------- |
| `RETRIEVER_TOP_K`      | `30`                     | 임베딩 1차 후보 수                      |
| `RETRIEVER_FINAL_K`    | `7`                      | Re-ranker 후 QA에 전달하는 최종 청크 수 |
| `SIMILARITY_THRESHOLD` | `0.15`                   | 유사도 임계값 (이하 필터 제거)          |
| `CHUNK_SIZE`           | `1000`                   | 청크 최대 문자 수                       |
| `CHUNK_OVERLAP`        | `200`                    | 청크 간 겹침 문자 수                    |
| `MAX_MEMORY_TOKENS`    | `4000`                   | 대화 히스토리 최대 토큰                 |
| `LLM_MODEL`            | `gpt-4o`                 | 사용 LLM 모델                           |
| `RERANKER_MODEL`       | `BAAI/bge-reranker-base` | Cross-Encoder 재순위화 모델             |

`config.py`에서 수정할 수 있습니다.

---

## 📋 에러 처리

| 상황               | 동작                                                 |
| ------------------ | ---------------------------------------------------- |
| 관련 문서 없음     | "제공된 문서에서 관련 내용을 찾을 수 없습니다." 반환 |
| OpenAI API 오류    | 지수 백오프 최대 3회 재시도 (1s → 2s → 4s)           |
| 스캔본 PDF         | CID 폰트 감지 시 자동 OCR 경로 전환                  |
| 파일 인제스트 실패 | 해당 파일 스킵, 나머지 계속 처리                     |
| API 키 누락        | 임포트 시 즉시 `EnvironmentError` 발생               |

---

## 🗺️ 로드맵

- [ ] v0.2 — 브라우저 드래그&드롭 PDF 업로드 UI
- [ ] v0.3 — 사용자 인증 & 클라우드 세션 동기화
- [ ] v0.4 — 문서별 검색 필터 & 문서 관리 UI
- [ ] v1.0 — 유료 구독 모델 (PRO 플랜)

---

## 👤 개발자

<table>
  <tr>
    <td align="center">
      <b>shYOON</b><br/>
      <sub>Developer & Researcher</sub><br/>
      <a href="mailto:upustream@gmail.com">upustream@gmail.com</a>
    </td>
  </tr>
</table>

논문·특허 데이터 추가 요청은 [upustream@gmail.com](mailto:upustream@gmail.com) 으로 문의해 주세요.

---

<div align="center">

**리서처헬퍼 v0.1** &nbsp;·&nbsp; Made with ❤️ for Researchers

</div>
