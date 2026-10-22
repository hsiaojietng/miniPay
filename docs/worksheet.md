Starting state
Account	Balance (cents)
ALICE	10000
BOB	2500
CASH	-12500

Scenario 1: Alice sends Bob 3000 cents (30.00).

Ledger entries I would write
Transfer Account Amount (cents)
T1   Alice   -3000
T2    Bob     +3000   

Account	Balance (cents)
ALICE	7000
BOB	5500
CASH	-12500

Scenario 2: Bob tries to send Alice 4000 cents (40.00). Start from the original state.

Ledger entries I would write
Transfer Account Amount (cents) Status
T1   Bob   -4000                Failed

Account	Balance (cents)
ALICE	10000
BOB	2500
CASH	-12500

Rule that stops it: Sender account does not have enough amount to transfer
Domain error raised: Transfer amount should be enough
Should a FAILED transfer record exist? Yes (/) / No, because: it should not exists. Since the basis of balancing is sum of all entries, if this exists, the system will not be balanced since the opposite effect (increase in the destination account did not occur)

Scenario 3: The 30.00 transfer from Example 1 is reversed.

Ledger entries I would write
Transfer Account Amount (cents)
T1   Alice   -3000
T2    Bob     +3000
T3   Alice   +3000
T3   Bob     -3000   

Account	Balance (cents)
ALICE	10000
BOB	2500
CASH	-12500

Status of the original transfer: Reversed
Status of the reversal: Completed
Why the original entries are never deleted: The entries were a success at the start before being reversed, hence they should exist as entries and they also meet the requirements that the sum of entries equals 0
Twist (Bob already sent 5000 to Carol): can the reversal go ahead? What should happen?: No, because another transaction is made. Bob might not even have enough in his account to reverse the amount and cause the system to fail.