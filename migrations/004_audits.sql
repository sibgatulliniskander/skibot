-- Verdicts LLM post-game : un par game, regénérable (INSERT OR REPLACE).
CREATE TABLE audits (
    match_id      TEXT PRIMARY KEY REFERENCES matches(match_id) ON DELETE CASCADE,
    created_at    TEXT NOT NULL,
    model         TEXT NOT NULL,
    verdict_json  TEXT NOT NULL,   -- structure validée par le vérificateur de citations
    verdict_md    TEXT NOT NULL,   -- rendu markdown (avec les faits cités et leur provenance)
    input_tokens  INTEGER,
    output_tokens INTEGER,
    cost_usd      REAL
);
