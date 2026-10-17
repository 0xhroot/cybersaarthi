"""Deterministic validation for LLM structured-extraction output.

The model only ever produces *text*. A field is accepted into a derived artifact
when it survives all three deterministic stages:

1. :func:`parse_structured` - JSON recovery + strict pydantic schema validation
   (unknown fields and type errors reject the output, they are never coerced).
2. :func:`check_fields_against_source` - every accepted value must be found in
   the authorized source record it claims to come from, with numbers compared
   exactly (``Decimal``) and dates compared after deterministic normalization.
3. :func:`canonical_hash` - content-addressed hashing so identical derivations
   are idempotent and any later tampering with a payload is detectable.

Nothing here calls the LLM; these functions are the reason exact values can be
trusted regardless of what the model claimed.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ValidationError

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_CURRENCY_RE = re.compile(r"^[\u20b9$€£]\s*")
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y", "%d.%m.%Y")
_MIN_SUBSTRING_LEN = 3

_ISSUE_PATH_FALLBACK = ""


@dataclass(frozen=True)
class FieldIssue:
    """One deterministic problem found in model output or a field's provenance."""

    field: str
    code: str
    message: str

    def as_dict(self) -> dict[str, object]:
        return {"field": self.field, "code": self.code, "message": self.message}


@dataclass(frozen=True)
class ExtractionResult:
    """Outcome of schema validation; ``data`` is None when the schema failed."""

    data: dict[str, Any] | None
    issues: tuple[FieldIssue, ...]

    @property
    def status(self) -> str:
        if self.data is None:
            return "invalid"
        if self.issues:
            return "flagged"
        return "valid"

    @property
    def ok(self) -> bool:
        return self.status == "valid"


def parse_json_object(raw: str) -> dict[str, Any] | None:
    """Recover the first JSON *object* from model output.

    Tries the raw text first, then fenced ```json blocks, then the outermost
    ``{...}`` span (models often wrap JSON in prose). Returns None when no
    parseable object exists - callers must treat that as a hard failure.
    """
    text = raw.strip()
    if not text:
        return None
    candidates = [text]
    candidates.extend(match.group(1) for match in _FENCE_RE.finditer(text))
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def parse_structured[SchemaT: BaseModel](raw: str, schema: type[SchemaT]) -> ExtractionResult:
    """Validate model output against *schema*, collecting every issue.

    Unknown fields reject the result (schemas use pydantic's default extra=ignore
    so this check is the single, explicit enforcement point); schema type errors
    reject it too. A rejected result carries ``data=None`` and never reaches a
    derived artifact.
    """
    parsed = parse_json_object(raw)
    if parsed is None:
        return ExtractionResult(
            None,
            (FieldIssue(_ISSUE_PATH_FALLBACK, "malformed_json", "no JSON object in model output"),),
        )

    allowed = set(schema.model_fields)
    issues = [
        FieldIssue(key, "unknown_field", "field is not part of the extraction schema")
        for key in parsed
        if key not in allowed
    ]
    try:
        model = schema.model_validate(parsed)
    except ValidationError as exc:
        for err in exc.errors():
            path = ".".join(str(part) for part in err["loc"])
            issues.append(FieldIssue(path, "schema_error", err["msg"]))
        return ExtractionResult(None, tuple(issues))
    if issues:
        return ExtractionResult(None, tuple(issues))
    return ExtractionResult(model.model_dump(mode="json"), tuple(issues))


def canonical_hash(payload: Mapping[str, Any]) -> str:
    """sha256 over canonical JSON (sorted keys, no incidental whitespace)."""
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_text(value: str) -> str:
    """Whitespace-collapsed, casefolded form used for text comparisons."""
    return " ".join(value.split()).casefold()


def as_decimal(value: Any) -> Decimal | None:
    """Parse *value* as an exact Decimal (currency symbols and grouping stripped).

    Booleans are rejected (``bool`` subclasses ``int``); unparseable values
    return None rather than approximating.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int | float):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    if isinstance(value, str):
        text = _CURRENCY_RE.sub("", value.strip()).replace(",", "")
        if not text:
            return None
        try:
            return Decimal(text)
        except InvalidOperation:
            return None
    return None


def as_date(value: Any) -> date | None:
    """Deterministic date parse: ISO first, then unambiguous day-first formats."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    # Day-first among the slash formats (dd/mm/yyyy): the intake workflow's
    # documented convention; ambiguous inputs are flagged by callers instead of
    # being guessed a second way here.
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def values_equal(expected: Any, actual: Any) -> bool:
    """Strict equality for citation quotes: exact numbers, normalized text,
    or equal dates. Substring containment is deliberately NOT enough here -
    "1000" must not pass against "1000.50"."""
    if isinstance(expected, bool) or isinstance(actual, bool):
        return expected is actual or expected == actual and type(expected) is type(actual)
    exp_dec, act_dec = as_decimal(expected), as_decimal(actual)
    if exp_dec is not None and act_dec is not None:
        return exp_dec == act_dec
    if isinstance(expected, str) and isinstance(actual, str):
        exp_date, act_date = as_date(expected), as_date(actual)
        if exp_date is not None and act_date is not None:
            return exp_date == act_date
        return normalize_text(expected) == normalize_text(actual)
    exp_date, act_date = as_date(expected), as_date(actual)
    if exp_date is not None and act_date is not None:
        return exp_date == act_date
    return expected == actual


