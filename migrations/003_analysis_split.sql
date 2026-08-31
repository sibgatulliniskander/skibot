-- Split exploration/confirmation : tiré UNE FOIS (par session), puis figé.
-- Les games absentes de cette table forment le pool prospectif.
CREATE TABLE analysis_split (
    match_id    TEXT PRIMARY KEY REFERENCES matches(match_id) ON DELETE CASCADE,
    split       TEXT NOT NULL CHECK (split IN ('explore', 'confirm')),
    seed        INTEGER NOT NULL,
    assigned_at TEXT NOT NULL
);
