from __future__ import annotations

from backend.auth import require_role
from backend.domain import Account, Role


def delete_user(admin: Account, target: Account) -> None:
    """Control: gated on the ADMIN role before the destructive action."""
    require_role(admin, Role.ADMIN)
    do_delete(target)


def purge_user(admin: Account, target: Account) -> None:
    """Planted #12: the require_role gate its sibling delete_user has is missing."""
    do_purge(target)
