"""Requêtes du dashboard — lecture seule, tout vient de SQLite.

Les chiffres affichés publiquement suivent la clause d'honnêteté : WR et KPIs
excluent les remakes, l'ère courante est celle du protocole (règle n°11).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

import pandas as pd

from ..analysis.run import ERA_START

TIERS = ["IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD", "DIAMOND"]
TIERS_FR = {
    "IRON": "Fer", "BRONZE": "Bronze", "SILVER": "Argent", "GOLD": "Or",
    "PLATINUM": "Platine", "EMERALD": "Émeraude", "DIAMOND": "Diamant",
    "MASTER": "Master", "GRANDMASTER": "Grand Maître", "CHALLENGER": "Challenger",
}
DIVISIONS = {"IV": 0, "III": 1, "II": 2, "I": 3}
NEXT_REVIEW = "2026-12-01"
TARGET = "MASTER (fin 2027)"
MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
             "août", "septembre", "octobre", "novembre", "décembre"]


def _month_year(iso: str) -> str:
    d = datetime.fromisoformat(iso)
    return f"{MONTHS_FR[d.month - 1]} {d.year}"


def lp_absolute(tier: str, division: str, lp: int) -> int:
    """LP cumulés depuis Iron IV 0 LP (1 division = 100 LP, 1 tier = 400)."""
    if tier in ("MASTER", "GRANDMASTER", "CHALLENGER"):
        return len(TIERS) * 400 + lp
    return TIERS.index(tier) * 400 + DIVISIONS[division] * 100 + lp


def tier_ticks() -> list[dict]:
    """Frontières de tiers pour l'axe Y du graphe LP."""
    return [{"value": i * 400, "label": t.capitalize()} for i, t in enumerate(TIERS)] + [
        {"value": len(TIERS) * 400, "label": "Master"}
    ]


def _era_ms() -> int:
    return int(datetime.fromisoformat(ERA_START).replace(tzinfo=UTC).timestamp() * 1000)


def summary(conn: sqlite3.Connection) -> dict:
    rank = conn.execute(
        "SELECT * FROM rank_snapshots ORDER BY snapshot_id DESC LIMIT 1"
    ).fetchone()
    era = conn.execute(
        """SELECT COUNT(*) n, COALESCE(SUM(y_win), 0) w FROM features f
           JOIN matches m USING (match_id)
           WHERE f.is_remake = 0 AND m.game_start >= ?""",
        (_era_ms(),),
    ).fetchone()
    prospective = conn.execute(
        """SELECT COUNT(*) c FROM features f
           LEFT JOIN analysis_split s USING (match_id)
           WHERE f.is_remake = 0 AND s.match_id IS NULL"""
    ).fetchone()["c"]
    total = conn.execute(
        "SELECT COUNT(*) c FROM features WHERE is_remake = 0"
    ).fetchone()["c"]
    last = conn.execute("SELECT MAX(game_start) ts FROM matches").fetchone()["ts"]
    days_to_review = (
        datetime.fromisoformat(NEXT_REVIEW).replace(tzinfo=UTC) - datetime.now(UTC)
    ).days
    next_tier, lp_to_next = None, None
    if rank and rank["tier"] in TIERS:
        idx = TIERS.index(rank["tier"])
        boundary = (idx + 1) * 400
        lp_to_next = boundary - lp_absolute(rank["tier"], rank["division"], rank["lp"])
        next_tier = TIERS_FR[TIERS[idx + 1]] if idx + 1 < len(TIERS) else "Master"
    return {
        "rank": (
            f"{TIERS_FR.get(rank['tier'], rank['tier'])} {rank['division']} · {rank['lp']} LP"
            if rank else "inconnu"
        ),
        "rank_wl": f"{rank['wins']}W / {rank['losses']}L" if rank else "",
        "target": TARGET,
        "games_total": total,
        "era_start": ERA_START,
        "era_human": _month_year(ERA_START),
        "next_tier": next_tier,
        "lp_to_next": lp_to_next,
        "era_games": era["n"],
        "era_wr": round(100 * era["w"] / era["n"], 1) if era["n"] else None,
        "prospective": prospective,
        "next_review": NEXT_REVIEW,
        "days_to_review": max(days_to_review, 0),
        "last_game": (
            datetime.fromtimestamp(last / 1000, tz=UTC).astimezone().strftime("%d/%m/%Y %H:%M")
            if last else "—"
        ),
    }


def lp_history(conn: sqlite3.Connection) -> list[dict]:
    """Un point par snapshot (dédoublonné par heure) : la courbe publique."""
    rows = conn.execute(
        "SELECT taken_at, tier, division, lp FROM rank_snapshots ORDER BY snapshot_id"
    ).fetchall()
    out, seen = [], set()
    for r in rows:
        key = r["taken_at"][:13]  # 1 point max par heure
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "t": r["taken_at"],
            "lp": lp_absolute(r["tier"], r["division"], r["lp"]),
            "label": f"{TIERS_FR.get(r['tier'], r['tier'])} {r['division']} {r['lp']} LP",
        })
    return out


def weekly_wr(conn: sqlite3.Connection, weeks: int = 16) -> list[dict]:
    df = pd.read_sql_query(
        """SELECT m.game_start, f.y_win FROM features f
           JOIN matches m USING (match_id) WHERE f.is_remake = 0""",
        conn,
    )
    if df.empty:
        return []
    df["week"] = (
        pd.to_datetime(df["game_start"], unit="ms")
        .dt.to_period("W").dt.start_time.dt.strftime("%d/%m")
    )
    keys = df.drop_duplicates("week").sort_values("game_start")["week"].tolist()[-weeks:]
    g = df.groupby("week").agg(n=("y_win", "size"), w=("y_win", "sum"))
    return [
        {"week": k, "n": int(g.loc[k, "n"]), "wr": round(100 * g.loc[k, "w"] / g.loc[k, "n"], 1)}
        for k in keys
    ]


