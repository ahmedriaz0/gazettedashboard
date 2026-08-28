import React, { useState, useEffect } from 'react';
import { supabase } from '../supabaseClient';

const PAGE_SIZE = 25;

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
    const from = (page - 1) * PAGE_SIZE;
    const to = from + PAGE_SIZE - 1;

    let query = supabase.from('student_results').select('*', { count: 'exact' });

    if (rollNumber.trim()) query = query.eq('roll_number', parseInt(rollNumber.trim(), 10));
    if (name.trim()) query = query.ilike('name', `%${name.trim()}%`);
    if (board.trim()) query = query.ilike('board', `%${board.trim()}%`);
    if (year) query = query.eq('year', parseInt(year, 10));
    if (classNum) query = query.eq('class', parseInt(classNum, 10));
    if (minMarks !== '') query = query.gte('marks', Math.max(0, parseInt(minMarks, 10)));
    if (maxMarks !== '') query = query.lte('marks', Math.max(0, parseInt(maxMarks, 10)));

    query = query.range(from, to).order('roll_number', { ascending: true });

    const { data, count, error } = await query;

    if (error) {
      alert("Error fetching records: " + error.message);
    } else {
      let sortedData = data || [];
      if (name.trim()) {
        const queryTerm = name.trim().toLowerCase();
        sortedData = [...sortedData].sort((a, b) => {
          const nameA = (a.name || '').toLowerCase();
          const nameB = (b.name || '').toLowerCase();
          const aStartsWith = nameA.startsWith(queryTerm);
          const bStartsWith = nameB.startsWith(queryTerm);

          if (aStartsWith && !bStartsWith) return -1;
          if (!aStartsWith && bStartsWith) return 1;
          return nameA.localeCompare(nameB);
        });
      }

      setResults(sortedData);
      setTotalCount(count || 0);
      setCurrentPage(page);

      if (sortedData.length > 0) {
        const validMarks = sortedData.map((r) => r.marks).filter((m) => typeof m === 'number');
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
    <div className="min-h-screen bg-slate-50 p-6 md:p-10 font-sans">
      <div className="max-w-7xl mx-auto space-y-6">
        
        {/* Page Header */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between pb-2 border-b border-slate-200">
          <div>
            <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">
              Gazette Student Records
            </h1>
            <p className="text-slate-500 text-sm mt-1">
              Search and analyze performance statistics across BISE educational board examinations.
            </p>
          </div>
        </div>

        {/* Filter Card */}
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5 transition-all">
          <form onSubmit={handleSearchSubmit} className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            {/* Roll Number - Digits Only */}
            <input
              placeholder="Roll Number"
              type="text"
              inputMode="numeric"
              value={rollNumber}
              onChange={(e) => setRollNumber(e.target.value.replace(/[^0-9]/g, ''))}
              className="px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition"
            />

            {/* Student Name - Alphabets Only */}
            <input
              placeholder="Student Name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value.replace(/[^a-zA-Z\s.]/g, ''))}
              className="px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition"
            />

            <select
              value={board}
              onChange={(e) => setBoard(e.target.value)}
              className="px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition"
            >
              <option value="">All Boards</option>
              {PUNJAB_BOARDS.map((b) => (
                <option key={b} value={b}>{b}</option>
              ))}
            </select>

            <select
              value={classNum}
              onChange={(e) => setClassNum(e.target.value)}
              className="px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition"
            >
              <option value="">All Classes</option>
              <option value="9">9th Class (SSC-I)</option>
              <option value="10">10th Class (SSC-II)</option>
              <option value="11">11th Class (HSSC-I)</option>
              <option value="12">12th Class (HSSC-II)</option>
            </select>

            <select
              value={year}
              onChange={(e) => setYear(e.target.value)}
              className="px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition"
            >
              <option value="">All Years</option>
              {yearsList.map((y) => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>

            <div className="flex gap-2">
              <input
                placeholder="Min Marks"
                type="number"
                min="0"
                value={minMarks}
                onChange={handleMinMarksChange}
                className="w-1/2 px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition"
              />
              <input
                placeholder="Max Marks"
                type="number"
                min="0"
                value={maxMarks}
                onChange={handleMaxMarksChange}
                className="w-1/2 px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition"
              />
            </div>

            <div className="lg:col-span-6 flex justify-end gap-2 pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={handleReset}
                className="px-4 py-2 border border-slate-300 text-slate-600 rounded-lg text-sm font-medium hover:bg-slate-100 transition"
              >
                Reset
              </button>
              <button
                type="submit"
                className="px-5 py-2 bg-blue-600 text-white rounded-lg text-sm font-semibold hover:bg-blue-700 shadow-sm transition"
              >
                Search Records
              </button>
            </div>
          </form>
        </div>

        {/* Metric Cards Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Total Records" value={totalCount.toLocaleString()} badgeColor="bg-blue-50 text-blue-700 border-blue-200" />
          <StatCard label="Highest Marks" value={stats.max} badgeColor="bg-emerald-50 text-emerald-700 border-emerald-200" />
          <StatCard label="Lowest Marks" value={stats.min} badgeColor="bg-rose-50 text-rose-700 border-rose-200" />
          <StatCard label="Average Marks" value={stats.avg} badgeColor="bg-amber-50 text-amber-700 border-amber-200" />
        </div>

        {/* Table Container */}
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
          {loading ? (
            <div className="py-16 text-center text-slate-500 font-medium">
              Fetching records from database...
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-200 text-xs font-semibold text-slate-500 uppercase tracking-wider">
                      <th className="py-3 px-4">Roll No</th>
                      <th className="py-3 px-4">Student Name</th>
                      <th className="py-3 px-4">Marks</th>
                      <th className="py-3 px-4">Board</th>
                      <th className="py-3 px-4">Group</th>
                      <th className="py-3 px-4">Class</th>
                      <th className="py-3 px-4">Year</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-sm">
                    {results.length === 0 ? (
                      <tr>
                        <td colSpan="7" className="py-12 text-center text-slate-400">
                          No matching records found.
                        </td>
                      </tr>
                    ) : (
                      results.map((row, index) => (
                        <tr key={row.id || index} className="hover:bg-slate-50 transition">
                          <td className="py-3.5 px-4 font-semibold text-slate-900">{row.roll_number}</td>
                          <td className="py-3.5 px-4 text-slate-700 font-medium">{row.name || "—"}</td>
                          <td className="py-3.5 px-4">
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-blue-100 text-blue-800">
                              {row.marks ?? "—"}
                            </span>
                          </td>
                          <td className="py-3.5 px-4 text-slate-600">{row.board || "—"}</td>
                          <td className="py-3.5 px-4 text-slate-600">{row.group || "—"}</td>
                          <td className="py-3.5 px-4 text-slate-600">{row.class ? `${row.class}th` : "—"}</td>
                          <td className="py-3.5 px-4 text-slate-600">{row.year ?? "—"}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>

              {/* Pagination Controls */}
              <div className="flex items-center justify-between px-5 py-3.5 bg-slate-50 border-t border-slate-200">
                <span className="text-xs text-slate-600">
                  Page <strong className="text-slate-900">{currentPage}</strong> of <strong className="text-slate-900">{totalPages}</strong>
                </span>

                <div className="flex gap-2">
                  <button
                    disabled={currentPage <= 1 || loading}
                    onClick={() => fetchResults(currentPage - 1)}
                    className="px-3.5 py-1.5 border border-slate-300 rounded-lg text-xs font-medium text-slate-700 bg-white hover:bg-slate-100 disabled:opacity-50 disabled:cursor-not-allowed transition"
                  >
                    ← Previous
                  </button>

                  <button
                    disabled={currentPage >= totalPages || loading}
                    onClick={() => fetchResults(currentPage + 1)}
                    className="px-3.5 py-1.5 border border-slate-300 rounded-lg text-xs font-medium text-slate-700 bg-white hover:bg-slate-100 disabled:opacity-50 disabled:cursor-not-allowed transition"
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

// Subcomponent for Metric Cards
function StatCard({ label, value, badgeColor }) {
  return (
    <div className={`p-4 rounded-xl border bg-white shadow-sm flex flex-col justify-between`}>
      <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">
        {label}
      </span>
      <span className={`text-2xl font-black mt-2 inline-block px-2.5 py-1 rounded-lg border text-center ${badgeColor}`}>
        {value}
      </span>
    </div>
  );
}