from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AccountStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"
    PENDING_VERIFICATION = "pending_verification"


class OrderStatus(str, Enum):
    CART = "cart"
    PLACED = "placed"
    PAID = "paid"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class Role(str, Enum):
    ADMIN = "admin"
    STAFF = "staff"
    MEMBER = "member"
    GUEST = "guest"


class PaymentResult(str, Enum):
    APPROVED = "approved"
    DECLINED = "declined"
    PENDING = "pending"
    FRAUD_REVIEW = "fraud_review"


class ApiError(Exception):
    """Domain-level error carrying an HTTP-style status code."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass
class Account:
    id: str
    status: AccountStatus
    role: Role


@dataclass
class Order:
    id: str
    status: OrderStatus
    total_cents: int
