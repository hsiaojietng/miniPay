"""Turns errors into HTTP responses that all share one body shape: {"code", "message"}."""

import re
from http import HTTPStatus

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

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
    return _error(STATUS_BY_ERROR.get(type(exc), 400), _snake_case(type(exc).__name__), str(exc))


async def validation_error_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    # A bad amount gets the same code whether Pydantic or the service caught it.
    if all(e["loc"][-1] == "amount_cents" for e in errors):
        code = "invalid_amount"
    else:
        code = "validation_error"
    message = "; ".join(f"{_field(e['loc'])}: {e['msg']}" for e in errors)
    return _error(422, code, message)


async def http_error_handler(request: Request, exc: HTTPException):
    # Errors the framework raises itself, such as an unknown URL (404) or wrong method (405).
    code = HTTPStatus(exc.status_code).phrase.lower().replace(" ", "_")
    return _error(exc.status_code, code, str(exc.detail))


async def unexpected_error_handler(request: Request, exc: Exception):
    # Anything else is a bug or an outage. The message stays generic so internals never leak;
    # the server still logs the full traceback.
    return _error(500, "internal_error", "Internal server error")


def _error(status_code, code, message):
    # "code" lets clients branch without parsing the message.
    return JSONResponse(status_code=status_code, content={"code": code, "message": message})


def _field(loc):
    # loc starts with where the value came from ("body", "path", "header"); the rest names the field.
    return ".".join(str(part) for part in loc[1:]) or str(loc[0])


def _snake_case(name):
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
