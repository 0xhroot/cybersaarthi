"""User service: account lifecycle and role management.

Phase 5 turns accounts into a managed lifecycle: self-registration creates a
PENDING account (never privileged, the client-supplied role is ignored), and
an administrator approves/rejects/suspends/activates it and assigns roles.
"""

from __future__ import annotations

from uuid import UUID

from app.core.codes import CODE_ACCOUNT_NOT_ACTIVE, CODE_ACCOUNT_TRANSITION_INVALID
from app.core.enums import AccountStatus
from app.core.security import hash_password
from app.models import User
from app.repositories.user_repository import UserRepository


class AccountTransitionError(ValueError):
    """Raised on an illegal account-status transition.

    Carries a stable machine-readable code so the API layer can translate it to
    the standard error envelope without re-deriving the cause from prose.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class UserService:
    """Account lifecycle with centralized legal-transition enforcement.

    The account status machine is::

        PENDING --(approve)--> ACTIVE --(suspend)--> SUSPENDED --(activate)--> ACTIVE
           |                                          |
           +--(reject)-----------> REJECTED <----------+

    Only the transitions above are legal. In particular ``activate`` reinstate
    only SUSPENDED accounts (a REJECTED or PENDING account is never promoted
    directly to ACTIVE), and roles are only granted to ACTIVE accounts.
    """

    _VALID_TRANSITIONS: dict[str, frozenset[str]] = {
        AccountStatus.PENDING.value: frozenset(
            {AccountStatus.ACTIVE.value, AccountStatus.REJECTED.value}
        ),
        AccountStatus.ACTIVE.value: frozenset({AccountStatus.SUSPENDED.value}),
        AccountStatus.SUSPENDED.value: frozenset(
            {AccountStatus.ACTIVE.value, AccountStatus.REJECTED.value}
        ),
        AccountStatus.REJECTED.value: frozenset(),
    }

    def __init__(self, repository: UserRepository) -> None:
        self._repository = repository

    async def register_pending(
        self,
        *,
        username: str,
        email: str,
        password: str,
    ) -> User:
        """Create a PENDING account. No role is assigned on registration."""
        password_hash = hash_password(password)
        return await self._repository.create(
            username=username,
            email=email,
            password_hash=password_hash,
            status=AccountStatus.PENDING.value,
        )

    async def create_user(
        self,
        *,
        username: str,
        email: str,
        password: str,
    ) -> User:
        """Create an immediately ACTIVE account (used by bootstrap/seed tooling)."""
        password_hash = hash_password(password)
        return await self._repository.create(
            username=username,
            email=email,
            password_hash=password_hash,
            status=AccountStatus.ACTIVE.value,
        )

    async def create_user_with_role(
        self,
        *,
        username: str,
        email: str,
        password: str,
        role: str,
    ) -> User:
        """Create an ACTIVE user and assign a single initial role."""
        user = await self.create_user(username=username, email=email, password=password)
        await self.set_role(user.id, role)
        return user

    async def approve(self, user_id: UUID, role: str) -> User | None:
        """Approve a PENDING account and grant exactly one role; None if absent."""
        user = await self._repository.get(user_id)
        if user is None:
            return None
        self._assert_transition(user, AccountStatus.ACTIVE.value)
        user = await self._repository.update_status(user_id, AccountStatus.ACTIVE.value)
        assert user is not None
        await self._repository.replace_roles(user_id, role)
        return user

    async def reject(self, user_id: UUID) -> User | None:
        """Reject a non-active account (PENDING or SUSPENDED)."""
        user = await self._repository.get(user_id)
        if user is None:
            return None
        self._assert_transition(user, AccountStatus.REJECTED.value)
        return await self._repository.update_status(user_id, AccountStatus.REJECTED.value)

    async def suspend(self, user_id: UUID) -> User | None:
        """Suspend an ACTIVE account."""
        user = await self._repository.get(user_id)
        if user is None:
            return None
        self._assert_transition(user, AccountStatus.SUSPENDED.value)
        return await self._repository.update_status(user_id, AccountStatus.SUSPENDED.value)

    async def activate(self, user_id: UUID) -> User | None:
        """Reinstate a SUSPENDED account (never promotes PENDING/REJECTED).

        ``activate`` is reinstatement-only: it is NOT the approval path. A
        PENDING account is promoted only by ``approve``; activation from any
        source other than SUSPENDED is illegal.
        """
        user = await self._repository.get(user_id)
        if user is None:
            return None
        if user.status != AccountStatus.SUSPENDED.value:
            raise AccountTransitionError(
                CODE_ACCOUNT_TRANSITION_INVALID,
                f"activate only reinstates SUSPENDED accounts; cannot activate "
                f"{user.status} account {user.id}",
            )
        return await self._repository.update_status(user_id, AccountStatus.ACTIVE.value)

    async def set_role(self, user_id: UUID, role: str) -> None:
        await self._repository.replace_roles(user_id, role)

    async def change_role(self, user_id: UUID, role: str) -> User | None:
        """Assign a single role to *user_id*; returns the user or None.

        Privileges are never granted to an account that is not ACTIVE.
        """
        user = await self._repository.get(user_id)
        if user is None:
            return None
        self._require_active(user)
        await self.set_role(user_id, role)
        return user

    async def update_status(self, user_id: UUID, status: str) -> User | None:
        return await self._repository.update_status(user_id, status)

    def _assert_transition(self, user: User, target: str) -> None:
        """Raise when the account-status transition is illegal (typed error)."""
        allowed = self._VALID_TRANSITIONS.get(user.status)
        if allowed is None or target not in allowed:
            raise AccountTransitionError(
                CODE_ACCOUNT_TRANSITION_INVALID,
                f"illegal account transition: {user.status} -> {target} for user {user.id}",
            )

    def _require_active(self, user: User) -> None:
        if user.status != AccountStatus.ACTIVE.value:
            raise AccountTransitionError(
                CODE_ACCOUNT_NOT_ACTIVE,
                f"cannot grant a role to a {user.status} account: {user.id}",
            )

    async def admin_count(self) -> int:
        return await self._repository.count_admins()

    async def is_sole_active_admin(self, user_id: UUID) -> bool:
        """True when *user_id* is one of a single remaining ACTIVE admin."""
        roles = await self.roles(user_id)
        if "ADMIN" not in roles:
            return False
        return await self._repository.count_admins() <= 1

    async def roles(self, user_id: UUID) -> list[str]:
        return await self._repository.roles_for_user(user_id)

    async def permissions(self, user_id: UUID) -> list[str]:
        from app.core.rbac import ROLE_PERMISSIONS

        roles = await self.roles(user_id)
        perms = {permission for role in roles for permission in ROLE_PERMISSIONS.get(role, ())}
        return sorted(perms)

    async def get(self, user_id: UUID) -> User | None:
        return await self._repository.get(user_id)

    async def list_users(
        self,
        *,
        limit: int,
        offset: int,
        status: str | None = None,
        search: str | None = None,
    ) -> tuple[list[User], int]:
        return await self._repository.list_users(
            limit=limit, offset=offset, status=status, search=search
        )

    async def get_by_username(self, username: str) -> User | None:
        return await self._repository.get_by_username(username)

    async def get_by_email(self, email: str) -> User | None:
        return await self._repository.get_by_email(email)

    async def username_exists(self, username: str) -> bool:
        return await self.get_by_username(username) is not None

    async def email_exists(self, email: str) -> bool:
        return await self.get_by_email(email) is not None
