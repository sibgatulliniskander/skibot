"""Extraction des features : une ligne par game, recalculable à volonté depuis la base.

Clause d'honnêteté : chaque valeur provient de la donnée (tables aplaties,
challenges Riot, Data Dragon). Ce qui n'est pas mesurable reste NULL.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime

from . import ddragon

EXTRACTOR_VERSION = 3
FAMILIARITY_WINDOW_DAYS = 30
MS = 60_000  # une minute en ms

COLUMNS = [
    "match_id", "computed_at", "extractor_version", "account",
    "y_win", "y2_team_gold_diff_15", "is_remake", "ended_in_surrender",
    "session_game_index", "games_played_today", "minutes_since_prev_game",
    "prev_game_result", "current_streak", "hour_of_day", "day_of_week",
    "session_length_so_far_min",
    "my_champion", "my_champ_recent_games", "my_champ_recent_wr",
    "enemy_jungler_champion", "side", "i_am_autofilled",
    "ally_tank_count", "enemy_tank_count", "ally_ranged_count", "enemy_ranged_count",
    "ally_ap_ratio", "enemy_ap_ratio",
    "gold_diff_ejgl_5", "gold_diff_ejgl_10", "gold_diff_ejgl_15",
    "xp_diff_ejgl_10", "cs_diff_ejgl_10",
    "kills_pre15", "deaths_pre15", "assists_pre15", "deaths_pre8",
    "first_blood_team", "first_dragon_team", "grubs_team", "herald_team", "plates_diff",
    "dragons_diff", "soul_team", "barons_diff", "atakhan_team", "towers_diff",
    "deaths_post25", "kill_participation", "damage_share",
    "wards_placed", "wards_killed", "control_wards_bought",
    "jungle_cs_before_10", "counter_jungle_diff", "scuttle_crabs",
    "initial_crab_secured", "early_gank_kills", "early_jungle_duel_kills",
    "solo_kills", "epic_monster_steals", "vision_advantage_vs_ejgl",
    "pings_total", "on_my_way_pings",
]


def run(
    conn: sqlite3.Connection,
    *,
    rebuild: bool = False,
    meta_provider: Callable[[str], dict | None] = ddragon.champion_meta,
    log: Callable[[str], None] = print,
) -> dict:
    """Extrait les features des games qui n'en ont pas encore (ou toutes si rebuild)."""
    if rebuild:
        with conn:
            conn.execute("DELETE FROM features")
    hist = _my_history(conn)
    ctx = _session_context(hist)
    done = {r["match_id"] for r in conn.execute("SELECT match_id FROM features")}
    todo = [h for h in hist if h["match_id"] not in done]
    log(f"{len(todo)} game(s) à extraire (extracteur v{EXTRACTOR_VERSION})")

    meta_cache: dict[str, dict | None] = {}
    n = 0
    with conn:
        for h in todo:
            patch = h["patch"]
            if patch not in meta_cache:
                meta_cache[patch] = meta_provider(patch)
                if meta_cache[patch] is None:
                    log(f"  Data Dragon indisponible (patch {patch}) : compo à NULL")
            f = _extract_one(conn, h, ctx[h["match_id"]], meta_cache[patch])
            for c in COLUMNS:
                f.setdefault(c, None)
            conn.execute(
                "INSERT OR REPLACE INTO features ({}) VALUES ({})".format(
                    ", ".join(COLUMNS), ", ".join(":" + c for c in COLUMNS)
                ),
                f,
            )
            n += 1
            if n % 100 == 0:
                log(f"  {n}/{len(todo)}")

    return {
        "extracted": n,
        "total": conn.execute("SELECT COUNT(*) c FROM features").fetchone()["c"],
        "with_challenges": conn.execute(
            "SELECT COUNT(*) c FROM features WHERE jungle_cs_before_10 IS NOT NULL"
        ).fetchone()["c"],
        "with_gold15": conn.execute(
            "SELECT COUNT(*) c FROM features WHERE y2_team_gold_diff_15 IS NOT NULL"
        ).fetchone()["c"],
        "remakes": conn.execute(
            "SELECT COUNT(*) c FROM features WHERE is_remake = 1"
        ).fetchone()["c"],
    }


