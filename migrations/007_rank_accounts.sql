-- Multi-comptes : chaque snapshot de rang porte son compte.
-- NULL = lignes historiques (compte principal).
ALTER TABLE rank_snapshots ADD COLUMN riot_id TEXT;
