from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from app.analytics import recompute_daily_summary
from app.config import Settings
from app.db import Database
from app.riot_client import RiotClient
from app.riot_parser import parse_match

logger = logging.getLogger(__name__)


class RiotPoller:
    def __init__(self, db: Database, riot_client: RiotClient, settings: Settings):
        self.db = db
        self.riot_client = riot_client
        self.settings = settings
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
        logger.info("Riot poller started with interval %ss", self.settings.poll_interval_seconds)
        while not self._stop.is_set():
            try:
                await self.poll_once()
            except Exception:
                logger.exception("Riot poll cycle failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.settings.poll_interval_seconds)
            except asyncio.TimeoutError:
                pass

    async def poll_once(self) -> None:
        accounts = await self.db.list_linked_accounts()
        if not accounts:
            logger.info("Poll skipped; no linked opted-in accounts")
            return

        logger.info("Polling Riot API for %s linked account(s)", len(accounts))
        for account in accounts:
            match_ids = await self.riot_client.get_recent_match_ids(
                account.puuid, account.region_cluster, count=20
            )
            inserted_count = 0
            for match_id in match_ids:
                if await self.db.match_exists(match_id):
                    continue
                match_payload = await self.riot_client.get_match(match_id, account.region_cluster)
                if not match_payload:
                    continue
                record = parse_match(match_id, match_payload, account.puuid, account.discord_user_id)
                if record is None:
                    logger.warning("Match %s did not include expected participant", match_id)
                    continue
                if await self.db.insert_match(record):
                    inserted_count += 1

            ranked_entries = await self.riot_client.get_ranked_entries_by_puuid(
                account.puuid, account.platform_routing
            )
            for entry in ranked_entries:
                await self.db.insert_ranked_snapshot(account.discord_user_id, account.puuid, entry)

            today = datetime.now(UTC).date().isoformat()
            await asyncio.to_thread(recompute_daily_summary, account.discord_user_id, today, self.db.path)
            logger.info(
                "Polled %s#%s: %s new match(es), %s ranked snapshot(s)",
                account.game_name,
                account.tag_line,
                inserted_count,
                len(ranked_entries),
            )

