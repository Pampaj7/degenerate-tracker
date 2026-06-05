from __future__ import annotations

import logging

import discord
from discord.ext import commands

from app.commands import setup_commands
from app.config import Settings
from app.db import Database
from app.poller import RiotPoller
from app.presence_tracker import PresenceTracker
from app.riot_client import RiotClient

logger = logging.getLogger(__name__)


class DegenerateTrackerBot(commands.Bot):
    def __init__(self, db: Database, riot_client: RiotClient, settings: Settings):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.presences = True
        super().__init__(command_prefix="!", intents=intents)
        self.db = db
        self.riot_client = riot_client
        self.settings = settings
        self.presence_tracker = PresenceTracker(db)
        self.poller = RiotPoller(db, riot_client, settings)
        self._poller_task = None

    async def setup_hook(self) -> None:
        setup_commands(self.tree, self.db, self.riot_client, self.settings)
        await self.presence_tracker.close_stale_sessions()
        if self.settings.guild_id:
            guild = discord.Object(id=self.settings.guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info("Synced slash commands to guild %s", self.settings.guild_id)
        else:
            await self.tree.sync()
            logger.info("Synced global slash commands")
        self._poller_task = self.loop.create_task(self.poller.run_forever())

    async def on_ready(self) -> None:
        logger.info("Logged in as %s", self.user)

    async def on_presence_update(self, before: discord.Member, after: discord.Member) -> None:
        await self.presence_tracker.handle_presence_update(before, after)

    async def close(self) -> None:
        self.poller.stop()
        if self._poller_task:
            await self._poller_task
        await self.riot_client.close()
        await super().close()

