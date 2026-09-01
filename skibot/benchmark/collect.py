"""Crawler de junglers Diamant+ : échantillon de games pour le benchmark.

Payload match uniquement (pas de timeline) : 1 requête par game, et chaque
game fournit les DEUX junglers. Les métriques extraites utilisent les mêmes
compteurs Riot (challenges / DTO) que les features du joueur.
"""

from __future__ import annotations

import random
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime

from ..features import ddragon
from ..riot.client import NotFoundError, RiotClient

QUEUE = "RANKED_SOLO_5x5"
SEED = 42  # échantillonnage reproductible
MIN_DURATION_S = 300  # < 5 min = remake, exclu


def collect(
    conn: sqlite3.Connection,
    client: RiotClient,
    *,
    tier: str = "DIAMOND",
    divisions: tuple[str, ...] = ("I", "II"),
    max_players: int = 60,
    games_per_player: int = 5,
    log: Callable[[str], None] = print,
) -> dict:
    """Crawl incrémental : les games déjà en base ne sont jamais re-téléchargées."""
    entries: list[dict] = []
    for div in divisions:
        entries.extend(client.league_entries_by_tier(QUEUE, tier, div))
    players = [e["puuid"] for e in entries if e.get("puuid")]
    random.Random(SEED).shuffle(players)
    players = players[:max_players]
    log(f"{len(players)} joueurs {tier} {'/'.join(divisions)} échantillonnés")

    known = {r["match_id"] for r in conn.execute("SELECT DISTINCT match_id FROM bench_games")}
    meta_cache: dict[str, dict | None] = {}
    n_games = n_junglers = 0
    for i, puuid in enumerate(players, 1):
        try:
            ids = client.match_ids(puuid, queue=420, count=games_per_player)
        except NotFoundError:
            continue
        for mid in ids:
            if mid in known:
                continue
            known.add(mid)
            match = client.match(mid)
            rows = extract_junglers(match, tier, meta_cache)
            if not rows:
                continue
            with conn:
                for row in rows:
                    conn.execute(
                        f"INSERT OR IGNORE INTO bench_games ({', '.join(row)}) "
                        f"VALUES ({', '.join(':' + c for c in row)})",
                        row,
                    )
            n_games += 1
            n_junglers += len(rows)
        if i % 10 == 0:
            log(f"  {i}/{len(players)} joueurs — {n_games} games, {n_junglers} junglers")

    total = conn.execute("SELECT COUNT(*) c FROM bench_games").fetchone()["c"]
    return {"new_games": n_games, "new_junglers": n_junglers, "total_junglers": total}