def value_matches_source(value: Any, source_values: Iterable[Any]) -> bool:
    """True when *value* is found among *source_values*.

    Text: exact normalized match or substring of a longer source string
    (names appear inside sentences). Numbers: exact Decimal equality against
    any source value, so grouping/currency formatting never loses precision.
    Dates: equal after deterministic normalization. Lists: every element must
    match. This is the check that stops the model inventing amounts, dates or
    identifiers that are not in the evidence.
    """
    sources = list(source_values)
    if isinstance(value, list):
        if not value:
            return True
        return all(
            item is None or value_matches_source(item, sources) for item in value
        )
    if isinstance(value, dict | tuple):
        return False
    if value is None:
        return True
    if isinstance(value, bool):
        return any(type(source) is bool and source is value for source in sources)

    if isinstance(value, int | float):
        numeric = as_decimal(value)
        if numeric is None:
            return False
        return any(as_decimal(source) == numeric for source in sources)

    if isinstance(value, str):
        target = normalize_text(value)
        if not target:
            return False
        for source in sources:
            if source is None:
                continue
            if isinstance(source, str):
                source_norm = normalize_text(source)
                if source_norm == target or (
                    len(target) >= _MIN_SUBSTRING_LEN and target in source_norm
                ):
                    return True
            elif isinstance(source, int | float | Decimal) and not isinstance(source, bool):
                source_dec = as_decimal(source)
                claimed_dec = as_decimal(value)
                if source_dec is not None and claimed_dec is not None and source_dec == claimed_dec:
                    return True
            elif isinstance(source, date | datetime):
                source_date = as_date(source)
                claimed_date = as_date(value)
                if (
                    source_date is not None
                    and claimed_date is not None
                    and source_date == claimed_date
                ):
                    return True
        # Numeric-looking strings also compare exactly against numeric sources
        # (grouping/currency differences must not mask a match or a mismatch).
        claimed_dec = as_decimal(value)
        if claimed_dec is not None:
            if any(as_decimal(source) == claimed_dec for source in sources):
                return True
        claimed_date = as_date(value)
        if claimed_date is not None:
            # Date-form strings normalize across formats (15/03/2026 == 2026-03-15).
            for source in sources:
                source_date = as_date(source)
                if source_date is not None and source_date == claimed_date:
                    return True
        return False

    return any(source == value for source in sources)


def _flatten(source: Any) -> list[Any]:
    """Flatten nested dicts/lists so lookups see every stored value."""
    out: list[Any] = []
    if isinstance(source, Mapping):
        for item in source.values():
            out.extend(_flatten(item))
    elif isinstance(source, list | tuple):
        for item in source:
            out.extend(_flatten(item))
    else:
        out.append(source)
    return out


def check_fields_against_source(
    data: Mapping[str, Any],
    source: Mapping[str, Any],
    *,
    locators: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[FieldIssue, ...]:
    """Validate every field of a schema-passing extraction against its source.

    Checks (per field, deterministic, all reported - never silently dropped):
    - ``locator_invalid``: the claimed source field does not exist in the record.
    - ``unsupported_field_type``: structured dict values cannot be source-checked.
    - ``value_not_in_source``: the value is absent from the flattened source.

    Returns an empty tuple only when every field is backed by the source; the
    caller stores the issues alongside the payload for reviewer visibility.
    """
    issues: list[FieldIssue] = []
    flat_source = _flatten(source)
    for name, value in data.items():
        if locators is not None and name in locators:
            locator = locators[name]
            claimed_field = locator.get("field")
            if not isinstance(claimed_field, str) or claimed_field not in source:
                issues.append(
                    FieldIssue(
                        name,
                        "locator_invalid",
                        f"locator field {claimed_field!r} not present in source record",
                    )
                )
        if value is None:
            continue
        if isinstance(value, dict):
            issues.append(
                FieldIssue(
                    name,
                    "unsupported_field_type",
                    "structured values cannot be source-checked field-by-field",
                )
            )
            continue
        if not value_matches_source(value, flat_source):
            issues.append(
                FieldIssue(
                    name,
                    "value_not_in_source",
                    f"value {value!r} not found in source record",
                )
            )
    return tuple(issues)
