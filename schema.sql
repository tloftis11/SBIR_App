-- Run this in the Supabase SQL editor before running the pipeline.

create extension if not exists vector;

create table if not exists awards (
  id               text primary key,
  program          text,
  phase            text,
  agency           text,
  branch           text,
  solicitation_id  text,
  solicitation_number text,
  solicitation_year   int,
  contract         text,
  firm             text,
  title            text,
  abstract         text,
  keywords         text,
  award_amount     bigint,
  duns             text,
  hubzone_owned    boolean,
  sdb_owned        boolean,
  woman_owned      boolean,
  number_employees int,
  address1         text,
  address2         text,
  city             text,
  state_code       text,
  zip              text,
  url              text,
  poc_name         text,
  poc_phone        text,
  poc_email        text,
  pi_name          text,
  pi_title         text,
  pi_email         text,
  ri_name          text,
  award_year       int,
  award_start_date text,
  award_end_date   text,
  created_at       timestamptz default now(),
  updated_at       timestamptz default now()
);

create index if not exists awards_agency_idx    on awards(agency);
create index if not exists awards_phase_idx     on awards(phase);
create index if not exists awards_year_idx      on awards(award_year);
create index if not exists awards_state_idx     on awards(state_code);
create index if not exists awards_firm_idx      on awards(firm);

create table if not exists award_embeddings (
  award_id    text primary key references awards(id) on delete cascade,
  embedding   vector(1024),
  model       text default 'voyage-3',
  embedded_at timestamptz default now()
);

-- Approximate nearest-neighbor index.
-- IVFFlat requires data before building; run the pipeline first, then:
--   CREATE INDEX ... (lists = 200) for 100k+ rows.
-- Uncomment after initial load:
-- create index award_embeddings_ivfflat_idx
--   on award_embeddings
--   using ivfflat (embedding vector_cosine_ops)
--   with (lists = 100);

-- Semantic search function called by the API layer.
create or replace function match_awards(
  query_embedding vector(1024),
  match_count     int     default 20,
  filter_agency   text    default null,
  filter_phase    text    default null,
  filter_year_min int     default null,
  filter_year_max int     default null,
  filter_state    text    default null
)
returns table (
  id           text,
  firm         text,
  title        text,
  abstract     text,
  agency       text,
  phase        text,
  award_year   int,
  award_amount bigint,
  state_code   text,
  similarity   float
)
language sql stable as $$
  select
    a.id, a.firm, a.title, a.abstract,
    a.agency, a.phase, a.award_year, a.award_amount, a.state_code,
    1 - (e.embedding <=> query_embedding) as similarity
  from award_embeddings e
  join awards a on a.id = e.award_id
  where
    (filter_agency   is null or a.agency     = filter_agency)
    and (filter_phase    is null or a.phase      = filter_phase)
    and (filter_year_min is null or a.award_year >= filter_year_min)
    and (filter_year_max is null or a.award_year <= filter_year_max)
    and (filter_state    is null or a.state_code  = filter_state)
  order by e.embedding <=> query_embedding
  limit match_count;
$$;

-- Keep updated_at current on row changes.
create or replace function update_updated_at()
returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end;
$$;

drop trigger if exists awards_updated_at on awards;
create trigger awards_updated_at
  before update on awards
  for each row execute function update_updated_at();
