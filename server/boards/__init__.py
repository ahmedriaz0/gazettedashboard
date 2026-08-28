"""
Board registry. This is the ONLY file that needs to know every board
module exists — nothing else in the app imports the board files
directly.

HOW TO ADD A NEW BOARD:
1. Sample the PDF: run
     pdftotext -f <page> -l <page> -layout your_file.pdf -
   on a page containing real student rows (skip intro/summary pages) and
   look at the raw text. If rows look scrambled or mis-paired even
   though the raw text "looks fine" on screen, try opening it with
   PyMuPDF instead (`page.get_text("words")`) — pdftotext -layout can
   silently misplace values when row heights vary (see sahiwal.py) or
   scramble reading order entirely under certain watermarks.
2. Copy the closest-matching existing module as a template:
     - lahore.py       — single column, explicit PASS keyword
     - faisalabad.py   — single column, no status keyword
     - bahawalpur.py / dgkhan.py / rawalpindi.py — two columns per line
     - sargodha.py     — needs post-regex filtering -> use `parser`
     - sahiwal.py       — pdftotext literally can't represent the table
                          -> use `page_records_fn` (PyMuPDF)
   Write a regex (or PyMuPDF-based function) that produces
   roll_number/name/marks/group. See boards/base.py for the full
   BOARD_CONFIG contract (pattern / page_marker / skip_page / parser /
   page_records_fn — use only the ones your board actually needs).
3. Add "<newboard>" to `match_names` (lowercase substrings that should
   map an incoming board dropdown value to this module).
4. Import and register it below, in BOARD_MODULES.
5. Test standalone before wiring into the API: dry-run your
   pattern/parser/page_records_fn across the WHOLE document (not just
   the sample page) and check for a plausible total record count and
   zero duplicate roll numbers before trusting it against Supabase.

That's it. main.py's upload/search endpoints never need to change —
only process_page()'s hook-dispatch logic does, and only if a genuinely
new KIND of quirk shows up (not for every new board).
"""
from . import lahore, faisalabad, bahawalpur, dgkhan, sargodha, rawalpindi, sahiwal, gujranwala, generic

# Every board module lives here. Order doesn't matter.
BOARD_MODULES = {
    "Lahore": lahore.BOARD_CONFIG,
    "Faisalabad": faisalabad.BOARD_CONFIG,
    "Bahawalpur": bahawalpur.BOARD_CONFIG,
    "DG Khan": dgkhan.BOARD_CONFIG,
    "Sargodha": sargodha.BOARD_CONFIG,
    "Rawalpindi": rawalpindi.BOARD_CONFIG,
    "Sahiwal": sahiwal.BOARD_CONFIG,
    "Gujranwala": gujranwala.BOARD_CONFIG,
}

GENERIC_CONFIG = generic.BOARD_CONFIG


def resolve_board(board_label: str):
    """
    Maps a free-text board name (e.g. "BISE Lahore", "Faisalabad Board")
    to (normalized_name, config). Falls back to the generic config if
    nothing matches.
    """
    label_lower = board_label.lower()
    for normalized_name, config in BOARD_MODULES.items():
        if any(alias in label_lower for alias in config["match_names"]):
            return normalized_name, config
    return "Generic", GENERIC_CONFIG
