"""
export_niche_template.py
------------------------
Step 1 of 2. Creates a spreadsheet (niche_grades.csv) listing every school,
with an empty 'niche_grade' column for you to fill in.

HOW TO RUN (Windows PowerShell):
    1. Put this file in the SAME folder as tennis_schools.json
    2. In that folder, run:  python export_niche_template.py
    3. Open the new niche_grades.csv in Excel or Google Sheets

If a school already has a grade in the JSON, it is pre-filled here so you
never lose progress. Keep this one CSV as your working file and fill it in
over time — you do NOT need to finish all of them before importing.
"""

import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(HERE, "tennis_schools.json")
CSV_PATH = os.path.join(HERE, "niche_grades.csv")


def main():
    if not os.path.exists(JSON_PATH):
        print(f"ERROR: Could not find tennis_schools.json next to this script.")
        print(f"       Expected it here: {JSON_PATH}")
        print(f"       Move this script into the same folder as tennis_schools.json and try again.")
        return

    with open(JSON_PATH, "r", encoding="utf-8") as f:
        schools = json.load(f)

    # Sort by state, then school name, so you can fill grades region by region.
    rows = sorted(
        schools,
        key=lambda s: ((s.get("state") or "").upper(), (s.get("school") or "").upper()),
    )

    written = 0
    # utf-8-sig adds a BOM so Excel opens accented school names correctly.
    with open(CSV_PATH, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["school", "state", "division", "niche_grade"])
        for s in rows:
            name = s.get("school")
            if not name:
                continue  # skip blank/placeholder rows in the JSON
            writer.writerow([
                name,
                s.get("state") or "",
                s.get("division") or "",
                s.get("niche_grade") or "",   # pre-fill if already set
            ])
            written += 1

    already = sum(1 for s in schools if s.get("niche_grade"))
    print(f"Done. Wrote {written} schools to:")
    print(f"   {CSV_PATH}")
    print(f"{already} of them already have a grade (pre-filled).")
    print()
    print("Next: open niche_grades.csv, fill in the 'niche_grade' column")
    print("(A+, A, A-, B+, ... leave blank if you don't have it yet),")
    print("then run:  python import_niche_grades.py")


if __name__ == "__main__":
    main()