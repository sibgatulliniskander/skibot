"""Comparaison de distributions : mes games de l'ère courante vs junglers Diamant+.

Seules les métriques dont la SOURCE est identique des deux côtés (mêmes
compteurs Riot) sont comparées. Un écart de distribution est un générateur
d'hypothèses — jamais une preuve causale.
"""

from __future__ import annotations

import json
import sqlite3
from bisect import bisect_left, bisect_right
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from ..analysis.run import ERA_START
from ..analysis.stats import FR_LABELS
from ..config import PROJECT_ROOT, account_filter

# Métriques à source strictement identique (challenges / DTO) côté moi et côté bench
COMPARE_METRICS = [
    "jungle_cs_before_10", "counter_jungle_diff", "scuttle_crabs",
    "early_gank_kills", "early_jungle_duel_kills", "solo_kills",
    "epic_monster_steals", "vision_advantage_vs_ejgl",
    "kill_participation", "damage_share", "pings_total", "on_my_way_pings",
    # source timeline, identique des deux côtés (backfill_timelines côté bench)
    "deaths_pre15", "deaths_post25", "gold_diff_ejgl_10", "gold_diff_ejgl_15",
    "xp_diff_ejgl_10", "cs_diff_ejgl_10",
]
MIN_N = 30

# Métriques RELATIVES à l'adversaire direct : chez les Diamant (miroir Diamant
# vs Diamant), leur médiane vaut ~0 par construction. Ma valeur y mesure ma
# domination de MON elo, pas un écart vis-à-vis d'eux.
RELATIVE_METRICS = {
    "gold_diff_ejgl_10", "gold_diff_ejgl_15", "xp_diff_ejgl_10",
    "cs_diff_ejgl_10", "counter_jungle_diff", "vision_advantage_vs_ejgl",
}


def compare(conn: sqlite3.Connection, *, era_start: str = ERA_START) -> dict:
    era_ms = int(pd.Timestamp(era_start).value // 1_000_000)
    cond, params = account_filter("f.account")
    me = pd.read_sql_query(
        "SELECT f.* FROM features f JOIN matches m USING (match_id) "
        f"WHERE f.is_remake = 0 AND m.game_start >= ? AND {cond}",
        conn, params=(era_ms, *params),
    )
    bench = pd.read_sql_query("SELECT * FROM bench_games", conn)
    if bench.empty:
        return {"metrics": [], "n_me": len(me), "n_bench": 0, "era_start": era_start}

    results = []
    for metric in COMPARE_METRICS:
        mine = me[metric].dropna()
        theirs = bench[metric].dropna()
        if len(mine) < MIN_N or len(theirs) < MIN_N:
            continue
        sorted_bench = sorted(float(v) for v in theirs)
        my_med = float(mine.median())
        # rang moyen des ex aequo : une valeur egale a la masse des leurs -> ~50 %
        lo = bisect_left(sorted_bench, my_med)
        hi = bisect_right(sorted_bench, my_med)
        pct = 100 * (lo + hi) / 2 / len(sorted_bench)
        results.append({
            "metric": metric,
            "label": FR_LABELS.get(metric, metric),
            "my_median": my_med,
            "bench_p25": float(theirs.quantile(0.25)),
            "bench_median": float(theirs.median()),
            "bench_p75": float(theirs.quantile(0.75)),
            "my_percentile_in_bench": round(pct, 1),
            "gap": round(abs(pct - 50), 1),  # distance à la médiane Diamant
            "n_me": len(mine),
            "n_bench": len(theirs),
            "relative": metric in RELATIVE_METRICS,
        })
    results.sort(key=lambda r: -r["gap"])
    return {
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "era_start": era_start,
        "n_me": len(me),
        "n_bench_junglers": len(bench),
        "bench_tier": str(bench["tier"].iloc[0]) if len(bench) else None,
        "metrics": results,
    }


def write_latest(result: dict, out_dir: Path | None = None) -> Path:
    out_dir = out_dir or PROJECT_ROOT / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "benchmark_latest.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return path
