import os
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client

from boards import resolve_board

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
    try:
        result = subprocess.run(
            [PDFINFO_BIN, pdf_path],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        for line in result.stdout.splitlines():
            if line.startswith("Pages:"):
                return int(line.split(":")[1].strip())
        raise RuntimeError("Could not determine page count from PDF output.")
    except FileNotFoundError:
        raise RuntimeError(f"Poppler executable '{PDFINFO_BIN}' not found. Verify Poppler installation path.")


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
    """
    try:
        result = subprocess.run(
            [PDFTOTEXT_BIN, "-f", str(page_num), "-l", str(page_num), "-layout", pdf_path, "-"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            return ""
        return result.stdout or ""
    except Exception:
        return ""


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
# 1. PDF UPLOAD & PARSER ENDPOINT
# -------------------------------------------------------------
@app.post("/api/upload-and-parse")
async def upload_and_parse_gazette(
    file: UploadFile = File(...),
    board: str = Form(...),
    class_num: int = Form(...),
    year: int = Form(...),
):
    temp_file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(temp_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    config = None  # so the finally block can check config.get("cleanup_fn")
                    # even if resolve_board() itself somehow raised
    try:
        normalized_board, config = resolve_board(board)
        compiled_re = config.get("pattern")

        total_pages = get_page_count(temp_file_path)
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
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
            future_to_page = {executor.submit(process_page, p): p for p in range(1, total_pages + 1)}
            for future in concurrent.futures.as_completed(future_to_page):
                page_records = future.result()
                records.extend(page_records)
                processed_pages += 1
                if processed_pages % 200 == 0:
                    print(f"Processed {processed_pages}/{total_pages} pages... ({len(records)} records extracted)")

        print(f"[*] Uploading {len(records)} records to Supabase...")

        batch_size = 500
        inserted_count = 0
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            supabase.table(TABLE_NAME).insert(batch).execute()
            inserted_count += len(batch)

        return {
            "status": "success",
            "board_matched": normalized_board,
            "total_pages": total_pages,
            "records_inserted": inserted_count
        }

    except Exception as e:
        print(f"[X] Processing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
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

        # Deliberately non-fatal: extraction + Supabase insert already
        # succeeded by this point (that happens earlier, inside the try
        # block, before `return`). A leftover temp file is a minor
        # annoyance to clean up manually later; raising here instead
        # would turn an already-successful upload into a reported 500,
        # which is exactly what was happening before this fix.
        try:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
        except Exception as remove_err:
            print(f"[!] Could not remove temp file {temp_file_path} (non-fatal): {remove_err}")


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
