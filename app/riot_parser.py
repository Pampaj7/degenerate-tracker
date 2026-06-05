from __future__ import annotations

import json
from typing import Any

from app.formatters import utc_now_ts
from app.models import MatchRecord


QUEUE_NAMES = {
    400: "Normal Draft",
    420: "Ranked Solo",
    430: "Normal Blind",
    440: "Ranked Flex",
    450: "ARAM",
    490: "Quickplay",
    700: "Clash",
    1700: "Arena",
}


def _ms_to_seconds(value: int | None) -> int | None:
    if value is None:
        return None
    return int(value / 1000)


def parse_match(match_id: str, payload: dict[str, Any], puuid: str, discord_user_id: str) -> MatchRecord | None:
    info = payload.get("info") or {}
    participants = info.get("participants") or []
    participant = next((p for p in participants if p.get("puuid") == puuid), None)
    if participant is None:
        return None

    total_minions = participant.get("totalMinionsKilled") or 0
    neutral_minions = participant.get("neutralMinionsKilled") or 0
    queue_id = info.get("queueId")

    return MatchRecord(
        match_id=match_id,
        puuid=puuid,
        discord_user_id=discord_user_id,
        game_creation=_ms_to_seconds(info.get("gameCreation")),
        game_start_timestamp=_ms_to_seconds(info.get("gameStartTimestamp")),
        game_end_timestamp=_ms_to_seconds(info.get("gameEndTimestamp")),
        game_duration_seconds=info.get("gameDuration"),
        queue_id=queue_id,
        queue_name=QUEUE_NAMES.get(queue_id, f"Queue {queue_id}" if queue_id is not None else None),
        champion_name=participant.get("championName"),
        team_position=participant.get("teamPosition"),
        individual_position=participant.get("individualPosition"),
        win=int(bool(participant.get("win"))),
        kills=participant.get("kills"),
        deaths=participant.get("deaths"),
        assists=participant.get("assists"),
        total_damage_dealt_to_champions=participant.get("totalDamageDealtToChampions"),
        gold_earned=participant.get("goldEarned"),
        total_minions_killed=participant.get("totalMinionsKilled"),
        neutral_minions_killed=participant.get("neutralMinionsKilled"),
        cs=total_minions + neutral_minions,
        vision_score=participant.get("visionScore"),
        summoner_level=participant.get("summonerLevel"),
        item0=participant.get("item0"),
        item1=participant.get("item1"),
        item2=participant.get("item2"),
        item3=participant.get("item3"),
        item4=participant.get("item4"),
        item5=participant.get("item5"),
        item6=participant.get("item6"),
        raw_json=json.dumps(payload, separators=(",", ":")),
        created_at=utc_now_ts(),
    )

