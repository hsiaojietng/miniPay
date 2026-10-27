"""Parsing of user-entered SGD amounts into integer cents."""

from decimal import Decimal, InvalidOperation

from app.domain.errors import InvalidAmount

CENTS_PER_DOLLAR = 100


def parse_money(value):
    if not isinstance(value, (str, Decimal)):
        raise TypeError(f"Amount must be a string or Decimal, got {type(value).__name__}")

    try:
        amount = Decimal(value)
    except InvalidOperation:
        raise InvalidAmount(f"Amount {value!r} is not a number") from None

    if not amount.is_finite():
        raise InvalidAmount(f"Amount {value!r} is not a finite number")
    if amount.as_tuple().exponent < -2:
        raise InvalidAmount(f"Amount {value!r} has more than two decimal places")

    return int(amount * CENTS_PER_DOLLAR)
