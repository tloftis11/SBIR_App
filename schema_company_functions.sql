-- Run in Supabase SQL Editor.
-- Adds the two RPC functions used by the /companies endpoints.

CREATE OR REPLACE FUNCTION search_companies(
  query       text    DEFAULT '',
  sort_by     text    DEFAULT 'count',   -- 'count' or 'funding'
  filter_agency text  DEFAULT NULL,
  filter_state  text  DEFAULT NULL,
  filter_phase  text  DEFAULT NULL,
  result_limit  int   DEFAULT 30
)
RETURNS TABLE(
  firm          text,
  award_count   bigint,
  total_funding bigint,
  phase_1_count bigint,
  phase_2_count bigint,
  year_first    int,
  year_last     int
)
LANGUAGE sql STABLE AS $$
  SELECT
    firm,
    COUNT(*)                                                         AS award_count,
    COALESCE(SUM(award_amount), 0)                                   AS total_funding,
    COUNT(*) FILTER (
      WHERE LOWER(phase) LIKE '%phase i%'
        AND LOWER(phase) NOT LIKE '%phase ii%'
    )                                                                AS phase_1_count,
    COUNT(*) FILTER (WHERE LOWER(phase) LIKE '%phase ii%')           AS phase_2_count,
    MIN(award_year)                                                  AS year_first,
    MAX(award_year)                                                  AS year_last
  FROM awards
  WHERE firm IS NOT NULL
    AND (query = ''        OR firm        ILIKE '%' || query || '%')
    AND (filter_agency IS NULL OR agency     = filter_agency)
    AND (filter_state  IS NULL OR state_code = filter_state)
    AND (filter_phase  IS NULL OR phase      = filter_phase)
  GROUP BY firm
  ORDER BY
    CASE WHEN sort_by = 'funding'
      THEN COALESCE(SUM(award_amount), 0)::numeric
      ELSE COUNT(*)::numeric
    END DESC
  LIMIT result_limit;
$$;


CREATE OR REPLACE FUNCTION company_awards(firm_name text)
RETURNS TABLE(
  id           text,
  title        text,
  abstract     text,
  agency       text,
  phase        text,
  award_year   int,
  award_amount int,
  state_code   text,
  keywords     text
)
LANGUAGE sql STABLE AS $$
  SELECT id, title, abstract, agency, phase, award_year, award_amount, state_code, keywords
  FROM awards
  WHERE firm = firm_name
  ORDER BY award_year DESC NULLS LAST;
$$;
