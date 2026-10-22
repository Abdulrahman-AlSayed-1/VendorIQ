# VendorIQ — E-commerce Backend with Stripe Sandbox

VendorIQ is a deterministic, high-performance e-commerce REST API built with **Python 3.13+**, **FastAPI**, **PostgreSQL**, **SQLAlchemy 2.0 (async)**, **Alembic**, and **Stripe-hosted Checkout** (sandbox test mode).

---

## 1. Features & Architectural Highlights

- **Modular Monolith**: Strict separation of concerns across API route controllers, business domain services, database persistence, and gateway abstractions.
- **Argon2id Authentication & RBAC**: Memory-hard password hashing via `argon2-cffi` and PyJWT bearer token authorization supporting `customer` and `admin` roles.
- **Product Catalog**: Case-insensitive keyword search, filtering (by category UUID/slug, brand, price range, in-stock status), allowlisted sorting, pagination, and strict soft-deactivation preserving historical orders.
- **Server-Side Pricing & Cart**: Dynamic pricing calculations directly from the PostgreSQL catalog; client-supplied prices or discounts are strictly ignored.
- **Short-Lived Inventory Reservations**: PostgreSQL row-level locking (`SELECT ... FOR UPDATE`) during checkout session creation with 30-minute reservation TTLs to eliminate race conditions and overselling.
- **Stripe Sandbox Integration**: Itemized line items passed to Stripe-hosted Checkout in test mode (`sk_test_...`). Live-mode secret keys are strictly rejected at startup in development and test environments.
- **Idempotent Webhooks**: Raw HTTP byte signature verification (`Stripe-Signature`), event deduplication ledger (`stripe_webhook_events`), and automatic retry triggers (HTTP 500 on unhandled processing failures).
- **Hermetic Testing**: Fast, 100% offline test suite using in-memory SQLite (`aiosqlite`) and mocked Stripe SDK calls.

---

## 2. Prerequisites

