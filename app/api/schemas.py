"""Request and response bodies for the miniPay HTTP API.

Request models check the shape of a request before it reaches a service: types, simple ranges
and unknown fields. Business rules (funds, account existence, currency) stay in the services.
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.ledger import CURRENCY

# amount_cents is a BIGINT column; anything larger would fail in Postgres instead of here.
MAX_AMOUNT_CENTS = 2**63 - 1


class RequestModel(BaseModel):
    # Unknown fields are rejected so a typo such as "idempotency_kye" fails with a 422
    # instead of being dropped and silently turning off idempotency.
    model_config = ConfigDict(extra="forbid")


class OpenAccountRequest(RequestModel):
    holder: str = Field(min_length=1)


class DepositRequest(RequestModel):
    # The account comes from the path, /v1/accounts/{account_id}/deposits.
    # strict: reject 10.0, "1000" and true rather than coercing them into cents.
    amount_cents: int = Field(gt=0, le=MAX_AMOUNT_CENTS, strict=True)
    currency: str = CURRENCY


class TransferRequest(RequestModel):
    from_account_id: UUID
    to_account_id: UUID
    amount_cents: int = Field(gt=0, le=MAX_AMOUNT_CENTS, strict=True)
    currency: str = CURRENCY
    idempotency_key: str | None = Field(default=None, min_length=1)


class AccountResponse(BaseModel):
    id: UUID
    holder: str


class TransferResponse(BaseModel):
    transfer_id: UUID


class BalanceResponse(BaseModel):
    account_id: UUID
    balance_cents: int
    currency: str


class StatementLineResponse(BaseModel):
    transfer_id: UUID
    amount_cents: int
    balance_after_cents: int


class StatementResponse(BaseModel):
    account_id: UUID
    currency: str
    lines: list[StatementLineResponse]
