from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LinkedAccount:
    discord_user_id: str
    guild_id: str
    display_name: str | None
    game_name: str
    tag_line: str
    puuid: str
    platform_routing: str
    region_cluster: str


@dataclass(frozen=True)
class MatchRecord:
    match_id: str
    puuid: str
    discord_user_id: str
    game_creation: int | None
    game_start_timestamp: int | None
    game_end_timestamp: int | None
    game_duration_seconds: int | None
    queue_id: int | None
    queue_name: str | None
    champion_name: str | None
    team_position: str | None
    individual_position: str | None
    win: int
    kills: int | None
    deaths: int | None
    assists: int | None
    total_damage_dealt_to_champions: int | None
    gold_earned: int | None
    total_minions_killed: int | None
    neutral_minions_killed: int | None
    cs: int | None
    vision_score: int | None
    summoner_level: int | None
    item0: int | None
    item1: int | None
    item2: int | None
    item3: int | None
    item4: int | None
    item5: int | None
    item6: int | None
    raw_json: str
    created_at: int

