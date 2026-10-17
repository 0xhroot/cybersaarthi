"""Strict structured-output contract for the smart ingestion copilot (feature 1).

Every field is required with no defaults: a truncated or partial model reply
fails schema validation explicitly instead of silently dropping fields, and
unknown fields reject the whole reply (enforced by
``app.services.structured_extraction.parse_structured``). Items are non-empty
bounded strings so empty/garbage entries surface as schema errors.

Values are always *strings copied from the source*: monetary amounts keep the
verbatim digits and currency symbol (exact ``Decimal`` comparison happens in
the validator - never binary float), dates keep their original format including
any explicit time-zone text. Nothing here converts a syntactically valid reply
into a verified case fact; source verification and human review are separate
stages.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

ExtractedString = Annotated[str, Field(min_length=1, max_length=600)]


class EvidenceExtractionSchema(BaseModel):
    """One evidence page/record distilled into bounded, source-checkable lists."""

    person_names: list[ExtractedString]
    organization_names: list[ExtractedString]
    phone_numbers: list[ExtractedString]
    email_addresses: list[ExtractedString]
    account_references: list[ExtractedString]
    transaction_amounts: list[ExtractedString]
    transaction_dates: list[ExtractedString]
    urls: list[ExtractedString]
    domains: list[ExtractedString]
    device_identifiers: list[ExtractedString]
    statements: list[ExtractedString]
    events: list[ExtractedString]