def _my_history(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT m.match_id, m.game_start,
                  COALESCE(m.game_end, m.game_start + m.game_duration_s * 1000) AS game_end,
                  m.session_id, m.patch, m.has_timeline,
                  s.started_at AS session_started_at,
                  p.win, p.champion_name
           FROM matches m
           JOIN participants p ON p.match_id = m.match_id AND p.is_me = 1
           LEFT JOIN sessions s ON s.session_id = m.session_id
           ORDER BY m.game_start"""
    ).fetchall()


def _session_context(hist: list[sqlite3.Row]) -> dict[str, dict]:
    """Features de contexte (A) : calculées sur l'historique chronologique complet."""
    ctx: dict[str, dict] = {}
    local_dates = [datetime.fromtimestamp(h["game_start"] / 1000).astimezone() for h in hist]
    for i, h in enumerate(hist):
        prev = hist[i - 1] if i else None
        start_local = local_dates[i]

        sgi = 1
        j = i - 1
        while j >= 0 and hist[j]["session_id"] == h["session_id"]:
            sgi += 1
            j -= 1

        streak = 0
        if prev is not None:
            ref = prev["win"]
            j = i - 1
            while j >= 0 and hist[j]["win"] == ref:
                streak += 1
                j -= 1
            streak = streak if ref else -streak

        window_start = h["game_start"] - FAMILIARITY_WINDOW_DAYS * 86_400_000
        recent = [
            k for k in range(i)
            if hist[k]["game_start"] >= window_start
            and hist[k]["champion_name"] == h["champion_name"]
        ]
        ctx[h["match_id"]] = {
            "session_game_index": sgi,
            "games_played_today": sum(
                1 for k in range(i) if local_dates[k].date() == start_local.date()
            ),
            "minutes_since_prev_game": (
                (h["game_start"] - prev["game_end"]) / MS if prev is not None else None
            ),
            "prev_game_result": ("W" if prev["win"] else "L") if prev is not None else None,
            "current_streak": streak,
            "hour_of_day": start_local.hour,
            "day_of_week": start_local.weekday(),
            "session_length_so_far_min": (
                (h["game_start"] - h["session_started_at"]) / MS
                if h["session_started_at"] is not None else None
            ),
            "my_champ_recent_games": len(recent),
            "my_champ_recent_wr": (
                100.0 * sum(hist[k]["win"] for k in recent) / len(recent) if recent else None
            ),
        }
    return ctx


def _extract_one(
    conn: sqlite3.Connection, h: sqlite3.Row, ctx: dict, meta: dict | None
) -> dict:
    mid = h["match_id"]
    parts = conn.execute("SELECT * FROM participants WHERE match_id = ?", (mid,)).fetchall()
    me = next(p for p in parts if p["is_me"])
    my_pid, my_team = me["participant_id"], me["team_id"]
    pid_team = {p["participant_id"]: p["team_id"] for p in parts}
    ejgl = next(
        (p for p in parts if p["team_id"] != my_team and p["team_position"] == "JUNGLE"), None
    )
    raw_me = json.loads(me["raw_json"])
    ch = raw_me.get("challenges") or {}

    f: dict = {
        "match_id": mid,
        "computed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "extractor_version": EXTRACTOR_VERSION,
        "y_win": me["win"],
        "account": me["riot_id"],
        "is_remake": 1 if raw_me.get("gameEndedInEarlySurrender") else 0,
        "ended_in_surrender": 1 if raw_me.get("gameEndedInSurrender") else 0,
        **ctx,
        "my_champion": me["champion_name"],
        "enemy_jungler_champion": ejgl["champion_name"] if ejgl else None,
        "side": "blue" if my_team == 100 else "red",
        "i_am_autofilled": 0 if me["team_position"] == "JUNGLE" else 1,
    }

    # B. compo via Data Dragon
    enemy_team = 200 if my_team == 100 else 100
    for prefix, team in (("ally", my_team), ("enemy", enemy_team)):
        champs = [p["champion_id"] for p in parts if p["team_id"] == team]
        if meta and champs and all(c in meta for c in champs):
            infos = [meta[c] for c in champs]
            f[prefix + "_tank_count"] = sum("Tank" in x["tags"] for x in infos)
            f[prefix + "_ranged_count"] = sum(x["ranged"] for x in infos)
            f[prefix + "_ap_ratio"] = sum(x["ap_ratio"] for x in infos) / len(infos)

    # KP et part des dégâts (depuis le DTO, dispo même sans timeline)
    team_kills = sum(p["kills"] for p in parts if p["team_id"] == my_team)
    f["kill_participation"] = (me["kills"] + me["assists"]) / team_kills if team_kills else None
    team_dmg = sum(p["damage_to_champions"] for p in parts if p["team_id"] == my_team)
    f["damage_share"] = me["damage_to_champions"] / team_dmg if team_dmg else None

    # F. challenges Riot (NULL si absents du payload de cette game)
    f["jungle_cs_before_10"] = ch.get("jungleCsBefore10Minutes")
    f["counter_jungle_diff"] = ch.get("moreEnemyJungleThanOpponent")
    f["scuttle_crabs"] = ch.get("scuttleCrabKills")
    f["initial_crab_secured"] = ch.get("initialCrabCount")
    f["early_gank_kills"] = ch.get("killsOnLanersEarlyJungleAsJungler")
    f["early_jungle_duel_kills"] = ch.get("junglerKillsEarlyJungle")
    f["solo_kills"] = ch.get("soloKills")
    f["epic_monster_steals"] = ch.get("epicMonsterSteals")
    f["vision_advantage_vs_ejgl"] = ch.get("visionScoreAdvantageLaneOpponent")
    ping_vals = [
        v for k, v in raw_me.items() if k.endswith("Pings") and isinstance(v, (int, float))
    ]
    f["pings_total"] = int(sum(ping_vals)) if ping_vals else None
    f["on_my_way_pings"] = raw_me.get("onMyWayPings")

    if h["has_timeline"]:
        _timeline_features(conn, f, mid, my_pid, my_team, pid_team, ejgl)
    return f


def _timeline_features(conn, f, mid, my_pid, my_team, pid_team, ejgl):
    # C. diffs vs jungler adverse aux minutes 5/10/15 + Y2
    fr = {
        (r["frame_index"], r["participant_id"]): r
        for r in conn.execute(
            "SELECT * FROM timeline_frames WHERE match_id = ? AND frame_index IN (5, 10, 15)",
            (mid,),
        )
    }
    ejgl_pid = ejgl["participant_id"] if ejgl else None

    def diff(minute: int, field: str):
        a, b = fr.get((minute, my_pid)), fr.get((minute, ejgl_pid))
        return a[field] - b[field] if a and b else None

    f["gold_diff_ejgl_5"] = diff(5, "total_gold")
    f["gold_diff_ejgl_10"] = diff(10, "total_gold")
    f["gold_diff_ejgl_15"] = diff(15, "total_gold")
    f["xp_diff_ejgl_10"] = diff(10, "xp")
    a, b = fr.get((10, my_pid)), fr.get((10, ejgl_pid))
    if a and b:
        f["cs_diff_ejgl_10"] = (a["minions_killed"] + a["jungle_minions_killed"]) - (
            b["minions_killed"] + b["jungle_minions_killed"]
        )
    g15 = [r for (idx, _pid), r in fr.items() if idx == 15]
    if g15:
        ally = sum(r["total_gold"] for r in g15 if pid_team.get(r["participant_id"]) == my_team)
        enemy = sum(r["total_gold"] for r in g15 if pid_team.get(r["participant_id"]) != my_team)
        f["y2_team_gold_diff_15"] = ally - enemy

    evs = conn.execute(
        """SELECT type, timestamp_ms, participant_id, killer_id, victim_id, assisting_ids,
                  monster_type, building_type, item_id,
                  json_extract(extra_json, '$.teamId') AS ev_team,
                  json_extract(extra_json, '$.killerTeamId') AS killer_team,
                  json_extract(extra_json, '$.killType') AS kill_type
           FROM timeline_events
           WHERE match_id = ? AND type IN
             ('CHAMPION_KILL', 'ELITE_MONSTER_KILL', 'BUILDING_KILL',
              'TURRET_PLATE_DESTROYED', 'DRAGON_SOUL_GIVEN', 'CHAMPION_SPECIAL_KILL',
              'WARD_PLACED', 'WARD_KILL', 'ITEM_PURCHASED')
           ORDER BY timestamp_ms""",
        (mid,),
    ).fetchall()

    def killer_team(e):
        return e["killer_team"] if e["killer_team"] is not None else pid_team.get(e["killer_id"])

    kills = [e for e in evs if e["type"] == "CHAMPION_KILL"]
    f["kills_pre15"] = sum(
        1 for e in kills if e["killer_id"] == my_pid and e["timestamp_ms"] < 15 * MS
    )
    f["deaths_pre15"] = sum(
        1 for e in kills if e["victim_id"] == my_pid and e["timestamp_ms"] < 15 * MS
    )
    f["deaths_pre8"] = sum(
        1 for e in kills if e["victim_id"] == my_pid and e["timestamp_ms"] < 8 * MS
    )
    f["deaths_post25"] = sum(
        1 for e in kills if e["victim_id"] == my_pid and e["timestamp_ms"] >= 25 * MS
    )
    f["assists_pre15"] = sum(
        1 for e in kills
        if e["timestamp_ms"] < 15 * MS
        and e["assisting_ids"] and my_pid in json.loads(e["assisting_ids"])
    )

    fb = next(
        (e for e in evs
         if e["type"] == "CHAMPION_SPECIAL_KILL" and e["kill_type"] == "KILL_FIRST_BLOOD"),
        None,
    )
    f["first_blood_team"] = (1 if pid_team.get(fb["killer_id"]) == my_team else 0) if fb else None

    monsters = [e for e in evs if e["type"] == "ELITE_MONSTER_KILL"]
    dragons = [e for e in monsters if e["monster_type"] == "DRAGON"]
    f["first_dragon_team"] = (1 if killer_team(dragons[0]) == my_team else 0) if dragons else None
    f["dragons_diff"] = sum(1 if killer_team(e) == my_team else -1 for e in dragons)
    f["grubs_team"] = sum(
        1 for e in monsters if e["monster_type"] == "HORDE" and killer_team(e) == my_team
    )
    f["herald_team"] = sum(
        1 for e in monsters if e["monster_type"] == "RIFTHERALD" and killer_team(e) == my_team
    )
    barons = [e for e in monsters if e["monster_type"] == "BARON_NASHOR"]
    f["barons_diff"] = sum(1 if killer_team(e) == my_team else -1 for e in barons)
    f["atakhan_team"] = next(
        (1 if killer_team(e) == my_team else 0
         for e in monsters if e["monster_type"] == "ATAKHAN"),
        None,
    )
    # Riot émet 2 variantes de DRAGON_SOUL_GIVEN : l'annonce du type d'âme
    # (teamId 0, au spawn du 3e dragon) et l'attribution réelle (teamId 100/200).
    # Ne retenir que l'attribution — vérifié contre l'équipe au 4e dragon (429/429).
    soul = next(
        (e for e in evs if e["type"] == "DRAGON_SOUL_GIVEN" and e["ev_team"] in (100, 200)),
        None,
    )
    f["soul_team"] = (1 if soul["ev_team"] == my_team else 0) if soul else None

    # ev_team = équipe qui PERD le bâtiment / la plate
    towers = [
        e for e in evs
        if e["type"] == "BUILDING_KILL" and e["building_type"] == "TOWER_BUILDING"
    ]
    f["towers_diff"] = sum(1 if e["ev_team"] != my_team else -1 for e in towers)
    plates = [e for e in evs if e["type"] == "TURRET_PLATE_DESTROYED"]
    f["plates_diff"] = sum(1 if e["ev_team"] != my_team else -1 for e in plates)

    # E. vision (WARD_KILL utilise killerId ; WARD_PLACED, creatorId -> participant_id)
    f["wards_placed"] = sum(
        1 for e in evs if e["type"] == "WARD_PLACED" and e["participant_id"] == my_pid
    )
    f["wards_killed"] = sum(
        1 for e in evs if e["type"] == "WARD_KILL" and e["killer_id"] == my_pid
    )
    f["control_wards_bought"] = sum(
        1 for e in evs
        if e["type"] == "ITEM_PURCHASED" and e["participant_id"] == my_pid
        and e["item_id"] == 2055
    )
