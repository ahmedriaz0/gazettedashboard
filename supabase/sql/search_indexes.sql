-- Run this once in the Supabase SQL Editor, same place as search_students.sql.
--
-- Why: `ilike '%term%'` has a leading wildcard, so a normal btree index on
-- `name`/`board` can't be used — Postgres falls back to a full sequential
-- scan of the whole table on every search, and search_students()'s
-- `count(*) over()` needs that full scan to finish just to compute
-- total_count. On a large table that occasionally exceeds Supabase's
-- statement_timeout ("canceling statement due to statement timeout").
--
-- pg_trgm's GIN index supports ILIKE with wildcards on both ends, so the
-- planner can jump straight to matching rows instead of scanning everything.

create extension if not exists pg_trgm;

create index if not exists idx_student_results_name_trgm
  on student_results using gin (name gin_trgm_ops);

create index if not exists idx_student_results_board_trgm
  on student_results using gin (board gin_trgm_ops);

-- Cheap to add, help the exact-match/eq filters and the default
-- roll_number ordering when no name filter is given.
create index if not exists idx_student_results_class on student_results (class);
create index if not exists idx_student_results_year on student_results (year);
create index if not exists idx_student_results_roll_number on student_results (roll_number);
