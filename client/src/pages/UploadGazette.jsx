import React, { useState } from 'react';

const PUNJAB_BOARDS = [
  'BISE Lahore',
  'BISE Faisalabad',
  'BISE Gujranwala',
  'BISE Rawalpindi',
  'BISE Multan',
  'BISE Sargodha',
  'BISE Sahiwal',
  'BISE Bahawalpur',
  'BISE DG Khan',
  'FBISE Federal'
];

export default function UploadGazette() {
  const [file, setFile] = useState(null);
  const [board, setBoard] = useState("BISE Lahore");
  const [classNum, setClassNum] = useState(10);
  
  // Dynamic Year Dropdown setup
  const currentYear = new Date().getFullYear();
  const yearsList = [];
  for (let y = currentYear; y >= 2020; y--) {
    yearsList.push(y);
  }
  const [year, setYear] = useState(currentYear);

  const [includeName, setIncludeName] = useState(true);
  const [includeGroup, setIncludeGroup] = useState(false);

  const [loading, setLoading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState('idle'); // 'idle' | 'uploading' | 'parsing' | 'saving' | 'complete' | 'error'
  const [stageText, setStageText] = useState("");
  const [statusMsg, setStatusMsg] = useState("");
  const [isError, setIsError] = useState(false);

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!file) return alert("Please select a PDF file first.");

    setLoading(true);
    setIsError(false);
    setUploadProgress(0);
    setCurrentStep('uploading');
    setStageText("Uploading PDF file to server...");
    setStatusMsg("");

    const selectedFields = ["roll_number", "marks"];
    if (includeName) selectedFields.push("name");
    if (includeGroup) selectedFields.push("group");

    const formData = new FormData();
    formData.append("file", file);
    formData.append("board", board);
    formData.append("class_num", classNum);
    formData.append("year", year);
    formData.append("selected_fields", JSON.stringify(selectedFields));

    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE_URL}/api/upload-and-parse`);

    // Track upload progress
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        const percent = Math.round((event.loaded / event.total) * 100);
        setUploadProgress(percent);
        if (percent < 100) {
          setStageText(`Uploading PDF (${percent}%)... (${(event.loaded / (1024 * 1024)).toFixed(1)} MB / ${(event.total / (1024 * 1024)).toFixed(1)} MB)`);
        } else {
          setCurrentStep('parsing');
          setStageText("Upload complete! Extracting text and parsing pages with Poppler layout engine...");
        }
      }
    };

    xhr.onload = () => {
      setLoading(false);
      try {
        const data = JSON.parse(xhr.responseText);
        if (xhr.status >= 200 && xhr.status < 300) {
          setCurrentStep('complete');
          setIsError(false);
          setStatusMsg(`Success! Processed ${data.total_pages} pages and inserted ${data.records_inserted} student records into Supabase.`);
        } else {
          setCurrentStep('error');
          setIsError(true);
          setStatusMsg(`Error: ${typeof data.detail === "object" ? JSON.stringify(data.detail) : (data.detail || "Upload failed")}`);
        }
      } catch (err) {
        setCurrentStep('error');
        setIsError(true);
        setStatusMsg("Error parsing server response: " + xhr.responseText);
      }
    };

    xhr.onerror = () => {
      setLoading(false);
      setCurrentStep('error');
      setIsError(true);
      setStatusMsg("Network error connecting to backend server. Make sure FastAPI is running on port 8000.");
    };

    xhr.send(formData);
  };

  return (
    <div className="max-w-4xl mx-auto bg-white rounded-xl shadow-sm border border-slate-200 p-6 md:p-8">
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-slate-800 tracking-tight">
          Upload Board Gazette
        </h2>
        <p className="text-slate-500 text-sm mt-1">
          Select the target board and metadata. The parser will extract tabular text layout and save valid records to Supabase.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* File Selection Box */}
        <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg">
          <label className="block text-sm font-semibold text-slate-700 mb-2">
            1. Gazette PDF File:
          </label>
          <input
            type="file"
            accept="application/pdf"
            onChange={(e) => {
              setFile(e.target.files[0]);
              setUploadProgress(0);
              setCurrentStep('idle');
              setStatusMsg("");
            }}
            required
            disabled={loading}
            className="block w-full text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 disabled:opacity-50 cursor-pointer"
          />
          {file && (
            <p className="mt-2 text-xs text-slate-500 font-medium">
              Selected: <span className="text-slate-800 font-semibold">{file.name}</span> ({(file.size / (1024 * 1024)).toFixed(2)} MB)
            </p>
          )}
        </div>

        {/* 3-Column Dropdowns */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
              Board
            </label>
            <select
              value={board}
              onChange={(e) => setBoard(e.target.value)}
              disabled={loading}
              className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition disabled:opacity-50"
            >
              {PUNJAB_BOARDS.map((b) => (
                <option key={b} value={b}>{b}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
              Class
            </label>
            <select
              value={classNum}
              onChange={(e) => setClassNum(Number(e.target.value))}
              disabled={loading}
              className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition disabled:opacity-50"
            >
              <option value={9}>9th Class (SSC-I)</option>
              <option value={10}>10th Class (SSC-II)</option>
              <option value={11}>11th Class (HSSC-I)</option>
              <option value={12}>12th Class (HSSC-II)</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
              Year
            </label>
            <select
              value={year}
              onChange={(e) => setYear(Number(e.target.value))}
              disabled={loading}
              className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:bg-white transition disabled:opacity-50"
            >
              {yearsList.map((y) => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Field Selection Box */}
        <fieldset className="border border-slate-200 rounded-lg p-4 bg-slate-50/50">
          <legend className="px-2 text-xs font-bold text-slate-500 uppercase tracking-wider">
            2. Fields Present in this PDF
          </legend>
          <div className="space-y-2 mt-1">
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked
                disabled
                className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500 cursor-not-allowed"
              />
              <span><strong className="font-semibold text-slate-900">Roll / Code Number & Marks</strong> (Mandatory)</span>
            </label>

            <label className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
              <input
                type="checkbox"
                checked={includeName}
                onChange={(e) => setIncludeName(e.target.checked)}
                disabled={loading}
                className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50"
              />
              <span><strong className="font-semibold text-slate-900">Student Name</strong></span>
            </label>

            <label className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
              <input
                type="checkbox"
                checked={includeGroup}
                onChange={(e) => setIncludeGroup(e.target.checked)}
                disabled={loading}
                className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500 disabled:opacity-50"
              />
              <span><strong className="font-semibold text-slate-900">Group</strong> (e.g. Science / Arts)</span>
            </label>
          </div>
        </fieldset>

        {/* Multi-Step Real-Time Status Progress Indicator */}
        {loading && (
          <div className="space-y-4 bg-slate-50 p-4 rounded-xl border border-slate-200">
            {/* Step Badges */}
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-semibold border-b border-slate-200 pb-3">
              <div className={`flex items-center gap-1.5 ${currentStep === 'uploading' ? 'text-blue-600' : 'text-slate-400'}`}>
                <span className={`w-2 h-2 rounded-full ${currentStep === 'uploading' ? 'bg-blue-600 animate-pulse' : 'bg-emerald-500'}`} />
                1. File Transfer
              </div>
              <span className="text-slate-300">→</span>
              <div className={`flex items-center gap-1.5 ${currentStep === 'parsing' ? 'text-blue-600 font-bold' : 'text-slate-400'}`}>
                <span className={`w-2 h-2 rounded-full ${currentStep === 'parsing' ? 'bg-blue-600 animate-pulse' : currentStep === 'complete' ? 'bg-emerald-500' : 'bg-slate-300'}`} />
                2. Layout Parsing
              </div>
              <span className="text-slate-300">→</span>
              <div className={`flex items-center gap-1.5 ${currentStep === 'saving' ? 'text-blue-600 font-bold' : 'text-slate-400'}`}>
                <span className={`w-2 h-2 rounded-full ${currentStep === 'complete' ? 'bg-emerald-500' : 'bg-slate-300'}`} />
                3. Supabase Database Sync
              </div>
            </div>

            {/* Stage Description & Percentage Bar */}
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs text-slate-700 font-medium">
                <span>{stageText}</span>
                {currentStep === 'uploading' && <span className="font-bold text-slate-900">{uploadProgress}%</span>}
              </div>

              {currentStep === 'uploading' ? (
                <div className="w-full h-2 bg-slate-200 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-600 transition-all duration-200"
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
              ) : (
                <div className="w-full h-2 bg-blue-100 rounded-full overflow-hidden relative">
                  <div className="h-full bg-blue-600 w-1/3 animate-pulse rounded-full" />
                </div>
              )}
            </div>
          </div>
        )}

        {/* Submit Button */}
        <button
          type="submit"
          disabled={loading}
          className="w-full py-2.5 px-4 bg-blue-600 text-white font-semibold rounded-lg shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 transition flex items-center justify-center gap-2"
        >
          {loading && (
            <svg className="animate-spin h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
          )}
          {loading ? "Processing Gazette Data..." : "Upload & Parse to Supabase"}
        </button>
      </form>

      {/* Final Status Message Badge */}
      {statusMsg && (
        <div
          className={`mt-6 p-4 rounded-lg text-sm border ${
            isError
              ? 'bg-rose-50 border-rose-200 text-rose-800'
              : 'bg-emerald-50 border-emerald-200 text-emerald-800'
          }`}
        >
          <strong className="font-semibold">Status:</strong> {statusMsg}
        </div>
      )}
    </div>
  );
}