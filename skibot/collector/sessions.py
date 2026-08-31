"""Regroupement déterministe des games en sessions de jeu.

Une session = suite de games où l'écart entre la fin d'une game et le début de la
suivante est inférieur au seuil (60 min par défaut). Recalculé à chaque collecte ;
les notes manuelles sont préservées par started_at.
"""

from __future__ import annotations

import sqlite3


def rebuild_sessions(conn: sqlite3.Connection, gap_minutes: int) -> int:
    """Recalcule toutes les sessions. Retourne le nombre de sessions."""
    rows = conn.execute(
        "SELECT match_id, game_start, "
        "COALESCE(game_end, game_start + game_duration_s * 1000) AS game_end "
        "FROM matches ORDER BY game_start"
    ).fetchall()
    gap_ms = gap_minutes * 60 * 1000

    groups: list[list[sqlite3.Row]] = []
    current: list[sqlite3.Row] = []
    prev_end: int | None = None
    for r in rows:
        if prev_end is not None and r["game_start"] - prev_end > gap_ms:
            groups.append(current)
            current = []
        current.append(r)
        prev_end = r["game_end"]
    if current:
        groups.append(current)

    with conn:
        notes = {
            r["started_at"]: r["note"]
            for r in conn.execute("SELECT started_at, note FROM sessions WHERE note IS NOT NULL")
        }
        conn.execute("UPDATE matches SET session_id = NULL")
        conn.execute("DELETE FROM sessions")
        for g in groups:
            started_at = g[0]["game_start"]
            cur = conn.execute(
                "INSERT INTO sessions (started_at, ended_at, n_games, note) VALUES (?, ?, ?, ?)",
                (started_at, g[-1]["game_end"], len(g), notes.get(started_at)),
            )
            sid = cur.lastrowid
            conn.executemany(
                "UPDATE matches SET session_id = ? WHERE match_id = ?",
                [(sid, r["match_id"]) for r in g],
            )
    return len(groups)
