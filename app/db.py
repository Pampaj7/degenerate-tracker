from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import aiosqlite

from app.formatters import utc_now_ts
from app.models import LinkedAccount, MatchRecord

logger = logging.getLogger(__name__)


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users (
    discord_user_id TEXT PRIMARY KEY,
    guild_id TEXT NOT NULL,
    display_name TEXT,
    opted_in INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS riot_accounts (
    discord_user_id TEXT PRIMARY KEY,
    game_name TEXT NOT NULL,
    tag_line TEXT NOT NULL,
    puuid TEXT NOT NULL,
    platform_routing TEXT NOT NULL,
    region_cluster TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    FOREIGN KEY (discord_user_id) REFERENCES users(discord_user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS matches (
    match_id TEXT PRIMARY KEY,
    puuid TEXT NOT NULL,
    discord_user_id TEXT NOT NULL,
    game_creation INTEGER,
    game_start_timestamp INTEGER,
    game_end_timestamp INTEGER,
    game_duration_seconds INTEGER,
    queue_id INTEGER,
    queue_name TEXT,
    champion_name TEXT,
    team_position TEXT,
    individual_position TEXT,
    win INTEGER NOT NULL,
    kills INTEGER,
    deaths INTEGER,
    assists INTEGER,
    total_damage_dealt_to_champions INTEGER,
    gold_earned INTEGER,
    total_minions_killed INTEGER,
    neutral_minions_killed INTEGER,
    cs INTEGER,
    vision_score INTEGER,
    summoner_level INTEGER,
    item0 INTEGER,
    item1 INTEGER,
    item2 INTEGER,
    item3 INTEGER,
    item4 INTEGER,
    item5 INTEGER,
    item6 INTEGER,
    raw_json TEXT,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS ranked_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discord_user_id TEXT NOT NULL,
    puuid TEXT NOT NULL,
    queue_type TEXT NOT NULL,
    tier TEXT,
    rank TEXT,
    league_points INTEGER,
    wins INTEGER,
    losses INTEGER,
    snapshot_ts INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS presence_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discord_user_id TEXT NOT NULL,
    guild_id TEXT NOT NULL,
    activity_type TEXT NOT NULL,
    activity_name TEXT NOT NULL,
    start_ts INTEGER NOT NULL,
    end_ts INTEGER,
    duration_seconds INTEGER,
    closed_reason TEXT
);

CREATE TABLE IF NOT EXISTS daily_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discord_user_id TEXT NOT NULL,
    date_utc TEXT NOT NULL,
    games INTEGER,
    wins INTEGER,
    losses INTEGER,
    ranked_games INTEGER,
    ranked_wins INTEGER,
    ranked_losses INTEGER,
    total_duration_seconds INTEGER,
    avg_kills REAL,
    avg_deaths REAL,
    avg_assists REAL,
    avg_kda REAL,
    lp_delta INTEGER,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    UNIQUE(discord_user_id, date_utc)
);

CREATE INDEX IF NOT EXISTS idx_matches_user_time ON matches(discord_user_id, game_end_timestamp);
CREATE INDEX IF NOT EXISTS idx_matches_puuid ON matches(puuid);
CREATE INDEX IF NOT EXISTS idx_ranked_user_time ON ranked_snapshots(discord_user_id, snapshot_ts);
CREATE INDEX IF NOT EXISTS idx_presence_user_time ON presence_sessions(discord_user_id, start_ts);
CREATE INDEX IF NOT EXISTS idx_daily_date ON daily_summaries(date_utc);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(SCHEMA)
            await db.commit()
        logger.info("Database initialized at %s", self.path)

    async def execute(self, sql: str, parameters: tuple[Any, ...] = ()) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("PRAGMA foreign_keys=ON")
            await db.execute(sql, parameters)
            await db.commit()

    async def fetchone(self, sql: str, parameters: tuple[Any, ...] = ()) -> aiosqlite.Row | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(sql, parameters)
            row = await cursor.fetchone()
            await cursor.close()
            return row

    async def fetchall(self, sql: str, parameters: tuple[Any, ...] = ()) -> list[aiosqlite.Row]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(sql, parameters)
            rows = await cursor.fetchall()
            await cursor.close()
            return rows

    async def upsert_user(self, discord_user_id: str, guild_id: str, display_name: str | None, opted_in: bool) -> None:
        now = utc_now_ts()
        await self.execute(
            """
            INSERT INTO users(discord_user_id, guild_id, display_name, opted_in, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(discord_user_id) DO UPDATE SET
                guild_id=excluded.guild_id,
                display_name=excluded.display_name,
                opted_in=excluded.opted_in,
                updated_at=excluded.updated_at
            """,
            (discord_user_id, guild_id, display_name, int(opted_in), now, now),
        )

    async def set_opted_in(self, discord_user_id: str, opted_in: bool) -> None:
        await self.execute(
            "UPDATE users SET opted_in=?, updated_at=? WHERE discord_user_id=?",
            (int(opted_in), utc_now_ts(), discord_user_id),
        )

    async def is_opted_in(self, discord_user_id: str) -> bool:
        row = await self.fetchone("SELECT opted_in FROM users WHERE discord_user_id=?", (discord_user_id,))
        return bool(row and row["opted_in"])

    async def delete_user_data(self, discord_user_id: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("PRAGMA foreign_keys=ON")
            for table in ("matches", "ranked_snapshots", "presence_sessions", "daily_summaries", "riot_accounts"):
                await db.execute(f"DELETE FROM {table} WHERE discord_user_id=?", (discord_user_id,))
            await db.execute("DELETE FROM users WHERE discord_user_id=?", (discord_user_id,))
            await db.commit()

    async def link_riot_account(
        self,
        discord_user_id: str,
        game_name: str,
        tag_line: str,
        puuid: str,
        platform_routing: str,
        region_cluster: str,
    ) -> None:
        now = utc_now_ts()
        await self.execute(
            """
            INSERT INTO riot_accounts(
                discord_user_id, game_name, tag_line, puuid,
                platform_routing, region_cluster, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(discord_user_id) DO UPDATE SET
                game_name=excluded.game_name,
                tag_line=excluded.tag_line,
                puuid=excluded.puuid,
                platform_routing=excluded.platform_routing,
                region_cluster=excluded.region_cluster,
                updated_at=excluded.updated_at
            """,
            (discord_user_id, game_name, tag_line, puuid, platform_routing, region_cluster, now, now),
        )

    async def unlink_riot_account(self, discord_user_id: str) -> None:
        await self.execute("DELETE FROM riot_accounts WHERE discord_user_id=?", (discord_user_id,))

    async def get_linked_account(self, discord_user_id: str) -> aiosqlite.Row | None:
        return await self.fetchone(
            """
            SELECT u.guild_id, u.display_name, r.*
            FROM riot_accounts r
            JOIN users u ON u.discord_user_id = r.discord_user_id
            WHERE r.discord_user_id=? AND u.opted_in=1
            """,
            (discord_user_id,),
        )

    async def list_linked_accounts(self) -> list[LinkedAccount]:
        rows = await self.fetchall(
            """
            SELECT u.guild_id, u.display_name, r.*
            FROM riot_accounts r
            JOIN users u ON u.discord_user_id = r.discord_user_id
            WHERE u.opted_in=1
            ORDER BY r.updated_at DESC
            """
        )
        return [
            LinkedAccount(
                discord_user_id=row["discord_user_id"],
                guild_id=row["guild_id"],
                display_name=row["display_name"],
                game_name=row["game_name"],
                tag_line=row["tag_line"],
                puuid=row["puuid"],
                platform_routing=row["platform_routing"],
                region_cluster=row["region_cluster"],
            )
            for row in rows
        ]

    async def match_exists(self, match_id: str) -> bool:
        row = await self.fetchone("SELECT 1 FROM matches WHERE match_id=?", (match_id,))
        return row is not None

    async def insert_match(self, record: MatchRecord) -> bool:
        columns = tuple(record.__dataclass_fields__.keys())
        placeholders = ", ".join("?" for _ in columns)
        sql = f"INSERT OR IGNORE INTO matches({', '.join(columns)}) VALUES ({placeholders})"
        values = tuple(getattr(record, column) for column in columns)
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(sql, values)
            await db.commit()
            inserted = cursor.rowcount > 0
            await cursor.close()
            return inserted

    async def insert_ranked_snapshot(self, discord_user_id: str, puuid: str, entry: dict[str, Any]) -> None:
        await self.execute(
            """
            INSERT INTO ranked_snapshots(
                discord_user_id, puuid, queue_type, tier, rank,
                league_points, wins, losses, snapshot_ts
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                discord_user_id,
                puuid,
                entry.get("queueType", "UNKNOWN"),
                entry.get("tier"),
                entry.get("rank"),
                entry.get("leaguePoints"),
                entry.get("wins"),
                entry.get("losses"),
                utc_now_ts(),
            ),
        )

    async def start_presence_session(
        self, discord_user_id: str, guild_id: str, activity_type: str, activity_name: str
    ) -> None:
        open_session = await self.fetchone(
            """
            SELECT id FROM presence_sessions
            WHERE discord_user_id=? AND guild_id=? AND activity_type=? AND activity_name=? AND end_ts IS NULL
            """,
            (discord_user_id, guild_id, activity_type, activity_name),
        )
        if open_session:
            return
        await self.execute(
            """
            INSERT INTO presence_sessions(discord_user_id, guild_id, activity_type, activity_name, start_ts)
            VALUES (?, ?, ?, ?, ?)
            """,
            (discord_user_id, guild_id, activity_type, activity_name, utc_now_ts()),
        )

    async def close_presence_session(
        self,
        discord_user_id: str,
        guild_id: str,
        reason: str,
        activity_type: str | None = None,
        activity_name: str | None = None,
    ) -> None:
        now = utc_now_ts()
        clauses = ["discord_user_id=?", "guild_id=?", "end_ts IS NULL"]
        params: list[Any] = [discord_user_id, guild_id]
        if activity_type is not None:
            clauses.append("activity_type=?")
            params.append(activity_type)
        if activity_name is not None:
            clauses.append("activity_name=?")
            params.append(activity_name)
        params = [now, now, reason, *params]
        await self.execute(
            f"""
            UPDATE presence_sessions
            SET end_ts=?, duration_seconds=? - start_ts, closed_reason=?
            WHERE {' AND '.join(clauses)}
            """,
            tuple(params),
        )

    async def close_stale_presence_sessions(self) -> None:
        now = utc_now_ts()
        await self.execute(
            """
            UPDATE presence_sessions
            SET end_ts=?, duration_seconds=? - start_ts, closed_reason='startup'
            WHERE end_ts IS NULL
            """,
            (now, now),
        )
