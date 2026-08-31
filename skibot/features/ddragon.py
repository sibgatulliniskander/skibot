"""Cache local Data Dragon : tags, portée et profil de dégâts par champion et par patch."""

from __future__ import annotations

import json

import requests

from ..config import PROJECT_ROOT

CACHE_DIR = PROJECT_ROOT / "data" / "ddragon"
_VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
_CHAMPION_URL = "https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json"


def champion_meta(patch: str) -> dict[int, dict] | None:
    """champion_id -> {tags, ranged, ap_ratio} pour un patch ("15.17").

    Renvoie None en cas d'échec réseau : les features de compo resteront NULL
    plutôt que d'être inventées. Le JSON est caché sur disque par patch.
    """
    cache = CACHE_DIR / f"{patch}.json"
    try:
        if cache.exists():
            raw = json.loads(cache.read_text(encoding="utf-8"))
        else:
            versions = requests.get(_VERSIONS_URL, timeout=15).json()
            version = next((v for v in versions if v.startswith(patch + ".")), versions[0])
            raw = requests.get(_CHAMPION_URL.format(version=version), timeout=30).json()
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(raw), encoding="utf-8")
    except (requests.RequestException, ValueError, KeyError):
        return None
    meta: dict[int, dict] = {}
    for champ in raw["data"].values():
        info = champ.get("info") or {}
        attack, magic = info.get("attack", 0), info.get("magic", 0)
        meta[int(champ["key"])] = {
            "tags": champ.get("tags") or [],
            "ranged": (champ.get("stats") or {}).get("attackrange", 125) >= 350,
            "ap_ratio": magic / (attack + magic) if (attack + magic) else 0.5,
        }
    return meta
