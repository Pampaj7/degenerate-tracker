from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from app.config import DEFAULT_DB_PATH
from app.formatters import compute_kda, compute_winrate, get_period_start, rank_label, rank_points, utc_now_ts


RANKED_QUEUES = {"Ranked Solo", "Ranked Flex"}
QUEUE_FILTERS = {
    "ranked solo": "Ranked Solo",
    "ranked flex": "Ranked Flex",
    "aram": "ARAM",
    "normal": "Normal",
}
DISCORD_ONLINE_TYPE = "discord_online"
DISCORD_VOICE_TYPE = "discord_voice"
LEAGUE_ACTIVITY_TYPE = "league_of_legends"


def _connect(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _match_where(
    user_id: str | None,
    period: str,
    filters: dict[str, Any] | None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if user_id:
        clauses.append("m.discord_user_id = ?")
        params.append(user_id)
    start = get_period_start(period)
    if start is not None:
        clauses.append("COALESCE(m.game_end_timestamp, m.game_start_timestamp, m.game_creation, m.created_at) >= ?")
        params.append(start)
    filters = filters or {}
    queue = (filters.get("queue") or "all").lower()
    if queue != "all":
        queue_name = QUEUE_FILTERS.get(queue)
        if queue_name == "Normal":
            clauses.append("m.queue_name LIKE ?")
            params.append("Normal%")
        elif queue_name:
            clauses.append("m.queue_name = ?")
            params.append(queue_name)
    if filters.get("champion"):
        clauses.append("m.champion_name = ?")
        params.append(filters["champion"])
    if filters.get("role"):
        clauses.append("COALESCE(NULLIF(m.team_position, ''), m.individual_position) = ?")
        params.append(filters["role"])
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    return where, params


def load_matches(
    user_id: str | None = None,
    period: str = "7 days",
    filters: dict[str, Any] | None = None,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> pd.DataFrame:
    where, params = _match_where(user_id, period, filters)
    with _connect(db_path) as conn:
        return pd.read_sql_query(
            f"""
            SELECT m.*, u.display_name, r.game_name, r.tag_line
            FROM matches m
            LEFT JOIN users u ON u.discord_user_id = m.discord_user_id
            LEFT JOIN riot_accounts r ON r.discord_user_id = m.discord_user_id
            {where}
            ORDER BY COALESCE(m.game_end_timestamp, m.game_start_timestamp, m.game_creation, m.created_at) DESC
            """,
            conn,
            params=params,
        )


def aggregate_user_stats(
    user_id: str,
    period: str = "7 days",
    filters: dict[str, Any] | None = None,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    df = load_matches(user_id, period, filters, db_path)
    games = int(len(df))
    wins = int(df["win"].sum()) if games else 0
    losses = games - wins
    kills = float(df["kills"].fillna(0).mean()) if games else 0.0
    deaths = float(df["deaths"].fillna(0).mean()) if games else 0.0
    assists = float(df["assists"].fillna(0).mean()) if games else 0.0
    total_kills = int(df["kills"].fillna(0).sum()) if games else 0
    total_deaths = int(df["deaths"].fillna(0).sum()) if games else 0
    total_assists = int(df["assists"].fillna(0).sum()) if games else 0
    lp_delta = estimate_lp_delta(user_id, period, db_path=db_path)
    return {
        "games": games,
        "wins": wins,
        "losses": losses,
        "winrate": compute_winrate(wins, games),
        "avg_kills": round(kills, 2),
        "avg_deaths": round(deaths, 2),
        "avg_assists": round(assists, 2),
        "avg_kda": compute_kda(total_kills, total_deaths, total_assists),
        "lp_delta": lp_delta["delta"],
        "lp_delta_text": lp_delta["text"],
        "total_duration_seconds": int(df["game_duration_seconds"].fillna(0).sum()) if games else 0,
    }


def aggregate_leaderboard(
    period: str = "today", metric: str = "games", db_path: Path | str = DEFAULT_DB_PATH
) -> pd.DataFrame:
    df = load_matches(period=period, db_path=db_path)
    if df.empty:
        return pd.DataFrame(
            columns=["discord_user_id", "display_name", "games", "wins", "losses", "winrate", "lp_delta", "total_time"]
        )
    grouped = (
        df.groupby(["discord_user_id", "display_name"], dropna=False)
        .agg(
            games=("match_id", "count"),
            wins=("win", "sum"),
            total_time=("game_duration_seconds", "sum"),
        )
        .reset_index()
    )
    grouped["losses"] = grouped["games"] - grouped["wins"]
    grouped["winrate"] = grouped.apply(lambda row: compute_winrate(row["wins"], row["games"]), axis=1)
    grouped["lp_delta"] = grouped["discord_user_id"].apply(
        lambda user_id: estimate_lp_delta(user_id, period, db_path=db_path)["delta"]
    )
    sort_metric = metric if metric in grouped.columns else "games"
    return grouped.sort_values(sort_metric, ascending=False)


def estimate_lp_delta(
    user_id: str, period: str = "today", queue_type: str = "RANKED_SOLO_5x5", db_path: Path | str = DEFAULT_DB_PATH
) -> dict[str, Any]:
    start = get_period_start(period)
    params: list[Any] = [user_id, queue_type]
    start_clause = ""
    if start is not None:
        start_clause = "AND snapshot_ts >= ?"
        params.append(start)
    with _connect(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT tier, rank, league_points, snapshot_ts
            FROM ranked_snapshots
            WHERE discord_user_id=? AND queue_type=? {start_clause}
            ORDER BY snapshot_ts ASC
            """,
            params,
        ).fetchall()
    if len(rows) < 2:
        return {"delta": 0, "text": "not enough snapshots"}
    first = rows[0]
    latest = rows[-1]
    first_points = rank_points(first["tier"], first["rank"], first["league_points"])
    latest_points = rank_points(latest["tier"], latest["rank"], latest["league_points"])
    if first_points is None or latest_points is None:
        return {"delta": 0, "text": "unranked or unknown rank"}
    delta = latest_points - first_points
    first_label = rank_label(first["tier"], first["rank"], first["league_points"])
    latest_label = rank_label(latest["tier"], latest["rank"], latest["league_points"])
    if first_label != latest_label:
        text = f"{first_label} -> {latest_label} ({delta:+d})"
    else:
        text = f"{delta:+d} LP"
    return {"delta": delta, "text": text}


def latest_rank(user_id: str, db_path: Path | str = DEFAULT_DB_PATH) -> str:
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT tier, rank, league_points
            FROM ranked_snapshots
            WHERE discord_user_id=? AND queue_type='RANKED_SOLO_5x5'
            ORDER BY snapshot_ts DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    if not row:
        return "Unranked"
    return rank_label(row["tier"], row["rank"], row["league_points"])


def player_options(db_path: Path | str = DEFAULT_DB_PATH) -> list[dict[str, str]]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT u.discord_user_id, COALESCE(u.display_name, r.game_name, u.discord_user_id) AS label
            FROM users u
            LEFT JOIN riot_accounts r ON r.discord_user_id = u.discord_user_id
            WHERE u.opted_in=1
            ORDER BY label
            """
        ).fetchall()
    return [{"label": row["label"], "value": row["discord_user_id"]} for row in rows]


def _presence_duration(row: pd.Series, period_start: int | None, period_end: int) -> int:
    start_ts = int(row["start_ts"] or 0)
    end_ts = int(row["end_ts"] or period_end)
    clipped_start = max(start_ts, period_start or 0)
    clipped_end = min(end_ts, period_end)
    return max(0, clipped_end - clipped_start)


def load_presence_sessions(
    user_id: str | None = None,
    period: str = "today",
    db_path: Path | str = DEFAULT_DB_PATH,
) -> pd.DataFrame:
    period_start = get_period_start(period)
    now = utc_now_ts()
    clauses = []
    params: list[Any] = []
    if user_id:
        clauses.append("p.discord_user_id=?")
        params.append(user_id)
    if period_start is not None:
        clauses.append("COALESCE(p.end_ts, ?) >= ?")
        params.extend([now, period_start])
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    with _connect(db_path) as conn:
        df = pd.read_sql_query(
            f"""
            SELECT p.*, u.display_name
            FROM presence_sessions p
            LEFT JOIN users u ON u.discord_user_id = p.discord_user_id
            {where}
            ORDER BY p.start_ts DESC
            """,
            conn,
            params=params,
        )
    if df.empty:
        return df
    df["effective_duration_seconds"] = df.apply(
        lambda row: _presence_duration(row, period_start, now),
        axis=1,
    )
    return df[df["effective_duration_seconds"] > 0]


def aggregate_discord_presence(
    user_id: str,
    period: str = "today",
    db_path: Path | str = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    df = load_presence_sessions(user_id, period, db_path)
    if df.empty:
        return {
            "online_seconds": 0,
            "voice_seconds": 0,
            "league_presence_seconds": 0,
            "open_sessions": 0,
            "sessions": 0,
        }
    grouped = df.groupby("activity_type")["effective_duration_seconds"].sum().to_dict()
    return {
        "online_seconds": int(grouped.get(DISCORD_ONLINE_TYPE, 0)),
        "voice_seconds": int(grouped.get(DISCORD_VOICE_TYPE, 0)),
        "league_presence_seconds": int(grouped.get(LEAGUE_ACTIVITY_TYPE, 0)),
        "open_sessions": int(df["end_ts"].isna().sum()),
        "sessions": int(len(df)),
    }


def aggregate_discord_presence_leaderboard(
    period: str = "today",
    metric: str = "voice_seconds",
    db_path: Path | str = DEFAULT_DB_PATH,
) -> pd.DataFrame:
    df = load_presence_sessions(period=period, db_path=db_path)
    columns = ["discord_user_id", "display_name", "online_seconds", "voice_seconds", "league_presence_seconds"]
    if df.empty:
        return pd.DataFrame(columns=columns)
    pivot = (
        df.pivot_table(
            index=["discord_user_id", "display_name"],
            columns="activity_type",
            values="effective_duration_seconds",
            aggfunc="sum",
            fill_value=0,
        )
        .reset_index()
        .rename_axis(None, axis=1)
    )
    for activity_type in (DISCORD_ONLINE_TYPE, DISCORD_VOICE_TYPE, LEAGUE_ACTIVITY_TYPE):
        if activity_type not in pivot.columns:
            pivot[activity_type] = 0
    pivot = pivot.rename(
        columns={
            DISCORD_ONLINE_TYPE: "online_seconds",
            DISCORD_VOICE_TYPE: "voice_seconds",
            LEAGUE_ACTIVITY_TYPE: "league_presence_seconds",
        }
    )
    sort_metric = metric if metric in pivot.columns else "voice_seconds"
    return pivot[columns].sort_values(sort_metric, ascending=False)


def recompute_daily_summary(user_id: str, date_utc: str, db_path: Path | str = DEFAULT_DB_PATH) -> None:
    start = int(datetime.fromisoformat(date_utc).replace(tzinfo=UTC).timestamp())
    end = start + 86400
    with _connect(db_path) as conn:
        df = pd.read_sql_query(
            """
            SELECT *
            FROM matches
            WHERE discord_user_id=?
              AND COALESCE(game_end_timestamp, game_start_timestamp, game_creation, created_at) >= ?
              AND COALESCE(game_end_timestamp, game_start_timestamp, game_creation, created_at) < ?
            """,
            conn,
            params=[user_id, start, end],
        )
        games = int(len(df))
        wins = int(df["win"].sum()) if games else 0
        ranked = df[df["queue_name"].isin(RANKED_QUEUES)] if games else df
        ranked_games = int(len(ranked))
        lp_delta = estimate_lp_delta(user_id, "today", db_path=db_path)["delta"] if date_utc == datetime.now(UTC).date().isoformat() else 0
        now = utc_now_ts()
        conn.execute(
            """
            INSERT INTO daily_summaries(
                discord_user_id, date_utc, games, wins, losses, ranked_games, ranked_wins, ranked_losses,
                total_duration_seconds, avg_kills, avg_deaths, avg_assists, avg_kda, lp_delta, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(discord_user_id, date_utc) DO UPDATE SET
                games=excluded.games,
                wins=excluded.wins,
                losses=excluded.losses,
                ranked_games=excluded.ranked_games,
                ranked_wins=excluded.ranked_wins,
                ranked_losses=excluded.ranked_losses,
                total_duration_seconds=excluded.total_duration_seconds,
                avg_kills=excluded.avg_kills,
                avg_deaths=excluded.avg_deaths,
                avg_assists=excluded.avg_assists,
                avg_kda=excluded.avg_kda,
                lp_delta=excluded.lp_delta,
                updated_at=excluded.updated_at
            """,
            (
                user_id,
                date_utc,
                games,
                wins,
                games - wins,
                ranked_games,
                int(ranked["win"].sum()) if ranked_games else 0,
                ranked_games - int(ranked["win"].sum()) if ranked_games else 0,
                int(df["game_duration_seconds"].fillna(0).sum()) if games else 0,
                float(df["kills"].fillna(0).mean()) if games else 0.0,
                float(df["deaths"].fillna(0).mean()) if games else 0.0,
                float(df["assists"].fillna(0).mean()) if games else 0.0,
                compute_kda(int(df["kills"].fillna(0).sum()), int(df["deaths"].fillna(0).sum()), int(df["assists"].fillna(0).sum())) if games else 0.0,
                lp_delta,
                now,
                now,
            ),
        )
        conn.commit()
