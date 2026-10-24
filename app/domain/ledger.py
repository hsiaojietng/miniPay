"""In-memory double-entry ledger for miniPay. Amounts are integer cents in SGD."""

import uuid
from dataclasses import dataclass

from app.domain.errors import (
    AccountAlreadyExists,
    AccountNotFound,
    InvalidAmount,
    UnsupportedCurrency,
)

CURRENCY = "SGD"


@dataclass(frozen=True)
class Entry:
    transfer_id: str
    account_id: str
    amount: int


class Ledger:
    cash_account_id = "CASH"

    def __init__(self):
        self._holder_by_account_id = {}
        self._account_id_by_holder = {}
        self._entries = []

    def open_account(self, holder):
        if holder in self._account_id_by_holder:
            raise AccountAlreadyExists(f"{holder} already has an account")

        account_id = str(uuid.uuid4())
        self._holder_by_account_id[account_id] = holder
        self._account_id_by_holder[holder] = account_id
        return account_id

    def deposit(self, account_id, amount, currency=CURRENCY):
        self._check_currency(currency)
        self._check_amount(amount)
        self._check_account_exists(account_id)

        transfer_id = str(uuid.uuid4())
        self._entries.append(Entry(transfer_id, self.cash_account_id, -amount))
        self._entries.append(Entry(transfer_id, account_id, amount))
        return transfer_id

    def transfer(self, from_account_id, to_account_id, amount, currency="SGD"):
        raise NotImplementedError

    def reverse(self, transfer_id):
        raise NotImplementedError

    def balance(self, account_id, requested_by):
        raise NotImplementedError

    def statement(self, account_id, requested_by):
        raise NotImplementedError

    def entries_for(self, transfer_id):
        raise NotImplementedError

    def all_entries(self):
        raise NotImplementedError

    def _check_currency(self, currency):
        if currency != CURRENCY:
            raise UnsupportedCurrency(f"Only {CURRENCY} is supported, got {currency!r}")

    def _check_amount(self, amount):
        if amount <= 0:
            raise InvalidAmount(f"Amount must be greater than 0, got {amount}")

    def _check_account_exists(self, account_id):
        if account_id not in self._holder_by_account_id:
            raise AccountNotFound(f"Account {account_id} does not exist")
