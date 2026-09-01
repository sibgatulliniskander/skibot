"""Dashboard Flask : vue publique (/) et vue interne (/interne).

Lecture seule sur la base ; le statut de la consigne vient de
protocol/consigne-active.md (source de vérité versionnée).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from flask import Flask, render_template

from ..config import PROJECT_ROOT, load_config
from . import queries

CONSIGNE_FILE = PROJECT_ROOT / "protocol" / "consigne-active.md"


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def consigne_status() -> str:
    """Extrait la ligne de statut de consigne-active.md (jamais reformulée)."""
    try:
        for line in CONSIGNE_FILE.read_text(encoding="utf-8").splitlines():
            if line.startswith("**Statut"):
                return line.strip("* ").removeprefix("Statut : ")
    except OSError:
        pass
    return "statut indisponible"


def create_app(db_path: Path | None = None) -> Flask:
    app = Flask(__name__)
    if db_path is None:
        cfg = load_config(require_key=False)
        db_path = cfg.db_path
        if cfg.game_name:
            queries.set_official(f"{cfg.game_name}#{cfg.tag_line}")
    app.config["DB_PATH"] = Path(db_path)
    app.config.setdefault("REPORTS_DIR", PROJECT_ROOT / "reports")

    @app.route("/")
    def index():
        conn = _connect(app.config["DB_PATH"])
        try:
            return render_template(
                "index.html",
                summary=queries.summary(conn),
                lp=queries.lp_history(conn),
                ticks=queries.tier_ticks(),
                weekly=queries.weekly_wr(conn),
                consigne=consigne_status(),
            )
        finally:
            conn.close()

    @app.route("/interne")
    def interne():
        conn = _connect(app.config["DB_PATH"])
        try:
            return render_template(
                "interne.html",
                summary=queries.summary(conn),
                trends=queries.levier_trends(conn),
                games=queries.recent_games(conn),
                audits=queries.latest_audits(conn),
                hypotheses=queries.hypothesis_tags(conn),
                consigne=consigne_status(),
            )
        finally:
            conn.close()

    @app.route("/audits")
    def audits():
        conn = _connect(app.config["DB_PATH"])
        try:
            return render_template(
                "audits.html",
                summary=queries.summary(conn),
                audits=queries.all_audits(conn),
                hypotheses=queries.hypothesis_tags(conn),
            )
        finally:
            conn.close()

    @app.route("/benchmark")
    def benchmark():
        conn = _connect(app.config["DB_PATH"])
        try:
            return render_template(
                "benchmark.html",
                summary=queries.summary(conn),
                bench=queries.latest_benchmark(app.config["REPORTS_DIR"]),
            )
        finally:
            conn.close()

    @app.route("/carte")
    def carte():
        conn = _connect(app.config["DB_PATH"])
        try:
            return render_template(
                "carte.html",
                summary=queries.summary(conn),
                points=queries.map_points(conn),
            )
        finally:
            conn.close()

    @app.route("/analyse")
    def analyse():
        conn = _connect(app.config["DB_PATH"])
        try:
            return render_template(
                "analyse.html",
                summary=queries.summary(conn),
                analysis=queries.latest_analysis(app.config["REPORTS_DIR"]),
            )
        finally:
            conn.close()

    return app
