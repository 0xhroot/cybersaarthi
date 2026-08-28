"""Lazy spaCy wrapper for named entity recognition.

The model is loaded once per process. NER failures degrade gracefully: callers
can fall back to rule-based extraction, keeping the pipeline deterministic and
testable even when the model is unavailable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

# spaCy label -> our controlled entity types.
NER_LABEL_MAP: dict[str, str] = {
    "PERSON": "person",
    "ORG": "organization",
    "GPE": "location",
    "LOC": "location",
    "EVENT": "event",
}


@dataclass(frozen=True)
class NerMention:
    entity_type: str
    text: str
    start: int
    end: int


@lru_cache(maxsize=16)
def get_nlp(model_name: str) -> Any:
    import spacy

    return spacy.load(model_name)


def load_nlp(model_name: str) -> Any | None:
    """Load the model, returning None instead of raising on failure."""
    try:
        return get_nlp(model_name)
    except Exception:
        logger.exception("spaCy model %s could not be loaded; NER disabled", model_name)
        return None


def extract_ner_mentions(text: str, model_name: str) -> list[NerMention]:
    """Named entity mentions in ``text`` mapped to our controlled types."""
    nlp = load_nlp(model_name)
    if nlp is None or not text.strip():
        return []
    doc = nlp(text)
    mentions: list[NerMention] = []
    for ent in doc.ents:
        entity_type = NER_LABEL_MAP.get(ent.label_)
        if entity_type is None:
            continue
        mentions.append(
            NerMention(
                entity_type=entity_type,
                text=ent.text,
                start=ent.start_char,
                end=ent.end_char,
            )
        )
    return mentions
