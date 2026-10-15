"""Approved local documentation search (read-only, allowlisted paths).

The knowledge tool answers "how does CyberSaarthi…" questions from the
repository's own markdown docs — never from arbitrary files and never from
the network. Only the files matched by the allowlist globs are readable, each
file is size-capped, and the model only ever sees heading-scoped chunks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.ai.schemas import SourceRef

# Allowlisted documentation roots, relative to the repo root. Keep tight: this
# list is the entire filesystem surface the knowledge tool can read.
ALLOWLIST_GLOBS = (
    "README.md",
    "docs/*.md",
    "docs/ai/*.md",
)

MAX_FILE_BYTES = 128_000
CHUNK_MAX_CHARS = 1_800
TOP_CHUNKS = 4
_TOKEN_RE = re.compile(r"[a-z0-9_]{3,}")


@dataclass(slots=True)
class KnowledgeChunk:
    doc: str  # repo-relative path
    heading: str
    text: str
    score: float

    def as_source(self) -> SourceRef:
        return SourceRef(type="knowledge", id=f"{self.doc}#{self.heading}", label=self.heading)


def _repo_root() -> Path:
    from app.core.config import get_settings

    return get_settings().repo_root


def _allowlisted_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for pattern in ALLOWLIST_GLOBS:
        for path in sorted(root.glob(pattern)):
            if path.is_file() and path.stat().st_size <= MAX_FILE_BYTES:
                resolved = path.resolve()
                # Defense in depth: never escape the repo root.
                if resolved.is_relative_to(root.resolve()):
                    files.append(resolved)
    return files


def _split_chunks(text: str, doc: str) -> list[tuple[str, str]]:
    """Split markdown on headings into (heading, body) pairs."""
    chunks: list[tuple[str, str]] = []
    heading = "preamble"
    lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("#"):
            if lines:
                chunks.append((heading, "\n".join(lines).strip()))
                lines = []
            heading = line.lstrip("# ").strip()[:120] or heading
        else:
            lines.append(line)
    if lines:
        chunks.append((heading, "\n".join(lines).strip()))
    # Merge tiny chunks and enforce the per-chunk cap.
    merged: list[tuple[str, str]] = []
    for head, body in chunks:
        if not body:
            continue
        if merged and len(merged[-1][1]) + len(body) < CHUNK_MAX_CHARS // 2:
            merged[-1] = (merged[-1][0], merged[-1][1] + "\n\n" + body)
        else:
            merged.append((head, body[:CHUNK_MAX_CHARS]))
    return merged


def search(root: Path, query: str, *, top_k: int = TOP_CHUNKS) -> list[KnowledgeChunk]:
    """Case-insensitive token-overlap keyword search over allowlisted docs."""
    tokens = set(_TOKEN_RE.findall(query.lower()))
    if not tokens:
        return []
    scored: list[KnowledgeChunk] = []
    for path in _allowlisted_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(path.relative_to(root.resolve()))
        for heading, body in _split_chunks(text, rel):
            haystack = f"{heading}\n{body}".lower()
            hits = sum(1 for token in tokens if token in haystack)
            if hits == 0:
                continue
            scored.append(
                KnowledgeChunk(
                    doc=rel,
                    heading=heading,
                    text=body[:CHUNK_MAX_CHARS],
                    score=float(hits) / len(tokens),
                )
            )
    scored.sort(key=lambda chunk: chunk.score, reverse=True)
    return scored[:top_k]


def format_chunks(chunks: list[KnowledgeChunk]) -> str:
    if not chunks:
        return "No matching documentation excerpts found."
    parts: list[str] = []
    for chunk in chunks:
        parts.append(
            f"--- doc={chunk.doc} section={chunk.heading!r} relevance={chunk.score:.2f} ---\n"
            f"{chunk.text}"
        )
    return "\n\n".join(parts)
