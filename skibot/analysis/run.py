"""Orchestration : screening sur l'exploration, confirmation indépendante, rapport.

Règle absolue : aucune conclusion sur l'échantillon d'exploration seul.
Un effet est [exploratoire] tant qu'il n'a pas répliqué (p <= alpha, même
direction) sur l'échantillon de confirmation.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from ..config import PROJECT_ROOT
from . import report, split, stats
from .stats import FR_DESC, FR_LABELS

FDR_Q = 0.10
ALPHA_CONFIRM = 0.05
# Début de "l'ère courante" (process homogène : elo/meta actuels). Révisé en
# revue trimestrielle uniquement. L'historique complet sert aux tendances et
# aux tests de stabilité, jamais seul à choisir une consigne.
ERA_START = "2026-03-01"
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
        """SELECT f.*, s.split, m.game_start FROM features f
           JOIN analysis_split s USING (match_id)
           JOIN matches m USING (match_id)
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
    era_start: str = ERA_START,
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

    # Stabilité temporelle : effet recalculé sur l'ère courante (descriptif —
    # une candidate n'est proposable comme consigne que si elle y tient).
    era_ms = int(pd.Timestamp(era_start).value // 1_000_000)
    era_df = df[df["game_start"] >= era_ms]
    for r in (r for r in results if r["retained"]):
        e = stats.test_feature(era_df, specs[r["feature"]])
        r["era"] = e
        if e is None:
            r["era_label"] = "— (effectifs insuffisants)"
        else:
            same_dir = r["direction"] == 0 or e["direction"] == r["direction"]
            if e["p"] > 0.05 or not same_dir:
                r["era_verdict"] = "instable"
                verdict = "INSTABLE : ne pas en faire une consigne"
            elif e["effect_abs"] < r["effect_abs"] / 2:
                r["era_verdict"] = "affaibli"
                verdict = "AFFAIBLI (effet réduit de moitié ou plus) : prudence"
            else:
                r["era_verdict"] = "stable"
                verdict = "stable"
            r["era_label"] = f"{e['effect_label']}, p={e['p']:.2g} — {verdict}"

    out_dir = out_dir or PROJECT_ROOT / "reports"
    _write_latest_json(out_dir, results, {
        "n_explore": len(explore), "n_confirm": len(confirm),
        "n_prospective": n_prospective, "n_era": len(era_df),
        "era_start": era_start, "fdr_q": FDR_Q, "alpha": ALPHA_CONFIRM,
    })
    path = report.write(
        out_dir,
        results,
        {
            "n_explore": len(explore),
            "n_confirm": len(confirm),
            "n_prospective": n_prospective,
            "n_era": len(era_df),
            "era_start": era_start,
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


def _fmt_value(feature: str, v: float) -> str:
    if feature in ("kill_participation", "damage_share"):
        return f"{v:.0%}"
    r = round(v, 2 if abs(v) < 1 else 1)
    return "0" if r == 0 else f"{r:g}"


def _human(r: dict) -> str | None:
    """Phrase de comparaison en langage courant, pour le dashboard."""
    if "med_w" in r:
        return (
            f"{_fmt_value(r['feature'], r['med_w'])} quand je gagne · "
            f"{_fmt_value(r['feature'], r['med_l'])} quand je perds"
        )
    if "wr1" in r:
        return f"{r['wr1']:.0f} % de victoires quand c'est le cas · {r['wr0']:.0f} % sinon"
    return None


def _strength(r: dict) -> str:
    cuts = (0.4, 0.2, 0.1) if r["kind"] == "binaire" else (0.5, 0.25, 0.12)
    if r["effect_abs"] >= cuts[0]:
        return "effet très fort"
    if r["effect_abs"] >= cuts[1]:
        return "effet fort"
    if r["effect_abs"] >= cuts[2]:
        return "effet net"
    return "effet léger"


def _write_latest_json(out_dir: Path, results: list[dict], meta: dict) -> None:
    """Export structuré du dernier screening, consommé par le dashboard."""
    export = []
    for r in results:
        c = r.get("confirm")
        export.append({
            "feature": r["feature"], "kind": r["kind"], "category": r["category"],
            "tag": r["tag"], "n": r["n"], "p": r["p"], "q": r["q"],
            "retained": r["retained"], "effect_label": r["effect_label"],
            "label": FR_LABELS.get(r["feature"], r["feature"]),
            "desc": FR_DESC.get(r["feature"]),
            "human": _human(r),
            "strength": _strength(r),
            "verdict": r.get("verdict"),
            "confirm_label": c["effect_label"] if c else None,
            "confirm_p": c["p"] if c else None,
            "era_label": r.get("era_label"),
            "era_verdict": r.get("era_verdict"),
            "note": r.get("note", ""),
        })
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "meta": meta,
        "results": export,
    }
    (out_dir / "analyse_latest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )
