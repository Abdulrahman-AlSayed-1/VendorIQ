# VendorIQ Documentation Index

Welcome to the **VendorIQ** architecture and implementation specification documents:

1. **[Architecture Specification](file:///Users/al-sayed04/Desktop/VendorIQ/docs/architecture.md)**: System design, layer boundaries, modular monolith layout, security model, and transaction boundaries.
2. **[Database Schema Specification](file:///Users/al-sayed04/Desktop/VendorIQ/docs/database_schema.md)**: Complete database models, ER diagram, UUID keys, decimal precision, JSONB attributes, and indexes.
3. **[REST API Specification](file:///Users/al-sayed04/Desktop/VendorIQ/docs/api_specification.md)**: Endpoints for Auth, Catalog, Cart, Checkout, Orders, Payments, Webhooks, and Admin operations with request/response contracts.
4. **[Stripe Sandbox Integration](file:///Users/al-sayed04/Desktop/VendorIQ/docs/stripe_integration.md)**: Stripe test mode safety, Checkout Session creation, itemized line items, idempotency key strategy, and verified webhooks.
5. **[Inventory Policy & Order Lifecycle](file:///Users/al-sayed04/Desktop/VendorIQ/docs/inventory_and_orders.md)**: Short-lived reservation model, row-level locking (`SELECT ... FOR UPDATE`), legal state transitions, and historical snapshots.
6. **[Implementation Roadmap & DoD](file:///Users/al-sayed04/Desktop/VendorIQ/docs/implementation_roadmap.md)**: Phased milestones (Phases 1-4), testing strategy, and Definition of Done checklist.
