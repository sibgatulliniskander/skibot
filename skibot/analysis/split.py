"""Split exploration/confirmation : tiré une seule fois, PAR SESSION, puis figé en base.

Par session : toutes les games d'une même session vont du même côté, pour
empêcher les fuites de contexte intra-session (streak, fatigue, heure) entre
l'exploration et la confirmation. Une fois assigné, le split n'est JAMAIS
re-tiré : re-tirer jusqu'à obtenir le résultat voulu serait du p-hacking.
"""

from __future__ import annotations

import random
import sqlite3
from datetime import UTC, datetime

DEFAULT_SEED = 42
EXPLORE_FRAC = 0.60


def ensure_split(
    conn: sqlite3.Connection,
    seed: int = DEFAULT_SEED,
    explore_frac: float = EXPLORE_FRAC,
) -> dict:
    """Assigne le split s'il n'existe pas encore ; sinon renvoie l'existant (figé)."""
    existing = conn.execute(
        "SELECT split, COUNT(*) c FROM analysis_split GROUP BY split"
    ).fetchall()
    if existing:
        return {r["split"]: r["c"] for r in existing} | {"frozen": True}

    rows = conn.execute(
        """SELECT f.match_id, m.session_id
           FROM features f JOIN matches m USING (match_id)
           WHERE f.is_remake = 0"""
    ).fetchall()
    by_session: dict[int, list[str]] = {}
    for r in rows:
        by_session.setdefault(r["session_id"], []).append(r["match_id"])

    sessions = sorted(by_session)  # ordre déterministe avant mélange
    random.Random(seed).shuffle(sessions)
    target = round(len(rows) * explore_frac)
    assigned: list[tuple[str, str]] = []
    n_explore = 0
    for sid in sessions:
        games = by_session[sid]
        side = "explore" if n_explore < target else "confirm"
        if side == "explore":
            n_explore += len(games)
        assigned.extend((mid, side) for mid in games)

    now = datetime.now(UTC).isoformat(timespec="seconds")
    with conn:
        conn.executemany(
            "INSERT INTO analysis_split (match_id, split, seed, assigned_at) "
            "VALUES (?, ?, ?, ?)",
            [(mid, side, seed, now) for mid, side in assigned],
        )
    return {"explore": n_explore, "confirm": len(rows) - n_explore, "frozen": False}
