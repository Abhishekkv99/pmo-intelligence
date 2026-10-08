from sqlalchemy import Boolean, CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import Role, check_in


class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            f"role IS NULL OR {check_in('role', Role)}", name="ck_users_role"
        ),
    )

    email: Mapped[str] = mapped_column(
        String(320), nullable=False, unique=True, index=True
    )
    hashed_password: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auth_provider: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="local"
    )
    entra_oid: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True, index=True
    )

    # The entitlement (see app.utils.entitlements). NULL until someone grants
    # a role: a newly provisioned SSO user can sign in but reads nothing.
    # default=None is explicit so the attribute is loaded after
    # UserRepository.create and a later read inside a request cannot
    # lazy-load it (MissingGreenlet).
    role: Mapped[str | None] = mapped_column(String(20), nullable=True, default=None)

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"
