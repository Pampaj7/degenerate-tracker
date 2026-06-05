import sqlite3
from pathlib import Path

from app.analytics import (
    aggregate_discord_presence,
    aggregate_discord_presence_leaderboard,
    aggregate_leaderboard,
    aggregate_user_stats,
    estimate_lp_delta,
)
from app.db import SCHEMA


def _create_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            """
            INSERT INTO users(discord_user_id, guild_id, display_name, opted_in, created_at, updated_at)
            VALUES ('1', '10', 'Alpha', 1, 1, 1), ('2', '10', 'Beta', 1, 1, 1)
            """
        )
        conn.execute(
            """
            INSERT INTO riot_accounts(discord_user_id, game_name, tag_line, puuid, platform_routing, region_cluster, created_at, updated_at)
            VALUES ('1', 'AlphaLol', 'EUW', 'p1', 'euw1', 'europe', 1, 1)
            """
        )
        matches = [
            ("EUW1_1", "p1", "1", 2_000_000_000, "Ranked Solo", "Ahri", "MIDDLE", 1, 8, 2, 10, 1800),
            ("EUW1_2", "p1", "1", 2_000_000_100, "Ranked Solo", "Ahri", "MIDDLE", 0, 2, 7, 4, 2000),
        ]
        for row in matches:
            conn.execute(
                """
                INSERT INTO matches(
                    match_id, puuid, discord_user_id, game_end_timestamp, queue_name, champion_name,
                    team_position, win, kills, deaths, assists, game_duration_seconds, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                row,
            )
        conn.execute(
            """
            INSERT INTO ranked_snapshots(discord_user_id, puuid, queue_type, tier, rank, league_points, wins, losses, snapshot_ts)
            VALUES
              ('1', 'p1', 'RANKED_SOLO_5x5', 'GOLD', 'IV', 20, 10, 10, 2_000_000_000),
              ('1', 'p1', 'RANKED_SOLO_5x5', 'GOLD', 'III', 45, 12, 11, 2_000_000_200)
            """
        )
        conn.commit()


def test_aggregate_user_stats(tmp_path):
    db_path = tmp_path / "test.sqlite"
    _create_db(db_path)

    stats = aggregate_user_stats("1", "all", db_path=db_path)

    assert stats["games"] == 2
    assert stats["wins"] == 1
    assert stats["losses"] == 1
    assert stats["winrate"] == 50.0
    assert stats["avg_kda"] == 2.67
    assert stats["total_duration_seconds"] == 3800


def test_leaderboard_and_lp_delta(tmp_path):
    db_path = tmp_path / "test.sqlite"
    _create_db(db_path)

    board = aggregate_leaderboard("all", "games", db_path)
    lp = estimate_lp_delta("1", "all", db_path=db_path)

    assert board.iloc[0]["discord_user_id"] == "1"
    assert lp["delta"] == 125
    assert "Gold IV 20 LP -> Gold III 45 LP" in lp["text"]


def test_discord_presence_aggregation(tmp_path):
    db_path = tmp_path / "test.sqlite"
    _create_db(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO presence_sessions(
                discord_user_id, guild_id, activity_type, activity_name,
                start_ts, end_ts, duration_seconds, closed_reason
            )
            VALUES
              ('1', '10', 'discord_online', 'Online', 1_700_000_000, 1_700_003_600, 3600, 'offline'),
              ('1', '10', 'discord_voice', 'General', 1_700_000_600, 1_700_001_500, 900, 'voice_left'),
              ('1', '10', 'league_of_legends', 'League of Legends', 1_700_000_100, 1_700_001_900, 1800, 'activity_ended'),
              ('2', '10', 'discord_voice', 'General', 1_700_000_000, 1_700_000_300, 300, 'voice_left')
            """
        )
        conn.commit()

    stats = aggregate_discord_presence("1", "all", db_path)
    board = aggregate_discord_presence_leaderboard("all", "voice_seconds", db_path)

    assert stats["online_seconds"] == 3600
    assert stats["voice_seconds"] == 900
    assert stats["league_presence_seconds"] == 1800
    assert board.iloc[0]["discord_user_id"] == "1"
