from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "degenerate_tracker.sqlite"


@dataclass(frozen=True)
class Settings:
    discord_token: str
    riot_api_key: str
    guild_id: int | None
    riot_region_cluster: str
    riot_platform_routing: str
    poll_interval_seconds: int
    dash_host: str
    dash_port: int
    public_dashboard_url: str | None
    database_path: Path

    @property
    def local_dashboard_url(self) -> str:
        return f"http://localhost:{self.dash_port}"

    @property
    def dashboard_base_url(self) -> str:
        return (self.public_dashboard_url or self.local_dashboard_url).rstrip("/")


def _optional_int(value: str | None) -> int | None:
    if not value:
        return None
    return int(value)


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        discord_token=os.getenv("DISCORD_TOKEN", ""),
        riot_api_key=os.getenv("RIOT_API_KEY", ""),
        guild_id=_optional_int(os.getenv("GUILD_ID")),
        riot_region_cluster=os.getenv("RIOT_REGION_CLUSTER", "europe"),
        riot_platform_routing=os.getenv("RIOT_PLATFORM_ROUTING", "euw1"),
        poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "300")),
        dash_host=os.getenv("DASH_HOST", "0.0.0.0"),
        dash_port=int(os.getenv("DASH_PORT", "8050")),
        public_dashboard_url=os.getenv("PUBLIC_DASHBOARD_URL") or None,
        database_path=Path(os.getenv("DATABASE_PATH", str(DEFAULT_DB_PATH))),
    )

