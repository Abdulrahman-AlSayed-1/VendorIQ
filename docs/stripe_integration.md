# VendorIQ — Stripe Sandbox Payment Integration Guide

## 1. Overview & Security Safeguards

VendorIQ integrates with **Stripe-hosted Checkout** strictly in **Test Mode (Sandbox)**. Real payment charges are strictly blocked by code assertions.

### 1.1 Environment Configuration (.env)
```ini
STRIPE_SECRET_KEY=sk_test_replace_me
STRIPE_PUBLISHABLE_KEY=pk_test_replace_me
STRIPE_WEBHOOK_SECRET=whsec_replace_me
STRIPE_CURRENCY=usd
FRONTEND_URL=http://localhost:3000
STRIPE_SUCCESS_URL=http://localhost:3000/checkout/success?session_id={CHECKOUT_SESSION_ID}
STRIPE_CANCEL_URL=http://localhost:3000/checkout/cancel
CHECKOUT_RESERVATION_MINUTES=30
```

### 1.2 Live-Mode Safeguard
In `src/vendoriq/core/config.py`, a Pydantic validator guarantees that if `APP_ENV != "production"`, any key starting with `sk_live_` causes immediate application failure:
```python
if env in ("development", "test", "testing") and v.startswith("sk_live_"):
    raise ValueError(
        "Live-mode Stripe secret keys are strictly prohibited in development and test environments."
    )
```

---

## 2. Checkout Session Creation

When an authenticated customer initiates checkout (`POST /api/v1/checkout/sessions`):

1. **Cart Loading & Revalidation**: The customer's cart is loaded. Empty carts or items exceeding current stock are rejected.
2. **Authoritative Line Items**: Prices are evaluated directly from the `Product` table (never client input).
3. **Inventory Reservation**: Stock is decremented inside a database transaction with `SELECT ... FOR UPDATE` (reservation expires in 30 minutes).
4. **Order & Payment Creation**:
   * Order created with status `pending_payment`.
   * Order items created with full snapshots.
   * Cart items are cleared.
   * Associated `Payment` record created with status `pending`.
5. **Stripe API Call (Outside DB Transaction)**:
   * Deterministic idempotency key: `f"checkout_session_{order.id}"`.
   * Stripe-hosted checkout parameters:
     * `payment_method_types = ["card"]`
     * `mode = "payment"`
     * `client_reference_id = str(order.id)`
     * `metadata = {"order_id": str(order.id), "order_number": order.order_number}`
     * `expires_at = int(order.expires_at.timestamp())`
     * `line_items`: Each item converted to cents (`int(item.unit_price * 100)`).
6. **Session Persistence**: Stripe's `cs_test_...` session ID is stored in the `Payment` record and returned to the client alongside `session.url`.

---

## 3. Stripe Webhook Architecture (`/api/v1/webhooks/stripe`)

### 3.1 Signature Verification
Stripe signs every webhook using HMAC-SHA256 in the `Stripe-Signature` header.
* The endpoint reads the **raw HTTP body bytes** (`await request.body()`) before JSON parsing.
* Verifies signature via `stripe.Webhook.construct_event(payload_bytes, sig_header, settings.STRIPE_WEBHOOK_SECRET)`.
* Returns `HTTP 400` if signature is invalid or secret mismatch.

### 3.2 Idempotency & Duplicate Protection
Stripe uses at-least-once delivery; events can be re-delivered.
1. The unique `event.id` is queried in `stripe_webhook_events`.
2. If the record exists and status is `'processed'`, the endpoint immediately responds with `HTTP 200 OK` (no repeated business effects).
3. If new, the event is saved with status `'pending'`.

### 3.3 Authoritative Event-to-State Mapping

| Stripe Event | Authoritative Condition | Payment Status | Order Status | Inventory Effect |
| :--- | :--- | :--- | :--- | :--- |
| `checkout.session.completed` | `session.payment_status == 'paid'` | `succeeded` | `paid` | Reservation finalized (committed permanently) |
| `checkout.session.completed` | `session.payment_status == 'unpaid'` (async payment) | `pending` | `pending_payment` | Remains reserved waiting for settlement |
| `checkout.session.async_payment_succeeded` | Async payment cleared | `succeeded` | `paid` | Reservation finalized |
| `checkout.session.async_payment_failed` | Async payment bounced | `failed` | `cancelled` | Reserved stock released back to inventory |
| `checkout.session.expired` | Customer abandoned session | `cancelled` | `cancelled` | Reserved stock released back to inventory |
| `payment_intent.payment_failed` | Card declined / failed | `failed` | `pending_payment` or `cancelled` | Re-attempt allowed or stock released |

---

## 4. Local Testing with Stripe CLI

To test webhooks on a local development machine:

1. **Install Stripe CLI**:
   ```bash
   brew install stripe/stripe-cli/stripe
   ```
2. **Authenticate with Test Account**:
   ```bash
   stripe login
   ```
3. **Forward Webhooks to Local Server**:
   ```bash
   stripe listen --forward-to localhost:8000/api/v1/webhooks/stripe
   ```
4. **Copy Signing Secret**:
   The CLI outputs `> Ready! Your webhook signing secret is whsec_...`.
   Paste this value into `.env` as `STRIPE_WEBHOOK_SECRET`.
5. **Trigger Test Events**:
   ```bash
   stripe trigger checkout.session.completed
   ```
