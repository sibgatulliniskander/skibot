"""Dossier de faits : la fiche déterministe d'une game, seule source de l'auditor.

Chaque fait est numéroté (F1, F2...) et porte sa provenance. Le LLM ne reçoit
QUE ce dossier ; le vérificateur (audit.py) rejette toute citation hors dossier.
Un fait absent (NULL) n'apparaît pas — jamais de valeur inventée.
"""

from __future__ import annotations

import sqlite3
from bisect import bisect_right
from datetime import UTC, datetime

import pandas as pd

P_EVENT = "prouvé — events timeline"
P_FRAME = "prouvé — frames timeline"
P_CHAL = "prouvé — challenges Riot"
P_DTO = "prouvé — données de match Riot"
P_LOCAL = "prouvé — base locale (sessions)"
P_DD = "prouvé — Data Dragon (tags/portées)"
I_DD = "inféré — approximation Data Dragon"

MS = 60_000

# Métriques accompagnées d'un repère perso (médianes W/L + percentile de la game)
BASELINE_METRICS = [
    "gold_diff_ejgl_5", "gold_diff_ejgl_10", "gold_diff_ejgl_15",
    "xp_diff_ejgl_10", "cs_diff_ejgl_10", "jungle_cs_before_10",
    "counter_jungle_diff", "scuttle_crabs", "early_gank_kills",
    "deaths_pre15", "kills_pre15", "deaths_post25",
    "kill_participation", "damage_share", "solo_kills",
    "wards_placed", "wards_killed", "control_wards_bought",
    "vision_advantage_vs_ejgl", "pings_total", "on_my_way_pings",
    "plates_diff", "dragons_diff", "barons_diff", "towers_diff",
]
MIN_BASELINE_N = 30


def compute_baselines(conn: sqlite3.Connection) -> dict:
    """Médianes perso (W/L) et distribution par métrique, historique hors remakes."""
    df = pd.read_sql_query(
        "SELECT y_win, " + ", ".join(BASELINE_METRICS)
        + " FROM features WHERE is_remake = 0",
        conn,
    )
    out: dict[str, dict] = {}
    for metric in BASELINE_METRICS:
        s = df[metric].dropna()
        if len(s) < MIN_BASELINE_N:
            continue
        out[metric] = {
            "med_w": float(df.loc[df["y_win"] == 1, metric].median()),
            "med_l": float(df.loc[df["y_win"] == 0, metric].median()),
            "sorted": sorted(float(v) for v in s),
        }
    return out