def extract_junglers(match: dict, tier: str, meta_cache: dict) -> list[dict]:
    """Extrait une ligne de métriques par jungler du match (0, 1 ou 2 lignes)."""
    info = match.get("info") or {}
    participants = info.get("participants") or []
    if not info.get("gameCreation") or not participants:
        return []
    if info.get("gameDuration", 0) < MIN_DURATION_S:
        return []
    version = info.get("gameVersion", "")
    patch = ".".join(version.split(".")[:2])
    if patch not in meta_cache:
        meta_cache[patch] = ddragon.champion_meta(patch)
    meta = meta_cache[patch]

    rows = []
    for p in participants:
        if p.get("teamPosition") != "JUNGLE":
            continue
        if p.get("gameEndedInEarlySurrender"):
            return []
        ch = p.get("challenges") or {}
        team_id = p["teamId"]
        mates = [x for x in participants if x["teamId"] == team_id]
        foes = [x for x in participants if x["teamId"] != team_id]
        team_kills = sum(x.get("kills", 0) for x in mates)
        team_dmg = sum(x.get("totalDamageDealtToChampions", 0) for x in mates)
        ping_vals = [v for k, v in p.items() if k.endswith("Pings") and isinstance(v, int)]

        def ap_ratio(team: list[dict]) -> float | None:
            if not meta or any(x["championId"] not in meta for x in team):
                return None
            return sum(meta[x["championId"]]["ap_ratio"] for x in team) / len(team)

        rows.append({
            "match_id": match["metadata"]["matchId"],
            "participant_id": p["participantId"],
            "puuid": p["puuid"],
            "tier": tier,
            "champion_id": p["championId"],
            "champion_name": p["championName"],
            "patch": patch,
            "game_start": info.get("gameStartTimestamp", info["gameCreation"]),
            "game_duration_s": info.get("gameDuration", 0),
            "win": 1 if p.get("win") else 0,
            "jungle_cs_before_10": ch.get("jungleCsBefore10Minutes"),
            "counter_jungle_diff": ch.get("moreEnemyJungleThanOpponent"),
            "scuttle_crabs": ch.get("scuttleCrabKills"),
            "initial_crab_secured": ch.get("initialCrabCount"),
            "early_gank_kills": ch.get("killsOnLanersEarlyJungleAsJungler"),
            "early_jungle_duel_kills": ch.get("junglerKillsEarlyJungle"),
            "solo_kills": ch.get("soloKills"),
            "epic_monster_steals": ch.get("epicMonsterSteals"),
            "vision_advantage_vs_ejgl": ch.get("visionScoreAdvantageLaneOpponent"),
            "kill_participation": (
                (p.get("kills", 0) + p.get("assists", 0)) / team_kills if team_kills else None
            ),
            "damage_share": (
                p.get("totalDamageDealtToChampions", 0) / team_dmg if team_dmg else None
            ),
            "pings_total": int(sum(ping_vals)) if ping_vals else None,
            "on_my_way_pings": p.get("onMyWayPings"),
            "kills": p.get("kills"),
            "deaths": p.get("deaths"),
            "assists": p.get("assists"),
            "wards_placed": p.get("wardsPlaced"),
            "wards_killed": p.get("wardsKilled"),
            "control_wards_bought": p.get("visionWardsBoughtInGame"),
            "ally_ap_ratio": ap_ratio(mates),
            "enemy_ap_ratio": ap_ratio(foes),
            "enemy_tank_count": (
                sum("Tank" in meta[x["championId"]]["tags"] for x in foes)
                if meta and all(x["championId"] in meta for x in foes) else None
            ),
            "item0": p.get("item0"), "item1": p.get("item1"), "item2": p.get("item2"),
            "item3": p.get("item3"), "item4": p.get("item4"), "item5": p.get("item5"),
            "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        })
    return rows


TIMELINE_COLS = ("deaths_pre15", "deaths_post25", "gold_diff_ejgl_10",
                 "gold_diff_ejgl_15", "xp_diff_ejgl_10", "cs_diff_ejgl_10")


def timeline_metrics(timeline: dict, jungler_pids: list[int]) -> dict[int, dict]:
    """Morts par phase + écarts @10/@15 entre les deux junglers d'une game."""
    frames = (timeline.get("info") or {}).get("frames") or []
    out: dict[int, dict] = {
        pid: {"deaths_pre15": 0, "deaths_post25": 0} for pid in jungler_pids
    }
    for fr in frames:
        for ev in fr.get("events") or []:
            victim = ev.get("victimId")
            if ev.get("type") == "CHAMPION_KILL" and victim in out:
                minute = ev.get("timestamp", 0) // 60_000
                if minute < 15:
                    out[victim]["deaths_pre15"] += 1
                elif minute >= 25:
                    out[victim]["deaths_post25"] += 1
    if len(jungler_pids) == 2:
        a, b = jungler_pids
        for idx in (10, 15):
            if len(frames) <= idx:
                continue
            pf = frames[idx].get("participantFrames") or {}
            fa, fb = pf.get(str(a)), pf.get(str(b))
            if not fa or not fb:
                continue
            gold = fa.get("totalGold", 0) - fb.get("totalGold", 0)
            out[a][f"gold_diff_ejgl_{idx}"] = gold
            out[b][f"gold_diff_ejgl_{idx}"] = -gold
            if idx == 10:
                xp = fa.get("xp", 0) - fb.get("xp", 0)
                cs_a = fa.get("minionsKilled", 0) + fa.get("jungleMinionsKilled", 0)
                cs_b = fb.get("minionsKilled", 0) + fb.get("jungleMinionsKilled", 0)
                out[a]["xp_diff_ejgl_10"] = xp
                out[b]["xp_diff_ejgl_10"] = -xp
                out[a]["cs_diff_ejgl_10"] = cs_a - cs_b
                out[b]["cs_diff_ejgl_10"] = cs_b - cs_a
    return out


def backfill_timelines(
    conn: sqlite3.Connection,
    client: RiotClient,
    *,
    limit: int = 400,
    log: Callable[[str], None] = print,
) -> int:
    """Complète les métriques timeline des games bench qui n'en ont pas encore."""
    todo = conn.execute(
        """SELECT match_id, GROUP_CONCAT(participant_id) pids FROM bench_games
           WHERE deaths_pre15 IS NULL GROUP BY match_id LIMIT ?""",
        (limit,),
    ).fetchall()
    if not todo:
        return 0
    log(f"Complément timelines : {len(todo)} game(s) à enrichir...")
    n = 0
    for i, r in enumerate(todo, 1):
        pids = [int(x) for x in r["pids"].split(",")]
        try:
            timeline = client.timeline(r["match_id"])
        except NotFoundError:
            # timeline indisponible : marquer 0 morts serait mentir -> on laisse NULL
            continue
        metrics = timeline_metrics(timeline, pids)
        with conn:
            for pid, m in metrics.items():
                conn.execute(
                    "UPDATE bench_games SET "
                    + ", ".join(f"{c} = :{c}" for c in m)
                    + " WHERE match_id = :mid AND participant_id = :pid",
                    {**m, "mid": r["match_id"], "pid": pid},
                )
        n += 1
        if i % 50 == 0:
            log(f"  {i}/{len(todo)}")
    return n
