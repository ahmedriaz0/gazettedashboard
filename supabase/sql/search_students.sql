-- Run this once in the Supabase SQL Editor (Project → SQL Editor → New query).
-- I can't run this myself: the client only has the anon key, which can't
-- create functions. This needs the project owner's SQL Editor access.
--
-- Why this exists: filtering with `.ilike('name', '%ali%').range(0, 24)`
-- fetches only 25 rows ordered by roll_number, THEN re-sorts just those 25
-- client-side. An exact "ALI" match with a roll_number outside that first
-- page of matches never gets downloaded, so it never appears. Ranking has
-- to happen in the database, before LIMIT/OFFSET is applied.
--
-- This function ranks name matches (0 = exact, 1 = starts-with,
-- 2 = contains) and applies that ranking globally, before paging, so exact
-- matches always surface on page 1 regardless of roll_number.

create or replace function search_students(
  p_roll_number bigint default null,
  p_name text default null,
  p_board text default null,
  p_class int default null,
  p_year int default null,
  p_min_marks int default null,
  p_max_marks int default null,
  p_limit int default 25,
  p_offset int default 0
)
returns table (
  record jsonb,
  total_count bigint
)
language sql
stable
as $$
  select
    to_jsonb(s) as record,
    count(*) over() as total_count
  from student_results s
  where
    (p_roll_number is null or s.roll_number = p_roll_number)
    and (p_name is null or s.name ilike '%' || p_name || '%')
    and (p_board is null or s.board ilike '%' || p_board || '%')
    and (p_class is null or s.class = p_class)
    and (p_year is null or s.year = p_year)
    and (p_min_marks is null or s.marks >= p_min_marks)
    and (p_max_marks is null or s.marks <= p_max_marks)
  order by
    case
      when p_name is not null and lower(s.name) = lower(p_name) then 0
      when p_name is not null and lower(s.name) like lower(p_name) || '%' then 1
      when p_name is not null then 2
      else 0
    end,
    s.roll_number asc
  limit p_limit offset p_offset;
$$;

-- PostgREST (which supabase-js talks to) needs explicit execute grants.
grant execute on function search_students(
  bigint, text, text, int, int, int, int, int, int
) to anon, authenticated;
