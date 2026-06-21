"""Extract FIFA World Cup 2026 Regulations Annexe C into canonical CSV.

Usage: backend/.venv/bin/python scripts/extract_annex_c.py [pdf-path]
If no path is given, the official May 2026 regulations are downloaded to memory.
"""

from __future__ import annotations

import csv
import io
import re
import sys
from pathlib import Path
from urllib.request import urlopen

from pypdf import PdfReader


SOURCE_URL = "https://digitalhub.fifa.com/m/636f5c9c6f29771f/original/FWC2026_regulations_EN.pdf"
TARGETS = [79, 85, 81, 74, 82, 77, 87, 80]  # columns 1A,1B,1D,1E,1G,1I,1K,1L
ROW = re.compile(r"^\s*(\d+)\s+" + r"\s+".join([r"3([A-L])"] * 8) + r"\s*$")


def main() -> None:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    reader = PdfReader(str(source)) if source else PdfReader(io.BytesIO(urlopen(SOURCE_URL).read()))
    rows: list[tuple[str, int, str]] = []
    options: set[int] = set()
    for page in reader.pages[79:]:
        for line in (page.extract_text() or "").splitlines():
            match = ROW.match(line)
            if not match:
                continue
            option = int(match.group(1))
            groups = list(match.groups()[1:])
            options.add(option)
            qualified_set = "".join(sorted(groups))
            rows.extend((qualified_set, target, group) for target, group in zip(TARGETS, groups, strict=True))
    if options != set(range(1, 496)):
        missing = sorted(set(range(1, 496)) - options)
        raise SystemExit(f"Expected options 1-495; missing {missing[:10]}")
    output = Path(__file__).resolve().parents[1] / "data" / "seed" / "annex_c.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["qualified_group_set", "target_match_number", "third_place_group_code"])
        writer.writerows(sorted(rows))
    print(f"Wrote {len(rows)} assignments to {output}")


if __name__ == "__main__":
    main()
