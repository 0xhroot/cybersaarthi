"""Import all models so that ``app.models.Base.metadata`` is complete and
Alembic autogenerate / test fixtures can see the full schema."""

from app.models.audit_log import AuditLog
from app.models.base import Base
from app.models.case import Case
from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole

__all__ = ["AuditLog", "Base", "Case", "Role", "User", "UserRole"]
