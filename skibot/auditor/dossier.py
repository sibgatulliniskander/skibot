"""Dossier de faits : la fiche déterministe d'une game, seule source de l'auditor.

Chaque fait est numéroté (F1, F2...) et porte sa provenance. Le LLM ne reçoit
QUE ce dossier ; le vérificateur (audit.py) rejette toute citation hors dossier.
Un fait absent (NULL) n'apparaît pas — jamais de valeur inventée.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

P_EVENT = "prouvé — events timeline"
P_FRAME = "prouvé — frames timeline"
P_CHAL = "prouvé — challenges Riot"
P_DTO = "prouvé — données de match Riot"
P_LOCAL = "prouvé — base locale (sessions)"
P_DD = "prouvé — Data Dragon (tags/portées)"
I_DD = "inféré — approximation Data Dragon"

MS = 60_000


def build(conn: sqlite3.Connection, match_id: str) -> dict:
    f = conn.execute("SELECT * FROM features WHERE match_id = ?", (match_id,)).fetchone()
    if f is None:
        raise ValueError(f"features manquantes pour {match_id} — lance `skibot features` d'abord")
    m = conn.execute("SELECT * FROM matches WHERE match_id = ?", (match_id,)).fetchone()
    me = conn.execute(
        "SELECT * FROM participants WHERE match_id = ? AND is_me = 1", (match_id,)
    ).fetchone()

    facts: list[dict] = []

    def add(text: str, prov: str) -> None:
        facts.append({"id": f"F{len(facts) + 1}", "text": text, "prov": prov})

    def has(col: str) -> bool:
        return f[col] is not None

    # --- contexte de session
    if has("session_game_index"):
        add(f"Game n°{f['session_game_index']} de la session de jeu", P_LOCAL)
    if has("games_played_today"):
        add(f"{f['games_played_today']} game(s) déjà jouée(s) ce jour avant celle-ci", P_LOCAL)
    if has("minutes_since_prev_game"):
        add(f"{f['minutes_since_prev_game']:.0f} min d'écart depuis la game précédente", P_LOCAL)
    if has("current_streak") and f["current_streak"] != 0:
        s = f["current_streak"]
        add(f"Série entrante : {abs(s)} {'victoire(s)' if s > 0 else 'défaite(s)'} consécutive(s)",
            P_LOCAL)

    # --- draft & compo
    if f["i_am_autofilled"]:
        pos = me["team_position"] if me else "?"
        add(f"AUTOFILL : poste joué {pos} au lieu de la jungle", P_DTO)
    if has("ally_tank_count") and has("enemy_tank_count"):
        add(f"Tanks (tag Riot) : {f['ally_tank_count']} allié(s) vs "
            f"{f['enemy_tank_count']} ennemi(s)", P_DD)
    if has("ally_ap_ratio") and has("enemy_ap_ratio"):
        add(f"Profil de dégâts estimé : équipe {f['ally_ap_ratio']:.0%} AP vs "
            f"adversaires {f['enemy_ap_ratio']:.0%} AP", I_DD)

    # --- early game vs jungler adverse
    for minute, col in ((5, "gold_diff_ejgl_5"), (10, "gold_diff_ejgl_10"),
                        (15, "gold_diff_ejgl_15")):
        if has(col):
            add(f"Écart d'or vs jungler adverse à {minute} min : {f[col]:+d}", P_FRAME)
    if has("xp_diff_ejgl_10"):
        add(f"Écart d'XP vs jungler adverse à 10 min : {f['xp_diff_ejgl_10']:+d}", P_FRAME)
    if has("cs_diff_ejgl_10"):
        add(f"Écart de CS (sbires + jungle) vs jungler adverse à 10 min : "
            f"{f['cs_diff_ejgl_10']:+d}", P_FRAME)
    if has("jungle_cs_before_10"):
        add(f"CS jungle avant 10 min : {f['jungle_cs_before_10']:.0f}", P_CHAL)
    if has("counter_jungle_diff"):
        add(f"Différentiel de counter-jungle : {f['counter_jungle_diff']:+.0f} CS "
            f"(positif = j'ai pris plus dans sa jungle que lui dans la mienne)", P_CHAL)
    if has("scuttle_crabs"):
        add(f"Scuttles prises : {f['scuttle_crabs']} (première scuttle sécurisée : "
            f"{'oui' if f['initial_crab_secured'] else 'non'})"
            if has("initial_crab_secured") else f"Scuttles prises : {f['scuttle_crabs']}",
            P_CHAL)
    if has("early_gank_kills"):
        add(f"Kills sur les laners adverses en early en tant que jungler : "
            f"{f['early_gank_kills']}", P_CHAL)
    if has("early_jungle_duel_kills"):
        add(f"Kills sur le jungler adverse dans la jungle en early : "
            f"{f['early_jungle_duel_kills']}", P_CHAL)

    # --- mes kills/morts (avec minutes si la timeline est là)
    death_minutes = _death_minutes(conn, match_id, me)
    if has("deaths_pre15"):
        detail = ""
        early = [t for t in death_minutes if t < 15]
        if early:
            detail = " (aux minutes " + ", ".join(str(t) for t in early) + ")"
        add(f"Morts avant 15 min : {f['deaths_pre15']}{detail}", P_EVENT)
    if has("kills_pre15"):
        add(f"Kills avant 15 min : {f['kills_pre15']} · assists : "
            f"{f['assists_pre15'] if has('assists_pre15') else '?'}", P_EVENT)
    if has("deaths_post25"):
        detail = ""
        late = [t for t in death_minutes if t >= 25]
        if late:
            detail = " (aux minutes " + ", ".join(str(t) for t in late) + ")"
        add(f"Morts après 25 min : {f['deaths_post25']}{detail}", P_EVENT)
    if me is not None:
        add(f"Score final : {me['kills']}/{me['deaths']}/{me['assists']}", P_DTO)
    if has("kill_participation"):
        add(f"Participation aux kills de l'équipe : {f['kill_participation']:.0%}", P_DTO)
    if has("damage_share"):
        add(f"Part des dégâts aux champions de l'équipe : {f['damage_share']:.0%}", P_DTO)
    if has("solo_kills"):
        add(f"Solo kills : {f['solo_kills']}", P_CHAL)

    # --- objectifs
    if has("first_blood_team"):
        add(f"First blood : {'mon équipe' if f['first_blood_team'] else 'équipe adverse'}",
            P_EVENT)
    if has("first_dragon_team"):
        add(f"Premier dragon : {'mon équipe' if f['first_dragon_team'] else 'équipe adverse'}",
            P_EVENT)
    if has("grubs_team"):
        add(f"Grubs (Horde du Vide) prises par mon équipe : {f['grubs_team']}", P_EVENT)
    if has("herald_team"):
        add(f"Hérauts pris par mon équipe : {f['herald_team']}", P_EVENT)
    if has("plates_diff"):
        add(f"Différentiel de plates de tourelle : {f['plates_diff']:+d}", P_EVENT)
    if has("dragons_diff"):
        add(f"Différentiel de dragons : {f['dragons_diff']:+d}", P_EVENT)
    if has("soul_team"):
        add(f"Âme draconique : {'mon équipe' if f['soul_team'] else 'équipe adverse'}", P_EVENT)
    if has("barons_diff"):
        add(f"Différentiel de Barons : {f['barons_diff']:+d}", P_EVENT)
    if has("atakhan_team"):
        add(f"Atakhan : {'mon équipe' if f['atakhan_team'] else 'équipe adverse'}", P_EVENT)
    if has("towers_diff"):
        add(f"Différentiel de tours : {f['towers_diff']:+d}", P_EVENT)
    if has("epic_monster_steals"):
        add(f"Vols de monstres épiques par moi : {f['epic_monster_steals']}", P_CHAL)
    if has("y2_team_gold_diff_15"):
        add(f"Écart d'or entre équipes à 15 min : {f['y2_team_gold_diff_15']:+d}", P_FRAME)

    # --- vision
    if has("wards_placed"):
        add(f"Wards posées par moi : {f['wards_placed']} · wards détruites : "
            f"{f['wards_killed'] if has('wards_killed') else '?'} "
            f"(les POSITIONS de wards ne sont pas mesurables)", P_EVENT)
    if has("control_wards_bought"):
        add(f"Pink wards achetées : {f['control_wards_bought']}", P_EVENT)
    if has("vision_advantage_vs_ejgl"):
        add(f"Avantage de score de vision vs jungler adverse : "
            f"{f['vision_advantage_vs_ejgl']:+.2f}", P_CHAL)

    # --- communication & fin de game
    if has("pings_total"):
        add(f"Pings émis : {f['pings_total']} au total, dont "
            f"{f['on_my_way_pings'] if has('on_my_way_pings') else '?'} « on my way »", P_DTO)
    if f["ended_in_surrender"]:
        add("Game terminée par un surrender", P_DTO)

    header = {
        "match_id": match_id,
        "date": datetime.fromtimestamp(m["game_start"] / 1000, tz=UTC)
        .astimezone().strftime("%d/%m/%Y %H:%M"),
        "result": "VICTOIRE" if f["y_win"] else "DÉFAITE",
        "champion": f["my_champion"],
        "vs": f["enemy_jungler_champion"] or "inconnu",
        "side": f["side"],
        "duration_min": m["game_duration_s"] // 60,
        "patch": m["patch"],
    }
    return {"header": header, "facts": facts}


def _death_minutes(conn, match_id, me) -> list[int]:
    if me is None:
        return []
    rows = conn.execute(
        "SELECT timestamp_ms FROM timeline_events "
        "WHERE match_id = ? AND type = 'CHAMPION_KILL' AND victim_id = ? "
        "ORDER BY timestamp_ms",
        (match_id, me["participant_id"]),
    ).fetchall()
    return [r["timestamp_ms"] // MS for r in rows]


def render(d: dict) -> str:
    h = d["header"]
    lines = [
        f"=== GAME {h['match_id']} ===",
        (
            f"{h['date']} — {h['champion']} (jungle, côté {h['side']}) vs {h['vs']} — "
            f"{h['result']} en {h['duration_min']} min (patch {h['patch']})"
        ),
        "",
        "DOSSIER DE FAITS (seule source autorisée) :",
    ]
    lines.extend(f"{f['id']}. {f['text']} [{f['prov']}]" for f in d["facts"])
    return "\n".join(lines)