- **Python**: `>= 3.13`
- **uv**: Fast Python package manager ([Install uv](https://docs.astral.sh/uv/))
- **Docker & Docker Compose**: For running PostgreSQL locally
- **Stripe CLI**: (Optional) For forwarding sandbox webhooks locally ([Install Stripe CLI](https://docs.stripe.com/stripe-cli))

---

## 3. Quickstart & Local Setup

### 3.1 Clone & Install Dependencies
```bash
git clone <repo-url>
cd VendorIQ
uv sync
```

### 3.2 Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Ensure `.env` contains your Stripe test mode credentials and settings:
```ini
APP_NAME="VendorIQ API"
APP_ENV=development
DEBUG=true
API_V1_PREFIX="/api/v1"

# Security
SECRET_KEY="replace-with-a-secure-random-secret-key-in-production"
ALGORITHM="HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Database (PostgreSQL with asyncpg driver)
DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/vendoriq"

# Stripe Sandbox Settings
STRIPE_SECRET_KEY="sk_test_replace_me"
STRIPE_PUBLISHABLE_KEY="pk_test_replace_me"
STRIPE_WEBHOOK_SECRET="whsec_replace_me"
STRIPE_CURRENCY="usd"
FRONTEND_URL="http://localhost:3000"
STRIPE_SUCCESS_URL="http://localhost:3000/checkout/success"
STRIPE_CANCEL_URL="http://localhost:3000/checkout/cancel"
CHECKOUT_RESERVATION_MINUTES=30
```

### 3.3 Start PostgreSQL Database
```bash
docker compose up -d
```

### 3.4 Apply Database Migrations
Run Alembic migrations to construct all tables, constraints, and indexes:
```bash
uv run alembic upgrade head
```

### 3.5 Seed Sample Data
Execute the idempotent seed script to populate sample categories, products, stock, and default test accounts:
```bash
uv run python -m vendoriq.scripts.seed
```
* **Default Admin**: `admin@vendoriq.local` / `AdminSecure123!`
* **Default Customer**: `customer@vendoriq.local` / `CustomerPass123!`

### 3.6 Start the API Server
```bash
uv run uvicorn vendoriq.main:app --reload --port 8000
```
* Interactive Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
* Redoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)
* Health Check: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

---

## 4. Testing & Code Quality

### Run Test Suite
Run the full automated test suite (hermetic, runs offline with in-memory SQLite):
```bash
uv run pytest
```

### Run Ruff Linter & Formatter
```bash
uv run ruff check .
uv run ruff format --check .
```

---

## 5. Stripe Sandbox Webhook Testing (Local Development)

To test Stripe checkout payments and webhooks locally on your machine:

1. **Login with Stripe CLI**:
   ```bash
   stripe login
   ```
2. **Forward Webhooks to Local API**:
   ```bash
   stripe listen --forward-to localhost:8000/api/v1/webhooks/stripe
   ```
3. **Set the Webhook Secret**:
   Copy the signing secret displayed by the CLI (e.g. `whsec_...`) and update `STRIPE_WEBHOOK_SECRET` in your `.env`.
4. **Trigger a Sample Test Webhook Event**:
   ```bash
   stripe trigger checkout.session.completed
   ```

---

## 6. API Workflow Examples

### 6.1 Customer Registration & Login
```bash
# Register
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice Johnson", "email": "alice@example.com", "password": "SecurePassword123!"}'

# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com", "password": "SecurePassword123!"}'
# Response returns {"access_token": "eyJhbG...", "token_type": "bearer"}
```

### 6.2 Product Discovery
```bash
# Search active products with keyword and price filter
curl -X GET "http://localhost:8000/api/v1/products?search=headphones&min_price=100.00&sort=price_asc"
```

### 6.3 Shopping Cart Operations
```bash
# Add product to cart
curl -X POST http://localhost:8000/api/v1/cart/items \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"product_id": "<PRODUCT_UUID>", "quantity": 1}'

# View cart with recalculated totals
curl -X GET http://localhost:8000/api/v1/cart \
  -H "Authorization: Bearer <TOKEN>"
```

### 6.4 Initiate Stripe Checkout
```bash
curl -X POST http://localhost:8000/api/v1/checkout/sessions \
  -H "Authorization: Bearer <TOKEN>"
# Returns:
# {
#   "order_id": "...",
#   "order_number": "ORD-20261022-XXXXXX",
#   "payment_id": "...",
#   "stripe_checkout_session_id": "cs_test_...",
#   "checkout_url": "https://checkout.stripe.com/c/pay/cs_test_...",
#   "expires_at": "..."
# }
```

### 6.5 Customer Order & Payment Retrieval
```bash
# List customer orders
curl -X GET http://localhost:8000/api/v1/orders \
  -H "Authorization: Bearer <TOKEN>"

# Get order details
curl -X GET http://localhost:8000/api/v1/orders/<ORDER_UUID> \
  -H "Authorization: Bearer <TOKEN>"

# Cancel a pending order (releases reserved stock)
curl -X POST http://localhost:8000/api/v1/orders/<ORDER_UUID>/cancel \
  -H "Authorization: Bearer <TOKEN>"

# Inspect payment status
curl -X GET http://localhost:8000/api/v1/payments/<PAYMENT_UUID> \
  -H "Authorization: Bearer <TOKEN>"
```

---

## 7. Documentation Index

For in-depth architectural and implementation specifications, see the `/docs` folder:
- **[Architecture Specification](docs/architecture.md)**
- **[Database Schema Specification](docs/database_schema.md)**
- **[REST API Specification](docs/api_specification.md)**
- **[Stripe Sandbox Integration Guide](docs/stripe_integration.md)**
- **[Inventory Policy & Order Lifecycle](docs/inventory_and_orders.md)**
- **[Implementation Roadmap & DoD](docs/implementation_roadmap.md)**
- **[Agent Engineering Guidelines](AGENTS.md)**
