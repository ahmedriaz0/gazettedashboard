import React, { useState, useEffect } from 'react';
import { supabase } from '../supabaseClient';

const PAGE_SIZE = 25;

// Must match v_count_cap in supabase/sql/search_students.sql — the RPC caps
// counting work at this many rows so a broad search (no filters, or a very
// common name) can't time out. Past this the total is a floor, not exact.
// Set well above the table's real size so normal use always shows the exact
// total; it's a safety net against a runaway future table, not a normal ceiling.
const COUNT_CAP = 2000000;

const PUNJAB_BOARDS = [
  'BISE Lahore',
  'BISE Faisalabad',
  'BISE Rawalpindi',
  'BISE Multan',
  'BISE Gujranwala',
  'BISE Sargodha',
  'BISE Bahawalpur',
  'BISE Sahiwal',
  'BISE DG Khan'
];

export default function SearchResults() {
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);

  // Stats State
  const [stats, setStats] = useState({ avg: 0, max: 0, min: 0 });

  // Filter States
  const [rollNumber, setRollNumber] = useState('');
  const [name, setName] = useState('');
  const [board, setBoard] = useState('');
  const [year, setYear] = useState('');
  const [classNum, setClassNum] = useState('');
  const [minMarks, setMinMarks] = useState('');
  const [maxMarks, setMaxMarks] = useState('');

  const currentYear = new Date().getFullYear();
  const yearsList = [];
  for (let y = currentYear; y >= 2020; y--) {
    yearsList.push(y);
  }

  const handleMinMarksChange = (e) => {
    const val = e.target.value;
    if (val === '') return setMinMarks('');
    setMinMarks(Math.max(0, parseInt(val, 10) || 0).toString());
  };

  const handleMaxMarksChange = (e) => {
    const val = e.target.value;
    if (val === '') return setMaxMarks('');
    setMaxMarks(Math.max(0, parseInt(val, 10) || 0).toString());
  };

  const fetchResults = async (page = 1) => {
    setLoading(true);
    const offset = (page - 1) * PAGE_SIZE;

    // Ranking (exact match > starts-with > contains) has to happen in the
    // database, before LIMIT/OFFSET — a client-side sort can only reorder
    // the one page of rows that already came back, so an exact match
    // outside that page would never surface. See supabase/sql/search_students.sql.
    const { data, error } = await supabase.rpc('search_students', {
      p_roll_number: rollNumber.trim() ? parseInt(rollNumber.trim(), 10) : null,
      p_name: name.trim() || null,
      p_board: board.trim() || null,
      p_class: classNum ? parseInt(classNum, 10) : null,
      p_year: year ? parseInt(year, 10) : null,
      p_min_marks: minMarks !== '' ? Math.max(0, parseInt(minMarks, 10)) : null,
      p_max_marks: maxMarks !== '' ? Math.max(0, parseInt(maxMarks, 10)) : null,
      p_limit: PAGE_SIZE,
      p_offset: offset,
    });

    if (error) {
      alert("Error fetching records: " + error.message);
      setLoading(false);
      return;
    }

    const rows = (data || []).map((row) => row.record);
    const total = data && data.length > 0 ? Number(data[0].total_count) : 0;

    setResults(rows);
    setTotalCount(total);
    setCurrentPage(page);

    if (rows.length > 0) {
      const validMarks = rows.map((r) => r.marks).filter((m) => typeof m === 'number');
      if (validMarks.length > 0) {
        const sum = validMarks.reduce((acc, val) => acc + val, 0);
        setStats({
          avg: Math.round(sum / validMarks.length),
          max: Math.max(...validMarks),
          min: Math.min(...validMarks),
        });
      }
    } else {
      setStats({ avg: 0, max: 0, min: 0 });
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchResults(1);
  }, []);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    fetchResults(1);
  };

  const handleReset = () => {
    setRollNumber('');
    setName('');
    setBoard('');
    setYear('');
    setClassNum('');
    setMinMarks('');
    setMaxMarks('');
    fetchResults(1);
  };

  const totalPages = Math.ceil(totalCount / PAGE_SIZE) || 1;

  return (
    <div className="min-h-screen bg-bg p-4 sm:p-6 md:p-10">
      <div className="mx-auto max-w-7xl space-y-6">

        {/* Page Header */}
        <div className="border-b border-border pb-4">
          <h1 className="text-2xl font-semibold tracking-tight text-ink sm:text-3xl">
            Student Records
          </h1>
          <p className="mt-1 text-sm text-ink-muted">
            Search and analyze performance statistics across BISE educational board examinations.
          </p>
        </div>

        {/* Filter Panel */}
        <div className="border border-border bg-surface p-4 sm:p-5">
          <form onSubmit={handleSearchSubmit} className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-4 lg:grid-cols-6">
            <Field label="Roll Number">
              <input
                placeholder="e.g. 104521"
                type="text"
                inputMode="numeric"
                value={rollNumber}
                onChange={(e) => setRollNumber(e.target.value.replace(/[^0-9]/g, ''))}
                className={inputClass}
              />
            </Field>

            <Field label="Student Name">
              <input
                placeholder="e.g. Ahmed Raza"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value.replace(/[^a-zA-Z\s.]/g, ''))}
                className={inputClass}
              />
            </Field>

            <Field label="Board">
              <select value={board} onChange={(e) => setBoard(e.target.value)} className={inputClass}>
                <option value="">All Boards</option>
                {PUNJAB_BOARDS.map((b) => (
                  <option key={b} value={b}>{b}</option>
                ))}
              </select>
            </Field>

            <Field label="Class">
              <select value={classNum} onChange={(e) => setClassNum(e.target.value)} className={inputClass}>
                <option value="">All Classes</option>
                <option value="9">9th Class (SSC-I)</option>
                <option value="10">10th Class (SSC-II)</option>
                <option value="11">11th Class (HSSC-I)</option>
                <option value="12">12th Class (HSSC-II)</option>
              </select>
            </Field>

            <Field label="Year">
              <select value={year} onChange={(e) => setYear(e.target.value)} className={inputClass}>
                <option value="">All Years</option>
                {yearsList.map((y) => (
                  <option key={y} value={y}>{y}</option>
                ))}
              </select>
            </Field>

            <Field label="Marks Range">
              <div className="flex gap-2">
                <input
                  placeholder="Min"
                  type="number"
                  min="0"
                  value={minMarks}
                  onChange={handleMinMarksChange}
                  className={`w-1/2 ${inputClass}`}
                />
                <input
                  placeholder="Max"
                  type="number"
                  min="0"
                  value={maxMarks}
                  onChange={handleMaxMarksChange}
                  className={`w-1/2 ${inputClass}`}
                />
              </div>
            </Field>

            <div className="flex justify-end gap-2 border-t border-border pt-3 lg:col-span-6">
              <button
                type="button"
                onClick={handleReset}
                className="border border-border px-4 py-2 text-xs font-medium text-ink-muted transition-colors hover:border-border-strong hover:text-ink sm:text-sm"
              >
                Reset
              </button>
              <button
                type="submit"
                className="bg-ink px-5 py-2 text-xs font-medium text-bg transition-opacity hover:opacity-85 sm:text-sm"
              >
                Search Records
              </button>
            </div>
          </form>
        </div>

        {/* Stat Strip */}
        <div className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-4">
          <StatTile
            label="Total Records"
            value={totalCount >= COUNT_CAP ? `${totalCount.toLocaleString()}+` : totalCount.toLocaleString()}
          />
          <StatTile label="Highest Marks" value={stats.max} />
          <StatTile label="Lowest Marks" value={stats.min} />
          <StatTile label="Average Marks" value={stats.avg} />
        </div>

        {/* Results Table */}
        <div className="border border-border bg-surface">
          {loading ? (
            <div className="py-16 text-center text-sm text-ink-muted">
              Fetching records&hellip;
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-left">
                  <thead>
                    <tr className="border-b border-border text-xs font-medium uppercase tracking-wide text-ink-muted">
                      <th className="px-4 py-3">Roll No</th>
                      <th className="px-4 py-3">Student Name</th>
                      <th className="px-4 py-3">Marks</th>
                      <th className="px-4 py-3">Board</th>
                      <th className="px-4 py-3">Group</th>
                      <th className="px-4 py-3">Class</th>
                      <th className="px-4 py-3">Year</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border text-sm">
                    {results.length === 0 ? (
                      <tr>
                        <td colSpan="7" className="py-14 text-center text-ink-faint">
                          No matching records found.
                        </td>
                      </tr>
                    ) : (
                      results.map((row, index) => (
                        <tr key={row.id || index} className="hover:bg-surface-muted">
                          <td className="px-4 py-3.5 font-mono font-medium text-ink">{row.roll_number}</td>
                          <td className="px-4 py-3.5 text-ink">{row.name || '—'}</td>
                          <td className="px-4 py-3.5 font-mono font-semibold text-ink">{row.marks ?? '—'}</td>
                          <td className="px-4 py-3.5 text-ink-muted">{row.board || '—'}</td>
                          <td className="px-4 py-3.5 text-ink-muted">{row.group || '—'}</td>
                          <td className="px-4 py-3.5 text-ink-muted">{row.class ? `${row.class}th` : '—'}</td>
                          <td className="px-4 py-3.5 text-ink-muted">{row.year ?? '—'}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>

              {/* Pagination Controls */}
              <div className="flex items-center justify-between border-t border-border px-4 py-3.5 sm:px-5">
                <span className="text-xs text-ink-muted">
                  Page <strong className="text-ink">{currentPage}</strong> of <strong className="text-ink">{totalPages}</strong>
                </span>

                <div className="flex gap-2">
                  <button
                    disabled={currentPage <= 1 || loading}
                    onClick={() => fetchResults(currentPage - 1)}
                    className="border border-border px-3.5 py-1.5 text-xs font-medium text-ink-muted transition-colors hover:border-border-strong hover:text-ink disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-border disabled:hover:text-ink-muted"
                  >
                    ← Previous
                  </button>

                  <button
                    disabled={currentPage >= totalPages || loading}
                    onClick={() => fetchResults(currentPage + 1)}
                    className="border border-border px-3.5 py-1.5 text-xs font-medium text-ink-muted transition-colors hover:border-border-strong hover:text-ink disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-border disabled:hover:text-ink-muted"
                  >
                    Next →
                  </button>
                </div>
              </div>
            </>
          )}
        </div>

      </div>
    </div>
  );
}

const inputClass =
  'w-full border border-border bg-bg px-3 py-2 text-sm text-ink placeholder-ink-faint transition-colors focus:border-border-strong focus:outline-none';

function Field({ label, children }) {
  return (
    <div>
      <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-ink-muted">
        {label}
      </label>
      {children}
    </div>
  );
}

function StatTile({ label, value }) {
  return (
    <div className="border border-border bg-surface p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">
        {label}
      </p>
      <p className="mt-2 font-mono text-2xl font-semibold text-ink sm:text-3xl">
        {value}
      </p>
    </div>
  );
}
