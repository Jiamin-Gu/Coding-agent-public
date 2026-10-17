"""Shared normalisation and validation helpers used across shopkit modules."""

import re
from datetime import datetime

from .errors import ValidationError

SKU_RE = re.compile(r"[A-Z0-9-]{1,20}\Z")
CODE_RE = re.compile(r"[A-Z0-9]{3,16}\Z")


def now_iso(clock) -> str:
    """Return the current event timestamp in ISO format (seconds precision)."""
    return clock().isoformat(timespec="seconds")


def norm_text(value, field: str = "value") -> str:
    """Strip ``value``; must be a non-empty string."""
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a string")
    text = value.strip()
    if not text:
        raise ValidationError(f"{field} must not be empty")
    return text


def norm_category(value) -> str:
    """Strip and lowercase a category name; must be a non-empty string."""
    if not isinstance(value, str):
        raise ValidationError("category must be a string")
    text = value.strip().lower()
    if not text:
        raise ValidationError("category must not be empty")
    return text


def norm_code(value) -> str:
    """Strip and uppercase a coupon code (format is validated separately)."""
    if not isinstance(value, str):
        raise ValidationError("coupon code must be a string")
    return value.strip().upper()


def validate_sku(sku) -> str:
    """Validate a sku against ``[A-Z0-9-]{1,20}``."""
    if not isinstance(sku, str) or not SKU_RE.match(sku):
        raise ValidationError("invalid sku")
    return sku


def validate_code_format(code: str) -> str:
    """Validate an already-normalised coupon code against ``[A-Z0-9]{3,16}``."""
    if not CODE_RE.match(code):
        raise ValidationError("invalid coupon code")
    return code


def require_int(value, field: str) -> int:
    """Require a real ``int`` (bool is rejected)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{field} must be an integer")
    return value


def require_bool(value, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValidationError(f"{field} must be a bool")
    return value


def validate_qty(value) -> int:
    """Validate a line quantity: int (not bool) and >= 1."""
    require_int(value, "qty")
    if value < 1:
        raise ValidationError("qty must be >= 1")
    return value


def parse_date(value, field: str = "date") -> str:
    """Validate a ``YYYY-MM-DD`` string (exactly 10 chars) and return it."""
    if not isinstance(value, str) or len(value) != 10:
        raise ValidationError(f"{field} must be a YYYY-MM-DD string")
    try:
        d = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError(f"{field} is not a valid date")
    if d.isoformat() != value:
        raise ValidationError(f"{field} is not a valid date")
    return value
