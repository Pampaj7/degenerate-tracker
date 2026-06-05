from __future__ import annotations

import logging

import discord

from app.db import Database

logger = logging.getLogger(__name__)


LEAGUE_ACTIVITY_NAMES = {"league of legends", "league client"}
DISCORD_ONLINE_TYPE = "discord_online"
DISCORD_VOICE_TYPE = "discord_voice"
DISCORD_GAME_TYPE = "discord_game"
ONLINE_ACTIVITY_NAME = "Online"


def _game_activity_names(member: discord.Member) -> set[str]:
    names: set[str] = set()
    for activity in member.activities:
        name = getattr(activity, "name", None)
        activity_type = getattr(activity, "type", None)
        if name and activity_type is discord.ActivityType.playing:
            names.add(name)
    return names


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

        if before.status is discord.Status.offline and after.status is not discord.Status.offline:
            await self.db.start_presence_session(discord_user_id, guild_id, DISCORD_ONLINE_TYPE, ONLINE_ACTIVITY_NAME)
        elif before.status is not discord.Status.offline and after.status is discord.Status.offline:
            await self.db.close_presence_session(
                discord_user_id,
                guild_id,
                "offline",
                activity_type=DISCORD_ONLINE_TYPE,
            )

        before_games = _game_activity_names(before)
        after_games = _game_activity_names(after)

        for game_name in sorted(before_games - after_games):
            await self.db.close_presence_session(
                discord_user_id,
                guild_id,
                "activity_ended",
                activity_type=DISCORD_GAME_TYPE,
                activity_name=game_name,
            )

        for game_name in sorted(after_games - before_games):
            await self.db.start_presence_session(discord_user_id, guild_id, DISCORD_GAME_TYPE, game_name)

        if after.status is discord.Status.offline:
            await self.db.close_presence_session(
                discord_user_id,
                guild_id,
                "offline",
                activity_type=DISCORD_GAME_TYPE,
            )

    async def handle_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.bot or not member.guild:
            return
        discord_user_id = str(member.id)
        guild_id = str(member.guild.id)
        if not await self.db.is_opted_in(discord_user_id):
            return

        before_channel = before.channel
        after_channel = after.channel
        if before_channel == after_channel:
            return

        if before_channel is not None:
            await self.db.close_presence_session(
                discord_user_id,
                guild_id,
                "voice_left",
                activity_type=DISCORD_VOICE_TYPE,
                activity_name=before_channel.name,
            )

        if after_channel is not None:
            await self.db.start_presence_session(
                discord_user_id,
                guild_id,
                DISCORD_VOICE_TYPE,
                after_channel.name,
            )
