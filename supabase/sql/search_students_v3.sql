-- Run this once in the Supabase SQL Editor (Project → SQL Editor → New query).
-- I can't run it from the app: the client only has the anon key, which can't
-- create functions or materialized views. This needs the project owner's
-- SQL Editor access. Until it runs, the Search page will say so explicitly
-- rather than silently showing "no records".
--
-- WHY A NEW FUNCTION INSTEAD OF EDITING search_students():
-- The Excel/Sheets-style column filters let a user tick SEVERAL values in one
-- column at once ("Lahore" AND "Multan" AND "Sargodha"). search_students()
-- takes one scalar per column (p_board text), so it cannot express that. This
-- function takes arrays instead. The old function is left in place and
-- untouched so anything still calling it keeps working.
--
-- It also adds sorting, because clicking a column header to sort is half of
-- what makes a filter feel like a spreadsheet. Sorting must happen in the
-- database for the same reason ranking does: sorting the 25 rows that already
-- came back only reorders that page, it doesn't find the true top 25.
--
-- Everything that made search_students() fast is kept:
--   * the count is a separate plain count(*) (no sort), capped by v_count_cap
--     so a filterless query can't run away;
--   * for a name search, the top-N ids per rank tier are found with an inner
--     LIMIT before joining back to full rows, so the work is bounded by page
--     size rather than by how many rows match.
-- See search_students.sql for the full history of why those two things matter,
-- and search_indexes.sql for the trigram/btree indexes they depend on.

create or replace function search_students_v3(
  p_roll_number bigint default null,
  p_name text default null,
  p_boards text[] default null,
  p_classes int[] default null,
  p_years int[] default null,
  p_min_marks int default null,
  p_max_marks int default null,
  p_sort_column text default null,
  p_sort_dir text default 'asc',
  p_limit int default 25,
  p_offset int default 0
)
returns table (
  record jsonb,
  total_count bigint
)
language plpgsql
stable
set statement_timeout = '15s'
as $$
declare
  v_total bigint;
  v_count_cap constant int := 2000000;
  v_sort text;
  v_dir text;
  v_order text;
  -- Whitelist. p_sort_column is interpolated into dynamic SQL below, so it
  -- must never be taken from the caller unchecked — anything not in this list
  -- falls back to roll_number.
  v_allowed constant text[] := array[
    'roll_number', 'name', 'marks', 'board', 'group', 'class', 'year'
  ];
begin
  -- Empty arrays mean "no filter", same as null. The client sends [] when a
  -- column's filter menu is open but nothing is ticked; treating that as
  -- "match nothing" would be surprising.
  if p_boards is not null and cardinality(p_boards) = 0 then p_boards := null; end if;
  if p_classes is not null and cardinality(p_classes) = 0 then p_classes := null; end if;
  if p_years is not null and cardinality(p_years) = 0 then p_years := null; end if;

  if p_sort_column is not null and p_sort_column = any(v_allowed) then
    v_sort := p_sort_column;
  else
    v_sort := 'roll_number';
  end if;
  v_dir := case when lower(coalesce(p_sort_dir, 'asc')) = 'desc' then 'desc' else 'asc' end;
  -- NULLS LAST in both directions: a blank name or missing marks should sink
  -- to the bottom whichever way the user sorts, the way a spreadsheet does.
  v_order := format('%I %s nulls last', v_sort, v_dir);

  select count(*) into v_total
  from (
    select 1
    from student_results s
    where
      (p_roll_number is null or s.roll_number = p_roll_number)
      and (p_name is null or s.name ilike '%' || p_name || '%')
      and (p_boards is null or s.board = any(p_boards))
      and (p_classes is null or s.class = any(p_classes))
      and (p_years is null or s.year = any(p_years))
      and (p_min_marks is null or s.marks >= p_min_marks)
      and (p_max_marks is null or s.marks <= p_max_marks)
    limit v_count_cap
  ) capped;

  -- Ranked path: a name search with no explicit sort chosen. Exact matches
  -- first, then starts-with, then contains — so searching "ALI" surfaces the
  -- student actually called ALI on page 1 instead of burying them behind
  -- every ALIYA and MUHAMMAD ALI in the table.
  if p_name is not null and p_sort_column is null then
    return query
    with ranked_ids as (
      (
        select s.id, 0 as rnk
        from student_results s
        where
          lower(s.name) = lower(p_name)
          and (p_roll_number is null or s.roll_number = p_roll_number)
          and (p_boards is null or s.board = any(p_boards))
          and (p_classes is null or s.class = any(p_classes))
          and (p_years is null or s.year = any(p_years))
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
          and (p_boards is null or s.board = any(p_boards))
          and (p_classes is null or s.class = any(p_classes))
          and (p_years is null or s.year = any(p_years))
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
          and (p_boards is null or s.board = any(p_boards))
          and (p_classes is null or s.class = any(p_classes))
          and (p_years is null or s.year = any(p_years))
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
    -- Plain path: order by whichever column the user clicked. Dynamic SQL is
    -- needed because ORDER BY can't be parameterised; v_order was built from
    -- the whitelist above via format(%I), so it is safe to interpolate.
    return query execute format(
      'select to_jsonb(s) as record, $1 as total_count
         from student_results s
        where ($2 is null or s.roll_number = $2)
          and ($3 is null or s.name ilike ''%%'' || $3 || ''%%'')
          and ($4 is null or s.board = any($4))
          and ($5 is null or s.class = any($5))
          and ($6 is null or s.year = any($6))
          and ($7 is null or s.marks >= $7)
          and ($8 is null or s.marks <= $8)
        order by %s
        limit $9 offset $10',
      v_order
    )
    using v_total, p_roll_number, p_name, p_boards, p_classes, p_years,
          p_min_marks, p_max_marks, p_limit, p_offset;
  end if;
end;
$$;

grant execute on function search_students_v3(
  bigint, text, text[], int[], int[], int, int, text, text, int, int
) to anon, authenticated;


-- ---------------------------------------------------------------------
-- FACET VALUES for the filter dropdowns.
--
-- A spreadsheet's filter menu lists the values actually present in the
-- column, with counts. Computing that live would mean a GROUP BY over the
-- whole table every time a menu opens — the single most expensive thing this
-- UI could do. These columns only change when a gazette is uploaded, so the
-- answer is precomputed here and read as a few dozen rows.
--
-- REFRESH IT AFTER EVERY UPLOAD, or new boards/years won't appear in the
-- filter menus:
--     refresh materialized view student_facets;
create materialized view if not exists student_facets as
select
  s.board,
  s.class,
  s.year,
  count(*)::bigint as cnt
from student_results s
group by s.board, s.class, s.year;

create index if not exists idx_student_facets_board on student_facets (board);

grant select on student_facets to anon, authenticated;


-- ---------------------------------------------------------------------
-- Index supporting the marks range filter. search_indexes.sql covers class,
-- year, roll_number and trigrams on name/board, but nothing served
-- `marks >= x and marks <= y`, so that filter fell back to a scan.
create index if not exists idx_student_results_marks on student_results (marks);

-- Serves the common "board + class + year" combination in one index scan.
create index if not exists idx_student_results_board_class_year
  on student_results (board, class, year);
