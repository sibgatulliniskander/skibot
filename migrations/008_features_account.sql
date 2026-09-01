-- Multi-comptes : chaque ligne de features porte son compte (riot_id).
-- NULL = lignes antérieures à la migration (re-remplies par features --rebuild).
ALTER TABLE features ADD COLUMN account TEXT;
