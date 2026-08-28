"""
Fallback config used when the `board` form field doesn't match any
registered board (see boards/__init__.py's resolve_board()). Only
captures roll_number and marks via a bare "<roll> PASS <marks>" pattern
— the safest common denominator. Once you've sampled a new board's
actual layout, give it a real module (see boards/__init__.py's "HOW TO
ADD A NEW BOARD" for a template to copy) instead of relying on this.
"""
import re

BOARD_CONFIG = {
    "match_names": [],  # never matched directly; used only as the default fallback
    "pattern": re.compile(r"(?P<roll_number>\d{5,7})\s+PASS\s+(?P<marks>\d{3,4})"),
    "fields": ["roll_number", "marks"],
}
