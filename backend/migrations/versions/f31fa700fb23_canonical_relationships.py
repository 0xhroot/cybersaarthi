"""canonical relationships: one row per logical edge

Revision ID: f31fa700fb23
Revises: 081a88d02574
Create Date: 2026-08-29 00:00:00.000000

A logical relationship (case, source entity, target entity, type) must map to
exactly one canonical row regardless of which source record or evidence
mechanism discovered it. Previously the unique key included ``source_record_id``,
so the same pair/type found in several records (structured field pairs and
free-text co-occurrence alike) produced duplicate rows - and therefore duplicate
graph edges in Neo4j and the graph API.

This migration:
  1. re-orients undirected (same entity-type) pairs so ``(a, b)`` and ``(b, a)``
     collapse to the same canonical orientation;
  2. preserves every discovery's provenance by moving ``relationship_evidence``
     rows under the retained relationship and deleting the duplicate rows;
  3. replaces the per-record unique constraint with the canonical one
     ``(case_id, source_entity_id, target_entity_id, relationship_type)``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f31fa700fb23"
down_revision: str | None = "081a88d02574"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Postgres row groups keyed on the canonical logical relationship; reused by
# all three data-fix statements (CTEs cannot be shared between statements).
# All three data-fix statements repeat the same duplicate-grouping CTE; it stays
# inline in each static ``op.execute`` text so ruff's SQL-injection guard is happy.


def upgrade() -> None:
    # 1. Canonical orientation for undirected (same entity-type) pairs: put the
    #    lexicographically smaller entity id in the source position.
    op.execute(
        sa.text(
            """
        WITH pair_ids AS (
            SELECT r.id AS rel_id,
                   LEAST(r.source_entity_id, r.target_entity_id) AS src,
                   GREATEST(r.source_entity_id, r.target_entity_id) AS dst
            FROM relationships r
            JOIN entities e1 ON e1.id = r.source_entity_id
            JOIN entities e2 ON e2.id = r.target_entity_id
            WHERE e1.entity_type = e2.entity_type
              AND r.source_entity_id <> r.target_entity_id
        )
        UPDATE relationships r
        SET source_entity_id = p.src, target_entity_id = p.dst
        FROM pair_ids p
        WHERE r.id = p.rel_id
          AND (r.source_entity_id <> p.src OR r.target_entity_id <> p.dst)
        """
        )
    )

    # 2. Keep only the earliest relationship per logical edge; move every
    #    discovery's evidence rows under the retained row (dropping any that
    #    already duplicate a (kept row, record, type) provenance entry), then
    #    delete the duplicate relationship rows.
    op.execute(
        sa.text(
            """
        WITH grouped AS (
            SELECT case_id, source_entity_id, target_entity_id, relationship_type,
                   MIN(id::text)::uuid AS keep_id
            FROM relationships
            GROUP BY case_id, source_entity_id, target_entity_id, relationship_type
        ),
        dups AS (
            SELECT r.id AS dup_id, g.keep_id
            FROM relationships r
            JOIN grouped g
              ON g.case_id = r.case_id
             AND g.source_entity_id = r.source_entity_id
             AND g.target_entity_id = r.target_entity_id
             AND g.relationship_type = r.relationship_type
            WHERE r.id <> g.keep_id
        )
        DELETE FROM relationship_evidence ev
        USING dups d
        WHERE ev.relationship_id = d.dup_id
          AND EXISTS (
              SELECT 1 FROM relationship_evidence other
              WHERE other.relationship_id = d.keep_id
                AND other.source_record_id IS NOT DISTINCT FROM ev.source_record_id
                AND other.evidence_type = ev.evidence_type
          )
        """
        )
    )
    op.execute(
        sa.text(
            """
        WITH grouped AS (
            SELECT case_id, source_entity_id, target_entity_id, relationship_type,
                   MIN(id::text)::uuid AS keep_id
            FROM relationships
            GROUP BY case_id, source_entity_id, target_entity_id, relationship_type
        ),
        dups AS (
            SELECT r.id AS dup_id, g.keep_id
            FROM relationships r
            JOIN grouped g
              ON g.case_id = r.case_id
             AND g.source_entity_id = r.source_entity_id
             AND g.target_entity_id = r.target_entity_id
             AND g.relationship_type = r.relationship_type
            WHERE r.id <> g.keep_id
        )
        UPDATE relationship_evidence ev
        SET relationship_id = d.keep_id
        FROM dups d
        WHERE ev.relationship_id = d.dup_id
        """
        )
    )
    op.execute(
        sa.text(
            """
        WITH grouped AS (
            SELECT case_id, source_entity_id, target_entity_id, relationship_type,
                   MIN(id::text)::uuid AS keep_id
            FROM relationships
            GROUP BY case_id, source_entity_id, target_entity_id, relationship_type
        ),
        dups AS (
            SELECT r.id AS dup_id, g.keep_id
            FROM relationships r
            JOIN grouped g
              ON g.case_id = r.case_id
             AND g.source_entity_id = r.source_entity_id
             AND g.target_entity_id = r.target_entity_id
             AND g.relationship_type = r.relationship_type
            WHERE r.id <> g.keep_id
        )
        DELETE FROM relationships r
        USING dups d
        WHERE r.id = d.dup_id
        """
        )
    )

    # 3. Enforce the canonical key at the database level.
    op.drop_constraint(
        "uq_relationships_case_src_dst_type_record",
        "relationships",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_relationships_case_src_dst_type",
        "relationships",
        ["case_id", "source_entity_id", "target_entity_id", "relationship_type"],
    )


def downgrade() -> None:
    # Restoring the per-record key cannot reproduce merged rows; this only
    # removes the canonical constraint so the pre-fix schema shape returns.
    op.drop_constraint(
        "uq_relationships_case_src_dst_type",
        "relationships",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_relationships_case_src_dst_type_record",
        "relationships",
        [
            "case_id",
            "source_entity_id",
            "target_entity_id",
            "relationship_type",
            "source_record_id",
        ],
    )
