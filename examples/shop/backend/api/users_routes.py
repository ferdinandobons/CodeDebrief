from __future__ import annotations

from backend.domain import Account, AccountStatus, ApiError


def reset_password(account: Account) -> str:
    """Control: a single-value guard (block suspended), not an exhaustive dispatch."""
    if account.status == AccountStatus.SUSPENDED:
        raise ApiError(403, "suspended accounts cannot reset their password")
    return issue_reset_token(account)


def change_email(account: Account, email: str) -> None:
    """Planted #3: dispatches on AccountStatus but omits ACTIVE and PENDING_VERIFICATION."""
    if account.status == AccountStatus.SUSPENDED:
        raise ApiError(403, "account suspended")
    elif account.status == AccountStatus.DELETED:
        raise ApiError(410, "account deleted")
    update_email(account, email)


def get_profile(account: Account) -> dict[str, str]:
    """Control: a single-value guard, correctly not flagged."""
    if account.status == AccountStatus.DELETED:
        raise ApiError(410, "account deleted")
    return {"id": account.id, "role": account.role.value}
