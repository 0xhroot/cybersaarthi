"""Digital forensics triage copilot (phase 5B, feature 8).

Deterministic parsing and rule-based observations over supported digital
artifacts, plus ONE bounded local-model explanation of the RECORDED
observations. CyberSaarthi performs no device acquisition, no file execution
and no malware analysis: URLs are never fetched, resolved or opened (no
network call exists in this module), and an observation is an observation -
a "malicious" verdict is never emitted.

Design (see ``docs/ai/PHASE_5_6_7_PLAN.md`` §3):

- **Parsers operate on already-parsed source records**; hash-manifest entries
  are re-verified against the case's *stored object bytes* (sha-256 via
  ``validation.fingerprint``), never against model output.
- **Rules are deterministic and structural**, each carrying severity and a
  record locator. Evidence with no parseable forensic structure (pure prose)
  is a typed refusal (``TRIAGE_UNSUPPORTED_CONTENT``) - never an empty
  success.
- **The model explanation is fenced, bounded and validated**: it may only
  describe the recorded observations, and a failed or malformed reply is
  recorded in the payload (artifact flagged) while the deterministic
  observations stay reviewable. A model *exception* additionally marks the
  job ``partial`` - an outage is never reported as clean success.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import re
import uuid
from collections import Counter
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rbac
from app.core.codes import (
    CODE_CASE_ACCESS_DENIED,
    CODE_EVIDENCE_NOT_FOUND,
    CODE_EVIDENCE_UNAVAILABLE,
    CODE_INTEGRITY_MISMATCH,
    CODE_INTEGRITY_SOURCE_MISSING,
    CODE_OCR_REQUIRED,
    CODE_TRIAGE_ACTIVE,
    CODE_TRIAGE_FAILED,
    CODE_TRIAGE_UNSUPPORTED_CONTENT,
    CODE_UNSUPPORTED_FORMAT,
)
from app.core.config import Settings
from app.core.enums import EvidenceFormat
from app.models import AnalysisJob, EvidenceFile, SourceRecord
from app.repositories.evidence_repository import EvidenceRepository
from app.services import analysis_jobs as jobs_svc
from app.services import artifacts as artifacts_svc
from app.services import audit as audit_svc
from app.services import authorization as authz_svc
from app.services.parsing import OCRRequiredError, ParseError, parse
from app.services.structured_extraction import parse_json_object
from app.services.validation import (
    UploadValidationError,
    detect_encoding,
    detect_format,
    fingerprint,
)

logger = logging.getLogger(__name__)

TRIAGE_RULES_VERSION = "1.0.0"

# Deterministic rule ids and their severities. Observations only - no
# intent, payload or "malicious" classification is ever produced.
TRIAGE_RULES: dict[str, str] = {
    "triage.url.userinfo": "high",
    "triage.url.ip_host": "high",
    "triage.url.punycode": "medium",
    "triage.url.nonstandard_port": "low",
    "triage.email.missing_message_id": "low",
    "triage.email.return_path_mismatch": "medium",
    "triage.manifest.hash_mismatch": "high",
    "triage.manifest.entry_missing": "medium",
    "triage.history.cross_scheme_redirect_chain_hint": "info",
    "triage.log.auth_failure_burst": "high",
}

# Structural analysis caps (beyond the settings-level record/url caps).
_MAX_OBSERVATIONS = 200
_MAX_LOG_LINES = 5000
_MAX_EXCERPTS = 8
_EXCERPT_CHARS = 400

_URL_RE = re.compile(r"https?://[^\s<>\"')\]\}]+", re.IGNORECASE)
_SHA256_RE = re.compile(r"\b[0-9a-fA-F]{64}\b")
_EMAIL_LINE_RE = re.compile(r"^([A-Za-z][A-Za-z0-9-]{1,40}):\s?(.*)$")
_AUTH_RESULT_RE = re.compile(
    r"\b(spf|dkim|dmarc)\s*=\s*(pass|fail|none|softfail|permerror|temperror)\b",
    re.IGNORECASE,
)
_TIMESTAMP_RE = re.compile(
    r"\b(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)\b"
)
_SEVERITY_RE = re.compile(
    r"\b(critical|fatal|emergency|alert|error|err|fail|failed|failure|denied|"
    r"warn|warning|notice|info|information|debug|trace)\b",
    re.IGNORECASE,
)
_AUTH_WORD_RE = re.compile(
    r"\b(auth|authentication|authenticate|authorized|login|logon|signin|"
    r"password|passwd|credential)\w*\b",
    re.IGNORECASE,
)
_FAIL_WORD_RE = re.compile(r"\b(fail\w*|denied|invalid|rejected|locked)\w*\b", re.IGNORECASE)
_SOURCE_TOKEN_RE = re.compile(r"^[A-Za-z][\w.\-]{1,40}$")

# Severity token -> normalized severity (first match by this priority wins).
_SEVERITY_PRIORITY: tuple[tuple[str, str], ...] = (
    ("critical", "critical"),
    ("fatal", "critical"),
    ("emergency", "critical"),
    ("alert", "critical"),
    ("error", "error"),
    ("err", "error"),
    ("failure", "error"),
    ("failed", "error"),
    ("fail", "error"),
    ("denied", "error"),
    ("warning", "warning"),
    ("warn", "warning"),
    ("notice", "notice"),
    ("information", "info"),
    ("info", "info"),
    ("debug", "debug"),
    ("trace", "debug"),
)

_EMAIL_HEADER_KEYS = {
    "from",
    "to",
    "cc",
    "subject",
    "date",
    "message-id",
    "return-path",
    "received",
    "x-originating-ip",
    "received-spf",
    "authentication-results",
    "dkim-signature",
    "reply-to",
    "mime-version",
    "content-type",
}
_HISTORY_URL_KEYS = ("url", "link", "urladdress", "pageurl")
_HISTORY_TITLE_KEYS = ("title", "pagetitle", "name")
_HISTORY_TIME_KEYS = (
    "visitedat",
    "visittime",
    "timestamp",
    "time",
    "date",
    "lastvisit",
    "visitdate",
)
_MANIFEST_NAME_HINTS = ("filename", "filepath", "file", "name", "path")


class TriageRejected(Exception):
    """Typed refusal for a triage submission (code + human message)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class TriageRunError(Exception):
    """Internal run failure carrying a typed code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# --- deterministic parsers ---------------------------------------------------


def _norm_key(key: Any) -> str:
    return re.sub(r"[\s_\-]+", "", str(key)).strip().lower()


def _first_value(row: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    normalized = {_norm_key(k): v for k, v in row.items()}
    for key in keys:
        value = normalized.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def analyze_url(url: str) -> dict[str, Any]:
    """Structural (never networked) analysis of one URL string.

    Nothing here resolves, fetches or opens the URL: only ``urlsplit`` and
    ``ipaddress`` parse the recorded string.
    """
    result: dict[str, Any] = {
        "url": url[:300],
        "length": len(url),
        "scheme": "",
        "host": "",
        "port": None,
        "userinfo": False,
        "ip_host": False,
        "punycode": False,
        "nonstandard_port": False,
        "subdomain_depth": 0,
        "query_tokens": 0,
        "parse_error": False,
    }
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        try:
            port = parts.port
        except ValueError:
            port = None
            result["parse_error"] = True
    except ValueError:
        result["parse_error"] = True
        return result
    result["scheme"] = parts.scheme.lower()
    result["host"] = host[:253]
    result["port"] = port
    result["userinfo"] = "@" in parts.netloc
    if port is not None and port not in (80, 443):
        result["nonstandard_port"] = True
    try:
        ipaddress.ip_address(host)
        result["ip_host"] = True
    except ValueError:
        pass
    result["punycode"] = "xn--" in host
    labels = [label for label in host.split(".") if label]
    result["subdomain_depth"] = max(0, len(labels) - 2) if len(labels) >= 2 else len(labels)
    result["query_tokens"] = len(parse_qsl(parts.query, keep_blank_values=True))
    return result


def extract_urls(text: str, *, limit: int) -> list[str]:
    """Unique http(s) URLs in first-occurrence order (never fetched)."""
    seen: dict[str, None] = {}
    for match in _URL_RE.finditer(text):
        url = match.group(0).rstrip(".,;:!")
        if url:
            seen.setdefault(url, None)
        if len(seen) >= limit:
            break
    return list(seen)


def parse_email_headers(row: dict[str, Any], text: str) -> dict[str, list[str]] | None:
    """Recognized e-mail headers from a csv/json row or ``Key: value`` lines.

    Returns ``None`` unless at least two recognized headers are present (a
    single From-like field in ordinary prose is not an e-mail structure).
    """
    headers: dict[str, list[str]] = {}
    for key, value in row.items():
        norm = str(key).strip().lower()
        if norm in _EMAIL_HEADER_KEYS and str(value).strip():
            headers.setdefault(norm, []).append(str(value).strip()[:500])
    for line in text.splitlines():
        match = _EMAIL_LINE_RE.match(line.strip())
        if match and match.group(1).lower() in _EMAIL_HEADER_KEYS:
            value = match.group(2).strip()
            if value:
                headers.setdefault(match.group(1).lower(), []).append(value[:500])
    if len(headers) < 2:
        return None
    return headers


def parse_authentication_results(headers: dict[str, list[str]]) -> dict[str, str]:
    """SPF/DKIM/DMARC results when an Authentication-Results header exists."""
    out: dict[str, str] = {}
    for value in headers.get("authentication-results", []) + headers.get("received-spf", []):
        for match in _AUTH_RESULT_RE.finditer(value):
            out.setdefault(match.group(1).lower(), match.group(2).lower())
    return out


def _address_domain(value: str) -> str | None:
    """Domain part of one address/header value (``Name <a@b>`` aware)."""
    inside = re.search(r"<([^>]+)>", value)
    address = inside.group(1) if inside else value
    at = address.rfind("@")
    if at < 0 or at == len(address) - 1:
        return None
    domain = address[at + 1 :].strip().strip(".").lower()
    return domain or None


def parse_history_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize browser-history rows (url/title/visit fields)."""
    entries: list[dict[str, Any]] = []
    for row in rows:
        url = _first_value(row, _HISTORY_URL_KEYS)
        if url is None:
            continue
        entries.append(
            {
                "url": url[:500],
                "title": (_first_value(row, _HISTORY_TITLE_KEYS) or "")[:200] or None,
                "visited_at": _first_value(row, _HISTORY_TIME_KEYS),
            }
        )
    return entries


