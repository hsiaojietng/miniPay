In Scope

1. Open account
2. Deposit of amount
3. Transfer of amount
4. View account balance
5. View account statement
6. Reverse an amount transfer

Out of Scope

1. Debit/Credit cards
2. Interest
3. Multiple currencies
4. User interface

Business Rules

1. Transfer/deposit amount must be greater than 0
2. Sender must have enough amount to perform transfer
3. Sender and receiver must be different accounts
4. Both sender and receiver accounts must exist
5. Only one currency (SGD)
6. Only one account per unique sender/receiver
7. Transfer/deposit amount must only apply to one destination account
8. Transfer/deposit amount must only come from one source account
9. Account holder can only view account balance/statement of their own account
10. Reverse amount transfer can only occur once
11. Reverse amount transfer can only be of the full amount, not partial

Edge Cases

1. Transferring to yourself
2. An amount of 0
3. An amount exceeding by 1 cent
4. Same request sent twice
5. Unknown account
6. Server crashing between debit and credit
7. 2 transfers from the same account at the same time
8. 2 transfers received in the same account at the same time
9. Deposit and tranfer amount at the same time 
10. Deposit more amount into account while transferring amount more than account at the same time

Acceptance Criteria

Open Account

1. Given Alice do not have an account, when she opts to create an account, then Alice's account will be created with $0
2. Given Alice already has an account, when she opts to create an account, the system will prompt account already exists

Deposit Amount

1. Given Alice has $10, when she deposits $30, then the special cash account will decrease by $30 and Alice account will increase by $30 to become $40
2. Given Alice has $0, when Alice transfers $0, then system will prompt deposit has to be greater than 0

Transfer Amount

1. Given Alice has $100, Bob has $0. When Alice transfers $20 to Bob, then Alice will have $80 left and Bob will have $20. Also, the sum of entries will be 0
2. Given Alice has $100, when Alice transfers $20 to herself, then Alice will have $100 left, also the sum of entries will be 0
3. Given Alice has $0, when Alice transfers $0, then system will prompt transfer has to be greater than 0
4. Given Alice has $20, when Alice transfers $30, then system will prompt account balance is not enough

View Account Balance

1. Given Alice has $30, when she views account balance, then system should present $30

View Account Statement

1. Given Alice has $30 and made a transfer of $20 to Bob and deposit of $20, when she views account statement, then system should present Alice had $30 at the start, show the account -$20 to Bob to become $10 and then +$20 to become $30 from the deposit
2. Given Bob has $20, when she views account statement, then system should present $20

Reverse an amount transfer

1. Given Alice made a transfer of $30 to Bob, when Alice makes a reverse transfer, then Alice's account +$30 and Bob's account -$30.
2. Given Alice has already made a reverse transfer, when Alice makes a reverse transfer, then system should prompt that no transfer has been made to be reversed
3. Given Alice did not make a transfer, when Alice makes a reverse transfer, then system should prompt that no transfer has been made to be reversed
