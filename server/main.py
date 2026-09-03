import os
import shutil
import subprocess
import time
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client

from boards import resolve_board
from boards import ocr
from boards import _coltable

app = FastAPI(title="BISE Gazette Universal Parser & Search API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Supabase Configuration ---
SUPABASE_URL = "https://vijizoadoxsijlvfrxek.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZpaml6b2Fkb3hzaWpsdmZyeGVrIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODc1NjQ3MzgsImV4cCI6MjEwMzE0MDczOH0.zhakKWWEqiPACjtN02d4-Z8Ls1DhJF1pQIWQlxewvCk"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
TABLE_NAME = "student_results"

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "temp_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Each unit of "parallelism" here is a whole extra `pdftotext` subprocess.
# 16 was tuned against a real multi-core dev machine; on a host that only
# gets a FRACTION of a shared vCPU (e.g. Render's Free/Starter tiers),
# os.cpu_count() still reports the host's full core count (cgroup CPU
# quotas don't change it), so it can't be auto-detected reliably here —
# 16-way spawning on a throttled CPU thrashes instead of parallelizing,
# which is slower than fewer workers would be. Tune via env var on Render
# without a redeploy; try 2, 4, 8 and see what's actually fastest for
# your plan/region.
PARSE_MAX_WORKERS = int(os.environ.get("PARSE_MAX_WORKERS", "4"))

# -------------------------------------------------------------
# IN-MEMORY JOB STORE
# -------------------------------------------------------------
# Parsing a 4,000+ page gazette can take minutes. Doing that inline inside
# a single HTTP request handler blocks the asyncio event loop (nothing else
# can be served, including the host's health checks) and holds one HTTP
# connection open far longer than most hosts/proxies (Render, Vercel,
# browsers) allow before silently killing it. That's what "stuck at
# parsing" in production was: the connection got cut with no response ever
# reaching the client, even though the server might still be working.
#
# Fix: the upload endpoint just saves the file, spawns a background job,
# and returns a job_id immediately. The real work runs in a worker thread
# (asyncio.to_thread) so it never blocks the event loop, and the frontend
# polls /api/upload-status/{job_id} for progress instead of keeping one
# long request open.
#
# NOTE: this is in-memory and per-process — jobs are lost if the server
# restarts mid-parse, and this won't work correctly across multiple
# replicas/workers. Fine for a single-instance deployment; swap for
# Redis/DB-backed job storage if you scale out.
JOBS: dict[str, dict] = {}
JOB_MAX_AGE_SECONDS = 3600


def _prune_old_jobs():
    cutoff = time.time() - JOB_MAX_AGE_SECONDS
    stale_ids = [jid for jid, j in JOBS.items() if j.get("created_at", 0) < cutoff and j["status"] in ("complete", "error")]
    for jid in stale_ids:
        JOBS.pop(jid, None)

# -------------------------------------------------------------
# POPPLER BINARY PATH CONFIGURATION
# -------------------------------------------------------------
POPPLER_BIN_DIR = os.environ.get("POPPLER_BIN_DIR", r"C:\poppler\poppler-26.02.0\Library\bin")

PDFINFO_BIN = "pdfinfo" if shutil.which("pdfinfo") else (
    os.path.join(POPPLER_BIN_DIR, "pdfinfo.exe") if os.path.exists(POPPLER_BIN_DIR) else "pdfinfo"
)
PDFTOTEXT_BIN = "pdftotext" if shutil.which("pdftotext") else (
    os.path.join(POPPLER_BIN_DIR, "pdftotext.exe") if os.path.exists(POPPLER_BIN_DIR) else "pdftotext"
)

# NOTE: each board has its own file under boards/ (boards/lahore.py,
# boards/faisalabad.py, boards/bahawalpur.py, boards/dgkhan.py,
# boards/sargodha.py, boards/rawalpindi.py, boards/sahiwal.py, ...).
# boards/__init__.py resolves an incoming board name string to the
# right one via resolve_board(). See boards/base.py for the full
# BOARD_CONFIG contract (pattern / page_marker / skip_page / parser /
# page_records_fn).


def get_page_count(pdf_path: str) -> int:
    """Page count via pdfinfo, falling back to MuPDF.

    The fallback is not belt-and-braces: poppler refuses some of these
    files outright ("Couldn't find trailer dictionary" on an AES-256
    encrypted gazette, even one whose permissions allow reading), and
    without it the job dies here — before any board, OCR included, gets a
    chance at a single page. MuPDF opens those files, and it is already a
    dependency of every coordinate board.
    """
    try:
        result = subprocess.run(
            [PDFINFO_BIN, pdf_path],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode == 0:
            for line in (result.stdout or "").splitlines():
                if line.startswith("Pages:"):
                    return int(line.split(":")[1].strip())
    except FileNotFoundError:
        pass  # no poppler on this host; MuPDF below

    try:
        doc, lock = _coltable.get_doc_and_lock(pdf_path)
        with lock:
            page_count = doc.page_count
    except Exception as e:
        raise RuntimeError(
            f"Could not determine page count for this PDF "
            f"(pdfinfo '{PDFINFO_BIN}' and MuPDF both failed: {e})"
        )

    # MuPDF opens a truncated/corrupt file and reports 0 pages rather than
    # raising (results/sahiwal.pdf, a half-finished download, does exactly
    # this). Returning 0 here would let the job run to "complete" having
    # parsed nothing, which reads as "this gazette had no candidates"
    # instead of "this file is broken".
    if page_count < 1:
        raise RuntimeError(
            "This PDF reports 0 pages — it is corrupt or was not fully "
            "uploaded. Re-upload the file."
        )
    return page_count


def get_page_text(pdf_path: str, page_num: int) -> str:
    """
    ROOT-CAUSE FIX for the Windows crash:
    subprocess.run(..., text=True) with no explicit encoding decodes
    using the OS's default codepage — cp1252 on Windows. pdftotext
    always emits UTF-8, and the moment a page contains any character
    outside Latin-1 (an unusual dash, a watermark artifact, certain
    diacritics — the Rawalpindi gazette had one), that decode crashes
    inside a background reader thread. The crash doesn't propagate as a
    normal exception, it just leaves `result.stdout` as None, which
    then blew up downstream at `text.strip()` with
    "'NoneType' object has no attribute 'strip'".

    Fix: force encoding="utf-8" explicitly (matching what pdftotext
    actually outputs) with errors="replace" so a single bad byte
    degrades gracefully (one garbled character) instead of crashing the
    whole page's extraction. Also defensively coalesce None -> "" in
    case any other library/version quirk slips one through.

    OCR: an empty result here means poppler found no text layer for this
    page — a scanned page, or one this PDF's encryption keeps poppler out
    of. Under OCR_MODE=auto (the default) boards/ocr.py then rebuilds the
    page from the rendered image with Tesseract, in the same
    `-layout`-style column spacing the regex boards expect; under
    OCR_MODE=force poppler is skipped entirely. See boards/ocr.py.
    """
    if ocr.forced():
        return ocr.page_text_for_pdf(pdf_path, page_num)

    text = ""
    try:
        result = subprocess.run(
            [PDFTOTEXT_BIN, "-f", str(page_num), "-l", str(page_num), "-layout", pdf_path, "-"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode == 0:
            text = result.stdout or ""
    except Exception:
        text = ""

    if not text.strip() and ocr.enabled():
        return ocr.page_text_for_pdf(pdf_path, page_num)
    return text


def _page_marker_present(page_marker, text: str) -> bool:
    """page_marker can be a single string (dgkhan.py, sahiwal.py) or a
    list of strings where ANY match counts (rawalpindi.py, whose two
    side-by-side columns print slightly different header spelling)."""
    if page_marker is None:
        return True
    if isinstance(page_marker, str):
        return page_marker in text
    return any(marker in text for marker in page_marker)


# -------------------------------------------------------------
# 1. PDF UPLOAD & PARSER ENDPOINT (background job + polling)
# -------------------------------------------------------------
def _run_parse_job_sync(job_id: str, temp_file_path: str, board: str, class_num: int, year: int):
    """Runs entirely inside a worker thread (via asyncio.to_thread) so it
    never blocks the event loop. Owns the full lifecycle of the job: status
    transitions, progress updates, error capture, and temp-file cleanup."""
    job = JOBS[job_id]
    config = None
    try:
        normalized_board, config = resolve_board(board)
        compiled_re = config.get("pattern")

        total_pages = get_page_count(temp_file_path)
        job["total_pages"] = total_pages
        job["status"] = "parsing"
        print(f"[*] Total Pages to Process: {total_pages} (board={normalized_board})")

        records = []
        current_time = datetime.now(timezone.utc).isoformat()

        def build_record(parsed: dict) -> dict:
            return {
                "roll_number": parsed["roll_number"],
                "name": parsed.get("name"),
                "marks": parsed.get("marks"),
                "board": board.strip(),
                "group": parsed.get("group"),
                "class": int(class_num),
                "year": int(year),
                "created_at": current_time,
            }

        def process_page(page_num):
            # Boards that need direct PDF access instead of pdftotext
            # (currently only boards/sahiwal.py) bypass Poppler entirely
            # — see that module's docstring for why.
            if config.get("page_records_fn"):
                parsed_rows = config["page_records_fn"](temp_file_path, page_num)
                return [build_record(r) for r in parsed_rows]

            text = get_page_text(temp_file_path, page_num)
            if not text.strip():
                return []

            # Skip pages that don't carry this board's data-table header
            # at all (front matter, merit lists, institution-wise stats
            # sections) — see e.g. boards/dgkhan.py, boards/rawalpindi.py.
            if not _page_marker_present(config.get("page_marker"), text):
                return []

            # Skip pages a board has explicitly flagged as a known
            # false-positive source (see boards/bahawalpur.py).
            skip_page = config.get("skip_page")
            if skip_page and skip_page(text):
                return []

            # Boards whose regex needs post-filtering that a bare
            # compiled_re.finditer() can't express (see
            # boards/sargodha.py) provide a "parser" function that
            # replaces the default regex loop entirely.
            if config.get("parser"):
                return [build_record(r) for r in config["parser"](text)]

            # Default path: plain named-group regex.
            page_records = []
            for match in compiled_re.finditer(text):
                groups = match.groupdict()
                page_records.append(build_record({
                    "roll_number": int(groups["roll_number"]),
                    "name": groups.get("name", "").strip() if groups.get("name") else None,
                    "marks": int(groups["marks"]),
                    "group": groups.get("group"),
                }))
            return page_records

        import concurrent.futures

        processed_pages = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=PARSE_MAX_WORKERS) as executor:
            future_to_page = {executor.submit(process_page, p): p for p in range(1, total_pages + 1)}
            for future in concurrent.futures.as_completed(future_to_page):
                page_records = future.result()
                records.extend(page_records)
                processed_pages += 1
                job["processed_pages"] = processed_pages
                job["records_found"] = len(records)
                if processed_pages % 200 == 0:
                    print(f"Processed {processed_pages}/{total_pages} pages... ({len(records)} records extracted)")

        print(f"[*] Uploading {len(records)} records to Supabase...")
        job["status"] = "saving"

        batch_size = 500
        inserted_count = 0
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            supabase.table(TABLE_NAME).insert(batch).execute()
            inserted_count += len(batch)
            job["records_inserted"] = inserted_count

        job["status"] = "complete"
        job["board_matched"] = normalized_board

    except Exception as e:
        print(f"[X] Processing error: {e}")
        job["status"] = "error"
        job["error"] = str(e)
    finally:
        # Boards that hold a file handle open across the whole upload
        # (currently only sahiwal.py, via PyMuPDF) need to release it
        # BEFORE we try to delete the temp file, or Windows raises
        # PermissionError here — see boards/sahiwal.py's close_doc().
        cleanup_fn = config.get("cleanup_fn") if config else None
        if cleanup_fn:
            try:
                cleanup_fn(temp_file_path)
            except Exception as cleanup_err:
                print(f"[!] cleanup_fn failed (non-fatal): {cleanup_err}")

        # The regex boards (boards/multan.py, boards/generic.py) declare no
        # cleanup_fn because they never opened the PDF themselves — but OCR
        # does, on their behalf, for any page with no text layer. No-op when
        # nothing was cached.
        try:
            _coltable.close_doc(temp_file_path)
        except Exception as doc_cleanup_err:
            print(f"[!] _coltable.close_doc failed (non-fatal): {doc_cleanup_err}")

        try:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
        except Exception as remove_err:
            print(f"[!] Could not remove temp file {temp_file_path} (non-fatal): {remove_err}")


@app.post("/api/upload-and-parse", status_code=202)
async def upload_and_parse_gazette(
    file: UploadFile = File(...),
    board: str = Form(...),
    class_num: int = Form(...),
    year: int = Form(...),
):
    temp_file_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex}_{file.filename}")

    def _save():
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

    await asyncio.to_thread(_save)

    _prune_old_jobs()
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {
        "status": "queued",
        "total_pages": None,
        "processed_pages": 0,
        "records_found": 0,
        "records_inserted": 0,
        "board_matched": None,
        "error": None,
        "created_at": time.time(),
    }

    asyncio.create_task(
        asyncio.to_thread(_run_parse_job_sync, job_id, temp_file_path, board, class_num, year)
    )

    return {"job_id": job_id}


# -------------------------------------------------------------
# 1b. UPLOAD JOB STATUS (polling endpoint for the above)
# -------------------------------------------------------------
@app.get("/api/upload-status/{job_id}")
async def get_upload_status(job_id: str):
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown or expired job_id")
    return job


# -------------------------------------------------------------
# 2. SEARCH & PAGINATION ENDPOINT
# -------------------------------------------------------------
@app.get("/api/results")
async def get_results(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    roll_number: Optional[int] = None,
    name: Optional[str] = None,
    board: Optional[str] = None,
    class_num: Optional[int] = None,
    year: Optional[int] = None,
):
    try:
        from_idx = (page - 1) * page_size
        to_idx = from_idx + page_size - 1

        query = supabase.table(TABLE_NAME).select("*", count="exact").order("roll_number", desc=False)

        if roll_number is not None:
            query = query.eq("roll_number", roll_number)
        if name:
            query = query.ilike("name", f"%{name.strip()}%")
        if board:
            query = query.ilike("board", f"%{board.strip()}%")
        if class_num is not None:
            query = query.eq("class", class_num)
        if year is not None:
            query = query.eq("year", year)

        response = query.range(from_idx, to_idx).execute()

        return {
            "data": response.data,
            "total_count": response.count if response.count is not None else 0,
            "page": page,
            "page_size": page_size,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
