"""CLI Maintenance Script: Reconcile Expired Reservations.

Finds all unpaid orders whose 30-minute reservation TTL has elapsed, atomically releases
the reserved stock back into inventory, and transitions orders to CANCELLED.
Can be executed as a periodic cron job or k8s CronJob:
    uv run python -m vendoriq.scripts.reconcile
"""

import asyncio
import logging
import sys

from vendoriq.core.db import async_session_maker
from vendoriq.services.inventory_service import inventory_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("vendoriq.reconcile")


async def main() -> None:
    logger.info("Starting expired order reservation reconciliation...")
    async with async_session_maker() as session:
        cancelled_ids = await inventory_service.reconcile_expired_reservations(session)
        if cancelled_ids:
            logger.info(
                "Successfully cancelled %d expired orders and released inventory: %s",
                len(cancelled_ids),
                [str(oid) for oid in cancelled_ids],
            )
        else:
            logger.info("No expired reservations found. Everything is in sync.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        logger.exception("Reconciliation failed with error.")
        sys.exit(1)
