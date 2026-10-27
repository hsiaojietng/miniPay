"""Tests for parsing user-entered SGD amounts into integer cents.

Parsing goes through Decimal so "12.34" is exact; floats are rejected outright
because the value has already lost precision before the parser sees it.
"""

from decimal import Decimal

import pytest

from app.domain.errors import InvalidAmount
from app.domain.money import parse_money


@pytest.mark.parametrize(
    "text, cents",
    [
        ("12.34", 1234),
        ("12.3", 1230),
        ("12", 1200),
        ("0.01", 1),
        ("100000.00", 10000000),
    ],
)
def test_parse_money_returns_integer_cents(text, cents):
    result = parse_money(text)

    assert result == cents
    assert isinstance(result, int)


def test_parse_money_accepts_decimal():
    assert parse_money(Decimal("12.34")) == 1234


@pytest.mark.parametrize("value", [12.34, 12.5, 0.1])
def test_parse_money_rejects_floats(value):
    with pytest.raises(TypeError):
        parse_money(value)


@pytest.mark.parametrize("text", ["12.345", "0.001", "1.999"])
def test_parse_money_rejects_more_than_two_decimal_places(text):
    with pytest.raises(InvalidAmount):
        parse_money(text)


@pytest.mark.parametrize("text", ["", "abc", "12.3.4", "NaN", "Infinity"])
def test_parse_money_rejects_non_numbers(text):
    with pytest.raises(InvalidAmount):
        parse_money(text)
