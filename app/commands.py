from __future__ import annotations

import asyncio
from typing import Any

import discord
from discord import app_commands

from app.analytics import (
    aggregate_discord_presence,
    aggregate_discord_presence_leaderboard,
    aggregate_leaderboard,
    aggregate_user_stats,
    latest_rank,
    load_matches,
)
from app.config import Settings
from app.db import Database
from app.formatters import format_duration, ts_to_utc_date
from app.riot_client import RiotClient


def _ids(interaction: discord.Interaction) -> tuple[str, str]:
    guild_id = str(interaction.guild_id or 0)
    return str(interaction.user.id), guild_id


def _display_name(user: discord.abc.User) -> str:
    return getattr(user, "display_name", None) or user.name


def _target_user(interaction: discord.Interaction, user: discord.User | None) -> discord.abc.User:
    return user or interaction.user


async def _ensure_user(db: Database, interaction: discord.Interaction) -> None:
    discord_user_id, guild_id = _ids(interaction)
    await db.upsert_user(discord_user_id, guild_id, _display_name(interaction.user), opted_in=False)


def setup_commands(
    tree: app_commands.CommandTree,
    db: Database,
    riot_client: RiotClient,
    settings: Settings,
) -> None:
    @tree.command(name="optin", description="Opt in to DegenerateTracker analytics")
    async def optin(interaction: discord.Interaction) -> None:
        discord_user_id, guild_id = _ids(interaction)
        await db.upsert_user(discord_user_id, guild_id, _display_name(interaction.user), opted_in=True)
        await interaction.response.send_message("You are opted in. Link your Riot account with `/lol_link`.", ephemeral=True)

    @tree.command(name="optout", description="Stop future tracking without deleting existing data")
    async def optout(interaction: discord.Interaction) -> None:
        await _ensure_user(db, interaction)
        discord_user_id, _ = _ids(interaction)
        await db.set_opted_in(discord_user_id, False)
        await interaction.response.send_message("You are opted out. Existing data remains until `/delete_my_data`.", ephemeral=True)

    @tree.command(name="delete_my_data", description="Delete your DegenerateTracker data")
    async def delete_my_data(interaction: discord.Interaction) -> None:
        discord_user_id, _ = _ids(interaction)
        await db.delete_user_data(discord_user_id)
        await interaction.response.send_message("Your stored analytics data has been deleted.", ephemeral=True)

    @tree.command(name="lol_link", description="Link your Riot ID")
    @app_commands.describe(game_name="Riot ID game name", tag_line="Riot ID tag line without #")
    async def lol_link(interaction: discord.Interaction, game_name: str, tag_line: str) -> None:
        await interaction.response.defer(ephemeral=True)
        discord_user_id, guild_id = _ids(interaction)
        await db.upsert_user(discord_user_id, guild_id, _display_name(interaction.user), opted_in=True)
        account = await riot_client.resolve_riot_id(game_name, tag_line, settings.riot_region_cluster)
        if not account or not account.get("puuid"):
            await interaction.followup.send("I could not resolve that Riot ID. Check the spelling and tag line.", ephemeral=True)
            return
        await db.link_riot_account(
            discord_user_id,
            account.get("gameName") or game_name,
            account.get("tagLine") or tag_line,
            account["puuid"],
            settings.riot_platform_routing,
            settings.riot_region_cluster,
        )
        await interaction.followup.send(f"Linked `{game_name}#{tag_line}`. Polling will pick it up shortly.", ephemeral=True)

    @tree.command(name="lol_unlink", description="Unlink your Riot account")
    async def lol_unlink(interaction: discord.Interaction) -> None:
        discord_user_id, _ = _ids(interaction)
        await db.unlink_riot_account(discord_user_id)
        await interaction.response.send_message("Your Riot account link was removed.", ephemeral=True)

    @tree.command(name="lol_today", description="Show today's League stats")
    async def lol_today(interaction: discord.Interaction, user: discord.User | None = None) -> None:
        await _stats_response(interaction, _target_user(interaction, user), "today", db)

    @tree.command(name="lol_week", description="Show this week's League stats")
    async def lol_week(interaction: discord.Interaction, user: discord.User | None = None) -> None:
        await _stats_response(interaction, _target_user(interaction, user), "7 days", db)

    @tree.command(name="lol_recent", description="Show recent League matches")
    @app_commands.describe(count="Number of matches to show")
    async def lol_recent(interaction: discord.Interaction, user: discord.User | None = None, count: int = 5) -> None:
        await interaction.response.defer(ephemeral=False)
        target = _target_user(interaction, user)
        count = max(1, min(count, 10))
        df = await asyncio.to_thread(load_matches, str(target.id), "all", None, db.path)
        if df.empty:
            await interaction.followup.send(f"No matches stored for {_display_name(target)} yet.")
            return
        lines = []
        for row in df.head(count).itertuples():
            result = "W" if row.win else "L"
            kda = f"{int(row.kills or 0)}/{int(row.deaths or 0)}/{int(row.assists or 0)}"
            lines.append(
                f"{ts_to_utc_date(getattr(row, 'game_end_timestamp', None))} | {result} | "
                f"{row.champion_name or 'Unknown'} | {row.queue_name or 'Unknown'} | {kda}"
            )
        await interaction.followup.send("```text\n" + "\n".join(lines) + "\n```")

    @tree.command(name="lol_rank", description="Show latest stored rank")
    async def lol_rank(interaction: discord.Interaction, user: discord.User | None = None) -> None:
        target = _target_user(interaction, user)
        rank = await asyncio.to_thread(latest_rank, str(target.id), db.path)
        await interaction.response.send_message(f"{_display_name(target)}: {rank}")

    @tree.command(name="lol_dashboard", description="Get a dashboard link")
    async def lol_dashboard(interaction: discord.Interaction, user: discord.User | None = None) -> None:
        target = _target_user(interaction, user)
        url = f"{settings.dashboard_base_url}/player/{target.id}"
        await interaction.response.send_message(f"Dashboard: {url}", ephemeral=True)

    @tree.command(name="lol_compare", description="Compare two players")
    async def lol_compare(
        interaction: discord.Interaction, user_a: discord.User, user_b: discord.User, period: str = "7 days"
    ) -> None:
        await interaction.response.defer()
        stats_a, stats_b = await asyncio.gather(
            asyncio.to_thread(aggregate_user_stats, str(user_a.id), period, None, db.path),
            asyncio.to_thread(aggregate_user_stats, str(user_b.id), period, None, db.path),
        )
        await interaction.followup.send(
            f"**{_display_name(user_a)}**: {stats_a['games']} games, {stats_a['winrate']}% WR, "
            f"{stats_a['avg_kda']} KDA, {stats_a['lp_delta_text']}\n"
            f"**{_display_name(user_b)}**: {stats_b['games']} games, {stats_b['winrate']}% WR, "
            f"{stats_b['avg_kda']} KDA, {stats_b['lp_delta_text']}"
        )

    @tree.command(name="leaderboard", description="Show server leaderboard")
    async def leaderboard(interaction: discord.Interaction, period: str = "today", metric: str = "games") -> None:
        await interaction.response.defer()
        board = await asyncio.to_thread(aggregate_leaderboard, period, metric, db.path)
        if board.empty:
            await interaction.followup.send("No stored matches for that period yet.")
            return
        lines = []
        for index, row in enumerate(board.head(10).itertuples(), start=1):
            name = row.display_name or row.discord_user_id
            lines.append(
                f"{index}. {name}: {row.games} games, {row.wins}-{row.losses}, "
                f"{row.winrate}% WR, {int(row.lp_delta):+d} LP"
            )
        await interaction.followup.send("```text\n" + "\n".join(lines) + "\n```")

    @tree.command(name="roast", description="Generate a gentle stats roast")
    async def roast(interaction: discord.Interaction, user: discord.User | None = None) -> None:
        target = _target_user(interaction, user)
        stats = await asyncio.to_thread(aggregate_user_stats, str(target.id), "7 days", None, db.path)
        if stats["games"] == 0:
            message = f"{_display_name(target)} has no tracked games yet. Suspiciously clean record."
        elif stats["avg_deaths"] >= 8:
            message = f"{_display_name(target)} is averaging {stats['avg_deaths']} deaths. The gray screen has a tenant."
        elif stats["winrate"] < 45:
            message = f"{_display_name(target)} has a {stats['winrate']}% winrate this week. Brave queueing, questionable outcomes."
        else:
            message = f"{_display_name(target)} is doing fine. Disappointing for roast material, honestly."
        await interaction.response.send_message(message)

    @tree.command(name="status", description="Show DegenerateTracker status")
    async def status(interaction: discord.Interaction) -> None:
        linked = await db.list_linked_accounts()
        await interaction.response.send_message(
            f"Tracking {len(linked)} linked opted-in account(s). "
            f"Poll interval: {settings.poll_interval_seconds}s. Dashboard: {settings.dashboard_base_url}",
            ephemeral=True,
        )

    @tree.command(name="discord_time", description="Show tracked Discord online and voice time")
    async def discord_time(
        interaction: discord.Interaction,
        user: discord.User | None = None,
        period: str = "today",
    ) -> None:
        target = _target_user(interaction, user)
        stats = await asyncio.to_thread(aggregate_discord_presence, str(target.id), period, db.path)
        await interaction.response.send_message(
            f"**{_display_name(target)}** Discord time ({period})\n"
            f"Online: {format_duration(stats['online_seconds'])}\n"
            f"Voice: {format_duration(stats['voice_seconds'])}\n"
            f"LoL activity visible on Discord: {format_duration(stats['league_presence_seconds'])}\n"
            f"Open sessions: {stats['open_sessions']}"
        )

    @tree.command(name="discord_leaderboard", description="Show Discord presence leaderboard")
    async def discord_leaderboard(
        interaction: discord.Interaction,
        period: str = "today",
        metric: str = "voice_seconds",
    ) -> None:
        await interaction.response.defer()
        board = await asyncio.to_thread(aggregate_discord_presence_leaderboard, period, metric, db.path)
        if board.empty:
            await interaction.followup.send("No tracked Discord presence sessions for that period yet.")
            return
        lines = []
        for index, row in enumerate(board.head(10).itertuples(), start=1):
            name = row.display_name or row.discord_user_id
            lines.append(
                f"{index}. {name}: online {format_duration(row.online_seconds)}, "
                f"voice {format_duration(row.voice_seconds)}, LoL visible {format_duration(row.league_presence_seconds)}"
            )
        await interaction.followup.send("```text\n" + "\n".join(lines) + "\n```")


async def _stats_response(
    interaction: discord.Interaction,
    user: discord.abc.User,
    period: str,
    db: Database,
) -> None:
    await interaction.response.defer()
    stats = await asyncio.to_thread(aggregate_user_stats, str(user.id), period, None, db.path)
    await interaction.followup.send(
        f"**{_display_name(user)}** ({period})\n"
        f"Games: {stats['games']} | W-L: {stats['wins']}-{stats['losses']} | WR: {stats['winrate']}%\n"
        f"Avg KDA: {stats['avg_kda']} | Avg deaths: {stats['avg_deaths']} | LP: {stats['lp_delta_text']}\n"
        f"Time played: {format_duration(stats['total_duration_seconds'])}"
    )
