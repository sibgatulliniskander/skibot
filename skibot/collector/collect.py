"""Orchestration de la collecte incrémentale des games ranked (multi-comptes)."""

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
    """Récupère les nouvelles games de chaque compte, met à jour sessions et rangs.

    Multi-comptes (main + smurfs) : même base, même joueur — les sessions et
    l'analyse fusionnent la chronologie. Idempotent : chaque game est insérée
    dans sa propre transaction ; une interruption ne perd rien.
    """
    accounts = cfg.accounts or ((cfg.game_name, cfg.tag_line),)
    known = {r["match_id"] for r in conn.execute("SELECT match_id FROM matches")}
    n_ok = n_no_timeline = n_skipped = 0
    ranks: list[tuple[str, str | None]] = []

    for game_name, tag_line in accounts:
        account = client.account_by_riot_id(game_name, tag_line)
        puuid = account["puuid"]
        riot_id = f"{account.get('gameName')}#{account.get('tagLine')}"
        log(f"Compte résolu : {riot_id}")

        # Borne temporelle PAR COMPTE : dernière game connue de ce compte,
        # avec 1 h de marge (les doublons sont filtrés via known).
        last = conn.execute(
            """SELECT MAX(m.game_creation) AS ts FROM matches m
               JOIN participants p ON p.match_id = m.match_id
               WHERE p.is_me = 1 AND p.puuid = ?""",
            (puuid,),
        ).fetchone()["ts"]
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

        todo = [m for m in reversed(all_ids) if m not in known]  # ancien -> récent
        if max_games is not None:
            todo = todo[:max_games]
        log(f"{len(todo)} nouvelle(s) game(s) à récupérer pour {riot_id}")

        for i, match_id in enumerate(todo, 1):
            known.add(match_id)
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

        ranks.append((riot_id, snapshot_rank(conn, client, puuid, riot_id=riot_id)))

    n_sessions = sessions.rebuild_sessions(conn, cfg.session_gap_minutes)
    return {
        "new_games": n_ok,
        "no_timeline": n_no_timeline,
        "skipped": n_skipped,
        "sessions": n_sessions,
        "rank": ranks[0][1] if ranks else None,
        "ranks": ranks,
    }


def snapshot_rank(
    conn: sqlite3.Connection, client: RiotClient, puuid: str, *, riot_id: str | None = None
) -> str | None:
    """Snapshotte le rang solo/duo actuel (seule source possible d'historique LP)."""
    entries = client.league_entries(puuid)
    solo = next((e for e in entries if e.get("queueType") == "RANKED_SOLO_5x5"), None)
    if solo is None:
        return None
    with conn:
        conn.execute(
            """INSERT INTO rank_snapshots
               (taken_at, queue_type, tier, division, lp, wins, losses, riot_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(UTC).isoformat(timespec="seconds"),
                solo["queueType"],
                solo["tier"],
                solo["rank"],
                solo["leaguePoints"],
                solo["wins"],
                solo["losses"],
                riot_id,
            ),
        )
    return f"{solo['tier']} {solo['rank']} — {solo['leaguePoints']} LP"
