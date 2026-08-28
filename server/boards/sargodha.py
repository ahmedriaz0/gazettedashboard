"""
BISE Sargodha gazette format.

Sample raw line (via `pdftotext -layout`) — THREE candidates side-by-side
per physical line (Multan/D.G.Khan have two):

    500001   WASIF UR REHMAN               660    500042   SHEHRIYAR HASSAN   ...    500082   ABDUL RAHEEM KHAN   648

Fields available: roll_number, name, marks. Failing candidates show
"ABSENT" or a wrapped list of subject codes (e.g. "PHY(PR) CHM CHM(PR)
... TILL 2ND A/2026") instead of marks, which the pattern naturally skips
— same as every other board here.

*** This board needs a "parser" function, not just a "pattern" regex —
see main.py's process_page(), which checks config.get("parser") before
falling back to the regex path. ***

Why a plain regex isn't enough: every so often a new institute's block of
candidates is introduced by a header row that looks exactly like a normal
candidate row structurally — a 6-digit code, then the institute's name,
e.g.:

    100002   THE EDUCATORS (BOYS) BHAKKAR CAMPUS BHAKKAR
    300568   GOVT. HIGHER SECONDARY SCHOOL CHAK NO. 101/SB

Most of these are harmless: they either have no trailing digits at all
(safely unmatched) or contain a character outside the name class
(parentheses, commas) that stops the match before it can reach anything
resembling marks. But Punjab village/school names are frequently written
as "... CHAK NO. <number>" — e.g. "CHAK NO. 101/SB" — and that trailing
number is 3 digits, sitting right where a real candidate's marks would be.
Digit-boundary guards (borrowed from dgkhan.py) don't help here, because
"101" in "CHAK NO. 101/SB" genuinely is a clean, boundary-respecting 3-digit
token — it's not a fragment of a longer number.

Testing on the full 815-page document found every single one of these
false matches (118 of them) had one thing in common: the captured "name"
contained the word "SCHOOL". No genuine candidate name ever does. So this
module filters matches after the regex runs, dropping any row whose name
contains "SCHOOL" — something a bare compiled regex handed to
`compiled_re.finditer()` can't do on its own, hence the "parser" function
below instead of (or alongside) "pattern".

Verified on the full 815-page document: 68,835 matches, 0 duplicate roll
numbers. One remaining known cosmetic issue (1 record out of 68,835): a
trailing improvement-subject note ("ADD. BIO") can get appended to a name
when it immediately precedes the marks with no disqualifying punctuation
in between — roll_number and marks are still correct in that row, just the
name has an extra trailing word. Not worth a special case for a 1-in-68835
occurrence.
"""
import re

_PATTERN = re.compile(
    r"(?<!\d)(?P<roll_number>\d{6})(?!\d)[ ]+(?P<name>[A-Z][A-Z\.\- ]{0,39}?)[ ]+"
    r"(?<!\d)(?P<marks>\d{3,4})(?!\d)"
)


def parse(text):
    """Return a list of {"roll_number", "name", "marks"} dicts for one page
    of raw (-layout) text, skipping institute-header rows that structurally
    resemble a candidate row (see module docstring)."""
    records = []
    for m in _PATTERN.finditer(text):
        name = m.group("name").strip()
        if "SCHOOL" in name:
            continue
        records.append({
            "roll_number": int(m.group("roll_number")),
            "name": name,
            "marks": int(m.group("marks")),
            "group": None,
        })
    return records


BOARD_CONFIG = {
    "match_names": ["sargodha", "sarghoda"],
    "pattern": _PATTERN,   # kept for introspection / consistency; NOT used directly by main.py once the parser hook is present
    "parser": parse,
    "fields": ["roll_number", "name", "marks"],
}
