# VendorIQ — REST API Specification

All endpoints are prefixed with `/api/v1` and use standard JSON request and response bodies unless otherwise specified.

---

## 1. Authentication & Users

### 1.1 `POST /api/v1/auth/register`
* **Access**: Public
* **Status**: `201 Created`
* **Request**:
```json
{
  "name": "Alex Mercer",
  "email": "alex.mercer@example.com",
  "password": "StrongPassword123!"
}
```
* **Response**:
```json
{
  "id": "a3b4c5d6-e7f8-4a9b-8c1d-2e3f4a5b6c7d",
  "name": "Alex Mercer",
  "email": "alex.mercer@example.com",
  "role": "customer",
  "is_active": true,
  "created_at": "2026-10-21T20:00:00Z",
  "updated_at": "2026-10-21T20:00:00Z"
}
```
* **Errors**: `409 Conflict` if email already registered; `422 Unprocessable Entity` on validation failure.

### 1.2 `POST /api/v1/auth/login`
* **Access**: Public
* **Status**: `200 OK`
* **Request**:
```json
{
  "email": "alex.mercer@example.com",
  "password": "StrongPassword123!"
}
```
* **Response**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6...",
  "token_type": "bearer",
  "expires_in": 86400
}
```
* **Errors**: `401 Unauthorized` on invalid credentials; `403 Forbidden` if account is deactivated.

### 1.3 `GET /api/v1/auth/me`
* **Access**: Authenticated Customer or Admin (`Bearer <token>`)
* **Status**: `200 OK`
* **Response**: Returns the `UserRead` model.

---

## 2. Product Catalog

### 2.1 `GET /api/v1/products`
* **Access**: Public
* **Query Parameters**:
  * `search`: string (case-insensitive keyword search against name, brand, description)
  * `category_id`: UUID
  * `category_slug`: string
  * `brand`: string
  * `min_price`: decimal (`>= 0`)
  * `max_price`: decimal (`>= min_price`)
  * `in_stock`: boolean (if true, only products with `stock > 0`)
  * `sort`: enum (`price_asc`, `price_desc`, `newest`) Default: `newest`
  * `page`: integer (`>= 1`, default: `1`)
  * `page_size`: integer (`1` to `100`, default: `20`)
* **Response**:
```json
{
  "items": [
    {
      "id": "e8d2e8b0-51a4-4361-9c16-b8dc5cf60a77",
      "name": "Studio Wireless Headphones",
      "slug": "studio-wireless-headphones",
      "sku": "AUD-HDPH-001",
      "description": "High-fidelity noise cancelling headphones",
      "brand": "AcousticPro",
      "category_id": "c1f7b0b2-29e3-4c91-9cb1-3a9a1d418290",
      "price": "199.99",
      "currency": "usd",
      "stock": 45,
      "attributes": {"color": "Midnight Black", "bluetooth": "5.3"},
      "image_urls": ["https://images.example.com/hdph1.jpg"],
      "is_active": true,
      "created_at": "2026-10-21T18:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

### 2.2 `GET /api/v1/products/{id_or_slug}`
* **Access**: Public
* **Status**: `200 OK` (or `404 Not Found` if missing or inactive).

### 2.3 `GET /api/v1/categories` & `GET /api/v1/categories/{id_or_slug}`
* **Access**: Public
* **Response**: Returns category details or list of active categories.

---

## 3. Shopping Cart Management

### 3.1 `GET /api/v1/cart`
* **Access**: Authenticated Customer
* **Response**:
```json
{
  "id": "7b8e1a2f-9c0d-4e5f-b6a7-8c9d0e1f2a3b",
  "items": [
    {
      "id": "2c3d4e5f-6a7b-8c9d-0e1f-2a3b4c5d6e7f",
      "product_id": "e8d2e8b0-51a4-4361-9c16-b8dc5cf60a77",
      "product_name": "Studio Wireless Headphones",
      "sku": "AUD-HDPH-001",
      "unit_price": "199.99",
      "quantity": 2,
      "line_total": "399.98",
      "in_stock": true,
      "available_stock": 45
    }
  ],
  "currency": "usd",
  "subtotal": "399.98",
  "discount_total": "0.00",
  "grand_total": "399.98",
  "item_count": 2
}
```

### 3.2 `POST /api/v1/cart/items`
* **Access**: Authenticated Customer
* **Request**:
```json
{
  "product_id": "e8d2e8b0-51a4-4361-9c16-b8dc5cf60a77",
  "quantity": 1
}
```
* **Behavior**: If product already in cart, increments quantity. Validates `quantity <= product.stock`.

### 3.3 `PATCH /api/v1/cart/items/{item_id}`
* **Access**: Authenticated Customer
* **Request**: `{"quantity": 3}` (Must be `>= 1` and `<= stock`).

### 3.4 `DELETE /api/v1/cart/items/{item_id}` & `DELETE /api/v1/cart`
* **Access**: Authenticated Customer
* **Behavior**: Removes single item or empties entire cart.

---

## 4. Checkout & Stripe Sessions

### 4.1 `POST /api/v1/checkout/sessions`
* **Access**: Authenticated Customer
* **Headers**: Optional `Idempotency-Key: <client_key>`
* **Status**: `201 Created`
* **Response**:
```json
{
  "order_id": "f4a5b6c7-d8e9-4a0b-1c2d-3e4f5a6b7c8d",
  "order_number": "ORD-20261021-9876",
  "payment_id": "9a0b1c2d-3e4f-5a6b-7c8d-e9f0a1b2c3d4",
  "stripe_checkout_session_id": "cs_test_a1b2c3d4e5f6g7h8",
  "checkout_url": "https://checkout.stripe.com/c/pay/cs_test_a1b2c3d4e5f6g7h8",
  "expires_at": "2026-10-21T20:30:00Z"
}
```

---

## 5. Orders & Payments

### 5.1 `GET /api/v1/orders`
* **Access**: Authenticated Customer
* **Query Parameters**: `page`, `page_size`, `status`
* **Response**: Paginated list of customer orders.

### 5.2 `GET /api/v1/orders/{order_id}`
* **Access**: Authenticated Customer (IDOR protected: must own the order) or Admin.
* **Response**: Complete order with item snapshots, line totals, and payment status.

### 5.3 `POST /api/v1/orders/{order_id}/cancel`
* **Access**: Authenticated Customer
* **Rules**: Only allowed if `status == 'pending_payment'`. Releases reserved inventory immediately.

### 5.4 `GET /api/v1/payments/{payment_id}`
* **Access**: Authenticated Customer (owns order) or Admin.
* **Response**: Authoritative payment provider status.

---

## 6. Stripe Webhook

### 6.1 `POST /api/v1/webhooks/stripe`
* **Access**: Server-to-server (No user bearer auth required).
* **Headers**: `Stripe-Signature: t=...,v1=...`
* **Body**: Raw HTTP byte stream.
* **Status**: `200 OK` on verified event; `400 Bad Request` on invalid signature; `500 Internal Server Error` on unhandled processing glitch to trigger Stripe's automatic retry backoff.

---

## 7. Administrative Operations (`require_admin`)

* `POST /api/v1/admin/categories`
* `PATCH /api/v1/admin/categories/{category_id}`
* `POST /api/v1/admin/products`
* `PATCH /api/v1/admin/products/{product_id}`
* `PATCH /api/v1/admin/products/{product_id}/stock` (`{"stock": 100}`)
* `GET /api/v1/admin/orders` (all customer orders with filters)
* `PATCH /api/v1/admin/orders/{order_id}/status` (`{"status": "shipped"}`)
* `POST /api/v1/admin/orders/reconcile-expired` (triggers sweep of abandoned reservations)
