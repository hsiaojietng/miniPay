"""miniPay HTTP application. Run with: uvicorn app.main:app --reload"""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from app.api.errors import (
    http_error_handler,
    ledger_error_handler,
    unexpected_error_handler,
    validation_error_handler,
)
from app.api.routes import router
from app.domain.errors import LedgerError

app = FastAPI(title="miniPay")
app.include_router(router)
app.add_exception_handler(LedgerError, ledger_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
# Starlette's class, not FastAPI's subclass, so the router's own 404/405 are caught too.
app.add_exception_handler(HTTPException, http_error_handler)
app.add_exception_handler(Exception, unexpected_error_handler)
