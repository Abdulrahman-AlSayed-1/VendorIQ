# VendorIQ — E-commerce Backend & AI Shopping Agent

VendorIQ is a deterministic, high-performance e-commerce REST API and autonomous conversational shopping assistant built with **Python 3.13+**, **FastAPI**, **PostgreSQL**, **SQLAlchemy 2.0 (async)**, **Alembic**, **Stripe-hosted Checkout** (sandbox test mode), and an intelligent WhatsApp shopping agent powered by **Google Gemini** (`google-genai`) and **neonize**.

---

## 1. Features & Architectural Highlights

### Deterministic Core Backend
- **Modular Monolith**: Strict separation of concerns across API route controllers, business domain services, database persistence, and payment gateway abstractions.
- **Argon2id Authentication & RBAC**: Memory-hard password hashing via `argon2-cffi` and PyJWT bearer token authorization supporting `customer` and `admin` roles.
- **Product Catalog**: Case-insensitive keyword search, filtering (by category UUID/slug, brand, price range, in-stock status), allowlisted sorting, pagination, and strict soft-deactivation preserving historical orders.
- **Server-Side Pricing & Cart**: Dynamic pricing calculations directly from the PostgreSQL catalog; client-supplied prices or discounts are strictly ignored.
- **Short-Lived Inventory Reservations**: PostgreSQL row-level locking (`SELECT ... FOR UPDATE`) during checkout session creation with 30-minute reservation TTLs to eliminate race conditions and overselling.
- **Stripe Sandbox Integration**: Itemized line items passed to Stripe-hosted Checkout in test mode (`sk_test_...`). Live-mode secret keys are strictly rejected at startup in development and test environments.
- **Idempotent Webhooks**: Raw HTTP byte signature verification (`Stripe-Signature`), event deduplication ledger (`stripe_webhook_events`), and automatic retry triggers (HTTP 500 on unhandled processing failures).
- **Hermetic Testing**: Fast, 100% offline test suite with 51 passing tests using in-memory SQLite (`aiosqlite`) and mocked Stripe SDK / Gemini calls.

### WhatsApp AI Shopping Agent
- **Powered by Google Gemini**: Built with `google-genai` and `neonize` multi-device client.
- **Zero-Friction Customer Onboarding**: Automatically maps incoming WhatsApp phone numbers to authenticated customer records in PostgreSQL without manual sign-up.
- **Autonomous Toolset**: The agent executes real business logic through domain tools:
  - Catalog browsing and semantic/keyword product search.
  - Live stock checks and product specification lookups.
  - Shopping cart management (add, update quantities, remove, clear, recalculate).
  - Stripe checkout session generation with clickable payment URLs.
  - Order tracking and order cancellation.
- **Private Chat Exclusivity**: Ignores group chats, status broadcasts, and channel updates—the bot only interacts in 1-on-1 private direct messages.
- **"Message Yourself" Testing**: Full loop protection (outgoing message ID tracking and response text timestamp caching) allowing single-device self-testing without recursive loops.
- **Proactive Payment Confirmations**: A background worker continuously monitors the database for newly completed orders (`status == PAID` and `whatsapp_notified_at IS NULL`) and immediately pushes itemized payment confirmations to the customer's WhatsApp chat.

---

## 2. Prerequisites

