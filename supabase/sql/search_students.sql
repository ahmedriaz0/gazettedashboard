-- Run this once in the Supabase SQL Editor (Project → SQL Editor → New query).
-- I can't run this myself: the client only has the anon key, which can't
-- create functions. This needs the project owner's SQL Editor access.
--
-- History:
-- v1 fetched with `.ilike().range()` client-side, which only re-sorted the
-- one page that came back — an exact match outside that page never
-- surfaced. v2 (this file, previously) moved ranking into the database via
-- `count(*) over()` + `order by <rank>, roll_number`.
--
-- v2 bug (this revision fixes it): `count(*) over()` with no PARTITION BY
-- has to see every matching row before it can attach a count to row 1, so
-- Postgres can't use an index to stream the first page — it must scan and,
-- for a name search, fully sort the ENTIRE matching set before slicing off
-- p_limit rows. For "all boards, no other filter" that's ~850k rows; for a
-- common name like "muhammad" it's still hundreds of thousands. Both blow
-- Supabase's statement_timeout and the RPC call fails outright, which the
-- client silently renders as "No matching records found." A specific board
-- (~87k rows, plain roll_number sort) or a less-common name happens to
-- finish inside the timeout, which is why filtering appeared to "fix" it.
--
-- Fix: split the count out of the data query (a plain count(*) needs no
-- sort at all), and for name searches, find the top-N *ids* per rank tier
-- with an inner LIMIT before joining back to full rows — so the amount of
-- work is bounded by page size, not by how many rows match.
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
language plpgsql
stable
-- Belt-and-suspenders: even a plain count(*) over an unfiltered ~850k-row
-- table can occasionally run past Supabase's default role-level timeout
-- under load. This override applies only for the duration of this
-- function's execution.
set statement_timeout = '15s'
as $$
declare
  v_total bigint;
  -- Cap counting work for very broad matches (no filters at all, or a
  -- common name) so the query can never run long regardless of how many
  -- rows actually match. Set comfortably above the whole table's current
  -- size (~850k) so the real total always displays — the cap is a safety
  -- net against a truly runaway future table, not a normal-case ceiling.
  -- Raise this further if student_results grows past it. Now that
  -- search_indexes.sql's trigram/btree indexes exist, a plain count(*)
  -- (no sort, unlike the old count(*) over() bug) stays well inside the
  -- statement_timeout below even at this size.
  v_count_cap constant int := 2000000;
begin
  select count(*) into v_total
  from (
    select 1
    from student_results s
    where
      (p_roll_number is null or s.roll_number = p_roll_number)
      and (p_name is null or s.name ilike '%' || p_name || '%')
      and (p_board is null or s.board ilike '%' || p_board || '%')
      and (p_class is null or s.class = p_class)
      and (p_year is null or s.year = p_year)
      and (p_min_marks is null or s.marks >= p_min_marks)
      and (p_max_marks is null or s.marks <= p_max_marks)
    limit v_count_cap
  ) capped;

  if p_name is not null then
    return query
    with ranked_ids as (
      (
        select s.id, 0 as rnk
        from student_results s
        where
          lower(s.name) = lower(p_name)
          and (p_roll_number is null or s.roll_number = p_roll_number)
          and (p_board is null or s.board ilike '%' || p_board || '%')
          and (p_class is null or s.class = p_class)
          and (p_year is null or s.year = p_year)
          and (p_min_marks is null or s.marks >= p_min_marks)
          and (p_max_marks is null or s.marks <= p_max_marks)
        order by s.roll_number
        limit (p_offset + p_limit)
      )
      union all
      (
        select s.id, 1 as rnk
        from student_results s
        where
          lower(s.name) like lower(p_name) || '%'
          and lower(s.name) <> lower(p_name)
          and (p_roll_number is null or s.roll_number = p_roll_number)
          and (p_board is null or s.board ilike '%' || p_board || '%')
          and (p_class is null or s.class = p_class)
          and (p_year is null or s.year = p_year)
          and (p_min_marks is null or s.marks >= p_min_marks)
          and (p_max_marks is null or s.marks <= p_max_marks)
        order by s.roll_number
        limit (p_offset + p_limit)
      )
      union all
      (
        select s.id, 2 as rnk
        from student_results s
        where
          s.name ilike '%' || p_name || '%'
          and lower(s.name) not like lower(p_name) || '%'
          and (p_roll_number is null or s.roll_number = p_roll_number)
          and (p_board is null or s.board ilike '%' || p_board || '%')
          and (p_class is null or s.class = p_class)
          and (p_year is null or s.year = p_year)
          and (p_min_marks is null or s.marks >= p_min_marks)
          and (p_max_marks is null or s.marks <= p_max_marks)
        order by s.roll_number
        limit (p_offset + p_limit)
      )
    )
    select to_jsonb(s) as record, v_total as total_count
    from ranked_ids r
    join student_results s on s.id = r.id
    order by r.rnk, s.roll_number
    limit p_limit offset p_offset;
  else
    return query
    select to_jsonb(s) as record, v_total as total_count
    from student_results s
    where
      (p_roll_number is null or s.roll_number = p_roll_number)
      and (p_board is null or s.board ilike '%' || p_board || '%')
      and (p_class is null or s.class = p_class)
      and (p_year is null or s.year = p_year)
      and (p_min_marks is null or s.marks >= p_min_marks)
      and (p_max_marks is null or s.marks <= p_max_marks)
    order by s.roll_number
    limit p_limit offset p_offset;
  end if;
end;
$$;

-- PostgREST (which supabase-js talks to) needs explicit execute grants.
grant execute on function search_students(
  bigint, text, text, int, int, int, int, int, int
) to anon, authenticated;
