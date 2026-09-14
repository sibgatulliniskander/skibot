# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

skibot: public, data-driven project to climb from Platinum to Master in League of
Legends by end of 2027, documented on stream. The user is a Lean Six Sigma project
manager and Python/Flask developer, playing jungle. **Communicate with the user in
French.**

## Commands

```
python -m venv .venv                        # setup (Windows)
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\python -m pytest              # all tests
.venv\Scripts\python -m pytest tests/test_ingest.py::test_ingest_full   # single test
.venv\Scripts\ruff check .                  # lint
.venv\Scripts\skibot set-key                # store/renew the Riot key in .env (validates it)
.venv\Scripts\skibot collect                # fetch new ranked games (needs .env)
.venv\Scripts\skibot features               # extract analysis variables (features table)
.venv\Scripts\skibot analyze                # screening + confirmation, report in reports/
.venv\Scripts\skibot dashboard              # Flask dashboard on http://127.0.0.1:5000
.venv\Scripts\skibot set-anthropic-key      # store the Anthropic key in .env (validates it)
.venv\Scripts\skibot audit                  # LLM post-game verdicts (default: 3 newest unaudited)
.venv\Scripts\skibot bench-collect          # crawl a Diamond jungler sample (needs .env)
.venv\Scripts\skibot bench                  # compare my current-era distributions vs Diamond
.venv\Scripts\skibot status                 # DB state, no API key needed
```

`.env` (from `.env.example`): `RIOT_API_KEY`, `RIOT_GAME_NAME`, `RIOT_TAG_LINE`,
`RIOT_PLATFORM`. Dev API keys expire every 24h — a 401/403 raises `RiotAuthError`
with refresh instructions; collection is incremental and idempotent, so rerunning
after a key refresh resumes where it stopped.

## Architecture

Single installable package `skibot/` with subpackages per pipeline stage:
`riot/` (API client) → `collector/` (ingestion) → `features/` → `analysis/` →
`auditor/` → `dashboard/` (the last four are future milestones). SQLite DB at
`data/skibot.db` (gitignored), possible Postgres migration later.

Key design decisions:

- **Raw payloads are the source of truth.** Full Match-V5 match and timeline JSON
  are stored in `matches.raw_match_json` / `raw_timeline_json`, so features can
  always be recomputed without refetching the API. The flattened tables
  (`participants`, `timeline_frames`, `timeline_events`) promote analysis-friendly
  columns; unpromoted event fields go to `extra_json` — except the bulky
  `victimDamageDealt`/`victimDamageReceived`, which live only in the raw JSON.
- **DRAGON_SOUL_GIVEN quirk**: Riot emits an announce event (teamId 0, when
  the soul type is revealed) AND an award event (teamId 100/200). Only the
  award counts — features/extract.py filters teamId in (100, 200); validated
  429/429 against the 4th-dragon team.
- **`participant_id` (1-10) is the join key** across participants/frames/events.
  `WARD_PLACED` events use `creatorId`, mapped into `participant_id` at ingest.
  Ward events have NO position in the Riot timeline (`pos_x`/`pos_y` NULL) — never
  claim ward positions.
- **Each game ingests in one transaction** (`collector/ingest.py`); dedup happens
  in `collector/collect.py` by filtering known match_ids before fetching.
- **Sessions are recomputed deterministically** from 60-min gaps between games
  (`collector/sessions.py`); manual `note`s are preserved by `started_at` across
  rebuilds. Only ranked solo/duo (queue 420) is collected.
- **Multi-account**: RIOT_ALT_ACCOUNTS in .env ("Name#Tag;Name#Tag") merges
  smurf games into the SAME db (same player = same process; per-account
  incremental start_time). rank_snapshots.riot_id tags each snapshot; the
  public LP curve filters to the main account (queries.set_official).
- **`rank_snapshots` appends the current rank on every collect** — it is the only
  possible source of LP history (the League API has no historical endpoint).
- **Migrations**: numbered SQL files in `migrations/`, applied in filename order,
  recorded in `schema_migrations`. Never edit an applied migration — add a new file.
- Rate limiting: dual sliding window (20 req/1s, 100 req/2min) in
  `riot/rate_limiter.py`, plus `Retry-After` handling on 429.
