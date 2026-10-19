-- Changements de Riot ID : chaque ancien nom d'un compte pointe vers son nom
-- actuel. Maintenue par la collecte (collector/collect.py:sync_account_name) ;
-- features.account et rank_snapshots.riot_id portent toujours le nom actuel.
-- Le PUUID ne suffit pas comme identité : Riot le chiffre par clé API.
CREATE TABLE account_aliases (
    alias      TEXT PRIMARY KEY,
    canonical  TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
