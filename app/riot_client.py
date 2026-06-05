from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import quote

import aiohttp

logger = logging.getLogger(__name__)


class RiotClient:
    def __init__(self, api_key: str, default_region_cluster: str, default_platform_routing: str):
        self.api_key = api_key
        self.default_region_cluster = default_region_cluster
        self.default_platform_routing = default_platform_routing
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "RiotClient":
        await self.open()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def open(self) -> None:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers={"X-Riot-Token": self.api_key})

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(self, url: str, *, retries: int = 3) -> Any | None:
        await self.open()
        assert self._session is not None

        for attempt in range(retries + 1):
            try:
                async with self._session.get(url) as response:
                    if response.status == 429:
                        retry_after = int(response.headers.get("Retry-After", "1"))
                        logger.warning("Riot API rate limited; retrying after %ss", retry_after)
                        await asyncio.sleep(retry_after)
                        continue
                    if response.status == 404:
                        return None
                    if response.status == 403:
                        logger.warning("Riot API returned 403. Check that the development key is still valid.")
                        return None
                    if response.status >= 500:
                        wait_seconds = min(2**attempt, 30)
                        logger.warning("Riot API server error %s; retrying in %ss", response.status, wait_seconds)
                        await asyncio.sleep(wait_seconds)
                        continue
                    if response.status >= 400:
                        logger.warning("Riot API returned HTTP %s for %s", response.status, self._redact_url(url))
                        return None
                    return await response.json()
            except aiohttp.ClientError as exc:
                wait_seconds = min(2**attempt, 30)
                logger.warning("Riot API request failed: %s; retrying in %ss", exc.__class__.__name__, wait_seconds)
                await asyncio.sleep(wait_seconds)
        return None

    @staticmethod
    def _redact_url(url: str) -> str:
        return url.split("?api_key=", 1)[0]

    async def resolve_riot_id(
        self, game_name: str, tag_line: str, region_cluster: str | None = None
    ) -> dict[str, Any] | None:
        region = region_cluster or self.default_region_cluster
        encoded_game = quote(game_name, safe="")
        encoded_tag = quote(tag_line, safe="")
        url = f"https://{region}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{encoded_game}/{encoded_tag}"
        return await self._request(url)

    async def get_recent_match_ids(
        self, puuid: str, region_cluster: str | None = None, count: int = 20
    ) -> list[str]:
        region = region_cluster or self.default_region_cluster
        url = (
            f"https://{region}.api.riotgames.com/lol/match/v5/matches/by-puuid/"
            f"{quote(puuid, safe='')}/ids?start=0&count={count}"
        )
        data = await self._request(url)
        return data if isinstance(data, list) else []

    async def get_match(self, match_id: str, region_cluster: str | None = None) -> dict[str, Any] | None:
        region = region_cluster or self.default_region_cluster
        url = f"https://{region}.api.riotgames.com/lol/match/v5/matches/{quote(match_id, safe='')}"
        data = await self._request(url)
        return data if isinstance(data, dict) else None

    async def get_ranked_entries_by_puuid(
        self, puuid: str, platform_routing: str | None = None
    ) -> list[dict[str, Any]]:
        platform = platform_routing or self.default_platform_routing
        url = f"https://{platform}.api.riotgames.com/lol/league/v4/entries/by-puuid/{quote(puuid, safe='')}"
        data = await self._request(url)
        return data if isinstance(data, list) else []

