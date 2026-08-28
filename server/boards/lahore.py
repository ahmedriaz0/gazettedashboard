"""
BISE Lahore gazette format.

Sample raw line (via `pdftotext -layout`):
    100121 AYESHA TAHIR     16/06/09 PASS 597 D

Fields available: roll_number, name, marks (dob and grade letter are in
the source but we don't store them).
"""
import re

BOARD_CONFIG = {
    "match_names": ["lahore"],
    "pattern": re.compile(
        r"(?P<roll_number>\d{6})\s+(?P<name>[A-Z][A-Z\.\s]*?)\s+"
        r"\d{2}/\d{2}/\d{2}\s+PASS\s+(?P<marks>\d{3,4})\s+[A-E]\+?"
    ),
    "fields": ["roll_number", "name", "marks"],
}
