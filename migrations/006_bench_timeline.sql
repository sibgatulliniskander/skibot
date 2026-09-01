-- Métriques timeline du benchmark (complément : 1 requête timeline par game)
ALTER TABLE bench_games ADD COLUMN deaths_pre15 INTEGER;
ALTER TABLE bench_games ADD COLUMN deaths_post25 INTEGER;
ALTER TABLE bench_games ADD COLUMN gold_diff_ejgl_10 INTEGER;
ALTER TABLE bench_games ADD COLUMN gold_diff_ejgl_15 INTEGER;
ALTER TABLE bench_games ADD COLUMN xp_diff_ejgl_10 INTEGER;
ALTER TABLE bench_games ADD COLUMN cs_diff_ejgl_10 INTEGER;
