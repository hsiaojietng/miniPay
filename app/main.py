"""miniPay HTTP application. Run with: uvicorn app.main:app --reload"""

from fastapi import FastAPI

from app.api.errors import ledger_error_handler
from app.api.routes import router
from app.domain.errors import LedgerError

app = FastAPI(title="miniPay")
app.include_router(router)
app.add_exception_handler(LedgerError, ledger_error_handler)
