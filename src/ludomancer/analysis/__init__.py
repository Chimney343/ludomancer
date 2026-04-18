"""Analysis pipeline for feature extraction, ranking, and payload building."""

from ludomancer.analysis.features import build_corpus, fit_vectorizer
from ludomancer.analysis.recommender import classify, genre_centroid, recommend
from ludomancer.analysis.summary import build_llm_payload

__all__ = [
    "build_corpus",
    "build_llm_payload",
    "classify",
    "fit_vectorizer",
    "genre_centroid",
    "recommend",
]
