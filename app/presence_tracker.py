from __future__ import annotations

import logging

import discord

from app.db import Database

logger = logging.getLogger(__name__)


LEAGUE_ACTIVITY_NAMES = {"league of legends", "league client"}


def _league_activity(member: discord.Member) -> discord.Activity | discord.Game | None:
    for activity in member.activities:
        name = getattr(activity, "name", None)
        if name and name.lower() in LEAGUE_ACTIVITY_NAMES:
            return activity
    return None


class PresenceTracker:
    def __init__(self, db: Database):
        self.db = db

    async def close_stale_sessions(self) -> None:
        await self.db.close_stale_presence_sessions()

    async def handle_presence_update(self, before: discord.Member, after: discord.Member) -> None:
        if after.bot or not after.guild:
            return
        discord_user_id = str(after.id)
        guild_id = str(after.guild.id)
        if not await self.db.is_opted_in(discord_user_id):
            return

        before_activity = _league_activity(before)
        after_activity = _league_activity(after)
        if before_activity is None and after_activity is not None:
            activity_type = getattr(getattr(after_activity, "type", None), "name", "playing")
            await self.db.start_presence_session(discord_user_id, guild_id, activity_type, after_activity.name)
        elif before_activity is not None and after_activity is None:
            await self.db.close_presence_session(discord_user_id, guild_id, "activity_ended")
        elif after.status is discord.Status.offline:
            await self.db.close_presence_session(discord_user_id, guild_id, "offline")

