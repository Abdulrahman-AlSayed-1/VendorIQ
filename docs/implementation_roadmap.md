# VendorIQ — Implementation Roadmap & Definition of Done

## 1. Phased Execution Roadmap

```
Phase 1: Foundation & Auth ──► Phase 2: Catalog & Cart ──► Phase 3: Stripe Sandbox ──► Phase 4: Orders & Hardening
```

---

### Phase 1 — Foundation & Authentication
- [x] Establish dependency baseline (`argon2-cffi`, `pyjwt`, `stripe`, `greenlet`, `aiosqlite`).
- [x] Configure Pydantic settings with Stripe sandbox safety and live-key rejection.
- [x] Implement core security module (`src/vendoriq/core/security.py`) with Argon2id and JWT.
- [x] Implement clean `User` entity with UUIDv4, normalized email, and roles (`customer`, `admin`).
- [x] Build `AuthService` handling registration, authentication, and JWT issuing.
- [x] Create API endpoints: `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `GET /api/v1/auth/me`.
- [x] Implement role-based dependency `CurrentAdminDep`.
- [x] Setup isolated in-memory test database fixture and verify auth tests.

---

### Phase 2 — Catalog, Cart & Inventory
- [ ] Implement `Category` and `Product` models with UUIDs, slugs, SKUs, and JSONB attributes/images.
- [ ] Implement `ProductService` with keyword search (`ILIKE`), filtering (category, brand, price range, in_stock), allowlisted sorting (`price_asc`, `price_desc`, `newest`), and pagination.
- [ ] Implement public catalog endpoints:
  * `GET /api/v1/products`
  * `GET /api/v1/products/{id_or_slug}`
  * `GET /api/v1/categories`
  * `GET /api/v1/categories/{id_or_slug}`
- [ ] Implement `Cart` and `CartItem` models with cascade deletion.
- [ ] Implement `CartService` with dynamic server-side price recalculation and inventory validation.
- [ ] Implement cart API endpoints:
  * `GET /api/v1/cart`
  * `POST /api/v1/cart/items`
  * `PATCH /api/v1/cart/items/{item_id}`
  * `DELETE /api/v1/cart/items/{item_id}`
  * `DELETE /api/v1/cart`
- [ ] Implement admin catalog management:
  * `POST /api/v1/admin/categories`
  * `PATCH /api/v1/admin/categories/{category_id}`
  * `POST /api/v1/admin/products`
  * `PATCH /api/v1/admin/products/{product_id}`
  * `PATCH /api/v1/admin/products/{product_id}/stock`
- [ ] Write automated tests for catalog search, filters, pagination, and cart mutations.

---

### Phase 3 — Stripe Sandbox & Checkout
- [ ] Implement `Order`, `OrderItem`, `Payment`, and `StripeWebhookEvent` models.
- [ ] Implement `InventoryService` with row-level locking (`SELECT ... FOR UPDATE`) and reservation TTL.
- [ ] Implement `PaymentService` isolating Stripe SDK operations:
  * `create_checkout_session(order, line_items)` with idempotency key `checkout_session_{order.id}`.
  * Itemized line item construction (cents conversion).
  * Webhook signature verification (`stripe.Webhook.construct_event`).
- [ ] Implement `CheckoutService` orchestrating cart validation, reservation, order snapshotting, and cart clearing.
- [ ] Implement `POST /api/v1/checkout/sessions` endpoint.
- [ ] Implement `POST /api/v1/webhooks/stripe` endpoint with idempotent event processing.
- [ ] Implement event handlers:
  * `checkout.session.completed` (finalizes stock, updates order to `paid`)
  * `checkout.session.expired` (releases stock, updates order to `cancelled`)
  * `checkout.session.async_payment_succeeded` / `failed`
- [ ] Write unit tests with mocked Stripe SDK covering successful payment, expiration, idempotency, and retries.

---

### Phase 4 — Orders, Administration & Hardening
- [ ] Implement customer order endpoints:
  * `GET /api/v1/orders` (paginated customer history)
  * `GET /api/v1/orders/{order_id}` (IDOR protected details)
  * `POST /api/v1/orders/{order_id}/cancel` (releases stock for `pending_payment` orders)
  * `GET /api/v1/payments/{payment_id}`
- [ ] Implement admin order fulfillment:
  * `GET /api/v1/admin/orders`
  * `PATCH /api/v1/admin/orders/{order_id}/status`
  * `POST /api/v1/admin/orders/reconcile-expired`
- [ ] Generate Alembic schema migration for all tables, constraints, and indexes.
- [ ] Write idempotent seed script `src/vendoriq/scripts/seed.py` for categories, products, stock, and default users.
- [ ] Update `README.md` with complete developer setup, Stripe test credentials, and CLI instructions.
- [ ] Execute full automated test suite and Ruff code linting.

---

## 2. Definition of Done Checklist

A milestone is only marked complete when all of the following criteria are validated:

- [ ] **Working Implementation**: All endpoints return valid schemas and HTTP status codes (no placeholders or stubs).
- [ ] **Atomic Safety**: External Stripe calls are never executed inside open database transactions.
- [ ] **Inventory Consistency**: Concurrent checkout attempts for the last item in stock never result in negative inventory or overselling.
- [ ] **Authoritative Pricing**: Client-supplied prices and totals are completely ignored; only database prices are used.
- [ ] **Webhook Idempotency**: Delivering the identical Stripe webhook twice produces zero duplicate state transitions or stock decrements.
- [ ] **Security**: Password hashes are never returned; customer resources cannot be accessed by unauthorized users; admin endpoints reject customer tokens.
- [ ] **Test Coverage**: All tests run and pass cleanly via `uv run pytest`.
- [ ] **Migrations & Seed**: Database can be initialized from scratch via Alembic and populated via `vendoriq.scripts.seed`.
