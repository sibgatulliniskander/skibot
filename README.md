# skibot

Outils du projet **Road to Master** : atteindre Master sur League of Legends d'ici
fin 2027 avec une méthode data-driven et AI-driven, documentée en stream.

Aucune assistance in-game : tout est post-game ou champ select uniquement
(conformité Riot).

## Setup

```
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
copy .env.example .env   # puis renseigner la clé Riot et le Riot ID
```

La clé API (developer.riotgames.com) expire toutes les 24 h pour une clé dev :
la régénérer et mettre à jour `.env` quand la collecte signale une clé expirée.

## Usage

```
skibot set-key   # enregistre/renouvelle la clé Riot dans .env (avec vérification)
skibot collect   # récupère les nouvelles games ranked solo/duo + timelines
skibot features  # extrait ~60 variables d'analyse par game (table features)
skibot analyze   # screening + confirmation, rapport markdown dans reports/
skibot dashboard # dashboard Flask : vue publique / et vue interne /interne
skibot status    # état de la base (games, sessions, dernier rang connu)
```

La collecte est incrémentale et idempotente : relançable à volonté, jamais de
doublon, et une interruption ne perd rien.

## Structure

- `skibot/riot/` — client API Riot (rate limiter 20 req/s et 100 req/2 min)
- `skibot/collector/` — ingestion match + timeline -> SQLite (`data/skibot.db`)
- `skibot/features/` — extraction des variables d'analyse (+ cache Data Dragon)
- `skibot/analysis/` — screening wins/losses (split figé par session, FDR, confirmation indépendante)
- `skibot/dashboard/` — Flask + Chart.js : courbe LP, WR, leviers, consigne active
- `skibot/auditor/` — jalon suivant
- `protocol/` — protocole DMAIC versionné en markdown
- `migrations/` — schéma SQL (fichiers numérotés, appliqués automatiquement)

## Tests

```
.venv\Scripts\python -m pytest
```
