"""Configuration centrale : chargement du .env, chemins, constantes Riot."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Plateforme -> routing régional (Account-V1 et Match-V5 utilisent le régional)
REGIONAL_ROUTING = {
    "euw1": "europe", "eun1": "europe", "tr1": "europe", "ru": "europe", "me1": "europe",
    "na1": "americas", "br1": "americas", "la1": "americas", "la2": "americas",
    "kr": "asia", "jp1": "asia",
    "oc1": "sea", "ph2": "sea", "sg2": "sea", "th2": "sea", "tw2": "sea", "vn2": "sea",
}

QUEUE_SOLO_DUO = 420
SESSION_GAP_MINUTES = 60


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    riot_api_key: str
    game_name: str
    tag_line: str
    platform: str
    db_path: Path
    queue_id: int = QUEUE_SOLO_DUO
    session_gap_minutes: int = SESSION_GAP_MINUTES

    @property
    def regional(self) -> str:
        return REGIONAL_ROUTING[self.platform]


def load_config(require_key: bool = True) -> Config:
    """Charge la config depuis .env. require_key=False pour les commandes hors API (status)."""
    load_dotenv(PROJECT_ROOT / ".env")
    key = os.environ.get("RIOT_API_KEY", "").strip()
    game_name = os.environ.get("RIOT_GAME_NAME", "").strip()
    tag_line = os.environ.get("RIOT_TAG_LINE", "").strip()
    platform = os.environ.get("RIOT_PLATFORM", "euw1").strip().lower()
    if require_key:
        if not key:
            raise ConfigError(
                "RIOT_API_KEY manquante. Copie .env.example vers .env et renseigne ta clé "
                "(developer.riotgames.com)."
            )
        if not game_name or not tag_line:
            raise ConfigError(
                "RIOT_GAME_NAME / RIOT_TAG_LINE manquants dans .env (ton Riot ID : nom#tag)."
            )
    if platform not in REGIONAL_ROUTING:
        raise ConfigError(f"RIOT_PLATFORM inconnue : {platform!r} (ex : euw1)")
    db_path = Path(os.environ.get("SKIBOT_DB", str(PROJECT_ROOT / "data" / "skibot.db")))
    return Config(key, game_name, tag_line, platform, db_path)


def update_env_value(name: str, value: str, env_path: Path | None = None) -> Path:
    """Met à jour (ou ajoute) une variable dans .env, créé depuis .env.example si absent."""
    env_path = env_path or PROJECT_ROOT / ".env"
    example = PROJECT_ROOT / ".env.example"
    if not env_path.exists() and example.exists():
        env_path.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    prefix = f"{name}="
    for i, line in enumerate(lines):
        if line.strip().startswith(prefix):
            lines[i] = f"{name}={value}"
            break
    else:
        lines.append(f"{name}={value}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return env_path
