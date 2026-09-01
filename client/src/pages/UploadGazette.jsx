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

const STAGES = [
  { id: 'uploading', label: 'File Transfer' },
  { id: 'parsing', label: 'Layout Parsing' },
  { id: 'saving', label: 'Database Sync' },
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
          setStageText("Upload received! Server is queuing the parse job...");
        }
      }
    };

    // The upload endpoint responds as soon as the file is saved and a
    // background job is queued (202 + job_id) — it does NOT wait for
    // parsing to finish. That's what keeps this working for 4,000+ page
    // gazettes on a hosted server: parsing can take minutes, and no
    // single HTTP request is left open that long for a host's proxy or
    // health checks to kill. Progress after this point comes from
    // polling /api/upload-status/{job_id}.
    xhr.onload = () => {
      let data;
      try {
        data = JSON.parse(xhr.responseText);
      } catch (err) {
        setLoading(false);
        setCurrentStep('error');
        setIsError(true);
        setStatusMsg("Error parsing server response: " + xhr.responseText);
        return;
      }

      if (xhr.status >= 200 && xhr.status < 300 && data.job_id) {
        pollJobStatus(data.job_id);
      } else {
        setLoading(false);
        setCurrentStep('error');
        setIsError(true);
        setStatusMsg(`Error: ${typeof data.detail === "object" ? JSON.stringify(data.detail) : (data.detail || "Upload failed")}`);
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

  const pollJobStatus = (jobId) => {
    const POLL_INTERVAL_MS = 1500;
    let consecutiveFailures = 0;

    const tick = async () => {
      let res;
      try {
        res = await fetch(`${API_BASE_URL}/api/upload-status/${jobId}`);
      } catch (err) {
        consecutiveFailures += 1;
        if (consecutiveFailures >= 5) {
          setLoading(false);
          setCurrentStep('error');
          setIsError(true);
          setStatusMsg("Lost connection to the backend server while checking parse progress.");
          return;
        }
        setTimeout(tick, POLL_INTERVAL_MS);
        return;
      }

      if (!res.ok) {
        setLoading(false);
        setCurrentStep('error');
        setIsError(true);
        setStatusMsg(res.status === 404
          ? "Job not found (server may have restarted mid-parse). Please retry the upload."
          : `Error checking parse progress (HTTP ${res.status}).`);
        return;
      }

      consecutiveFailures = 0;
      const job = await res.json();

      if (job.status === "queued" || job.status === "parsing") {
        setCurrentStep('parsing');
        if (job.total_pages) {
          setStageText(`Parsing page ${job.processed_pages}/${job.total_pages} (${job.records_found} records found so far)...`);
        } else {
          setStageText("Reading PDF page count...");
        }
        setTimeout(tick, POLL_INTERVAL_MS);
      } else if (job.status === "saving") {
        setCurrentStep('saving');
        setStageText(`Saving ${job.records_found} records to Supabase (${job.records_inserted} inserted so far)...`);
        setTimeout(tick, POLL_INTERVAL_MS);
      } else if (job.status === "complete") {
        setLoading(false);
        setCurrentStep('complete');
        setIsError(false);
        setStatusMsg(`Success! Processed ${job.total_pages} pages and inserted ${job.records_inserted} student records into Supabase.`);
      } else if (job.status === "error") {
        setLoading(false);
        setCurrentStep('error');
        setIsError(true);
        setStatusMsg(`Error: ${job.error || "Upload failed"}`);
      }
    };

    tick();
  };

  const stageIndex = STAGES.findIndex((s) => s.id === currentStep);

  return (
    <div className="mx-auto max-w-4xl border border-border bg-surface p-5 sm:p-8">
      <div className="mb-6 border-b border-border pb-4">
        <h2 className="text-xl font-semibold tracking-tight text-ink sm:text-2xl">
          Upload Board Gazette
        </h2>
        <p className="mt-1 text-sm text-ink-muted">
          Select the target board and metadata. The parser will extract tabular text layout and save valid records to Supabase.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* File Selection Box */}
        <div className="border border-border bg-bg p-4">
          <label className="mb-2 block text-xs font-medium uppercase tracking-wide text-ink-muted">
            1. Gazette PDF File
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
            className="block w-full text-sm text-ink-muted file:mr-4 file:border file:border-border-strong file:bg-bg file:px-4 file:py-2 file:text-xs file:font-medium file:text-ink hover:file:bg-surface-muted disabled:opacity-50 cursor-pointer"
          />
          {file && (
            <p className="mt-2 text-xs text-ink-muted">
              Selected: <span className="font-medium text-ink">{file.name}</span> ({(file.size / (1024 * 1024)).toFixed(2)} MB)
            </p>
          )}
        </div>

        {/* 3-Column Dropdowns */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-ink-muted">
              Board
            </label>
            <select
              value={board}
              onChange={(e) => setBoard(e.target.value)}
              disabled={loading}
              className={inputClass}
            >
              {PUNJAB_BOARDS.map((b) => (
                <option key={b} value={b}>{b}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-ink-muted">
              Class
            </label>
            <select
              value={classNum}
              onChange={(e) => setClassNum(Number(e.target.value))}
              disabled={loading}
              className={inputClass}
            >
              <option value={9}>9th Class (SSC-I)</option>
              <option value={10}>10th Class (SSC-II)</option>
              <option value={11}>11th Class (HSSC-I)</option>
              <option value={12}>12th Class (HSSC-II)</option>
            </select>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-ink-muted">
              Year
            </label>
            <select
              value={year}
              onChange={(e) => setYear(Number(e.target.value))}
              disabled={loading}
              className={inputClass}
            >
              {yearsList.map((y) => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Field Selection Box */}
        <fieldset className="border border-border bg-bg p-4">
          <legend className="px-1 text-xs font-medium uppercase tracking-wide text-ink-muted">
            2. Fields Present in this PDF
          </legend>
          <div className="mt-1 space-y-2">
            <label className="flex items-center gap-2 text-sm text-ink-muted">
              <input
                type="checkbox"
                checked
                disabled
                className="h-4 w-4 accent-ink cursor-not-allowed"
              />
              <span><strong className="font-medium text-ink">Roll / Code Number & Marks</strong> (Mandatory)</span>
            </label>

            <label className="flex cursor-pointer items-center gap-2 text-sm text-ink-muted">
              <input
                type="checkbox"
                checked={includeName}
                onChange={(e) => setIncludeName(e.target.checked)}
                disabled={loading}
                className="h-4 w-4 accent-ink disabled:opacity-50"
              />
              <span><strong className="font-medium text-ink">Student Name</strong></span>
            </label>

            <label className="flex cursor-pointer items-center gap-2 text-sm text-ink-muted">
              <input
                type="checkbox"
                checked={includeGroup}
                onChange={(e) => setIncludeGroup(e.target.checked)}
                disabled={loading}
                className="h-4 w-4 accent-ink disabled:opacity-50"
              />
              <span><strong className="font-medium text-ink">Group</strong> (e.g. Science / Arts)</span>
            </label>
          </div>
        </fieldset>

        {/* Multi-Step Real-Time Status Progress Indicator */}
        {loading && (
          <div className="space-y-4 border border-border bg-bg p-4">
            {/* Step List */}
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3 text-xs font-medium">
              {STAGES.map((stage, i) => {
                const state = i < stageIndex ? 'done' : i === stageIndex ? 'active' : 'pending';
                return (
                  <div key={stage.id} className="flex items-center gap-1.5">
                    <span
                      className={`h-2 w-2 rounded-full ${
                        state === 'pending' ? 'bg-border' : 'bg-ink'
                      }`}
                    />
                    <span className={state === 'pending' ? 'text-ink-faint' : 'text-ink'}>
                      {i + 1}. {stage.label}
                    </span>
                  </div>
                );
              })}
            </div>

            {/* Stage Description & Percentage Bar */}
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs text-ink-muted">
                <span>{stageText}</span>
                {currentStep === 'uploading' && <span className="font-semibold text-ink">{uploadProgress}%</span>}
              </div>

              {currentStep === 'uploading' ? (
                <div className="h-1.5 w-full overflow-hidden bg-border">
                  <div
                    className="h-full bg-ink transition-all duration-200"
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
              ) : (
                <div className="relative h-1.5 w-full overflow-hidden bg-border">
                  <div className="h-full w-1/3 animate-pulse bg-ink" />
                </div>
              )}
            </div>
          </div>
        )}

        {/* Submit Button */}
        <button
          type="submit"
          disabled={loading}
          className="flex w-full items-center justify-center gap-2 bg-ink px-4 py-2.5 text-sm font-medium text-bg transition-opacity hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading && (
            <svg className="h-4 w-4 animate-spin text-bg" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
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
          className={`mt-6 border p-4 text-sm ${
            isError
              ? 'border-danger/40 bg-danger-bg text-danger'
              : 'border-border-strong bg-bg text-ink'
          }`}
        >
          <strong className="font-semibold">Status:</strong> {statusMsg}
        </div>
      )}
    </div>
  );
}

const inputClass =
  'w-full border border-border bg-bg px-3 py-2 text-sm text-ink transition-colors focus:border-border-strong focus:outline-none disabled:opacity-50';
