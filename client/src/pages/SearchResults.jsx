import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
} from '@tanstack/react-table';
import { supabase } from '../supabaseClient';

const PAGE_SIZE = 25;

// Must match v_count_cap in supabase/sql/search_students_v3.sql — the RPC caps
// counting work at this many rows so a broad search (no filters, or a very
// common name) can't time out. Past this the total is a floor, not exact.
const COUNT_CAP = 2000000;

// Fallback lists used only if the student_facets materialized view isn't
// there yet. The real menus are built from the values actually present in the
// data — see supabase/sql/search_students_v3.sql.
const FALLBACK_BOARDS = [
  'BISE Lahore', 'BISE Faisalabad', 'BISE Rawalpindi', 'BISE Multan',
  'BISE Gujranwala', 'BISE Sargodha', 'BISE Bahawalpur', 'BISE Sahiwal',
  'BISE DG Khan',
];
const FALLBACK_CLASSES = [9, 10, 11, 12];

const SETUP_HINT =
  'The database function search_students_v3 is missing. Run ' +
  'supabase/sql/search_students_v3.sql once in the Supabase SQL Editor, ' +
  'then reload this page.';

/* ------------------------------------------------------------------ *
 * Filtering runs in Postgres, never in the browser.
 *
 * TanStack Table is in fully manual mode here (manualFiltering /
 * manualSorting / manualPagination): it owns the filter, sort and page
 * STATE and renders the header menus, but every actual comparison happens
 * in the database against the indexes in supabase/sql/. With ~850k rows,
 * the client-side filter row models would have to download the entire
 * table to work, which is the one thing this UI must not do — so
 * getFilteredRowModel/getSortedRowModel are deliberately NOT installed.
 * ------------------------------------------------------------------ */

