"""Cross-encoder reranker — 트랜스포머 기반 문맥 파악 재순위화.

BAAI/bge-reranker-base (한국어·다국어 특화)를 사용하여 (쿼리, 문서) 쌍의
실제 관련성을 평가한다. 코사인 유사도보다 문맥과 의미를 정밀하게 포착.

모델은 최초 사용 시 1회 로드 (lazy singleton). 미설치·로드 실패 시
원본 embedding 순서로 폴백하여 시스템이 중단되지 않는다.
"""

import logging
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

_reranker = None


def _get_reranker():
    """Return a cached CrossEncoder model, initialised once."""
    global _reranker
    if _reranker is None:
        try:
            from sentence_transformers import CrossEncoder
            from config import RERANKER_MODEL
            logger.info("Cross-encoder 로드 중: %s (최초 1회)", RERANKER_MODEL)
            _reranker = CrossEncoder(RERANKER_MODEL, max_length=512)
            logger.info("Cross-encoder 준비 완료")
        except ImportError:
            logger.warning(
                "sentence-transformers 미설치 — Reranking 비활성화. "
                "'pip install sentence-transformers' 실행 필요"
            )
        except Exception as e:
            logger.error("Cross-encoder 로드 실패 (폴백 사용): %s", e)
    return _reranker


def rerank(query: str, docs: list[Document], top_k: int) -> list[Document]:
    """Cross-encoder로 문서를 재순위화하여 상위 top_k개 반환.

    Args:
        query: 사용자 질문 (독립형으로 응축된 것).
        docs:  embedding 유사도로 사전 필터링된 후보 문서들.
        top_k: 반환할 최종 문서 수.

    Returns:
        Cross-encoder 점수 내림차순으로 정렬된 top_k개 문서.
        Reranker 불가 시 원본 순서에서 top_k개 반환.
    """
    if not docs:
        return []

    if len(docs) <= top_k:
        # 후보가 이미 적으면 재순위화 의미 없음
        return docs

    model = _get_reranker()
    if model is None:
        logger.debug("Reranker 없음, embedding 순서 사용 (상위 %d)", top_k)
        return docs[:top_k]

    try:
        pairs = [(query, doc.page_content) for doc in docs]
        scores = model.predict(pairs)

        scored = sorted(
            zip(scores, docs),
            key=lambda x: float(x[0]),
            reverse=True,
        )

        top_docs = [doc for _, doc in scored[:top_k]]
        top_scores = [float(s) for s, _ in scored[:top_k]]

        logger.debug(
            "Reranking %d→%d 문서 | 점수: %s",
            len(docs),
            len(top_docs),
            [f"{s:.3f}" for s in top_scores],
        )
        return top_docs

    except Exception as e:
        logger.warning("Reranking 실패, embedding 순서 사용: %s", e)
        return docs[:top_k]
