-- 002: cached account balance, plus a database-level guard against negative balances.
-- Applies on top of docs/schema.sql. Runs in one transaction, so it either fully applies or not at all.

BEGIN;

ALTER TABLE accounts ADD COLUMN balance_cents BIGINT NOT NULL DEFAULT 0;
ALTER TABLE accounts ADD COLUMN allow_negative BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE accounts ADD CONSTRAINT balance_not_negative
  CHECK (allow_negative OR balance_cents >= 0);

-- CASH funds every deposit, so its balance is negative by design. Create it if it is missing,
-- and flag it before the backfill, or the backfill would trip the constraint on CASH.
INSERT INTO accounts (id, owner_name, allow_negative)
VALUES (gen_random_uuid(), 'CASH', TRUE)
ON CONFLICT (owner_name) DO UPDATE SET allow_negative = TRUE;

-- Backfill from the ledger. If any ordinary account sums to below zero, the constraint
-- rejects this UPDATE and the whole migration rolls back, so a broken ledger cannot slip through.
UPDATE accounts a
SET balance_cents = COALESCE(
  (SELECT SUM(e.amount_cents) FROM ledger_entries e WHERE e.account_id = a.id), 0
);

COMMIT;
