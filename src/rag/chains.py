"""LLM chain builders and prompt templates for the 2-chain RAG system."""

import logging

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableSequence
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

# --- Prompt templates (from PROMPTS.md — do not modify without ADR entry) ---

CONDENSE_QUESTION_TEMPLATE = """대화 기록과 후속 질문이 주어집니다.
후속 질문을 대화 기록과 독립적으로 이해할 수 있는 단독 질문으로 재작성하세요.

규칙:
- 대화 기록의 지시어("이것", "그것", "해당", "위의", "앞의", "저것", "이 방법", "그 조건")가 가리키는 대상을 구체적 내용으로 대체하라.
- 질문의 전문 용어, 화학식, 수치, 고유명사, 약어는 원문 그대로 유지하라.
- 질문의 의미, 범위, 의도를 변경하거나 단순화하지 마라.
- 대화 기록이 없거나 질문이 이미 독립적이면 질문을 그대로 반환하라.
- 재작성된 질문만 출력하라. 설명, 번호, prefix를 추가하지 마라.

대화 기록:
{chat_history}

후속 질문: {question}
독립 질문:"""

QA_SYSTEM_TEMPLATE = """당신은 포장재·코팅 기술 분야의 전문 연구 분석가입니다.
아래 [컨텍스트]를 근거로 [질문]에 최대한 충실히 답하세요.

반드시 준수할 규칙:
1. [컨텍스트]에 있는 내용을 최우선 근거로 사용하라. 컨텍스트 외부 지식으로 추측하거나 보완하지 마라.
2. 컨텍스트가 질문의 일부에만 관련되어 있어도 관련된 내용에 대해서는 반드시 답하라.
   - 답할 수 있는 내용을 먼저 제시하고, 컨텍스트에서 확인되지 않는 부분은 "해당 부분은 제공된 문서에서 확인되지 않습니다."라고 표시하라.
   - 컨텍스트가 질문과 완전히 무관할 때에만 "제공된 문서에서 해당 내용을 찾을 수 없습니다."로 시작하라.
3. 수치, 비율, 온도, 농도, 화학식, 공정 조건 등 정량적 정보는 원문을 그대로 인용하라. 해석하거나 단위 환산하지 마라.
4. 전문 용어는 [컨텍스트]에 사용된 표현을 그대로 사용하라. 임의로 번역, 동의어 대체, 일반화하지 마라.
5. 항상 한국어로 답변하라. 질문이 영어이더라도 한국어로 답하라.
6. 답변에 사용한 정보의 출처를 본문 내에서 명시하라.
   - 형식: `(출처: {{파일명}}, p.{{페이지번호}})`
   - 여러 출처를 사용한 경우 각 정보 뒤에 해당 출처를 붙여라.
   - 출처를 알 수 없는 내용은 답변에 포함하지 마라.
7. 답변을 마크다운 형식으로 구조화하여 가독성을 높여라. 내용 유형에 맞게 선택하라:
   - 여러 특성·장점·구성 요소 나열: 글머리 기호 목록 (- 항목)
   - 순서가 있는 절차·제조 단계: 번호 목록 (1. 단계)
   - 두 가지 이상 대상을 비교: 마크다운 표 (| 항목 | 값 | ... |)
   - 핵심 수치·화학식·공정 조건: **굵게** 강조
   - 복합 주제로 답변이 긴 경우: ### 소제목으로 섹션 구분
   - 단문 사실 답변: 형식 없이 자연스럽게 작성

[컨텍스트]
{context}

[질문]
{question}

[답변]"""


def format_context(docs: list[Document]) -> str:
    """
    Assemble retrieved documents into a formatted context string for Chain-2.

    Returns empty string for empty doc list.
    Each chunk is prefixed with [filename, p.N] and separated by ---.
    """
    if not docs:
        return ""
    parts = []
    for doc in docs:
        source = doc.metadata.get("source", "알 수 없음")
        page = doc.metadata.get("page", "?")
        parts.append(f"[{source}, p.{page}]\n{doc.page_content.strip()}")
    return "\n\n---\n\n".join(parts)


def build_condense_chain(llm: ChatOpenAI) -> RunnableSequence:
    """Build Chain-1: condenses follow-up questions into standalone queries."""
    prompt = PromptTemplate(
        input_variables=["chat_history", "question"],
        template=CONDENSE_QUESTION_TEMPLATE,
    )
    return prompt | llm | StrOutputParser()


def build_qa_chain(llm: ChatOpenAI) -> RunnableSequence:
    """Build Chain-2: answers questions using retrieved context."""
    prompt = PromptTemplate(
        input_variables=["context", "question"],
        template=QA_SYSTEM_TEMPLATE,
    )
    return prompt | llm | StrOutputParser()
