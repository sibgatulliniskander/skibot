"""Parsing des payloads Match-V5 (match + timeline) vers les tables SQLite."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

# Champs promus en colonnes dans timeline_events ; le reste part dans extra_json
_PROMOTED_EVENT_KEYS = {
    "timestamp", "type", "participantId", "creatorId", "killerId", "victimId",
    "assistingParticipantIds", "position", "monsterType", "monsterSubType",
    "buildingType", "towerType", "laneType", "wardType", "itemId", "skillSlot",
}
# Volumineux et déjà présents dans raw_timeline_json : on ne les duplique pas
_EXCLUDED_FROM_EXTRA = {"victimDamageDealt", "victimDamageReceived"}


def is_valid_match(match_json: dict) -> bool:
    """Riot renvoie parfois un payload vide (gameCreation=0, durée 0, sans participants)."""
    info = match_json.get("info") or {}
    return bool(info.get("gameCreation")) and bool(info.get("participants"))


def match_exists(conn: sqlite3.Connection, match_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM matches WHERE match_id = ?", (match_id,)).fetchone()
    return row is not None


def ingest_match(
    conn: sqlite3.Connection,
    match_json: dict,
    timeline_json: dict | None,
    my_puuid: str,
) -> None:
    """Insère une game complète (match + participants + timeline) en une seule transaction."""
    info = match_json["info"]
    match_id = match_json["metadata"]["matchId"]
    version = info.get("gameVersion", "")
    patch = ".".join(version.split(".")[:2])
    with conn:
        conn.execute(
            """INSERT INTO matches
               (match_id, queue_id, platform_id, game_version, patch, game_creation,
                game_start, game_end, game_duration_s, fetched_at, has_timeline,
                raw_match_json, raw_timeline_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                match_id,
                info["queueId"],
                info.get("platformId", ""),
                version,
                patch,
                info["gameCreation"],
                info.get("gameStartTimestamp", info["gameCreation"]),
                info.get("gameEndTimestamp"),
                info["gameDuration"],
                datetime.now(UTC).isoformat(timespec="seconds"),
                1 if timeline_json is not None else 0,
                json.dumps(match_json, separators=(",", ":")),
                json.dumps(timeline_json, separators=(",", ":")) if timeline_json else None,
            ),
        )
        for p in info["participants"]:
            riot_id = None
            if p.get("riotIdGameName"):
                riot_id = f"{p['riotIdGameName']}#{p.get('riotIdTagline', '')}"
            conn.execute(
                """INSERT INTO participants
                   (match_id, participant_id, puuid, riot_id, is_me, team_id, win,
                    champion_id, champion_name, team_position, kills, deaths, assists,
                    gold_earned, cs_total, vision_score, damage_to_champions, raw_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    match_id,
                    p["participantId"],
                    p["puuid"],
                    riot_id,
                    1 if p["puuid"] == my_puuid else 0,
                    p["teamId"],
                    1 if p["win"] else 0,
                    p["championId"],
                    p["championName"],
                    p.get("teamPosition"),
                    p["kills"],
                    p["deaths"],
                    p["assists"],
                    p["goldEarned"],
                    p.get("totalMinionsKilled", 0) + p.get("neutralMinionsKilled", 0),
                    p.get("visionScore", 0),
                    p.get("totalDamageDealtToChampions", 0),
                    json.dumps(p, separators=(",", ":")),
                ),
            )
        if timeline_json is not None:
            _ingest_timeline(conn, match_id, timeline_json)


def _ingest_timeline(conn: sqlite3.Connection, match_id: str, timeline: dict) -> None:
    # Riot renvoie parfois null au lieu de {}/[] : toujours normaliser avec "or"
    for idx, frame in enumerate(timeline["info"].get("frames") or []):
        for pid_str, pf in (frame.get("participantFrames") or {}).items():
            pos = pf.get("position") or {}
            dmg = pf.get("damageStats") or {}
            conn.execute(
                """INSERT INTO timeline_frames
                   (match_id, frame_index, participant_id, timestamp_ms, total_gold,
                    current_gold, xp, level, minions_killed, jungle_minions_killed,
                    pos_x, pos_y, damage_to_champions, damage_taken)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    match_id,
                    idx,
                    int(pid_str),
                    frame["timestamp"],
                    pf.get("totalGold", 0),
                    pf.get("currentGold", 0),
                    pf.get("xp", 0),
                    pf.get("level", 0),
                    pf.get("minionsKilled", 0),
                    pf.get("jungleMinionsKilled", 0),
                    pos.get("x"),
                    pos.get("y"),
                    dmg.get("totalDamageDoneToChampions"),
                    dmg.get("totalDamageTaken"),
                ),
            )
        for ev in (frame.get("events") or []):
            _insert_event(conn, match_id, ev)


def _insert_event(conn: sqlite3.Connection, match_id: str, ev: dict) -> None:
    pos = ev.get("position") or {}
    # WARD_PLACED (et autres events "creator") utilisent creatorId au lieu de participantId
    participant_id = ev.get("participantId")
    if participant_id is None:
        participant_id = ev.get("creatorId")
    assisting = ev.get("assistingParticipantIds")
    extra = {
        k: v for k, v in ev.items()
        if k not in _PROMOTED_EVENT_KEYS and k not in _EXCLUDED_FROM_EXTRA
    }
    conn.execute(
        """INSERT INTO timeline_events
           (match_id, timestamp_ms, type, participant_id, killer_id, victim_id,
            assisting_ids, pos_x, pos_y, monster_type, monster_sub_type, building_type,
            tower_type, lane_type, ward_type, item_id, skill_slot, extra_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            match_id,
            ev.get("timestamp", 0),
            ev.get("type", "UNKNOWN"),
            participant_id,
            ev.get("killerId"),
            ev.get("victimId"),
            json.dumps(assisting) if assisting is not None else None,
            pos.get("x"),
            pos.get("y"),
            ev.get("monsterType"),
            ev.get("monsterSubType"),
            ev.get("buildingType"),
            ev.get("towerType"),
            ev.get("laneType"),
            ev.get("wardType"),
            ev.get("itemId"),
            ev.get("skillSlot"),
            json.dumps(extra, separators=(",", ":")) if extra else None,
        ),
    )
