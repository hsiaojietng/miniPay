"""In-memory double-entry ledger for miniPay. Amounts are integer cents in SGD."""

import uuid
from dataclasses import dataclass

from app.domain.errors import (
    AccessDenied,
    AccountAlreadyExists,
    AccountNotFound,
    InsufficientFunds,
    InvalidAmount,
    SameAccountTransfer,
    TransferAlreadyReversed,
    TransferNotFound,
    UnsupportedCurrency,
)

CURRENCY = "SGD"


@dataclass(frozen=True)
class Entry:
    transfer_id: str
    account_id: str
    amount: int


@dataclass(frozen=True)
class Transfer:
    from_account_id: str
    to_account_id: str
    amount: int


class Ledger:
    cash_account_id = "CASH"

    def __init__(self):
        self._holder_by_account_id = {}
        self._account_id_by_holder = {}
        self._entries = []
        self._transfers = {}
        self._reversed_transfer_ids = set()

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

    def transfer(self, from_account_id, to_account_id, amount, currency=CURRENCY):
        self._check_currency(currency)
        self._check_amount(amount)
        self._check_account_exists(from_account_id)
        self._check_account_exists(to_account_id)
        self._check_self_transfer(from_account_id, to_account_id)
        self._check_sufficient_funds(from_account_id, amount)

        transfer_id = str(uuid.uuid4())
        self._entries.append(Entry(transfer_id, from_account_id, -amount))
        self._entries.append(Entry(transfer_id, to_account_id, amount))
        self._transfers[transfer_id] = Transfer(from_account_id, to_account_id, amount)
        return transfer_id

    def reverse(self, transfer_id):
        original = self._transfers.get(transfer_id)
        if original is None:
            raise TransferNotFound(f"Transfer {transfer_id} does not exist")
        if transfer_id in self._reversed_transfer_ids:
            raise TransferAlreadyReversed(f"Transfer {transfer_id} has already been reversed")
        self._check_sufficient_funds(original.to_account_id, original.amount)

        reversal_id = str(uuid.uuid4())
        self._entries.append(Entry(reversal_id, original.to_account_id, -original.amount))
        self._entries.append(Entry(reversal_id, original.from_account_id, original.amount))
        self._reversed_transfer_ids.add(transfer_id)
        return reversal_id

    def balance(self, account_id, requested_by):
        self._check_account_exists(account_id)
        self._check_holder(account_id, requested_by)
        return self._balance_of(account_id)

    def statement(self, account_id, requested_by):
        raise NotImplementedError

    def entries_for(self, transfer_id):
        return [e for e in self._entries if e.transfer_id == transfer_id]

    def all_entries(self):
        return list(self._entries)

    def _check_currency(self, currency):
        if currency != CURRENCY:
            raise UnsupportedCurrency(f"Only {CURRENCY} is supported, got {currency!r}")

    def _check_amount(self, amount):
        if amount <= 0:
            raise InvalidAmount(f"Amount must be greater than 0, got {amount}")

    def _check_account_exists(self, account_id):
        if account_id not in self._holder_by_account_id:
            raise AccountNotFound(f"Account {account_id} does not exist")

    def _check_holder(self, account_id, requested_by):
        if self._holder_by_account_id[account_id] != requested_by:
            raise AccessDenied(f"{requested_by} cannot view account {account_id}")

    def _check_self_transfer(self, from_account_id, to_account_id):
        if from_account_id == to_account_id:
            raise SameAccountTransfer(f"Cannot transfer to the same account {to_account_id}")

    def _check_sufficient_funds(self, account_id, amount):
        available = self._balance_of(account_id)
        if amount > available:
            raise InsufficientFunds(
                f"Account {account_id} has {available}, cannot transfer {amount}"
            )

    def _balance_of(self, account_id):
        return sum(e.amount for e in self._entries if e.account_id == account_id)
