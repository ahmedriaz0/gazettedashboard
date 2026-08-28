"""
BISE Multan gazette format.

Sample raw line (via `pdftotext -layout`) — NOTE: this gazette prints two
candidates side-by-side per physical line (left column + right column),
unlike Lahore/Faisalabad which are one-candidate-per-line:

    100003 ADEELA MUMTAZ                         869                      100063 NIDA BATOOL
    100121 DUA IMRAN                              1143                       100181 QURAT UL AIN                        ABSENT

Fields available: roll_number, name, marks (no group/DOB info present;
this gazette is SSC-only, confirmed by sampling pages 1, 500, 700, 900
and 1043 of a 1043-page sample file — all show the same
"Secondary School Certificate (Ist Annual) Examination" header, so
"group" is never populated here).

Why this needed its own module instead of reusing an existing one
(verified against the real 1043-page / ~87.6k-row gazette):
  - lahore.py:      0 matches. Multan has no "DD/MM/YY ... PASS" token.
  - faisalabad.py:  ~45k matches instead of ~87.6k. Its regex anchors
                    marks to end-of-line ($), which only catches the
                    RIGHT-hand column here and silently drops almost
                    every LEFT-hand candidate — a ~50% silent data-loss
                    bug, not a clean failure.
  - generic.py:     0 matches. No "PASS" keyword appears anywhere.

Failed/absent handling: failing/absent candidates show either the literal
word "ABSENT" or a wrapped list of subject codes ("PHY-A CH-B BIO-A TILL
SA-2026") in place of marks. Neither is followed by a bare 3-4 digit
token, so the pattern below naturally skips them — same philosophy as
faisalabad.py, no special-casing needed.

Known edge case (rare, does not corrupt data): a handful of rows (6 out
of 87,652 sampled — ~0.007%) carry an extra remark line like
"RCD Attested Admission Form is Required" that pushes the right-hand
column's roll number onto its own separate output line, decoupling it
from that candidate's name/marks. Without a length cap, the non-greedy
name group would backtrack across the column gap and merge two
candidates into one garbled record. Capping the name group at 30 chars
(real names topped out at 25 chars in the full sample) makes those
specific matches fail to form at all, so the affected candidate is
skipped rather than corrupted. This trades ~6 dropped rows out of 87.6k
for zero corrupted rows — verified by diffing matches with/without the
cap on the full document.
"""
import re

BOARD_CONFIG = {
    "match_names": ["multan"],
    "pattern": re.compile(
        r"(?P<roll_number>\d{6})[ ]+(?P<name>[A-Z][A-Z\. ]{0,29}?)[ ]+(?P<marks>\d{3,4})\b"
    ),
    "fields": ["roll_number", "name", "marks"],
}
