-- Run this in Supabase SQL Editor after data is loaded.
-- Adds the get_filter_options() RPC used by the /filters endpoint.

CREATE OR REPLACE FUNCTION get_filter_options()
RETURNS jsonb
LANGUAGE sql
STABLE
AS $$
  SELECT jsonb_build_object(
    'agencies', (
      SELECT jsonb_agg(DISTINCT agency ORDER BY agency)
      FROM awards
      WHERE agency IS NOT NULL
    ),
    'phases', (
      SELECT jsonb_agg(DISTINCT phase ORDER BY phase)
      FROM awards
      WHERE phase IS NOT NULL
    ),
    'states', (
      SELECT jsonb_agg(DISTINCT state_code ORDER BY state_code)
      FROM awards
      WHERE state_code IS NOT NULL
    ),
    'year_min', (SELECT MIN(award_year) FROM awards WHERE award_year IS NOT NULL),
    'year_max', (SELECT MAX(award_year) FROM awards WHERE award_year IS NOT NULL)
  )
$$;
