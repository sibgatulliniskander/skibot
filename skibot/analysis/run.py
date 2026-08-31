"""Orchestration : screening sur l'exploration, confirmation indépendante, rapport.

Règle absolue : aucune conclusion sur l'échantillon d'exploration seul.
Un effet est [exploratoire] tant qu'il n'a pas répliqué (p <= alpha, même
direction) sur l'échantillon de confirmation.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

import pandas as pd

from ..config import PROJECT_ROOT
from . import report, split, stats

FDR_Q = 0.10
ALPHA_CONFIRM = 0.05
DAYS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def _hour_bin(h) -> str | None:
    if pd.isna(h):
        return None
    h = int(h)
    if 6 <= h < 12:
        return "matin"
    if 12 <= h < 18:
        return "après-midi"
    if 18 <= h < 24:
        return "soirée"
    return "nuit"


def load_dataset(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query(
        """SELECT f.*, s.split FROM features f
           JOIN analysis_split s USING (match_id)
           WHERE f.is_remake = 0""",
        conn,
    )
    df["hour_bin"] = df["hour_of_day"].map(_hour_bin)
    df["day_of_week"] = df["day_of_week"].map(
        lambda d: DAYS_FR[int(d)] if pd.notna(d) else None
    )
    return df


def analyze(
    conn: sqlite3.Connection,
    *,
    out_dir: Path | None = None,
    log: Callable[[str], None] = print,
) -> dict:
    split_info = split.ensure_split(conn)
    state = "figé réutilisé" if split_info.get("frozen") else "créé (seed 42)"
    log(
        f"Split {state} : {split_info.get('explore', 0)} exploration / "
        f"{split_info.get('confirm', 0)} confirmation"
    )
    df = load_dataset(conn)
    explore = df[df["split"] == "explore"]
    confirm = df[df["split"] == "confirm"]
    n_prospective = conn.execute(
        """SELECT COUNT(*) c FROM features f
           LEFT JOIN analysis_split s USING (match_id)
           WHERE f.is_remake = 0 AND s.match_id IS NULL"""
    ).fetchone()["c"]

    specs = {s.name: s for s in stats.FEATURES}
    results: list[dict] = []
    skipped: list[str] = []
    for spec in stats.FEATURES:
        r = stats.test_feature(explore, spec)
        if r is None:
            skipped.append(spec.name)
            continue
        results.append(r)
    if skipped:
        log(f"Non testées (effectifs insuffisants) : {', '.join(skipped)}")

    for r, q in zip(results, stats.benjamini_hochberg([r["p"] for r in results])):
        r["q"] = q
        r["retained"] = q <= FDR_Q

    for r in sorted((r for r in results if r["retained"]), key=lambda x: x["q"]):
        c = stats.test_feature(confirm, specs[r["feature"]])
        r["confirm"] = c
        if c is None:
            r["verdict"] = "inconfirmable (effectifs)"
        elif c["p"] <= ALPHA_CONFIRM and (
            r["direction"] == 0 or c["direction"] == r["direction"]
        ):
            r["verdict"] = "confirmé"
        else:
            r["verdict"] = "non répliqué"

    out_dir = out_dir or PROJECT_ROOT / "reports"
    path = report.write(
        out_dir,
        results,
        {
            "n_explore": len(explore),
            "n_confirm": len(confirm),
            "n_prospective": n_prospective,
            "fdr_q": FDR_Q,
            "alpha": ALPHA_CONFIRM,
        },
    )
    retained = [r for r in results if r["retained"]]
    confirmed = [r for r in retained if r.get("verdict") == "confirmé"]
    return {
        "tested": len(results),
        "retained": len(retained),
        "confirmed": len(confirmed),
        "report": path,
        "results": results,
    }
