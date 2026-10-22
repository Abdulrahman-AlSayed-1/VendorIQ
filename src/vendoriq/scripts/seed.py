import asyncio
import logging
from decimal import Decimal

from sqlalchemy import select

from vendoriq.core.db import async_session_maker, engine
from vendoriq.core.security import hash_password
from vendoriq.models.category import Category
from vendoriq.models.product import Product
from vendoriq.models.user import User, UserRole

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vendoriq.seed")


async def seed_database() -> None:
    logger.info("Starting idempotent database seed...")

    async with async_session_maker() as session:
        # 1. Seed Default Admin User
        admin_email = "admin@vendoriq.local"
        existing_admin = (
            await session.execute(select(User).where(User.email == admin_email))
        ).scalar_one_or_none()

        if not existing_admin:
            admin_user = User(
                name="System Administrator",
                email=admin_email,
                password_hash=hash_password("AdminSecure123!"),
                role=UserRole.ADMIN,
                is_active=True,
            )
            session.add(admin_user)
            logger.info("Created default admin user: %s", admin_email)
        else:
            logger.info("Admin user %s already exists, skipping.", admin_email)

        # 2. Seed Default Customer User
        customer_email = "customer@vendoriq.local"
        existing_cust = (
            await session.execute(select(User).where(User.email == customer_email))
        ).scalar_one_or_none()

        if not existing_cust:
            cust_user = User(
                name="Demo Customer",
                email=customer_email,
                password_hash=hash_password("CustomerPass123!"),
                role=UserRole.CUSTOMER,
                is_active=True,
            )
            session.add(cust_user)
            logger.info("Created default customer user: %s", customer_email)
        else:
            logger.info("Customer user %s already exists, skipping.", customer_email)

        # 3. Seed Sample Categories
        categories_data = [
            {
                "name": "Audio",
                "slug": "audio",
                "description": "High-fidelity headphones, speakers, and sound gear.",
            },
            {
                "name": "Computing",
                "slug": "computing",
                "description": "Keyboards, mice, monitors, and workstation peripherals.",
            },
            {
                "name": "Accessories",
                "slug": "accessories",
                "description": "Cables, charging adapters, stands, and cases.",
            },
        ]

        cats_by_slug: dict[str, Category] = {}
        for cat_info in categories_data:
            existing_cat = (
                await session.execute(
                    select(Category).where(Category.slug == cat_info["slug"])
                )
            ).scalar_one_or_none()

            if not existing_cat:
                cat = Category(
                    name=cat_info["name"],
                    slug=cat_info["slug"],
                    description=cat_info["description"],
                    is_active=True,
                )
                session.add(cat)
                cats_by_slug[cat_info["slug"]] = cat
                logger.info("Created category: %s", cat_info["name"])
            else:
                cats_by_slug[cat_info["slug"]] = existing_cat

        await session.flush()

        # 4. Seed Sample Products
        products_data = [
            {
                "category_slug": "audio",
                "name": "VendorIQ Wireless ANC Headphones",
                "slug": "vendoriq-wireless-anc-headphones",
                "sku": "AUD-ANC-001",
                "description": "Flagship wireless over-ear headphones with active noise cancellation and 40h battery.",
                "brand": "VendorIQ Audio",
                "price": Decimal("249.99"),
                "stock": 50,
                "attributes": {
                    "color": "Space Gray",
                    "battery_hours": 40,
                    "bluetooth": "5.3",
                },
                "image_urls": [
                    "https://images.unsplash.com/photo-1505740420928-5e560c06d30e"
                ],
            },
            {
                "category_slug": "audio",
                "name": "Pulse Waterproof Portable Speaker",
                "slug": "pulse-waterproof-portable-speaker",
                "sku": "AUD-SPK-002",
                "description": "Compact IP67 waterproof outdoor speaker with deep bass.",
                "brand": "Pulse",
                "price": Decimal("79.99"),
                "stock": 35,
                "attributes": {"waterproof_rating": "IP67", "battery_hours": 16},
                "image_urls": [
                    "https://images.unsplash.com/photo-1608043152269-423dbba4e7e1"
                ],
            },
            {
                "category_slug": "computing",
                "name": "Apex Custom Mechanical Keyboard",
                "slug": "apex-custom-mechanical-keyboard",
                "sku": "CMP-KEY-001",
                "description": "Hot-swappable 75% mechanical keyboard with factory-lubed switches and RGB backlight.",
                "brand": "ApexTech",
                "price": Decimal("139.00"),
                "stock": 25,
                "attributes": {
                    "switches": "Linear Red",
                    "layout": "75%",
                    "hot_swappable": True,
                },
                "image_urls": [
                    "https://images.unsplash.com/photo-1595225476474-87563907a212"
                ],
            },
            {
                "category_slug": "computing",
                "name": "Precision Ergonomic Vertical Mouse",
                "slug": "precision-ergonomic-vertical-mouse",
                "sku": "CMP-MOU-002",
                "description": "Ergonomically sculpted wireless vertical mouse promoting natural hand posture.",
                "brand": "ErgoPro",
                "price": Decimal("59.50"),
                "stock": 40,
                "attributes": {
                    "sensor": "Optical 4000 DPI",
                    "connectivity": "2.4GHz + BT",
                },
                "image_urls": [
                    "https://images.unsplash.com/photo-1615663245857-ac93bb7c39e7"
                ],
            },
            {
                "category_slug": "accessories",
                "name": "Braided 100W USB-C Fast Charging Cable (2m)",
                "slug": "braided-100w-usbc-cable-2m",
                "sku": "ACC-CAB-001",
                "description": "Ultra-durable Kevlar-reinforced 100W USB-C to USB-C charging and data cable.",
                "brand": "VendorIQ Gear",
                "price": Decimal("19.99"),
                "stock": 100,
                "attributes": {
                    "wattage": "100W",
                    "length": "2m",
                    "material": "Braided Nylon",
                },
                "image_urls": [
                    "https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c"
                ],
            },
        ]

        for prod_info in products_data:
            existing_prod = (
                await session.execute(
                    select(Product).where(Product.sku == prod_info["sku"])
                )
            ).scalar_one_or_none()

            if not existing_prod:
                category = cats_by_slug.get(prod_info["category_slug"])
                prod = Product(
                    category_id=category.id if category else None,
                    name=prod_info["name"],
                    slug=prod_info["slug"],
                    sku=prod_info["sku"],
                    description=prod_info["description"],
                    brand=prod_info["brand"],
                    price=prod_info["price"],
                    currency="usd",
                    stock=prod_info["stock"],
                    attributes=prod_info["attributes"],
                    image_urls=prod_info["image_urls"],
                    is_active=True,
                )
                session.add(prod)
                logger.info(
                    "Created product: %s (%s)", prod_info["name"], prod_info["sku"]
                )
            else:
                logger.info("Product %s already exists, skipping.", prod_info["sku"])

        await session.commit()
        logger.info("Database seed completed successfully.")

    await engine.dispose()


def main() -> None:
    asyncio.run(seed_database())


if __name__ == "__main__":
    main()
