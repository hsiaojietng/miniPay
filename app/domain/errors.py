"""Domain errors raised by the miniPay ledger."""


class LedgerError(Exception):
    """Base class for all ledger business rule violations."""


class InvalidAmount(LedgerError):
    """Transfer/deposit amount is not greater than 0."""


class InsufficientFunds(LedgerError):
    """Sender does not have enough balance to perform the transfer."""


class SameAccountTransfer(LedgerError):
    """Sender and receiver are the same account."""


class AccountNotFound(LedgerError):
    """Sender or receiver account does not exist."""


class UnsupportedCurrency(LedgerError):
    """Currency is not SGD."""


class AccountAlreadyExists(LedgerError):
    """Holder already has an account."""


class AccessDenied(LedgerError):
    """Requester is not the holder of the account."""


class TransferNotFound(LedgerError):
    """Transfer to be reversed does not exist."""


class TransferAlreadyReversed(LedgerError):
    """Transfer has already been reversed."""