def build(
    conn: sqlite3.Connection,
    match_id: str,
    *,
    baselines: dict | None = None,
    consigne: dict | None = None,
) -> dict:
    f = conn.execute("SELECT * FROM features WHERE match_id = ?", (match_id,)).fetchone()
    if f is None:
        raise ValueError(f"features manquantes pour {match_id} — lance `skibot features` d'abord")
    m = conn.execute("SELECT * FROM matches WHERE match_id = ?", (match_id,)).fetchone()
    me = conn.execute(
        "SELECT * FROM participants WHERE match_id = ? AND is_me = 1", (match_id,)
    ).fetchone()
    if baselines is None:
        baselines = compute_baselines(conn)

    facts: list[dict] = []

    def ref(col: str) -> str:
        """Repère perso : médianes W/L et percentile de la valeur de cette game."""
        b = baselines.get(col)
        if b is None or f[col] is None:
            return ""
        pct = 100 * bisect_right(b["sorted"], float(f[col])) / len(b["sorted"])
        if col in ("kill_participation", "damage_share"):  # ratios affichés en %
            med_w, med_l = f"{b['med_w']:.0%}", f"{b['med_l']:.0%}"
        else:
            med_w, med_l = f"{b['med_w']:g}", f"{b['med_l']:g}"
        if pct >= 50:
            position = f"plus haut que dans {pct:.0f} % de tes games"
        else:
            position = f"plus bas que dans {100 - pct:.0f} % de tes games"
        return (
            f" · d'habitude : {med_w} quand tu gagnes, {med_l} quand tu perds — "
            f"cette game : {position}"
        )

    def add(text: str, prov: str) -> None:
        facts.append({"id": f"F{len(facts) + 1}", "text": text, "prov": prov})

    def has(col: str) -> bool:
        return f[col] is not None

    # --- consigne active (protocol/consigne.json — absent hors expérimentation)
    if consigne and consigne.get("metric"):
        metric, target = consigne["metric"], consigne.get("target")
        # sqlite3.Row : `in` teste les valeurs, pas les colonnes -> .keys() nécessaire
        value = f[metric] if metric in f.keys() else None  # noqa: SIM118
        etat = "non mesurable sur cette game" if value is None else (
            f"{value:g} (objectif {consigne.get('operator', '>=')} {target})"
        )
        add(
            f"CONSIGNE ACTIVE n°{consigne.get('numero', '?')} : "
            f"« {consigne.get('comportement', '?')} » — métrique {metric} de cette "
            f"game : {etat}",
            P_LOCAL,
        )

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
            add(f"Écart d'or vs jungler adverse à {minute} min : {f[col]:+d}{ref(col)}", P_FRAME)
    if has("xp_diff_ejgl_10"):
        add(f"Écart d'XP vs jungler adverse à 10 min : {f['xp_diff_ejgl_10']:+d}{ref('xp_diff_ejgl_10')}", P_FRAME)
    if has("cs_diff_ejgl_10"):
        add(f"Écart de CS (sbires + jungle) vs jungler adverse à 10 min : "
            f"{f['cs_diff_ejgl_10']:+d}{ref('cs_diff_ejgl_10')}", P_FRAME)
    if has("jungle_cs_before_10"):
        add(f"CS jungle avant 10 min : {f['jungle_cs_before_10']:.0f}{ref('jungle_cs_before_10')}", P_CHAL)
    if has("counter_jungle_diff"):
        add(f"Différentiel de counter-jungle : {f['counter_jungle_diff']:+.0f} CS "
            f"(positif = j'ai pris plus dans sa jungle que lui dans la mienne){ref('counter_jungle_diff')}", P_CHAL)
    if has("scuttle_crabs"):
        add(f"Scuttles prises : {f['scuttle_crabs']} (première scuttle sécurisée : "
            f"{'oui' if f['initial_crab_secured'] else 'non'})"
            if has("initial_crab_secured") else f"Scuttles prises : {f['scuttle_crabs']}",
            P_CHAL)
    if has("early_gank_kills"):
        add(f"Kills sur les laners adverses en early en tant que jungler : "
            f"{f['early_gank_kills']}{ref('early_gank_kills')}", P_CHAL)
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
        add(f"Morts avant 15 min : {f['deaths_pre15']}{detail}{ref('deaths_pre15')}", P_EVENT)
    if has("kills_pre15"):
        add(f"Kills avant 15 min : {f['kills_pre15']} · assists : "
            f"{f['assists_pre15'] if has('assists_pre15') else '?'}{ref('kills_pre15')}", P_EVENT)
    if has("deaths_post25"):
        detail = ""
        late = [t for t in death_minutes if t >= 25]
        if late:
            detail = " (aux minutes " + ", ".join(str(t) for t in late) + ")"
        add(f"Morts après 25 min : {f['deaths_post25']}{detail}{ref('deaths_post25')}", P_EVENT)
    if me is not None:
        add(f"Score final : {me['kills']}/{me['deaths']}/{me['assists']}", P_DTO)
    if has("kill_participation"):
        add(f"Participation aux kills de l'équipe : {f['kill_participation']:.0%}{ref('kill_participation')}", P_DTO)
    if has("damage_share"):
        add(f"Part des dégâts aux champions de l'équipe : {f['damage_share']:.0%}{ref('damage_share')}", P_DTO)
    if has("solo_kills"):
        add(f"Solo kills : {f['solo_kills']}{ref('solo_kills')}", P_CHAL)

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
        add(f"Plates — avance de mon équipe sur l'adversaire : {f['plates_diff']:+d}{ref('plates_diff')}", P_EVENT)
    if has("dragons_diff"):
        add(f"Dragons — avance de mon équipe : {f['dragons_diff']:+d}{ref('dragons_diff')}", P_EVENT)
    if has("soul_team"):
        add(f"Âme draconique : {'mon équipe' if f['soul_team'] else 'équipe adverse'}", P_EVENT)
    if has("barons_diff"):
        add(f"Barons — avance de mon équipe : {f['barons_diff']:+d}{ref('barons_diff')}", P_EVENT)
    if has("atakhan_team"):
        add(f"Atakhan : {'mon équipe' if f['atakhan_team'] else 'équipe adverse'}", P_EVENT)
    if has("towers_diff"):
        add(f"Tours — avance de mon équipe : {f['towers_diff']:+d}{ref('towers_diff')}", P_EVENT)
    if has("epic_monster_steals"):
        add(f"Vols de monstres épiques par moi : {f['epic_monster_steals']}", P_CHAL)
    if has("y2_team_gold_diff_15"):
        add(f"Écart d'or entre équipes à 15 min : {f['y2_team_gold_diff_15']:+d}", P_FRAME)

    # --- vision
    if has("wards_placed"):
        add(f"Wards posées par moi : {f['wards_placed']} · wards détruites : "
            f"{f['wards_killed'] if has('wards_killed') else '?'} "
            f"(les POSITIONS de wards ne sont pas mesurables){ref('wards_placed')}", P_EVENT)
    if has("control_wards_bought"):
        add(f"Pink wards achetées : {f['control_wards_bought']}{ref('control_wards_bought')}", P_EVENT)
    if has("vision_advantage_vs_ejgl"):
        add(f"Avantage de score de vision vs jungler adverse : "
            f"{f['vision_advantage_vs_ejgl']:+.2f}{ref('vision_advantage_vs_ejgl')}", P_CHAL)

    # --- communication & fin de game
    if has("pings_total"):
        add(f"Pings émis : {f['pings_total']} au total, dont "
            f"{f['on_my_way_pings'] if has('on_my_way_pings') else '?'} « on my way »{ref('pings_total')}", P_DTO)
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
        "DOSSIER DE FAITS (seule source autorisée). Les repères « d'habitude »",
        "comparent cette game à l'historique complet du joueur, hors remakes",
        "[prouvé — base locale] :",
    ]
    lines.extend(f"{f['id']}. {f['text']} [{f['prov']}]" for f in d["facts"])
    return "\n".join(lines)
