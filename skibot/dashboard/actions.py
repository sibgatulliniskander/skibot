"""Actions du pipeline lancées depuis le dashboard.

Un seul job à la fois (verrou global) : les actions écrivent dans SQLite et
consomment les quotas API — les sérialiser évite les conflits, y compris avec
la tâche planifiée horaire (busy_timeout côté connexion).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, datetime

from .. import db
from ..config import load_config
from ..riot.client import RiotClient

_BUSY = threading.Lock()
JOBS: dict[str, dict] = {}


def _do_maj(log: Callable[[str], None]) -> None:
    """Collecte les nouvelles games puis extrait leurs features."""
    cfg = load_config()
    conn = db.connect(cfg.db_path)
    client = RiotClient(cfg.riot_api_key, cfg.platform, cfg.regional)
    s = collect_summary = None
    from ..collector import collect as collect_mod
    collect_summary = collect_mod.collect(conn, client, cfg, log=log)
    log(f"-> {collect_summary['new_games']} game(s) ajoutée(s)")
    from ..features import extract
    s = extract.run(conn, log=log)
    log(f"-> {s['extracted']} feature(s) extraite(s) — terminé")


def _do_audit(log: Callable[[str], None]) -> None:
    """Audite jusqu'à 10 games éligibles des 7 derniers jours (~5 c/game)."""
    import os

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY absente du .env (skibot set-anthropic-key)")
    cfg = load_config(require_key=False)
    conn = db.connect(cfg.db_path)
    from ..auditor import audit as auditor_mod
    s = auditor_mod.run(conn, limit=10, log=log)
    log(f"-> {s['audited']} game(s) auditée(s), coût {s['cost_usd']:.2f} $ — terminé")


def _do_analyze(log: Callable[[str], None]) -> None:
    """Screening + confirmation, rapport et export JSON régénérés."""
    cfg = load_config(require_key=False)
    conn = db.connect(cfg.db_path)
    from ..analysis import run as analysis_run
    s = analysis_run.analyze(conn, log=log)
    log(f"-> {s['tested']} variables, {s['confirmed']} effet(s) confirmé(s) — terminé")


def _do_bench(log: Callable[[str], None]) -> None:
    """Recalcule la comparaison moi vs Diamant (sans crawl)."""
    cfg = load_config(require_key=False)
    conn = db.connect(cfg.db_path)
    from ..benchmark import compare as compare_mod
    result = compare_mod.compare(conn)
    if not result["metrics"]:
        raise RuntimeError("pas assez de données bench — lancer le crawl d'abord")
    compare_mod.write_latest(result)
    log(f"-> {len(result['metrics'])} métriques comparées — terminé")


def _do_bench_collect(log: Callable[[str], None]) -> None:
    """Crawle un échantillon Diamant + timelines puis recalcule la comparaison."""
    cfg = load_config()
    conn = db.connect(cfg.db_path)
    client = RiotClient(cfg.riot_api_key, cfg.platform, cfg.regional)
    from ..benchmark import collect as bench_mod
    s = bench_mod.collect(conn, client, log=log)
    n_tl = bench_mod.backfill_timelines(conn, client, log=log)
    log(f"-> {s['new_junglers']} jungler(s) ajoutés, {n_tl} timeline(s) enrichie(s)")
    _do_bench(log)


ACTIONS: dict[str, tuple[str, Callable]] = {
    "maj": ("Mise à jour (collecte + features)", _do_maj),
    "audit": ("Audits (7 derniers jours, max 10)", _do_audit),
    "analyze": ("Analyse (screening + confirmation)", _do_analyze),
    "bench": ("Benchmark (comparaison)", _do_bench),
    "bench_collect": ("Crawl Diamant + benchmark", _do_bench_collect),
}


def start(name: str) -> tuple[bool, str]:
    """Démarre une action en arrière-plan. Refuse si un job tourne déjà."""
    if name not in ACTIONS:
        return False, f"action inconnue : {name}"
    if not _BUSY.acquire(blocking=False):
        return False, "une action est déjà en cours — attends qu'elle se termine"
    label, fn = ACTIONS[name]
    JOBS[name] = {
        "label": label,
        "status": "running",
        "log": [],
        "started": datetime.now(UTC).isoformat(timespec="seconds"),
        "ended": None,
    }

    def runner() -> None:
        job = JOBS[name]
        try:
            fn(job["log"].append)
            job["status"] = "ok"
        except Exception as e:  # noqa: BLE001 — le job doit toujours libérer le verrou
            job["log"].append(f"ERREUR : {e}")
            job["status"] = "error"
        finally:
            job["ended"] = datetime.now(UTC).isoformat(timespec="seconds")
            _BUSY.release()

    threading.Thread(target=runner, daemon=True, name=f"action-{name}").start()
    return True, "démarré"


def status() -> dict:
    running = next((n for n, j in JOBS.items() if j["status"] == "running"), None)
    return {
        "running": running,
        "jobs": {
            n: {
                "label": j["label"],
                "status": j["status"],
                "started": j["started"],
                "ended": j["ended"],
                "log_tail": j["log"][-12:],
            }
            for n, j in JOBS.items()
        },
    }
