"""Print every cleaner's items so their numbers can be checked by hand."""

from __future__ import annotations

import sys

from zarchcleaner.cleaners import CLEANERS
from zarchcleaner.models import Risk
from zarchcleaner.usage import human_size

TOTAL = 0
for cleaner in CLEANERS:
    print(f"\n## {cleaner.category} — {cleaner.title}")
    for item in cleaner.scan():
        state = "OK    " if item.available else "KOSONG"
        total = "" if item.available else ""
        print(
            f"  [{state}] {item.id:<26} {human_size(item.size):>10}  "
            f"{item.risk.value:<9} root={str(item.needs_root):<5} "
            f"default={item.enabled_default}"
        )
        print(f"           {item.title}")
        if item.note:
            print(f"           note: {item.note}")
        target = item.summary_target()
        if target:
            print(f"           target: {target}")
        if item.available:
            TOTAL += item.size

print(f"\nTotal terukur: {human_size(TOTAL)}")
sys.exit(0)