- Dashboard (skibot/dashboard/): read-only SQLite access, data injected
  server-side into Jinja templates (no separate API), Chart.js from CDN.
  The consigne status shown comes verbatim from protocol/consigne-active.md.
  Routes: / (public), /interne, /audits (all verdicts + hypothesis tags),
  /analyse (renders reports/analyse_latest.json written by `skibot analyze`),
  /benchmark (renders reports/benchmark_latest.json), /carte (kill/death map
  from timeline positions — canvas over the Data Dragon minimap, client-side
  filters; ward positions are never mapped, Riot does not provide them).
  Flask caches templates when not in debug: restart `skibot dashboard` after
  template edits. The Windows scheduled task (scripts/collect.bat) chains
  collect + features hourly. The /interne page has an Actions panel
  (dashboard/actions.py): POST /action/<name> runs pipeline actions (maj,
  audit, analyze, bench, bench_collect) in a background thread — one job at a
  time (global lock), GET /action/status polls; run the server threaded=True.
  SQLite connections set busy_timeout=15s (dashboard jobs vs hourly task).
  The dashboard auto-starts at Windows logon (scripts/dashboard.vbs copied
  with an absolute path into the user's Startup folder; log: data/dashboard.log)
  — after code changes, kill the running python/skibot dashboard process and
  relaunch the Startup .vbs (or reboot) to serve the new code. The desktop
  shortcut "skibot dashboard.lnk" runs scripts/open-dashboard.vbs, which
  restarts the server if it is down before opening /interne (self-healing).
  When relaunching the server from a Claude tool call, spawn it DETACHED
  (Invoke-CimMethod Win32_Process Create) — a child of the tool's shell dies
  with the tool.

- Benchmark (skibot/benchmark/): crawls Diamond I-II jungler games (match DTO
  only, no timelines — 1 request/game, 2 junglers/game) into `bench_games`,
  never mixed with the player's data. `skibot bench` compares current-era
  distributions on the 12 metrics whose Riot counters are identical on both
  sides (COMPARE_METRICS), writes reports/benchmark_latest.json. Percentiles
  use midpoint tie-ranking. A gap vs Diamond is a hypothesis generator, never
  causal proof. Foundation for the future build advisor (items stored).
- Auditor (skibot/auditor/): the LLM (claude-opus-5) only ever sees a
  deterministic "dossier de faits" (numbered facts, each with provenance) built
  in auditor/dossier.py; verify_citations() mechanically rejects any verdict
  citing a nonexistent fact or making an uncited claim (one retry, then
  AuditError — nothing non-conform is stored). Verdicts are descriptive only:
  the prompt forbids recommendations (consignes belong to the protocol).
  Structured output via output_config json_schema; verdicts stored in `audits`,
  shown in the dashboard's internal view. The dossier carries personal baselines
  (W/L medians + percentile per metric, computed in code) so verdicts highlight
  deviations from the player's own norms; verdicts also pick 1-3 tags from the
  closed taxonomy in auditor/prompts.py (aggregated in the dashboard as
  hypothesis candidates for the analyst — never conclusions), ask one factual
  replay question, and track the active consigne's X when protocol/consigne.json
  exists. verify_citations also rejects prescriptive wording (PRESCRIPTIVE_MARKERS).

## Project rules

- **Riot compliance**: no in-game assistance, ever. Everything is post-game or
  champ-select only.
- **Honesty clause** (drives `auditor/` and `analysis/`): every claim must be
  labeled "proven by event X" or "inferred from Y" — never assert what the data
  cannot prove.
- **Analysis discipline** (skibot/analysis/): the explore/confirm split is
  assigned ONCE, by session (never by game), persisted in `analysis_split` and
  NEVER redrawn (redrawing = p-hacking). Screening uses Mann-Whitney/Fisher/chi2
  + Benjamini-Hochberg (q <= 0.10); candidates are then re-tested on the
  independent confirmation sample (alpha = 0.05, same direction required).
  Games outside the split are the prospective pool. Findings tagged "levier"
  (actionable) vs "mécanisme" (descriptive — never turn these into consignes).
  Reports also grade each candidate's temporal stability on the "current era"
  (ERA_START in skibot/analysis/run.py, protocol rule 11): a levier that is
  unstable/weakened in the current era is NOT eligible as a consigne.
  Reports land in reports/ (gitignored). The protocol state (active consigne,
  decisions) lives in protocol/ — keep it in sync with any analysis change.
- Repo is public: the Riot key lives only in `.env` (gitignored); never commit
  `.env` or `data/`.
- Features layer (skibot/features/): ~60 variables per game in the `features`
  table (session context, draft/comp via a cached Data Dragon lookup, early game
  vs enemy jungler, objectives, Riot precomputed challenges), Y = y_win,
  Y2 = y2_team_gold_diff_15. NULL means "not measurable for that game" — never
  invent values. `is_remake = 1` rows must be excluded from analyses. Rerun with
  `skibot features --rebuild` after changing the extractor (bump
  EXTRACTOR_VERSION in skibot/features/extract.py).
