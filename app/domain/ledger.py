"""In-memory double-entry ledger for miniPay. Amounts are integer cents in SGD."""

import uuid

from app.domain.errors import AccountAlreadyExists


class Ledger:
    cash_account_id = "CASH"

    def __init__(self):
        self._holder_by_account_id = {}
        self._account_id_by_holder = {}

    def open_account(self, holder):
        if holder in self._account_id_by_holder:
            raise AccountAlreadyExists(f"{holder} already has an account")

        account_id = str(uuid.uuid4())
        self._holder_by_account_id[account_id] = holder
        self._account_id_by_holder[holder] = account_id
        return account_id

    def deposit(self, account_id, amount, currency="SGD"):
        raise NotImplementedError

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
