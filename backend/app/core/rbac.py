"""Role-based access control model.

Roles are seeded in the Phase 4 migration (``scripts``/migrations) with fixed
identifiers; this module is the single source of truth for which permission a
role grants. Permissions are coarse-grained action strings that map one-to-one
to endpoint families, so a handler either requires one explicit permission or
falls back to the ownership checks enforced by ``assert_case_access``.

Model (Phase 4): each case has an ``owner_id``. A user may act on a case when
they are the owner or have the ``admin`` role. ``case.read`` gates the read
handlers; mutating handlers additionally require their own permission.

Roles (least privilege, no organizations/tenants — Phase 4 scope):
    ADMIN        : every permission (full control, implicit case access).
    INVESTIGATOR : runs investigations end to end.
    ANALYST      : read-only + analytics + findings review.
    VIEWER       : read-only.
"""

from __future__ import annotations

from collections.abc import Iterable

ROLE_ADMIN = "ADMIN"
ROLE_INVESTIGATOR = "INVESTIGATOR"
ROLE_ANALYST = "ANALYST"
ROLE_VIEWER = "VIEWER"

ALL_ROLES = (ROLE_ADMIN, ROLE_INVESTIGATOR, ROLE_ANALYST, ROLE_VIEWER)

# Permission strings -----------------------------------------------------
PERM_CASE_READ = "case.read"
PERM_CASE_CREATE = "case.create"
PERM_CASE_UPDATE = "case.update"
PERM_CASE_ARCHIVE = "case.archive"
PERM_EVIDENCE_READ = "evidence.read"
PERM_EVIDENCE_UPLOAD = "evidence.upload"
PERM_INGESTION_RUN = "ingestion.run"
PERM_ANALYTICS_RUN = "analytics.run"
PERM_FINDINGS_READ = "findings.read"
PERM_FINDINGS_REVIEW = "findings.review"
PERM_FINDINGS_CONFIRM = "findings.confirm"
PERM_FINDINGS_DISMISS = "findings.dismiss"
PERM_USERS_MANAGE = "users.manage"
PERM_AUDIT_READ = "audit.read"

ALL_PERMISSIONS: frozenset[str] = frozenset(
    {
        PERM_CASE_READ,
        PERM_CASE_CREATE,
        PERM_CASE_UPDATE,
        PERM_CASE_ARCHIVE,
        PERM_EVIDENCE_READ,
        PERM_EVIDENCE_UPLOAD,
        PERM_INGESTION_RUN,
        PERM_ANALYTICS_RUN,
        PERM_FINDINGS_READ,
        PERM_FINDINGS_REVIEW,
        PERM_FINDINGS_CONFIRM,
        PERM_FINDINGS_DISMISS,
        PERM_USERS_MANAGE,
        PERM_AUDIT_READ,
    }
)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    ROLE_ADMIN: ALL_PERMISSIONS,
    ROLE_INVESTIGATOR: frozenset(
        {
            PERM_CASE_READ,
            PERM_CASE_CREATE,
            PERM_CASE_UPDATE,
            PERM_CASE_ARCHIVE,
            PERM_EVIDENCE_READ,
            PERM_EVIDENCE_UPLOAD,
            PERM_INGESTION_RUN,
            PERM_ANALYTICS_RUN,
            PERM_FINDINGS_READ,
            PERM_FINDINGS_REVIEW,
            PERM_FINDINGS_CONFIRM,
            PERM_FINDINGS_DISMISS,
            PERM_AUDIT_READ,
        }
    ),
    ROLE_ANALYST: frozenset(
        {
            PERM_CASE_READ,
            PERM_EVIDENCE_READ,
            PERM_ANALYTICS_RUN,
            PERM_FINDINGS_READ,
            PERM_FINDINGS_REVIEW,
        }
    ),
    ROLE_VIEWER: frozenset({PERM_CASE_READ, PERM_EVIDENCE_READ, PERM_FINDINGS_READ}),
}


def is_valid_role(role: str) -> bool:
    return role in ALL_ROLES


def is_admin_role(role: str) -> bool:
    return role == ROLE_ADMIN


def has_permission(roles: Iterable[str], permission: str) -> bool:
    """True when any of *roles* grants *permission*."""
    return any(permission in ROLE_PERMISSIONS[role] for role in roles)


def roles_from_permission(permission: str) -> list[str]:
    """Roles that hold a permission (used by tests and docs)."""
    return [role for role, perms in ROLE_PERMISSIONS.items() if permission in perms]
