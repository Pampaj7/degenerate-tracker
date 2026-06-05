from __future__ import annotations

import asyncio
import logging
import signal
from contextlib import suppress

from app.config import load_settings
from app.dashboard import start_dashboard_in_thread
from app.db import Database
from app.discord_bot import DegenerateTrackerBot
from app.riot_client import RiotClient


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


async def main() -> None:
    configure_logging()
    settings = load_settings()
    if not settings.discord_token:
        raise RuntimeError("DISCORD_TOKEN is required")
    if not settings.riot_api_key:
        raise RuntimeError("RIOT_API_KEY is required")

    db = Database(settings.database_path)
    await db.initialize()
    start_dashboard_in_thread(settings)

    riot_client = RiotClient(
        settings.riot_api_key,
        settings.riot_region_cluster,
        settings.riot_platform_routing,
    )
    bot = DegenerateTrackerBot(db, riot_client, settings)

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    bot_task = asyncio.create_task(bot.start(settings.discord_token))
    stop_task = asyncio.create_task(stop_event.wait())
    done, pending = await asyncio.wait({bot_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)

    if stop_task in done and not bot_task.done():
        await bot.close()

    for task in pending:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    if bot_task in done:
        bot_task.result()


if __name__ == "__main__":
    asyncio.run(main())
