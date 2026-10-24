"""In-memory double-entry ledger for miniPay. Amounts are integer cents in SGD."""


class Ledger:
    cash_account_id = "CASH"

    def open_account(self, holder):
        raise NotImplementedError

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
