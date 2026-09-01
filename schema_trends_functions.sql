-- Run in Supabase SQL Editor after data is loaded.
-- Adds the 4 RPC functions used by the /trends endpoint.

CREATE OR REPLACE FUNCTION trends_by_year(
  filter_agency  text DEFAULT NULL,
  filter_phase   text DEFAULT NULL,
  filter_year_min int DEFAULT NULL,
  filter_year_max int DEFAULT NULL,
  filter_state   text DEFAULT NULL
)
RETURNS TABLE(year int, count bigint, total_amount bigint)
LANGUAGE sql STABLE AS $$
  SELECT
    award_year                     AS year,
    COUNT(*)                       AS count,
    COALESCE(SUM(award_amount), 0) AS total_amount
  FROM awards
  WHERE award_year IS NOT NULL
    AND (filter_agency  IS NULL OR agency     = filter_agency)
    AND (filter_phase   IS NULL OR phase      = filter_phase)
    AND (filter_year_min IS NULL OR award_year >= filter_year_min)
    AND (filter_year_max IS NULL OR award_year <= filter_year_max)
    AND (filter_state   IS NULL OR state_code = filter_state)
  GROUP BY award_year
  ORDER BY award_year;
$$;

CREATE OR REPLACE FUNCTION trends_by_agency(
  filter_phase    text DEFAULT NULL,
  filter_year_min int  DEFAULT NULL,
  filter_year_max int  DEFAULT NULL,
  filter_state    text DEFAULT NULL
)
RETURNS TABLE(agency text, count bigint)
LANGUAGE sql STABLE AS $$
  SELECT
    agency,
    COUNT(*) AS count
  FROM awards
  WHERE agency IS NOT NULL
    AND (filter_phase    IS NULL OR phase      = filter_phase)
    AND (filter_year_min IS NULL OR award_year >= filter_year_min)
    AND (filter_year_max IS NULL OR award_year <= filter_year_max)
    AND (filter_state    IS NULL OR state_code = filter_state)
  GROUP BY agency
  ORDER BY count DESC
  LIMIT 20;
$$;

CREATE OR REPLACE FUNCTION trends_by_phase(
  filter_agency   text DEFAULT NULL,
  filter_year_min int  DEFAULT NULL,
  filter_year_max int  DEFAULT NULL,
  filter_state    text DEFAULT NULL
)
RETURNS TABLE(phase text, count bigint)
LANGUAGE sql STABLE AS $$
  SELECT
    phase,
    COUNT(*) AS count
  FROM awards
  WHERE phase IS NOT NULL
    AND (filter_agency   IS NULL OR agency     = filter_agency)
    AND (filter_year_min IS NULL OR award_year >= filter_year_min)
    AND (filter_year_max IS NULL OR award_year <= filter_year_max)
    AND (filter_state    IS NULL OR state_code = filter_state)
  GROUP BY phase
  ORDER BY count DESC;
$$;

CREATE OR REPLACE FUNCTION trends_top_states(
  filter_agency   text DEFAULT NULL,
  filter_phase    text DEFAULT NULL,
  filter_year_min int  DEFAULT NULL,
  filter_year_max int  DEFAULT NULL
)
RETURNS TABLE(state text, count bigint)
LANGUAGE sql STABLE AS $$
  SELECT
    state_code AS state,
    COUNT(*)   AS count
  FROM awards
  WHERE state_code IS NOT NULL
    AND (filter_agency   IS NULL OR agency     = filter_agency)
    AND (filter_phase    IS NULL OR phase      = filter_phase)
    AND (filter_year_min IS NULL OR award_year >= filter_year_min)
    AND (filter_year_max IS NULL OR award_year <= filter_year_max)
  GROUP BY state_code
  ORDER BY count DESC
  LIMIT 15;
$$;
