"""Text similarity functions used for cached-answer retrieval."""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable, List, Set, Tuple


@dataclass(frozen=True)
class SimilarityMatch:
    question_id: str
    question: str
    combined_score: float
    sequence_score: float
    jaccard_score: float


def tokenize(text: str) -> Set[str]:
    """Tokenize mixed Korean, English, and numeric text."""
    tokens = re.findall(r"[가-힣]+|[A-Za-z0-9]+", text.lower())
    return {token for token in tokens if len(token) > 1}


def jaccard_similarity(first: str, second: str) -> float:
    first_tokens, second_tokens = tokenize(first), tokenize(second)
    union = first_tokens | second_tokens
    return len(first_tokens & second_tokens) / len(union) if union else 0.0


def sequence_similarity(first: str, second: str) -> float:
    return SequenceMatcher(None, first.lower(), second.lower()).ratio()


def combined_similarity(first: str, second: str) -> Tuple[float, float, float]:
    sequence_score = sequence_similarity(first, second)
    jaccard_score = jaccard_similarity(first, second)
    combined_score = round(0.55 * sequence_score + 0.45 * jaccard_score, 4)
    return combined_score, sequence_score, jaccard_score


def rank_candidates(
    query: str, candidates: Iterable[tuple[str, str]]
) -> List[SimilarityMatch]:
    matches = []
    for question_id, question in candidates:
        combined, sequence, jaccard = combined_similarity(query, question)
        matches.append(
            SimilarityMatch(
                question_id=question_id,
                question=question,
                combined_score=combined,
                sequence_score=sequence,
                jaccard_score=jaccard,
            )
        )
    return sorted(matches, key=lambda match: match.combined_score, reverse=True)
