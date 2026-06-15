from backend.domain import Account
from backend.users_service import authenticate


def test_authenticate_returns_active_account(account: Account) -> None:
    # A test flow: LogicChart links it to authenticate as a covering test.
    assert authenticate(account) is account
