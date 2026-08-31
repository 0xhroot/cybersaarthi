"""Unit tests for the role-based access control model."""

from __future__ import annotations

from app.core import rbac


def test_every_role_maps_to_valid_roles() -> None:
    for role in rbac.ALL_ROLES:
        assert rbac.is_valid_role(role)
    assert not rbac.is_valid_role("SUPERUSER")
    assert not rbac.is_valid_role("")


def test_only_admin_is_admin() -> None:
    assert rbac.is_admin_role(rbac.ROLE_ADMIN)
    for role in (rbac.ROLE_INVESTIGATOR, rbac.ROLE_ANALYST, rbac.ROLE_VIEWER):
        assert not rbac.is_admin_role(role)


def test_admin_has_every_permission() -> None:
    for permission in rbac.ALL_PERMISSIONS:
        assert rbac.has_permission([rbac.ROLE_ADMIN], permission)


def test_investigator_has_everything_except_user_management() -> None:
    for permission in rbac.ALL_PERMISSIONS:
        expected = permission != rbac.PERM_USERS_MANAGE
        assert rbac.has_permission([rbac.ROLE_INVESTIGATOR], permission) is expected


def test_analyst_is_read_only_plus_analytics_and_review() -> None:
    permissions = {
        rbac.PERM_CASE_READ,
        rbac.PERM_EVIDENCE_READ,
        rbac.PERM_ANALYTICS_RUN,
        rbac.PERM_FINDINGS_READ,
        rbac.PERM_FINDINGS_REVIEW,
    }
    for permission in rbac.ALL_PERMISSIONS:
        assert rbac.has_permission([rbac.ROLE_ANALYST], permission) is (permission in permissions)


def test_viewer_is_strictly_read_only() -> None:
    permissions = {rbac.PERM_CASE_READ, rbac.PERM_EVIDENCE_READ, rbac.PERM_FINDINGS_READ}
    for permission in rbac.ALL_PERMISSIONS:
        assert rbac.has_permission([rbac.ROLE_VIEWER], permission) is (permission in permissions)


def test_has_permission_covers_any_role_in_the_set() -> None:
    assert rbac.has_permission([rbac.ROLE_VIEWER], rbac.PERM_CASE_READ)
    assert not rbac.has_permission([rbac.ROLE_VIEWER], rbac.PERM_CASE_CREATE)
    # Combined roles: the analyst's review permission applies.
    assert rbac.has_permission([rbac.ROLE_VIEWER, rbac.ROLE_ANALYST], rbac.PERM_FINDINGS_REVIEW)
    assert not rbac.has_permission([], rbac.PERM_CASE_READ)


def test_roles_from_permission() -> None:
    assert rbac.ROLE_ADMIN in rbac.roles_from_permission(rbac.PERM_USERS_MANAGE)
    assert rbac.ROLE_INVESTIGATOR not in rbac.roles_from_permission(rbac.PERM_USERS_MANAGE)
    assert set(rbac.roles_from_permission(rbac.PERM_CASE_READ)) >= {
        rbac.ROLE_ADMIN,
        rbac.ROLE_INVESTIGATOR,
        rbac.ROLE_ANALYST,
        rbac.ROLE_VIEWER,
    }
    assert set(rbac.roles_from_permission(rbac.PERM_INGESTION_RUN)) == {
        rbac.ROLE_ADMIN,
        rbac.ROLE_INVESTIGATOR,
    }


def test_every_permission_is_covered_and_valid() -> None:
    expected = {
        rbac.PERM_CASE_READ,
        rbac.PERM_CASE_CREATE,
        rbac.PERM_CASE_UPDATE,
        rbac.PERM_CASE_ARCHIVE,
        rbac.PERM_EVIDENCE_READ,
        rbac.PERM_EVIDENCE_UPLOAD,
        rbac.PERM_EVIDENCE_DELETE,
        rbac.PERM_INGESTION_RUN,
        rbac.PERM_ANALYTICS_RUN,
        rbac.PERM_FINDINGS_READ,
        rbac.PERM_FINDINGS_REVIEW,
        rbac.PERM_FINDINGS_CONFIRM,
        rbac.PERM_FINDINGS_DISMISS,
        rbac.PERM_USERS_MANAGE,
        rbac.PERM_AUDIT_READ,
    }
    assert rbac.ALL_PERMISSIONS == frozenset(expected)
