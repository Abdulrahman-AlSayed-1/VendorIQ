# VendorIQ — System Architecture & Design Specification

## 1. Overview & Architectural Goals
VendorIQ is a deterministic, secure, and performant e-commerce REST API backend built with **FastAPI**, **PostgreSQL**, and **SQLAlchemy 2.0 (async)**, featuring complete **Stripe-hosted Checkout (sandbox test mode)** payment lifecycle management.

The system is architected as a **Modular Monolith** with strict layer isolation:
- **Thin HTTP Controllers (`src/vendoriq/api/`)**: Handle request parsing, validation, HTTP response formatting, and status codes. No direct business logic.
- **Service Layer (`src/vendoriq/services/`)**: Enforces business rules, transactions, cart calculations, inventory validation, and checkout orchestration.
- **Payment Abstraction (`src/vendoriq/services/payment_service.py`)**: Isolates all external Stripe SDK interactions behind a clean provider interface, preventing vendor lock-in.
- **Persistence Layer (`src/vendoriq/models/`, `src/vendoriq/core/db.py`)**: SQLAlchemy 2.0 declarative models using UUID primary keys, normalized relationships, and async sessions.
- **Schemas (`src/vendoriq/schemas/`)**: Strict Pydantic v2 schemas providing input contracts, output sanitization, and automatic OpenAPI documentation.

---

## 2. Directory Structure Layout

```
VendorIQ/
├── docs/                               # Comprehensive architecture and implementation plans
│   ├── architecture.md
│   ├── database_schema.md
│   ├── api_specification.md
│   ├── stripe_integration.md
│   ├── inventory_and_orders.md
│   └── implementation_roadmap.md
├── alembic/                            # Database schema migrations
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── src/vendoriq/
│   ├── __init__.py
│   ├── main.py                         # FastAPI application factory, CORS, exception handlers
│   ├── core/
│   │   ├── config.py                   # Pydantic Settings with env validation & Stripe safety
│   │   ├── db.py                       # Async engine & sessionmaker
│   │   ├── security.py                 # Argon2id password hashing & PyJWT token utilities
│   │   └── exceptions.py               # Custom domain exceptions
│   ├── models/
│   │   ├── base.py                     # SQLAlchemy DeclarativeBase
│   │   ├── user.py                     # User entity & UserRole enum
│   │   ├── category.py                 # Category entity
│   │   ├── product.py                  # Product entity
│   │   ├── cart.py                     # Cart & CartItem entities
│   │   ├── order.py                    # Order & OrderItem entities
│   │   ├── payment.py                  # Payment entity & PaymentStatus enum
│   │   └── webhook_event.py            # StripeWebhookEvent entity
│   ├── schemas/
│   │   ├── auth.py / user.py           # Registration, login, profile schemas
│   │   ├── category.py                 # Category read/create/update schemas
│   │   ├── product.py                  # Product read/filter/create/update schemas
│   │   ├── cart.py                     # Cart & item schemas with totals
│   │   ├── checkout.py                 # Checkout session request/response
│   │   ├── order.py                    # Order and order-item detail schemas
│   │   └── payment.py                  # Payment status schemas
│   ├── services/
│   │   ├── auth_service.py             # User authentication and JWT tokens
│   │   ├── product_service.py          # Catalog querying, filtering, sorting, pagination
│   │   ├── cart_service.py             # Cart mutation and price recalculation
│   │   ├── inventory_service.py        # Row-level locking & stock reservation
│   │   ├── order_service.py            # Order creation, snapshots, state transitions
│   │   ├── checkout_service.py         # Checkout orchestration and cart-to-order workflow
│   │   └── payment_service.py          # Stripe SDK calls, sessions, webhooks verification
│   ├── api/
│   │   ├── deps.py                     # Dependency injection (AsyncSession, CurrentUser, RequireAdmin)
│   │   └── routes/
│   │       ├── health.py               # Liveness and readiness endpoints
│   │       ├── auth.py                 # Register, login, profile endpoints
│   │       ├── products.py             # Public catalog endpoints
│   │       ├── categories.py           # Public category endpoints
│   │       ├── cart.py                 # Authenticated customer cart endpoints
│   │       ├── checkout.py             # Checkout session creation
│   │       ├── orders.py               # Customer order history & details
│   │       ├── payments.py             # Customer payment status retrieval
│   │       ├── webhooks.py             # Stripe raw signature verified webhook handler
│   │       └── admin.py                # Protected catalog and order fulfillment operations
│   └── scripts/
│       └── seed.py                     # Idempotent development seed script
└── tests/
    ├── conftest.py                     # Async in-memory SQLite fixture, mock clients, test users
    ├── test_health.py                  # Health API tests
    ├── test_auth.py                    # Authentication & authorization tests
    ├── test_catalog.py                 # Catalog search, filter, pagination tests
    ├── test_cart.py                    # Cart operations & pricing tests
    ├── test_checkout.py                # Checkout session & reservation tests
    ├── test_webhooks.py                # Webhook signature & event processing tests
    └── test_admin.py                   # Administrative catalog & order tests
```

---

## 3. Core Architectural Principles & Boundaries

### 3.1 Network vs. Database Transaction Boundaries
* External network requests (such as Stripe API calls) **must never be executed inside an open database transaction**.
* Open database transactions hold connections and row-level locks; waiting on external network I/O invites thread starvation, lock contention, and connection pool exhaustion.
* **Pattern**:
  1. Transaction 1: Create local pending Order and reserve stock with `SELECT ... FOR UPDATE`, commit transaction.
  2. External Call: Invoke `stripe.checkout.Session.create(...)` using deterministic idempotency key.
  3. Transaction 2: Update Order with Stripe Session ID and create Payment record, commit transaction.
  4. If Step 2 fails, roll back or release Step 1's reservation.

### 3.2 Single Source of Truth
* The client is **never** the source of truth for:
  * Product prices
  * Discounts or line item totals
  * Available inventory
  * Payment status
* All prices and totals are dynamically evaluated on the server directly from the PostgreSQL catalog.

### 3.3 Security & Role-Based Access Control (RBAC)
* Passwords hashed with **Argon2id** (`argon2-cffi`), memory-hard and resistant to GPU cracking.
* Tokens are signed **JWTs** (`HS256`) with configurable expiration.
* Direct Object Reference Protection (IDOR):
  * Every cart, order, and payment query enforces `WHERE user_id = current_user.id`.
  * Customers cannot inspect or modify other customers' data.
* Administrative Endpoints:
  * Protected via `CurrentAdminDep` enforcing `user.role == UserRole.ADMIN`.
  * Catalog management, product deactivation, stock overrides, and fulfillment state transitions require admin privileges.

### 3.4 Stripe Sandbox Isolation & Safety
* Environment settings strictly validate `STRIPE_SECRET_KEY`:
  * If `APP_ENV != "production"`, any key starting with `sk_live_` raises an immediate startup exception.
  * Real card numbers are never accepted, stored, or processed. All transactions use Stripe-hosted Checkout in test mode.
