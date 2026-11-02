"""Tests for the API request models. Bodies are parsed from JSON, as FastAPI does."""

import json
import uuid

import pytest
from pydantic import ValidationError

from app.api.schemas import (
    MAX_AMOUNT_CENTS,
    DepositRequest,
    OpenAccountRequest,
    TransferRequest,
)

ALICE = str(uuid.uuid4())
BOB = str(uuid.uuid4())


def transfer_body(**overrides):
    body = {"from_account_id": ALICE, "to_account_id": BOB, "amount_cents": 3000}
    body.update(overrides)
    return json.dumps(body)


def error_types(exc_info):
    return {e["type"] for e in exc_info.value.errors()}


def test_valid_transfer_parses_with_defaults():
    request = TransferRequest.model_validate_json(transfer_body())

    assert request.from_account_id == uuid.UUID(ALICE)
    assert request.to_account_id == uuid.UUID(BOB)
    assert request.amount_cents == 3000
    assert request.currency == "SGD"
    assert request.idempotency_key is None


def test_transfer_accepts_idempotency_key():
    request = TransferRequest.model_validate_json(transfer_body(idempotency_key="abc-123"))

    assert request.idempotency_key == "abc-123"


@pytest.mark.parametrize("amount", [0, -1, -3000])
def test_transfer_rejects_non_positive_amount(amount):
    with pytest.raises(ValidationError) as exc_info:
        TransferRequest.model_validate_json(transfer_body(amount_cents=amount))

    assert error_types(exc_info) == {"greater_than"}


def test_transfer_accepts_smallest_amount():
    request = TransferRequest.model_validate_json(transfer_body(amount_cents=1))

    assert request.amount_cents == 1


def test_transfer_rejects_amount_too_large_for_bigint():
    with pytest.raises(ValidationError) as exc_info:
        TransferRequest.model_validate_json(transfer_body(amount_cents=MAX_AMOUNT_CENTS + 1))

    assert error_types(exc_info) == {"less_than_equal"}


@pytest.mark.parametrize("amount", [10.5, 10.0, "3000", True, None])
def test_transfer_rejects_amount_that_is_not_an_integer(amount):
    with pytest.raises(ValidationError):
        TransferRequest.model_validate_json(transfer_body(amount_cents=amount))


@pytest.mark.parametrize("typo", ["idempotency_kye", "amount", "to_acount_id"])
def test_transfer_rejects_unknown_field(typo):
    with pytest.raises(ValidationError) as exc_info:
        TransferRequest.model_validate_json(transfer_body(**{typo: "x"}))

    assert "extra_forbidden" in error_types(exc_info)


@pytest.mark.parametrize("field", ["from_account_id", "to_account_id", "amount_cents"])
def test_transfer_rejects_missing_required_field(field):
    body = json.loads(transfer_body())
    del body[field]

    with pytest.raises(ValidationError) as exc_info:
        TransferRequest.model_validate_json(json.dumps(body))

    assert error_types(exc_info) == {"missing"}


def test_transfer_rejects_malformed_account_id():
    with pytest.raises(ValidationError) as exc_info:
        TransferRequest.model_validate_json(transfer_body(to_account_id="not-a-uuid"))

    assert error_types(exc_info) == {"uuid_parsing"}


def test_transfer_rejects_empty_idempotency_key():
    with pytest.raises(ValidationError) as exc_info:
        TransferRequest.model_validate_json(transfer_body(idempotency_key=""))

    assert error_types(exc_info) == {"string_too_short"}


def test_transfer_leaves_business_rules_to_the_service():
    # Same account and other currencies are business rules: the service raises domain errors.
    request = TransferRequest.model_validate_json(
        transfer_body(to_account_id=ALICE, currency="USD")
    )

    assert request.from_account_id == request.to_account_id
    assert request.currency == "USD"


def test_valid_deposit_parses():
    request = DepositRequest.model_validate_json(
        json.dumps({"account_id": ALICE, "amount_cents": 3000})
    )

    assert request.account_id == uuid.UUID(ALICE)
    assert request.amount_cents == 3000
    assert request.currency == "SGD"


@pytest.mark.parametrize("amount", [0, -1, 10.5])
def test_deposit_rejects_invalid_amount(amount):
    with pytest.raises(ValidationError):
        DepositRequest.model_validate_json(
            json.dumps({"account_id": ALICE, "amount_cents": amount})
        )


def test_deposit_rejects_unknown_field():
    with pytest.raises(ValidationError) as exc_info:
        DepositRequest.model_validate_json(
            json.dumps({"account_id": ALICE, "amount_cents": 3000, "amont_cents": 1})
        )

    assert "extra_forbidden" in error_types(exc_info)


def test_valid_open_account_parses():
    request = OpenAccountRequest.model_validate_json(json.dumps({"holder": "Alice"}))

    assert request.holder == "Alice"


def test_open_account_rejects_empty_holder():
    with pytest.raises(ValidationError) as exc_info:
        OpenAccountRequest.model_validate_json(json.dumps({"holder": ""}))

    assert error_types(exc_info) == {"string_too_short"}


def test_open_account_rejects_unknown_field():
    with pytest.raises(ValidationError) as exc_info:
        OpenAccountRequest.model_validate_json(json.dumps({"holder": "Alice", "name": "A"}))

    assert "extra_forbidden" in error_types(exc_info)
