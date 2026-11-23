# GCash / Maya payment gateway integration boundary

## Implemented now

The student portal accepts GCash, Maya and bank-transfer reference details plus a PDF/PNG/JPEG proof file (maximum 5 MB). The record remains `PENDING` until a Cashier or Administrator verifies it. Verification updates the account balance, revises the COR snapshot when needed and assigns an internal printable acknowledgment receipt number. Proof files are served only through an authenticated, ownership-checked download view.

## Not yet connected to a live provider

This project does not initiate a GCash/Maya checkout, receive provider-authenticated payment status, or call a provider's receipt API. A screenshot or reference number is evidence for staff review, not cryptographic proof that funds settled.

Live integration requires the institution to obtain and configure:

1. An approved merchant/business account for the selected provider.
2. Provider sandbox and production API credentials, kept in environment variables or a secrets manager.
3. Provider-specific checkout/order creation and return/cancel flows.
4. Provider-specific webhook endpoint, signature verification, timestamp/replay protection and idempotency handling.
5. Server-to-server transaction status confirmation before marking a payment `VERIFIED`.
6. Provider reconciliation and refund/cancellation handling.

Do not implement a webhook that trusts a browser redirect or unsigned JSON payload. The exact request signature algorithm and payload schema must come from the institution's current provider documentation and credentials. Configure the callback URL only after HTTPS deployment.
