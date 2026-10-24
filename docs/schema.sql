CREATE TABLE accounts (
  id UUID PRIMARY KEY,
  owner_name TEXT NOT NULL,
  currency CHAR(3) NOT NULL DEFAULT 'SGD',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE transfers (
  id UUID PRIMARY KEY,
  from_account UUID NOT NULL REFERENCES accounts(id),
  to_account UUID NOT NULL REFERENCES accounts(id),
  amount_cents BIGINT NOT NULL CHECK (amount_cents > 0),
  status TEXT NOT NULL CHECK (status IN ('PENDING','COMPLETED','FAILED','REVERSED')),
  idempotency_key TEXT UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (from_account <> to_account)
);

CREATE TABLE ledger_entries (
  id BIGSERIAL PRIMARY KEY,
  transfer_id UUID NOT NULL REFERENCES transfers(id),
  account_id UUID NOT NULL REFERENCES accounts(id),
  amount_cents BIGINT NOT NULL,  -- negative = debit, positive = credit
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);