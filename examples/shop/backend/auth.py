from __future__ import annotations

from backend.domain import Account, ApiError, Role


def require_role(account: Account, required: Role) -> None:
    """Ensure the account holds the required role, else raise ApiError(403)."""
    if account.role != required:
        raise ApiError(403, f"requires {required.value}")


def ensure_authenticated(account: Account | None) -> Account:
    """Ensure a request is authenticated."""
    if account is None:
        raise ApiError(401, "authentication required")
    return account
