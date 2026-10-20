# SIH Showcase — Investigation Summary (SYNTHETIC DATA — DEMONSTRATION ONLY)

Case {{CASE_NUMBER}} — Sunrise Mercantile payment-diversion fraud.
All names, accounts, transactions and hashes below are fictional.

## Established findings

1. On 2026-04-05 an unauthorised debit of INR 47,500.00 (TXN-SIH-1001) left
   the complainant's account for beneficiary account ACCSIH001
   (evidence:{{EV_STATEMENT}}).

2. The merchant wallet settlement ledger records the same reference
   TXN-SIH-1001 at INR 45,000.00 on 2026-04-05 — a discrepancy of
   INR 2,500.00 against the bank statement (evidence:{{EV_LEDGER}}).

3. Six dated completed debits between 2026-04-05 and 2026-04-10 total
   INR 125,700.00, of which two debits of INR 47,500.00 each share the same
   amount (TXN-SIH-1001 and TXN-SIH-1004) (evidence:{{EV_STATEMENT}}).

4. A credential-phishing campaign impersonating the merchant was active on
   2026-04-10; the captured lure email failed Message-ID checks and its
   Return-Path domain does not match its From domain
   (evidence:{{EV_URLS}}).

## Claims under review (deliberately imperfect draft for the AI auditor)

5. The merchant director personally approved every transfer on
   2026-04-04 (timeline:{{EV_TIMELINE}}).

6. TXN-SIH-1002 moved INR 15,300.00 from the complainant's account
   (evidence:{{EV_STATEMENT}}).

7. The funds were routed through a hawala network in Dubai
   (evidence:{{EV_MISSING}}).

8. The merchant account was opened using forged GST documents.

## Total exposure

Across all seven debits in the statement the total exposure is
INR 125,000.00 (evidence:{{EV_STATEMENT}}).
