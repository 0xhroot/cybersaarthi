"""Unit tests: allowlisted documentation search (knowledge tool)."""

from __future__ import annotations

from pathlib import Path

from app.ai import knowledge


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_only_allowlisted_globs_are_readable(tmp_path: Path) -> None:
    _write(tmp_path, "README.md", "# Readme\n\nEvidence ingestion overview.\n")
    _write(tmp_path, "docs/guide.md", "# Guide\n\nHow to run analytics.\n")
    _write(tmp_path, "docs/ai/setup.md", "# Setup\n\nLocal model runtime.\n")
    _write(tmp_path, "secrets/notes.md", "# Secret\n\nThis must never surface.\n")
    _write(tmp_path, "docs/nested/deep.md", "# Deep\n\nNot matched by docs/*.md.\n")

    files = knowledge._allowlisted_files(tmp_path)
    rels = {str(p.relative_to(tmp_path)) for p in files}
    assert rels == {"README.md", "docs/guide.md", "docs/ai/setup.md"}


def test_oversized_files_are_skipped(tmp_path: Path) -> None:
    _write(tmp_path, "README.md", "x" * (knowledge.MAX_FILE_BYTES + 1))
    assert knowledge._allowlisted_files(tmp_path) == []


def test_search_finds_token_overlap_and_ranks(tmp_path: Path) -> None:
    _write(tmp_path, "README.md", "# Title\n\nEvidence ingestion pipeline details.\n")
    _write(
        tmp_path,
        "docs/analytics.md",
        "# Analytics\n\nAnalytics and PageRank centrality metrics.\n",
    )

    chunks = knowledge.search(tmp_path, "analytics centrality")
    assert chunks
    assert chunks[0].doc == "docs/analytics.md"
    assert chunks[0].score > 0


def test_search_ignores_files_outside_allowlist(tmp_path: Path) -> None:
    _write(tmp_path, "private/leak.md", "# Leak\n\nanalytics analytics analytics\n")
    assert knowledge.search(tmp_path, "analytics") == []


def test_search_empty_or_stopwordish_query_returns_empty(tmp_path: Path) -> None:
    _write(tmp_path, "README.md", "# Title\n\nSome content.\n")
    assert knowledge.search(tmp_path, "   ") == []


def test_format_chunks_empty_message() -> None:
    assert "No matching" in knowledge.format_chunks([])


def test_chunk_text_is_capped(tmp_path: Path) -> None:
    body = "word " * 2000
    _write(tmp_path, "README.md", f"# Big\n\n{body}\n")
    chunks = knowledge.search(tmp_path, "word", top_k=1)
    assert chunks
    assert len(chunks[0].text) <= knowledge.CHUNK_MAX_CHARS