def summarize_history(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-domain visit counts, first/last recorded visit, cross-scheme hint.

    ``first``/``last`` compare the recorded strings lexicographically (valid
    for ISO-like timestamps); no timezone claim is made about them.
    """
    visits: Counter[str] = Counter()
    first: dict[str, str] = {}
    last: dict[str, str] = {}
    schemes: dict[str, set[str]] = {}
    host_record: dict[str, int] = {}
    for entry in entries:
        info = analyze_url(entry["url"])
        host = info["host"] or "(no host)"
        visits[host] += 1
        schemes.setdefault(host, set()).add(info["scheme"])
        host_record.setdefault(host, int(entry.get("record_no") or 0))
        stamp = entry.get("visited_at")
        if isinstance(stamp, str) and stamp:
            if host not in first or stamp < first[host]:
                first[host] = stamp
            if host not in last or stamp > last[host]:
                last[host] = stamp
    top = sorted(visits.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    cross_scheme = sorted(host for host, seen in schemes.items() if {"http", "https"} <= seen)
    return {
        "visits_total": len(entries),
        "domains": len(visits),
        "top_domains": [
            {
                "host": host,
                "visits": count,
                "first": first.get(host),
                "last": last.get(host),
            }
            for host, count in top
        ],
        "cross_scheme_hosts": [
            {"host": host, "record_no": host_record.get(host, 0)} for host in cross_scheme
        ],
    }


def manifest_entry_from_row(
    record_no: int, row: dict[str, Any], text: str
) -> dict[str, Any] | None:
    """One ``{record_no, sha256, filename}`` manifest entry, if present."""
    sha: str | None = None
    for key, value in row.items():
        if "sha256" in _norm_key(key):
            match = _SHA256_RE.search(str(value))
            if match:
                sha = match.group(0).lower()
                break
    if sha is None:
        for value in row.values():
            match = _SHA256_RE.search(str(value))
            if match:
                sha = match.group(0).lower()
                break
    if sha is None:
        match = _SHA256_RE.search(text)
        if match:
            sha = match.group(0).lower()
    if sha is None:
        return None
    filename: str | None = None
    for key, value in row.items():
        norm = _norm_key(key)
        if any(hint in norm for hint in _MANIFEST_NAME_HINTS):
            candidate = str(value).strip()
            if candidate and _SHA256_RE.fullmatch(candidate) is None:
                filename = candidate[:256]
                break
    if filename is None:
        tokens = text.split()
        for index, token in enumerate(tokens):
            if token.lower().strip(",;|") != sha:
                continue
            for neighbor in tokens[index + 1 : index + 2] + tokens[max(0, index - 1) : index]:
                cleaned = neighbor.strip(",;|")
                if cleaned and _SHA256_RE.fullmatch(cleaned) is None:
                    filename = cleaned[:256]
                    break
            if filename:
                break
    return {"record_no": record_no, "sha256": sha, "filename": filename}


def manifest_verdicts(
    entries: list[dict[str, Any]], available: dict[str, str | None]
) -> list[dict[str, Any]]:
    """Deterministic verdict per manifest entry.

    ``available`` maps lowercased filename -> recomputed sha-256 of the
    stored bytes (``None`` value = object missing). Verdicts: ``match``,
    ``mismatch``, ``missing`` (no such file in the case) or
    ``object_unavailable`` (row exists, stored bytes are gone).
    """
    out: list[dict[str, Any]] = []
    for entry in entries:
        name = (entry.get("filename") or "").strip().lower()
        if not name or name not in available:
            verdict, computed = "missing", None
        elif available[name] is None:
            verdict, computed = "object_unavailable", None
        elif available[name] == entry["sha256"]:
            verdict, computed = "match", available[name]
        else:
            verdict, computed = "mismatch", available[name]
        out.append({**entry, "verdict": verdict, "computed_sha256": computed})
    return out


def parse_log_lines(text: str, *, record_no: int) -> list[dict[str, Any]]:
    """Timestamped severity lines (source token, auth-failure marker)."""
    lines: list[dict[str, Any]] = []
    for raw_line in text.splitlines()[:_MAX_LOG_LINES]:
        line = raw_line.strip()
        if not line:
            continue
        stamp_match = _TIMESTAMP_RE.search(line)
        severity_match = _SEVERITY_RE.search(line)
        if stamp_match is None or severity_match is None:
            continue
        token = severity_match.group(1).lower()
        severity = next((norm for key, norm in _SEVERITY_PRIORITY if key == token), "info")
        source = "unknown"
        for candidate in line.split()[1:4]:
            cleaned = candidate.strip("[],():;")
            if _SOURCE_TOKEN_RE.match(cleaned) and cleaned.lower() != token:
                source = cleaned[:40]
                break
        auth_failure = bool(_AUTH_WORD_RE.search(line) and _FAIL_WORD_RE.search(line))
        lines.append(
            {
                "record_no": record_no,
                "timestamp": stamp_match.group(1),
                "severity": severity,
                "source": source,
                "auth_failure": auth_failure,
            }
        )
    return lines


def _parse_timestamp(value: str) -> datetime | None:
    text = value.strip()
    if " " in text and "T" not in text:
        text = text.replace(" ", "T", 1)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def auth_failure_burst(
    events: list[dict[str, Any]], *, threshold: int = 5, window_seconds: int = 600
) -> dict[str, Any] | None:
    """Burst of auth-failure lines within one window (timestamps required)."""
    stamps: list[tuple[datetime, dict[str, Any]]] = []
    for event in events:
        parsed = _parse_timestamp(str(event.get("timestamp") or ""))
        if parsed is not None:
            stamps.append((parsed, event))
    stamps.sort(key=lambda pair: pair[0])
    for index, (start, first_event) in enumerate(stamps):
        window = [
            (stamp, event)
            for stamp, event in stamps[index:]
            if (stamp - start).total_seconds() <= window_seconds
        ]
        if len(window) >= threshold:
            return {
                "count": len(window),
                "window_seconds": window_seconds,
                "first": window[0][0].isoformat(),
                "last": window[-1][0].isoformat(),
                "record_no": int(first_event.get("record_no") or 0),
            }
    return None


def _parse_explanation(text: str) -> dict[str, Any] | None:
    """Validate the model's explanation JSON (summary + three lists)."""
    data = parse_json_object(text)
    if not isinstance(data, dict):
        return None
    summary = data.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return None
    out: dict[str, Any] = {"summary": summary.strip()[:1000]}
    for key in ("explanations", "not_established", "verification_steps"):
        value = data.get(key, [])
        if not isinstance(value, list):
            return None
        out[key] = [str(item)[:500] for item in value if str(item).strip()][:20]
    return out


# --- deterministic analysis over records -------------------------------------


def _unit_content(record: SourceRecord, fmt: EvidenceFormat | None) -> str:
    raw = dict(record.raw_data or {})
    page = raw.get("page")
    if isinstance(page, int) and isinstance(raw.get("text"), str):
        return str(raw["text"])
    if fmt == EvidenceFormat.TXT and isinstance(raw.get("text"), str):
        return str(raw["text"])
    strings = [str(v) for v in raw.values() if isinstance(v, str)]
    if strings:
        return "\n".join(strings)
    return json.dumps(raw, ensure_ascii=False, default=str)


def triage_contents(
    contents: list[tuple[SourceRecord, str]], *, settings: Settings
) -> dict[str, Any]:
    """Deterministic parse + rules over (record, text) pairs.

    Pure: no session, storage, network or model access. Manifest entries are
    *detected* here; byte verification is the caller's async step.
    """
    profile: dict[str, Any] = {
        "records_scanned": len(contents),
        "email_header_records": 0,
        "history_rows": 0,
        "manifest_entries": 0,
        "log_lines": 0,
        "urls_found": 0,
        "observations_truncated": False,
    }
    email_headers: list[dict[str, Any]] = []
    auth_results: list[dict[str, Any]] = []
    url_reports: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    missing: list[str] = []
    record_by_no = {record.record_no: record for record, _ in contents}

    def observe(rule: str, record: SourceRecord, detail: dict[str, Any]) -> None:
        if len(observations) >= _MAX_OBSERVATIONS:
            profile["observations_truncated"] = True
            return
        observations.append(
            {
                "rule": rule,
                "severity": TRIAGE_RULES[rule],
                "locator": {"record_no": record.record_no},
                "detail": detail,
            }
        )

    # 1. E-mail headers + URL collection.
    seen_urls: dict[str, int] = {}
    any_message_id = False
    any_auth_results = False
    any_return_path = False
    for record, text in contents:
        row = dict(record.raw_data or {})
        headers = parse_email_headers(row, text)
        if headers is not None:
            profile["email_header_records"] += 1
            email_headers.append(
                {"record_no": record.record_no, "headers": {k: v[:3] for k, v in headers.items()}}
            )
            auth = parse_authentication_results(headers)
            if auth:
                any_auth_results = True
                auth_results.append({"record_no": record.record_no, **auth})
            if "message-id" in headers:
                any_message_id = True
            else:
                observe(
                    "triage.email.missing_message_id",
                    record,
                    {"present": False, "headers_seen": sorted(headers)},
                )
            if headers.get("return-path"):
                any_return_path = True
                return_path_domain = _address_domain(headers["return-path"][0])
                from_domain = _address_domain(headers["from"][0]) if headers.get("from") else None
                if return_path_domain and from_domain and return_path_domain != from_domain:
                    observe(
                        "triage.email.return_path_mismatch",
                        record,
                        {"from_domain": from_domain, "return_path_domain": return_path_domain},
                    )
        for url in extract_urls(text, limit=settings.TRIAGE_MAX_URLS):
            seen_urls.setdefault(url, record.record_no)

    # 2. URL structural rules (bounded).
    for url, record_no in list(seen_urls.items())[: settings.TRIAGE_MAX_URLS]:
        info = analyze_url(url)
        url_reports.append({**info, "record_no": record_no})
        url_record = record_by_no.get(record_no)
        if url_record is None:
            continue
        if info["userinfo"]:
            observe("triage.url.userinfo", url_record, {"url": url[:200], "host": info["host"]})
        if info["ip_host"]:
            observe("triage.url.ip_host", url_record, {"url": url[:200], "host": info["host"]})
        if info["punycode"]:
            observe("triage.url.punycode", url_record, {"url": url[:200], "host": info["host"]})
        if info["nonstandard_port"]:
            observe(
                "triage.url.nonstandard_port",
                url_record,
                {"url": url[:200], "host": info["host"], "port": info["port"]},
            )
    profile["urls_found"] = len(url_reports)

    # 3. Browser-history rows.
    history_entries: list[dict[str, Any]] = []
    for record, _text in contents:
        for entry in parse_history_rows([dict(record.raw_data or {})]):
            history_entries.append({**entry, "record_no": record.record_no})
    history_summary: dict[str, Any] | None = None
    if history_entries:
        profile["history_rows"] = len(history_entries)
        history_summary = summarize_history(history_entries)
        if not any(entry.get("visited_at") for entry in history_entries):
            missing.append("browser-history rows carry no visit timestamps")
        for cross in history_summary["cross_scheme_hosts"]:
            cross_record = record_by_no.get(int(cross["record_no"]))
            if cross_record is not None:
                observe(
                    "triage.history.cross_scheme_redirect_chain_hint",
                    cross_record,
                    {
                        "host": cross["host"],
                        "note": "both http and https visits are recorded for this host; "
                        "redirect chains are not established by history alone",
                    },
                )

    # 4. Hash manifests (entries detected here; bytes verified by the caller).
    manifest_entries: list[dict[str, Any]] = []
    for record, text in contents:
        manifest_entry = manifest_entry_from_row(
            record.record_no, dict(record.raw_data or {}), text
        )
        if manifest_entry is not None:
            manifest_entries.append(manifest_entry)
    manifest_entries = manifest_entries[: settings.TRIAGE_MANIFEST_MAX_ENTRIES]
    profile["manifest_entries"] = len(manifest_entries)
    if manifest_entries:
        missing.append(
            "the manifest covers only the filenames it lists; unlisted files were not verified"
        )

    # 5. Log lines.
    log_lines: list[dict[str, Any]] = []
    for record, text in contents:
        log_lines.extend(parse_log_lines(text, record_no=record.record_no))
    log_lines = log_lines[:_MAX_LOG_LINES]
    logs_summary: dict[str, Any] | None = None
    if log_lines:
        profile["log_lines"] = len(log_lines)
        severity_counts = Counter(line["severity"] for line in log_lines)
        source_counts = Counter(line["source"] for line in log_lines)
        stamps = [line["timestamp"] for line in log_lines]
        auth_events = [line for line in log_lines if line["auth_failure"]]
        logs_summary = {
            "severity_counts": dict(sorted(severity_counts.items())),
            "top_sources": [
                {"source": source, "lines": count}
                for source, count in sorted(source_counts.items(), key=lambda kv: (-kv[1], kv[0]))[
                    :10
                ]
            ],
            "first_event": min(stamps) if stamps else None,
            "last_event": max(stamps) if stamps else None,
            "auth_failure_lines": len(auth_events),
        }
        if len(auth_events) < 5:
            missing.append("too few timestamped auth-failure lines to evaluate a burst")
        burst = auth_failure_burst(auth_events)
        if burst is not None:
            burst_record = record_by_no.get(int(burst["record_no"]))
            if burst_record is not None:
                observe(
                    "triage.log.auth_failure_burst",
                    burst_record,
                    {k: v for k, v in burst.items() if k != "record_no"},
                )

    if (
        profile["email_header_records"] == 0
        and profile["urls_found"] == 0
        and profile["history_rows"] == 0
        and profile["manifest_entries"] == 0
        and profile["log_lines"] == 0
    ):
        raise TriageRunError(
            CODE_TRIAGE_UNSUPPORTED_CONTENT,
            "no forensic structure (e-mail headers, URLs, browser history, "
            "hash manifest or log lines) found in this evidence",
        )

    if profile["email_header_records"]:
        if not any_message_id:
            missing.append("no Message-ID header present in any record")
        if not any_auth_results:
            missing.append("no SPF/DKIM/DMARC authentication results present")
        if not any_return_path:
            missing.append("no Return-Path header present")

    return {
        "profile": profile,
        "manifest_entries": manifest_entries,
        "fields": {
            "email_headers": email_headers,
            "auth_results": auth_results,
            "urls": url_reports,
            "history": history_summary,
            "logs": logs_summary,
            "manifest": None,  # filled after byte verification
        },
        "observations": observations,
        "missing_information": missing,
    }


async def _verify_manifest(
    session: AsyncSession,
    *,
    case_id: uuid.UUID,
    storage: Any,
    exclude_evidence_id: uuid.UUID,
    entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Recompute sha-256 of the case's other stored objects and compare."""
    result = await session.execute(
        select(EvidenceFile).where(
            EvidenceFile.case_id == str(case_id),
            EvidenceFile.deleted_at.is_(None),
        )
    )
    others = [row for row in result.scalars() if row.id != str(exclude_evidence_id)]
    by_name = {(row.original_filename or "").strip().lower(): row for row in others}
    available: dict[str, str | None] = {}
    for entry in entries:
        name = (entry.get("filename") or "").strip().lower()
        if not name or name in available:
            continue
        target = by_name.get(name)
        if target is None:
            # no file by that name: leave the key out so the verdict is a
            # plain "missing" (None in the map means object_unavailable).
            continue
        present = await _to_thread(storage.exists, target.stored_key)
        if not present:
            available[name] = None
            continue
        raw = await _to_thread(storage.download, target.stored_key)
        available[name] = fingerprint(raw)
    return manifest_verdicts(entries, {k: v for k, v in available.items()})


async def _to_thread(fn: Any, *args: Any) -> Any:
    return await asyncio.to_thread(fn, *args)


def _record_manifest_observations(
    analysis: dict[str, Any], *, contents: list[tuple[SourceRecord, str]]
) -> None:
    """Append rule observations for verified manifest verdicts (bounded).

    Called only after byte verification, so an observation always cites a
    recomputed sha-256 - never a model claim. A ``match`` fires nothing.
    """
    record_by_no = {record.record_no: record for record, _ in contents}
    observations: list[dict[str, Any]] = analysis["observations"]
    for row in analysis["fields"]["manifest"] or []:
        if len(observations) >= _MAX_OBSERVATIONS:
            analysis["profile"]["observations_truncated"] = True
            break
        record = record_by_no.get(int(row.get("record_no") or 0))
        if record is None:
            continue
        if row["verdict"] == "mismatch":
            rule = "triage.manifest.hash_mismatch"
            detail: dict[str, Any] = {
                "filename": row.get("filename"),
                "expected_sha256": row["sha256"],
                "computed_sha256": row["computed_sha256"],
            }
        elif row["verdict"] in ("missing", "object_unavailable"):
            rule = "triage.manifest.entry_missing"
            detail = {"filename": row.get("filename"), "verdict": row["verdict"]}
        else:
            continue
        observations.append(
            {
                "rule": rule,
                "severity": TRIAGE_RULES[rule],
                "locator": {"record_no": record.record_no},
                "detail": detail,
            }
        )


# --- submission --------------------------------------------------------------


def _clear_stale(job: AnalysisJob, settings: Settings) -> bool:
    """Terminal-ize a stale pending/running job left by a restart.

    Mirrors the extraction/multilingual runners: no durable queue exists, so
    an orphaned job would lock its evidence forever.
    """
    try:
        if job.status == "running":
            if not jobs_svc.is_timed_out(job):
                return False
            job.error = f"superseded: exceeded {job.timeout_seconds}s timeout budget"
            jobs_svc.transition(job, "failed")
        elif job.status == "pending":
            if (datetime.now(UTC) - job.created_at).total_seconds() <= 2 * max(
                1, job.timeout_seconds or settings.TRIAGE_TIMEOUT_SECONDS
            ):
                return False
            jobs_svc.transition(job, "canceled")
        else:
            return False
        return True
    except jobs_svc.InvalidJobTransition:  # pragma: no cover - raced to terminal
        return False


async def submit_triage(
    session: AsyncSession,
    *,
    case_id: uuid.UUID,
    evidence_id: uuid.UUID,
    actor_id: uuid.UUID,
    settings: Settings,
) -> tuple[AnalysisJob, bool]:
    """Validate and enqueue one triage run (idempotent, typed refusals)."""
    result = await session.execute(
        select(EvidenceFile).where(
            EvidenceFile.id == str(evidence_id),
            EvidenceFile.case_id == str(case_id),
        )
    )
    evidence = result.scalar_one_or_none()
    if evidence is None:
        raise TriageRejected(CODE_EVIDENCE_NOT_FOUND, "evidence not found in this case")
    if evidence.deleted_at is not None:
        raise TriageRejected(
            CODE_EVIDENCE_UNAVAILABLE, "evidence is deleted; restore it before triage"
        )
    if evidence.format is None:
        try:
            detect_format(evidence.original_filename, b"")
        except UploadValidationError as exc:
            raise TriageRejected(
                CODE_UNSUPPORTED_FORMAT,
                "evidence format is not supported (supported: csv, json, txt, pdf)",
            ) from exc
    elif evidence.format not in ("csv", "json", "txt", "pdf"):
        raise TriageRejected(
            CODE_UNSUPPORTED_FORMAT, f"evidence format {evidence.format!r} is not supported"
        )

    active_result = await session.execute(
        select(AnalysisJob)
        .where(
            AnalysisJob.case_id == str(case_id),
            AnalysisJob.evidence_file_id == str(evidence_id),
            AnalysisJob.feature == "triage",
            AnalysisJob.status.in_(("pending", "running")),
        )
        .order_by(AnalysisJob.created_at.desc())
    )
    active = active_result.scalar_one_or_none()
    if active is not None and not _clear_stale(active, settings):
        raise TriageRejected(CODE_TRIAGE_ACTIVE, "a triage run is already active for this evidence")
    if active is not None:
        await session.flush()

    attempt_result = await session.execute(
        select(func.count())
        .select_from(AnalysisJob)
        .where(
            AnalysisJob.case_id == str(case_id),
            AnalysisJob.evidence_file_id == str(evidence_id),
            AnalysisJob.feature == "triage",
        )
    )
    attempt = int(attempt_result.scalar_one()) + 1
    idempotency_key = f"triage:{evidence_id}:a{attempt}"
    try:
        job, created = await jobs_svc.create_job(
            session,
            case_id=case_id,
            feature="triage",
            idempotency_key=idempotency_key,
            actor_id=actor_id,
            evidence_file_id=evidence_id,
            timeout_seconds=settings.TRIAGE_TIMEOUT_SECONDS,
        )
    except IntegrityError:
        await session.rollback()
        dup = await session.execute(
            select(AnalysisJob).where(
                AnalysisJob.case_id == str(case_id),
                AnalysisJob.idempotency_key == idempotency_key,
            )
        )
        row = dup.scalar_one_or_none()
        if row is None:
            raise
        return row, False
    await session.flush()
    return job, created


# --- execution ---------------------------------------------------------------


async def _load_records(
    session: AsyncSession, *, evidence: EvidenceFile, raw: bytes
) -> list[SourceRecord]:
    """Existing or idempotently-created source records (shared unique key)."""
    repo = EvidenceRepository(session)
    existing = await repo.get_source_records(evidence.id)
    if existing:
        return existing
    if evidence.format:
        fmt = EvidenceFormat(evidence.format)
    else:
        fmt = detect_format(evidence.original_filename, raw)
    encoding = evidence.encoding or detect_encoding(raw)
    try:
        parsed = parse(raw, fmt, encoding)
    except OCRRequiredError as exc:
        raise TriageRunError(CODE_OCR_REQUIRED, str(exc)) from exc
    except ParseError as exc:
        code = CODE_OCR_REQUIRED if fmt == EvidenceFormat.PDF else CODE_UNSUPPORTED_FORMAT
        raise TriageRunError(code, f"could not parse: {exc}") from exc
    created: list[SourceRecord] = []
    for record_no, raw_data in enumerate(parsed, start=1):
        row = await repo.create_source_record(
            evidence_file_id=evidence.id, record_no=record_no, raw_data=raw_data
        )
        if row is None:
            row = await repo.get_source_record(evidence.id, record_no)
        if row is not None:
            created.append(row)
    updates: dict[str, Any] = {}
    if not evidence.record_count:
        updates["record_count"] = len(parsed)
    if not evidence.format:
        updates["format"] = fmt.value
    if not evidence.encoding:
        updates["encoding"] = encoding
    if updates:
        await repo.update_evidence(
            evidence.id, status=evidence.status, status_detail=evidence.status_detail, **updates
        )
    return created


async def execute_triage(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    settings: Settings,
    storage: Any,
    extractor: Any,
) -> None:
    """Run one triage analysis. Own session, cooperative cancel, honest
    partial/failed states. The model is validated, never trusted."""

    job = await session.get(AnalysisJob, job_id)
    if job is None:
        return
    case_id = uuid.UUID(str(job.case_id))
    actor_id = uuid.UUID(str(job.actor_id)) if job.actor_id else None
    evidence_id = uuid.UUID(str(job.evidence_file_id)) if job.evidence_file_id else None
    summary: dict[str, Any] = {
        "records_total": 0,
        "records_scanned": 0,
        "urls_analyzed": 0,
        "observations_total": 0,
        "manifest_entries_verified": 0,
        "artifacts_created": 0,
        "artifacts_reused": 0,
        "artifacts_flagged": 0,
        "explanation_failed": 0,
        "units_failed": 0,
    }
    stage = "load"

    async def _fail(code: str, error: str, *, denial: bool = False) -> None:
        if summary:
            job.result_summary = summary
        job.error = f"{code}: {error}"[:500]
        if job.status != "running":
            jobs_svc.transition(job, "running")
        jobs_svc.transition(job, "failed")
        await session.flush()
        if actor_id is not None:
            await audit_svc.record_audit(
                session,
                actor_id=actor_id,
                action="triage.failed",
                resource_type="analysis_job",
                resource_id=job.id,
                case_id=case_id,
                metadata={"code": code, "denial": denial},
            )
        await session.commit()

    if actor_id is not None and not await authz_svc.still_authorized_for_case(
        session, user_id=actor_id, case_id=case_id, permission=rbac.PERM_EVIDENCE_READ
    ):
        await _fail(
            CODE_CASE_ACCESS_DENIED, "case access was revoked before the run started", denial=True
        )
        return
    if job.cancel_requested:
        jobs_svc.transition(job, "canceled")
        await session.flush()
        if actor_id is not None:
            await audit_svc.record_audit(
                session,
                actor_id=actor_id,
                action="triage.canceled",
                resource_type="analysis_job",
                resource_id=job.id,
                case_id=case_id,
                metadata={"stage": "before_run"},
            )
        await session.commit()
        return

    evidence = None
    if evidence_id is not None:
        repo = EvidenceRepository(session)
        evidence = await repo.get_evidence(evidence_id)
    if evidence is None or evidence.deleted_at is not None:
        await _fail(CODE_EVIDENCE_UNAVAILABLE, "evidence is no longer available")
        return

    jobs_svc.transition(job, "running")
    await session.commit()

    try:
        stage = "fetch"
        if not await _to_thread(storage.exists, evidence.stored_key):
            raise TriageRunError(CODE_INTEGRITY_SOURCE_MISSING, "stored object unavailable")
        raw = await _to_thread(storage.download, evidence.stored_key)
        if fingerprint(raw) != evidence.sha256:
            raise TriageRunError(CODE_INTEGRITY_MISMATCH, "bytes do not match recorded sha256")

        stage = "parse"
        records = await _load_records(session, evidence=evidence, raw=raw)
        fmt = EvidenceFormat(evidence.format) if evidence.format else None
        contents: list[tuple[SourceRecord, str]] = []
        for record in records[: settings.TRIAGE_MAX_RECORDS]:
            text = _unit_content(record, fmt)
            if text.strip():
                contents.append((record, text))
        summary["records_total"] = len(records)
        summary["records_scanned"] = len(contents)
        jobs_svc.advance(job, processed=0, total=1)
        await session.flush()
        await session.commit()
        if not contents:
            if fmt == EvidenceFormat.PDF:
                raise TriageRunError(CODE_OCR_REQUIRED, "PDF has no extractable text layer")
            raise TriageRunError(
                CODE_TRIAGE_UNSUPPORTED_CONTENT, "no analyzable text in this evidence"
            )

        stage = "analyze"
        stop = jobs_svc.should_stop(job)
        if stop is not None:
            await _stop(
                session, job, stop=stop, summary=summary, case_id=case_id, actor_id=actor_id
            )
            return
        analysis = triage_contents(contents, settings=settings)
        profile = analysis["profile"]
        summary["urls_analyzed"] = int(profile["urls_found"])
        if profile["manifest_entries"]:
            entries = await _verify_manifest(
                session,
                case_id=case_id,
                storage=storage,
                exclude_evidence_id=uuid.UUID(str(evidence.id)),
                entries=analysis["manifest_entries"],
            )
            analysis["fields"]["manifest"] = entries
            summary["manifest_entries_verified"] = len(entries)
            _record_manifest_observations(analysis, contents=contents)
        summary["observations_total"] = len(analysis["observations"])

        stage = "explain"
        await session.refresh(job)
        stop = jobs_svc.should_stop(job)
        if stop is not None:
            await _stop(
                session, job, stop=stop, summary=summary, case_id=case_id, actor_id=actor_id
            )
            return
        if actor_id is not None and not await authz_svc.still_authorized_for_case(
            session, user_id=actor_id, case_id=case_id, permission=rbac.PERM_EVIDENCE_READ
        ):
            await _fail(CODE_CASE_ACCESS_DENIED, "access revoked mid-run", denial=True)
            return

        explanation: dict[str, Any] | None = None
        explanation_error: str | None = None
        issues: list[dict[str, Any]] = []
        observations_bounded = {
            "format_profile": profile,
            "observations": analysis["observations"][:50],
            "missing_information": analysis["missing_information"],
            "excerpts": [
                {"record_no": record.record_no, "text": text[:_EXCERPT_CHARS]}
                for record, text in contents[:_MAX_EXCERPTS]
            ],
        }
        try:
            completion = await extractor.explain_triage(observations=observations_bounded)
        except Exception as exc:  # noqa: BLE001 - AI-layer outage -> honest partial
            summary["units_failed"] += 1
            summary["explanation_failed"] += 1
            explanation_error = f"model call failed: {str(exc)[:200]}"
            issues.append({"code": "model_call_failed"})
            logger.warning("triage model call failed: %s", str(exc)[:200])
        else:
            explanation = _parse_explanation(completion.text)
            if explanation is None:
                summary["explanation_failed"] += 1
                explanation_error = "unparseable model output"
                issues.append({"code": "unparseable_model_output"})

        stage = "record"
        validation = "flagged" if issues else "valid"
        if issues:
            summary["artifacts_flagged"] += 1
        payload: dict[str, Any] = {
            "triage": True,
            "evidence_file_id": str(evidence.id),
            "format_profile": profile,
            "fields": analysis["fields"],
            "observations": analysis["observations"],
            "missing_information": analysis["missing_information"],
            "explanation": explanation,
            "explanation_failed": summary["explanation_failed"] > 0,
            "explanation_error": explanation_error,
            "analysis_scope": (
                "structural observations only: no file was executed, opened or "
                "resolved, and no URL was fetched"
            ),
            "rules_version": TRIAGE_RULES_VERSION,
        }
        _, created = await artifacts_svc.record_artifact(
            session,
            case_id=case_id,
            kind="triage_observation",
            origin="llm",
            payload=payload,
            evidence_file_id=uuid.UUID(str(evidence.id)),
            source_locator={
                "scope": "evidence_file",
                "records_scanned": profile["records_scanned"],
            },
            validation_status=validation,
            validation_errors=issues or None,
            prompt_version=TRIAGE_RULES_VERSION,
            model_profile="triage",
            analysis_job_id=job.id,
            created_by=actor_id,
            status="pending_review",
        )
        if created:
            summary["artifacts_created"] += 1
        else:
            summary["artifacts_reused"] += 1
        jobs_svc.advance(job, processed=1)
        await session.flush()

        if summary["artifacts_created"] == 0 and summary["units_failed"]:
            await _fail(CODE_TRIAGE_FAILED, "triage produced no artifact")
            return

        stage = "complete"
        job.result_summary = summary
        if summary["units_failed"]:
            job.error = f"{summary['units_failed']} unit(s) failed (model)"
            jobs_svc.transition(job, "partial")
        else:
            jobs_svc.transition(job, "succeeded")
        await session.flush()
        await audit_svc.record_audit(
            session,
            actor_id=actor_id,
            action="triage.completed",
            resource_type="analysis_job",
            resource_id=job.id,
            case_id=case_id,
            metadata=_counts(summary),
        )
        await session.commit()
    except TriageRunError as exc:
        await session.rollback()
        await session.refresh(job)
        await _fail(exc.code, exc.message)
    except Exception:
        logger.exception("triage run crashed", extra={"job_id": str(job_id)})
        await session.rollback()
        await session.refresh(job)
        await _fail(CODE_TRIAGE_FAILED, f"unexpected error during stage {stage}")


async def _stop(
    session: AsyncSession,
    job: AnalysisJob,
    *,
    stop: str,
    summary: dict[str, Any],
    case_id: uuid.UUID,
    actor_id: uuid.UUID | None,
) -> None:
    if summary:
        job.result_summary = summary
    if stop == "cancel":
        jobs_svc.transition(job, "canceled")
        action = "triage.canceled"
    else:
        job.error = f"triage timed out after {job.timeout_seconds}s"
        jobs_svc.transition(job, "failed")
        action = "triage.timed_out"
    await session.flush()
    if actor_id is not None:
        await audit_svc.record_audit(
            session,
            actor_id=actor_id,
            action=action,
            resource_type="analysis_job",
            resource_id=job.id,
            case_id=case_id,
            metadata=_counts(summary),
        )
    await session.commit()


def _counts(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        k: summary[k]
        for k in (
            "records_total",
            "records_scanned",
            "urls_analyzed",
            "observations_total",
            "manifest_entries_verified",
            "artifacts_created",
            "artifacts_reused",
            "artifacts_flagged",
            "explanation_failed",
        )
        if k in summary
    }


async def run_triage_job(app: Any, job_id: uuid.UUID) -> None:
    """Background worker: own DB session, own scope, never raises."""
    from app.core.config import get_settings
    from app.db.postgres import Database

    settings: Settings = get_settings()
    database: Database = app.state.database
    factory = database.session_factory()
    try:
        async with factory() as session:
            await execute_triage(
                session,
                job_id=job_id,
                settings=settings,
                storage=app.state.storage,
                extractor=app.state.ai_service,
            )
    except Exception:
        logger.exception("background triage failed", extra={"job_id": str(job_id)})
        async with factory() as session:
            job = await session.get(AnalysisJob, job_id)
            if job is not None and not jobs_svc.is_terminal(job.status):
                job.error = "background triage task crashed"
                jobs_svc.transition(job, "failed")
                await session.commit()
