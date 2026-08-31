"""Orchestration de la collecte incrémentale des games ranked."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime

from ..config import Config
from ..riot.client import NotFoundError, RiotClient
from . import ingest, sessions


def collect(
    conn: sqlite3.Connection,
    client: RiotClient,
    cfg: Config,
    *,
    log: Callable[[str], None] = print,
    max_games: int | None = None,
) -> dict:
    """Récupère les nouvelles games (match + timeline), met à jour sessions et rang.

    Idempotent : chaque game est insérée dans sa propre transaction, donc une
    interruption (clé expirée, réseau) ne perd rien — relancer reprend la suite.
    """
    account = client.account_by_riot_id(cfg.game_name, cfg.tag_line)
    puuid = account["puuid"]
    log(f"Compte résolu : {account.get('gameName')}#{account.get('tagLine')}")

    # Borne temporelle : dernière game connue, avec 1 h de marge (les doublons
    # sont filtrés ensuite via les match_id déjà en base).
    last = conn.execute("SELECT MAX(game_creation) AS ts FROM matches").fetchone()["ts"]
    start_time = (last // 1000 - 3600) if last is not None else None

    all_ids: list[str] = []
    start = 0
    while True:
        batch = client.match_ids(
            puuid, queue=cfg.queue_id, start=start, count=100, start_time=start_time
        )
        all_ids.extend(batch)
        if len(batch) < 100:
            break
        start += 100

    known = {r["match_id"] for r in conn.execute("SELECT match_id FROM matches")}
    todo = [m for m in reversed(all_ids) if m not in known]  # du plus ancien au plus récent
    if max_games is not None:
        todo = todo[:max_games]
    log(f"{len(todo)} nouvelle(s) game(s) à récupérer")

    n_ok = 0
    n_no_timeline = 0
    n_skipped = 0
    for i, match_id in enumerate(todo, 1):
        match_json = client.match(match_id)
        if not ingest.is_valid_match(match_json):
            n_skipped += 1
            log(f"  [{i}/{len(todo)}] {match_id} ignorée (payload invalide côté Riot)")
            continue
        try:
            timeline_json = client.timeline(match_id)
        except NotFoundError:
            timeline_json = None
            n_no_timeline += 1
        ingest.ingest_match(conn, match_json, timeline_json, puuid)
        n_ok += 1
        suffix = "" if timeline_json is not None else " (sans timeline)"
        log(f"  [{i}/{len(todo)}] {match_id}{suffix}")

    n_sessions = sessions.rebuild_sessions(conn, cfg.session_gap_minutes)
    rank = snapshot_rank(conn, client, puuid)
    return {
        "new_games": n_ok,
        "no_timeline": n_no_timeline,
        "skipped": n_skipped,
        "sessions": n_sessions,
        "rank": rank,
    }


def snapshot_rank(conn: sqlite3.Connection, client: RiotClient, puuid: str) -> str | None:
    """Snapshotte le rang solo/duo actuel (seule source possible d'historique LP)."""
    entries = client.league_entries(puuid)
    solo = next((e for e in entries if e.get("queueType") == "RANKED_SOLO_5x5"), None)
    if solo is None:
        return None
    with conn:
        conn.execute(
            """INSERT INTO rank_snapshots
               (taken_at, queue_type, tier, division, lp, wins, losses)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(UTC).isoformat(timespec="seconds"),
                solo["queueType"],
                solo["tier"],
                solo["rank"],
                solo["leaguePoints"],
                solo["wins"],
                solo["losses"],
            ),
        )
    return f"{solo['tier']} {solo['rank']} — {solo['leaguePoints']} LP"
