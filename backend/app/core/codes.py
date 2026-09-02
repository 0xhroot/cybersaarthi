"""Stable machine-readable API error codes (single source of truth).

These constants live outside any API package so both the service layer (which
signals domain conditions) and the API layer (which maps them to HTTP
responses) can reference them without a circular import through the ``app.api``
package tree.
"""

from __future__ import annotations

# Authentication / account lifecycle.
CODE_INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
CODE_ACCOUNT_PENDING = "ACCOUNT_PENDING"
CODE_ACCOUNT_SUSPENDED = "ACCOUNT_SUSPENDED"
CODE_ACCOUNT_REJECTED = "ACCOUNT_REJECTED"
CODE_ACCOUNT_TRANSITION_INVALID = "ACCOUNT_TRANSITION_INVALID"
CODE_ACCOUNT_NOT_ACTIVE = "ACCOUNT_NOT_ACTIVE"

# Authorization / access control.
CODE_INSUFFICIENT_PERMISSION = "INSUFFICIENT_PERMISSION"
CODE_CASE_ACCESS_DENIED = "CASE_ACCESS_DENIED"

# Registration.
CODE_DUPLICATE_EMAIL = "DUPLICATE_EMAIL"

MESSAGES = {
    CODE_INVALID_CREDENTIALS: "invalid username or password",
    CODE_ACCOUNT_PENDING: "account is pending administrator approval",
    CODE_ACCOUNT_SUSPENDED: "account has been suspended",
    CODE_ACCOUNT_REJECTED: "account registration was rejected",
}
