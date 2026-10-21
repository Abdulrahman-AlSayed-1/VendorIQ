# VendorIQ — Engineering Instructions & Guidelines for Agents

This document defines the persistent engineering standards, architectural boundaries, and operational protocols for working within the **VendorIQ** repository. All autonomous and paired agents must strictly adhere to these instructions.

---

## 1. Project Overview & Scope Boundaries
* **Product**: VendorIQ is an e-commerce backend REST API built with **Python 3.13+**, **FastAPI**, **PostgreSQL**, **SQLAlchemy 2.0 (async)**, **Alembic**, and **Stripe-hosted Checkout** (sandbox test mode).
* **Deterministic Core**: Build robust, deterministic backend services that a future AI agent can invoke via tools without rewriting business logic.
* **Explicit Exclusions (Current Phase)**:
  * **NO** AI-agents, LLMs, prompts, or AI tool calling.
  * **NO** vector databases or semantic search.
  * **NO** live payment processing or production Stripe credentials.
  * **NO** microservices, message brokers, or premature distributed architecture.
  * **NO** frontend application implementation.

---

## 2. Core Engineering Mindset & Protocols
* **Inspect Before Modifying**: Always read existing code, models, schemas, and tests before writing or editing files. Reuse established conventions.
* **Incremental Execution**: Implement features in small, testable slices. Never create massive disconnected drafts.
* **Honest Test Execution**: Never assume or claim tests passed without executing them via the CLI and inspecting stdout/stderr. Report actual test counts and failures verbatim.
* **Documentation Currency**: When architecture or schema evolves, keep `/docs` synchronized.

---

## 3. Architecture & Directory Boundaries

The repository uses a **Modular Monolith** with standard Python `src`-layout (`src/vendoriq/`):

```
src/vendoriq/
├── api/
│   ├── deps.py               # Dependency injection (SessionDep, CurrentUserDep, CurrentAdminDep)
│   └── routes/               # Thin HTTP controllers (auth, products, cart, checkout, orders, admin, webhooks)
├── core/
│   ├── config.py             # Pydantic Settings with env validation & Stripe safety
│   ├── db.py                 # Async engine & sessionmaker
│   ├── security.py           # Argon2id hashing & PyJWT encoding/decoding
│   └── exceptions.py         # Domain-level exceptions
├── models/                   # SQLAlchemy 2.0 DeclarativeBase models (UUID PKs)
├── schemas/                  # Pydantic v2 validation and serialization schemas
├── services/                 # Authoritative business logic and domain workflows
└── scripts/                  # Idempotent database seed and CLI maintenance scripts
```

### Boundary Rules
1. **Thin HTTP Handlers**: Route handlers in `api/routes/` only parse parameters, call services, and return schemas. Zero business logic in routes.
2. **Business Rules in Services**: Validation, calculations, status transitions, and inventory mutations belong exclusively in `services/`.
3. **Payment Abstraction**: All Stripe SDK calls are encapsulated inside `services/payment_service.py`. The rest of the application remains agnostic of the payment gateway.
4. **No External Network Calls Inside Database Transactions**:
   * Holding an open database transaction during external HTTP calls (e.g. Stripe API) causes connection pool exhaustion and lock contention.
   * Commit local reservations before calling external APIs; persist API results in a follow-up transaction.

---

## 4. Coding Conventions & Type Safety
* **Python Version**: `>= 3.13`.
* **Typing**: Enforce strict type hints on all functions and methods. Use modern standard-library syntax (`list[str]`, `dict[str, Any]`, `X | None`, `typing.Annotated`).
* **Pydantic v2**:
  * Use `BaseModel` with explicit field constraints (`Field(..., min_length=...)`).
  * Enable `model_config = ConfigDict(from_attributes=True)` on read schemas.
* **Monetary Precision**:
  * **NEVER** use binary floating-point numbers (`float`) for prices or totals.
  * Internally & in DB: Use `Decimal` / `NUMERIC(10, 2)`.
  * Stripe Integration: Convert `Decimal` to integer cents (`int(amount * 100)`) exclusively within `PaymentService`.
* **Code Style**: Format and lint using **Ruff**. Clean imports, zero dead code, no unused variables.

---

## 5. Database, Concurrency & Inventory Rules
* **Primary Keys**: Use `uuid.UUID` (`UUID(as_uuid=True)`) as primary keys across all tables.
* **Public Order Identifier**: Generate a customer-friendly tracking code (`order_number`: `ORD-YYYYMMDD-XXXX`) in addition to internal UUIDs.
* **Single Source of Truth**: The client is never the source of truth for prices, discounts, stock, or payment state.
* **Inventory Policy**:
  * Implement a **Short-Lived Reservation Model** (30-minute TTL).
  * Use row-level locking (`SELECT ... FOR UPDATE`) during checkout session creation to prevent race conditions and overselling.
  * Enforce DB constraint: `CHECK (stock >= 0)`.
  * If a Stripe checkout session expires, fails, or is cancelled, release reserved stock back atomically.
* **Catalog Soft-Deactivation**:
  * Products must use soft-deactivation (`is_active = False`) rather than physical deletion (`DELETE`).
  * Preserve historical order integrity by saving immutable snapshots of product name, SKU, and unit price in `OrderItem`.
* **Migrations**:
  * Use **Alembic** for all schema updates.
  * Production must never use `Base.metadata.create_all()`.

---

## 6. Authentication & Authorization
* **Password Hashing**: Use **Argon2id** via `argon2-cffi`. Never use plaintext or weak legacy hashes.
* **Tokens**: Use signed **JWTs** (`HS256`) with configurable expiration via `ACCESS_TOKEN_EXPIRE_MINUTES`.
* **Roles & RBAC**:
  * User roles: `customer` and `admin`.
  * Public registration (`POST /api/v1/auth/register`) strictly assigns `customer`. Admin accounts are created via seed or administrative action.
  * Admin endpoints require `CurrentAdminDep`.
* **IDOR Prevention**:
  * All customer cart, order, and payment operations must be explicitly scoped by `user_id == current_user.id`.

---

## 7. Stripe Sandbox & Webhooks
* **Test Mode Only**: Restrict checkout strictly to Stripe test mode. Reject any `sk_live_` secret key at startup in development and test environments.
* **Line Items**: Pass fully itemized line items (name, description, unit price in cents, quantity) to Stripe Checkout.
* **Idempotency**: Use deterministic idempotency keys (`f"checkout_session_{order.id}"`) when calling Stripe.
* **Webhook Verification**:
  * Read the **raw HTTP body bytes** (`await request.body()`) and verify `Stripe-Signature` using `stripe.Webhook.construct_event`.
  * Webhook route must not require user authentication.
* **Event Idempotency Ledger**:
  * Persist `stripe_event_id` in `stripe_webhook_events`.
  * Skip previously processed events with `200 OK`.
  * On unhandled database or processing exceptions, return `HTTP 500` so Stripe automatically retries event delivery.
* **Authoritative Payment Transition**:
  * Mark orders `paid` only when verified `checkout.session.completed` (with `payment_status == 'paid'`) or `checkout.session.async_payment_succeeded` arrives.

---

## 8. Testing & Quality Assurance
* **Hermetic Testing**: Automated tests must run fast and offline using `pytest-asyncio` and an in-memory SQLite database (`sqlite+aiosqlite:///:memory:`).
* **Mocked Stripe SDK**: Unit and API tests must mock Stripe SDK calls to ensure deterministic execution without network dependency.
* **Run Tests**: Execute tests via `uv run pytest`.
* **Linting**: Execute linting via `uv run ruff check .`.