def levier_trends(conn: sqlite3.Connection, window: int = 15, games: int = 150) -> dict:
    """Médianes glissantes des leviers candidats (suivi interne, pas un verdict)."""
    df = pd.read_sql_query(
        """SELECT m.game_start, f.on_my_way_pings, f.vision_advantage_vs_ejgl
           FROM features f JOIN matches m USING (match_id)
           WHERE f.is_remake = 0 ORDER BY m.game_start""",
        conn,
    ).tail(games)
    if df.empty:
        return {"labels": [], "omw": [], "vision": []}
    labels = pd.to_datetime(df["game_start"], unit="ms").dt.strftime("%d/%m").tolist()
    roll = lambda s: [
        None if pd.isna(v) else round(float(v), 3)
        for v in s.rolling(window, min_periods=5).median()
    ]
    return {
        "labels": labels,
        "omw": roll(df["on_my_way_pings"]),
        "vision": roll(df["vision_advantage_vs_ejgl"]),
    }


def recent_games(conn: sqlite3.Connection, n: int = 20) -> list[dict]:
    rows = conn.execute(
        """SELECT m.game_start, m.game_duration_s, f.y_win, f.my_champion,
                  f.enemy_jungler_champion, f.gold_diff_ejgl_15, f.session_game_index,
                  f.on_my_way_pings
           FROM features f JOIN matches m USING (match_id)
           WHERE f.is_remake = 0 ORDER BY m.game_start DESC LIMIT ?""",
        (n,),
    ).fetchall()
    return [
        {
            "date": datetime.fromtimestamp(r["game_start"] / 1000, tz=UTC)
            .astimezone().strftime("%d/%m %H:%M"),
            "win": bool(r["y_win"]),
            "champ": r["my_champion"],
            "vs": r["enemy_jungler_champion"] or "?",
            "gd15": r["gold_diff_ejgl_15"],
            "session_idx": r["session_game_index"],
            "omw": r["on_my_way_pings"],
            "duration": f"{r['game_duration_s'] // 60} min",
        }
        for r in rows
    ]


def latest_audits(conn: sqlite3.Connection, n: int = 3) -> list[dict]:
    rows = conn.execute(
        """SELECT a.verdict_json, a.model, a.cost_usd, m.game_start,
                  f.my_champion, f.enemy_jungler_champion, f.y_win
           FROM audits a JOIN matches m USING (match_id) JOIN features f USING (match_id)
           ORDER BY m.game_start DESC LIMIT ?""",
        (n,),
    ).fetchall()
    return [
        {
            "date": datetime.fromtimestamp(r["game_start"] / 1000, tz=UTC)
            .astimezone().strftime("%d/%m %H:%M"),
            "win": bool(r["y_win"]),
            "champ": r["my_champion"],
            "vs": r["enemy_jungler_champion"] or "?",
            "verdict": json.loads(r["verdict_json"]),
            "model": r["model"],
        }
        for r in rows
    ]


def hypothesis_tags(conn: sqlite3.Connection, last_n: int = 20) -> dict:
    """Compte les tags des derniers verdicts : hypothèses candidates pour l'analyste."""
    rows = conn.execute(
        """SELECT a.verdict_json FROM audits a JOIN matches m USING (match_id)
           ORDER BY m.game_start DESC LIMIT ?""",
        (last_n,),
    ).fetchall()
    counts: dict[str, int] = {}
    for r in rows:
        for t in json.loads(r["verdict_json"]).get("tags", []):
            counts[t] = counts.get(t, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: -kv[1])
    return {"n_verdicts": len(rows), "tags": [{"tag": t, "count": c} for t, c in ordered]}


def all_audits(conn: sqlite3.Connection, limit: int = 100) -> list[dict]:
    rows = conn.execute(
        """SELECT a.verdict_json, a.model, a.cost_usd, m.game_start, m.game_duration_s,
                  f.my_champion, f.enemy_jungler_champion, f.y_win
           FROM audits a JOIN matches m USING (match_id) JOIN features f USING (match_id)
           ORDER BY m.game_start DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [
        {
            "date": datetime.fromtimestamp(r["game_start"] / 1000, tz=UTC)
            .astimezone().strftime("%d/%m/%Y %H:%M"),
            "duration": f"{r['game_duration_s'] // 60} min",
            "win": bool(r["y_win"]),
            "champ": r["my_champion"],
            "vs": r["enemy_jungler_champion"] or "?",
            "verdict": json.loads(r["verdict_json"]),
            "model": r["model"],
            "cost": r["cost_usd"],
        }
        for r in rows
    ]


def latest_analysis(reports_dir) -> dict | None:
    """Dernier screening exporté par `skibot analyze` (analyse_latest.json)."""
    from pathlib import Path

    path = Path(reports_dir) / "analyse_latest.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    results = data.get("results", [])
    confirmed = [r for r in results if r.get("verdict") == "confirmé"]
    confirmed.sort(key=lambda r: (r["tag"] != "levier", r["q"]))
    failed = [r for r in results if r.get("retained") and r.get("verdict") != "confirmé"]
    return {
        "generated": data.get("generated", "?")[:10],
        "meta": data.get("meta", {}),
        "confirmed": confirmed,
        "failed": failed,
        "n_tested": len(results),
    }
