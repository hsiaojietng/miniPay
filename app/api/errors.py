"""Turns domain errors raised by the services into HTTP responses."""

import re

from fastapi import Request
from fastapi.responses import JSONResponse

from app.domain.errors import (
    AccessDenied,
    AccountAlreadyExists,
    AccountNotFound,
    InsufficientFunds,
    InvalidAmount,
    LedgerError,
    SameAccountTransfer,
    TransferAlreadyReversed,
    TransferNotFound,
    UnsupportedCurrency,
)

STATUS_BY_ERROR = {
    AccountNotFound: 404,
    TransferNotFound: 404,
    AccessDenied: 403,
    AccountAlreadyExists: 409,
    TransferAlreadyReversed: 409,
    InvalidAmount: 422,
    InsufficientFunds: 422,
    SameAccountTransfer: 422,
    UnsupportedCurrency: 422,
}


async def ledger_error_handler(request: Request, exc: LedgerError):
    # "detail" matches FastAPI's own errors; "code" lets clients branch without parsing the message.
    return JSONResponse(
        status_code=STATUS_BY_ERROR.get(type(exc), 400),
        content={"detail": str(exc), "code": _snake_case(type(exc).__name__)},
    )


def _snake_case(name):
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
