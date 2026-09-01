-- The typo-correction dictionary, as a table.
--
-- _load_sql_vocab() currently derives this with a DISTINCT regexp_matches over
-- every active product name: ~2.3 s, held in a per-process Python set, rebuilt
-- by every worker and lost on every restart. It is also only consulted after a
-- query already looks misspelt, so the cost lands on a user who is mid-search.
--
-- As a table it is built once, indexed, and answers a correction in ~110 ms.
-- The important property is what it is NOT: correcting a word against an 18k-row
-- dictionary never touches the 166k-row product table. Matching typos directly
-- against products measured 3.4-3.9 s cold; this keeps the approximate pass off
-- that path entirely.

CREATE TABLE IF NOT EXISTS search_vocab (
    word text PRIMARY KEY,
    freq integer NOT NULL DEFAULT 0
);

COMMENT ON TABLE search_vocab IS
  'Distinct >=3-letter words from active product names, with occurrence counts. '
  'Rebuilt by scripts/refresh_search_vocab.py after a catalog import.';

-- freq breaks ties between equally-similar corrections: for "ornment", both
-- "ornament" and the vendor typo "oranment" score 0.55, and the common spelling
-- is the one worth offering.
CREATE INDEX IF NOT EXISTS ix_search_vocab_freq ON search_vocab (freq DESC);

-- Trigram, to find near spellings. GIN over 18k short rows is small and fast;
-- the equivalent index on products is what made the naive approach slow.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_search_vocab_trgm
  ON search_vocab USING GIN (word gin_trgm_ops);
