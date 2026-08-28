# AGENTS.md

## Project Overview
This repository contains a full-stack web application designed to process, extract, store, and search large educational board exam result gazette PDFs (80MB+, 4,000+ pages) for Pakistani boards (e.g., BISE Lahore, BISE Faisalabad).

### Architecture & Technology Stack
* **Frontend:** React (Vite SPA) hosted on **Vercel**.
* **Backend:** Python FastAPI deployed via **Docker** on **Render**.
* **Database:** **Supabase** (PostgreSQL) storing parsed student records in `public.student_results`.
* **PDF Engine:** Poppler CLI utilities (`pdftotext`, `pdfinfo`) executed in streaming sub-processes for low-memory layout preservation.

---

## Directory Layout
```text
├── client/                     # Vite + React Frontend
│   ├── src/
│   │   ├── pages/
│   │   │   ├── UploadGazette.jsx # Large file uploads + Progress Tracking
│   │   │   └── SearchResults.jsx # Direct Supabase querying & pagination
│   │   ├── supabaseClient.js     # Direct Supabase JS client configuration
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── .env.example
│   ├── package.json
│   └── vite.config.js
│
├── server/                     # FastAPI Backend
│   ├── main.py                 # Core API: regex extraction, batch upsert
│   ├── Dockerfile              # Container definition with Linux poppler-utils
│   ├── requirements.txt        # Python backend dependencies
│   └── temp_uploads/           # Ephemeral storage during processing
│
└── AGENTS.md                   # System prompts, constraints, and operational context

```

---

## Technical Constraints & Guidelines for Agents

### 1. Database & Schema Conventions

* **Table Name:** `student_results`
* **Schema Fields:**
* `id` (bigint / uuid, primary key)
* `roll_number` (bigint, indexed)
* `name` (text, nullable)
* `marks` (integer)
* `board` (text)
* `group` (text, nullable)
* `class` (integer)
* `year` (integer)
* `created_at` (timestamptz)


* **Client-Side Querying:** The frontend (`SearchResults.jsx`) queries Supabase directly via `@supabase/supabase-js` using standard pagination (`.range(from, to)`) to eliminate backend server load for read queries.

### 2. PDF Processing Guidelines (`server/main.py`)

* Never read entire 80MB+ PDFs into RAM at once with standard pure-Python in-memory readers.
* Use page-by-page layout extraction via Poppler's `pdftotext -f <page> -l <page> -layout` to preserve multi-column gazette alignments.
* Maintain dynamic Poppler binary resolution to ensure cross-platform execution (Windows local fallback vs. Linux `/usr/bin/` in Docker):
```python
PDFINFO_BIN = "pdfinfo" if shutil.which("pdfinfo") else os.path.join(POPPLER_BIN_DIR, "pdfinfo.exe")
PDFTOTEXT_BIN = "pdftotext" if shutil.which("pdftotext") else os.path.join(POPPLER_BIN_DIR, "pdftotext.exe")

```


* Batch database insertions in chunks of 500 records to prevent Supabase payload timeout errors.
* Always clean up temporary files in `temp_uploads/` using a `finally` block.

### 3. Frontend Standards (`client/`)

* **Upload Progress:** Always use `XMLHttpRequest` (`xhr.upload.onprogress`) for the upload endpoint so users receive continuous progress tracking on large uploads.
* **Environment Variables:**
* Public client variables must use the `VITE_` prefix (`VITE_API_BASE_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`).
* On Vercel, `VITE_` variables must be set with **Config** visibility (not **Secret**), without trailing quotes or semicolons.



---

## Local Development Workflow

### Starting the Backend

```powershell
cd server
.\venv\Scripts\Activate.ps1
python -m uvicorn main:app --reload --port 8000

```

### Starting the Frontend

```powershell
cd client
npm install
npm run dev

```

---

## Deployment Standards

* **Vercel (Frontend):**
* Framework: `Vite`
* Root Directory: `client`
* Build Command: `npm run build`
* Output Directory: `dist`


* **Render (Backend):**
* Environment: `Docker`
* Root Directory: `server`
* Dockerfile must include `apt-get install -y --no-install-recommends poppler-utils`.



