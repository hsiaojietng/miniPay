"""Version 1 HTTP routes for miniPay. Each route validates its body, calls one service and shapes the reply."""

from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, Header

from app.api.schemas import (
    AccountResponse,
    BalanceResponse,
    DepositRequest,
    OpenAccountRequest,
    StatementLineResponse,
    StatementResponse,
    TransferRequest,
    TransferResponse,
)
from app.db.connection import DATABASE_URL
from app.domain.ledger import CURRENCY
from app.services import account_service
from app.services.transfer_service import transfer

router = APIRouter(prefix="/v1")


def get_conn():
    # Autocommit so reads see committed data at once; services open their own transaction for writes.
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        yield conn


Conn = Annotated[psycopg.Connection, Depends(get_conn)]
# Stand-in for authentication: the caller names the holder they act as. Not secure.
Holder = Annotated[str, Header(alias="X-Holder")]


@router.post("/accounts", status_code=201, response_model=AccountResponse)
def open_account(body: OpenAccountRequest, conn: Conn):
    account_id = account_service.open_account(conn, body.holder)
    return AccountResponse(id=account_id, holder=body.holder)


@router.post("/accounts/{account_id}/deposits", status_code=201, response_model=TransferResponse)
def deposit(account_id: UUID, body: DepositRequest, conn: Conn):
    transfer_id = account_service.deposit(conn, str(account_id), body.amount_cents, body.currency)
    return TransferResponse(transfer_id=transfer_id)


@router.post("/transfers", status_code=201, response_model=TransferResponse)
def create_transfer(body: TransferRequest, conn: Conn):
    transfer_id = transfer(
        conn,
        str(body.from_account_id),
        str(body.to_account_id),
        body.amount_cents,
        body.currency,
        body.idempotency_key,
    )
    return TransferResponse(transfer_id=transfer_id)


@router.get("/accounts/{account_id}/balance", response_model=BalanceResponse)
def balance(account_id: UUID, holder: Holder, conn: Conn):
    cents = account_service.balance(conn, str(account_id), holder)
    return BalanceResponse(account_id=account_id, balance_cents=cents, currency=CURRENCY)


@router.get("/accounts/{account_id}/statement", response_model=StatementResponse)
def statement(account_id: UUID, holder: Holder, conn: Conn):
    lines = account_service.statement(conn, str(account_id), holder)
    return StatementResponse(
        account_id=account_id,
        currency=CURRENCY,
        lines=[
            StatementLineResponse(
                transfer_id=line.transfer_id,
                amount_cents=line.amount,
                balance_after_cents=line.balance_after,
            )
            for line in lines
        ],
    )
