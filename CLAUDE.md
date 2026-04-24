# 프로젝트: Research RAG — 전문 연구자용 논문 Q&A 시스템

## 기술 스택
- Python 3.11 (venv)
- Streamlit (UI)
- LangChain (RAG 오케스트레이션)
- OpenAI gpt-4o (LLM), text-embedding-3-large (임베딩, dim 3072)
- Pinecone (벡터 DB, index: resercher-helper)
- pdfplumber (PDF 파싱 — 다단 레이아웃 지원, pypdf 사용 금지)

## 아키텍처 규칙
- CRITICAL: 모든 OpenAI / Pinecone API 호출은 src/rag/ 또는 src/ingest/ 내에서만 수행한다. app.py나 src/ui/에서 직접 API를 호출하지 마라.
- CRITICAL: app.py는 src/rag/engine.py의 RAGEngine 인터페이스만 사용한다. 체인·리트리버 객체를 직접 생성하거나 조작하지 마라.
- CRITICAL: 새 모듈 작성 시 반드시 테스트를 먼저 작성하고, 테스트가 통과하는 구현을 작성할 것 (TDD)
- CRITICAL: 모든 에러 처리는 ERROR_HANDLING.md의 명세를 따른다. 임의로 에러를 무시하거나 다른 방식으로 처리하지 마라.
- 인제스트 로직(src/ingest/)과 RAG 로직(src/rag/)은 서로 의존하지 않는다. 공통 의존성은 config.py에서만 가져온다.
- 답변 언어는 한국어 고정이다. 언어 감지나 다국어 처리를 추가하지 마라.
- 데이터 스키마(Pinecone 메타데이터, Document 형식, 반환 타입)는 DATA_SCHEMA.md를 따른다.
- 프롬프트 텍스트는 PROMPTS.md에 정의된 상수를 그대로 사용한다. 임의로 수정하지 마라.

## 개발 프로세스
- 커밋 메시지는 conventional commits 형식을 따를 것 (feat:, fix:, docs:, refactor:)

## 명령어
streamlit run app.py           # 앱 실행
python ingest.py               # PDF 인제스트 (기본: --dir rag_data)
pytest tests/                  # 테스트 실행
pip install -r requirements.txt  # 의존성 설치
