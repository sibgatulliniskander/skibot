"""Typage des variables, tests statistiques du screening et correction FDR.

- Continue : Mann-Whitney U + delta de Cliff (aucune hypothèse de normalité)
- Binaire : Fisher exact + écart de win rate en points
- Catégorielle : chi2 (niveaux < MIN_LEVEL_N regroupés en "(autres)")
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from scipy import stats as sp

CONTINUOUS = "continue"
BINARY = "binaire"
CATEGORICAL = "catégorielle"
LEVIER = "levier"
MECANISME = "mécanisme"

MIN_GROUP_N = 10  # effectif minimal par groupe (W/L, ou valeur 0/1)

# Libellés français des variables (affichage dashboard)
FR_LABELS = {
    "session_game_index": "Position de la game dans la session",
    "games_played_today": "Games déjà jouées dans la journée",
    "minutes_since_prev_game": "Pause avant la game",
    "prev_game_result": "Résultat de la game précédente",
    "current_streak": "Série en cours",
    "hour_bin": "Moment de la journée",
    "day_of_week": "Jour de la semaine",
    "session_length_so_far_min": "Durée de session déjà écoulée",
    "my_champion": "Mon champion",
    "my_champ_recent_games": "Familiarité récente avec le champion",
    "my_champ_recent_wr": "Win rate récent sur le champion",
    "enemy_jungler_champion": "Jungler adverse",
    "side": "Côté de la carte",
    "i_am_autofilled": "Autofill",
    "ally_tank_count": "Tanks alliés",
    "enemy_tank_count": "Tanks ennemis",
    "ally_ranged_count": "Champions à distance alliés",
    "enemy_ranged_count": "Champions à distance ennemis",
    "ally_ap_ratio": "Profil AP de mon équipe",
    "enemy_ap_ratio": "Profil AP adverse",
    "gold_diff_ejgl_5": "Avance d'or sur le jungler adverse (5 min)",
    "gold_diff_ejgl_10": "Avance d'or sur le jungler adverse (10 min)",
    "gold_diff_ejgl_15": "Avance d'or sur le jungler adverse (15 min)",
    "xp_diff_ejgl_10": "Avance d'XP sur le jungler adverse (10 min)",
    "cs_diff_ejgl_10": "Avance de CS sur le jungler adverse (10 min)",
    "kills_pre15": "Mes kills avant 15 min",
    "deaths_pre15": "Mes morts avant 15 min",
    "assists_pre15": "Mes assists avant 15 min",
    "deaths_pre8": "Mes morts avant 8 min",
    "first_blood_team": "First blood pour mon équipe",
    "first_dragon_team": "Premier dragon pour mon équipe",
    "grubs_team": "Grubs prises par mon équipe",
    "herald_team": "Hérauts pris par mon équipe",
    "plates_diff": "Plates : avance de mon équipe",
    "dragons_diff": "Dragons : avance de mon équipe",
    "soul_team": "Âme draconique pour mon équipe",
    "barons_diff": "Barons : avance de mon équipe",
    "atakhan_team": "Atakhan pour mon équipe",
    "towers_diff": "Tours : avance de mon équipe",
    "deaths_post25": "Mes morts après 25 min",
    "kill_participation": "Ma participation aux kills",
    "damage_share": "Ma part des dégâts de l'équipe",
    "wards_placed": "Wards que je pose",
    "wards_killed": "Wards ennemies que je détruis",
    "control_wards_bought": "Pink wards que j'achète",
    "jungle_cs_before_10": "Mes CS jungle avant 10 min",
    "counter_jungle_diff": "Counter-jungle : bilan des CS volés",
    "scuttle_crabs": "Scuttles que je prends",
    "initial_crab_secured": "Première scuttle sécurisée",
    "early_gank_kills": "Mes kills de gank en early",
    "early_jungle_duel_kills": "Duels jungle gagnés en early",
    "solo_kills": "Mes solo kills",
    "epic_monster_steals": "Mes vols d'objectifs",
    "vision_advantage_vs_ejgl": "Vision : mon avance sur le jungler adverse",
    "pings_total": "Mes pings émis",
    "on_my_way_pings": "Mes pings « on my way »",
}
MIN_LEVEL_N = 20  # effectif minimal d'un niveau catégoriel

# Précisions de périmètre (affichées sous la carte) : QUI est mesuré, et comment
FR_DESC = {
    "plates_diff": "Plates détruites par mon équipe moins celles détruites par l'adversaire. Négatif = ils en ont pris plus que nous.",
    "towers_diff": "Tours détruites par mon équipe moins tours perdues.",
    "dragons_diff": "Dragons pris par mon équipe moins ceux pris par l'adversaire.",
    "barons_diff": "Barons pris par mon équipe moins ceux pris par l'adversaire.",
    "grubs_team": "Prises par n'importe qui dans mon équipe, pas forcément par moi.",
    "herald_team": "Pris par n'importe qui dans mon équipe.",
    "first_dragon_team": "Sécurisé par mon équipe, pas forcément par moi.",
    "first_blood_team": "Réalisé par n'importe qui dans mon équipe.",
    "atakhan_team": "Pris par mon équipe.",
    "soul_team": "Obtenue par mon équipe.",
    "counter_jungle_diff": "CS que je prends dans sa jungle moins CS qu'il prend dans la mienne.",
    "vision_advantage_vs_ejgl": "Mon score de vision moins celui du jungler adverse (compteur Riot).",
    "kill_participation": "Part des kills de mon équipe où je suis impliqué (kill ou assist).",
    "damage_share": "Ma part des dégâts aux champions infligés par mon équipe entière.",
    "gold_diff_ejgl_5": "Mon or total moins le sien, à la 5e minute.",
    "gold_diff_ejgl_10": "Mon or total moins le sien, à la 10e minute.",
    "gold_diff_ejgl_15": "Mon or total moins le sien, à la 15e minute.",
    "xp_diff_ejgl_10": "Mon XP moins le sien, à la 10e minute.",
    "cs_diff_ejgl_10": "Mes CS (sbires + jungle) moins les siens, à la 10e minute.",
}


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    kind: str
    category: str  # A..F
    tag: str       # levier = actionnable par une consigne ; mécanisme = descriptif
    note: str = ""


FEATURES: list[FeatureSpec] = [
    # A. contexte de session
    FeatureSpec("session_game_index", CONTINUOUS, "A", LEVIER),
    FeatureSpec("games_played_today", CONTINUOUS, "A", LEVIER),
    FeatureSpec("minutes_since_prev_game", CONTINUOUS, "A", LEVIER),
    FeatureSpec("prev_game_result", CATEGORICAL, "A", LEVIER),
    FeatureSpec("current_streak", CONTINUOUS, "A", LEVIER),
    FeatureSpec("hour_bin", CATEGORICAL, "A", LEVIER),
    FeatureSpec("day_of_week", CATEGORICAL, "A", LEVIER),
    FeatureSpec("session_length_so_far_min", CONTINUOUS, "A", LEVIER),
    # B. draft & compo
    FeatureSpec("my_champion", CATEGORICAL, "B", LEVIER),
    FeatureSpec("my_champ_recent_games", CONTINUOUS, "B", LEVIER),
    FeatureSpec("my_champ_recent_wr", CONTINUOUS, "B", LEVIER,
                note="prudence : bruit à faible effectif, corrèle mécaniquement avec les streaks"),
    FeatureSpec("enemy_jungler_champion", CATEGORICAL, "B", LEVIER),
    FeatureSpec("side", CATEGORICAL, "B", MECANISME),
    FeatureSpec("i_am_autofilled", BINARY, "B", LEVIER),
    FeatureSpec("ally_tank_count", CONTINUOUS, "B", LEVIER),
    FeatureSpec("enemy_tank_count", CONTINUOUS, "B", LEVIER),
    FeatureSpec("ally_ranged_count", CONTINUOUS, "B", LEVIER),
    FeatureSpec("enemy_ranged_count", CONTINUOUS, "B", LEVIER),
    FeatureSpec("ally_ap_ratio", CONTINUOUS, "B", LEVIER, note="approximation Data Dragon"),
    FeatureSpec("enemy_ap_ratio", CONTINUOUS, "B", LEVIER, note="approximation Data Dragon"),
    # C. early game (< 15 min)
    FeatureSpec("gold_diff_ejgl_5", CONTINUOUS, "C", MECANISME),
    FeatureSpec("gold_diff_ejgl_10", CONTINUOUS, "C", MECANISME),
    FeatureSpec("gold_diff_ejgl_15", CONTINUOUS, "C", MECANISME),
    FeatureSpec("xp_diff_ejgl_10", CONTINUOUS, "C", MECANISME),
    FeatureSpec("cs_diff_ejgl_10", CONTINUOUS, "C", MECANISME),
    FeatureSpec("kills_pre15", CONTINUOUS, "C", MECANISME),
    FeatureSpec("deaths_pre15", CONTINUOUS, "C", MECANISME),
    FeatureSpec("assists_pre15", CONTINUOUS, "C", MECANISME),
    FeatureSpec("deaths_pre8", CONTINUOUS, "C", MECANISME),
    FeatureSpec("first_blood_team", BINARY, "C", MECANISME),
    FeatureSpec("first_dragon_team", BINARY, "C", MECANISME),
    FeatureSpec("grubs_team", CONTINUOUS, "C", MECANISME),
    FeatureSpec("herald_team", CONTINUOUS, "C", MECANISME),
    FeatureSpec("plates_diff", CONTINUOUS, "C", MECANISME),
    # D. mid/late & objectifs
    FeatureSpec("dragons_diff", CONTINUOUS, "D", MECANISME),
    FeatureSpec("soul_team", BINARY, "D", MECANISME),
    FeatureSpec("barons_diff", CONTINUOUS, "D", MECANISME),
    FeatureSpec("atakhan_team", BINARY, "D", MECANISME),
    FeatureSpec("towers_diff", CONTINUOUS, "D", MECANISME),
    FeatureSpec("deaths_post25", CONTINUOUS, "D", MECANISME),
    FeatureSpec("kill_participation", CONTINUOUS, "D", MECANISME),
    FeatureSpec("damage_share", CONTINUOUS, "D", MECANISME),
    # E. vision & économie (comportements contrôlables)
    FeatureSpec("wards_placed", CONTINUOUS, "E", LEVIER),
    FeatureSpec("wards_killed", CONTINUOUS, "E", LEVIER),
    FeatureSpec("control_wards_bought", CONTINUOUS, "E", LEVIER),
    # F. challenges Riot
    FeatureSpec("jungle_cs_before_10", CONTINUOUS, "F", LEVIER),
    FeatureSpec("counter_jungle_diff", CONTINUOUS, "F", LEVIER),
    FeatureSpec("scuttle_crabs", CONTINUOUS, "F", LEVIER),
    FeatureSpec("initial_crab_secured", CONTINUOUS, "F", LEVIER),
    FeatureSpec("early_gank_kills", CONTINUOUS, "F", LEVIER),
    FeatureSpec("early_jungle_duel_kills", CONTINUOUS, "F", LEVIER),
    FeatureSpec("solo_kills", CONTINUOUS, "F", MECANISME),
    FeatureSpec("epic_monster_steals", CONTINUOUS, "F", MECANISME),
    FeatureSpec("vision_advantage_vs_ejgl", CONTINUOUS, "F", LEVIER),
    FeatureSpec("pings_total", CONTINUOUS, "F", LEVIER),
    FeatureSpec("on_my_way_pings", CONTINUOUS, "F", LEVIER),
]


def test_feature(df: pd.DataFrame, spec: FeatureSpec) -> dict | None:
    """Teste une variable contre y_win. None si effectifs insuffisants."""
    sub = df[[spec.name, "y_win"]].dropna()
    if sub.empty:
        return None
    if spec.kind == CONTINUOUS:
        return _test_continuous(sub, spec)
    if spec.kind == BINARY:
        return _test_binary(sub, spec)
    return _test_categorical(sub, spec)


def benjamini_hochberg(pvals: list[float]) -> list[float]:
    """q-values BH : q_i = min_{j >= i} (p_(j) * m / j), dans l'ordre d'entrée."""
    m = len(pvals)
    idx = sorted(range(m), key=lambda i: pvals[i])
    q = [0.0] * m
    prev = 1.0
    for rank in range(m, 0, -1):
        i = idx[rank - 1]
        prev = min(prev, pvals[i] * m / rank)
        q[i] = prev
    return q


def _base(spec: FeatureSpec, n: int) -> dict:
    return {
        "feature": spec.name, "kind": spec.kind, "category": spec.category,
        "tag": spec.tag, "note": spec.note, "n": n,
    }


def _test_continuous(sub: pd.DataFrame, spec: FeatureSpec) -> dict | None:
    wins = sub.loc[sub["y_win"] == 1, spec.name].astype(float)
    losses = sub.loc[sub["y_win"] == 0, spec.name].astype(float)
    if len(wins) < MIN_GROUP_N or len(losses) < MIN_GROUP_N:
        return None
    u, p = sp.mannwhitneyu(wins, losses, alternative="two-sided")
    delta = 2 * u / (len(wins) * len(losses)) - 1  # delta de Cliff
    r = _base(spec, len(sub))
    r.update({
        "p": float(p),
        "direction": 1 if delta > 0 else -1,
        "effect_abs": abs(delta),
        "med_w": float(wins.median()),
        "med_l": float(losses.median()),
        "effect_label": (
            f"δ={delta:+.2f} (méd. W {wins.median():g} vs L {losses.median():g})"
        ),
    })
    return r


def _test_binary(sub: pd.DataFrame, spec: FeatureSpec) -> dict | None:
    v = sub[spec.name].astype(int)
    y = sub["y_win"].astype(int)
    n1, n0 = int((v == 1).sum()), int((v == 0).sum())
    if n1 < MIN_GROUP_N or n0 < MIN_GROUP_N:
        return None
    table = [
        [int(((v == 1) & (y == 1)).sum()), int(((v == 1) & (y == 0)).sum())],
        [int(((v == 0) & (y == 1)).sum()), int(((v == 0) & (y == 0)).sum())],
    ]
    _odds, p = sp.fisher_exact(table)
    wr1 = table[0][0] / n1 * 100
    wr0 = table[1][0] / n0 * 100
    diff = wr1 - wr0
    r = _base(spec, len(sub))
    r.update({
        "p": float(p),
        "direction": 1 if diff > 0 else -1,
        "effect_abs": abs(diff) / 100,
        "wr1": wr1,
        "wr0": wr0,
        "effect_label": f"WR {wr1:.0f}% si oui vs {wr0:.0f}% si non ({diff:+.0f} pts)",
    })
    return r


def _test_categorical(sub: pd.DataFrame, spec: FeatureSpec) -> dict | None:
    v = sub[spec.name].astype(str)
    counts = v.value_counts()
    keep = counts[counts >= MIN_LEVEL_N].index
    v = v.where(v.isin(keep), "(autres)")
    if v.nunique() < 2 or len(sub) < 4 * MIN_GROUP_N:
        return None
    tab = pd.crosstab(v, sub["y_win"])
    if tab.shape[1] < 2:
        return None
    _chi2, p, _dof, _exp = sp.chi2_contingency(tab)
    overall = sub["y_win"].mean() * 100
    levels = []
    for lev in tab.index:
        n = int(tab.loc[lev].sum())
        wr = tab.loc[lev].get(1, 0) / n * 100
        levels.append({"level": str(lev), "n": n, "wr": wr})
    levels.sort(key=lambda x: x["wr"], reverse=True)
    extreme = max(levels, key=lambda x: abs(x["wr"] - overall))
    r = _base(spec, len(sub))
    r.update({
        "p": float(p),
        "direction": 0,  # pas de direction unique pour une catégorielle
        "effect_abs": abs(extreme["wr"] - overall) / 100,
        "effect_label": (
            f"écart max : {extreme['level']} {extreme['wr']:.0f}% "
            f"(n={extreme['n']}, moyenne {overall:.0f}%)"
        ),
        "levels": levels,
    })
    return r
