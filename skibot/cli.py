"""CLI skibot : `skibot collect`, `skibot status`."""

from __future__ import annotations

from datetime import UTC, datetime

import click

from . import db
from .collector import collect as collect_mod
from .config import ConfigError, load_config, update_env_value
from .riot.client import RiotApiError, RiotAuthError, RiotClient


@click.group()
def main() -> None:
    """Outils du projet skibot (Road to Master)."""


@main.command()
@click.option("--max-games", type=int, default=None, help="Limite le nombre de games sur ce run.")
def collect(max_games: int | None) -> None:
    """Récupère les nouvelles games ranked (match + timeline) et met à jour la base."""
    try:
        cfg = load_config()
    except ConfigError as e:
        raise click.ClickException(str(e))
    conn = db.connect(cfg.db_path)
    client = RiotClient(cfg.riot_api_key, cfg.platform, cfg.regional)
    try:
        summary = collect_mod.collect(conn, client, cfg, log=click.echo, max_games=max_games)
    except RiotAuthError as e:
        raise click.ClickException(str(e))
    except RiotApiError as e:
        raise click.ClickException(f"Erreur API Riot : {e}")
    click.echo(
        f"\n{summary['new_games']} game(s) ajoutée(s)"
        f" ({summary['no_timeline']} sans timeline), {summary['sessions']} session(s) en base."
    )
    if summary.get("skipped"):
        click.echo(f"{summary['skipped']} game(s) ignorée(s) : payload invalide côté Riot.")
    if summary["rank"]:
        click.echo(f"Rang actuel : {summary['rank']}")


@main.command()
@click.option("--rebuild", is_flag=True, help="Recalcule toutes les games (apres une evolution de l'extracteur).")
def features(rebuild):
    """Extrait les features d'analyse (une ligne par game) depuis la base."""
    cfg = load_config(require_key=False)
    conn = db.connect(cfg.db_path)
    from .features import extract
    s = extract.run(conn, rebuild=rebuild, log=click.echo)
    click.echo(f"\n{s['extracted']} game(s) extraite(s), {s['total']} au total.")
    click.echo(
        "Couverture : challenges {}/{}, gold@15 {}/{}, remakes exclus : {}.".format(
            s["with_challenges"], s["total"], s["with_gold15"], s["total"], s["remakes"]
        )
    )


@main.command("set-key")
def set_key() -> None:
    """Enregistre ta clé Riot dans .env et vérifie qu'elle fonctionne."""
    key = click.prompt("Colle ta clé Riot (RGAPI-...)", hide_input=True).strip()
    if not key.startswith("RGAPI-"):
        click.confirm("La clé ne commence pas par RGAPI- ; continuer quand même ?", abort=True)
    path = update_env_value("RIOT_API_KEY", key)
    click.echo(f"Clé enregistrée dans {path}")
    try:
        cfg = load_config()
    except ConfigError:
        click.echo(
            "Riot ID pas encore renseigné dans .env — impossible de tester la clé maintenant, "
            "elle sera vérifiée au premier `skibot collect`."
        )
        return
    client = RiotClient(cfg.riot_api_key, cfg.platform, cfg.regional)
    try:
        account = client.account_by_riot_id(cfg.game_name, cfg.tag_line)
    except RiotAuthError:
        raise click.ClickException(
            "Cette clé est refusée par l'API Riot (mal copiée ou déjà expirée ?)."
        )
    click.echo(f"Clé valide — compte résolu : {account.get('gameName')}#{account.get('tagLine')}")


@main.command()
def status() -> None:
    """Affiche l'état de la base : games, sessions, dernier rang connu."""
    cfg = load_config(require_key=False)
    conn = db.connect(cfg.db_path)
    n_matches = conn.execute("SELECT COUNT(*) AS c FROM matches").fetchone()["c"]
    n_timeline = conn.execute(
        "SELECT COUNT(*) AS c FROM matches WHERE has_timeline = 1"
    ).fetchone()["c"]
    n_sessions = conn.execute("SELECT COUNT(*) AS c FROM sessions").fetchone()["c"]
    last_start = conn.execute("SELECT MAX(game_start) AS ts FROM matches").fetchone()["ts"]
    rank = conn.execute(
        "SELECT * FROM rank_snapshots ORDER BY snapshot_id DESC LIMIT 1"
    ).fetchone()

    click.echo(f"Base : {cfg.db_path}")
    click.echo(f"Games : {n_matches} ({n_timeline} avec timeline)")
    click.echo(f"Sessions : {n_sessions}")
    if last_start is not None:
        dt = datetime.fromtimestamp(last_start / 1000, tz=UTC).astimezone()
        click.echo(f"Dernière game : {dt:%Y-%m-%d %H:%M}")
    if rank is not None:
        click.echo(
            f"Dernier rang connu : {rank['tier']} {rank['division']} — {rank['lp']} LP "
            f"({rank['wins']}W/{rank['losses']}L, snapshot {rank['taken_at']})"
        )


if __name__ == "__main__":
    main()
