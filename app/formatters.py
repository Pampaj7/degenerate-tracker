from __future__ import annotations

from datetime import UTC, datetime, timedelta


RANK_ORDER = {
    "IRON": 0,
    "BRONZE": 1,
    "SILVER": 2,
    "GOLD": 3,
    "PLATINUM": 4,
    "EMERALD": 5,
    "DIAMOND": 6,
    "MASTER": 7,
    "GRANDMASTER": 8,
    "CHALLENGER": 9,
}

DIVISION_ORDER = {"IV": 0, "III": 1, "II": 2, "I": 3}


def utc_now_ts() -> int:
    return int(datetime.now(UTC).timestamp())


def ts_to_utc_date(ts: int | None) -> str:
    if not ts:
        return "unknown"
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d")


def format_duration(seconds: int | float | None) -> str:
    if not seconds or seconds < 0:
        return "0m"
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def compute_kda(kills: int | float | None, deaths: int | float | None, assists: int | float | None) -> float:
    kills = kills or 0
    deaths = deaths or 0
    assists = assists or 0
    if deaths <= 0:
        return float(kills + assists)
    return round(float(kills + assists) / float(deaths), 2)


def compute_winrate(wins: int | float | None, games: int | float | None) -> float:
    wins = wins or 0
    games = games or 0
    if games <= 0:
        return 0.0
    return round(float(wins) / float(games) * 100.0, 2)


def get_period_start(period: str) -> int | None:
    now = datetime.now(UTC)
    normalized = (period or "all").lower().strip()
    if normalized == "today":
        start = datetime(now.year, now.month, now.day, tzinfo=UTC)
    elif normalized in {"7d", "7 days", "week"}:
        start = now - timedelta(days=7)
    elif normalized in {"30d", "30 days", "month"}:
        start = now - timedelta(days=30)
    elif normalized == "all":
        return None
    else:
        start = now - timedelta(days=7)
    return int(start.timestamp())


def rank_points(tier: str | None, rank: str | None, lp: int | None) -> int | None:
    if not tier:
        return None
    tier_value = RANK_ORDER.get(tier.upper())
    if tier_value is None:
        return None
    division_value = DIVISION_ORDER.get((rank or "IV").upper(), 0)
    return tier_value * 400 + division_value * 100 + int(lp or 0)


def rank_label(tier: str | None, rank: str | None, lp: int | None) -> str:
    if not tier:
        return "Unranked"
    if tier.upper() in {"MASTER", "GRANDMASTER", "CHALLENGER"}:
        return f"{tier.title()} {lp or 0} LP"
    return f"{tier.title()} {rank or ''} {lp or 0} LP".strip()