export default function SearchResults() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState('');
  const [totalCount, setTotalCount] = useState(0);
  const [facets, setFacets] = useState(null);

  const [sorting, setSorting] = useState([]);
  const [columnFilters, setColumnFilters] = useState([]);
  const [pagination, setPagination] = useState({ pageIndex: 0, pageSize: PAGE_SIZE });

  // Load the facet values (the distinct board/class/year values, with counts)
  // that populate the tick-list menus. Precomputed view, a few dozen rows.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const { data, error } = await supabase
        .from('student_facets')
        .select('board, class, year, cnt');
      if (cancelled) return;
      if (error || !data) {
        setFacets({
          board: FALLBACK_BOARDS.map((v) => ({ value: v, count: null })),
          class: FALLBACK_CLASSES.map((v) => ({ value: v, count: null })),
          year: yearFallback().map((v) => ({ value: v, count: null })),
        });
        return;
      }
      setFacets(buildFacets(data));
    })();
    return () => { cancelled = true; };
  }, []);

  const filterMap = useMemo(() => {
    const m = {};
    for (const f of columnFilters) m[f.id] = f.value;
    return m;
  }, [columnFilters]);

  const fetchRows = useCallback(async () => {
    setLoading(true);
    setErrorMsg('');

    const marks = filterMap.marks || {};
    const sort = sorting[0];

    const { data, error } = await supabase.rpc('search_students_v3', {
      p_roll_number: toInt(filterMap.roll_number),
      p_name: (filterMap.name || '').trim() || null,
      p_boards: emptyToNull(filterMap.board),
      p_classes: emptyToNull(filterMap.class),
      p_years: emptyToNull(filterMap.year),
      p_min_marks: toInt(marks.min),
      p_max_marks: toInt(marks.max),
      p_sort_column: sort ? sort.id : null,
      p_sort_dir: sort && sort.desc ? 'desc' : 'asc',
      p_limit: pagination.pageSize,
      p_offset: pagination.pageIndex * pagination.pageSize,
    });

    if (error) {
      const missing =
        error.code === 'PGRST202' || /search_students_v3/i.test(error.message || '');
      setErrorMsg(missing ? SETUP_HINT : error.message);
      setRows([]);
      setTotalCount(0);
      setLoading(false);
      return;
    }

    setRows((data || []).map((r) => r.record));
    setTotalCount(data && data.length ? Number(data[0].total_count) : 0);
    setLoading(false);
  }, [filterMap, sorting, pagination]);

  useEffect(() => { fetchRows(); }, [fetchRows]);

  // Any filter or sort change sends the user back to page 1 — staying on
  // page 40 of a result set that just shrank to 3 pages shows nothing.
  const resetToFirstPage = () => setPagination((p) => ({ ...p, pageIndex: 0 }));

  const setFilter = (id, value) => {
    setColumnFilters((prev) => {
      const rest = prev.filter((f) => f.id !== id);
      return isEmptyFilter(value) ? rest : [...rest, { id, value }];
    });
    resetToFirstPage();
  };

  const setSort = (id, dir) => {
    setSorting(dir === null ? [] : [{ id, desc: dir === 'desc' }]);
    resetToFirstPage();
  };

  const clearAll = () => {
    setColumnFilters([]);
    setSorting([]);
    resetToFirstPage();
  };

  const columns = useMemo(() => buildColumns(facets), [facets]);

  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting, columnFilters, pagination },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onPaginationChange: setPagination,
    manualFiltering: true,
    manualSorting: true,
    manualPagination: true,
    pageCount: Math.max(1, Math.ceil(totalCount / pagination.pageSize)),
    getCoreRowModel: getCoreRowModel(),
  });

  const pageStats = useMemo(() => {
    const vals = rows.map((r) => r.marks).filter((m) => typeof m === 'number');
    if (!vals.length) return { avg: '—', max: '—', min: '—' };
    const sum = vals.reduce((a, b) => a + b, 0);
    return {
      avg: Math.round(sum / vals.length),
      max: Math.max(...vals),
      min: Math.min(...vals),
    };
  }, [rows]);

  const totalPages = table.getPageCount();
  const activeCount = columnFilters.length + (sorting.length ? 1 : 0);

  return (
    <div className="min-h-screen bg-bg p-4 sm:p-6 md:p-10">
      <div className="mx-auto max-w-7xl space-y-5">
        <div className="border-b border-border pb-4">
          <h1 className="text-2xl font-semibold tracking-tight text-ink sm:text-3xl">
            Student Records
          </h1>
          <p className="mt-1 text-sm text-ink-muted">
            Filter and sort from the column headers, the way you would in a spreadsheet.
          </p>
        </div>

        {errorMsg && (
          <div className="border border-danger bg-danger-bg px-4 py-3 text-sm text-danger">
            {errorMsg}
          </div>
        )}

        <div className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-4">
          <StatTile
            label="Matching Records"
            value={totalCount >= COUNT_CAP
              ? `${totalCount.toLocaleString()}+`
              : totalCount.toLocaleString()}
          />
          <StatTile label="Highest (this page)" value={pageStats.max} />
          <StatTile label="Lowest (this page)" value={pageStats.min} />
          <StatTile label="Average (this page)" value={pageStats.avg} />
        </div>

        <ActiveFilterBar
          columnFilters={columnFilters}
          sorting={sorting}
          columns={columns}
          onRemoveFilter={(id) => setFilter(id, undefined)}
          onClearSort={() => setSorting([])}
          onClearAll={clearAll}
          activeCount={activeCount}
        />

        <div className="border border-border bg-surface">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left">
              <thead>
                {table.getHeaderGroups().map((hg) => (
                  <tr key={hg.id} className="border-b border-border">
                    {hg.headers.map((header) => (
                      <HeaderCell
                        key={header.id}
                        header={header}
                        filterValue={filterMap[header.column.id]}
                        sortDir={
                          sorting[0] && sorting[0].id === header.column.id
                            ? (sorting[0].desc ? 'desc' : 'asc')
                            : null
                        }
                        onSort={setSort}
                        onFilter={setFilter}
                      />
                    ))}
                  </tr>
                ))}
              </thead>
              <tbody className="divide-y divide-border text-sm">
                {loading ? (
                  <tr>
                    <td colSpan={columns.length} className="py-16 text-center text-sm text-ink-muted">
                      Fetching records&hellip;
                    </td>
                  </tr>
                ) : rows.length === 0 ? (
                  <tr>
                    <td colSpan={columns.length} className="py-14 text-center text-ink-faint">
                      {errorMsg ? 'Could not load records.' : 'No matching records found.'}
                    </td>
                  </tr>
                ) : (
                  table.getRowModel().rows.map((row) => (
                    <tr key={row.id} className="hover:bg-surface-muted">
                      {row.getVisibleCells().map((cell) => (
                        <td key={cell.id} className={cellClass(cell.column.id)}>
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </td>
                      ))}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-4 py-3.5 sm:px-5">
            <span className="text-xs text-ink-muted">
              Page <strong className="text-ink">{pagination.pageIndex + 1}</strong> of{' '}
              <strong className="text-ink">{totalPages.toLocaleString()}</strong>
            </span>
            <div className="flex gap-2">
              <PagerButton
                disabled={!table.getCanPreviousPage() || loading}
                onClick={() => table.previousPage()}
              >
                ← Previous
              </PagerButton>
              <PagerButton
                disabled={!table.getCanNextPage() || loading}
                onClick={() => table.nextPage()}
              >
                Next →
              </PagerButton>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------ columns ------------------------------ */

function buildColumns(facets) {
  const opts = (key) => (facets && facets[key]) || [];
  return [
    {
      accessorKey: 'roll_number',
      header: 'Roll No',
      meta: { filterType: 'number', sortKind: 'number', label: 'Roll No' },
      cell: (c) => <span className="font-mono font-medium text-ink">{c.getValue()}</span>,
    },
    {
      accessorKey: 'name',
      header: 'Student Name',
      meta: { filterType: 'text', sortKind: 'text', label: 'Student Name' },
      cell: (c) => <span className="text-ink">{c.getValue() || '—'}</span>,
    },
    {
      accessorKey: 'marks',
      header: 'Marks',
      meta: { filterType: 'range', sortKind: 'number', label: 'Marks' },
      cell: (c) => (
        <span className="font-mono font-semibold text-ink">{c.getValue() ?? '—'}</span>
      ),
    },
    {
      accessorKey: 'board',
      header: 'Board',
      meta: { filterType: 'set', sortKind: 'text', label: 'Board', options: opts('board') },
      cell: (c) => <span className="text-ink-muted">{c.getValue() || '—'}</span>,
    },
    {
      accessorKey: 'group',
      header: 'Group',
      // No filter: search_students_v3 exposes no group predicate (the column
      // is null for every board parsed so far). Sorting still works.
      meta: { filterType: null, sortKind: 'text', label: 'Group' },
      cell: (c) => <span className="text-ink-muted">{c.getValue() || '—'}</span>,
    },
    {
      accessorKey: 'class',
      header: 'Class',
      meta: { filterType: 'set', sortKind: 'number', label: 'Class', options: opts('class'), format: (v) => `${v}th` },
      cell: (c) => (
        <span className="text-ink-muted">{c.getValue() ? `${c.getValue()}th` : '—'}</span>
      ),
    },
    {
      accessorKey: 'year',
      header: 'Year',
      meta: { filterType: 'set', sortKind: 'number', label: 'Year', options: opts('year') },
      cell: (c) => <span className="text-ink-muted">{c.getValue() ?? '—'}</span>,
    },
  ];
}

function cellClass(id) {
  return id === 'roll_number' || id === 'marks'
    ? 'px-4 py-3.5 whitespace-nowrap'
    : 'px-4 py-3.5';
}

/* ---------------------------- header cell ---------------------------- */

function HeaderCell({ header, filterValue, sortDir, onSort, onFilter }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState(null);
  const btnRef = useRef(null);
  const menuRef = useRef(null);
  const col = header.column;
  const meta = col.columnDef.meta || {};
  const hasFilter = !isEmptyFilter(filterValue);

  // The menu is rendered through a portal onto document.body rather than
  // inside the <th>. The table lives in an `overflow-x-auto` wrapper (needed
  // so wide tables scroll on small screens), and any overflow value other
  // than `visible` clips absolutely-positioned descendants — which cut the
  // value list off after its first row. A portal escapes that container
  // entirely, so the menu is positioned in viewport coordinates instead.
  // Coordinates are in DOCUMENT space (rect + scroll offset), and the menu is
  // positioned `absolute`, so it scrolls with the page like a normal element.
  // A `fixed` menu would need a scroll listener to stay attached to its
  // header, and any such listener also fires for scrolls inside the menu's
  // own value list — which is fiddly to get right for no benefit here.
  const place = () => {
    const r = btnRef.current.getBoundingClientRect();
    setPos({
      left: Math.max(8, Math.min(r.left, window.innerWidth - MENU_WIDTH - 8)) + window.scrollX,
      top: r.bottom + 4 + window.scrollY,
    });
  };

  const toggle = () => {
    if (open) return setOpen(false);
    place();
    setOpen(true);
  };

  useEffect(() => {
    if (!open) return;
    const onDown = (e) => {
      if (btnRef.current?.contains(e.target) || menuRef.current?.contains(e.target)) return;
      setOpen(false);
    };
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
    // A resize can move the header out from under the menu; closing is the
    // cheap, predictable answer for a rare event.
    const onResize = () => setOpen(false);
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    window.addEventListener('resize', onResize);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
      window.removeEventListener('resize', onResize);
    };
  }, [open]);

  return (
    <th className="px-4 py-2.5 text-xs font-medium uppercase tracking-wide text-ink-muted">
      <button
        ref={btnRef}
        type="button"
        onClick={toggle}
        aria-haspopup="menu"
        aria-expanded={open}
        className={`flex w-full items-center gap-1.5 whitespace-nowrap py-1 text-left transition-colors hover:text-ink ${
          hasFilter || sortDir ? 'text-ink' : ''
        }`}
      >
        <span>{flexRender(col.columnDef.header, header.getContext())}</span>
        {sortDir && <SortGlyph dir={sortDir} />}
        {hasFilter && <FunnelGlyph />}
        <CaretGlyph open={open} />
      </button>

      {open && pos && createPortal(
        <div
          ref={menuRef}
          style={{ position: 'absolute', left: pos.left, top: pos.top, width: MENU_WIDTH }}
        >
          <ColumnMenu
            meta={meta}
            value={filterValue}
            sortDir={sortDir}
            onSort={(d) => { onSort(col.id, d); setOpen(false); }}
            onApply={(v) => { onFilter(col.id, v); setOpen(false); }}
            onClose={() => setOpen(false)}
          />
        </div>,
        document.body,
      )}
    </th>
  );
}

const MENU_WIDTH = 256;

/* ---------------------------- column menu ---------------------------- */

function ColumnMenu({ meta, value, sortDir, onSort, onApply, onClose }) {
  const type = meta.filterType;
  const isText = type === 'text' || type === 'number';
  const [draft, setDraft] = useState(() => {
    if (type === 'set') return new Set(Array.isArray(value) ? value : []);
    if (type === 'range') return { min: value?.min ?? '', max: value?.max ?? '' };
    return value ?? '';
  });
  const [search, setSearch] = useState('');

  const shown = useMemo(() => {
    const options = meta.options || [];
    const q = search.trim().toLowerCase();
    if (!q) return options;
    return options.filter((o) => String(o.value).toLowerCase().includes(q));
  }, [meta.options, search]);

  const allShownTicked = shown.length > 0 && shown.every((o) => draft.has?.(o.value));

  const apply = () => {
    if (type === 'set') onApply(Array.from(draft));
    else if (type === 'range') {
      const min = draft.min === '' ? undefined : draft.min;
      const max = draft.max === '' ? undefined : draft.max;
      onApply(min === undefined && max === undefined ? undefined : { min, max });
    } else onApply(String(draft).trim() || undefined);
  };

  return (
    <div
      role="menu"
      onKeyDown={(e) => { if (e.key === 'Escape') onClose(); }}
      className="border border-border-strong bg-surface text-xs normal-case tracking-normal shadow-lg"
    >
      <div className="border-b border-border p-1">
        <MenuRow active={sortDir === 'asc'} onClick={() => onSort('asc')}>
          Sort {meta.sortKind === 'text' ? 'A → Z' : 'Low → High'}
        </MenuRow>
        <MenuRow active={sortDir === 'desc'} onClick={() => onSort('desc')}>
          Sort {meta.sortKind === 'text' ? 'Z → A' : 'High → Low'}
        </MenuRow>
        {sortDir && (
          <MenuRow onClick={() => onSort(null)}>Remove sort</MenuRow>
        )}
      </div>

      {type && (
        <>
          <div className="max-h-64 overflow-y-auto p-2.5">
            {type === 'set' && (
              <>
                <input
                  autoFocus
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search values…"
                  className={menuInputClass}
                />
                <div className="mt-2 flex items-center justify-between border-b border-border pb-1.5">
                  <button
                    type="button"
                    onClick={() =>
                      setDraft((d) => {
                        const n = new Set(d);
                        shown.forEach((o) => (allShownTicked ? n.delete(o.value) : n.add(o.value)));
                        return n;
                      })
                    }
                    className="font-medium text-ink hover:underline"
                  >
                    {allShownTicked ? 'Clear all' : 'Select all'}
                  </button>
                  <span className="text-ink-faint">{draft.size} selected</span>
                </div>
                <div className="mt-1.5 space-y-0.5">
                  {shown.length === 0 && (
                    <p className="py-2 text-center text-ink-faint">No values.</p>
                  )}
                  {shown.map((o) => (
                    <label
                      key={String(o.value)}
                      className="flex cursor-pointer items-center gap-2 px-1 py-1 hover:bg-surface-muted"
                    >
                      <input
                        type="checkbox"
                        checked={draft.has(o.value)}
                        onChange={() =>
                          setDraft((d) => {
                            const n = new Set(d);
                            n.has(o.value) ? n.delete(o.value) : n.add(o.value);
                            return n;
                          })
                        }
                        className="h-3.5 w-3.5 accent-ink"
                      />
                      <span className="flex-1 truncate text-ink">
                        {meta.format ? meta.format(o.value) : String(o.value)}
                      </span>
                      {o.count != null && (
                        <span className="font-mono text-ink-faint">{o.count.toLocaleString()}</span>
                      )}
                    </label>
                  ))}
                </div>
              </>
            )}

            {type === 'range' && (
              <div className="flex items-center gap-2">
                <input
                  autoFocus
                  type="number"
                  min="0"
                  placeholder="Min"
                  value={draft.min}
                  onChange={(e) => setDraft((d) => ({ ...d, min: digits(e.target.value) }))}
                  className={menuInputClass}
                />
                <span className="text-ink-faint">to</span>
                <input
                  type="number"
                  min="0"
                  placeholder="Max"
                  value={draft.max}
                  onChange={(e) => setDraft((d) => ({ ...d, max: digits(e.target.value) }))}
                  className={menuInputClass}
                />
              </div>
            )}

            {isText && (
              <input
                autoFocus
                inputMode={type === 'number' ? 'numeric' : 'text'}
                placeholder={type === 'number' ? 'Equals, e.g. 104521' : 'Contains…'}
                value={draft}
                onChange={(e) =>
                  setDraft(type === 'number' ? digits(e.target.value) : e.target.value)
                }
                onKeyDown={(e) => { if (e.key === 'Enter') apply(); }}
                className={menuInputClass}
              />
            )}
          </div>

          <div className="flex justify-end gap-2 border-t border-border p-2">
            <button
              type="button"
              onClick={() => onApply(undefined)}
              className="border border-border px-2.5 py-1 font-medium text-ink-muted transition-colors hover:border-border-strong hover:text-ink"
            >
              Clear
            </button>
            <button
              type="button"
              onClick={apply}
              className="bg-ink px-3 py-1 font-medium text-bg transition-opacity hover:opacity-85"
            >
              Apply
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function MenuRow({ children, onClick, active }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`block w-full px-2.5 py-1.5 text-left transition-colors hover:bg-surface-muted ${
        active ? 'font-semibold text-ink' : 'text-ink-muted'
      }`}
    >
      {children}
    </button>
  );
}

/* -------------------------- active filter bar ------------------------- */

function ActiveFilterBar({
  columnFilters, sorting, columns, onRemoveFilter, onClearSort, onClearAll, activeCount,
}) {
  if (!activeCount) return null;
  const labelOf = (id) => {
    const c = columns.find((c) => c.accessorKey === id);
    return (c && c.meta && c.meta.label) || id;
  };
  return (
    <div className="flex flex-wrap items-center gap-2 border border-border bg-surface-muted px-3 py-2.5">
      <span className="text-xs font-medium uppercase tracking-wide text-ink-muted">
        Filters
      </span>
      {columnFilters.map((f) => (
        <Chip key={f.id} onRemove={() => onRemoveFilter(f.id)}>
          {labelOf(f.id)}: {describeFilter(f.value, columns.find((c) => c.accessorKey === f.id))}
        </Chip>
      ))}
      {sorting.length > 0 && (
        <Chip onRemove={onClearSort}>
          Sorted by {labelOf(sorting[0].id)} {sorting[0].desc ? '↓' : '↑'}
        </Chip>
      )}
      <button
        type="button"
        onClick={onClearAll}
        className="ml-auto text-xs font-medium text-ink underline-offset-2 hover:underline"
      >
        Clear all
      </button>
    </div>
  );
}

function Chip({ children, onRemove }) {
  return (
    <span className="inline-flex items-center gap-1.5 border border-border bg-surface px-2 py-1 text-xs text-ink">
      <span className="max-w-[22rem] truncate">{children}</span>
      <button
        type="button"
        onClick={onRemove}
        aria-label="Remove filter"
        className="text-ink-faint transition-colors hover:text-ink"
      >
        ✕
      </button>
    </span>
  );
}

function describeFilter(value, col) {
  const fmt = col && col.meta && col.meta.format ? col.meta.format : (v) => String(v);
  if (Array.isArray(value)) {
    if (value.length <= 2) return value.map(fmt).join(', ');
    return `${value.length} selected`;
  }
  if (value && typeof value === 'object') {
    const { min, max } = value;
    if (min !== undefined && max !== undefined) return `${min}–${max}`;
    if (min !== undefined) return `≥ ${min}`;
    return `≤ ${max}`;
  }
  return String(value);
}

/* -------------------------------- bits -------------------------------- */

function PagerButton({ children, ...props }) {
  return (
    <button
      {...props}
      className="border border-border px-3.5 py-1.5 text-xs font-medium text-ink-muted transition-colors hover:border-border-strong hover:text-ink disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-border disabled:hover:text-ink-muted"
    >
      {children}
    </button>
  );
}

function StatTile({ label, value }) {
  return (
    <div className="border border-border bg-surface p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">{label}</p>
      <p className="mt-2 font-mono text-2xl font-semibold text-ink sm:text-3xl">{value}</p>
    </div>
  );
}

const SortGlyph = ({ dir }) => <span className="font-mono text-ink">{dir === 'asc' ? '↑' : '↓'}</span>;

const FunnelGlyph = () => (
  <svg viewBox="0 0 12 12" className="h-3 w-3 fill-ink" aria-hidden="true">
    <path d="M1 2h10L7 6.5V11L5 9.5v-3L1 2z" />
  </svg>
);

const CaretGlyph = ({ open }) => (
  <svg
    viewBox="0 0 10 10"
    className={`ml-auto h-2.5 w-2.5 shrink-0 fill-current transition-transform ${open ? 'rotate-180' : ''}`}
    aria-hidden="true"
  >
    <path d="M1 3l4 4 4-4z" />
  </svg>
);

const menuInputClass =
  'w-full min-w-0 border border-border bg-bg px-2 py-1.5 text-xs text-ink placeholder-ink-faint focus:border-border-strong focus:outline-none';

/* ------------------------------- helpers ------------------------------ */

function buildFacets(data) {
  const acc = { board: new Map(), class: new Map(), year: new Map() };
  for (const row of data) {
    for (const key of ['board', 'class', 'year']) {
      const v = row[key];
      if (v === null || v === undefined) continue;
      acc[key].set(v, (acc[key].get(v) || 0) + Number(row.cnt || 0));
    }
  }
  const sortVals = (m) =>
    Array.from(m, ([value, count]) => ({ value, count })).sort((a, b) =>
      typeof a.value === 'number' ? a.value - b.value : String(a.value).localeCompare(String(b.value))
    );
  return { board: sortVals(acc.board), class: sortVals(acc.class), year: sortVals(acc.year) };
}

function yearFallback() {
  const now = new Date().getFullYear();
  const out = [];
  for (let y = now; y >= 2020; y--) out.push(y);
  return out;
}

const digits = (s) => s.replace(/[^0-9]/g, '');

function toInt(v) {
  if (v === undefined || v === null || v === '') return null;
  const n = parseInt(v, 10);
  return Number.isNaN(n) ? null : Math.max(0, n);
}

function emptyToNull(v) {
  return Array.isArray(v) && v.length ? v : null;
}

function isEmptyFilter(v) {
  if (v === undefined || v === null || v === '') return true;
  if (Array.isArray(v)) return v.length === 0;
  if (typeof v === 'object') return v.min === undefined && v.max === undefined;
  return false;
}
