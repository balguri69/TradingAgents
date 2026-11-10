"""Validation helpers for financial data transfer objects."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from tradingagents.dataflows.exceptions import DTOValidationError


def validate_utc_datetime(dt: datetime, field_name: str = "timestamp") -> None:
    """Ensure datetime is timezone-aware and set to UTC."""
    if not isinstance(dt, datetime):
        raise DTOValidationError(f"{field_name} must be a datetime instance, got {type(dt)}")
    if dt.tzinfo is None:
        raise DTOValidationError(f"{field_name} must be timezone-aware (expected UTC, got naive)")


def validate_positive_decimal(val: Decimal, field_name: str) -> None:
    """Ensure value is a Decimal and strictly greater than zero."""
    if not isinstance(val, Decimal):
        raise DTOValidationError(f"{field_name} must be a Decimal, got {type(val).__name__}")
    if val.is_nan() or val.is_infinite():
        raise DTOValidationError(f"{field_name} cannot be NaN or Infinite, got {val}")
    if val <= 0:
        raise DTOValidationError(f"{field_name} must be strictly positive (> 0), got {val}")


def validate_non_negative_decimal(val: Decimal, field_name: str) -> None:
    """Ensure value is a Decimal and greater than or equal to zero."""
    if not isinstance(val, Decimal):
        raise DTOValidationError(f"{field_name} must be a Decimal, got {type(val).__name__}")
    if val.is_nan() or val.is_infinite():
        raise DTOValidationError(f"{field_name} cannot be NaN or Infinite, got {val}")
    if val < 0:
        raise DTOValidationError(f"{field_name} must be non-negative (>= 0), got {val}")
