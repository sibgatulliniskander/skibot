"""Client HTTP Riot : Account-V1, Match-V5 (+ timeline), League-V4."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote

import requests

from .rate_limiter import SlidingWindowRateLimiter

MAX_RETRIES_429 = 5
MAX_RETRIES_5XX = 3


class RiotApiError(RuntimeError):
    def __init__(self, status: int, url: str, detail: str = ""):
        self.status = status
        self.url = url
        super().__init__(f"HTTP {status} sur {url} {detail}".strip())


class RiotAuthError(RiotApiError):
    """Clé invalide ou expirée (401/403)."""


class NotFoundError(RiotApiError):
    """404 — ressource absente (ex : timeline indisponible pour une game)."""


class RiotClient:
    def __init__(
        self,
        api_key: str,
        platform: str,
        regional: str,
        limiter: SlidingWindowRateLimiter | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.platform = platform
        self.regional = regional
        self.timeout = timeout
        self.limiter = limiter or SlidingWindowRateLimiter()
        self.session = requests.Session()
        self.session.headers["X-Riot-Token"] = api_key

    def _get(self, url: str, params: dict[str, Any] | None = None) -> Any:
        retries_429 = 0
        retries_5xx = 0
        while True:
            self.limiter.acquire()
            resp = self.session.get(url, params=params, timeout=self.timeout)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (401, 403):
                raise RiotAuthError(
                    resp.status_code,
                    url,
                    "— clé Riot invalide ou expirée. Régénère-la sur "
                    "https://developer.riotgames.com, mets à jour RIOT_API_KEY dans .env "
                    "et relance : la collecte reprendra où elle en était.",
                )
            if resp.status_code == 404:
                raise NotFoundError(404, url)
            if resp.status_code == 429:
                retries_429 += 1
                if retries_429 > MAX_RETRIES_429:
                    raise RiotApiError(429, url, "rate limit persistant malgré les retries")
                retry_after = float(resp.headers.get("Retry-After", "10"))
                time.sleep(retry_after + 0.5)
                continue
            if resp.status_code >= 500:
                retries_5xx += 1
                if retries_5xx > MAX_RETRIES_5XX:
                    raise RiotApiError(resp.status_code, url, resp.text[:200])
                time.sleep(2.0 * retries_5xx)
                continue
            raise RiotApiError(resp.status_code, url, resp.text[:200])

    # ------------------------------------------------------------- endpoints

    def account_by_riot_id(self, game_name: str, tag_line: str) -> dict:
        url = (
            f"https://{self.regional}.api.riotgames.com"
            f"/riot/account/v1/accounts/by-riot-id/{quote(game_name)}/{quote(tag_line)}"
        )
        return self._get(url)

    def match_ids(
        self,
        puuid: str,
        *,
        queue: int,
        start: int = 0,
        count: int = 100,
        start_time: int | None = None,
    ) -> list[str]:
        params: dict[str, Any] = {"queue": queue, "start": start, "count": count}
        if start_time is not None:
            params["startTime"] = int(start_time)  # epoch secondes
        url = (
            f"https://{self.regional}.api.riotgames.com"
            f"/lol/match/v5/matches/by-puuid/{puuid}/ids"
        )
        return self._get(url, params)

    def match(self, match_id: str) -> dict:
        url = f"https://{self.regional}.api.riotgames.com/lol/match/v5/matches/{match_id}"
        return self._get(url)

    def timeline(self, match_id: str) -> dict:
        url = (
            f"https://{self.regional}.api.riotgames.com"
            f"/lol/match/v5/matches/{match_id}/timeline"
        )
        return self._get(url)

    def league_entries_by_tier(
        self, queue: str, tier: str, division: str, page: int = 1
    ) -> list[dict]:
        url = (
            f"https://{self.platform}.api.riotgames.com"
            f"/lol/league/v4/entries/{queue}/{tier}/{division}"
        )
        return self._get(url, {"page": page})

    def league_entries(self, puuid: str) -> list[dict]:
        url = f"https://{self.platform}.api.riotgames.com/lol/league/v4/entries/by-puuid/{puuid}"
        return self._get(url)