- **Python**: `>= 3.13`
- **uv**: Ultra-fast Python package manager ([Install uv](https://docs.astral.sh/uv/))
- **Docker & Docker Compose**: For running PostgreSQL locally
- **libmagic**: Required by `neonize` for media file detection (`brew install libmagic` on macOS)
- **Stripe CLI**: (Optional) For forwarding sandbox webhooks to `localhost:8000` ([Install Stripe CLI](https://docs.stripe.com/stripe-cli))

---

## 3. Quickstart & Local Setup

### 3.1 Clone & Install Dependencies
```bash
git clone <repo-url>
cd VendorIQ
uv sync
```

*(On macOS, install `libmagic` if not already installed)*:
```bash
brew install libmagic
```

### 3.2 Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Ensure `.env` contains your database, Stripe sandbox credentials, and Gemini API key:
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

# AI Shopping Assistant (Google Gemini & WhatsApp)
GEMINI_API_KEY="your-gemini-api-key"
GEMINI_MODEL="gemini-2.0-flash"
GEMINI_TEMPERATURE=0.2
AI_SESSION_TTL_MINUTES=60
AI_SESSION_MAX_TURNS=20
WHATSAPP_SESSION_NAME="vendoriq_whatsapp.db"
```

### 3.3 Start PostgreSQL Database
```bash
docker compose up -d
```

### 3.4 Apply Database Migrations
Run Alembic migrations to construct all tables, constraints, indexes, and notification tracking columns:
```bash
uv run alembic upgrade head
```

### 3.5 Seed Sample Data
Execute the idempotent seed script to populate sample categories, products, stock, and default test accounts:
```bash
uv run python -m vendoriq.scripts.seed
```
* **Default Admin**: `admin@vendoriq.com` / `AdminSecure123!`
* **Default Customer**: `customer@vendoriq.com` / `CustomerPass123!`

### 3.6 Periodic Reservation Reconciler (Optional / Cron)
Release abandoned checkout reservations older than 30 minutes:
```bash
uv run python -m vendoriq.scripts.reconcile
```

### 3.7 Start the REST API Server
```bash
uv run uvicorn vendoriq.main:app --reload --port 8000
```
* **Interactive Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
* **Interactive Redoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
* **Health Check**: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

### 3.8 Start the WhatsApp AI Bot
In a dedicated terminal, launch the WhatsApp bot client:
```bash
uv run vendoriq-bot
# or: uv run python -m vendoriq.ai.bot
```
1. On the first launch, a QR code appears in your terminal.
2. Open WhatsApp on your phone → **Linked Devices** → **Link a Device** → scan the terminal QR code.
3. Once connected, message the bot (or use WhatsApp's **"Message Yourself"** feature) to start shopping!

---

## 4. Stripe Sandbox Webhook Testing (Local Development)

Because Stripe webhooks are sent from Stripe's cloud servers, testing them on a local `localhost:8000` development server requires forwarding:

1. **Login with Stripe CLI**:
   ```bash
   stripe login
   ```
2. **Forward Webhooks to Local API**:
   ```bash
   stripe listen --forward-to localhost:8000/api/v1/webhooks/stripe
   ```
3. **Copy the Webhook Secret**:
   Copy the `whsec_...` signing secret printed by the Stripe CLI and paste it into `STRIPE_WEBHOOK_SECRET` in your `.env`.
4. **Complete Checkout**:
   When you complete a test checkout with Stripe's test card `4242 4242 4242 4242`, the Stripe CLI forwards the webhook to your local server within milliseconds, and the WhatsApp bot immediately sends an outbound payment confirmation!

---

## 5. Testing & Code Quality

### Run Automated Tests
Fast, hermetic, 100% offline test suite using in-memory SQLite (`aiosqlite`) and mocked external services:
```bash
uv run pytest
```

### Run Ruff Linter & Formatter
```bash
uv run ruff check .
uv run ruff format --check .
```

---

## 6. API Workflow Examples

### 6.1 Customer Registration & Login
```bash
# Register
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice Johnson", "email": "alice@vendoriq.com", "password": "SecurePassword123!"}'

# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@vendoriq.com", "password": "SecurePassword123!"}'
# Response returns {"access_token": "eyJhbG...", "token_type": "bearer"}
```

### 6.2 Product Discovery
```bash
# Search active products with keyword and price filter
curl -X GET "http://localhost:8000/api/v1/products?search=keyboard&min_price=50.00&sort=price_asc"
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
```

### 6.5 Customer Order Retrieval & Cancellation
```bash
# List customer orders
curl -X GET http://localhost:8000/api/v1/orders \
  -H "Authorization: Bearer <TOKEN>"

# Cancel a pending order (atomically releases reserved stock)
curl -X POST http://localhost:8000/api/v1/orders/<ORDER_UUID>/cancel \
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
