# AGENTS.md

## Project Overview
This repository contains a full-stack web application designed to process, extract, store, and search large educational board exam result gazette PDFs (80MB+, 4,000+ pages) for Pakistani boards (e.g., BISE Lahore, BISE Faisalabad).

### Architecture & Technology Stack
* **Frontend:** React (Vite SPA) hosted on **Vercel**.
* **Backend:** Python FastAPI deployed via **Docker** on **Render**.
* **Database:** **Supabase** (PostgreSQL) storing parsed student records in `public.student_results`.
* **PDF Engine:** Poppler CLI utilities (`pdftotext`, `pdfinfo`) executed in streaming sub-processes for low-memory layout preservation, PyMuPDF for word coordinates (which is what most board parsers actually use), and Tesseract OCR as the fallback for pages with no usable text layer.

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
* Most boards do NOT parse Poppler text at all — they read word coordinates via PyMuPDF and rebuild
  rows in `server/boards/_coltable.py`. Read `server/boards/__init__.py` before adding or changing a
  board parser; it explains why, and which existing module to copy.
* OCR fallback (`server/boards/ocr.py`): a page whose text layer is empty is rendered and read with
  Tesseract, returning the same `(x0, y0, text)` word triples the coordinate parsers already expect.
  Controlled by `OCR_MODE` (`auto` default / `off` / `force`), plus `OCR_DPI`, `OCR_PSM`, `OCR_LANG`,
  `OCR_MIN_CONF`. `auto` changes nothing for a page that has a text layer — verified word-for-word
  identical on every gazette wired to it. `force` OCRs every page and costs ~1s of CPU per page; it is for
  documents whose text layer is present but wrong, not for routine use.
* The Docker image must install `tesseract-ocr` and `tesseract-ocr-eng` alongside `poppler-utils`.
  On Windows, Tesseract is found automatically at the UB-Mannheim installer's default location;
  override with `TESSERACT_BIN` or `TESSERACT_BIN_DIR`.

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
* Dockerfile must include `apt-get install -y --no-install-recommends poppler-utils tesseract-ocr tesseract-ocr-eng`.



